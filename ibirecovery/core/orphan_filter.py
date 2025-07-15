# SPDX-License-Identifier: GPL-3.0-or-later
"""
Orphan file filtering and classification for ibiRecovery.

Automatically identifies and filters out duplicates, thumbnails, cache files,
and other non-essential orphaned files to reduce processing overhead.

Copyright (C) 2024 ibiRecovery Contributors
Licensed under GPL-3.0-or-later
"""

import hashlib
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Size thresholds for filtering (in bytes)
THUMBNAIL_MAX_SIZE = 50 * 1024  # 50KB - likely thumbnails
TINY_FILE_MAX_SIZE = 1 * 1024  # 1KB - likely metadata/cache
LARGE_FILE_MIN_SIZE = 10 * 1024 * 1024  # 10MB - definitely not thumbnails

# Patterns for files that are likely thumbnails, cache, or system files
SKIP_PATTERNS = [
    r".*thumb.*",
    r".*preview.*",
    r".*cache.*",
    r".*\.tmp$",
    r".*\.temp$",
    r".*_small\.",
    r".*_thumb\.",
    r".*_preview\.",
    r"^\._.*",  # macOS resource forks
    r"^\.ds_store$",  # macOS metadata (lowercase)
    r"^thumbs\.db$",  # Windows thumbnails (lowercase)
    r"\.thumbnails/.*",  # Linux thumbnail cache
    r".*\.thumb\d*$",  # Generic thumbnail extensions
    r".*_\d+x\d+\.",  # Size-specific thumbnails (e.g., _150x150.jpg)
]

# MIME types that are likely to be skippable
SKIP_MIME_TYPES = {
    "application/x-trash",
    "application/x-empty",
    "text/x-log",
    "application/x-cache",
}

# File extensions that are likely skippable
SKIP_EXTENSIONS = {
    ".tmp",
    ".temp",
    ".cache",
    ".log",
    ".bak",
    ".old",
    ".~",
    ".swp",
    ".swo",
    ".lock",
}


