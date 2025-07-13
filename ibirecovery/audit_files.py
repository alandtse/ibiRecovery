#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
ibiRecovery File Audit Script

This script compares the actual files on disk with the database records
to identify orphaned files and missing database entries.
"""

import sqlite3
import os
import sys
from pathlib import Path
import argparse
import json
from collections import defaultdict

def connect_db(db_path):
    """Connect to the SQLite database."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def get_all_database_files(conn):
    """Get all files from database with their contentIDs."""
    query = """
    SELECT id, name, contentID, mimeType, size, storageID
    FROM Files 
    WHERE contentID IS NOT NULL AND contentID != ''
    """
    return {row['contentID']: dict(row) for row in conn.execute(query).fetchall()}

def scan_files_directory(files_dir):
    """Recursively scan the files directory and return all found files."""
    found_files = {}
    
    print(f"Scanning files directory: {files_dir}")
    
    # Walk through all subdirectories
    for root, dirs, files in os.walk(files_dir):
        for file in files:
            file_path = Path(root) / file
            
            # Calculate relative path from files_dir
            try:
                rel_path = file_path.relative_to(files_dir)
                # Use the filename as potential contentID
                content_id = file_path.name
                
                found_files[content_id] = {
                    'path': str(file_path),
                    'relative_path': str(rel_path),
                    'size': file_path.stat().st_size if file_path.exists() else 0
                }
            except Exception as e:
                print(f"Error processing file {file_path}: {e}")
    
    return found_files

def find_file_by_content_id(files_dir, content_id):
    """Find a file using the discovered directory structure."""
    if not content_id:
        return None
    
    # Files are stored as: files_dir/first_char/contentID
    first_char = content_id[0] if content_id else '_'
    file_path = files_dir / first_char / content_id
    
    if file_path.exists() and file_path.is_file():
        return file_path
    
    return None

def audit_files(conn, files_dir, output_dir=None):
    """Perform comprehensive audit of files vs database."""
    
    print("=" * 60)
    print("FILE AUDIT REPORT")
    print("=" * 60)
    
    # Get database files
    print("Loading database records...")
    db_files = get_all_database_files(conn)
    print(f"Found {len(db_files)} files in database")
    
    # Scan actual files
    print("Scanning actual files on disk...")
    disk_files = scan_files_directory(files_dir)
    print(f"Found {len(disk_files)} files on disk")
    
    # Cross-reference
    print("\nPerforming cross-reference analysis...")
    
    matched_files = {}
    missing_files = {}
    orphaned_files = {}
    size_mismatches = {}
    
    # Check database files against disk
    for content_id, db_record in db_files.items():
        file_path = find_file_by_content_id(files_dir, content_id)
        
        if file_path:
            # File found - check size
            actual_size = file_path.stat().st_size
            db_size = db_record.get('size', 0) or 0
            
            matched_files[content_id] = {
                'db_record': db_record,
                'file_path': str(file_path),
                'actual_size': actual_size,
                'db_size': db_size
            }
            
            # Check for size mismatches (allow 10% variance for metadata differences)
            if db_size > 0 and abs(actual_size - db_size) > (db_size * 0.1):
                size_mismatches[content_id] = {
                    'db_size': db_size,
                    'actual_size': actual_size,
                    'difference': actual_size - db_size,
                    'file_name': db_record.get('name', 'Unknown')
                }
        else:
            # File missing from disk
            missing_files[content_id] = db_record
    
    # Check for orphaned files (on disk but not in database)
    for file_id, file_info in disk_files.items():
        if file_id not in db_files:
            # Try to find it by different matching strategies
            found_match = False
            
            # Check if any database file points to this location
            for db_content_id, db_record in db_files.items():
                if find_file_by_content_id(files_dir, db_content_id) == Path(file_info['path']):
                    found_match = True
                    break
            
            if not found_match:
                orphaned_files[file_id] = file_info
    
    # Generate report
    print("\n" + "="*60)
    print("AUDIT RESULTS")
    print("="*60)
    
    print(f"Database files: {len(db_files)}")
    print(f"Disk files: {len(disk_files)}")
    print(f"Matched files: {len(matched_files)}")
    print(f"Missing files (in DB but not on disk): {len(missing_files)}")
    print(f"Orphaned files (on disk but not in DB): {len(orphaned_files)}")
    print(f"Size mismatches: {len(size_mismatches)}")
    
    # Calculate recovery rate
    recovery_rate = (len(matched_files) / len(db_files)) * 100 if db_files else 0
    print(f"\nRecovery rate: {recovery_rate:.1f}%")
    
    # Show details
    if missing_files:
        print(f"\nMISSING FILES (first 10):")
        print("-" * 40)
        for i, (content_id, record) in enumerate(list(missing_files.items())[:10]):
            print(f"  {record.get('name', 'Unknown')} ({record.get('mimeType', 'Unknown')})")
        if len(missing_files) > 10:
            print(f"  ... and {len(missing_files) - 10} more")
    
    if size_mismatches:
        print(f"\nSIZE MISMATCHES (first 10):")
        print("-" * 40)
        for i, (content_id, mismatch) in enumerate(list(size_mismatches.items())[:10]):
            diff_pct = (mismatch['difference'] / mismatch['db_size']) * 100 if mismatch['db_size'] > 0 else 0
            print(f"  {mismatch['file_name']}: DB={mismatch['db_size']}, Disk={mismatch['actual_size']} ({diff_pct:+.1f}%)")
        if len(size_mismatches) > 10:
            print(f"  ... and {len(size_mismatches) - 10} more")
    
    if orphaned_files:
        print(f"\nORPHANED FILES (first 10):")
        print("-" * 40)
        for i, (file_id, file_info) in enumerate(list(orphaned_files.items())[:10]):
            size_mb = file_info['size'] / (1024*1024)
            print(f"  {file_info['relative_path']} ({size_mb:.1f} MB)")
        if len(orphaned_files) > 10:
            print(f"  ... and {len(orphaned_files) - 10} more")
    
    # Save detailed report if output directory specified
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        audit_report = {
            'summary': {
                'database_files': len(db_files),
                'disk_files': len(disk_files),
                'matched_files': len(matched_files),
                'missing_files': len(missing_files),
                'orphaned_files': len(orphaned_files),
                'size_mismatches': len(size_mismatches),
                'recovery_rate': recovery_rate
            },
            'matched_files': matched_files,
            'missing_files': missing_files,
            'orphaned_files': orphaned_files,
            'size_mismatches': size_mismatches
        }
        
        report_file = output_dir / 'file_audit_report.json'
        with open(report_file, 'w') as f:
            json.dump(audit_report, f, indent=2)
        
        print(f"\nDetailed audit report saved to: {report_file}")
        
        # Create CSV summary for easy analysis
        import csv
        csv_file = output_dir / 'audit_summary.csv'
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Type', 'ContentID', 'FileName', 'MimeType', 'DBSize', 'DiskSize', 'Status'])
            
            for content_id, match in matched_files.items():
                writer.writerow([
                    'Matched',
                    content_id,
                    match['db_record'].get('name', ''),
                    match['db_record'].get('mimeType', ''),
                    match['db_size'],
                    match['actual_size'],
                    'Size Mismatch' if content_id in size_mismatches else 'OK'
                ])
            
            for content_id, record in missing_files.items():
                writer.writerow([
                    'Missing',
                    content_id,
                    record.get('name', ''),
                    record.get('mimeType', ''),
                    record.get('size', 0),
                    0,
                    'File Not Found'
                ])
        
        print(f"CSV summary saved to: {csv_file}")
    
    return {
        'matched': len(matched_files),
        'missing': len(missing_files), 
        'orphaned': len(orphaned_files),
        'recovery_rate': recovery_rate
    }

