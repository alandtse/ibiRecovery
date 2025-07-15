"""Tests for backup database functionality."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ibirecovery.core.database import detect_ibi_structure, get_merged_files_with_albums


class TestBackupDatabaseDetection:
    """Test backup database detection functionality."""

    def test_detect_backup_database_standard_structure(self, temp_dir):
        """Test detection of backup database in standard ibi structure."""
        # Create standard ibi structure with backup
        ibi_root = temp_dir / "ibi_root"
        data_dir = ibi_root / "restsdk" / "data"
        db_dir = data_dir / "db"
        backup_dir = data_dir / "dbBackup"
        files_dir = data_dir / "files"

        db_dir.mkdir(parents=True)
        backup_dir.mkdir(parents=True)
        files_dir.mkdir(parents=True)

        # Create database files
        main_db = db_dir / "index.db"
        backup_db = backup_dir / "index.db"

        main_db.touch()
        backup_db.touch()

        # Test detection
        db_path, files_path, backup_db_path = detect_ibi_structure(ibi_root)

        assert db_path == main_db
        assert files_path == files_dir
        assert backup_db_path == backup_db

    def test_detect_backup_database_missing(self, temp_dir):
        """Test detection when backup database doesn't exist."""
        # Create structure without backup
        ibi_root = temp_dir / "ibi_root"
        data_dir = ibi_root / "restsdk" / "data"
        db_dir = data_dir / "db"
        files_dir = data_dir / "files"

        db_dir.mkdir(parents=True)
        files_dir.mkdir(parents=True)

        # Create only main database
        main_db = db_dir / "index.db"
        main_db.touch()

        # Test detection
        db_path, files_path, backup_db_path = detect_ibi_structure(ibi_root)

        assert db_path == main_db
        assert files_path == files_dir
        assert backup_db_path is None

    def test_detect_backup_database_alternative_structure(self, temp_dir):
        """Test detection in alternative directory structures."""
        # Create alternative structure: root/data/
        ibi_root = temp_dir / "ibi_root"
        data_dir = ibi_root / "data"
        db_dir = data_dir / "db"
        backup_dir = data_dir / "dbBackup"
        files_dir = data_dir / "files"

        db_dir.mkdir(parents=True)
        backup_dir.mkdir(parents=True)
        files_dir.mkdir(parents=True)

        # Create database files
        main_db = db_dir / "index.db"
        backup_db = backup_dir / "index.db"

        main_db.touch()
        backup_db.touch()

        # Test detection
        db_path, files_path, backup_db_path = detect_ibi_structure(ibi_root)

        assert db_path == main_db
        assert files_path == files_dir
        assert backup_db_path == backup_db


