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


def find_source_file(files_dir: Path, content_id: str) -> Optional[Path]:
    """Find the actual file using contentID."""
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
