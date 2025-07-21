#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
ibiRecovery Enhanced File Extraction Script

This script extracts files from recovered ibi databases with advanced features:
- Auto-detects ibi directory structure from root path
- Progress bars for file operations
- Resumable operations using rsync with fallback
- Default: Extract by albums + unorganized files (recommended)
- Option: Extract by file type (images, videos, documents)
- Always: Ensures 100% file recovery including orphaned content

Copyright (C) 2024 ibiRecovery Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import argparse
import csv
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import from core modules for modular functionality
try:
    from .core import MetadataExporter as CoreMetadataExporter
    from .core import check_rsync_available as core_check_rsync_available
    from .core import comprehensive_audit as core_comprehensive_audit
    from .core import connect_db as core_connect_db
    from .core import copy_file_fallback as core_copy_file_fallback
    from .core import copy_file_rsync as core_copy_file_rsync
    from .core import detect_ibi_structure as core_detect_ibi_structure
    from .core import export_metadata_formats as core_export_metadata_formats
    from .core import find_source_file as core_find_source_file
    from .core import format_size as core_format_size
    from .core import get_all_files_with_albums as core_get_all_files_with_albums
    from .core import get_best_timestamp as core_get_best_timestamp
    from .core import (
        get_comprehensive_export_data as core_get_comprehensive_export_data,
    )
    from .core import get_merged_files_with_albums as core_get_merged_files_with_albums
    from .core import get_time_organized_path as core_get_time_organized_path
    from .core import scan_files_directory as core_scan_files_directory
    from .core import set_file_metadata as core_set_file_metadata
    from .core import verify_file_availability as core_verify_file_availability

    CORE_MODULES_AVAILABLE = True
except ImportError:
    CORE_MODULES_AVAILABLE = False

# Optional dependencies with graceful fallback
try:
    from tqdm import tqdm

    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# Enhanced progress fallback if tqdm not available
if not HAS_TQDM:
    import time

    class tqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.iterable = iterable
            self.total = total or (len(iterable) if iterable else 0)
            self.desc = desc or ""
            self.n = 0
            self.start_time = time.time()

        def __iter__(self):
            if self.iterable:
                for item in self.iterable:
                    yield item
                    self.update(1)
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            print()  # Newline after progress

        def update(self, n=1):
            self.n += n
            if self.total > 0 and self.n > 0:
                percent = (self.n / self.total) * 100
                elapsed = time.time() - self.start_time
                rate = self.n / elapsed if elapsed > 0 else 0

                if rate > 0 and self.n < self.total:
                    remaining_items = self.total - self.n
                    eta_seconds = remaining_items / rate
                    eta_str = (
                        f", ETA: {int(eta_seconds//60):02d}:{int(eta_seconds%60):02d}"
                    )
                else:
                    eta_str = ""

                elapsed_str = f"{int(elapsed//60):02d}:{int(elapsed%60):02d}"
                rate_str = f", {rate:.1f} files/s" if rate > 0 else ""

                print(
                    f"\r{self.desc}: {self.n}/{self.total} ({percent:.1f}%) "
                    f"[{elapsed_str}{eta_str}{rate_str}]",
                    end="",
                    flush=True,
                )


# Optional metadata dependencies
try:
    from PIL import Image
    from PIL.ExifTags import GPSTAGS, TAGS

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import exifread

    HAS_EXIFREAD = True
except ImportError:
    HAS_EXIFREAD = False


class ExtractionState:
    """Global state for tracking extraction progress and handling interrupts."""

    def __init__(self):
        self.interrupted = False
        self.total_files_extracted = 0
        self.total_size_extracted = 0
        self.current_operation = "Initializing"
        self.start_time = None

    def signal_handler(self, signum, frame):
        """Handle keyboard interrupt gracefully."""
        self.interrupted = True
        print(f"\n\n⚠️  Extraction interrupted by user (Ctrl+C)")
        print(f"📊 Progress before interruption:")
        print(f"   Files extracted: {self.total_files_extracted}")
        print(f"   Data extracted: {format_size(self.total_size_extracted)}")
        print(f"   Current operation: {self.current_operation}")
        print(f"\n💡 You can resume this extraction by running the same command again.")
        print(
            f"   The --resume flag (enabled by default) will skip already-copied files."
        )
        sys.exit(0)


# Global extraction state
extraction_state = ExtractionState()


def detect_ibi_structure(
    root_path: Path,
) -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """
    Auto-detect ibi database and files directory structure.

    Returns:
        Tuple of (db_path, files_path, backup_db_path) or (None, None, None) if not found
    """
    if CORE_MODULES_AVAILABLE:
        return core_detect_ibi_structure(root_path)

    # Fallback implementation
    root_path = Path(root_path)

    # Common ibi directory structures to check
    candidates = [
        # Standard structure: root/restsdk/data/
        (
            root_path / "restsdk" / "data" / "db" / "index.db",
            root_path / "restsdk" / "data" / "files",
            root_path / "restsdk" / "data" / "dbBackup" / "index.db",
        ),
        # Alternative: direct in data folder
        (
            root_path / "data" / "db" / "index.db",
            root_path / "data" / "files",
            root_path / "data" / "dbBackup" / "index.db",
        ),
        # Alternative: root contains db and files directly
        (
            root_path / "db" / "index.db",
            root_path / "files",
            root_path / "dbBackup" / "index.db",
        ),
        # Alternative: index.db in root
        (
            root_path / "index.db",
            root_path / "files",
            root_path / "dbBackup" / "index.db",
        ),
    ]

    for db_path, files_path, backup_db_path in candidates:
        if db_path.exists() and files_path.exists():
            # Check if backup database exists
            backup_exists = backup_db_path.exists()

            print(f"✅ Detected ibi structure:")
            print(f"   Database: {db_path}")
            print(f"   Files: {files_path}")
            if backup_exists:
                print(f"   Backup DB: {backup_db_path}")
            else:
                print(f"   Backup DB: Not found (optional)")
                backup_db_path = None

            return db_path, files_path, backup_db_path

    return None, None, None


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


def get_organized_path(
    base_dir: Path,
    filename: str,
    file_metadata: Dict[str, Any],
    use_time_organization: bool = True,
) -> Path:
    """
    Get the organized path for a file within the base directory.

    Args:
        base_dir: Base directory for organization
        filename: Original filename
        file_metadata: File metadata dictionary
        use_time_organization: If True, organize by time; if False, use flat structure

    Returns:
        Path organized as base_dir/YYYY/MM/filename or base_dir/filename
    """
    if not use_time_organization:
        return base_dir / filename

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


def get_time_organized_path(
    base_dir: Path, filename: str, file_metadata: Dict[str, Any]
) -> Path:
    """Legacy function - use get_organized_path instead"""
    return get_organized_path(
        base_dir, filename, file_metadata, use_time_organization=True
    )


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


def copy_file_fallback(
    source: Path,
    dest: Path,
    resume: bool = True,
    file_metadata: Optional[Dict[str, Any]] = None,
    fix_metadata: bool = True,
) -> bool:
    """
    Fallback file copy using shutil with basic resume support and metadata correction.

    Args:
        source: Source file path
        dest: Destination file path
        resume: Whether to skip if destination exists and has same size
        file_metadata: Optional metadata dictionary for timestamp correction

    Returns:
        True if successful, False otherwise
    """
    try:
        # Simple resume: skip if destination exists and has same size
        if resume and dest.exists():
            if dest.stat().st_size == source.stat().st_size:
                # Still try to correct metadata if provided
                if file_metadata and fix_metadata:
                    set_file_metadata(dest, file_metadata)
                return True

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

        # Set correct metadata timestamps if provided
        if file_metadata and fix_metadata:
            set_file_metadata(dest, file_metadata)

        return True
    except (OSError, shutil.Error):
        return False


