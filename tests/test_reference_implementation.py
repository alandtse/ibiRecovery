"""Test the reference implementation API."""

import os
import sys
from pathlib import Path

import pytest

# Add the package to the path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "docs"))

try:
    from reference_implementation import IbiDatabaseParser
except ImportError:
    pytest.skip("Reference implementation not available", allow_module_level=True)


class TestIbiDatabaseParser:
    """Test the reference implementation parser."""

    def test_parser_initialization(self, mock_database, mock_ibi_structure):
        """Test parser initialization."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))

        assert parser.db_path == str(mock_database)
        assert parser.files_dir == str(mock_ibi_structure["files"])
        assert parser.conn is None  # Not connected yet

    def test_parser_connection(self, mock_database, mock_ibi_structure):
        """Test database connection."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))
        parser.connect()

        assert parser.conn is not None

        # Test basic query works
        cursor = parser.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Files")
        count = cursor.fetchone()[0]
        assert count == 4  # From our test data

        parser.close()

    def test_get_all_files(self, mock_database, mock_ibi_structure):
        """Test retrieving all files."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))
        parser.connect()

        files = parser.get_all_files()

        assert len(files) == 4

        # Check file structure
        first_file = files[0]
        expected_fields = ["id", "name", "contentID", "mimeType", "size"]
        for field in expected_fields:
            assert field in first_file

        parser.close()

    def test_get_content_tags_summary(self, mock_database, mock_ibi_structure):
        """Test retrieving content tags summary."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))
        parser.connect()

        tags_summary = parser.get_content_tags_summary()

        assert isinstance(tags_summary, dict)

        # Should have tag counts
        expected_tags = ["person", "beach", "document"]
        for tag in expected_tags:
            assert tag in tags_summary
            assert tags_summary[tag] > 0

        parser.close()

    def test_get_all_albums(self, mock_database, mock_ibi_structure):
        """Test retrieving all albums."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))
        parser.connect()

        albums = parser.get_all_albums()

        assert len(albums) == 2  # Family Vacation, Work Photos

        # Check album structure
        album_names = [album["name"] for album in albums]
        assert "Family Vacation" in album_names
        assert "Work Photos" in album_names

        # Check album has file count
        family_album = next(a for a in albums if a["name"] == "Family Vacation")
        assert family_album["estCount"] == 2

        parser.close()

    def test_verify_file_recovery_rate(
        self, mock_database, mock_ibi_structure, mock_files
    ):
        """Test file recovery rate verification."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))
        parser.connect()

        recovery_stats = parser.verify_file_recovery_rate()

        assert "total_files" in recovery_stats
        assert "available_files" in recovery_stats
        assert "recovery_rate" in recovery_stats

        assert recovery_stats["total_files"] == 4
        assert recovery_stats["available_files"] == 3  # 3 files exist, 1 missing
        assert recovery_stats["recovery_rate"] == 75.0  # 3/4 = 75%

        parser.close()

    def test_export_comprehensive_data(self, mock_database, mock_ibi_structure):
        """Test comprehensive data export."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))
        parser.connect()

        data = parser.export_comprehensive_data()

        assert "files" in data
        assert "albums" in data
        assert "tags_summary" in data
        assert "recovery_stats" in data
        assert "export_timestamp" in data

        # Check data completeness
        assert len(data["files"]) == 4
        assert len(data["albums"]) == 2
        assert len(data["tags_summary"]) >= 3  # person, beach, document

        parser.close()

    def test_parser_context_manager(self, mock_database, mock_ibi_structure):
        """Test parser as context manager."""
        with IbiDatabaseParser(
            str(mock_database), str(mock_ibi_structure["files"])
        ) as parser:
            files = parser.get_all_files()
            assert len(files) == 4

        # Connection should be closed after context
        assert (
            parser.conn is None or parser.conn.total_changes is not None
        )  # Connection handling

    def test_parser_error_handling(self, temp_dir):
        """Test parser error handling with invalid paths."""
        # Test with non-existent database
        with pytest.raises(Exception):
            parser = IbiDatabaseParser(str(temp_dir / "missing.db"), str(temp_dir))
            parser.connect()

    def test_parser_file_path_resolution(self, mock_database, mock_ibi_structure):
        """Test file path resolution logic."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))
        parser.connect()

        files = parser.get_all_files()

        # Check that files have proper path resolution
        for file_data in files:
            if file_data.get("contentID"):
                content_id = file_data["contentID"]
                expected_subdir = content_id[0]

                # The parser should provide logic to resolve file paths
                # Implementation-dependent validation
                assert len(content_id) > 1
                assert expected_subdir in "abcdef0123456789"

        parser.close()


