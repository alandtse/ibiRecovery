"""Tests for database compatibility between old and new ibi versions."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ibirecovery.core.database import (
    detect_ibi_structure,
    get_all_files_with_albums,
    get_merged_files_with_albums,
)


class TestDatabaseCompatibility:
    """Test compatibility between legacy and modern ibi database schemas."""

    def create_legacy_database(self, db_path, files_data):
        """Create a legacy ibi database without storageID column."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Create legacy Files table (without storageID)
        cursor.execute(
            """
            CREATE TABLE Files(
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                contentID TEXT UNIQUE,
                mimeType TEXT NOT NULL DEFAULT '',
                size INTEGER NOT NULL DEFAULT 0,
                imageDate INTEGER,
                videoDate INTEGER,
                cTime INTEGER NOT NULL
            )
        """
        )

        # Create FileGroups table
        cursor.execute(
            """
            CREATE TABLE FileGroups(
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                estCount INTEGER NOT NULL DEFAULT 0
            )
        """
        )

        # Create FileGroupFiles table
        cursor.execute(
            """
            CREATE TABLE FileGroupFiles(
                id TEXT NOT NULL PRIMARY KEY,
                fileID TEXT NOT NULL REFERENCES Files(id),
                fileGroupID TEXT NOT NULL REFERENCES FileGroups(id)
            )
        """
        )

        # Insert test files (legacy schema)
        for file_data in files_data:
            cursor.execute(
                """
                INSERT INTO Files (id, name, contentID, mimeType, size, imageDate, videoDate, cTime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    file_data["id"],
                    file_data["name"],
                    file_data["contentID"],
                    file_data["mimeType"],
                    file_data["size"],
                    file_data.get("imageDate"),
                    file_data.get("videoDate"),
                    file_data["cTime"],
                ),
            )

        conn.commit()
        conn.close()

    def create_modern_database(self, db_path, files_data):
        """Create a modern ibi database with storageID column and Filesystems table."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Create modern Files table (with storageID)
        cursor.execute(
            """
            CREATE TABLE Files(
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                contentID TEXT UNIQUE,
                mimeType TEXT NOT NULL DEFAULT '',
                size INTEGER NOT NULL DEFAULT 0,
                imageDate INTEGER,
                videoDate INTEGER,
                cTime INTEGER NOT NULL,
                storageID TEXT
            )
        """
        )

        # Create Filesystems table for userStorage mapping
        cursor.execute(
            """
            CREATE TABLE Filesystems(
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                cTime INTEGER NOT NULL,
                mTime INTEGER
            )
        """
        )

        # Create FileGroups table
        cursor.execute(
            """
            CREATE TABLE FileGroups(
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                estCount INTEGER NOT NULL DEFAULT 0
            )
        """
        )

        # Create FileGroupFiles table
        cursor.execute(
            """
            CREATE TABLE FileGroupFiles(
                id TEXT NOT NULL PRIMARY KEY,
                fileID TEXT NOT NULL REFERENCES Files(id),
                fileGroupID TEXT NOT NULL REFERENCES FileGroups(id)
            )
        """
        )

        # Insert filesystem mapping for userStorage
        cursor.execute(
            """
            INSERT INTO Filesystems (id, name, path, cTime)
            VALUES ('userfs1', 'auth0|user123', '/data/wd/diskVolume0/userStorage/auth0|user123', 1640995000000)
        """
        )

        # Insert test files (modern schema)
        for file_data in files_data:
            cursor.execute(
                """
                INSERT INTO Files (id, name, contentID, mimeType, size, imageDate, videoDate, cTime, storageID)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    file_data["id"],
                    file_data["name"],
                    file_data["contentID"],
                    file_data["mimeType"],
                    file_data["size"],
                    file_data.get("imageDate"),
                    file_data.get("videoDate"),
                    file_data["cTime"],
                    file_data.get("storageID", "local"),
                ),
            )

        conn.commit()
        conn.close()

    def test_legacy_database_compatibility(self, temp_dir):
        """Test that legacy databases (without storageID) work properly."""
        # Create legacy database
        legacy_db = temp_dir / "legacy.db"
        legacy_files = [
            {
                "id": "file1",
                "name": "legacy_photo.jpg",
                "contentID": "legacyContent1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            }
        ]
        self.create_legacy_database(legacy_db, legacy_files)

        # Test that we can read from legacy database
        files_with_albums, stats = get_merged_files_with_albums(legacy_db, None)

        assert len(files_with_albums) == 1
        assert stats["total_files"] == 1
        assert files_with_albums[0]["file"]["name"] == "legacy_photo.jpg"
        assert files_with_albums[0]["file"]["contentID"] == "legacyContent1"

    def test_modern_database_compatibility(self, temp_dir):
        """Test that modern databases (with storageID and Filesystems) work properly."""
        # Create modern database
        modern_db = temp_dir / "modern.db"
        modern_files = [
            {
                "id": "file1",
                "name": "modern_photo.jpg",
                "contentID": "modernContent1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
                "storageID": "local",
            },
            {
                "id": "file2",
                "name": "user_photo.jpg",
                "contentID": "userContent1",
                "mimeType": "image/jpeg",
                "size": 2000000,
                "imageDate": 1640995300000,
                "cTime": 1640995300000,
                "storageID": "userfs1",
            },
        ]
        self.create_modern_database(modern_db, modern_files)

        # Test that we can read from modern database
        files_with_albums, stats = get_merged_files_with_albums(modern_db, None)

        assert len(files_with_albums) == 2
        assert stats["total_files"] == 2

        # Check that both traditional and userStorage files are present
        file_names = {item["file"]["name"] for item in files_with_albums}
        assert "modern_photo.jpg" in file_names
        assert "user_photo.jpg" in file_names

    def test_mixed_database_merging(self, temp_dir):
        """Test merging legacy main database with modern backup database."""
        # Create legacy main database
        main_db = temp_dir / "main_legacy.db"
        main_files = [
            {
                "id": "file1",
                "name": "main_photo.jpg",
                "contentID": "mainContent1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            }
        ]
        self.create_legacy_database(main_db, main_files)

        # Create modern backup database
        backup_db = temp_dir / "backup_modern.db"
        backup_files = [
            {
                "id": "file1",
                "name": "main_photo.jpg",
                "contentID": "mainContent1",  # Same as main
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
                "storageID": "local",
            },
            {
                "id": "file2",
                "name": "backup_photo.jpg",
                "contentID": "backupContent1",  # Only in backup
                "mimeType": "image/jpeg",
                "size": 2000000,
                "imageDate": 1640995300000,
                "cTime": 1640995300000,
                "storageID": "userfs1",
            },
        ]
        self.create_modern_database(backup_db, backup_files)

        # Test merging
        files_with_albums, stats = get_merged_files_with_albums(main_db, backup_db)

        # Should have files from both databases
        assert len(files_with_albums) == 2
        assert stats["total_files"] == 2
        assert stats["backup_recovered"] == 1

        # Check that backup file is marked as such
        backup_file = next(
            (
                item
                for item in files_with_albums
                if item["file"]["contentID"] == "backupContent1"
            ),
            None,
        )
        assert backup_file is not None
        assert backup_file["file"]["_source"] == "backup"

    def test_modern_main_with_legacy_backup(self, temp_dir):
        """Test merging modern main database with legacy backup database."""
        # Create modern main database
        main_db = temp_dir / "main_modern.db"
        main_files = [
            {
                "id": "file1",
                "name": "main_photo.jpg",
                "contentID": "mainContent1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
                "storageID": "local",
            }
        ]
        self.create_modern_database(main_db, main_files)

        # Create legacy backup database
        backup_db = temp_dir / "backup_legacy.db"
        backup_files = [
            {
                "id": "file1",
                "name": "main_photo.jpg",
                "contentID": "mainContent1",  # Same as main
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            },
            {
                "id": "file2",
                "name": "backup_photo.jpg",
                "contentID": "backupContent1",  # Only in backup
                "mimeType": "image/jpeg",
                "size": 2000000,
                "imageDate": 1640995300000,
                "cTime": 1640995300000,
            },
        ]
        self.create_legacy_database(backup_db, backup_files)

        # Test merging
        files_with_albums, stats = get_merged_files_with_albums(main_db, backup_db)

        # Should have files from both databases
        assert len(files_with_albums) == 2
        assert stats["total_files"] == 2
        assert stats["backup_recovered"] == 1

        # Check that backup file is marked as such
        backup_file = next(
            (
                item
                for item in files_with_albums
                if item["file"]["contentID"] == "backupContent1"
            ),
            None,
        )
        assert backup_file is not None
        assert backup_file["file"]["_source"] == "backup"

    def test_database_schema_detection(self, temp_dir):
        """Test that we can detect legacy vs modern database schemas."""
        # Create legacy database
        legacy_db = temp_dir / "legacy.db"
        self.create_legacy_database(legacy_db, [])

        # Create modern database
        modern_db = temp_dir / "modern.db"
        self.create_modern_database(modern_db, [])

        # Check that both can be opened without errors
        legacy_conn = sqlite3.connect(legacy_db)
        legacy_conn.row_factory = sqlite3.Row

        modern_conn = sqlite3.connect(modern_db)
        modern_conn.row_factory = sqlite3.Row

        # Check table schemas
        legacy_tables = legacy_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        legacy_table_names = {row["name"] for row in legacy_tables}

        modern_tables = modern_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        modern_table_names = {row["name"] for row in modern_tables}

        # Legacy should have core tables but not Filesystems
        assert "Files" in legacy_table_names
        assert "FileGroups" in legacy_table_names
        assert "Filesystems" not in legacy_table_names

        # Modern should have all tables including Filesystems
        assert "Files" in modern_table_names
        assert "FileGroups" in modern_table_names
        assert "Filesystems" in modern_table_names

        legacy_conn.close()
        modern_conn.close()

    def test_error_handling_with_schema_differences(self, temp_dir):
        """Test graceful handling when schemas have unexpected differences."""
        # Create a database with missing expected tables
        broken_db = temp_dir / "broken.db"
        conn = sqlite3.connect(broken_db)

        # Only create Files table, missing other expected tables
        conn.execute(
            """
            CREATE TABLE Files(
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                contentID TEXT UNIQUE,
                mimeType TEXT NOT NULL DEFAULT '',
                size INTEGER NOT NULL DEFAULT 0,
                cTime INTEGER NOT NULL
            )
        """
        )
        conn.commit()
        conn.close()

        # Should handle gracefully even with incomplete schema
        try:
            files_with_albums, stats = get_merged_files_with_albums(broken_db, None)
            # Should return empty results rather than crash
            assert len(files_with_albums) == 0
            assert stats["total_files"] == 0
        except Exception as e:
            # If it does fail, it should be a graceful database error, not a crash
            assert (
                "database" in str(e).lower()
                or "sql" in str(e).lower()
                or "column" in str(e).lower()
            )

    def test_directory_metadata_filtering(self, temp_dir):
        """Test that directory metadata entries are filtered out during extraction."""
        # Create modern database with mixed files and directory metadata
        db_path = temp_dir / "modern.db"

        files_data = [
            # Regular file
            {
                "id": "file1",
                "name": "photo.jpg",
                "contentID": "content1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            },
            # Directory metadata entries (should be filtered out)
            {
                "id": "dir1",
                "name": "Samsung SM-G960U Camera Backup",
                "contentID": "ccpzskeo3lzjplaw7lipsoda",
                "mimeType": "application/x.wd.dir",
                "size": 0,
                "imageDate": None,
                "cTime": 1634887254000,
            },
            {
                "id": "dir2",
                "name": "auth0|5bb3b9d2f4cee6307c85560e",
                "contentID": "4ub6bom4bzldfcjm2jugt2x7",
                "mimeType": "application/x.wd.dir",
                "size": 0,
                "imageDate": None,
                "cTime": 1634887300973,
            },
            # Another regular file
            {
                "id": "file2",
                "name": "video.mp4",
                "contentID": "content2",
                "mimeType": "video/mp4",
                "size": 5000000,
                "videoDate": 1640995400000,
                "cTime": 1640995400000,
            },
        ]
        self.create_modern_database(db_path, files_data)

        # Get files using our database function
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        files_with_albums, stats = get_all_files_with_albums(conn)
        conn.close()

        # Should only return the 2 actual files, not the 2 directory entries
        assert len(files_with_albums) == 2
        assert stats["total_files"] == 2

        # Verify only actual files are returned
        returned_mime_types = {item["file"]["mimeType"] for item in files_with_albums}
        assert "application/x.wd.dir" not in returned_mime_types
        assert "image/jpeg" in returned_mime_types
        assert "video/mp4" in returned_mime_types

        # Verify specific files are returned
        file_names = {item["file"]["name"] for item in files_with_albums}
        assert "photo.jpg" in file_names
        assert "video.mp4" in file_names
        assert "Samsung SM-G960U Camera Backup" not in file_names
        assert "auth0|5bb3b9d2f4cee6307c85560e" not in file_names