def deduplicate_existing_extraction(
    output_dir: Path,
    use_hardlinks: bool = True,
    use_symlinks: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Post-process an existing extraction to deduplicate files using hardlinks or symlinks.

    Args:
        output_dir: Directory containing extracted files to deduplicate
        use_hardlinks: Whether to use hardlinks for deduplication
        use_symlinks: Whether to use symlinks for deduplication
        dry_run: If True, only report what would be done without making changes

    Returns:
        Dictionary with deduplication statistics
    """
    print(f"🔍 SCANNING EXISTING EXTRACTION FOR DEDUPLICATION")
    print(f"Directory: {output_dir}")
    print(
        f"Mode: {'Hardlinks' if use_hardlinks else 'Symlinks' if use_symlinks else 'Analysis only'}"
    )
    print(f"Dry run: {'Yes' if dry_run else 'No'}")
    print("=" * 60)

    # Scan all files and group by content
    files_by_content = defaultdict(list)
    total_files = 0
    total_size = 0

    print("Scanning files by content...")
    for file_path in output_dir.rglob("*"):
        if file_path.is_file() and not file_path.is_symlink():
            try:
                stat = file_path.stat()
                # Use size and first/last 1KB as content signature for performance
                with open(file_path, "rb") as f:
                    start_bytes = f.read(1024)
                    f.seek(
                        -min(1024, stat.st_size), 2
                    ) if stat.st_size > 1024 else f.seek(0)
                    end_bytes = f.read(1024)

                content_sig = f"{stat.st_size}:{hash(start_bytes)}:{hash(end_bytes)}"
                files_by_content[content_sig].append((file_path, stat.st_size))
                total_files += 1
                total_size += stat.st_size
            except (OSError, IOError) as e:
                print(f"Warning: Could not read {file_path}: {e}")

    # Find duplicates
    duplicates = {
        sig: files for sig, files in files_by_content.items() if len(files) > 1
    }

    print(f"\nFound {total_files} files ({format_size(total_size)} total)")
    print(f"Found {len(duplicates)} groups of duplicate files")

    if not duplicates:
        print("No duplicates found - extraction is already optimal!")
        return {"duplicates": 0, "space_saved": 0, "files_processed": 0}

    # Process duplicates
    stats = {"hardlinked": 0, "symlinked": 0, "errors": 0, "space_saved": 0}

    for content_sig, file_list in duplicates.items():
        if len(file_list) < 2:
            continue

        # Sort by path to ensure consistent behavior
        file_list.sort(key=lambda x: str(x[0]))
        primary_file, primary_size = file_list[0]
        duplicate_files = file_list[1:]

        print(
            f"\nProcessing {len(duplicate_files)} duplicates of {primary_file.name} ({format_size(primary_size)})"
        )

        for dup_file, dup_size in duplicate_files:
            if dry_run:
                print(
                    f"  Would {'hardlink' if use_hardlinks else 'symlink'}: {dup_file}"
                )
                stats["space_saved"] += dup_size
                continue

            try:
                # Backup original file temporarily
                backup_file = dup_file.with_suffix(dup_file.suffix + ".dedup_backup")
                dup_file.rename(backup_file)

                # Create link
                if use_hardlinks and not use_symlinks:
                    os.link(str(primary_file), str(dup_file))
                    action = "hardlinked"
                elif use_symlinks:
                    dup_file.symlink_to(primary_file)
                    action = "symlinked"
                else:
                    # Restore backup and skip
                    backup_file.rename(dup_file)
                    continue

                # Verify link was created successfully
                if dup_file.exists() and dup_file.stat().st_size == primary_size:
                    # Success - remove backup
                    backup_file.unlink()
                    stats[action] += 1
                    stats["space_saved"] += dup_size
                    print(f"  ✅ {action}: {dup_file}")
                else:
                    # Failed - restore backup
                    dup_file.unlink(missing_ok=True)
                    backup_file.rename(dup_file)
                    stats["errors"] += 1
                    print(f"  ❌ Failed to {action}: {dup_file}")

            except OSError as e:
                # Restore backup if it exists
                backup_file = dup_file.with_suffix(dup_file.suffix + ".dedup_backup")
                if backup_file.exists():
                    dup_file.unlink(missing_ok=True)
                    backup_file.rename(dup_file)
                stats["errors"] += 1
                print(f"  ❌ Error processing {dup_file}: {e}")

    # Summary
    print(f"\n📊 DEDUPLICATION SUMMARY:")
    print(f"   Files hardlinked: {stats['hardlinked']}")
    print(f"   Files symlinked: {stats['symlinked']}")
    print(f"   Errors: {stats['errors']}")
    print(f"   Space saved: {format_size(stats['space_saved'])}")

    return stats


def copy_file_with_dedup(
    source: Path,
    dest: Path,
    resume: bool = True,
    use_hardlinks: bool = True,
    use_symlinks: bool = False,
    copy_tracker: Dict[str, Path] = None,
    file_metadata: Optional[Dict[str, Any]] = None,
    fix_metadata: bool = True,
) -> Tuple[bool, str]:
    """
    Copy file with deduplication support using hardlinks or symlinks for duplicates.

    Args:
        source: Source file path
        dest: Destination file path
        resume: Whether to skip if destination exists and has same size
        use_hardlinks: Whether to use hardlinks for duplicate files (default: True)
        use_symlinks: Whether to use symlinks for duplicate files (default: False)
        copy_tracker: Dictionary tracking content_id -> first copy location
        file_metadata: Optional metadata dictionary for timestamp correction

    Returns:
        Tuple of (success: bool, action: str) where action is 'copied', 'hardlinked', 'symlinked', or 'skipped'
    """
    if copy_tracker is None:
        copy_tracker = {}

    try:
        # Simple resume: skip if destination exists and has same size
        if resume and dest.exists():
            if dest.stat().st_size == source.stat().st_size:
                # Still try to correct metadata if provided
                if file_metadata and fix_metadata:
                    set_file_metadata(dest, file_metadata)
                return True, "skipped"

        # Ensure destination directory exists
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Get source file stats - needed for both deduplication and copy operations
        source_stat = source.stat()

        # Generate content identifier - prefer database content_id if available in metadata
        if file_metadata and "contentID" in file_metadata:
            content_key = file_metadata["contentID"]
        else:
            # Fallback to source file properties for non-database files
            content_key = f"{source}:{source_stat.st_size}:{source_stat.st_mtime}"

        # Check if we've already copied this exact file
        if content_key in copy_tracker:
            first_copy_path = copy_tracker[content_key]

            # Verify the first copy still exists and is valid
            if (
                first_copy_path.exists()
                and first_copy_path.stat().st_size == source_stat.st_size
            ):
                try:
                    if use_hardlinks and not use_symlinks:
                        # Try hardlink first (more robust, saves actual space)
                        dest.unlink(missing_ok=True)  # Remove if exists
                        os.link(str(first_copy_path), str(dest))
                        # For hardlinks, metadata is automatically shared with original
                        return True, "hardlinked"
                    elif use_symlinks:
                        # Use symlink (saves space but creates dependency)
                        dest.unlink(missing_ok=True)  # Remove if exists
                        dest.symlink_to(first_copy_path)
                        # For symlinks, metadata is automatically shared with original
                        return True, "symlinked"
                except OSError:
                    # Fall back to copy if linking fails (e.g., cross-filesystem)
                    pass

        # Perform regular copy
        shutil.copy2(source, dest)

        # Set correct metadata timestamps if provided
        if file_metadata and fix_metadata:
            set_file_metadata(dest, file_metadata)

        # Track this as the first copy for future deduplication
        copy_tracker[content_key] = dest

        return True, "copied"

    except (OSError, shutil.Error) as e:
        print(f"Error copying {source} to {dest}: {e}")
        return False, "error"


def connect_db(db_path: Path) -> sqlite3.Connection:
    """Connect to the SQLite database."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def connect_db_readonly(db_path: Path):
    """Connect to the SQLite database in read-only mode - fallback implementation."""
    import tempfile

    try:
        # First try direct URI syntax for read-only access
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        # Test if we can actually query the database with a real table
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1"
        ).fetchone()
        return conn
    except sqlite3.Error:
        # Fallback: copy database to temporary location for read access
        # This handles mounted filesystems where URI syntax fails
        try:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
                shutil.copy2(db_path, tmp_file.name)
                conn = sqlite3.connect(tmp_file.name)
                conn.row_factory = sqlite3.Row
                return conn
        except Exception as e:
            print(f"Error connecting to database in read-only mode: {e}")
            raise


def find_source_file(
    files_dir: Path,
    content_id: str,
    file_name: str = None,
    storage_id: str = None,
    db_path: Path = None,
) -> Optional[Path]:
    """Find the actual file using contentID with userStorage support."""
    if CORE_MODULES_AVAILABLE:
        # Use enhanced version that supports userStorage
        return core_find_source_file(
            files_dir, content_id, file_name, storage_id, db_path
        )

    # Fallback for traditional ibi structure only
    if not content_id:
        return None

    # Try different directory structures based on contentID
    possible_paths = [
        files_dir
        / content_id[0]
        / content_id,  # Most common: /files/j/jT9JduP8vIHpwuY32gLQ
        files_dir / content_id[:2] / content_id[2:4] / content_id,
        files_dir / content_id,
    ]

    for path in possible_paths:
        if path.exists():
            return path

    return None