class OrphanFileFilter:
    """Filter and classify orphaned files to identify skippable content."""

    def __init__(self, files_dir: Path, db_path: Optional[Path] = None):
        """
        Initialize orphan file filter.

        Args:
            files_dir: Path to the files directory
            db_path: Optional path to database for metadata hints
        """
        self.files_dir = Path(files_dir)
        self.db_path = Path(db_path) if db_path else None
        self.known_content_ids: Set[str] = set()
        self.file_hashes: Dict[str, Path] = {}

    def load_known_content_ids(self, conn: sqlite3.Connection) -> None:
        """Load known contentIDs from database to identify true orphans."""
        cursor = conn.execute(
            "SELECT DISTINCT contentID FROM Files WHERE contentID IS NOT NULL AND contentID != ''"
        )
        self.known_content_ids = {row[0] for row in cursor.fetchall()}

    def hash_file_fast(self, file_path: Path, chunk_size: int = 8192) -> str:
        """Generate fast hash of file for duplicate detection."""
        hasher = hashlib.blake2b(digest_size=16)  # Fast, good enough for duplicates
        try:
            with open(file_path, "rb") as f:
                # Hash first chunk + file size for speed
                first_chunk = f.read(chunk_size)
                hasher.update(first_chunk)

                # Add file size to hash
                file_size = file_path.stat().st_size
                hasher.update(file_size.to_bytes(8, byteorder="big"))

                # For larger files, also hash a middle and end chunk
                if file_size > chunk_size * 3:
                    f.seek(file_size // 2)
                    hasher.update(f.read(chunk_size))
                    f.seek(-chunk_size, 2)  # Seek to end - chunk_size
                    hasher.update(f.read(chunk_size))

        except (OSError, IOError):
            # For unreadable files, hash the path and size
            hasher.update(str(file_path).encode("utf-8"))
            try:
                hasher.update(file_path.stat().st_size.to_bytes(8, byteorder="big"))
            except OSError:
                pass

        return hasher.hexdigest()

    def is_size_based_skip(self, file_path: Path, file_size: int) -> Tuple[bool, str]:
        """Check if file should be skipped based on size heuristics."""
        if file_size == 0:
            return True, "zero_byte_file"

        if file_size <= TINY_FILE_MAX_SIZE:
            return True, "tiny_file_likely_metadata"

        # Check for thumbnail-like files under size threshold
        if file_size <= THUMBNAIL_MAX_SIZE:
            filename = file_path.name.lower()
            if any(
                pattern in filename for pattern in ["thumb", "preview", "cache", "temp"]
            ):
                return True, "small_file_with_thumbnail_name"

        return False, ""

    def is_pattern_based_skip(self, file_path: Path) -> Tuple[bool, str]:
        """Check if file should be skipped based on naming patterns."""
        filename = file_path.name.lower()

        # Check skip patterns
        for pattern in SKIP_PATTERNS:
            if re.match(pattern, filename):
                return True, f"matches_skip_pattern_{pattern}"

        # Check file extensions
        if file_path.suffix.lower() in SKIP_EXTENSIONS:
            return True, f"skip_extension_{file_path.suffix}"

        return False, ""

    def is_content_duplicate(self, file_path: Path) -> Tuple[bool, str, Optional[Path]]:
        """Check if file is a content duplicate of a known file."""
        file_hash = self.hash_file_fast(file_path)

        if file_hash in self.file_hashes:
            original_path = self.file_hashes[file_hash]
            return True, "content_duplicate", original_path
        else:
            self.file_hashes[file_hash] = file_path
            return False, "", None

    def is_database_orphan(self, file_path: Path) -> bool:
        """Check if file is truly orphaned (not referenced in database)."""
        # Extract potential contentID from file path
        content_id = file_path.name

        # Files in the database are not orphans
        return content_id not in self.known_content_ids

    def classify_orphan_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Classify an orphan file and determine if it should be skipped.

        Returns:
            Dictionary with classification results
        """
        try:
            file_size = file_path.stat().st_size
        except OSError:
            return {
                "skip": True,
                "reason": "file_access_error",
                "file_path": file_path,
                "file_size": 0,
                "is_true_orphan": True,
            }

        classification = {
            "skip": False,
            "reason": "",
            "file_path": file_path,
            "file_size": file_size,
            "is_true_orphan": self.is_database_orphan(file_path),
            "duplicate_of": None,
        }

        # Skip non-orphan files (shouldn't happen, but safety check)
        if not classification["is_true_orphan"]:
            classification.update(
                {"skip": True, "reason": "not_orphan_has_database_entry"}
            )
            return classification

        # Size-based filtering
        skip, reason = self.is_size_based_skip(file_path, file_size)
        if skip:
            classification.update({"skip": True, "reason": reason})
            return classification

        # Pattern-based filtering
        skip, reason = self.is_pattern_based_skip(file_path)
        if skip:
            classification.update({"skip": True, "reason": reason})
            return classification

        # Content duplicate detection
        skip, reason, duplicate_path = self.is_content_duplicate(file_path)
        if skip:
            classification.update(
                {"skip": True, "reason": reason, "duplicate_of": duplicate_path}
            )
            return classification

        # File passed all filters - it's a legitimate orphan to recover
        classification.update({"skip": False, "reason": "legitimate_orphan"})
        return classification

    def filter_orphan_files(self, orphan_files: List[Path]) -> Dict[str, Any]:
        """
        Filter a list of orphan files and provide comprehensive statistics.

        Args:
            orphan_files: List of orphan file paths

        Returns:
            Dictionary with filtered files and statistics
        """
        # Load database content IDs if available
        if self.db_path and self.db_path.exists():
            try:
                conn = sqlite3.connect(self.db_path)
                self.load_known_content_ids(conn)
                conn.close()
            except sqlite3.Error:
                pass

        # Classify all orphan files
        results = {
            "total_orphans": len(orphan_files),
            "keep_files": [],
            "skip_files": [],
            "skip_reasons": defaultdict(int),
            "total_skip_size": 0,
            "total_keep_size": 0,
            "duplicates_found": [],
        }

        for file_path in orphan_files:
            classification = self.classify_orphan_file(file_path)

            if classification["skip"]:
                results["skip_files"].append(classification)
                results["skip_reasons"][classification["reason"]] += 1
                results["total_skip_size"] += classification["file_size"]

                if classification["duplicate_of"]:
                    results["duplicates_found"].append(classification)
            else:
                results["keep_files"].append(classification)
                results["total_keep_size"] += classification["file_size"]

        # Calculate statistics
        results.update(
            {
                "skip_count": len(results["skip_files"]),
                "keep_count": len(results["keep_files"]),
                "skip_percentage": (len(results["skip_files"]) / len(orphan_files))
                * 100
                if orphan_files
                else 0,
                "size_reduction_percentage": (
                    results["total_skip_size"]
                    / (results["total_skip_size"] + results["total_keep_size"])
                )
                * 100
                if (results["total_skip_size"] + results["total_keep_size"]) > 0
                else 0,
            }
        )

        return results

    def get_filtered_orphan_paths(self, orphan_files: List[Path]) -> List[Path]:
        """Get list of orphan files that should be kept (not skipped)."""
        results = self.filter_orphan_files(orphan_files)
        return [item["file_path"] for item in results["keep_files"]]


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def print_orphan_filter_summary(results: Dict[str, Any]) -> None:
    """Print a comprehensive summary of orphan filtering results."""
    print(f"\n📋 Orphan File Filtering Results:")
    print(f"   Total orphan files: {results['total_orphans']:,}")
    print(
        f"   Files to keep: {results['keep_count']:,} ({100 - results['skip_percentage']:.1f}%)"
    )
    print(
        f"   Files to skip: {results['skip_count']:,} ({results['skip_percentage']:.1f}%)"
    )

    if results["total_skip_size"] > 0:
        print(
            f"   Size reduction: {format_size(results['total_skip_size'])} ({results['size_reduction_percentage']:.1f}%)"
        )

    if results["skip_reasons"]:
        print(f"\n📊 Skip reasons breakdown:")
        for reason, count in sorted(
            results["skip_reasons"].items(), key=lambda x: x[1], reverse=True
        ):
            print(f"   {reason.replace('_', ' ').title()}: {count:,} files")

    if results["duplicates_found"]:
        print(f"   Content duplicates found: {len(results['duplicates_found']):,}")