def check_directory_structure(files_dir):
    """Analyze the directory structure to understand file organization."""
    print("\nDIRECTORY STRUCTURE ANALYSIS:")
    print("-" * 35)
    
    structure = defaultdict(int)
    total_files = 0
    
    for root, dirs, files in os.walk(files_dir):
        level = len(Path(root).relative_to(files_dir).parts)
        structure[level] += len(files)
        total_files += len(files)
    
    print(f"Total files found: {total_files}")
    for level, count in sorted(structure.items()):
        if level == 0:
            print(f"  Root level: {count} files")
        else:
            print(f"  Level {level}: {count} files")
    
    # Show some sample directory names
    sample_dirs = []
    for root, dirs, files in os.walk(files_dir):
        if len(sample_dirs) >= 10:
            break
        rel_path = Path(root).relative_to(files_dir)
        if rel_path != Path('.') and dirs:
            sample_dirs.append(str(rel_path))
    
    if sample_dirs:
        print(f"\nSample directory paths:")
        for dir_path in sample_dirs[:5]:
            print(f"  {dir_path}")

def main():
    parser = argparse.ArgumentParser(description='Audit files against database records')
    parser.add_argument('db_path', help='Path to the index.db file')
    parser.add_argument('files_dir', help='Path to the files directory')
    parser.add_argument('--output-dir', help='Directory to save detailed audit reports')
    parser.add_argument('--structure-only', action='store_true', help='Only analyze directory structure')
    
    args = parser.parse_args()
    
    db_path = Path(args.db_path)
    files_dir = Path(args.files_dir)
    
    if not db_path.exists():
        print(f"Database file not found: {db_path}")
        sys.exit(1)
    
    if not files_dir.exists():
        print(f"Files directory not found: {files_dir}")
        sys.exit(1)
    
    # Always check directory structure first
    check_directory_structure(files_dir)
    
    if not args.structure_only:
        conn = connect_db(db_path)
        results = audit_files(conn, files_dir, args.output_dir)
        conn.close()
        
        print(f"\n" + "="*50)
        print("AUDIT COMPLETE")
        print("="*50)
        print(f"Recovery Rate: {results['recovery_rate']:.1f}%")
        
        if results['recovery_rate'] > 90:
            print("✓ EXCELLENT: Very high file recovery rate")
        elif results['recovery_rate'] > 70:
            print("✓ GOOD: High file recovery rate")
        elif results['recovery_rate'] > 50:
            print("⚠ MODERATE: Acceptable file recovery rate")
        else:
            print("⚠ POOR: Low file recovery rate")

if __name__ == "__main__":
    main()