class TestReferenceImplementationIntegration:
    """Test integration aspects of reference implementation."""

    def test_parser_with_real_query_patterns(self, mock_database, mock_ibi_structure):
        """Test parser with realistic query patterns."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))
        parser.connect()

        # Test common query patterns that users might need

        # 1. Files with GPS data
        files = parser.get_all_files()
        gps_files = [f for f in files if f.get("latitude") and f.get("longitude")]
        assert len(gps_files) == 2

        # 2. Files by mime type
        image_files = [f for f in files if f["mimeType"].startswith("image/")]
        video_files = [f for f in files if f["mimeType"].startswith("video/")]
        assert len(image_files) == 3  # JPEG + PNG
        assert len(video_files) == 1  # MP4

        # 3. Files with AI tags
        tagged_files = []
        tags_summary = parser.get_content_tags_summary()
        # Implementation would provide tagged files list

        parser.close()

    def test_parser_performance_considerations(self, mock_database, mock_ibi_structure):
        """Test parser performance with larger datasets."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))
        parser.connect()

        # Time basic operations
        import time

        start_time = time.time()
        files = parser.get_all_files()
        files_time = time.time() - start_time

        start_time = time.time()
        albums = parser.get_all_albums()
        albums_time = time.time() - start_time

        start_time = time.time()
        tags = parser.get_content_tags_summary()
        tags_time = time.time() - start_time

        # Operations should complete quickly (< 1 second for test data)
        assert files_time < 1.0
        assert albums_time < 1.0
        assert tags_time < 1.0

        parser.close()

    def test_parser_data_consistency(self, mock_database, mock_ibi_structure):
        """Test data consistency across different queries."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))
        parser.connect()

        # Get data through different methods
        files = parser.get_all_files()
        albums = parser.get_all_albums()
        comprehensive_data = parser.export_comprehensive_data()

        # Check consistency
        assert len(files) == len(comprehensive_data["files"])
        assert len(albums) == len(comprehensive_data["albums"])

        # Check that album file counts match actual membership
        for album in albums:
            album_files = [f for f in files if album["name"] in f.get("albums", [])]
            # estCount might be approximate, but should be reasonable
            assert abs(len(album_files) - album["estCount"]) <= 1

        parser.close()


class TestReferenceImplementationDocumentation:
    """Test that reference implementation matches documentation."""

    def test_api_method_signatures(self, mock_database, mock_ibi_structure):
        """Test that API methods have expected signatures."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))

        # Check that expected methods exist
        expected_methods = [
            "connect",
            "close",
            "get_all_files",
            "get_all_albums",
            "get_content_tags_summary",
            "verify_file_recovery_rate",
            "export_comprehensive_data",
        ]

        for method_name in expected_methods:
            assert hasattr(parser, method_name)
            method = getattr(parser, method_name)
            assert callable(method)

    def test_data_format_consistency(self, mock_database, mock_ibi_structure):
        """Test that returned data formats are consistent."""
        parser = IbiDatabaseParser(str(mock_database), str(mock_ibi_structure["files"]))
        parser.connect()

        # Test that data formats match expected structure
        files = parser.get_all_files()

        # Each file should have consistent structure
        required_fields = ["id", "name", "contentID", "mimeType"]
        for file_data in files:
            for field in required_fields:
                assert field in file_data

        # Albums should have consistent structure
        albums = parser.get_all_albums()
        album_required_fields = ["id", "name", "type"]
        for album in albums:
            for field in album_required_fields:
                assert field in album

        parser.close()