def get_all_files_with_albums(
    conn: sqlite3.Connection,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Get all files with their album memberships and calculate statistics."""
    # First get all files with size information
    files_query = """
    SELECT f.id, f.name, f.contentID, f.mimeType, f.size,
           f.imageDate, f.videoDate, f.cTime, f.storageID
    FROM Files f
    WHERE f.contentID IS NOT NULL AND f.contentID != ''
    ORDER BY COALESCE(f.videoDate, f.imageDate, f.cTime)
    """

    files = conn.execute(files_query).fetchall()

    # Calculate statistics
    total_size = 0
    file_count = len(files)
    size_by_type = defaultdict(int)

    for file_record in files:
        size = file_record["size"] or 0
        total_size += size

        mime_type = file_record["mimeType"] or ""
        if mime_type.startswith("image/"):
            size_by_type["images"] += size
        elif mime_type.startswith("video/"):
            size_by_type["videos"] += size
        elif mime_type.startswith("application/") or mime_type.startswith("text/"):
            size_by_type["documents"] += size
        else:
            size_by_type["other"] += size

    # Get album memberships for all files
    album_query = """
    SELECT fgf.fileID, fg.name as album_name, fg.id as album_id
    FROM FileGroupFiles fgf
    JOIN FileGroups fg ON fgf.fileGroupID = fg.id
    ORDER BY fg.estCount DESC
    """

    # Build album membership map
    file_albums = defaultdict(list)
    for row in conn.execute(album_query):
        file_albums[row["fileID"]].append(
            {"name": row["album_name"], "id": row["album_id"]}
        )

    # Combine files with their albums
    files_with_albums = []
    for file_record in files:
        files_with_albums.append(
            {
                "file": dict(file_record),
                "albums": file_albums.get(file_record["id"], []),
            }
        )

    # Prepare statistics
    stats = {
        "total_files": file_count,
        "total_size": total_size,
        "size_by_type": dict(size_by_type),
    }

    return files_with_albums, stats


def sanitize_album_name(album_name: str) -> tuple[str, bool]:
    """
    Sanitize album name for filesystem compatibility while preserving as much as possible.

    Returns:
        tuple: (sanitized_name, name_was_changed)
    """
    if not album_name:
        return "Unknown_Album_Empty", True

    original_name = album_name

    # First, strip leading/trailing whitespace
    sanitized = album_name.strip()

    # If only whitespace, create descriptive name
    if not sanitized:
        return "Unknown_Album_Whitespace", True

    # Replace problematic characters with safe alternatives
    char_replacements = {
        "/": "_",  # Forward slash -> underscore
        "\\": "_",  # Backslash -> underscore
        ":": "-",  # Colon -> dash
        "*": "_star_",  # Asterisk -> word
        "?": "_",  # Question mark -> underscore
        '"': "'",  # Double quote -> single quote
        "<": "(",  # Less than -> parenthesis
        ">": ")",  # Greater than -> parenthesis
        "|": "_",  # Pipe -> underscore
        "\t": " ",  # Tab -> space
        "\n": " ",  # Newline -> space
        "\r": " ",  # Carriage return -> space
    }

    # Apply character replacements
    for bad_char, replacement in char_replacements.items():
        sanitized = sanitized.replace(bad_char, replacement)

    # Collapse multiple spaces into single spaces
    sanitized = " ".join(sanitized.split())

    # Remove any remaining non-printable characters
    sanitized = "".join(c for c in sanitized if c.isprintable())

    # Handle edge cases after sanitization
    if not sanitized:
        # If nothing printable remains, create descriptive name
        non_printable_count = len([c for c in original_name if not c.isprintable()])
        return f"Unknown_Album_NonPrintable_{non_printable_count}chars", True

    # Limit length to avoid filesystem issues (most filesystems support 255 chars)
    if len(sanitized) > 100:  # Conservative limit for compatibility
        sanitized = sanitized[:97] + "..."

    # Check if any changes were made
    name_changed = sanitized != original_name

    return sanitized, name_changed


def format_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1

    return f"{size_bytes:.1f} {size_names[i]}"


def scan_files_directory(files_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Scan all files in the files directory."""
    disk_files = {}

    print("Scanning all files on disk...")

    # Walk through all subdirectories
    for subdir in files_dir.iterdir():
        if not subdir.is_dir():
            continue

        for file_path in subdir.iterdir():
            if file_path.is_file():
                content_id = file_path.name
                try:
                    stat = file_path.stat()
                    disk_files[content_id] = {
                        "path": file_path,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                except (OSError, IOError):
                    continue

    return disk_files


def comprehensive_audit(
    files_with_albums: List[Dict[str, Any]],
    files_dir: Path,
    audit_report_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Perform comprehensive audit comparing database with disk."""
    import csv
    from collections import defaultdict

    print("=" * 60)
    print("📊 COMPREHENSIVE FILE AUDIT")
    print("=" * 60)

    # Build database files dict
    db_files = {}
    for item in files_with_albums:
        # Handle both flat format and nested format from get_all_files_with_albums
        if "file" in item:
            file_record = item["file"]
        else:
            file_record = item

        content_id = file_record.get("contentID")
        if content_id:
            db_files[content_id] = file_record

    # Scan all files on disk
    disk_files = scan_files_directory(files_dir)

    print(f"Database files: {len(db_files)}")
    print(f"Disk files: {len(disk_files)}")

    # Cross-reference analysis
    matched_files = {}
    missing_files = {}
    orphaned_files = {}
    size_mismatches = {}

    # Check database files against disk
    progress = (
        tqdm(
            db_files.items(),
            desc="Analyzing files",
            unit="files",
            unit_scale=False,
            dynamic_ncols=True,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        )
        if HAS_TQDM
        else db_files.items()
    )

    for content_id, db_record in progress:
        if content_id in disk_files:
            disk_info = disk_files[content_id]
            db_size = db_record.get("size", 0)
            disk_size = disk_info["size"]

            matched_files[content_id] = {
                "db_record": db_record,
                "disk_info": disk_info,
                "db_size": db_size,
                "disk_size": disk_size,
            }

            # Check for size mismatches
            if db_size and abs(db_size - disk_size) > 1024:  # Allow 1KB tolerance
                size_mismatches[content_id] = {
                    "file_name": db_record.get("name", "Unknown"),
                    "db_size": db_size,
                    "actual_size": disk_size,
                    "difference": disk_size - db_size,
                }
        else:
            missing_files[content_id] = db_record

    # Find orphaned files (on disk but not in database)
    for content_id, disk_info in disk_files.items():
        if content_id not in db_files:
            orphaned_files[content_id] = disk_info

    # Calculate statistics
    recovery_rate = (len(matched_files) / len(db_files)) * 100 if db_files else 0

    # Print summary
    print(f"\n📊 AUDIT RESULTS:")
    print(f"   Matched files: {len(matched_files)}")
    print(f"   Missing files (in DB but not on disk): {len(missing_files)}")
    print(f"   Orphaned files (on disk but not in DB): {len(orphaned_files)}")
    print(f"   Size mismatches: {len(size_mismatches)}")
    print(f"   Recovery rate: {recovery_rate:.1f}%")

    # Show details for missing files
    if missing_files:
        print(f"\n❌ MISSING FILES (first 10):")
        for i, (content_id, record) in enumerate(list(missing_files.items())[:10]):
            print(
                f"   {record.get('name', 'Unknown')} ({record.get('mimeType', 'Unknown')})"
            )
        if len(missing_files) > 10:
            print(f"   ... and {len(missing_files) - 10} more")

    # Show details for size mismatches
    if size_mismatches:
        print(f"\n⚠️  SIZE MISMATCHES (first 10):")
        for i, (content_id, mismatch) in enumerate(list(size_mismatches.items())[:10]):
            diff_pct = (
                (mismatch["difference"] / mismatch["db_size"]) * 100
                if mismatch["db_size"] > 0
                else 0
            )
            print(
                f"   {mismatch['file_name']}: DB={format_size(mismatch['db_size'])}, "
                f"Disk={format_size(mismatch['actual_size'])} ({diff_pct:+.1f}%)"
            )
        if len(size_mismatches) > 10:
            print(f"   ... and {len(size_mismatches) - 10} more")

    # Generate detailed reports if requested
    if audit_report_dir:
        audit_report_dir.mkdir(parents=True, exist_ok=True)

        # JSON report
        audit_report = {
            "summary": {
                "timestamp": datetime.now().isoformat(),
                "database_files": len(db_files),
                "disk_files": len(disk_files),
                "matched_files": len(matched_files),
                "missing_files": len(missing_files),
                "orphaned_files": len(orphaned_files),
                "size_mismatches": len(size_mismatches),
                "recovery_rate": recovery_rate,
            },
            "matched_files": {
                k: {
                    "name": v["db_record"].get("name"),
                    "mime_type": v["db_record"].get("mimeType"),
                    "db_size": v["db_size"],
                    "disk_size": v["disk_size"],
                }
                for k, v in matched_files.items()
            },
            "missing_files": {
                k: {
                    "name": v.get("name"),
                    "mime_type": v.get("mimeType"),
                    "size": v.get("size"),
                }
                for k, v in missing_files.items()
            },
            "orphaned_files": {
                k: {"size": v["size"], "path": str(v["path"])}
                for k, v in orphaned_files.items()
            },
            "size_mismatches": size_mismatches,
        }

        report_file = audit_report_dir / "audit_report.json"
        with open(report_file, "w") as f:
            json.dump(audit_report, f, indent=2)

        # CSV summary
        csv_file = audit_report_dir / "audit_summary.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Type",
                    "ContentID",
                    "FileName",
                    "MimeType",
                    "DBSize",
                    "DiskSize",
                    "Status",
                ]
            )

            for content_id, match in matched_files.items():
                status = "Size Mismatch" if content_id in size_mismatches else "OK"
                writer.writerow(
                    [
                        "Matched",
                        content_id,
                        match["db_record"].get("name", ""),
                        match["db_record"].get("mimeType", ""),
                        match["db_size"],
                        match["disk_size"],
                        status,
                    ]
                )

            for content_id, record in missing_files.items():
                writer.writerow(
                    [
                        "Missing",
                        content_id,
                        record.get("name", ""),
                        record.get("mimeType", ""),
                        record.get("size", 0),
                        0,
                        "Missing from disk",
                    ]
                )

            for content_id, disk_info in orphaned_files.items():
                writer.writerow(
                    [
                        "Orphaned",
                        content_id,
                        "",
                        "",
                        0,
                        disk_info["size"],
                        "Not in database",
                    ]
                )

        print(f"\n📁 DETAILED REPORTS SAVED:")
        print(f"   JSON report: {report_file}")
        print(f"   CSV summary: {csv_file}")

    # Return results in same format as quick verification
    total_size = sum(match["db_size"] for match in matched_files.values())
    return {
        "total_files": len(db_files),
        "sample_size": len(db_files),
        "available_count": len(matched_files),
        "missing_count": len(missing_files),
        "availability_rate": recovery_rate,
        "available_size": total_size,
        "total_sample_size": total_size,
        "orphaned_count": len(orphaned_files),
        "size_mismatches": len(size_mismatches),
        "comprehensive": True,
    }


def analyze_deduplication_potential(
    files_with_albums: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Analyze deduplication potential by finding files with same content_id."""
    from collections import Counter, defaultdict

    content_id_counts = Counter()
    content_id_files = defaultdict(list)
    total_files = 0
    total_size = 0

    # Count content_id occurrences
    for item in files_with_albums:
        file_record = item["file"]
        content_id = file_record.get("contentID")
        if content_id:
            content_id_counts[content_id] += 1
            content_id_files[content_id].append(file_record)
            total_files += 1
            total_size += file_record.get("size", 0)

    # Find duplicates
    duplicates = {cid: count for cid, count in content_id_counts.items() if count > 1}
    duplicate_files = sum(count for count in duplicates.values())
    unique_files = len(content_id_counts)
    space_saveable = sum(
        (count - 1) * content_id_files[cid][0].get("size", 0)
        for cid, count in duplicates.items()
    )

    # Calculate potential deduplication rate
    dedup_rate = (
        ((duplicate_files - len(duplicates)) / total_files * 100)
        if total_files > 0
        else 0
    )
    space_save_rate = (space_saveable / total_size * 100) if total_size > 0 else 0

    print(f"\n📊 DEDUPLICATION ANALYSIS:")
    print(f"   Total file entries in albums: {total_files}")
    print(f"   Unique content files: {unique_files}")
    print(f"   Duplicate content_ids: {len(duplicates)}")
    print(f"   Total duplicate entries: {duplicate_files - len(duplicates)}")
    print(f"   Potential deduplication rate: {dedup_rate:.1f}%")
    print(
        f"   Potential space savings: {format_size(space_saveable)} ({space_save_rate:.1f}%)"
    )

    if duplicates:
        print(f"\n📋 TOP DUPLICATED FILES:")
        # Show top 10 most duplicated files
        top_duplicates = sorted(duplicates.items(), key=lambda x: x[1], reverse=True)[
            :10
        ]
        for content_id, count in top_duplicates:
            sample_file = content_id_files[content_id][0]
            size = sample_file.get("size", 0)
            name = sample_file.get("name", "Unknown")
            print(
                f"   {name}: {count} copies, {format_size(size)} each, saves {format_size((count-1)*size)}"
            )

    return {
        "total_files": total_files,
        "unique_files": unique_files,
        "duplicate_content_ids": len(duplicates),
        "duplicate_entries": duplicate_files - len(duplicates),
        "deduplication_rate": dedup_rate,
        "space_saveable": space_saveable,
        "space_save_rate": space_save_rate,
        "top_duplicates": dict(
            sorted(duplicates.items(), key=lambda x: x[1], reverse=True)[:20]
        ),
    }


def verify_file_availability(
    files_with_albums: List[Dict[str, Any]],
    files_dir: Path,
    sample_size: int = 100,
    audit_report_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Verify file availability by checking files (sample or comprehensive audit)."""
    import random

    total_files = len(files_with_albums)
    if total_files == 0:
        return {
            "total_files": 0,
            "sample_size": 0,
            "available_count": 0,
            "missing_count": 0,
            "availability_rate": 0.0,
            "available_size": 0,
            "total_sample_size": 0,
        }

    # Determine if this is comprehensive audit mode
    is_comprehensive = sample_size == 0 or audit_report_dir is not None
    files_to_check = (
        files_with_albums
        if is_comprehensive
        else random.sample(files_with_albums, min(sample_size, total_files))
    )

    print(f"{'📊 COMPREHENSIVE AUDIT' if is_comprehensive else '🔍 QUICK VERIFICATION'}")
    print(
        f"Checking {len(files_to_check)} files{'(all files)' if is_comprehensive else f'(sample)'}"
    )

    # For comprehensive audit, we need additional tracking
    if is_comprehensive:
        # Also analyze deduplication potential during comprehensive audit
        analyze_deduplication_potential(files_with_albums)
        return comprehensive_audit(files_with_albums, files_dir, audit_report_dir)

    # Continue with existing quick verification logic for samples

    # Take a random sample
    sample_size = min(sample_size, total_files)
    sample_files = random.sample(files_with_albums, sample_size)

    available_count = 0
    missing_count = 0
    available_size = 0
    total_sample_size = 0

    print(f"Checking availability of {sample_size} sample files...")

    for item in sample_files:
        file_record = item["file"]
        content_id = file_record.get("contentID")
        file_size = file_record.get("size", 0) or 0
        total_sample_size += file_size

        if content_id:
            source_path = find_source_file(files_dir, content_id)
            if source_path and source_path.exists():
                available_count += 1
                available_size += file_size
            else:
                missing_count += 1
        else:
            missing_count += 1

    availability_rate = (available_count / sample_size) * 100 if sample_size > 0 else 0

    return {
        "total_files": total_files,
        "sample_size": sample_size,
        "available_count": available_count,
        "missing_count": missing_count,
        "availability_rate": availability_rate,
        "available_size": available_size,
        "total_sample_size": total_sample_size,
    }


def get_comprehensive_export_data(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Get all files with their metadata, tags, and albums for export."""

    # Main query - portable metadata only
    query = """
    SELECT f.id, f.name, f.contentID, f.mimeType, f.size,
           f.imageDate, f.videoDate, f.cTime, f.birthTime,
           f.imageLatitude, f.imageLongitude, f.imageAltitude,
           f.imageCity, f.imageProvince, f.imageCountry,
           f.videoLatitude, f.videoLongitude, f.videoAltitude,
           f.videoCity, f.videoProvince, f.videoCountry,
           f.imageCameraMake, f.imageCameraModel,
           f.description
    FROM Files f
    WHERE f.contentID IS NOT NULL AND f.contentID != ''
    ORDER BY COALESCE(f.videoDate, f.imageDate, f.cTime)
    """

    files = list(conn.execute(query).fetchall())

    # Get tags for all files
    tag_query = """
    SELECT fileID, tag, auto
    FROM FilesTags
    ORDER BY fileID, tag
    """
    tags_by_file = defaultdict(list)
    for row in conn.execute(tag_query):
        tags_by_file[row["fileID"]].append(
            {"tag": row["tag"], "auto": bool(row["auto"])}
        )

    # Get albums for all files
    album_query = """
    SELECT fgf.fileID, fg.name as album_name, fg.description as album_description
    FROM FileGroupFiles fgf
    JOIN FileGroups fg ON fgf.fileGroupID = fg.id
    ORDER BY fgf.fileID, fg.name
    """
    albums_by_file = defaultdict(list)
    for row in conn.execute(album_query):
        albums_by_file[row["fileID"]].append(
            {"name": row["album_name"], "description": row["album_description"]}
        )

    # Combine data
    complete_data = []
    for file_record in files:
        file_id = file_record["id"]
        complete_data.append(
            {
                "file_record": dict(file_record),
                "tags": tags_by_file.get(file_id, []),
                "albums": albums_by_file.get(file_id, []),
            }
        )

    return complete_data


def export_lightroom_csv(data: List[Dict[str, Any]], output_file: Path) -> None:
    """Export metadata in Lightroom-compatible CSV format."""
    import csv

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Filename", "Keywords", "Caption", "Album", "GPS"])

        for item in data:
            file_record = item["file_record"]
            tags = item["tags"]
            albums = item["albums"]

            # Build keywords from tags
            keywords = []
            for tag in tags:
                if tag["auto"]:  # AI-generated tags
                    keywords.append(tag["tag"])
            keywords_str = "; ".join(keywords)

            # GPS coordinates
            lat = file_record.get("imageLatitude") or file_record.get("videoLatitude")
            lon = file_record.get("imageLongitude") or file_record.get("videoLongitude")
            gps = f"{lat},{lon}" if lat and lon else ""

            # Primary album
            album = albums[0]["name"] if albums else ""

            writer.writerow(
                [
                    file_record["name"],
                    keywords_str,
                    file_record.get("description", ""),
                    album,
                    gps,
                ]
            )


def export_digikam_csv(data: List[Dict[str, Any]], output_file: Path) -> None:
    """Export metadata in digiKam hierarchical format."""
    import csv

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Tags", "Album", "Date", "Latitude", "Longitude"])

        for item in data:
            file_record = item["file_record"]
            tags = item["tags"]
            albums = item["albums"]

            # Build hierarchical tags
            tag_list = []
            for tag in tags:
                if tag["auto"]:
                    # Simple hierarchy: People/person, Places/beach, etc.
                    tag_name = tag["tag"]
                    if tag_name in ["person", "child", "baby", "face"]:
                        tag_list.append(f"People/{tag_name}")
                    elif tag_name in ["beach", "mountain", "city", "park"]:
                        tag_list.append(f"Places/{tag_name}")
                    else:
                        tag_list.append(f"Objects/{tag_name}")
            tags_str = "|".join(tag_list)

            # Date
            date = (
                file_record.get("imageDate")
                or file_record.get("videoDate")
                or file_record.get("cTime")
            )
            if date:
                try:
                    from datetime import datetime

                    date = datetime.fromisoformat(date.replace("Z", "+00:00")).strftime(
                        "%Y-%m-%d"
                    )
                except:
                    date = str(date)[:10]  # Just take YYYY-MM-DD part

            writer.writerow(
                [
                    file_record["name"],
                    tags_str,
                    albums[0]["name"] if albums else "",
                    date or "",
                    file_record.get("imageLatitude")
                    or file_record.get("videoLatitude")
                    or "",
                    file_record.get("imageLongitude")
                    or file_record.get("videoLongitude")
                    or "",
                ]
            )


class MetadataExporter:
    """Spec-driven metadata export engine."""

    def __init__(self, formats_config_path: Path):
        """Initialize with export formats configuration."""
        with open(formats_config_path) as f:
            self.config = json.load(f)
        self.transforms = self._setup_transforms()
        self.filters = self._setup_filters()

    def _setup_transforms(self):
        """Setup transformation functions."""
        return {
            "join_tags": lambda tags, separator="; ": separator.join(
                [tag["tag"] for tag in tags]
            ),
            "first_album_name": lambda albums: albums[0]["name"] if albums else "",
            "gps_coordinates": self._transform_gps_coordinates,
            "hierarchical_tags": self._transform_hierarchical_tags,
            "iso_date": self._transform_iso_date,
            "iptc_date": self._transform_iptc_date,
            "exif_datetime": self._transform_exif_datetime,
            "google_timestamp": self._transform_google_timestamp,
            "iso_datetime": self._transform_iso_datetime,
            "extract_year": self._transform_extract_year,
            "tag_array": lambda tags: [tag["tag"] for tag in tags],
            "album_array": lambda albums: [album["name"] for album in albums],
            "gps_object": self._transform_gps_object,
        }

    def _setup_filters(self):
        """Setup filter functions."""
        return {
            "auto_only": lambda tags: [tag for tag in tags if tag.get("auto", False)],
            "manual_only": lambda tags: [
                tag for tag in tags if not tag.get("auto", False)
            ],
            "all": lambda tags: tags,
        }

    def _transform_gps_coordinates(self, values):
        """Transform GPS coordinates to lat,lon format."""
        if not isinstance(values, (list, tuple)):
            return ""
        lat = next((v for v in values[:2] if v), None)
        lon = next((v for v in values[2:4] if v), None) if len(values) > 2 else None
        return f"{lat},{lon}" if lat and lon else ""

    def _transform_hierarchical_tags(self, tags, separator="|"):
        """Transform tags to hierarchical format."""
        hierarchical = []
        for tag in tags:
            tag_name = tag["tag"]
            if tag_name in ["person", "child", "baby", "face"]:
                hierarchical.append(f"People/{tag_name}")
            elif tag_name in ["beach", "mountain", "city", "park"]:
                hierarchical.append(f"Places/{tag_name}")
            else:
                hierarchical.append(f"Objects/{tag_name}")
        return separator.join(hierarchical)

    def _transform_iso_date(self, values):
        """Transform to ISO 8601 date."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return ""
        try:
            from datetime import datetime

            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format)
                timestamp = date_val / 1000 if date_val > 1e10 else date_val
                return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
            else:
                return datetime.fromisoformat(
                    str(date_val).replace("Z", "+00:00")
                ).strftime("%Y-%m-%d")
        except:
            return str(date_val)[:10]

    def _transform_iptc_date(self, values):
        """Transform to IPTC date format (YYYYMMDD)."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return ""
        try:
            from datetime import datetime

            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format)
                timestamp = date_val / 1000 if date_val > 1e10 else date_val
                return datetime.fromtimestamp(timestamp).strftime("%Y%m%d")
            else:
                return datetime.fromisoformat(
                    str(date_val).replace("Z", "+00:00")
                ).strftime("%Y%m%d")
        except:
            return str(date_val)[:8]

    def _transform_exif_datetime(self, values):
        """Transform to EXIF datetime format."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return ""
        try:
            from datetime import datetime

            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format)
                timestamp = date_val / 1000 if date_val > 1e10 else date_val
                return datetime.fromtimestamp(timestamp).strftime("%Y:%m:%d %H:%M:%S")
            else:
                return datetime.fromisoformat(
                    str(date_val).replace("Z", "+00:00")
                ).strftime("%Y:%m:%d %H:%M:%S")
        except:
            return str(date_val)

    def _transform_google_timestamp(self, values):
        """Transform to Google Photos timestamp format."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return {"timestamp": "0"}
        try:
            from datetime import datetime

            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format) - convert to seconds
                timestamp = int(date_val / 1000) if date_val > 1e10 else int(date_val)
                return {"timestamp": str(timestamp)}
            else:
                # Parse ISO format and convert to Unix timestamp
                dt = datetime.fromisoformat(str(date_val).replace("Z", "+00:00"))
                return {"timestamp": str(int(dt.timestamp()))}
        except:
            return {"timestamp": "0"}

    def _transform_gps_object(self, values):
        """Transform to GPS object."""
        if not isinstance(values, (list, tuple)):
            return {}
        lat = next((v for v in values[:2] if v), None)
        lon = next((v for v in values[2:4] if v), None) if len(values) > 2 else None
        return {"latitude": lat, "longitude": lon} if lat and lon else {}

    def _transform_iso_datetime(self, values):
        """Transform to ISO 8601 datetime format (YYYY-MM-DDTHH:MM:SS)."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return ""
        try:
            from datetime import datetime

            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format)
                timestamp = date_val / 1000 if date_val > 1e10 else date_val
                return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%dT%H:%M:%S")
            else:
                return datetime.fromisoformat(
                    str(date_val).replace("Z", "+00:00")
                ).strftime("%Y-%m-%dT%H:%M:%S")
        except:
            return str(date_val)

    def _transform_extract_year(self, values):
        """Extract year from date (YYYY)."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return ""
        try:
            from datetime import datetime

            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format)
                timestamp = date_val / 1000 if date_val > 1e10 else date_val
                return datetime.fromtimestamp(timestamp).strftime("%Y")
            else:
                return datetime.fromisoformat(
                    str(date_val).replace("Z", "+00:00")
                ).strftime("%Y")
        except:
            return str(date_val)[:4]

    def _get_nested_value(self, data, path):
        """Get value from nested data using dot notation."""
        parts = path.split(".")
        value = data
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value

    def _apply_transform(self, value, transform, **kwargs):
        """Apply transformation to value."""
        if transform in self.transforms:
            return self.transforms[transform](value, **kwargs)
        return value

    def _apply_filter(self, value, filter_name):
        """Apply filter to value."""
        if filter_name in self.filters:
            return self.filters[filter_name](value)
        return value

    def export_csv_format(self, data, format_spec, output_file):
        """Export data in CSV format based on spec."""
        import csv

        # Use custom delimiter if specified
        delimiter = format_spec.get("delimiter", ",")

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=delimiter)

            # Write header
            headers = [col["name"] for col in format_spec["columns"]]
            writer.writerow(headers)

            # Write data rows
            for item in data:
                row = []
                for col in format_spec["columns"]:
                    value = self._extract_column_value(item, col)
                    row.append(value)
                writer.writerow(row)

    def _extract_column_value(self, item, col_spec):
        """Extract column value based on specification."""
        source = col_spec["source"]

        # Handle multiple source fields
        if isinstance(source, list):
            values = [self._get_nested_value(item, s) for s in source]
            values = [v for v in values if v is not None]
        else:
            values = [self._get_nested_value(item, source)]
            values = [v for v in values if v is not None]

        if not values:
            return col_spec.get("default", "")

        # For single values, don't wrap in list for transforms
        if len(values) == 1 and not isinstance(source, list):
            value = values[0]
        else:
            value = values

        # Apply filter if specified
        if "filter" in col_spec and isinstance(value, list):
            value = self._apply_filter(value, col_spec["filter"])

        # Apply transform if specified
        if "transform" in col_spec:
            kwargs = {}
            if "separator" in col_spec:
                kwargs["separator"] = col_spec["separator"]
            # Always pass values array for GPS transforms
            if col_spec["transform"] in [
                "gps_coordinates",
                "gps_object",
            ] and isinstance(source, list):
                value = self._apply_transform(values, col_spec["transform"], **kwargs)
            else:
                value = self._apply_transform(value, col_spec["transform"], **kwargs)

        return value if value is not None else col_spec.get("default", "")

    def export_json_format(self, data, format_spec, output_file):
        """Export data in JSON format based on spec."""
        # Implementation for JSON export based on structure spec
        result = {}

        # Build result based on structure specification
        structure = format_spec["structure"]
        for key, spec in structure.items():
            if key == "files":
                result[key] = []
                for item in data:
                    file_data = {}
                    for field_name, field_spec in spec["fields"].items():
                        if isinstance(field_spec, dict) and "source" in field_spec:
                            file_data[field_name] = self._extract_column_value(
                                item, field_spec
                            )
                        elif isinstance(field_spec, dict):
                            # Nested object
                            nested_obj = {}
                            for nested_key, nested_source in field_spec.items():
                                if nested_key != "source":
                                    nested_obj[nested_key] = (
                                        self._get_nested_value(item, nested_source)
                                        or ""
                                    )
                            file_data[field_name] = nested_obj
                        else:
                            file_data[field_name] = (
                                self._get_nested_value(item, field_spec) or ""
                            )
                    result[key].append(file_data)
            else:
                # Handle metadata fields
                if isinstance(spec, dict):
                    result[key] = {}
                    for subkey, subspec in spec.items():
                        if subspec == "current_datetime":
                            from datetime import datetime

                            result[key][subkey] = datetime.now().isoformat()
                        else:
                            result[key][subkey] = subspec  # Handle stats later
                else:
                    result[key] = spec

        with open(output_file, "w") as f:
            json.dump(result, f, indent=2)

    def export_all_formats(self, data, output_dir, selected_formats=None):
        """Export data in all configured formats."""
        output_dir.mkdir(parents=True, exist_ok=True)
        exported_files = []

        formats_to_export = selected_formats or self.config["formats"].keys()

        for format_name in formats_to_export:
            if format_name not in self.config["formats"]:
                print(f"⚠️  Unknown format: {format_name}")
                continue

            format_spec = self.config["formats"][format_name]
            filename = f"{format_name}.{format_spec['file_extension']}"
            output_file = output_dir / filename

            try:
                if format_spec["type"] == "csv":
                    self.export_csv_format(data, format_spec, output_file)
                elif format_spec["type"] == "json":
                    self.export_json_format(data, format_spec, output_file)
                elif format_spec["type"] == "xml":
                    print(f"⚠️  XML export not yet implemented for {format_name}")
                    continue

                exported_files.append(
                    {
                        "format": format_spec["name"],
                        "file": output_file,
                        "description": format_spec["description"],
                    }
                )
                print(f"  ✅ {format_spec['name']}: {output_file}")

            except Exception as e:
                print(f"  ❌ Failed to export {format_name}: {e}")

        return exported_files


