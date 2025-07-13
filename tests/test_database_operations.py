"""Test database operations and parsing functionality."""

import os
import sqlite3
import sys
from pathlib import Path

import pytest

# Add the package to the path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ibirecovery.extract_files import (
    connect_db,
    detect_ibi_structure,
    get_all_files_with_albums,
    get_comprehensive_export_data,
)


class TestDatabaseOperations:
    """Test database connection and query operations."""

    def test_detect_ibi_structure_valid(self, mock_ibi_structure, mock_database):
        """Test detection of valid ibi directory structure."""
        root = mock_ibi_structure["root"]

        # The mock_database fixture creates the database, so detection should work
        db_path, files_path = detect_ibi_structure(root)

        assert db_path == mock_ibi_structure["db"] / "index.db"
        assert files_path == mock_ibi_structure["files"]

    def test_detect_ibi_structure_invalid(self, temp_dir):
        """Test detection with invalid directory structure."""
        invalid_root = temp_dir / "invalid"
        invalid_root.mkdir()

        # Should return (None, None) for invalid structure
        db_path, files_path = detect_ibi_structure(invalid_root)
        assert db_path is None
        assert files_path is None

    def test_detect_ibi_structure_direct_paths(self, mock_ibi_structure):
        """Test detection when given direct db/files paths."""
        db_path = mock_ibi_structure["db"] / "index.db"
        files_path = mock_ibi_structure["files"]

        # Create a dummy database file
        db_path.touch()

        detected_db, detected_files = detect_ibi_structure(mock_ibi_structure["root"])
        assert detected_db == db_path
        assert detected_files == files_path

    def test_connect_to_database_success(self, mock_database):
        """Test successful database connection."""
        conn = connect_db(mock_database)
        assert conn is not None

        # Test basic query
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Files")
        count = cursor.fetchone()[0]
        assert count == 4  # From our test data

        conn.close()

    def test_connect_to_database_missing(self, temp_dir):
        """Test connection to missing database file."""
        missing_db = temp_dir / "missing.db"

        # connect_db will create an empty database, but querying will fail
        conn = connect_db(missing_db)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("SELECT COUNT(*) FROM Files").fetchone()
        conn.close()

    def test_get_files_with_albums(self, mock_database):
        """Test retrieving files with album information."""
        conn = connect_db(mock_database)
        files, album_stats = get_all_files_with_albums(conn)
        conn.close()

        assert len(files) == 4

        # Check specific file data - files are returned as {'file': dict, 'albums': list}
        file1_record = next(f for f in files if f["file"]["name"] == "test1.jpg")
        file1 = file1_record["file"]
        albums = file1_record["albums"]

        assert file1["contentID"] == "a1b2c3d4e5f6"
        assert file1["mimeType"] == "image/jpeg"
        assert file1["size"] == 1024000
        assert len([a for a in albums if a["name"] == "Family Vacation"]) == 1
        # Note: Tags are not returned by get_all_files_with_albums, only by get_comprehensive_export_data

    def test_get_files_albums_organization(self, mock_database):
        """Test album organization in retrieved files."""
        conn = connect_db(mock_database)
        files, album_stats = get_all_files_with_albums(conn)
        conn.close()

        # Check album membership - albums are in f['albums'] as list of dicts
        family_vacation_files = [
            f for f in files if any(a["name"] == "Family Vacation" for a in f["albums"])
        ]
        work_files = [
            f for f in files if any(a["name"] == "Work Photos" for a in f["albums"])
        ]
        unorganized_files = [f for f in files if not f["albums"]]

        assert len(family_vacation_files) == 2  # test1.jpg, test2.mp4
        assert len(work_files) == 1  # test3.png
        assert len(unorganized_files) == 1  # missing.jpg (file4)

    def test_get_files_tags_classification(self, mock_database):
        """Test comprehensive export data with tags."""
        conn = connect_db(mock_database)
        export_data = get_comprehensive_export_data(conn)
        conn.close()

        # Check tag distributions - tags are only available in comprehensive export data
        files_with_person_tag = [
            f
            for f in export_data
            if any(t["tag"] == "person" for t in f.get("tags", []))
        ]
        files_with_auto_tags = [
            f for f in export_data if any(t for t in f.get("tags", []))
        ]

        assert len(files_with_person_tag) == 2  # test1.jpg, test2.mp4
        assert len(files_with_auto_tags) >= 3  # Most files should have tags

    def test_get_export_stats(self, mock_database):
        """Test export statistics generation."""
        conn = connect_db(mock_database)
        export_data = get_comprehensive_export_data(conn)
        conn.close()

        assert len(export_data) == 4

        # Check that export data contains expected file record fields
        first_file = export_data[0]
        expected_fields = ["file_record", "tags", "albums"]
        for field in expected_fields:
            assert field in first_file

        # Check file record structure
        file_record = first_file["file_record"]
        assert "name" in file_record
        assert "contentID" in file_record
        assert "mimeType" in file_record
        assert "size" in file_record

        # Check file type distribution
        image_files = [
            f for f in export_data if f["file_record"]["mimeType"].startswith("image/")
        ]
        video_files = [
            f for f in export_data if f["file_record"]["mimeType"].startswith("video/")
        ]

        assert len(image_files) >= 2  # JPEG and PNG files
        assert len(video_files) >= 1  # MP4 file


class TestDatabaseQueries:
    """Test specific database query functionality."""

    def test_gps_data_retrieval(self, mock_database):
        """Test GPS coordinate retrieval."""
        conn = connect_db(mock_database)
        export_data = get_comprehensive_export_data(conn)
        conn.close()

        # GPS data is in the comprehensive export data
        gps_files = [
            f
            for f in export_data
            if f["file_record"].get("imageLatitude")
            or f["file_record"].get("videoLatitude")
        ]
        assert len(gps_files) == 3  # test1.jpg, test2.mp4, and missing.jpg have GPS

        file1 = next(f for f in gps_files if f["file_record"]["name"] == "test1.jpg")
        assert abs(file1["file_record"]["imageLatitude"] - 37.7749) < 0.0001
        assert abs(file1["file_record"]["imageLongitude"] - (-122.4194)) < 0.0001

    def test_camera_metadata_retrieval(self, mock_database):
        """Test camera EXIF data retrieval."""
        conn = connect_db(mock_database)
        export_data = get_comprehensive_export_data(conn)
        conn.close()

        # Camera data is in the comprehensive export data
        camera_files = [
            f for f in export_data if f["file_record"].get("imageCameraMake")
        ]
        assert len(camera_files) == 2  # test1.jpg (Canon) and missing.jpg (Sony)

        canon_file = next(
            f for f in camera_files if f["file_record"]["imageCameraMake"] == "Canon"
        )
        assert canon_file["file_record"]["imageCameraModel"] == "EOS R5"

        sony_file = next(
            f for f in camera_files if f["file_record"]["imageCameraMake"] == "Sony"
        )
        assert sony_file["file_record"]["imageCameraModel"] == "A7R IV"

    def test_timestamp_handling(self, mock_database):
        """Test timestamp parsing and conversion."""
        conn = connect_db(mock_database)
        files, album_stats = get_all_files_with_albums(conn)
        conn.close()

        # All test files should have timestamps - check cTime field
        files_with_timestamps = [f for f in files if f["file"].get("cTime")]
        assert len(files_with_timestamps) == 4

        # Check that timestamps are reasonable (around 2022)
        for file_entry in files_with_timestamps:
            timestamp = file_entry["file"]["cTime"]
            # Should be roughly around 2022 (Unix timestamp)
            assert 1600000000 < timestamp < 1700000000
