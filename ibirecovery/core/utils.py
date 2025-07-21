# SPDX-License-Identifier: GPL-3.0-or-later
"""
Utility functions for ibiRecovery.

General-purpose helper functions used across the toolkit.

Copyright (C) 2024 ibiRecovery Contributors
Licensed under GPL-3.0-or-later
"""

from pathlib import Path
from typing import Optional


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


def find_source_file(
    files_dir: Path,
    content_id: str,
    file_name: str = None,
    storage_id: str = None,
    db_path: Path = None,
) -> Optional[Path]:
    """
    Find the actual file using contentID with support for both traditional and userStorage structures.

    Args:
        files_dir: Base files directory path
        content_id: Content ID to search for
        file_name: Original filename (for userStorage structure)
        storage_id: Storage ID (for userStorage structure)
        db_path: Database path (for filesystem mapping lookup)
    """
    if not content_id:
        return None

    # Strategy 1: Try userStorage structure (newer ibi versions)
    if file_name and storage_id and db_path:
        try:
            from .database import connect_db_readonly

            conn = connect_db_readonly(db_path)

            # Get filesystem mapping for this storage_id
            fs_result = conn.execute(
                "SELECT name, path FROM Filesystems WHERE id = ?", (storage_id,)
            ).fetchone()

            if fs_result:
                fs_name, fs_path = fs_result
                # Convert from original path to current mount structure
                if "/data/wd/diskVolume0/" in fs_path:
                    relative_path = fs_path.replace("/data/wd/diskVolume0/", "")
                    # Construct path: ibi_root/userStorage/user_id/filename
                    # Go up from /restsdk/data/files to ibi root (3 levels)
                    ibi_root = files_dir.parent.parent.parent
                    user_file_path = ibi_root / relative_path / file_name

                    if user_file_path.exists():
                        conn.close()
                        return user_file_path

            conn.close()
        except Exception:
            # Fallback to traditional method if userStorage lookup fails
            pass

    # Strategy 2: Traditional ibi structure (contentID-based paths)
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