def export_metadata_formats(
    files_with_albums: List[Dict[str, Any]],
    conn: sqlite3.Connection,
    output_dir: Path,
    selected_formats: Optional[List[str]] = None,
) -> None:
    """Export metadata using spec-driven format system."""

    print("Exporting metadata in standard formats...")

    # Get comprehensive data for export
    export_data = get_comprehensive_export_data(conn)

    # Initialize exporter with format specifications
    formats_config = Path(__file__).parent.parent / "export_formats.json"
    exporter = MetadataExporter(formats_config)

    # Export in specified formats
    exported_files = exporter.export_all_formats(
        export_data, output_dir, selected_formats
    )

    # Create summary
    summary = {
        "total_files": len(export_data),
        "files_with_tags": len([item for item in export_data if item["tags"]]),
        "files_with_albums": len([item for item in export_data if item["albums"]]),
        "unique_tags": len(
            set(tag["tag"] for item in export_data for tag in item["tags"])
        ),
        "unique_albums": len(
            set(album["name"] for item in export_data for album in item["albums"])
        ),
        "exported_formats": [f["format"] for f in exported_files],
        "export_timestamp": json.dumps(datetime.now().isoformat()),
    }

    summary_file = output_dir / "export_summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  ✅ Export Summary: {summary_file}")

    print(f"\nMetadata export complete: {len(export_data)} files processed")


