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
                    # Go up from /restsdk/data/files to ibi root (3 levels)
                    ibi_root = files_dir.parent.parent.parent
                    user_dir = ibi_root / relative_path

                    # Try direct path first
                    user_file_path = user_dir / file_name
                    if user_file_path.exists():
                        conn.close()
                        return user_file_path

                    # Enhanced recursive search for userStorage files
                    if user_dir.exists():
                        # Search recursively using rglob to handle complex album structures
                        # Filter to only return actual files, not directories
                        matching_files = [
                            p for p in user_dir.rglob(file_name) if p.is_file()
                        ]
                        if matching_files:
                            conn.close()
                            return matching_files[0]  # Return first match

                # Handle alternative path structures
                elif "/userStorage/" in fs_path:
                    # Direct userStorage reference
                    user_path_part = fs_path.split("/userStorage/")[-1]
                    ibi_root = files_dir.parent.parent.parent
                    user_dir = ibi_root / "userStorage" / user_path_part

                    # Search recursively in this structure too
                    if user_dir.exists():
                        # Filter to only return actual files, not directories
                        matching_files = [
                            p for p in user_dir.rglob(file_name) if p.is_file()
                        ]
                        if matching_files:
                            conn.close()
                            return matching_files[0]  # Return first match

            conn.close()
        except Exception as e:
            # Fallback to traditional method if userStorage lookup fails
            # Add debugging for production troubleshooting
            import os

            if os.environ.get("IBI_DEBUG"):
                print(
                    f"UserStorage lookup failed for {file_name} (storage: {storage_id}): {e}"
                )
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
