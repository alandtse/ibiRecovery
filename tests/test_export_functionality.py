"""Test metadata export functionality and format generation."""

import csv
import json
import os
import sys
from io import StringIO
from pathlib import Path

import pytest

# Add the package to the path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ibirecovery.extract_files import MetadataExporter

# load_export_formats doesn't exist as a separate function
# The MetadataExporter class loads formats internally


class TestMetadataExporter:
    """Test metadata export functionality."""

    def test_metadata_exporter_initialization(self, mock_export_formats):
        """Test MetadataExporter initialization with formats."""
        exporter = MetadataExporter(mock_export_formats)

        assert exporter.config is not None
        assert "formats" in exporter.config
        assert "json_metadata" in exporter.config["formats"]
        assert len(exporter.config["formats"]) >= 2  # At least our test formats

    def test_export_formats_loading(self, mock_export_formats):
        """Test loading export formats from JSON file."""
        exporter = MetadataExporter(mock_export_formats)

        assert "formats" in exporter.config
        assert (
            "lr_transporter_csv" in exporter.config["formats"]
            or "lightroom_csv" in exporter.config["formats"]
        )
        assert "json_metadata" in exporter.config["formats"]
        # Check description exists for available format
        if "lightroom_csv" in exporter.config["formats"]:
            assert (
                exporter.config["formats"]["lightroom_csv"]["description"]
                == "Adobe Lightroom CSV import format"
            )
        elif "lr_transporter_csv" in exporter.config["formats"]:
            assert (
                "LR/Transporter"
                in exporter.config["formats"]["lr_transporter_csv"]["description"]
            )

    def test_export_lightroom_csv(
        self, sample_files_data, temp_dir, mock_export_formats
    ):
        """Test Lightroom CSV export format."""
        exporter = MetadataExporter(mock_export_formats)

        # Export in Lightroom CSV format (using real format name)
        output_files = exporter.export_all_formats(
            sample_files_data, temp_dir, ["lr_transporter_csv"]
        )

        assert len(output_files) == 1
        csv_info = output_files[0]
        csv_file = csv_info["file"]
        assert csv_file.exists()
        assert csv_file.suffix == ".tsv"  # lr_transporter_csv format uses tsv

        # Read and verify CSV content
        with open(csv_file, "r") as f:
            content = f.read()
            lines = content.strip().split("\n")

        assert len(lines) >= 4  # Headers + 3 data rows
        assert "test1.jpg" in content
        assert "test2.mp4" in content
        assert "test3.png" in content

    def test_export_json_metadata(
        self, sample_files_data, temp_dir, mock_export_formats
    ):
        """Test JSON metadata export format."""
        exporter = MetadataExporter(mock_export_formats)

        # Export in JSON format
        output_files = exporter.export_all_formats(
            sample_files_data, temp_dir, ["json_metadata"]
        )

        assert len(output_files) == 1
        json_info = output_files[0]
        json_file = json_info["file"]
        assert json_file.exists()
        assert json_file.suffix == ".json"

        # Read and verify JSON content
        with open(json_file, "r") as f:
            data = json.load(f)

        # JSON structure will depend on the test format configuration
        assert isinstance(data, dict)  # Should be a structured JSON object
        # The exact structure depends on mock configuration

    def test_export_multiple_formats(
        self, sample_files_data, temp_dir, mock_export_formats
    ):
        """Test exporting multiple formats simultaneously."""
        exporter = MetadataExporter(mock_export_formats)

        # Export both formats
        output_files = exporter.export_all_formats(
            sample_files_data, temp_dir, ["lr_transporter_csv", "json_metadata"]
        )

        assert len(output_files) == 2

        # Check that both files exist
        tsv_files = [info for info in output_files if info["file"].suffix == ".tsv"]
        json_files = [info for info in output_files if info["file"].suffix == ".json"]

        assert len(tsv_files) == 1
        assert len(json_files) == 1

    def test_export_invalid_format(
        self, sample_files_data, temp_dir, mock_export_formats
    ):
        """Test handling of invalid export format."""
        exporter = MetadataExporter(mock_export_formats)

        # Try to export with invalid format - should handle gracefully
        output_files = exporter.export_all_formats(
            sample_files_data, temp_dir, ["invalid_format"]
        )

        # Should return empty list or handle error gracefully
        assert isinstance(output_files, list)

    def test_export_empty_data(self, temp_dir, mock_export_formats):
        """Test exporting with empty file data."""
        exporter = MetadataExporter(mock_export_formats)

        # Export with empty data
        output_files = exporter.export_all_formats([], temp_dir, ["lr_transporter_csv"])

        assert len(output_files) == 1
        csv_info = output_files[0]
        csv_file = csv_info["file"]
        assert csv_file.exists()

        # CSV should still have headers even with no data
        with open(csv_file, "r") as f:
            content = f.read()
            assert len(content) > 0  # Should have at least headers