def check_interrupt():
    """Check if extraction was interrupted and handle gracefully."""
    if extraction_state.interrupted:
        print(f"\n⚠️  Extraction stopped due to interrupt")
        return True
    return False


def extract_by_albums(
    files_with_albums: List[Dict[str, Any]],
    files_dir: Path,
    output_dir: Path,
    stats: Dict[str, Any],
    db_path: Path,
    copy_files: bool = True,
    use_rsync: bool = True,
    resume: bool = True,
    dedup: bool = True,
    use_hardlinks: bool = True,
    use_symlinks: bool = False,
    fix_metadata: bool = True,
    flat_albums: bool = False,
) -> Tuple[int, int]:
    """Extract files organized by albums, with unorganized files in a separate folder."""

    # Group files by their primary album (first album if multiple)
    album_files = defaultdict(list)
    unorganized_files = []

    for item in files_with_albums:
        if item["albums"]:
            # Use the first/primary album
            primary_album = item["albums"][0]["name"]
            album_files[primary_album].append(item)
        else:
            unorganized_files.append(item)

    # Calculate size statistics for albums
    album_sizes = {}
    unorganized_size = 0
    total_target_size = 0

    for album_name, files in album_files.items():
        album_size = sum((item["file"]["size"] or 0) for item in files)
        album_sizes[album_name] = album_size
        total_target_size += album_size

    for item in unorganized_files:
        size = item["file"]["size"] or 0
        unorganized_size += size
        total_target_size += size

    print(
        f"Found {len(album_files)} albums and {len(unorganized_files)} unorganized files"
    )
    print(f"Total size to extract: {format_size(total_target_size)}")
    print()

    total_extracted = 0
    total_size_extracted = 0
    total_files = sum(len(files) for files in album_files.values()) + len(
        unorganized_files
    )

    # Determine copy function and setup deduplication tracking
    if dedup:
        copy_tracker = {}  # Track contentID -> first copy location for deduplication
        dedup_stats = {
            "copied": 0,
            "hardlinked": 0,
            "symlinked": 0,
            "skipped": 0,
            "space_saved": 0,
        }
    copy_func = copy_file_rsync if use_rsync else copy_file_fallback

    # Extract organized albums
    for album_name, files in album_files.items():
        # Check for interrupt before each album
        if check_interrupt():
            return total_extracted, total_size_extracted

        extraction_state.current_operation = f"Extracting album: {album_name}"

        # Enhanced album name sanitization with preservation and messaging
        safe_album_name, name_changed = sanitize_album_name(album_name)

        if name_changed:
            print(f"  📝 Album name sanitized: '{album_name}' → '{safe_album_name}'")

        album_dir = output_dir / safe_album_name

        print(f"Extracting album: {album_name} ({len(files)} files)")

        if copy_files:
            album_dir.mkdir(parents=True, exist_ok=True)

        # Progress bar for this album with size information
        album_size = album_sizes[album_name]
        desc = f"  {album_name[:20]:<20} ({format_size(album_size)})"

        with tqdm(
            files,
            desc=desc,
            unit="files",
            leave=False,
            unit_scale=False,
            dynamic_ncols=True,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        ) as pbar:
            extracted_count = 0
            extracted_size = 0
            for item in pbar:
                # Check for interrupt every few files
                if check_interrupt():
                    extraction_state.total_files_extracted += extracted_count
                    extraction_state.total_size_extracted += extracted_size
                    return (
                        total_extracted + extracted_count,
                        total_size_extracted + extracted_size,
                    )

                file_record = item["file"]
                file_size = file_record["size"] or 0

                if copy_files:
                    source_path = find_source_file(
                        files_dir,
                        file_record["contentID"],
                        file_record["name"],
                        file_record.get("storageID"),
                        db_path,
                    )
                    if source_path:
                        # Use conditional organization within album folder
                        dest_path = get_organized_path(
                            album_dir,
                            file_record["name"],
                            file_record,
                            use_time_organization=not flat_albums,
                        )
                        # Handle duplicate filenames within time-organized structure
                        counter = 1
                        original_dest = dest_path
                        while dest_path.exists() and not resume:
                            stem = original_dest.stem
                            suffix = original_dest.suffix
                            # Keep the time-organized directory structure
                            dest_path = (
                                original_dest.parent / f"{stem}_{counter}{suffix}"
                            )
                            counter += 1

                        # Create directory structure
                        dest_path.parent.mkdir(parents=True, exist_ok=True)

                        # Use deduplication if enabled
                        if dedup:
                            success, action = copy_file_with_dedup(
                                source_path,
                                dest_path,
                                resume,
                                use_hardlinks,
                                use_symlinks,
                                copy_tracker,
                                file_record,
                                fix_metadata,  # Pass metadata for timestamp correction
                            )
                            if success:
                                extracted_count += 1
                                if action in ["copied", "skipped"]:
                                    extracted_size += file_size
                                    total_size_extracted += file_size
                                elif action in ["hardlinked", "symlinked"]:
                                    # Track space saved through deduplication
                                    dedup_stats["space_saved"] += file_size
                                dedup_stats[action] += 1
                            else:
                                pbar.write(f"  Error copying {file_record['name']}")
                        else:
                            # Use traditional copy function
                            if use_rsync:
                                success = copy_file_rsync(
                                    source_path,
                                    dest_path,
                                    resume,
                                    file_record,
                                    fix_metadata,
                                )
                            else:
                                success = copy_file_fallback(
                                    source_path,
                                    dest_path,
                                    resume,
                                    file_record,
                                    fix_metadata,
                                )

                            if success:
                                extracted_count += 1
                                extracted_size += file_size
                                total_size_extracted += file_size
                            else:
                                pbar.write(f"  Error copying {file_record['name']}")

                        # Update global state
                        extraction_state.total_files_extracted = (
                            total_extracted + extracted_count
                        )
                        extraction_state.total_size_extracted = total_size_extracted

                        # Update progress description with cumulative progress
                        overall_progress = (
                            total_size_extracted / total_target_size
                        ) * 100
                        pbar.set_description(f"{desc} [{overall_progress:.1f}% total]")
                    else:
                        pbar.write(f"  Source file not found: {file_record['name']}")
                else:
                    extracted_count += 1
                    extracted_size += file_size

        if copy_files:
            print(
                f"  Extracted {extracted_count}/{len(files)} files ({format_size(extracted_size)})"
            )
        total_extracted += extracted_count
        print()

    # Extract unorganized files (in DB but not in albums)
    if unorganized_files:
        # Check for interrupt before unorganized files
        if check_interrupt():
            return total_extracted, total_size_extracted

        extraction_state.current_operation = "Extracting unorganized files"

        unorganized_dir = output_dir / "Unorganized"
        print(
            f"Extracting unorganized files: Unorganized (time-organized) ({len(unorganized_files)} files, {format_size(unorganized_size)})"
        )

        desc = f"  Unorganized ({format_size(unorganized_size)})"
        with tqdm(
            unorganized_files,
            desc=desc,
            unit="files",
            leave=False,
            unit_scale=False,
            dynamic_ncols=True,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        ) as pbar:
            extracted_count = 0
            extracted_size = 0
            for item in pbar:
                # Check for interrupt during unorganized files
                if check_interrupt():
                    extraction_state.total_files_extracted += extracted_count
                    extraction_state.total_size_extracted += extracted_size
                    return (
                        total_extracted + extracted_count,
                        total_size_extracted + extracted_size,
                    )

                file_record = item["file"]
                file_size = file_record["size"] or 0

                if copy_files:
                    source_path = find_source_file(
                        files_dir,
                        file_record["contentID"],
                        file_record["name"],
                        file_record.get("storageID"),
                        db_path,
                    )
                    if source_path:
                        # Use conditional organization within Unorganized folder
                        dest_path = get_organized_path(
                            unorganized_dir,
                            file_record["name"],
                            file_record,
                            use_time_organization=not flat_albums,
                        )

                        # Create directory structure
                        dest_path.parent.mkdir(parents=True, exist_ok=True)

                        # Handle duplicate filenames
                        counter = 1
                        original_dest = dest_path
                        while dest_path.exists() and not resume:
                            stem = original_dest.stem
                            suffix = original_dest.suffix
                            dest_path = (
                                original_dest.parent / f"{stem}_{counter}{suffix}"
                            )
                            counter += 1

                        # Use deduplication if enabled
                        if dedup:
                            success, action = copy_file_with_dedup(
                                source_path,
                                dest_path,
                                resume,
                                use_hardlinks,
                                use_symlinks,
                                copy_tracker,
                                file_record,
                                fix_metadata,  # Pass metadata for timestamp correction
                            )
                            if success:
                                extracted_count += 1
                                if action in ["copied", "skipped"]:
                                    extracted_size += file_size
                                    total_size_extracted += file_size
                                elif action in ["hardlinked", "symlinked"]:
                                    # Track space saved through deduplication
                                    dedup_stats["space_saved"] += file_size
                                dedup_stats[action] += 1
                            else:
                                pbar.write(f"  Error copying {file_record['name']}")
                        else:
                            # Use traditional copy function
                            if use_rsync:
                                success = copy_file_rsync(
                                    source_path,
                                    dest_path,
                                    resume,
                                    file_record,
                                    fix_metadata,
                                )
                            else:
                                success = copy_file_fallback(
                                    source_path,
                                    dest_path,
                                    resume,
                                    file_record,
                                    fix_metadata,
                                )

                            if success:
                                extracted_count += 1
                                extracted_size += file_size
                                total_size_extracted += file_size
                            else:
                                pbar.write(f"  Error copying {file_record['name']}")

                        # Update global state
                        extraction_state.total_files_extracted = (
                            total_extracted + extracted_count
                        )
                        extraction_state.total_size_extracted = total_size_extracted

                        # Update progress description with cumulative progress
                        overall_progress = (
                            total_size_extracted / total_target_size
                        ) * 100
                        pbar.set_description(f"{desc} [{overall_progress:.1f}% total]")
                    else:
                        pbar.write(f"  Source file not found: {file_record['name']}")
                else:
                    extracted_count += 1
                    extracted_size += file_size

        if copy_files:
            print(
                f"  Extracted {extracted_count}/{len(unorganized_files)} files ({format_size(extracted_size)})"
            )
        total_extracted += extracted_count
        print()

    # Report deduplication statistics if enabled
    if dedup and copy_files:
        print(f"\n📊 DEDUPLICATION SUMMARY:")
        print(f"   Files copied: {dedup_stats['copied']}")
        print(f"   Files hardlinked: {dedup_stats['hardlinked']}")
        print(f"   Files symlinked: {dedup_stats['symlinked']}")
        print(f"   Files skipped (resume): {dedup_stats['skipped']}")
        print(
            f"   Space saved through deduplication: {format_size(dedup_stats['space_saved'])}"
        )

        total_operations = (
            sum(dedup_stats.values()) - dedup_stats["space_saved"]
        )  # space_saved is not a count
        if total_operations > 0:
            dedup_rate = (
                (dedup_stats["hardlinked"] + dedup_stats["symlinked"])
                / total_operations
                * 100
            )
            print(f"   Deduplication rate: {dedup_rate:.1f}%")

    return total_extracted, total_size_extracted


