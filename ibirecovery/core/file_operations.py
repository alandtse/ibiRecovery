# SPDX-License-Identifier: GPL-3.0-or-later
"""
File operations for ibiRecovery.

Handles file copying, metadata correction, timestamp detection,
and deduplication operations.

Copyright (C) 2024 ibiRecovery Contributors
Licensed under GPL-3.0-or-later
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def get_best_timestamp(file_metadata: Dict[str, Any]) -> Optional[float]:
    """
    Extract the best available timestamp from file metadata.

    Args:
        file_metadata: Dictionary containing metadata fields from database

    Returns:
        Timestamp in seconds since epoch, or None if no timestamp available
    """
    target_timestamp = None

    # For images, prefer imageDate
    if file_metadata.get("mimeType", "").startswith("image/"):
        target_timestamp = file_metadata.get("imageDate")

    # For videos, prefer videoDate
    elif file_metadata.get("mimeType", "").startswith("video/"):
        target_timestamp = file_metadata.get("videoDate")

    # Fall back to cTime, then birthTime
    if not target_timestamp:
        target_timestamp = file_metadata.get("cTime") or file_metadata.get("birthTime")

    if target_timestamp:
        # Convert timestamp to seconds if it appears to be in milliseconds or microseconds
        if isinstance(target_timestamp, (int, float)):
            # Detect milliseconds: timestamps > year 2200 in seconds (7258118400)
            if target_timestamp > 7258118400:  # Year 2200 in seconds
                if target_timestamp < 4102444800000:  # Year 2100 in milliseconds
                    target_timestamp = (
                        target_timestamp / 1000.0
                    )  # Convert ms to seconds
                elif target_timestamp < 4102444800000000:  # Year 2100 in microseconds
                    target_timestamp = (
                        target_timestamp / 1000000.0
                    )  # Convert μs to seconds

            # Validate timestamp is within reasonable bounds
            min_timestamp = -2208988800  # 1900-01-01
            max_timestamp = 4102444800  # 2100-01-01

            # Check for invalid values (NaN, infinity, extreme values)
            if (
                isinstance(target_timestamp, (int, float))
                and target_timestamp == target_timestamp  # NaN check
                and min_timestamp <= target_timestamp <= max_timestamp
            ):
                return target_timestamp

    return None


def get_time_organized_path(
    base_dir: Path, filename: str, file_metadata: Dict[str, Any]
) -> Path:
    """
    Get the time-organized path for a file within the base directory.

    Args:
        base_dir: Base directory for organization
        filename: Original filename
        file_metadata: File metadata dictionary

    Returns:
        Path organized as base_dir/YYYY/MM/filename
    """
    timestamp = get_best_timestamp(file_metadata)

    if timestamp:
        # Organize by year/month
        date_obj = datetime.fromtimestamp(timestamp)
        year_dir = base_dir / str(date_obj.year)
        month_dir = year_dir / f"{date_obj.month:02d}"
        return month_dir / filename
    else:
        # Fallback: put in a "Unknown_Date" subdirectory
        unknown_dir = base_dir / "Unknown_Date"
        return unknown_dir / filename


def set_file_metadata(
    dest: Path, file_metadata: Dict[str, Any], track_corrections: bool = False
) -> bool:
    """
    Set file timestamps based on database metadata.

    Args:
        dest: Destination file path
        file_metadata: Dictionary containing metadata fields from database

    Returns:
        True if successful, False otherwise
    """
    try:
        target_timestamp = get_best_timestamp(file_metadata)

        if target_timestamp:
            # Set both access and modification times to the target timestamp
            os.utime(dest, (target_timestamp, target_timestamp))
            return True

    except (OSError, TypeError, ValueError, OverflowError) as e:
        # Don't fail the whole copy operation for metadata issues
        print(f"Warning: Could not set metadata for {dest}: {e}")

    return False


def check_rsync_available() -> bool:
    """Check if rsync is available on the system."""
    try:
        result = subprocess.run(
            ["rsync", "--version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def copy_file_rsync(
    source: Path,
    dest: Path,
    resume: bool = True,
    file_metadata: Optional[Dict[str, Any]] = None,
    fix_metadata: bool = True,
) -> bool:
    """
    Copy file using rsync with resume capability and metadata correction.

    Args:
        source: Source file path
        dest: Destination file path
        resume: Whether to resume partial transfers
        file_metadata: Optional metadata dictionary for timestamp correction

    Returns:
        True if successful, False otherwise
    """
    try:
        cmd = ["rsync", "-av"]
        if resume:
            cmd.append("--partial")
        cmd.extend([str(source), str(dest)])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        success = result.returncode == 0

        # Set correct metadata timestamps if provided and copy succeeded
        if success and file_metadata and fix_metadata:
            set_file_metadata(dest, file_metadata)

        return success
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        return False


def copy_file_fallback(
    source: Path,
    dest: Path,
    resume: bool = True,
    file_metadata: Optional[Dict[str, Any]] = None,
    fix_metadata: bool = True,
) -> bool:
    """
    Fallback file copy using Python's built-in functions.

    Args:
        source: Source file path
        dest: Destination file path
        resume: Whether to skip if destination exists (resume behavior)
        file_metadata: Optional metadata for timestamp correction
        fix_metadata: Whether to apply metadata corrections

    Returns:
        True if successful, False otherwise
    """
    try:
        # If resuming and destination exists with same size, skip
        if resume and dest.exists():
            if dest.stat().st_size == source.stat().st_size:
                # File already copied, just correct metadata if needed
                if file_metadata and fix_metadata:
                    set_file_metadata(dest, file_metadata)
                return True

        # Create parent directory if needed
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Copy the file
        import shutil

        shutil.copy2(source, dest)

        # Set correct metadata timestamps if provided
        if file_metadata and fix_metadata:
            set_file_metadata(dest, file_metadata)

        return True

    except (OSError, IOError) as e:
        print(f"Error copying {source} to {dest}: {e}")
        return False
