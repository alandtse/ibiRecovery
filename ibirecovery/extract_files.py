#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
ibiRecovery Enhanced File Extraction Script

This script extracts files from recovered ibi databases with advanced features:
- Auto-detects ibi directory structure from root path
- Progress bars for file operations
- Resumable operations using rsync with fallback
- Default: Extract by albums + orphaned files (recommended)
- Option: Extract by file type (images, videos, documents)
- Always: Ensures 100% file recovery including orphaned content

Copyright (C) 2024 ibiRecovery Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import sqlite3
import os
import shutil
import sys
import subprocess
import signal
import json
import csv
from datetime import datetime
from pathlib import Path
import argparse
from collections import defaultdict
from typing import Optional, Tuple, List, Dict, Any

# Optional dependencies with graceful fallback
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    # Simple progress fallback
    class tqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.iterable = iterable
            self.total = total or (len(iterable) if iterable else 0)
            self.desc = desc or ""
            self.n = 0
            
        def __iter__(self):
            if self.iterable:
                for item in self.iterable:
                    yield item
                    self.update(1)
            return self
            
        def __enter__(self):
            return self
            
        def __exit__(self, *args):
            pass
            
        def update(self, n=1):
            self.n += n
            if self.total > 0:
                percent = (self.n / self.total) * 100
                print(f"\r{self.desc}: {self.n}/{self.total} ({percent:.1f}%)", end="", flush=True)

# Optional metadata dependencies
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import exifread
    HAS_EXIFREAD = True
except ImportError:
    HAS_EXIFREAD = False


class ExtractionState:
    """Global state for tracking extraction progress and handling interrupts."""
    
    def __init__(self):
        self.interrupted = False
        self.total_files_extracted = 0
        self.total_size_extracted = 0
        self.current_operation = "Initializing"
        self.start_time = None
        
    def signal_handler(self, signum, frame):
        """Handle keyboard interrupt gracefully."""
        self.interrupted = True
        print(f"\n\n⚠️  Extraction interrupted by user (Ctrl+C)")
        print(f"📊 Progress before interruption:")
        print(f"   Files extracted: {self.total_files_extracted}")
        print(f"   Data extracted: {format_size(self.total_size_extracted)}")
        print(f"   Current operation: {self.current_operation}")
        print(f"\n💡 You can resume this extraction by running the same command again.")
        print(f"   The --resume flag (enabled by default) will skip already-copied files.")
        sys.exit(0)


# Global extraction state
extraction_state = ExtractionState()