def find_existing_file_in_extraction(
    extraction_dir: Path, filename: str, current_time_organized: bool = None
) -> Optional[Path]:
    """
    Find an existing file in extraction directory, checking both flat and time-organized structures.

    Args:
        extraction_dir: Root extraction directory
        filename: File to find
        current_time_organized: If known, check specific structure first

    Returns:
        Path to existing file or None if not found
    """
    # Check flat structure first if specified or as fallback
    if current_time_organized is False:
        flat_path = extraction_dir / filename
        if flat_path.exists():
            return flat_path

    # Check time-organized structure (scan year/month dirs)
    if current_time_organized is True or current_time_organized is None:
        if extraction_dir.exists():
            for year_dir in extraction_dir.iterdir():
                if not year_dir.is_dir() or not year_dir.name.isdigit():
                    continue
                for month_dir in year_dir.iterdir():
                    if not month_dir.is_dir() or not month_dir.name.isdigit():
                        continue
                    time_path = month_dir / filename
                    if time_path.exists():
                        return time_path

    # Check flat structure as fallback
    if current_time_organized is None:
        flat_path = extraction_dir / filename
        if flat_path.exists():
            return flat_path

    return None


def reorganize_extraction(
    extraction_dir: Path,
    files_with_albums: List[Dict[str, Any]],
    target_time_organized: bool,
) -> Tuple[int, int]:
    """
    Reorganize existing extraction between flat and time-organized structures.

    Args:
        extraction_dir: Directory containing extracted files
        files_with_albums: Database file records
        target_time_organized: True for time-organized, False for flat

    Returns:
        Tuple of (files_moved, total_files_processed)
    """
    print(f"🔄 Reorganizing extraction directory...")
    print(
        f"   Target structure: {'Time-organized' if target_time_organized else 'Flat'}"
    )

    files_moved = 0
    total_processed = 0

    # Process album files
    album_files = defaultdict(list)
    unorganized_files = []

    for item in files_with_albums:
        if item["albums"]:
            primary_album = item["albums"][0]["name"]
            album_files[primary_album].append(item)
        else:
            unorganized_files.append(item)

    # Reorganize album files
    for album_name, files in album_files.items():
        # Enhanced album name sanitization with preservation and messaging
        safe_album_name, name_changed = sanitize_album_name(album_name)

        if name_changed:
            print(
                f"  📝 Album name sanitized during reorganization: '{album_name}' → '{safe_album_name}'"
            )

        album_dir = extraction_dir / safe_album_name

        for item in files:
            file_record = item["file"]
            filename = file_record["name"]

            # Find existing file (auto-detect current structure)
            old_path = find_existing_file_in_extraction(
                album_dir, filename, current_time_organized=None
            )

            if not old_path:
                total_processed += 1
                continue

            # Calculate new path
            new_path = get_organized_path(
                album_dir,
                filename,
                file_record,
                use_time_organization=target_time_organized,
            )

            # Move if different
            if old_path != new_path:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                old_path.rename(new_path)
                files_moved += 1

            total_processed += 1

    # Reorganize unorganized files
    unorganized_dir = extraction_dir / "Unorganized"
    if unorganized_dir.exists():
        for item in unorganized_files:
            file_record = item["file"]
            filename = file_record["name"]

            # Find existing file (auto-detect current structure)
            old_path = find_existing_file_in_extraction(
                unorganized_dir, filename, current_time_organized=None
            )

            if not old_path:
                total_processed += 1
                continue

            # Calculate new path
            new_path = get_organized_path(
                unorganized_dir,
                filename,
                file_record,
                use_time_organization=target_time_organized,
            )

            # Move if different
            if old_path != new_path:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                old_path.rename(new_path)
                files_moved += 1

            total_processed += 1

    # Clean up empty directories
    _cleanup_empty_directories(extraction_dir)

    return files_moved, total_processed


def _cleanup_empty_directories(root_dir: Path):
    """Recursively remove empty directories."""
    for dirpath in sorted(
        root_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True
    ):
        if dirpath.is_dir() and not any(dirpath.iterdir()):
            try:
                dirpath.rmdir()
            except OSError:
                pass  # Directory not empty or permission issue