class TestBackupDatabaseMerging:
    """Test backup database merging functionality."""

    def create_test_database(self, db_path, files_data):
        """Helper to create a test database with files."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Create simplified Files table
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

        # Insert test files
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

    def test_merge_with_backup_additional_files(self, temp_dir):
        """Test merging when backup database has additional files."""
        # Create main database
        main_db = temp_dir / "main.db"
        main_files = [
            {
                "id": "file1",
                "name": "photo1.jpg",
                "contentID": "content1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            }
        ]
        self.create_test_database(main_db, main_files)

        # Create backup database with additional files
        backup_db = temp_dir / "backup.db"
        backup_files = [
            {
                "id": "file1",
                "name": "photo1.jpg",
                "contentID": "content1",  # Same as main
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            },
            {
                "id": "file2",
                "name": "photo2.jpg",
                "contentID": "content2",  # Only in backup
                "mimeType": "image/jpeg",
                "size": 2000000,
                "imageDate": 1640995300000,
                "cTime": 1640995300000,
            },
        ]
        self.create_test_database(backup_db, backup_files)

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
                if item["file"]["contentID"] == "content2"
            ),
            None,
        )
        assert backup_file is not None
        assert backup_file["file"]["_source"] == "backup"

    def test_merge_with_no_additional_files(self, temp_dir):
        """Test merging when backup has no additional files."""
        # Create identical files in both databases
        files_data = [
            {
                "id": "file1",
                "name": "photo1.jpg",
                "contentID": "content1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            }
        ]

        main_db = temp_dir / "main.db"
        backup_db = temp_dir / "backup.db"

        self.create_test_database(main_db, files_data)
        self.create_test_database(backup_db, files_data)

        # Test merging
        files_with_albums, stats = get_merged_files_with_albums(main_db, backup_db)

        # Should only have files from main database
        assert len(files_with_albums) == 1
        assert stats["total_files"] == 1
        assert stats["backup_recovered"] == 0

        # File should not have backup source marker
        assert "_source" not in files_with_albums[0]["file"]

    def test_merge_without_backup_database(self, temp_dir):
        """Test merging when no backup database exists."""
        # Create only main database
        main_db = temp_dir / "main.db"
        main_files = [
            {
                "id": "file1",
                "name": "photo1.jpg",
                "contentID": "content1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            }
        ]
        self.create_test_database(main_db, main_files)

        # Test merging without backup
        files_with_albums, stats = get_merged_files_with_albums(main_db, None)

        assert len(files_with_albums) == 1
        assert stats["total_files"] == 1
        assert stats["backup_recovered"] == 0

    def test_merge_with_corrupted_backup(self, temp_dir):
        """Test merging when backup database is corrupted."""
        # Create main database
        main_db = temp_dir / "main.db"
        main_files = [
            {
                "id": "file1",
                "name": "photo1.jpg",
                "contentID": "content1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            }
        ]
        self.create_test_database(main_db, main_files)

        # Create corrupted backup database
        backup_db = temp_dir / "backup_corrupted.db"
        backup_db.write_bytes(b"not a valid sqlite database")

        # Test merging with corrupted backup - should handle gracefully
        files_with_albums, stats = get_merged_files_with_albums(main_db, backup_db)

        # Should only have files from main database
        assert len(files_with_albums) == 1
        assert stats["total_files"] == 1
        assert stats["backup_recovered"] == 0

    def test_merge_statistics_calculation(self, temp_dir):
        """Test that statistics are correctly calculated when merging."""
        # Create main database
        main_db = temp_dir / "main.db"
        main_files = [
            {
                "id": "file1",
                "name": "image.jpg",
                "contentID": "content1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            }
        ]
        self.create_test_database(main_db, main_files)

        # Create backup database with different file types
        backup_db = temp_dir / "backup.db"
        backup_files = [
            {
                "id": "file2",
                "name": "video.mp4",
                "contentID": "content2",
                "mimeType": "video/mp4",
                "size": 5000000,
                "videoDate": 1640995300000,
                "cTime": 1640995300000,
            },
            {
                "id": "file3",
                "name": "document.pdf",
                "contentID": "content3",
                "mimeType": "application/pdf",
                "size": 500000,
                "cTime": 1640995400000,
            },
        ]
        self.create_test_database(backup_db, backup_files)

        # Test merging
        files_with_albums, stats = get_merged_files_with_albums(main_db, backup_db)

        # Verify statistics
        assert stats["total_files"] == 3
        assert stats["total_size"] == 6500000  # 1M + 5M + 0.5M
        assert stats["backup_recovered"] == 2

        # Check size by type statistics
        assert "size_by_type" in stats
        assert stats["size_by_type"]["images"] == 1000000
        assert stats["size_by_type"]["videos"] == 5000000
        assert stats["size_by_type"]["documents"] == 500000


class TestReferenceImplementationBackup:
    """Test backup database support in reference implementation."""

    def test_reference_implementation_with_backup(self, temp_dir):
        """Test reference implementation backup database integration."""
        # Import the reference implementation
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent / "docs"))

        try:
            from reference_implementation import IbiDatabaseParser
        except ImportError:
            pytest.skip("Reference implementation not available")

        # Create test databases
        main_db = temp_dir / "main.db"
        backup_db = temp_dir / "backup.db"

        # Create simple main database with complete schema
        conn = sqlite3.connect(main_db)
        conn.execute(
            """
            CREATE TABLE Files(
                id TEXT PRIMARY KEY,
                name TEXT,
                contentID TEXT,
                mimeType TEXT,
                size INTEGER,
                cTime INTEGER,
                birthTime INTEGER,
                uTime INTEGER,
                mTime INTEGER,
                imageDate INTEGER,
                videoDate INTEGER,
                imageWidth INTEGER DEFAULT 0,
                imageHeight INTEGER DEFAULT 0
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE FilesTags (
                fileID TEXT,
                tag TEXT,
                auto INTEGER,
                FOREIGN KEY (fileID) REFERENCES Files(id)
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE FileGroups(
                id TEXT PRIMARY KEY,
                name TEXT,
                estCount INTEGER DEFAULT 0
            )
        """
        )
        conn.execute(
            """
            INSERT INTO Files (id, name, contentID, mimeType, size, cTime, birthTime, imageDate, imageWidth, imageHeight)
            VALUES ('file1', 'test.jpg', 'content1', 'image/jpeg', 1000, 1640995200, 1640995200, 1640995200, 1920, 1080)
        """
        )
        conn.commit()
        conn.close()

        # Create backup database with additional file
        conn = sqlite3.connect(backup_db)
        conn.execute(
            """
            CREATE TABLE Files(
                id TEXT PRIMARY KEY,
                name TEXT,
                contentID TEXT,
                mimeType TEXT,
                size INTEGER,
                cTime INTEGER,
                birthTime INTEGER,
                uTime INTEGER,
                mTime INTEGER,
                imageDate INTEGER,
                videoDate INTEGER,
                imageWidth INTEGER DEFAULT 0,
                imageHeight INTEGER DEFAULT 0
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE FilesTags (
                fileID TEXT,
                tag TEXT,
                auto INTEGER,
                FOREIGN KEY (fileID) REFERENCES Files(id)
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE FileGroups(
                id TEXT PRIMARY KEY,
                name TEXT,
                estCount INTEGER DEFAULT 0
            )
        """
        )
        conn.execute(
            """
            INSERT INTO Files (id, name, contentID, mimeType, size, cTime, birthTime, imageDate, imageWidth, imageHeight)
            VALUES ('file1', 'test.jpg', 'content1', 'image/jpeg', 1000, 1640995200, 1640995200, 1640995200, 1920, 1080)
        """
        )
        conn.execute(
            """
            INSERT INTO Files (id, name, contentID, mimeType, size, cTime, birthTime, imageDate, imageWidth, imageHeight)
            VALUES ('file2', 'backup.jpg', 'content2', 'image/jpeg', 2000, 1640995300, 1640995300, 1640995300, 1920, 1080)
        """
        )
        conn.commit()
        conn.close()

        # Test parser with backup database
        parser = IbiDatabaseParser(str(main_db), backup_db_path=str(backup_db))

        with parser:
            files = parser.get_all_files()

            # Should get files from both databases
            assert len(files) == 2

            # Check that backup file is marked
            backup_file = next((f for f in files if f["contentID"] == "content2"), None)
            assert backup_file is not None
            assert backup_file["_source"] == "backup"

    def test_reference_implementation_without_backup(self, temp_dir):
        """Test reference implementation without backup database."""
        # Import the reference implementation
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent / "docs"))

        try:
            from reference_implementation import IbiDatabaseParser
        except ImportError:
            pytest.skip("Reference implementation not available")

        # Create only main database
        main_db = temp_dir / "main.db"

        conn = sqlite3.connect(main_db)
        conn.execute(
            """
            CREATE TABLE Files(
                id TEXT PRIMARY KEY,
                name TEXT,
                contentID TEXT,
                mimeType TEXT,
                size INTEGER,
                cTime INTEGER,
                birthTime INTEGER,
                uTime INTEGER,
                mTime INTEGER,
                imageDate INTEGER,
                videoDate INTEGER,
                imageWidth INTEGER DEFAULT 0,
                imageHeight INTEGER DEFAULT 0
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE FilesTags (
                fileID TEXT,
                tag TEXT,
                auto INTEGER,
                FOREIGN KEY (fileID) REFERENCES Files(id)
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE FileGroups(
                id TEXT PRIMARY KEY,
                name TEXT,
                estCount INTEGER DEFAULT 0
            )
        """
        )
        conn.execute(
            """
            INSERT INTO Files (id, name, contentID, mimeType, size, cTime, birthTime, imageDate, imageWidth, imageHeight)
            VALUES ('file1', 'test.jpg', 'content1', 'image/jpeg', 1000, 1640995200, 1640995200, 1640995200, 1920, 1080)
        """
        )
        conn.commit()
        conn.close()

        # Test parser without backup database
        parser = IbiDatabaseParser(str(main_db))

        with parser:
            files = parser.get_all_files()

            # Should get only main database files
            assert len(files) == 1
            assert files[0]["contentID"] == "content1"
            assert "_source" not in files[0]


class TestBackupDatabaseErrorHandling:
    """Test error handling in backup database functionality."""

    def test_backup_database_permission_error(self, temp_dir):
        """Test handling when backup database has permission issues."""
        # Create main database
        main_db = temp_dir / "main.db"
        main_files = [
            {
                "id": "file1",
                "name": "photo1.jpg",
                "contentID": "content1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            }
        ]

        conn = sqlite3.connect(main_db)
        cursor = conn.cursor()
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
        cursor.execute(
            """
            CREATE TABLE FileGroups(
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                estCount INTEGER NOT NULL DEFAULT 0
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE FileGroupFiles(
                id TEXT NOT NULL PRIMARY KEY,
                fileID TEXT NOT NULL REFERENCES Files(id),
                fileGroupID TEXT NOT NULL REFERENCES FileGroups(id)
            )
        """
        )

        for file_data in main_files:
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

        # Create inaccessible backup database
        backup_db = temp_dir / "backup.db"
        backup_db.touch()
        backup_db.chmod(0o000)  # No permissions

        try:
            # Should handle permission errors gracefully
            # Mock connect_db to not exit on error for this test
            with patch("ibirecovery.core.database.connect_db") as mock_connect:

                def side_effect(db_path):
                    if db_path == backup_db:
                        # Simulate backup database connection failure
                        raise sqlite3.OperationalError("unable to open database file")
                    # Return real connection for main database
                    conn = sqlite3.connect(db_path)
                    conn.row_factory = sqlite3.Row
                    return conn

                mock_connect.side_effect = side_effect

                files_with_albums, stats = get_merged_files_with_albums(
                    main_db, backup_db
                )

                # Should only have files from main database
                assert len(files_with_albums) == 1
                assert stats["total_files"] == 1
                assert stats["backup_recovered"] == 0

        finally:
            # Restore permissions for cleanup
            backup_db.chmod(0o644)

    def test_backup_database_nonexistent_path(self, temp_dir):
        """Test handling when backup database path doesn't exist."""
        # Create main database
        main_db = temp_dir / "main.db"
        main_files = [
            {
                "id": "file1",
                "name": "photo1.jpg",
                "contentID": "content1",
                "mimeType": "image/jpeg",
                "size": 1000000,
                "imageDate": 1640995200000,
                "cTime": 1640995200000,
            }
        ]

        conn = sqlite3.connect(main_db)
        cursor = conn.cursor()
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
        cursor.execute(
            """
            CREATE TABLE FileGroups(
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                estCount INTEGER NOT NULL DEFAULT 0
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE FileGroupFiles(
                id TEXT NOT NULL PRIMARY KEY,
                fileID TEXT NOT NULL REFERENCES Files(id),
                fileGroupID TEXT NOT NULL REFERENCES FileGroups(id)
            )
        """
        )

        for file_data in main_files:
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

        # Non-existent backup database path
        backup_db = temp_dir / "nonexistent" / "backup.db"

        # Should handle gracefully
        files_with_albums, stats = get_merged_files_with_albums(main_db, backup_db)

        assert len(files_with_albums) == 1
        assert stats["total_files"] == 1
        assert stats["backup_recovered"] == 0
