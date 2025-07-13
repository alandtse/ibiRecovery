#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
ibi Database Parser - Reference Implementation

This is a minimal reference implementation showing how to parse ibi databases
based on the published schema documentation. Use this as a starting point
for building recovery tools, AI parsers, or data analysis scripts.

Copyright (C) 2024 ibiRecovery Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class IbiDatabaseParser:
    """Reference implementation for parsing ibi databases."""
    
    def __init__(self, db_path: str, files_dir: Optional[str] = None):
        """
        Initialize parser with database and optional files directory.
        
        Args:
            db_path: Path to index.db file
            files_dir: Path to files directory (for file recovery)
        """
        self.db_path = Path(db_path)
        self.files_dir = Path(files_dir) if files_dir else None
        self.conn = None
    
    def connect(self) -> None:
        """Connect to the SQLite database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
    
    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def get_database_info(self) -> Dict:
        """Get basic information about the database."""
        if not self.conn:
            raise RuntimeError("Database not connected")
        
        # Get table list
        tables = [row[0] for row in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        
        # Get file counts
        file_stats = dict(self.conn.execute("""
            SELECT 
                CASE 
                    WHEN mimeType LIKE 'image/%' THEN 'images'
                    WHEN mimeType LIKE 'video/%' THEN 'videos'
                    WHEN mimeType LIKE 'audio/%' THEN 'audio'
                    ELSE 'other'
                END as file_type,
                COUNT(*) as count
            FROM Files 
            WHERE contentID IS NOT NULL AND contentID != ''
            GROUP BY file_type
        """).fetchall())
        
        # Get tag count
        tag_count = self.conn.execute("SELECT COUNT(*) FROM FilesTags").fetchone()[0]
        
        # Get album count  
        album_count = self.conn.execute("SELECT COUNT(*) FROM FileGroups").fetchone()[0]
        
        return {
            'database_path': str(self.db_path),
            'table_count': len(tables),
            'tables': tables,
            'file_statistics': file_stats,
            'ai_tags': tag_count,
            'albums': album_count
        }
    
    def get_all_files(self) -> List[Dict]:
        """Get all files with portable metadata (excludes ibi ecosystem data)."""
        if not self.conn:
            raise RuntimeError("Database not connected")
        
        query = """
        SELECT 
            f.id, f.name, f.contentID, f.mimeType, f.size,
            f.birthTime, f.cTime, f.mTime, f.imageDate, f.videoDate,
            f.imageWidth, f.imageHeight, f.videoWidth, f.videoHeight,
            f.imageLatitude, f.imageLongitude, f.imageAltitude,
            f.videoLatitude, f.videoLongitude, f.videoAltitude,
            f.imageCity, f.imageProvince, f.imageCountry,
            f.videoCity, f.videoProvince, f.videoCountry,
            f.imageCameraMake, f.imageCameraModel,
            f.imageAperture, f.imageExposureTime, f.imageISOSpeed, f.imageFocalLength,
            f.videoDuration, f.audioTitle, f.audioArtist, f.audioAlbum,
            f.description
        FROM Files f
        WHERE f.contentID IS NOT NULL AND f.contentID != ''
        ORDER BY COALESCE(f.videoDate, f.imageDate, f.cTime)
        """
        
        return [dict(row) for row in self.conn.execute(query).fetchall()]
    
    def get_file_tags(self, file_id: str) -> List[Dict]:
        """Get AI-generated content tags for a specific file."""
        if not self.conn:
            raise RuntimeError("Database not connected")
        
        query = """
        SELECT tag, auto
        FROM FilesTags 
        WHERE fileID = ?
        ORDER BY tag
        """
        
        return [dict(row) for row in self.conn.execute(query, (file_id,)).fetchall()]
    
    def get_file_albums(self, file_id: str) -> List[Dict]:
        """Get albums containing a specific file.""" 
        if not self.conn:
            raise RuntimeError("Database not connected")
        
        query = """
        SELECT fg.id, fg.name, fg.description, fg.estCount
        FROM FileGroups fg
        JOIN FileGroupFiles fgf ON fg.id = fgf.fileGroupID
        WHERE fgf.fileID = ?
        ORDER BY fg.name
        """
        
        return [dict(row) for row in self.conn.execute(query, (file_id,)).fetchall()]
    
    def get_all_albums(self) -> List[Dict]:
        """Get all albums with their file counts."""
        if not self.conn:
            raise RuntimeError("Database not connected")
        
        query = """
        SELECT 
            fg.id, fg.name, fg.description, fg.estCount,
            fg.cTime, fg.mTime, fg.estMinTime, fg.estMaxTime,
            COUNT(fgf.fileID) as actual_count
        FROM FileGroups fg
        LEFT JOIN FileGroupFiles fgf ON fg.id = fgf.fileGroupID
        GROUP BY fg.id, fg.name, fg.description, fg.estCount, fg.cTime, fg.mTime
        ORDER BY fg.estCount DESC
        """
        
        return [dict(row) for row in self.conn.execute(query).fetchall()]
    
    def get_content_tags_summary(self) -> List[Dict]:
        """Get summary of AI-generated content tags."""
        if not self.conn:
            raise RuntimeError("Database not connected")
        
        query = """
        SELECT tag, COUNT(*) as count
        FROM FilesTags 
        WHERE auto = 1
        GROUP BY tag
        ORDER BY count DESC
        """
        
        return [dict(row) for row in self.conn.execute(query).fetchall()]
    
    def find_physical_file(self, content_id: str) -> Optional[Path]:
        """Find the physical file using contentID."""
        if not self.files_dir or not content_id:
            return None
        
        # ibi storage formula: /files/{first_char}/{contentID}
        first_char = content_id[0] if content_id else '_'
        file_path = self.files_dir / first_char / content_id
        
        return file_path if file_path.exists() else None
    
    def verify_file_recovery_rate(self, sample_size: int = 100) -> Dict:
        """Check what percentage of database files are physically recoverable."""
        if not self.files_dir:
            return {'error': 'Files directory not provided'}
        
        # Get sample of files
        query = f"""
        SELECT contentID, name 
        FROM Files 
        WHERE contentID IS NOT NULL AND contentID != ''
        ORDER BY RANDOM() LIMIT {sample_size}
        """
        
        files = list(self.conn.execute(query).fetchall())
        found_count = 0
        
        for row in files:
            if self.find_physical_file(row['contentID']):
                found_count += 1
        
        return {
            'sample_size': len(files),
            'files_found': found_count,
            'recovery_rate': (found_count / len(files)) * 100 if files else 0
        }
    
    def export_comprehensive_data(self) -> Dict:
        """Export all useful data in a structured format."""
        files = self.get_all_files()
        
        # Enhance each file with tags and albums
        for file_record in files:
            file_id = file_record['id']
            file_record['ai_tags'] = [tag['tag'] for tag in self.get_file_tags(file_id) if tag['auto']]
            file_record['albums'] = self.get_file_albums(file_id)
            
            # Add physical file path if available
            if self.files_dir:
                physical_path = self.find_physical_file(file_record['contentID'])
                file_record['physical_file_path'] = str(physical_path) if physical_path else None
        
        return {
            'database_info': self.get_database_info(),
            'files': files,
            'albums': self.get_all_albums(),
            'content_tags_summary': self.get_content_tags_summary(),
            'export_timestamp': str(Path().cwd()),  # Placeholder for actual timestamp
        }

def main():
    """Example usage of the ibi database parser."""
    import argparse
    
    parser = argparse.ArgumentParser(description='ibi Database Parser - Reference Implementation')
    parser.add_argument('database', help='Path to index.db file')
    parser.add_argument('--files-dir', help='Path to files directory')
    parser.add_argument('--output', help='Output JSON file for exported data')
    parser.add_argument('--verify-recovery', action='store_true', help='Check file recovery rate')
    
    args = parser.parse_args()
    
    # Initialize parser
    ibi_parser = IbiDatabaseParser(args.database, args.files_dir)
    
    try:
        ibi_parser.connect()
        
        # Get basic info
        db_info = ibi_parser.get_database_info()
        print("Database Information:")
        print(f"  Tables: {db_info['table_count']}")
        print(f"  Files: {db_info['file_statistics']}")
        print(f"  AI Tags: {db_info['ai_tags']}")
        print(f"  Albums: {db_info['albums']}")
        print()
        
        # Verify recovery rate if requested
        if args.verify_recovery and args.files_dir:
            recovery_info = ibi_parser.verify_file_recovery_rate()
            print(f"File Recovery Rate: {recovery_info['recovery_rate']:.1f}%")
            print(f"Sample: {recovery_info['files_found']}/{recovery_info['sample_size']} files found")
            print()
        
        # Export comprehensive data if requested
        if args.output:
            print("Exporting comprehensive data...")
            data = ibi_parser.export_comprehensive_data()
            
            with open(args.output, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
            print(f"Data exported to: {args.output}")
            print(f"Exported {len(data['files'])} files with metadata")
    
    finally:
        ibi_parser.close()

if __name__ == "__main__":
    main()