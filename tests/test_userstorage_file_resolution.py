"""Tests for userStorage file resolution issues."""

import sqlite3
from pathlib import Path

import pytest

from ibirecovery.core.utils import find_source_file


class TestUserStorageFileResolution:
    """Test userStorage file resolution to ensure it returns files, not directories."""

    def test_userstorage_returns_file_not_directory(self, temp_dir):
        """Test that userStorage resolution returns files, not directories with same name."""
        # Create ibi structure
        ibi_root = temp_dir / "ibi_root"
        files_dir = ibi_root / "restsdk" / "data" / "files"
        files_dir.mkdir(parents=True)

        # Create userStorage structure with potential name conflicts
        user_storage = ibi_root / "userStorage" / "auth0|user123"
        album_dir = user_storage / "Samsung SM-G960U Camera Backup"
        album_dir.mkdir(parents=True)

        # Create a file with the same name as the directory (this is the conflict!)
        file_in_album = (
            album_dir / "Samsung SM-G960U Camera Backup.jpg"
        )  # File inside directory
        file_in_album.write_bytes(b"test image data")

        # Also create a file with different name in the same directory
        other_file = album_dir / "IMG_20220806_184402.jpg"
        other_file.write_bytes(b"other image data")

        # Create database with filesystem mapping
        db_path = temp_dir / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE Filesystems(
                id TEXT PRIMARY KEY,
                name TEXT,
                path TEXT,
                cTime INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO Filesystems (id, name, path, cTime)
            VALUES ('userfs1', 'auth0|user123', '/data/wd/diskVolume0/userStorage/auth0|user123', 1640995000000)
            """
        )
        conn.commit()
        conn.close()

        # Test 1: Searching for the directory name should return the .jpg file, not the directory
        result = find_source_file(
            files_dir,
            "contentID1",
            "Samsung SM-G960U Camera Backup.jpg",  # Looking for the file
            "userfs1",
            db_path,
        )

        assert result is not None
        assert result.is_file()  # Should be a file, not directory
        assert result == file_in_album
        assert not result.is_dir()  # Ensure it's not the directory

        # Test 2: Searching for a regular file should work normally
        result2 = find_source_file(
            files_dir, "contentID2", "IMG_20220806_184402.jpg", "userfs1", db_path
        )

        assert result2 is not None
        assert result2.is_file()
        assert result2 == other_file

    def test_userstorage_directory_name_conflict_multiple_matches(self, temp_dir):
        """Test handling when there are multiple potential matches (files and directories)."""
        # Create ibi structure
        ibi_root = temp_dir / "ibi_root"
        files_dir = ibi_root / "restsdk" / "data" / "files"
        files_dir.mkdir(parents=True)

        # Create userStorage structure with multiple potential conflicts
        user_storage = ibi_root / "userStorage" / "auth0|user123"

        # Create album directory
        album1_dir = user_storage / "Photos" / "Camera"
        album1_dir.mkdir(parents=True)

        album2_dir = user_storage / "Backup" / "Camera"  # Another "Camera" directory
        album2_dir.mkdir(parents=True)

        # Create files that could conflict
        file1 = album1_dir / "Camera.jpg"  # File named same as directory
        file1.write_bytes(b"camera photo 1")

        file2 = (
            album2_dir / "Camera.jpg"
        )  # Another file with same name in different location
        file2.write_bytes(b"camera photo 2")

        # Create database with filesystem mapping
        db_path = temp_dir / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE Filesystems(
                id TEXT PRIMARY KEY,
                name TEXT,
                path TEXT,
                cTime INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO Filesystems (id, name, path, cTime)
            VALUES ('userfs1', 'auth0|user123', '/data/wd/diskVolume0/userStorage/auth0|user123', 1640995000000)
            """
        )
        conn.commit()
        conn.close()

        # Search should return one of the files, not any directories
        result = find_source_file(
            files_dir, "contentID1", "Camera.jpg", "userfs1", db_path
        )

        assert result is not None
        assert result.is_file()  # Should be a file
        assert result in [file1, file2]  # Should be one of the actual files
        assert not result.is_dir()  # Should not be a directory

        # Verify the specific directories exist but weren't returned
        assert (user_storage / "Photos" / "Camera").is_dir()
        assert (user_storage / "Backup" / "Camera").is_dir()

    def test_userstorage_no_file_matches_only_directories(self, temp_dir):
        """Test when only directories match the name, not files."""
        # Create ibi structure
        ibi_root = temp_dir / "ibi_root"
        files_dir = ibi_root / "restsdk" / "data" / "files"
        files_dir.mkdir(parents=True)

        # Create userStorage structure with only directory matches
        user_storage = ibi_root / "userStorage" / "auth0|user123"
        album_dir = user_storage / "MyPhotos"
        album_dir.mkdir(parents=True)

        # Create some other files but NOT the one we're looking for
        other_file = album_dir / "SomeOtherFile.jpg"
        other_file.write_bytes(b"other content")

        # Create database with filesystem mapping
        db_path = temp_dir / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE Filesystems(
                id TEXT PRIMARY KEY,
                name TEXT,
                path TEXT,
                cTime INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO Filesystems (id, name, path, cTime)
            VALUES ('userfs1', 'auth0|user123', '/data/wd/diskVolume0/userStorage/auth0|user123', 1640995000000)
            """
        )
        conn.commit()
        conn.close()

        # Search for "MyPhotos.jpg" - only the directory "MyPhotos" exists, not a file
        result = find_source_file(
            files_dir,
            "contentID1",
            "MyPhotos.jpg",  # This file doesn't exist, only directory "MyPhotos"
            "userfs1",
            db_path,
        )

        # Should return None since no actual file matches, only directory
        assert result is None

        # Verify the directory exists (just not returned)
        assert album_dir.is_dir()
        assert album_dir.name == "MyPhotos"
