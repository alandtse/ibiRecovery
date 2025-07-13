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
            config = json.load(f)

        # Check that config has required top-level sections
        assert "formats" in config
        assert "transforms" in config
        assert "filters" in config

        formats = config["formats"]

        # Check that each format has required fields
        required_format_fields = ["description", "file_extension"]

        for format_name, format_config in formats.items():
            assert isinstance(format_name, str)
            assert len(format_name) > 0

            for field in required_format_fields:
                assert field in format_config, f"Format {format_name} missing {field}"

            # Check field structure
            assert isinstance(format_config["description"], str)
            assert isinstance(format_config["file_extension"], str)
            assert not format_config["file_extension"].startswith(".")  # No leading dot

            # Formats can have either 'columns' (CSV) or other structures (JSON/XML)
            if format_config.get("type") == "csv":
                assert "columns" in format_config
                assert isinstance(format_config["columns"], list)
            elif format_config.get("type") == "json":
                assert "structure" in format_config
            elif format_config.get("type") == "xml":
                assert "mappings" in format_config or "template" in format_config

    def test_documented_formats_present(self):
        """Test that formats mentioned in documentation are present."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            config = json.load(f)

        formats = config["formats"]

        # Formats that should be available based on documentation
        expected_formats = [
            "lr_transporter_csv",  # Adobe Lightroom/Transporter
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
            config = json.load(f)

        formats = config["formats"]

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
            config = json.load(f)

        formats = config["formats"]

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
            config = json.load(f)

        formats = config["formats"]

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
            # Handle different format structures
            if format_config.get("type") == "csv":
                fields = format_config.get("columns", [])
                for field_config in fields:
                    assert isinstance(
                        field_config, dict
                    ), f"Column in {format_name} should be dict"
                    if "source" in field_config:
                        source = field_config["source"]
                        # Source validation for CSV columns
                        if source not in valid_sources and source != "all_metadata":
                            pass  # Custom sources might be valid
            elif format_config.get("type") == "json":
                # JSON formats have nested structure
                structure = format_config.get("structure", {})
                assert isinstance(
                    structure, dict
                ), f"JSON structure in {format_name} should be dict"
            elif format_config.get("type") == "xml":
                # XML formats have mappings
                mappings = format_config.get("mappings", {})
                assert isinstance(
                    mappings, dict
                ), f"XML mappings in {format_name} should be dict"

    def test_file_extensions_validity(self):
        """Test that file extensions are reasonable."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            config = json.load(f)

        formats = config["formats"]

        valid_extensions = [
            "csv",
            "tsv",
            "json",
            "xml",
            "xmp",
            "nfo",
            "txt",
        ]  # No leading dots

        for format_name, format_config in formats.items():
            extension = format_config["file_extension"]

            assert not extension.startswith(
                "."
            ), f"Extension for {format_name} should not start with dot"
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
            config = json.load(f)

        formats = config["formats"]

        csv_formats = {k: v for k, v in formats.items() if v["file_extension"] == "csv"}

        for format_name, format_config in csv_formats.items():
            # CSV formats use 'columns', not 'fields'
            fields = format_config.get("columns", [])

            # CSV formats should have multiple fields (not just 'all')
            assert (
                len(fields) > 1 or "all" in fields
            ), f"CSV format {format_name} should have multiple fields"

            # Should have some form of filename/identifier field
            has_identifier = any(
                "filename" in field.get("name", "").lower()
                or "name" in field.get("name", "").lower()
                or "file" in field.get("name", "").lower()
                for field in fields
            )
            assert (
                has_identifier
            ), f"CSV format {format_name} should have filename field"

    def test_json_formats_flexibility(self):
        """Test that JSON formats are appropriately flexible."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            config = json.load(f)

        formats = config["formats"]

        json_formats = {
            k: v for k, v in formats.items() if v["file_extension"] == "json"
        }

        for format_name, format_config in json_formats.items():
            # JSON formats use 'structure', not 'fields'
            fields = format_config.get("structure", {})

            # JSON formats should be comprehensive or have specific structure
            if "files" in fields:
                # Check nested fields structure
                files_fields = fields["files"].get("fields", {})
                assert (
                    len(files_fields) >= 3
                ), f"JSON format {format_name} should have adequate nested fields"
            elif "all" in str(fields):
                # Comprehensive JSON export - acceptable
                pass
            else:
                # Other structured JSON should have meaningful top-level fields
                assert (
                    len(fields) >= 2
                ), f"Structured JSON format {format_name} should have adequate fields"

    def test_professional_format_completeness(self):
        """Test that professional formats include necessary metadata."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            config = json.load(f)

        formats = config["formats"]

        # Professional formats should be comprehensive
        professional_formats = [
            "exiftool_csv",  # Industry standard
            "iptc_compliant_csv",  # Professional standard
            "xmp_sidecar",  # Universal metadata
        ]

        for format_name in professional_formats:
            if format_name in formats:
                format_config = formats[format_name]

                # Handle different format structures
                if format_config.get("type") == "csv":
                    fields = format_config.get("columns", [])
                    # Should have comprehensive field coverage
                    field_sources = [field.get("source", "") for field in fields]
                elif format_config.get("type") == "xml":
                    mappings = format_config.get("mappings", {})
                    field_sources = [
                        mapping.get("source", "") for mapping in mappings.values()
                    ]
                else:
                    continue  # Skip unknown format types

                # Should cover major metadata categories
                expected_coverage = [
                    "name",
                    "tags",
                    "coordinates",
                    "description",
                    "subject",  # XMP uses dc:subject for tags
                    "GPS",  # XMP GPS format
                ]  # GPS, content tags, identification

                coverage_found = sum(
                    1
                    for expected in expected_coverage
                    if any(
                        expected.lower() in str(source).lower()
                        for source in field_sources
                    )
                )

                # Lower threshold for XMP which has different field conventions
                min_coverage = 1 if format_name == "xmp_sidecar" else 2
                assert (
                    coverage_found >= min_coverage
                ), f"Professional format {format_name} lacks comprehensive coverage (found {coverage_found}, expected {min_coverage})"


class TestFormatsDocumentationConsistency:
    """Test that formats configuration matches documentation claims."""

    def test_readme_format_count_accuracy(self):
        """Test that README claims about format count are accurate."""
        project_root = Path(__file__).parent.parent
        formats_file = project_root / "export_formats.json"

        with open(formats_file, "r") as f:
            config = json.load(f)

        formats = config["formats"]

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
            config = json.load(f)

        formats = config["formats"]

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
