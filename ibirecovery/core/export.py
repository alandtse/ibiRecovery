# SPDX-License-Identifier: GPL-3.0-or-later
"""
Metadata export system for ibiRecovery.

Handles exporting file metadata to various formats for photo management software.

Copyright (C) 2024 ibiRecovery Contributors
Licensed under GPL-3.0-or-later
"""

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


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


class MetadataExporter:
    """Spec-driven metadata export engine."""

    def __init__(self, formats_config_path: Path):
        """Initialize with export formats configuration."""
        with open(formats_config_path) as f:
            self.config = json.load(f)
        self.transforms = self._setup_transforms()
        self.filters = self._setup_filters()

    def _setup_transforms(self):
        """Setup transformation functions."""
        return {
            "join_tags": lambda tags, separator="; ": separator.join(tags)
            if isinstance(tags, list)
            else tags,
            "first_album_name": lambda albums: albums[0]
            if isinstance(albums, list) and albums
            else "",
            "gps_coordinates": self._transform_gps_coordinates,
            "hierarchical_tags": self._transform_hierarchical_tags,
            "iso_date": self._transform_iso_date,
            "iptc_date": self._transform_iptc_date,
            "exif_datetime": self._transform_exif_datetime,
            "google_timestamp": self._transform_google_timestamp,
            "iso_datetime": self._transform_iso_datetime,
            "extract_year": self._transform_extract_year,
            "tag_array": lambda tags: tags if isinstance(tags, list) else [],
            "album_array": lambda albums: albums if isinstance(albums, list) else [],
            "gps_object": self._transform_gps_object,
        }

    def _setup_filters(self):
        """Setup filter functions."""
        return {
            "auto_only": lambda tags: [tag for tag in tags if tag.get("auto", False)]
            if isinstance(tags, list)
            else [],
            "manual_only": lambda tags: [
                tag for tag in tags if not tag.get("auto", False)
            ]
            if isinstance(tags, list)
            else [],
            "all": lambda tags: tags if isinstance(tags, list) else [],
        }

    def _transform_gps_coordinates(self, values):
        """Transform GPS coordinates to lat,lon format."""
        if not isinstance(values, (list, tuple)):
            return ""
        lat = next((v for v in values[:2] if v), None)
        lon = next((v for v in values[2:4] if v), None) if len(values) > 2 else None
        return f"{lat},{lon}" if lat and lon else ""

    def _transform_hierarchical_tags(self, tags, separator="|"):
        """Transform tags to hierarchical format."""
        if not isinstance(tags, list):
            return ""
        return separator.join(tags)

    def _transform_iso_date(self, timestamp):
        """Transform timestamp to ISO date format."""
        if not timestamp:
            return ""
        try:
            if timestamp > 1e10:  # Milliseconds
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        except (ValueError, OverflowError):
            return ""

    def _transform_iptc_date(self, timestamp):
        """Transform timestamp to IPTC date format."""
        if not timestamp:
            return ""
        try:
            if timestamp > 1e10:  # Milliseconds
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp).strftime("%Y%m%d")
        except (ValueError, OverflowError):
            return ""

    def _transform_exif_datetime(self, timestamp):
        """Transform timestamp to EXIF datetime format."""
        if not timestamp:
            return ""
        try:
            if timestamp > 1e10:  # Milliseconds
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp).strftime("%Y:%m:%d %H:%M:%S")
        except (ValueError, OverflowError):
            return ""

    def _transform_google_timestamp(self, timestamp):
        """Transform timestamp to Google Takeout format."""
        if not timestamp:
            return ""
        try:
            if timestamp > 1e10:  # Milliseconds
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, OverflowError):
            return ""

    def _transform_iso_datetime(self, timestamp):
        """Transform timestamp to ISO datetime format."""
        if not timestamp:
            return ""
        try:
            if timestamp > 1e10:  # Milliseconds
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, OverflowError):
            return ""

    def _transform_extract_year(self, timestamp):
        """Extract year from timestamp."""
        if not timestamp:
            return ""
        try:
            if timestamp > 1e10:  # Milliseconds
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp).strftime("%Y")
        except (ValueError, OverflowError):
            return ""

    def _transform_gps_object(self, values):
        """Transform GPS coordinates to object format."""
        if not isinstance(values, (list, tuple)) or len(values) < 2:
            return {}
        lat = values[0] if values[0] else None
        lon = values[1] if len(values) > 1 and values[1] else None
        return {"latitude": lat, "longitude": lon} if lat and lon else {}

    def export_csv_format(self, data, format_spec, output_file):
        """Export data to CSV format."""
        with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
            # Handle different CSV separators
            delimiter = format_spec.get("separator", ",")

            # Special handling for tab-separated files
            if delimiter == "\\t":
                delimiter = "\t"

            writer = csv.DictWriter(
                csvfile,
                fieldnames=list(format_spec["fields"].keys()),
                delimiter=delimiter,
                quoting=csv.QUOTE_MINIMAL,
            )

            writer.writeheader()

            for item in data:
                row = {}
                for field_name, field_config in format_spec["fields"].items():
                    source_field = field_config["source"]
                    value = item.get(source_field, "")

                    # Apply transformations
                    if "transform" in field_config:
                        transform_name = field_config["transform"]
                        if transform_name in self.transforms:
                            if (
                                transform_name == "gps_coordinates"
                                and source_field in ["gpsLatitude", "gpsLongitude"]
                            ):
                                # Special handling for GPS coordinates
                                lat = item.get("gpsLatitude")
                                lon = item.get("gpsLongitude")
                                value = self.transforms[transform_name]([lat, lon])
                            else:
                                value = self.transforms[transform_name](value)

                    row[field_name] = value or ""

                writer.writerow(row)

    def export_json_format(self, data, format_spec, output_file):
        """Export data to JSON format."""
        export_data = []

        for item in data:
            record = {}
            for field_name, field_config in format_spec["fields"].items():
                source_field = field_config["source"]
                value = item.get(source_field, "")

                # Apply transformations
                if "transform" in field_config:
                    transform_name = field_config["transform"]
                    if transform_name in self.transforms:
                        if transform_name == "gps_coordinates" and source_field in [
                            "gpsLatitude",
                            "gpsLongitude",
                        ]:
                            # Special handling for GPS coordinates
                            lat = item.get("gpsLatitude")
                            lon = item.get("gpsLongitude")
                            value = self.transforms[transform_name]([lat, lon])
                        else:
                            value = self.transforms[transform_name](value)

                record[field_name] = value

            export_data.append(record)

        with open(output_file, "w", encoding="utf-8") as jsonfile:
            json.dump(export_data, jsonfile, indent=2, ensure_ascii=False)

    def export_all_formats(self, data, output_dir, selected_formats=None):
        """Export data to all specified formats."""
        output_dir = Path(output_dir)
        from ..extract_files import safe_mkdir

        safe_mkdir(output_dir, parents=True)

        formats_to_export = selected_formats or self.config["formats"].keys()
        exported_files = []

        for format_name in formats_to_export:
            if format_name not in self.config["formats"]:
                print(f"⚠️  Unknown format: {format_name}")
                continue

            format_spec = self.config["formats"][format_name]
            output_file = output_dir / f"{format_name}.{format_spec['file_extension']}"

            try:
                if format_spec["type"] == "csv":
                    self.export_csv_format(data, format_spec, output_file)
                elif format_spec["type"] == "json":
                    self.export_json_format(data, format_spec, output_file)
                elif format_spec["type"] == "xml":
                    print(f"⚠️  XML export not yet implemented for {format_name}")
                    continue
                else:
                    print(f"⚠️  Unknown format type: {format_spec['type']}")
                    continue

                exported_files.append(
                    {
                        "format": format_name,
                        "file": str(output_file),
                        "description": format_spec.get("description", ""),
                    }
                )
                print(f"  ✅ Exported {format_name}: {output_file}")

            except Exception as e:
                print(f"  ❌ Failed to export {format_name}: {e}")

        return exported_files


def export_metadata_formats(
    files_with_albums: List[Dict[str, Any]],
    conn: sqlite3.Connection,
    output_dir: Path,
    selected_formats: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Export comprehensive metadata to various formats.
    """
    print(f"📤 Exporting metadata to: {output_dir}")

    # Get comprehensive export data
    export_data = get_comprehensive_export_data(conn)

    # Initialize exporter with format specifications
    formats_config = Path(__file__).parent.parent.parent / "export_formats.json"
    exporter = MetadataExporter(formats_config)

    # Export to all specified formats
    exported_files = exporter.export_all_formats(
        export_data, output_dir, selected_formats
    )

    print(f"✅ Exported metadata to {len(exported_files)} formats")

    # Return summary
    return {
        "total_files": len(export_data),
        "exported_formats": [f["format"] for f in exported_files],
        "export_timestamp": datetime.now().isoformat(),
        "output_directory": str(output_dir),
    }
