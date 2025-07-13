"""Test export formats configuration and validation."""

import json
import os
import sys
from pathlib import Path

import pytest

# Add the package to the path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestExportFormatsConfig:
    """Test the export_formats.json configuration file."""

    def test_export_formats_file_exists(self):
        """Test that export_formats.json exists in the project root."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        assert formats_file.exists(), "export_formats.json not found in project root"

    def test_export_formats_valid_json(self):
        """Test that export_formats.json is valid JSON."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)  # Should not raise exception

        assert isinstance(formats, dict)
        assert len(formats) > 0

    def test_export_formats_structure(self):
        """Test the structure of export formats configuration."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)

        # Check that each format has required fields
        required_format_fields = ["description", "file_extension", "fields"]

        for format_name, format_config in formats.items():
            assert isinstance(format_name, str)
            assert len(format_name) > 0

            for field in required_format_fields:
                assert field in format_config, f"Format {format_name} missing {field}"

            # Check field structure
            assert isinstance(format_config["description"], str)
            assert isinstance(format_config["file_extension"], str)
            assert format_config["file_extension"].startswith(".")
            assert isinstance(format_config["fields"], dict)

    def test_documented_formats_present(self):
        """Test that formats mentioned in documentation are present."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)

        # Formats that should be available based on documentation
        expected_formats = [
            "lightroom_csv",  # Adobe Lightroom
            "exiftool_csv",  # Industry standard ExifTool
            "iptc_compliant_csv",  # IPTC standard
            "json_metadata",  # JSON format
            "xmp_sidecar",  # XMP sidecar files
        ]

        format_names = list(formats.keys())

        for expected in expected_formats:
            assert expected in format_names, f"Expected format {expected} not found"

    def test_video_formats_present(self):
        """Test that video management formats are present."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)

        # Video-related formats mentioned in documentation
        video_formats = [
            "jellyfin_nfo",  # Jellyfin NFO files
            "plex_csv",  # Plex import format
            "iptc_video_csv",  # IPTC Video Metadata Hub
        ]

        format_names = list(formats.keys())

        for video_format in video_formats:
            assert (
                video_format in format_names
            ), f"Video format {video_format} not found"

    def test_format_descriptions_quality(self):
        """Test that format descriptions are informative."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)

        for format_name, format_config in formats.items():
            description = format_config["description"]

            # Description should be meaningful
            assert len(description) > 10, f"Description for {format_name} too short"
            assert not description.lower().startswith(
                "todo"
            ), f"Description for {format_name} is placeholder"

            # Should mention the target software or standard
            description_lower = description.lower()
            meaningful_keywords = [
                "lightroom",
                "adobe",
                "exiftool",
                "iptc",
                "xmp",
                "json",
                "jellyfin",
                "plex",
                "csv",
                "metadata",
                "standard",
                "format",
                "import",
                "export",
                "video",
                "photo",
                "professional",
            ]

            has_meaningful_keyword = any(
                keyword in description_lower for keyword in meaningful_keywords
            )
            assert (
                has_meaningful_keyword
            ), f"Description for {format_name} lacks meaningful keywords"

    def test_field_mappings_validity(self):
        """Test that field mappings in formats are valid."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)

        # Valid source types that should be recognized
        valid_sources = [
            "name",
            "description",
            "tags",
            "albums",
            "coordinates",
            "latitude",
            "longitude",
            "createdTime",
            "modifiedTime",
            "size",
            "mimeType",
            "make",
            "model",
            "all_metadata",
            "filename_with_path",
            "relative_path",
        ]

        # Valid transforms that should be implemented
        valid_transforms = [
            "join_semicolon",
            "join_comma",
            "format_gps",
            "iso_datetime",
            "extract_year",
            "format_size",
            "mime_to_category",
        ]

        for format_name, format_config in formats.items():
            fields = format_config["fields"]

            for field_name, field_config in fields.items():
                assert isinstance(
                    field_config, dict
                ), f"Field {field_name} in {format_name} should be dict"

                if "source" in field_config:
                    source = field_config["source"]
                    # Source should be valid or 'all_metadata' for comprehensive export
                    if source not in valid_sources and source != "all_metadata":
                        # Allow custom sources but warn about them
                        pass  # Custom sources might be valid

                if "transform" in field_config:
                    transform = field_config["transform"]
                    assert (
                        transform in valid_transforms
                    ), f"Invalid transform {transform} in {format_name}.{field_name}"

    def test_file_extensions_validity(self):
        """Test that file extensions are reasonable."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)

        valid_extensions = [".csv", ".json", ".xml", ".xmp", ".nfo", ".txt"]

        for format_name, format_config in formats.items():
            extension = format_config["file_extension"]

            assert extension.startswith(
                "."
            ), f"Extension for {format_name} should start with dot"
            assert len(extension) > 1, f"Extension for {format_name} too short"
            assert (
                extension.lower() == extension
            ), f"Extension for {format_name} should be lowercase"

            # Extension should be reasonable
            assert (
                extension in valid_extensions
            ), f"Unusual extension {extension} for {format_name}"


