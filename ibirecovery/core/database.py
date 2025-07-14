#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Database operations for ibiRecovery.

Handles database connections, structure detection, and data queries.

Copyright (C) 2024 ibiRecovery Contributors
Licensed under GPL-3.0-or-later
"""

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def detect_ibi_structure(root_path: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Auto-detect ibi database and files directory structure.

    Returns:
        Tuple of (db_path, files_path) or (None, None) if not found
    """
    root_path = Path(root_path)

    # Common ibi directory structures to check
    candidates = [
        # Standard structure: root/restsdk/data/
        (
            root_path / "restsdk" / "data" / "db" / "index.db",
            root_path / "restsdk" / "data" / "files",
        ),
        # Alternative: direct in data folder
        (root_path / "data" / "db" / "index.db", root_path / "data" / "files"),
        # Alternative: root contains db and files directly
        (root_path / "db" / "index.db", root_path / "files"),
        # Alternative: index.db in root
        (root_path / "index.db", root_path / "files"),
    ]

    for db_path, files_path in candidates:
        if db_path.exists() and files_path.exists():
            print(f"✅ Detected ibi structure:")
            print(f"   Database: {db_path}")
            print(f"   Files: {files_path}")
            return db_path, files_path

    return None, None


def connect_db(db_path: Path) -> sqlite3.Connection:
    """Connect to the SQLite database."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def get_all_files_with_albums(
    conn: sqlite3.Connection,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Get all files with their album memberships and calculate statistics."""
    # First get all files with size information
    files_query = """
    SELECT f.id, f.name, f.contentID, f.mimeType, f.size,
           f.imageDate, f.videoDate, f.cTime
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


def get_comprehensive_export_data(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Get comprehensive file and metadata for export purposes."""
    query = """
    SELECT
        f.name,
        f.contentID,
        f.mimeType,
        f.size,
        f.imageDate,
        f.videoDate,
        f.cTime,
        f.birthTime,
        f.gpsLatitude,
        f.gpsLongitude,
        f.cameraModel,
        f.cameraMake,
        f.description,
        GROUP_CONCAT(fg.name, ';') as albums,
        GROUP_CONCAT(t.value, ';') as tags
    FROM Files f
    LEFT JOIN FileGroupFiles fgf ON f.id = fgf.fileID
    LEFT JOIN FileGroups fg ON fgf.fileGroupID = fg.id
    LEFT JOIN Tags t ON f.id = t.fileID
    WHERE f.contentID IS NOT NULL AND f.contentID != ''
    GROUP BY f.id
    ORDER BY f.name
    """

    results = conn.execute(query).fetchall()

    # Convert to dictionaries for easier manipulation
    export_data = []
    for row in results:
        file_data = dict(row)
        # Split concatenated fields
        if file_data.get("albums"):
            file_data["albums"] = file_data["albums"].split(";")
        else:
            file_data["albums"] = []

        if file_data.get("tags"):
            file_data["tags"] = file_data["tags"].split(";")
        else:
            file_data["tags"] = []

        export_data.append(file_data)

    return export_data