def extract_by_type(
    files_with_albums: List[Dict[str, Any]],
    files_dir: Path,
    output_dir: Path,
    stats: Dict[str, Any],
    db_path: Path,
    copy_files: bool = True,
    use_rsync: bool = True,
    resume: bool = True,
    fix_metadata: bool = True,
) -> Tuple[int, int]:
    """Extract files organized by type (images, videos, documents)."""

    type_dirs = {
        "images": output_dir / "Images",
        "videos": output_dir / "Videos",
        "documents": output_dir / "Documents",
        "other": output_dir / "Other",
    }

    if copy_files:
        for dir_path in type_dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)

    total_extracted = 0
    total_size_extracted = 0
    type_counts = defaultdict(int)
    type_sizes = defaultdict(int)

    # Determine copy function
    copy_func = copy_file_rsync if use_rsync else copy_file_fallback

    print(f"Total size to extract: {format_size(stats['total_size'])}")
    print()

    # Group files by type first for better progress tracking
    files_by_type = defaultdict(list)
    for item in files_with_albums:
        file_record = item["file"]
        mime_type = file_record["mimeType"] or ""
        file_size = file_record["size"] or 0

        # Determine file category
        if mime_type.startswith("image/"):
            category = "images"
        elif mime_type.startswith("video/"):
            category = "videos"
        elif mime_type.startswith("application/") or mime_type.startswith("text/"):
            category = "documents"
        else:
            category = "other"

        files_by_type[category].append(item)
        type_sizes[category] += file_size

    # Extract by type with progress bars
    for category, items in files_by_type.items():
        if not items:
            continue

        # Check for interrupt before each category
        if check_interrupt():
            return total_extracted, total_size_extracted

        extraction_state.current_operation = f"Extracting {category}"

        category_size = type_sizes[category]
        print(
            f"Extracting {category}: {len(items)} files ({format_size(category_size)})"
        )

        desc = f"  {category.title():<12} ({format_size(category_size)})"
        with tqdm(
            items,
            desc=desc,
            unit="files",
            leave=False,
            unit_scale=False,
            dynamic_ncols=True,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        ) as pbar:
            extracted_size = 0
            for item in pbar:
                # Check for interrupt during type extraction
                if check_interrupt():
                    extraction_state.total_files_extracted += (
                        total_extracted - len(files_by_type[category]) + pbar.n
                    )
                    extraction_state.total_size_extracted += total_size_extracted
                    return total_extracted, total_size_extracted

                file_record = item["file"]
                file_size = file_record["size"] or 0
                type_counts[category] += 1

                if copy_files:
                    source_path = find_source_file(
                        files_dir,
                        file_record["contentID"],
                        file_record["name"],
                        file_record.get("storageID"),
                        db_path,
                    )
                    if source_path:
                        dest_path = type_dirs[category] / file_record["name"]

                        # Handle duplicate filenames
                        counter = 1
                        original_dest = dest_path
                        while dest_path.exists() and not resume:
                            stem = original_dest.stem
                            suffix = original_dest.suffix
                            dest_path = (
                                type_dirs[category] / f"{stem}_{counter}{suffix}"
                            )
                            counter += 1

                        if use_rsync:
                            success = copy_file_rsync(
                                source_path,
                                dest_path,
                                resume,
                                file_record,
                                fix_metadata,
                            )
                        else:
                            success = copy_file_fallback(
                                source_path,
                                dest_path,
                                resume,
                                file_record,
                                fix_metadata,
                            )

                        if success:
                            total_extracted += 1
                            extracted_size += file_size
                            total_size_extracted += file_size

                            # Update global state
                            extraction_state.total_files_extracted = total_extracted
                            extraction_state.total_size_extracted = total_size_extracted

                            # Update progress description with cumulative progress
                            overall_progress = (
                                total_size_extracted / stats["total_size"]
                            ) * 100
                            pbar.set_description(
                                f"{desc} [{overall_progress:.1f}% total]"
                            )
                        else:
                            pbar.write(f"Error copying {file_record['name']}")
                    else:
                        pbar.write(f"Source file not found: {file_record['name']}")
                else:
                    total_extracted += 1
                    extracted_size += file_size

        print(
            f"  {category.title()}: {type_counts[category]} files ({format_size(extracted_size)})"
        )

    return total_extracted, total_size_extracted


def read_image_metadata(file_path: Path) -> Dict[str, Any]:
    """Read existing metadata from an image file."""
    if not HAS_PIL:
        return {"error": "PIL/Pillow not available"}

    try:
        with Image.open(file_path) as img:
            exifdata = img.getexif()

            metadata = {}

            # Basic EXIF data
            for tag_id, value in exifdata.items():
                tag = TAGS.get(tag_id, tag_id)
                metadata[tag] = value

            # GPS data
            gps_info = exifdata.get_ifd(0x8825)
            if gps_info:
                gps_data = {}
                for key, value in gps_info.items():
                    sub_tag = GPSTAGS.get(key, key)
                    gps_data[sub_tag] = value
                metadata["GPS"] = gps_data

            return metadata
    except Exception as e:
        return {"error": str(e)}