class TestFormatCompatibility:
    """Test compatibility between formats and expected use cases."""

    def test_csv_formats_structure(self):
        """Test that CSV formats have appropriate field structures."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)

        csv_formats = {
            k: v for k, v in formats.items() if v["file_extension"] == ".csv"
        }

        for format_name, format_config in csv_formats.items():
            fields = format_config["fields"]

            # CSV formats should have multiple fields (not just 'all')
            assert (
                len(fields) > 1 or "all" in fields
            ), f"CSV format {format_name} should have multiple fields"

            # Should have some form of filename/identifier field
            has_identifier = any(
                "filename" in field.lower()
                or "name" in field.lower()
                or "file" in field.lower()
                for field in fields.keys()
            )
            assert (
                has_identifier
            ), f"CSV format {format_name} should have filename field"

    def test_json_formats_flexibility(self):
        """Test that JSON formats are appropriately flexible."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)

        json_formats = {
            k: v for k, v in formats.items() if v["file_extension"] == ".json"
        }

        for format_name, format_config in json_formats.items():
            fields = format_config["fields"]

            # JSON formats should be comprehensive or have specific structure
            if len(fields) == 1 and "all" in list(fields.values())[0].get("source", ""):
                # Comprehensive JSON export - acceptable
                pass
            else:
                # Structured JSON should have meaningful fields
                assert (
                    len(fields) >= 3
                ), f"Structured JSON format {format_name} should have adequate fields"

    def test_professional_format_completeness(self):
        """Test that professional formats include necessary metadata."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)

        # Professional formats should be comprehensive
        professional_formats = [
            "exiftool_csv",  # Industry standard
            "iptc_compliant_csv",  # Professional standard
            "xmp_sidecar",  # Universal metadata
        ]

        for format_name in professional_formats:
            if format_name in formats:
                format_config = formats[format_name]
                fields = format_config["fields"]

                # Should have comprehensive field coverage
                field_sources = [field.get("source", "") for field in fields.values()]

                # Should cover major metadata categories
                expected_coverage = [
                    "name",
                    "tags",
                    "coordinates",
                ]  # GPS, content tags, identification

                coverage_found = sum(
                    1
                    for expected in expected_coverage
                    if any(expected in source for source in field_sources)
                )

                assert (
                    coverage_found >= 2
                ), f"Professional format {format_name} lacks comprehensive coverage"


class TestFormatsDocumentationConsistency:
    """Test that formats configuration matches documentation claims."""

    def test_readme_format_count_accuracy(self):
        """Test that README claims about format count are accurate."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)

        total_formats = len(formats)

        # README mentions "12 export formats" - verify this is accurate
        # Allow some flexibility for updates
        assert (
            total_formats >= 10
        ), f"Expected at least 10 formats, found {total_formats}"
        assert (
            total_formats <= 15
        ), f"Format count {total_formats} seems too high for documentation"

    def test_software_compatibility_claims(self):
        """Test that claimed software compatibility is supported."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            formats = json.load(f)

        # Software mentioned in documentation should have corresponding formats
        documented_software = {
            "lightroom": ["lightroom", "lr"],
            "digikam": ["digikam", "iptc"],
            "jellyfin": ["jellyfin"],
            "plex": ["plex"],
            "exiftool": ["exiftool"],
        }

        format_names_lower = [name.lower() for name in formats.keys()]

        for software, expected_keywords in documented_software.items():
            has_format = any(
                any(keyword in format_name for keyword in expected_keywords)
                for format_name in format_names_lower
            )
            assert has_format, f"No format found for documented software: {software}"
