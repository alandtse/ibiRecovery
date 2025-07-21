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


def detect_ibi_structure(
    root_path: Path,
) -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """
    Auto-detect ibi database and files directory structure.

    Returns:
        Tuple of (db_path, files_path, backup_db_path) or (None, None, None) if not found
    """
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


def connect_db(db_path: Path) -> sqlite3.Connection:
    """Connect to the SQLite database."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


class ReadOnlyConnection:
    """Wrapper for sqlite3.Connection that tracks temporary files for cleanup."""

    def __init__(self, conn: sqlite3.Connection, temp_db_path: str = None):
        self.conn = conn
        self.temp_db_path = temp_db_path

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if self.conn:
            self.conn.close()
        if self.temp_db_path:
            import os

            try:
                os.unlink(self.temp_db_path)
            except OSError:
                pass  # File might already be deleted


def connect_db_readonly(db_path: Path) -> ReadOnlyConnection:
    """Connect to the SQLite database in read-only mode."""
    import shutil
    import tempfile

    try:
        # First try direct URI syntax for read-only access
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        # Test if we can actually query the database with a real table
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1"
        ).fetchone()
        return ReadOnlyConnection(conn)
    except sqlite3.Error:
        # Fallback: copy database to temporary location for read access
        # This handles mounted filesystems where URI syntax fails
        try:
            # Check if file exists before trying to copy
            if not db_path.exists():
                raise sqlite3.Error(f"Database file does not exist: {db_path}")

            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
                shutil.copy2(db_path, tmp_file.name)
                conn = sqlite3.connect(tmp_file.name)
                conn.row_factory = sqlite3.Row
                return ReadOnlyConnection(conn, tmp_file.name)
        except (OSError, IOError, shutil.Error) as e:
            print(f"Error connecting to database in read-only mode: {e}")
            raise sqlite3.Error(f"Cannot access database: {e}") from e
        except Exception as e:
            print(f"Error connecting to database in read-only mode: {e}")
            raise


def get_merged_files_with_albums(
    main_db_path: Path, backup_db_path: Optional[Path] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Get files from main database and optionally merge with backup database.

    This helps recover orphaned files by finding entries that exist in backup
    but not in main database.

    Returns:
        Tuple of (files_with_albums, stats)
    """
    # Get files from main database using read-only mode for mounted filesystems
    try:
        main_conn = connect_db(main_db_path)
        files_with_albums, stats = get_all_files_with_albums(main_conn)
    except sqlite3.OperationalError as e:
        if "readonly database" in str(e).lower():
            print("⚠️  Main database is read-only, switching to read-only mode")
            main_conn.close()
            main_conn = connect_db_readonly(main_db_path)
            files_with_albums, stats = get_all_files_with_albums(main_conn)
        else:
            raise

    print(f"📊 Main database: {stats['total_files']} files")

    if backup_db_path and backup_db_path.exists():
        try:
            # Get files from backup database in read-only mode to avoid WAL issues
            backup_conn = connect_db_readonly(backup_db_path)
            backup_files, backup_stats = get_all_files_with_albums(backup_conn)

            print(f"📊 Backup database: {backup_stats['total_files']} files")

            # Create set of contentIDs from main database
            main_content_ids = {item["file"]["contentID"] for item in files_with_albums}

            # Find files in backup that aren't in main
            additional_files = []
            for backup_item in backup_files:
                backup_content_id = backup_item["file"]["contentID"]
                if backup_content_id not in main_content_ids:
                    # Mark as recovered from backup
                    backup_item["file"]["_source"] = "backup"
                    additional_files.append(backup_item)

            if additional_files:
                print(
                    f"🔄 Found {len(additional_files)} additional files in backup database"
                )
                files_with_albums.extend(additional_files)

                # Update statistics
                for item in additional_files:
                    file_size = item["file"]["size"] or 0
                    stats["total_size"] += file_size

                    mime_type = item["file"]["mimeType"] or ""
                    if mime_type.startswith("image/"):
                        stats["size_by_type"]["images"] = (
                            stats["size_by_type"].get("images", 0) + file_size
                        )
                    elif mime_type.startswith("video/"):
                        stats["size_by_type"]["videos"] = (
                            stats["size_by_type"].get("videos", 0) + file_size
                        )
                    elif mime_type.startswith("application/") or mime_type.startswith(
                        "text/"
                    ):
                        stats["size_by_type"]["documents"] = (
                            stats["size_by_type"].get("documents", 0) + file_size
                        )
                    else:
                        stats["size_by_type"]["other"] = (
                            stats["size_by_type"].get("other", 0) + file_size
                        )

                stats["total_files"] = len(files_with_albums)
                stats["backup_recovered"] = len(additional_files)
            else:
                print("ℹ️  No additional files found in backup database")
                stats["backup_recovered"] = 0

            # Clean up temporary database file if it exists
            backup_conn.close()

        except sqlite3.Error as e:
            print(f"⚠️  Warning: Could not read backup database: {e}")
            stats["backup_recovered"] = 0
    else:
        print("ℹ️  No backup database available")
        stats["backup_recovered"] = 0

    main_conn.close()
    return files_with_albums, stats


def get_all_files_with_albums(
    conn: sqlite3.Connection,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Get all files with their album memberships and calculate statistics."""
    # Check if database has storageID column (modern schema)
    has_storage_id = False
    try:
        conn.execute("SELECT storageID FROM Files LIMIT 1")
        has_storage_id = True
    except sqlite3.OperationalError:
        has_storage_id = False

    # Build query based on schema
    if has_storage_id:
        files_query = """
        SELECT f.id, f.name, f.contentID, f.mimeType, f.size,
               f.imageDate, f.videoDate, f.cTime, f.storageID
        FROM Files f
        WHERE f.contentID IS NOT NULL AND f.contentID != ''
        ORDER BY COALESCE(f.videoDate, f.imageDate, f.cTime)
        """
    else:
        # Legacy schema without storageID
        files_query = """
        SELECT f.id, f.name, f.contentID, f.mimeType, f.size,
               f.imageDate, f.videoDate, f.cTime, 'local' as storageID
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