def detect_ibi_structure(root_path: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Auto-detect ibi database and files directory structure.
    
    Returns:
        Tuple of (db_path, files_path) or (None, None) if not found
    """
    root_path = Path(root_path)
    
    # Common ibi directory structures to check
    candidates = [
        # Standard structure: root/restsdk/data/
        (root_path / "restsdk" / "data" / "db" / "index.db", 
         root_path / "restsdk" / "data" / "files"),
        
        # Alternative: direct in data folder
        (root_path / "data" / "db" / "index.db",
         root_path / "data" / "files"),
        
        # Alternative: root contains db and files directly
        (root_path / "db" / "index.db",
         root_path / "files"),
        
        # Alternative: index.db in root
        (root_path / "index.db",
         root_path / "files"),
    ]
    
    for db_path, files_path in candidates:
        if db_path.exists() and files_path.exists():
            print(f"✅ Detected ibi structure:")
            print(f"   Database: {db_path}")
            print(f"   Files: {files_path}")
            return db_path, files_path
    
    return None, None


def check_rsync_available() -> bool:
    """Check if rsync is available on the system."""
    try:
        result = subprocess.run(["rsync", "--version"], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def copy_file_rsync(source: Path, dest: Path, resume: bool = True) -> bool:
    """
    Copy file using rsync with resume capability.
    
    Args:
        source: Source file path
        dest: Destination file path  
        resume: Whether to resume partial transfers
        
    Returns:
        True if successful, False otherwise
    """
    try:
        cmd = ["rsync", "-av"]
        if resume:
            cmd.append("--partial")
        cmd.extend([str(source), str(dest)])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        return False


def copy_file_fallback(source: Path, dest: Path, resume: bool = True) -> bool:
    """
    Fallback file copy using shutil with basic resume support.
    
    Args:
        source: Source file path
        dest: Destination file path
        resume: Whether to skip if destination exists and has same size
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Simple resume: skip if destination exists and has same size
        if resume and dest.exists():
            if dest.stat().st_size == source.stat().st_size:
                return True
                
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        return True
    except (OSError, shutil.Error):
        return False


def connect_db(db_path: Path) -> sqlite3.Connection:
    """Connect to the SQLite database."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def find_source_file(files_dir: Path, content_id: str) -> Optional[Path]:
    """Find the actual file using contentID."""
    if not content_id:
        return None
    
    # Try different directory structures based on contentID
    possible_paths = [
        files_dir / content_id[0] / content_id,  # Most common: /files/j/jT9JduP8vIHpwuY32gLQ
        files_dir / content_id[:2] / content_id[2:4] / content_id,
        files_dir / content_id,
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    return None


def get_all_files_with_albums(conn: sqlite3.Connection) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Get all files with their album memberships and calculate statistics."""
    # First get all files with size information
    files_query = """
    SELECT f.id, f.name, f.contentID, f.mimeType, f.size, 
           f.imageDate, f.videoDate, f.cTime
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
        size = file_record['size'] or 0
        total_size += size
        
        mime_type = file_record['mimeType'] or ''
        if mime_type.startswith('image/'):
            size_by_type['images'] += size
        elif mime_type.startswith('video/'):
            size_by_type['videos'] += size
        elif mime_type.startswith('application/') or mime_type.startswith('text/'):
            size_by_type['documents'] += size
        else:
            size_by_type['other'] += size
    
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
        file_albums[row['fileID']].append({
            'name': row['album_name'],
            'id': row['album_id']
        })
    
    # Combine files with their albums
    files_with_albums = []
    for file_record in files:
        files_with_albums.append({
            'file': dict(file_record),
            'albums': file_albums.get(file_record['id'], [])
        })
    
    # Prepare statistics
    stats = {
        'total_files': file_count,
        'total_size': total_size,
        'size_by_type': dict(size_by_type)
    }
    
    return files_with_albums, stats


def format_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"


def verify_file_availability(files_with_albums: List[Dict[str, Any]], files_dir: Path, 
                           sample_size: int = 100) -> Dict[str, Any]:
    """Verify file availability by checking a sample of files."""
    import random
    
    total_files = len(files_with_albums)
    if total_files == 0:
        return {
            'total_files': 0,
            'sample_size': 0,
            'available_count': 0,
            'missing_count': 0,
            'availability_rate': 0.0,
            'available_size': 0,
            'total_sample_size': 0
        }
    
    # Take a random sample
    sample_size = min(sample_size, total_files)
    sample_files = random.sample(files_with_albums, sample_size)
    
    available_count = 0
    missing_count = 0
    available_size = 0
    total_sample_size = 0
    
    print(f"Checking availability of {sample_size} sample files...")
    
    for item in sample_files:
        file_record = item['file']
        content_id = file_record.get('contentID')
        file_size = file_record.get('size', 0) or 0
        total_sample_size += file_size
        
        if content_id:
            source_path = find_source_file(files_dir, content_id)
            if source_path and source_path.exists():
                available_count += 1
                available_size += file_size
            else:
                missing_count += 1
        else:
            missing_count += 1
    
    availability_rate = (available_count / sample_size) * 100 if sample_size > 0 else 0
    
    return {
        'total_files': total_files,
        'sample_size': sample_size,
        'available_count': available_count,
        'missing_count': missing_count,
        'availability_rate': availability_rate,
        'available_size': available_size,
        'total_sample_size': total_sample_size
    }


def get_comprehensive_export_data(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Get all files with their metadata, tags, and albums for export."""
    
    # Main query - portable metadata only
    query = """
    SELECT f.id, f.name, f.contentID, f.mimeType, f.size,
           f.imageDate, f.videoDate, f.cTime, f.birthTime,
           f.imageLatitude, f.imageLongitude, f.imageAltitude,
           f.imageCity, f.imageProvince, f.imageCountry,
           f.videoLatitude, f.videoLongitude, f.videoAltitude,
           f.videoCity, f.videoProvince, f.videoCountry,
           f.imageCameraMake, f.imageCameraModel,
           f.description
    FROM Files f
    WHERE f.contentID IS NOT NULL AND f.contentID != ''
    ORDER BY COALESCE(f.videoDate, f.imageDate, f.cTime)
    """
    
    files = list(conn.execute(query).fetchall())
    
    # Get tags for all files
    tag_query = """
    SELECT fileID, tag, auto
    FROM FilesTags
    ORDER BY fileID, tag
    """
    tags_by_file = defaultdict(list)
    for row in conn.execute(tag_query):
        tags_by_file[row['fileID']].append({
            'tag': row['tag'],
            'auto': bool(row['auto'])
        })
    
    # Get albums for all files
    album_query = """
    SELECT fgf.fileID, fg.name as album_name, fg.description as album_description
    FROM FileGroupFiles fgf
    JOIN FileGroups fg ON fgf.fileGroupID = fg.id
    ORDER BY fgf.fileID, fg.name
    """
    albums_by_file = defaultdict(list)
    for row in conn.execute(album_query):
        albums_by_file[row['fileID']].append({
            'name': row['album_name'],
            'description': row['album_description']
        })
    
    # Combine data
    complete_data = []
    for file_record in files:
        file_id = file_record['id']
        complete_data.append({
            'file_record': dict(file_record),
            'tags': tags_by_file.get(file_id, []),
            'albums': albums_by_file.get(file_id, [])
        })
    
    return complete_data


def export_lightroom_csv(data: List[Dict[str, Any]], output_file: Path) -> None:
    """Export metadata in Lightroom-compatible CSV format."""
    import csv
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Filename', 'Keywords', 'Caption', 'Album', 'GPS'])
        
        for item in data:
            file_record = item['file_record']
            tags = item['tags']
            albums = item['albums']
            
            # Build keywords from tags
            keywords = []
            for tag in tags:
                if tag['auto']:  # AI-generated tags
                    keywords.append(tag['tag'])
            keywords_str = "; ".join(keywords)
            
            # GPS coordinates
            lat = file_record.get('imageLatitude') or file_record.get('videoLatitude')
            lon = file_record.get('imageLongitude') or file_record.get('videoLongitude')
            gps = f"{lat},{lon}" if lat and lon else ""
            
            # Primary album
            album = albums[0]['name'] if albums else ""
            
            writer.writerow([
                file_record['name'],
                keywords_str,
                file_record.get('description', ''),
                album,
                gps
            ])


def export_digikam_csv(data: List[Dict[str, Any]], output_file: Path) -> None:
    """Export metadata in digiKam hierarchical format."""
    import csv
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Name', 'Tags', 'Album', 'Date', 'Latitude', 'Longitude'])
        
        for item in data:
            file_record = item['file_record']
            tags = item['tags']
            albums = item['albums']
            
            # Build hierarchical tags
            tag_list = []
            for tag in tags:
                if tag['auto']:
                    # Simple hierarchy: People/person, Places/beach, etc.
                    tag_name = tag['tag']
                    if tag_name in ['person', 'child', 'baby', 'face']:
                        tag_list.append(f"People/{tag_name}")
                    elif tag_name in ['beach', 'mountain', 'city', 'park']:
                        tag_list.append(f"Places/{tag_name}")
                    else:
                        tag_list.append(f"Objects/{tag_name}")
            tags_str = "|".join(tag_list)
            
            # Date
            date = file_record.get('imageDate') or file_record.get('videoDate') or file_record.get('cTime')
            if date:
                try:
                    from datetime import datetime
                    date = datetime.fromisoformat(date.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                except:
                    date = str(date)[:10]  # Just take YYYY-MM-DD part
            
            writer.writerow([
                file_record['name'],
                tags_str,
                albums[0]['name'] if albums else "",
                date or "",
                file_record.get('imageLatitude') or file_record.get('videoLatitude') or "",
                file_record.get('imageLongitude') or file_record.get('videoLongitude') or ""
            ])


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
            'join_tags': lambda tags, separator='; ': separator.join([tag['tag'] for tag in tags]),
            'first_album_name': lambda albums: albums[0]['name'] if albums else '',
            'gps_coordinates': self._transform_gps_coordinates,
            'hierarchical_tags': self._transform_hierarchical_tags,
            'iso_date': self._transform_iso_date,
            'iptc_date': self._transform_iptc_date,
            'exif_datetime': self._transform_exif_datetime,
            'google_timestamp': self._transform_google_timestamp,
            'iso_datetime': self._transform_iso_datetime,
            'extract_year': self._transform_extract_year,
            'tag_array': lambda tags: [tag['tag'] for tag in tags],
            'album_array': lambda albums: [album['name'] for album in albums],
            'gps_object': self._transform_gps_object
        }
    
    def _setup_filters(self):
        """Setup filter functions."""
        return {
            'auto_only': lambda tags: [tag for tag in tags if tag.get('auto', False)],
            'manual_only': lambda tags: [tag for tag in tags if not tag.get('auto', False)],
            'all': lambda tags: tags
        }
    
    def _transform_gps_coordinates(self, values):
        """Transform GPS coordinates to lat,lon format."""
        if not isinstance(values, (list, tuple)):
            return ""
        lat = next((v for v in values[:2] if v), None)
        lon = next((v for v in values[2:4] if v), None) if len(values) > 2 else None
        return f"{lat},{lon}" if lat and lon else ""
    
    def _transform_hierarchical_tags(self, tags, separator='|'):
        """Transform tags to hierarchical format."""
        hierarchical = []
        for tag in tags:
            tag_name = tag['tag']
            if tag_name in ['person', 'child', 'baby', 'face']:
                hierarchical.append(f"People/{tag_name}")
            elif tag_name in ['beach', 'mountain', 'city', 'park']:
                hierarchical.append(f"Places/{tag_name}")
            else:
                hierarchical.append(f"Objects/{tag_name}")
        return separator.join(hierarchical)
    
    def _transform_iso_date(self, values):
        """Transform to ISO 8601 date."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return ""
        try:
            from datetime import datetime
            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format)
                timestamp = date_val / 1000 if date_val > 1e10 else date_val
                return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            else:
                return datetime.fromisoformat(str(date_val).replace('Z', '+00:00')).strftime('%Y-%m-%d')
        except:
            return str(date_val)[:10]
    
    def _transform_iptc_date(self, values):
        """Transform to IPTC date format (YYYYMMDD)."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return ""
        try:
            from datetime import datetime
            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format)
                timestamp = date_val / 1000 if date_val > 1e10 else date_val
                return datetime.fromtimestamp(timestamp).strftime('%Y%m%d')
            else:
                return datetime.fromisoformat(str(date_val).replace('Z', '+00:00')).strftime('%Y%m%d')
        except:
            return str(date_val)[:8]
    
    def _transform_exif_datetime(self, values):
        """Transform to EXIF datetime format."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return ""
        try:
            from datetime import datetime
            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format)
                timestamp = date_val / 1000 if date_val > 1e10 else date_val
                return datetime.fromtimestamp(timestamp).strftime('%Y:%m:%d %H:%M:%S')
            else:
                return datetime.fromisoformat(str(date_val).replace('Z', '+00:00')).strftime('%Y:%m:%d %H:%M:%S')
        except:
            return str(date_val)
    
    def _transform_google_timestamp(self, values):
        """Transform to Google Photos timestamp format."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return {"timestamp": "0"}
        try:
            from datetime import datetime
            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format) - convert to seconds
                timestamp = int(date_val / 1000) if date_val > 1e10 else int(date_val)
                return {"timestamp": str(timestamp)}
            else:
                # Parse ISO format and convert to Unix timestamp
                dt = datetime.fromisoformat(str(date_val).replace('Z', '+00:00'))
                return {"timestamp": str(int(dt.timestamp()))}
        except:
            return {"timestamp": "0"}
    
    def _transform_gps_object(self, values):
        """Transform to GPS object."""
        if not isinstance(values, (list, tuple)):
            return {}
        lat = next((v for v in values[:2] if v), None)
        lon = next((v for v in values[2:4] if v), None) if len(values) > 2 else None
        return {"latitude": lat, "longitude": lon} if lat and lon else {}
    
    def _transform_iso_datetime(self, values):
        """Transform to ISO 8601 datetime format (YYYY-MM-DDTHH:MM:SS)."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return ""
        try:
            from datetime import datetime
            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format)
                timestamp = date_val / 1000 if date_val > 1e10 else date_val
                return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%dT%H:%M:%S')
            else:
                return datetime.fromisoformat(str(date_val).replace('Z', '+00:00')).strftime('%Y-%m-%dT%H:%M:%S')
        except:
            return str(date_val)
    
    def _transform_extract_year(self, values):
        """Extract year from date (YYYY)."""
        date_val = next((v for v in values if v), None)
        if not date_val:
            return ""
        try:
            from datetime import datetime
            if isinstance(date_val, (int, float)):
                # Handle milliseconds since epoch (ibi format)
                timestamp = date_val / 1000 if date_val > 1e10 else date_val
                return datetime.fromtimestamp(timestamp).strftime('%Y')
            else:
                return datetime.fromisoformat(str(date_val).replace('Z', '+00:00')).strftime('%Y')
        except:
            return str(date_val)[:4]
    
    def _get_nested_value(self, data, path):
        """Get value from nested data using dot notation."""
        parts = path.split('.')
        value = data
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value
    
    def _apply_transform(self, value, transform, **kwargs):
        """Apply transformation to value."""
        if transform in self.transforms:
            return self.transforms[transform](value, **kwargs)
        return value
    
    def _apply_filter(self, value, filter_name):
        """Apply filter to value."""
        if filter_name in self.filters:
            return self.filters[filter_name](value)
        return value
    
    def export_csv_format(self, data, format_spec, output_file):
        """Export data in CSV format based on spec."""
        import csv
        
        # Use custom delimiter if specified
        delimiter = format_spec.get('delimiter', ',')
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=delimiter)
            
            # Write header
            headers = [col['name'] for col in format_spec['columns']]
            writer.writerow(headers)
            
            # Write data rows
            for item in data:
                row = []
                for col in format_spec['columns']:
                    value = self._extract_column_value(item, col)
                    row.append(value)
                writer.writerow(row)
    
    def _extract_column_value(self, item, col_spec):
        """Extract column value based on specification."""
        source = col_spec['source']
        
        # Handle multiple source fields
        if isinstance(source, list):
            values = [self._get_nested_value(item, s) for s in source]
            values = [v for v in values if v is not None]
        else:
            values = [self._get_nested_value(item, source)]
            values = [v for v in values if v is not None]
        
        if not values:
            return col_spec.get('default', '')
        
        # For single values, don't wrap in list for transforms
        if len(values) == 1 and not isinstance(source, list):
            value = values[0]
        else:
            value = values
        
        # Apply filter if specified
        if 'filter' in col_spec and isinstance(value, list):
            value = self._apply_filter(value, col_spec['filter'])
        
        # Apply transform if specified
        if 'transform' in col_spec:
            kwargs = {}
            if 'separator' in col_spec:
                kwargs['separator'] = col_spec['separator']
            # Always pass values array for GPS transforms
            if col_spec['transform'] in ['gps_coordinates', 'gps_object'] and isinstance(source, list):
                value = self._apply_transform(values, col_spec['transform'], **kwargs)
            else:
                value = self._apply_transform(value, col_spec['transform'], **kwargs)
        
        return value if value is not None else col_spec.get('default', '')
    
    def export_json_format(self, data, format_spec, output_file):
        """Export data in JSON format based on spec."""
        # Implementation for JSON export based on structure spec
        result = {}
        
        # Build result based on structure specification
        structure = format_spec['structure']
        for key, spec in structure.items():
            if key == 'files':
                result[key] = []
                for item in data:
                    file_data = {}
                    for field_name, field_spec in spec['fields'].items():
                        if isinstance(field_spec, dict) and 'source' in field_spec:
                            file_data[field_name] = self._extract_column_value(item, field_spec)
                        elif isinstance(field_spec, dict):
                            # Nested object
                            nested_obj = {}
                            for nested_key, nested_source in field_spec.items():
                                if nested_key != 'source':
                                    nested_obj[nested_key] = self._get_nested_value(item, nested_source) or ""
                            file_data[field_name] = nested_obj
                        else:
                            file_data[field_name] = self._get_nested_value(item, field_spec) or ""
                    result[key].append(file_data)
            else:
                # Handle metadata fields
                if isinstance(spec, dict):
                    result[key] = {}
                    for subkey, subspec in spec.items():
                        if subspec == 'current_datetime':
                            from datetime import datetime
                            result[key][subkey] = datetime.now().isoformat()
                        else:
                            result[key][subkey] = subspec  # Handle stats later
                else:
                    result[key] = spec
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
    
    def export_all_formats(self, data, output_dir, selected_formats=None):
        """Export data in all configured formats."""
        output_dir.mkdir(parents=True, exist_ok=True)
        exported_files = []
        
        formats_to_export = selected_formats or self.config['formats'].keys()
        
        for format_name in formats_to_export:
            if format_name not in self.config['formats']:
                print(f"⚠️  Unknown format: {format_name}")
                continue
                
            format_spec = self.config['formats'][format_name]
            filename = f"{format_name}.{format_spec['file_extension']}"
            output_file = output_dir / filename
            
            try:
                if format_spec['type'] == 'csv':
                    self.export_csv_format(data, format_spec, output_file)
                elif format_spec['type'] == 'json':
                    self.export_json_format(data, format_spec, output_file)
                elif format_spec['type'] == 'xml':
                    print(f"⚠️  XML export not yet implemented for {format_name}")
                    continue
                
                exported_files.append({
                    'format': format_spec['name'],
                    'file': output_file,
                    'description': format_spec['description']
                })
                print(f"  ✅ {format_spec['name']}: {output_file}")
                
            except Exception as e:
                print(f"  ❌ Failed to export {format_name}: {e}")
        
        return exported_files


def export_metadata_formats(files_with_albums: List[Dict[str, Any]], conn: sqlite3.Connection, 
                          output_dir: Path, selected_formats: Optional[List[str]] = None) -> None:
    """Export metadata using spec-driven format system."""
    
    print("Exporting metadata in standard formats...")
    
    # Get comprehensive data for export
    export_data = get_comprehensive_export_data(conn)
    
    # Initialize exporter with format specifications
    formats_config = Path(__file__).parent.parent / "export_formats.json"
    exporter = MetadataExporter(formats_config)
    
    # Export in specified formats
    exported_files = exporter.export_all_formats(export_data, output_dir, selected_formats)
    
    # Create summary
    summary = {
        'total_files': len(export_data),
        'files_with_tags': len([item for item in export_data if item['tags']]),
        'files_with_albums': len([item for item in export_data if item['albums']]),
        'unique_tags': len(set(tag['tag'] for item in export_data for tag in item['tags'])),
        'unique_albums': len(set(album['name'] for item in export_data for album in item['albums'])),
        'exported_formats': [f['format'] for f in exported_files],
        'export_timestamp': json.dumps(datetime.now().isoformat())
    }
    
    summary_file = output_dir / "export_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  ✅ Export Summary: {summary_file}")
    
    print(f"\nMetadata export complete: {len(export_data)} files processed")


def check_interrupt():
    """Check if extraction was interrupted and handle gracefully."""
    if extraction_state.interrupted:
        print(f"\n⚠️  Extraction stopped due to interrupt")
        return True
    return False


def extract_by_albums(files_with_albums: List[Dict[str, Any]], files_dir: Path, 
                     output_dir: Path, stats: Dict[str, Any], copy_files: bool = True, 
                     use_rsync: bool = True, resume: bool = True) -> Tuple[int, int]:
    """Extract files organized by albums, with orphaned files in a separate folder."""
    
    # Group files by their primary album (first album if multiple)
    album_files = defaultdict(list)
    orphaned_files = []
    
    for item in files_with_albums:
        if item['albums']:
            # Use the first/primary album
            primary_album = item['albums'][0]['name']
            album_files[primary_album].append(item)
        else:
            orphaned_files.append(item)
    
    # Calculate size statistics for albums
    album_sizes = {}
    orphaned_size = 0
    total_target_size = 0
    
    for album_name, files in album_files.items():
        album_size = sum((item['file']['size'] or 0) for item in files)
        album_sizes[album_name] = album_size
        total_target_size += album_size
    
    for item in orphaned_files:
        size = item['file']['size'] or 0
        orphaned_size += size
        total_target_size += size
    
    print(f"Found {len(album_files)} albums and {len(orphaned_files)} orphaned files")
    print(f"Total size to extract: {format_size(total_target_size)}")
    print()
    
    total_extracted = 0
    total_size_extracted = 0
    total_files = sum(len(files) for files in album_files.values()) + len(orphaned_files)
    
    # Determine copy function
    copy_func = copy_file_rsync if use_rsync else copy_file_fallback
    
    # Extract organized albums
    for album_name, files in album_files.items():
        # Check for interrupt before each album
        if check_interrupt():
            return total_extracted, total_size_extracted
            
        extraction_state.current_operation = f"Extracting album: {album_name}"
        
        safe_album_name = "".join(c for c in album_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        album_dir = output_dir / safe_album_name
        
        print(f"Extracting album: {album_name} ({len(files)} files)")
        
        if copy_files:
            album_dir.mkdir(parents=True, exist_ok=True)
        
        # Progress bar for this album with size information
        album_size = album_sizes[album_name]
        desc = f"  {album_name[:20]:<20} ({format_size(album_size)})"
        
        with tqdm(files, desc=desc, unit="files", leave=False) as pbar:
            extracted_count = 0
            extracted_size = 0
            for item in pbar:
                # Check for interrupt every few files
                if check_interrupt():
                    extraction_state.total_files_extracted += extracted_count
                    extraction_state.total_size_extracted += extracted_size
                    return total_extracted + extracted_count, total_size_extracted + extracted_size
                
                file_record = item['file']
                file_size = file_record['size'] or 0
                
                if copy_files:
                    source_path = find_source_file(files_dir, file_record['contentID'])
                    if source_path:
                        dest_path = album_dir / file_record['name']
                        # Handle duplicate filenames
                        counter = 1
                        original_dest = dest_path
                        while dest_path.exists() and not resume:
                            stem = original_dest.stem
                            suffix = original_dest.suffix
                            dest_path = album_dir / f"{stem}_{counter}{suffix}"
                            counter += 1
                        
                        if copy_func(source_path, dest_path, resume):
                            extracted_count += 1
                            extracted_size += file_size
                            total_size_extracted += file_size
                            
                            # Update global state
                            extraction_state.total_files_extracted = total_extracted + extracted_count
                            extraction_state.total_size_extracted = total_size_extracted
                            
                            # Update progress description with cumulative progress
                            overall_progress = (total_size_extracted / total_target_size) * 100
                            pbar.set_description(f"{desc} [{overall_progress:.1f}% total]")
                        else:
                            pbar.write(f"  Error copying {file_record['name']}")
                    else:
                        pbar.write(f"  Source file not found: {file_record['name']}")
                else:
                    extracted_count += 1
                    extracted_size += file_size
        
        if copy_files:
            print(f"  Extracted {extracted_count}/{len(files)} files ({format_size(extracted_size)})")
        total_extracted += extracted_count
        print()
    
    # Extract orphaned files
    if orphaned_files:
        # Check for interrupt before orphaned files
        if check_interrupt():
            return total_extracted, total_size_extracted
            
        extraction_state.current_operation = "Extracting orphaned files"
        
        orphaned_dir = output_dir / "Unorganized"
        print(f"Extracting orphaned files: Unorganized ({len(orphaned_files)} files, {format_size(orphaned_size)})")
        
        if copy_files:
            orphaned_dir.mkdir(parents=True, exist_ok=True)
        
        desc = f"  Unorganized ({format_size(orphaned_size)})"
        with tqdm(orphaned_files, desc=desc, unit="files", leave=False) as pbar:
            extracted_count = 0
            extracted_size = 0
            for item in pbar:
                # Check for interrupt during orphaned files
                if check_interrupt():
                    extraction_state.total_files_extracted += extracted_count
                    extraction_state.total_size_extracted += extracted_size
                    return total_extracted + extracted_count, total_size_extracted + extracted_size
                
                file_record = item['file']
                file_size = file_record['size'] or 0
                
                if copy_files:
                    source_path = find_source_file(files_dir, file_record['contentID'])
                    if source_path:
                        dest_path = orphaned_dir / file_record['name']
                        # Handle duplicate filenames
                        counter = 1
                        original_dest = dest_path
                        while dest_path.exists() and not resume:
                            stem = original_dest.stem
                            suffix = original_dest.suffix
                            dest_path = orphaned_dir / f"{stem}_{counter}{suffix}"
                            counter += 1
                        
                        if copy_func(source_path, dest_path, resume):
                            extracted_count += 1
                            extracted_size += file_size
                            total_size_extracted += file_size
                            
                            # Update global state
                            extraction_state.total_files_extracted = total_extracted + extracted_count
                            extraction_state.total_size_extracted = total_size_extracted
                            
                            # Update progress description with cumulative progress
                            overall_progress = (total_size_extracted / total_target_size) * 100
                            pbar.set_description(f"{desc} [{overall_progress:.1f}% total]")
                        else:
                            pbar.write(f"  Error copying {file_record['name']}")
                    else:
                        pbar.write(f"  Source file not found: {file_record['name']}")
                else:
                    extracted_count += 1
                    extracted_size += file_size
        
        if copy_files:
            print(f"  Extracted {extracted_count}/{len(orphaned_files)} files ({format_size(extracted_size)})")
        total_extracted += extracted_count
        print()
    
    return total_extracted, total_size_extracted


def extract_by_type(files_with_albums: List[Dict[str, Any]], files_dir: Path,
                   output_dir: Path, stats: Dict[str, Any], copy_files: bool = True,
                   use_rsync: bool = True, resume: bool = True) -> Tuple[int, int]:
    """Extract files organized by type (images, videos, documents)."""
    
    type_dirs = {
        'images': output_dir / 'Images',
        'videos': output_dir / 'Videos', 
        'documents': output_dir / 'Documents',
        'other': output_dir / 'Other'
    }
    
    if copy_files:
        for dir_path in type_dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)
    
    total_extracted = 0
    total_size_extracted = 0
    type_counts = defaultdict(int)
    type_sizes = defaultdict(int)
    
    # Determine copy function
    copy_func = copy_file_rsync if use_rsync else copy_file_fallback
    
    print(f"Total size to extract: {format_size(stats['total_size'])}")
    print()
    
    # Group files by type first for better progress tracking
    files_by_type = defaultdict(list)
    for item in files_with_albums:
        file_record = item['file']
        mime_type = file_record['mimeType'] or ''
        file_size = file_record['size'] or 0
        
        # Determine file category
        if mime_type.startswith('image/'):
            category = 'images'
        elif mime_type.startswith('video/'):
            category = 'videos'
        elif mime_type.startswith('application/') or mime_type.startswith('text/'):
            category = 'documents'
        else:
            category = 'other'
        
        files_by_type[category].append(item)
        type_sizes[category] += file_size
    
    # Extract by type with progress bars
    for category, items in files_by_type.items():
        if not items:
            continue
        
        # Check for interrupt before each category
        if check_interrupt():
            return total_extracted, total_size_extracted
            
        extraction_state.current_operation = f"Extracting {category}"
        
        category_size = type_sizes[category]
        print(f"Extracting {category}: {len(items)} files ({format_size(category_size)})")
        
        desc = f"  {category.title():<12} ({format_size(category_size)})"
        with tqdm(items, desc=desc, unit="files", leave=False) as pbar:
            extracted_size = 0
            for item in pbar:
                # Check for interrupt during type extraction
                if check_interrupt():
                    extraction_state.total_files_extracted += (total_extracted - len(files_by_type[category]) + pbar.n)
                    extraction_state.total_size_extracted += total_size_extracted
                    return total_extracted, total_size_extracted
                
                file_record = item['file']
                file_size = file_record['size'] or 0
                type_counts[category] += 1
                
                if copy_files:
                    source_path = find_source_file(files_dir, file_record['contentID'])
                    if source_path:
                        dest_path = type_dirs[category] / file_record['name']
                        
                        # Handle duplicate filenames
                        counter = 1
                        original_dest = dest_path
                        while dest_path.exists() and not resume:
                            stem = original_dest.stem
                            suffix = original_dest.suffix
                            dest_path = type_dirs[category] / f"{stem}_{counter}{suffix}"
                            counter += 1
                        
                        if copy_func(source_path, dest_path, resume):
                            total_extracted += 1
                            extracted_size += file_size
                            total_size_extracted += file_size
                            
                            # Update global state
                            extraction_state.total_files_extracted = total_extracted
                            extraction_state.total_size_extracted = total_size_extracted
                            
                            # Update progress description with cumulative progress
                            overall_progress = (total_size_extracted / stats['total_size']) * 100
                            pbar.set_description(f"{desc} [{overall_progress:.1f}% total]")
                        else:
                            pbar.write(f"Error copying {file_record['name']}")
                    else:
                        pbar.write(f"Source file not found: {file_record['name']}")
                else:
                    total_extracted += 1
                    extracted_size += file_size
        
        print(f"  {category.title()}: {type_counts[category]} files ({format_size(extracted_size)})")
    
    return total_extracted, total_size_extracted


def main():
    # Register signal handler for graceful interrupts
    signal.signal(signal.SIGINT, extraction_state.signal_handler)
    
    parser = argparse.ArgumentParser(
        description='Extract files from ibi recovery database with enhanced features',
        epilog='''
Organization modes:
  albums (default): Extract by albums with orphaned files in "Unorganized" folder
  type: Extract by file type (Images, Videos, Documents, Other)

Advanced options:
  --resume: Resume interrupted transfers (default: enabled)
  --no-rsync: Force use of Python copy instead of rsync
  --db-path: Override auto-detected database path
  --files-path: Override auto-detected files path
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('ibi_root', nargs='?', help='Path to ibi root directory (auto-detects structure)')
    parser.add_argument('output_dir', nargs='?', help='Output directory for extracted files (not needed for --verify)')
    parser.add_argument('--by-type', action='store_true', 
                       help='Extract by file type instead of albums')
    parser.add_argument('--list-only', action='store_true', 
                       help='List files without copying them')
    parser.add_argument('--stats', action='store_true',
                       help='Show statistics about file organization')
    parser.add_argument('--resume', action='store_true', default=True,
                       help='Resume interrupted transfers (default: enabled)')
    parser.add_argument('--no-resume', dest='resume', action='store_false',
                       help='Disable resume functionality')
    parser.add_argument('--no-rsync', action='store_true',
                       help='Force use of Python copy instead of rsync')
    parser.add_argument('--db-path', type=Path,
                       help='Override auto-detected database path')
    parser.add_argument('--files-path', type=Path,
                       help='Override auto-detected files path')
    parser.add_argument('--verify', action='store_true',
                       help='Verify file availability and database structure (no extraction)')
    parser.add_argument('--verify-sample', type=int, default=100,
                       help='Number of files to sample for verification (default: 100)')
    parser.add_argument('--export', action='store_true',
                       help='Export metadata to standard formats')
    parser.add_argument('--export-dir', type=Path,
                       help='Directory for exported metadata (default: ./metadata_exports)')
    parser.add_argument('--export-formats', nargs='+',
                       help='Specific formats to export (e.g., lightroom_csv exiftool_csv)')
    parser.add_argument('--list-formats', action='store_true',
                       help='List available export formats')
    
    args = parser.parse_args()
    
    # Handle format listing
    if args.list_formats:
        formats_config = Path(__file__).parent.parent / "export_formats.json"
        if formats_config.exists():
            with open(formats_config) as f:
                config = json.load(f)
            print("Available export formats:")
            for format_name, format_spec in config['formats'].items():
                print(f"  {format_name:<15} - {format_spec['description']}")
        else:
            print("❌ Export formats configuration not found")
        sys.exit(0)
    
    # Validate arguments
    if not args.list_formats and not args.ibi_root:
        parser.error("ibi_root is required unless using --list-formats")
        
    if not args.list_formats and not args.verify and not args.export and not args.output_dir:
        parser.error("output_dir is required unless using --verify or --export")
    
    # Set default export directory
    if args.export and not args.export_dir:
        args.export_dir = Path("./metadata_exports")
    
    ibi_root = Path(args.ibi_root) if args.ibi_root else None
    output_dir = Path(args.output_dir) if args.output_dir else None
    
    if ibi_root and not ibi_root.exists():
        print(f"❌ ibi root directory not found: {ibi_root}")
        sys.exit(1)
    
    # Auto-detect or use provided paths
    if args.db_path and args.files_path:
        db_path = args.db_path
        files_dir = args.files_path
        print(f"Using provided paths:")
        print(f"   Database: {db_path}")
        print(f"   Files: {files_dir}")
    else:
        db_path, files_dir = detect_ibi_structure(ibi_root)
        if not db_path or not files_dir:
            print(f"❌ Could not detect ibi structure in: {ibi_root}")
            print("Expected structure: restsdk/data/db/index.db and restsdk/data/files/")
            print("Use --db-path and --files-path to specify manually")
            sys.exit(1)
    
    if not db_path.exists():
        print(f"❌ Database file not found: {db_path}")
        sys.exit(1)
    
    if not files_dir.exists():
        print(f"❌ Files directory not found: {files_dir}")
        sys.exit(1)
    
    # Check rsync availability
    use_rsync = not args.no_rsync and check_rsync_available()
    if not args.list_only:
        if use_rsync:
            print("✅ Using rsync for file operations (resumable)")
        else:
            print("ℹ️  Using Python copy (rsync not available or disabled)")
        
        if args.resume:
            print("✅ Resume mode enabled")
        else:
            print("ℹ️  Resume mode disabled")
        print()
    
    if not args.list_only and output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    conn = connect_db(db_path)
    files_with_albums, stats = get_all_files_with_albums(conn)
    
    print(f"Found {stats['total_files']} total files in database ({format_size(stats['total_size'])})")
    
    # Show detailed statistics
    if args.stats or True:  # Always show basic stats
        organized_count = sum(1 for item in files_with_albums if item['albums'])
        orphaned_count = len(files_with_albums) - organized_count
        album_names = set()
        for item in files_with_albums:
            for album in item['albums']:
                album_names.add(album['name'])
        
        print(f"  Organized in albums: {organized_count} files")
        print(f"  Orphaned (no albums): {orphaned_count} files")  
        print(f"  Total albums: {len(album_names)}")
        
        if args.stats:
            print(f"  Size breakdown:")
            for file_type, size in stats['size_by_type'].items():
                print(f"    {file_type.title()}: {format_size(size)}")
        print()
    
    # Handle verification mode
    if args.verify:
        print("="*60)
        print("FILE AVAILABILITY VERIFICATION")
        print("="*60)
        
        verification = verify_file_availability(files_with_albums, files_dir, args.verify_sample)
        
        print(f"Sample results:")
        print(f"  Available: {verification['available_count']}/{verification['sample_size']} "
              f"({verification['availability_rate']:.1f}%)")
        print(f"  Missing: {verification['missing_count']}/{verification['sample_size']}")
        print(f"  Available data: {format_size(verification['available_size'])}")
        print(f"  Total sample data: {format_size(verification['total_sample_size'])}")
        print()
        
        if verification['availability_rate'] >= 95:
            print("✅ EXCELLENT: Very high file availability rate")
        elif verification['availability_rate'] >= 80:
            print("✅ GOOD: High file availability rate")
        elif verification['availability_rate'] >= 50:
            print("⚠️  FAIR: Moderate file availability rate")
        else:
            print("❌ POOR: Low file availability rate")
        
        estimated_recoverable = int((verification['availability_rate'] / 100) * stats['total_files'])
        estimated_size = int((verification['availability_rate'] / 100) * stats['total_size'])
        print(f"Estimated recoverable files: {estimated_recoverable}")
        print(f"Estimated recoverable data: {format_size(estimated_size)}")
        print()
        print("Recommendation: " + 
              ("Proceed with extraction" if verification['availability_rate'] >= 50 
               else "Check file paths and mount points"))
        
        conn.close()
        return
    
    # Handle export mode
    if args.export:
        print("="*60)
        print("METADATA EXPORT")
        print("="*60)
        
        export_metadata_formats(files_with_albums, conn, args.export_dir, args.export_formats)
        
        if not args.output_dir:  # Export only mode
            conn.close()
            return
        
        print()  # Add spacing before extraction
    
    # Extract files
    if args.by_type:
        print("Extracting files organized by type...")
        total_extracted, total_size = extract_by_type(files_with_albums, files_dir, output_dir, 
                                                    stats, not args.list_only, use_rsync, args.resume)
    else:
        print("Extracting files organized by albums...")
        total_extracted, total_size = extract_by_albums(files_with_albums, files_dir, output_dir, 
                                                       stats, not args.list_only, use_rsync, args.resume)
    
    if not args.list_only:
        print(f"✅ Total files extracted: {total_extracted} ({format_size(total_size)})")
    
    conn.close()


if __name__ == "__main__":
    main()