def compare_metadata(
    db_record: Dict[str, Any], file_metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """Compare database metadata with file metadata."""
    comparison = {
        "has_exif": bool(file_metadata and "error" not in file_metadata),
        "has_gps": bool(file_metadata.get("GPS")),
        "db_has_gps": bool(
            db_record.get("imageLatitude") and db_record.get("imageLongitude")
        ),
        "db_has_camera": bool(db_record.get("imageCameraMake")),
        "missing_metadata": [],
    }

    # Check for missing GPS
    if comparison["db_has_gps"] and not comparison["has_gps"]:
        comparison["missing_metadata"].append("GPS coordinates")

    # Check for missing camera info
    if comparison["db_has_camera"] and not file_metadata.get("Make"):
        comparison["missing_metadata"].append("Camera information")

    return comparison


def verify_metadata_sample(
    conn: sqlite3.Connection, files_dir: Path, sample_size: int = 50
) -> Dict[str, Any]:
    """Verify metadata for a sample of files."""
    if not HAS_PIL:
        return {"error": "PIL/Pillow not available. Install with: pip install Pillow"}

    print(f"\n🔍 METADATA VERIFICATION")
    print("=" * 40)
    print(f"Comparing file metadata with database for {sample_size} files...")

    # Get sample files
    query = f"""
    SELECT id, name, contentID, imageLatitude, imageLongitude,
           imageCameraMake, imageCameraModel, mimeType
    FROM Files
    WHERE contentID IS NOT NULL AND contentID != '' AND mimeType LIKE 'image/%'
    ORDER BY RANDOM() LIMIT {sample_size}
    """

    files = list(conn.execute(query).fetchall())
    results = {
        "total_checked": len(files),
        "has_exif": 0,
        "missing_exif": 0,
        "has_gps": 0,
        "missing_gps": 0,
        "missing_camera": 0,
        "files_found": 0,
    }

    progress = (
        tqdm(
            files,
            desc="Checking metadata",
            unit="files",
            unit_scale=False,
            dynamic_ncols=True,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        )
        if HAS_TQDM
        else files
    )

    for file_record in progress:
        # Find physical file
        content_id = file_record["contentID"]
        first_char = content_id[0] if content_id else "_"
        file_path = files_dir / first_char / content_id

        if not file_path.exists():
            continue

        results["files_found"] += 1

        # Read file metadata
        file_metadata = read_image_metadata(file_path)
        comparison = compare_metadata(dict(file_record), file_metadata)

        # Update statistics
        if comparison["has_exif"]:
            results["has_exif"] += 1
        else:
            results["missing_exif"] += 1

        if comparison["has_gps"]:
            results["has_gps"] += 1
        elif comparison["db_has_gps"]:
            results["missing_gps"] += 1

        if comparison["db_has_camera"] and not file_metadata.get("Make"):
            results["missing_camera"] += 1

    # Print summary
    print(f"\n📊 METADATA VERIFICATION RESULTS:")
    print(f"   Files checked: {results['files_found']}/{results['total_checked']}")
    print(f"   Files with EXIF: {results['has_exif']}")
    print(f"   Files missing EXIF: {results['missing_exif']}")
    print(f"   Files with GPS: {results['has_gps']}")
    print(f"   Files missing GPS: {results['missing_gps']}")
    print(f"   Files missing camera info: {results['missing_camera']}")

    if results["missing_gps"] > 0 or results["missing_camera"] > 0:
        print(f"\n💡 RECOMMENDATION:")
        print(f"   Consider using --export to generate metadata that can be")
        print(f"   embedded back into files using ExifTool or photo software.")

    return results


def main():
    # Register signal handler for graceful interrupts
    signal.signal(signal.SIGINT, extraction_state.signal_handler)

    parser = argparse.ArgumentParser(
        description="Extract files from ibi recovery database with enhanced features",
        epilog="""
Organization modes:
  albums (default): Extract by albums with unorganized files in "Unorganized" folder
  type: Extract by file type (Images, Videos, Documents, Other)

Advanced options:
  --resume: Resume interrupted transfers (default: enabled)
  --copy-method: Choose copy method (rsync/python, default: rsync)
  --dedup: Deduplication method (none/hardlinks/symlinks, default: hardlinks)
  --db-path: Override auto-detected database path
  --files-path: Override auto-detected files path
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "ibi_root",
        nargs="?",
        help="Path to ibi root directory (auto-detects structure)",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        help="Output directory for extracted files (not needed for --verify)",
    )
    parser.add_argument(
        "--by-type", action="store_true", help="Extract by file type instead of albums"
    )
    parser.add_argument(
        "--list-only", action="store_true", help="List files without copying them"
    )
    parser.add_argument(
        "--stats", action="store_true", help="Show statistics about file organization"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume interrupted transfers (default: enabled, use --no-resume to disable)",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Disable resume functionality",
    )
    parser.add_argument(
        "--copy-method",
        choices=["rsync", "python"],
        default="rsync",
        help="Copy method to use (default: rsync, fallback to python if rsync unavailable)",
    )
    parser.add_argument(
        "--db-path", type=Path, help="Override auto-detected database path"
    )
    parser.add_argument(
        "--files-path", type=Path, help="Override auto-detected files path"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify file availability and database structure (no extraction)",
    )
    parser.add_argument(
        "--verify-sample",
        type=int,
        default=100,
        help="Number of files to sample for verification (default: 100, 0 = all files)",
    )
    parser.add_argument(
        "--audit-report",
        type=Path,
        help="Directory to save detailed audit reports (enables comprehensive audit mode)",
    )
    parser.add_argument(
        "--verify-metadata",
        action="store_true",
        help="Compare existing file metadata with database (requires pillow)",
    )
    parser.add_argument(
        "--export", action="store_true", help="Export metadata to standard formats"
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        help="Directory for exported metadata (default: ./metadata_exports)",
    )
    parser.add_argument(
        "--dedup",
        choices=["none", "hardlinks", "symlinks"],
        default="hardlinks",
        help="Deduplication method (default: hardlinks, symlinks for cross-filesystem, none to disable)",
    )
    parser.add_argument(
        "--deduplicate-existing",
        type=Path,
        help="Post-process existing extraction directory to deduplicate files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what deduplication would do without making changes (use with --deduplicate-existing)",
    )
    parser.add_argument(
        "--no-fix-metadata",
        dest="fix_metadata",
        action="store_false",
        default=True,
        help="Disable metadata timestamp correction during extraction (enabled by default)",
    )
    parser.add_argument(
        "--export-formats",
        nargs="+",
        help="Specific formats to export (e.g., lightroom_csv exiftool_csv)",
    )
    parser.add_argument(
        "--list-formats", action="store_true", help="List available export formats"
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Use flat album structure instead of time-organized subdirectories",
    )
    parser.add_argument(
        "--reorganize",
        action="store_true",
        help="Reorganize existing extraction directory structure",
    )

    args = parser.parse_args()

    # Handle post-processing deduplication
    if args.deduplicate_existing:
        if not args.deduplicate_existing.exists():
            print(f"❌ Directory does not exist: {args.deduplicate_existing}")
            sys.exit(1)
        if not args.deduplicate_existing.is_dir():
            print(f"❌ Path is not a directory: {args.deduplicate_existing}")
            sys.exit(1)

        # Convert dedup choice to boolean flags for existing function
        use_hardlinks = args.dedup == "hardlinks"
        use_symlinks = args.dedup == "symlinks"

        stats = deduplicate_existing_extraction(
            args.deduplicate_existing,
            use_hardlinks,
            use_symlinks,
            args.dry_run,
        )

        if args.dry_run:
            print(
                f"\n✨ Dry run complete. Would save {format_size(stats['space_saved'])} of disk space."
            )
        else:
            print(
                f"\n✅ Deduplication complete! Saved {format_size(stats['space_saved'])} of disk space."
            )
        sys.exit(0)

    # Handle reorganization mode
    if args.reorganize:
        if not args.output_dir:
            print("❌ output_dir is required for reorganization")
            sys.exit(1)
        if not output_dir.exists():
            print(f"❌ Extraction directory does not exist: {output_dir}")
            sys.exit(1)
        if not output_dir.is_dir():
            print(f"❌ Path is not a directory: {output_dir}")
            sys.exit(1)

        # We need database connection for reorganization
        if not args.ibi_root:
            print("❌ ibi_root is required for reorganization")
            sys.exit(1)

        # Continue to database loading below...
        reorganize_mode = True
    else:
        reorganize_mode = False

    # Handle format listing
    if args.list_formats:
        formats_config = Path(__file__).parent.parent / "export_formats.json"
        if formats_config.exists():
            with open(formats_config) as f:
                config = json.load(f)
            print("Available export formats:")
            for format_name, format_spec in config["formats"].items():
                print(f"  {format_name:<15} - {format_spec['description']}")
        else:
            print("❌ Export formats configuration not found")
        sys.exit(0)

    # Validate arguments
    if not args.list_formats and not args.ibi_root:
        parser.error("ibi_root is required unless using --list-formats")

    if (
        not args.list_formats
        and not args.verify
        and not args.verify_metadata
        and not args.export
        and not args.list_only
        and not args.stats
        and not args.deduplicate_existing
        and not args.reorganize
        and not args.output_dir
    ):
        parser.error(
            "output_dir is required unless using --verify, --verify-metadata, --export, --list-only, --stats, --deduplicate-existing, or --reorganize"
        )

    # Set default export directory
    if args.export and not args.export_dir:
        args.export_dir = Path("./metadata_exports")

    ibi_root = Path(args.ibi_root) if args.ibi_root else None
    output_dir = Path(args.output_dir) if args.output_dir else None

    # For list-only mode, provide a dummy output_dir since paths are needed but not used
    if args.list_only and output_dir is None:
        output_dir = Path("/tmp/dummy")

    if ibi_root and not ibi_root.exists():
        print(f"❌ ibi root directory not found: {ibi_root}")
        sys.exit(1)

    # Auto-detect or use provided paths
    if args.db_path and args.files_path:
        db_path = args.db_path
        files_dir = args.files_path
        # Try to find backup database near the main database
        backup_db_path = db_path.parent.parent / "dbBackup" / "index.db"
        if not backup_db_path.exists():
            backup_db_path = None

        print(f"Using provided paths:")
        print(f"   Database: {db_path}")
        print(f"   Files: {files_dir}")
        if backup_db_path:
            print(f"   Backup DB: {backup_db_path}")
        else:
            print(f"   Backup DB: Not found (optional)")
    else:
        db_path, files_dir, backup_db_path = detect_ibi_structure(ibi_root)
        if not db_path or not files_dir:
            print(f"❌ Could not detect ibi structure in: {ibi_root}")
            print(
                "Expected structure: restsdk/data/db/index.db and restsdk/data/files/"
            )
            print("Use --db-path and --files-path to specify manually")
            sys.exit(1)

    if not db_path.exists():
        print(f"❌ Database file not found: {db_path}")
        sys.exit(1)

    if not files_dir.exists():
        print(f"❌ Files directory not found: {files_dir}")
        sys.exit(1)

    # Check rsync availability
    use_rsync = args.copy_method == "rsync" and check_rsync_available()
    if not args.list_only:
        if use_rsync:
            print("✅ Using rsync for file operations (resumable)")
        else:
            print("ℹ️  Using Python copy (rsync not available or disabled)")

        if args.resume:
            print("✅ Resume mode enabled")
        else:
            print("ℹ️  Resume mode disabled")
        print()

    if not args.list_only and output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Use merged database function to include backup database files
    if CORE_MODULES_AVAILABLE:
        files_with_albums, stats = core_get_merged_files_with_albums(
            db_path, backup_db_path
        )
        # Open connection for verification/metadata operations
        conn = connect_db(db_path)
    else:
        # Fallback to single database using read-only connection for mounted filesystems
        try:
            conn = connect_db(db_path)
            files_with_albums, stats = get_all_files_with_albums(conn)
        except sqlite3.OperationalError as e:
            if "readonly database" in str(e).lower():
                print("⚠️  Database is read-only, switching to read-only mode")
                conn.close() if "conn" in locals() else None
                conn = connect_db_readonly(db_path)
                files_with_albums, stats = get_all_files_with_albums(conn)
            else:
                raise
        stats["backup_recovered"] = 0

    print(
        f"Found {stats['total_files']} total files in database ({format_size(stats['total_size'])})"
    )

    # Show backup recovery information
    if stats.get("backup_recovered", 0) > 0:
        print(
            f"  📥 Recovered {stats['backup_recovered']} additional files from backup database"
        )
    elif backup_db_path:
        print(f"  ℹ️  Backup database checked - no additional files found")
    else:
        print(f"  ℹ️  No backup database available")

    # Show detailed statistics
    if args.stats or True:  # Always show basic stats
        organized_count = sum(1 for item in files_with_albums if item["albums"])
        unorganized_count = len(files_with_albums) - organized_count
        album_names = set()
        for item in files_with_albums:
            for album in item["albums"]:
                album_names.add(album["name"])

        print(f"  Organized in albums: {organized_count} files")
        print(f"  Unorganized (no albums): {unorganized_count} files")
        print(f"  Total albums: {len(album_names)}")

        if args.stats:
            print(f"  Size breakdown:")
            for file_type, size in stats["size_by_type"].items():
                print(f"    {file_type.title()}: {format_size(size)}")
        print()

    # Handle verification mode
    if args.verify:
        print("=" * 60)
        print("FILE AVAILABILITY VERIFICATION")
        print("=" * 60)

        if CORE_MODULES_AVAILABLE:
            verification = core_verify_file_availability(
                files_with_albums, files_dir, args.verify_sample, args.audit_report
            )
        else:
            verification = verify_file_availability(
                files_with_albums, files_dir, args.verify_sample, args.audit_report
            )

        # Display results based on verification type
        if verification.get("comprehensive"):
            print(f"Comprehensive audit results:")
            print(
                f"  Available: {verification['available_count']}/{verification['total_files']} "
                f"({verification['availability_rate']:.1f}%)"
            )
            print(
                f"  Missing: {verification['missing_count']}/{verification['total_files']}"
            )
            if verification.get("orphaned_count", 0) > 0:
                print(
                    f"  Orphaned files: {verification['orphaned_count']} (on disk but not in database)"
                )
            if verification.get("size_mismatches", 0) > 0:
                print(f"  Size mismatches: {verification['size_mismatches']}")
            print(f"  Available data: {format_size(verification['available_size'])}")
        else:
            print(f"Sample results:")
            print(
                f"  Available: {verification['files_found']}/{verification['sample_size']} "
                f"({verification['recovery_rate']:.1f}%)"
            )
            print(
                f"  Missing: {verification['sample_size'] - verification['files_found']}/{verification['sample_size']}"
            )
            # Only show data sizes if available (fallback verification has these fields)
            if "available_size" in verification:
                print(
                    f"  Available data: {format_size(verification['available_size'])}"
                )
            if "total_sample_size" in verification:
                print(
                    f"  Total sample data: {format_size(verification['total_sample_size'])}"
                )
        print()

        recovery_rate = verification.get(
            "recovery_rate", verification.get("availability_rate", 0)
        )
        if recovery_rate >= 95:
            print("✅ EXCELLENT: Very high file availability rate")
        elif recovery_rate >= 80:
            print("✅ GOOD: High file availability rate")
        elif recovery_rate >= 50:
            print("⚠️  FAIR: Moderate file availability rate")
        else:
            print("❌ POOR: Low file availability rate")

        estimated_recoverable = int((recovery_rate / 100) * stats["total_files"])
        estimated_size = int((recovery_rate / 100) * stats["total_size"])
        print(f"Estimated recoverable files: {estimated_recoverable}")
        print(f"Estimated recoverable data: {format_size(estimated_size)}")
        print()
        print(
            "Recommendation: "
            + (
                "Proceed with extraction"
                if recovery_rate >= 50
                else "Check file paths and mount points"
            )
        )

        conn.close()
        return

    # Handle reorganization mode
    if reorganize_mode:
        print("=" * 60)
        print("EXTRACTION REORGANIZATION")
        print("=" * 60)

        files_moved, total_processed = reorganize_extraction(
            output_dir, files_with_albums, target_time_organized=not args.flat
        )

        print(f"\n✅ Reorganization complete!")
        print(f"   Files moved: {files_moved}")
        print(f"   Files processed: {total_processed}")
        print(f"   Structure: {'Flat' if args.flat else 'Time-organized'}")

        conn.close()
        return

    # Handle metadata verification mode
    if args.verify_metadata:
        if not HAS_PIL:
            print("❌ Metadata verification requires PIL/Pillow")
            print("   Install with: pip install Pillow")
            conn.close()
            return

        verify_metadata_sample(conn, files_dir, args.verify_sample)
        conn.close()
        return

    # Handle export mode
    if args.export:
        print("=" * 60)
        print("METADATA EXPORT")
        print("=" * 60)

        export_metadata_formats(
            files_with_albums, conn, args.export_dir, args.export_formats
        )

        if not args.output_dir:  # Export only mode
            conn.close()
            return

        print()  # Add spacing before extraction

    # Extract files
    if args.by_type:
        print("Extracting files organized by type...")
        total_extracted, total_size = extract_by_type(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            db_path,
            not args.list_only,
            use_rsync,
            args.resume,
            args.fix_metadata,
        )
    else:
        print("Extracting files organized by albums...")
        total_extracted, total_size = extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            db_path,
            not args.list_only,
            use_rsync,
            args.resume,
            args.dedup != "none",
            args.dedup == "hardlinks",
            args.dedup == "symlinks",
            args.fix_metadata,
            args.flat,
        )

    if not args.list_only:
        print(f"✅ Total files extracted: {total_extracted} ({format_size(total_size)})")

    conn.close()


if __name__ == "__main__":
    main()