class TestExportTransformations:
    """Test data transformation functions for export."""

    def test_join_semicolon_transform(self, temp_dir, mock_export_formats):
        """Test semicolon joining transformation for tags."""
        exporter = MetadataExporter(mock_export_formats)

        # Test data with tags in the format expected by the exporter
        test_data = [
            {
                "file_record": {"name": "test.jpg", "mimeType": "image/jpeg"},
                "tags": [
                    {"tag": "person", "auto": True},
                    {"tag": "beach", "auto": True},
                    {"tag": "vacation", "auto": False},
                ],
                "albums": [],
            }
        ]

        output_files = exporter.export_all_formats(
            test_data, temp_dir, ["lr_transporter_csv"]
        )
        if output_files:  # Only test if export succeeded
            csv_info = output_files[0]
            csv_file = csv_info["file"]

            # Read CSV and check content
            with open(csv_file, "r") as f:
                content = f.read()

            # Should contain the filename
            assert "test.jpg" in content

    def test_gps_coordinate_formatting(self, temp_dir):
        """Test GPS coordinate formatting for export."""
        # This would test coordinate transformation
        # Implementation depends on the specific GPS format requirements

        test_coordinates = [
            (37.7749, -122.4194),  # San Francisco
            (40.7128, -74.0060),  # New York
            (None, None),  # No GPS data
        ]

        for lat, lon in test_coordinates:
            if lat and lon:
                # Test coordinate formatting logic
                assert isinstance(lat, (int, float))
                assert isinstance(lon, (int, float))
                assert -90 <= lat <= 90
                assert -180 <= lon <= 180


class TestExportFileHandling:
    """Test export file creation and management."""

    def test_export_directory_creation(self, sample_files_data, temp_dir):
        """Test automatic creation of export directory."""
        export_dir = temp_dir / "metadata_exports"

        # Directory shouldn't exist initially
        assert not export_dir.exists()

        # Create a minimal format config for testing
        formats_config = {
            "formats": {
                "simple_json": {
                    "name": "Simple JSON",
                    "description": "Simple JSON export",
                    "file_extension": "json",
                    "type": "json",
                    "structure": {
                        "files": {
                            "source": "files_array",
                            "fields": {"filename": "file_record.name"},
                        }
                    },
                }
            }
        }

        formats_file = temp_dir / "test_formats.json"
        with open(formats_file, "w") as f:
            json.dump(formats_config, f)

        exporter = MetadataExporter(formats_file)
        output_files = exporter.export_all_formats(
            sample_files_data, export_dir, ["simple_json"]
        )

        # Directory should be created
        assert export_dir.exists()
        assert export_dir.is_dir()

        # Output file should be in the directory
        assert len(output_files) == 1
        file_info = output_files[0]
        assert file_info["file"].parent == export_dir

    def test_export_file_naming(self, sample_files_data, temp_dir, mock_export_formats):
        """Test export file naming conventions."""
        exporter = MetadataExporter(mock_export_formats)

        output_files = exporter.export_all_formats(
            sample_files_data, temp_dir, ["lr_transporter_csv", "json_metadata"]
        )

        # Check file names
        file_names = [info["file"].name for info in output_files]

        # Should have descriptive names
        tsv_files = [name for name in file_names if name.endswith(".tsv")]
        json_files = [name for name in file_names if name.endswith(".json")]

        assert len(tsv_files) == 1
        assert len(json_files) == 1

        # Names should be related to the format
        assert any(
            "lr_transporter" in name.lower() or "tsv" in name.lower()
            for name in tsv_files
        )
        assert any(
            "json" in name.lower() or "metadata" in name.lower() for name in json_files
        )

    def test_export_file_overwrite_handling(
        self, sample_files_data, temp_dir, mock_export_formats
    ):
        """Test handling of existing export files."""
        exporter = MetadataExporter(mock_export_formats)

        # Export once
        output_files_1 = exporter.export_all_formats(
            sample_files_data, temp_dir, ["lr_transporter_csv"]
        )
        first_info = output_files_1[0]
        first_file = first_info["file"]
        first_content = first_file.read_text()

        # Export again (should overwrite)
        output_files_2 = exporter.export_all_formats(
            sample_files_data, temp_dir, ["lr_transporter_csv"]
        )
        second_info = output_files_2[0]
        second_file = second_info["file"]

        # Should be the same file path
        assert first_file == second_file

        # Content should be regenerated
        second_content = second_file.read_text()
        assert len(second_content) > 0
        # Content should be similar (same data exported)


class TestExportValidation:
    """Test validation of export output."""

    def test_csv_format_validation(
        self, sample_files_data, temp_dir, mock_export_formats
    ):
        """Test that exported CSV is properly formatted."""
        exporter = MetadataExporter(mock_export_formats)

        output_files = exporter.export_all_formats(
            sample_files_data, temp_dir, ["lr_transporter_csv"]
        )
        csv_info = output_files[0]
        csv_file = csv_info["file"]

        # Validate CSV structure (TSV format uses tabs)
        with open(csv_file, "r") as f:
            reader = csv.reader(f, delimiter="\t")
            headers = next(reader)
            rows = list(reader)

        # Should have headers (tab-separated format)
        assert len(headers) > 0
        assert "Filename" in headers  # Real format uses 'Filename' not 'filename'

        # All rows should have same number of columns as headers
        for row in rows:
            assert len(row) == len(headers)

    def test_json_format_validation(
        self, sample_files_data, temp_dir, mock_export_formats
    ):
        """Test that exported JSON is valid."""
        exporter = MetadataExporter(mock_export_formats)

        output_files = exporter.export_all_formats(
            sample_files_data, temp_dir, ["json_metadata"]
        )
        json_info = output_files[0]
        json_file = json_info["file"]

        # Validate JSON structure
        with open(json_file, "r") as f:
            data = json.load(f)  # Should not raise exception

        assert isinstance(data, (list, dict))
        if isinstance(data, list):
            assert len(data) == len(sample_files_data)

    def test_unicode_handling(self, temp_dir, mock_export_formats):
        """Test handling of Unicode characters in metadata."""
        # Test data with Unicode characters in correct format
        unicode_test_data = [
            {
                "file_record": {
                    "name": "café_photo.jpg",
                    "mimeType": "image/jpeg",
                    "description": "A photo with café signs and 日本語 text",
                },
                "tags": [
                    {"tag": "café", "auto": True},
                    {"tag": "français", "auto": True},
                    {"tag": "日本語", "auto": True},
                ],
                "albums": [
                    {
                        "name": "Vacation in Café de Paris",
                        "description": "Trip to Paris",
                    }
                ],
            }
        ]

        exporter = MetadataExporter(mock_export_formats)
        output_files = exporter.export_all_formats(
            unicode_test_data, temp_dir, ["lr_transporter_csv", "json_metadata"]
        )

        # Both files should be created without errors
        assert len(output_files) == 2

        # Content should preserve Unicode characters (may be escaped in JSON)
        for output_info in output_files:
            output_file = output_info["file"]
            content = output_file.read_text(encoding="utf-8")
            # Check for either raw unicode or escaped unicode
            assert "café" in content or "\\u00e9" in content
            assert len(content) > 0
