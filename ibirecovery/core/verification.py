# SPDX-License-Identifier: GPL-3.0-or-later
"""
Verification and audit functionality for ibiRecovery.

Handles file verification, availability checking, and comprehensive audits.

Copyright (C) 2024 ibiRecovery Contributors
Licensed under GPL-3.0-or-later
"""

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .orphan_filter import OrphanFileFilter, print_orphan_filter_summary
from .utils import find_source_file, format_size


def scan_files_directory(files_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Scan all files in the files directory."""
    scanned_files = {}

    print("🔍 Scanning files directory...")
    for subdir in files_dir.iterdir():
        if not subdir.is_dir():
            continue

        for file_path in subdir.iterdir():
            if file_path.is_file():
                scanned_files[file_path.name] = {
                    "path": file_path,
                    "size": file_path.stat().st_size,
                    "content_id": file_path.name,
                }

    return scanned_files


def comprehensive_audit(
    files_with_albums: List[Dict[str, Any]],
    files_dir: Path,
    audit_report_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Perform comprehensive audit comparing database with disk."""
    print("🔍 Starting comprehensive file audit...")

    # Scan all files on disk
    disk_files = scan_files_directory(files_dir)
    print(f"📁 Found {len(disk_files):,} files on disk")

    # Get all content IDs from database
    db_content_ids = set()
    db_files_by_id = {}

    for item in files_with_albums:
        file_record = item["file"]
        content_id = file_record["contentID"]
        if content_id:
            db_content_ids.add(content_id)
            db_files_by_id[content_id] = file_record

    print(f"🗄️  Found {len(db_content_ids):,} files in database")

    # Calculate availability rates
    disk_content_ids = set(disk_files.keys())

    # Files in database and on disk
    available_files = db_content_ids & disk_content_ids

    # Files in database but missing from disk
    missing_files = db_content_ids - disk_content_ids

    # Files on disk but not in database (orphaned)
    orphaned_files = disk_content_ids - db_content_ids

    # Apply orphan filtering to reduce noise
    orphan_filter_results = None
    filtered_orphaned_files = orphaned_files

    if orphaned_files:
        print(f"\n🔍 Analyzing {len(orphaned_files):,} orphaned files...")
        orphan_filter = OrphanFileFilter(files_dir)
        orphan_file_paths = [disk_files[cid]["path"] for cid in orphaned_files]
        orphan_filter_results = orphan_filter.filter_orphan_files(orphan_file_paths)

        # Show filtering results
        print_orphan_filter_summary(orphan_filter_results)

        # Get filtered list of content IDs to keep
        keep_paths = {item["file_path"] for item in orphan_filter_results["keep_files"]}
        filtered_orphaned_files = {
            cid for cid in orphaned_files if disk_files[cid]["path"] in keep_paths
        }

    # Calculate statistics
    db_total_size = sum(
        (db_files_by_id[cid].get("size") or 0) for cid in db_content_ids
    )
    available_size = sum(
        (db_files_by_id[cid].get("size") or 0) for cid in available_files
    )
    missing_size = sum((db_files_by_id[cid].get("size") or 0) for cid in missing_files)
    orphaned_size = sum((disk_files[cid]["size"]) for cid in orphaned_files)
    filtered_orphaned_size = sum(
        (disk_files[cid]["size"]) for cid in filtered_orphaned_files
    )

    # Calculate percentages
    file_recovery_rate = (
        (len(available_files) / len(db_content_ids)) * 100 if db_content_ids else 0
    )
    size_recovery_rate = (available_size / db_total_size) * 100 if db_total_size else 0
    orphan_rate = (len(orphaned_files) / len(disk_files)) * 100 if disk_files else 0
    filtered_orphan_rate = (
        (len(filtered_orphaned_files) / len(disk_files)) * 100 if disk_files else 0
    )

    print(f"\n📊 FINAL AUDIT RESULTS:")
    print(f"  Database files: {len(db_content_ids):,} ({format_size(db_total_size)})")
    print(
        f"  Available files: {len(available_files):,} ({format_size(available_size)})"
    )
    print(f"  Missing files: {len(missing_files):,} ({format_size(missing_size)})")
    print(
        f"  Raw orphaned files: {len(orphaned_files):,} ({format_size(orphaned_size)})"
    )
    print(
        f"  Filtered orphaned files: {len(filtered_orphaned_files):,} ({format_size(filtered_orphaned_size)})"
    )
    print(f"  File recovery rate: {file_recovery_rate:.1f}%")
    print(f"  Size recovery rate: {size_recovery_rate:.1f}%")
    print(f"  Raw orphan rate: {orphan_rate:.1f}%")
    print(f"  Filtered orphan rate: {filtered_orphan_rate:.1f}%")

    # Save detailed audit report if requested
    if audit_report_dir:
        audit_report_dir.mkdir(parents=True, exist_ok=True)

        # Detailed audit report
        audit_report = {
            "audit_timestamp": json.dumps(datetime.now().isoformat()),
            "summary": {
                "database_files": len(db_content_ids),
                "disk_files": len(disk_files),
                "available_files": len(available_files),
                "missing_files": len(missing_files),
                "orphaned_files": len(orphaned_files),
                "database_total_size": db_total_size,
                "available_size": available_size,
                "missing_size": missing_size,
                "orphaned_size": orphaned_size,
                "file_recovery_rate": file_recovery_rate,
                "size_recovery_rate": size_recovery_rate,
                "orphan_rate": orphan_rate,
            },
            "missing_file_details": [
                {
                    "content_id": cid,
                    "name": db_files_by_id[cid].get("name"),
                    "size": db_files_by_id[cid].get("size"),
                    "mime_type": db_files_by_id[cid].get("mimeType"),
                }
                for cid in list(missing_files)[:100]  # Limit for report size
            ],
            "orphaned_file_details": [
                {
                    "content_id": cid,
                    "path": str(disk_files[cid]["path"]),
                    "size": disk_files[cid]["size"],
                }
                for cid in list(orphaned_files)[:100]  # Limit for report size
            ],
        }

        # Save JSON report
        report_file = audit_report_dir / "audit_report.json"
        with open(report_file, "w") as f:
            json.dump(audit_report, f, indent=2)

        # Save CSV summary
        csv_file = audit_report_dir / "audit_summary.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Metric", "Count", "Size", "Percentage"])
            writer.writerow(
                [
                    "Database Files",
                    len(db_content_ids),
                    format_size(db_total_size),
                    "100.0%",
                ]
            )
            writer.writerow(
                [
                    "Available Files",
                    len(available_files),
                    format_size(available_size),
                    f"{file_recovery_rate:.1f}%",
                ]
            )
            writer.writerow(
                [
                    "Missing Files",
                    len(missing_files),
                    format_size(missing_size),
                    f"{(len(missing_files)/len(db_content_ids)*100):.1f}%",
                ]
            )
            writer.writerow(
                [
                    "Orphaned Files",
                    len(orphaned_files),
                    format_size(orphaned_size),
                    f"{orphan_rate:.1f}%",
                ]
            )

        print(f"📄 Detailed audit reports saved to: {audit_report_dir}")

    return {
        "database_files": len(db_content_ids),
        "disk_files": len(disk_files),
        "available_files": len(available_files),
        "missing_files": len(missing_files),
        "orphaned_files": len(orphaned_files),
        "filtered_orphaned_files": len(filtered_orphaned_files),
        "file_recovery_rate": file_recovery_rate,
        "size_recovery_rate": size_recovery_rate,
        "orphan_rate": orphan_rate,
        "filtered_orphan_rate": filtered_orphan_rate,
        "available_size": available_size,
        "missing_size": missing_size,
        "orphaned_size": orphaned_size,
        "filtered_orphaned_size": filtered_orphaned_size,
        "orphan_filter_results": orphan_filter_results,
        "comprehensive": True,
    }


def verify_file_availability(
    files_with_albums: List[Dict[str, Any]],
    files_dir: Path,
    sample_size: int = 100,
    audit_report_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Verify file availability by checking files (sample or comprehensive audit)."""
    if not files_with_albums:
        print("⚠️  No files to verify")
        return {
            "total_files": 0,
            "files_found": 0,
            "recovery_rate": 0.0,
            "sample_size": 0,
        }

    # Determine if this is comprehensive audit mode
    is_comprehensive = sample_size == 0 or audit_report_dir is not None

    if is_comprehensive:
        print("🔍 Running comprehensive audit mode...")
        # For comprehensive audit, we need additional tracking

        # Also analyze deduplication potential during comprehensive audit

        return comprehensive_audit(files_with_albums, files_dir, audit_report_dir)
    else:
        # Sample-based verification
        total_files = len(files_with_albums)
        actual_sample_size = min(sample_size, total_files)

        print(f"🔍 Verifying file availability (sample: {actual_sample_size} files)...")

        # Preferentially sample files with storageID for userStorage compatibility
        files_with_storage = [
            item for item in files_with_albums if item["file"].get("storageID")
        ]
        files_without_storage = [
            item for item in files_with_albums if not item["file"].get("storageID")
        ]

        # Create balanced sample: prefer files with storageID, but include some without
        if files_with_storage and len(files_with_storage) >= actual_sample_size // 2:
            # Use mostly files with storageID
            storage_sample_size = min(
                actual_sample_size * 3 // 4, len(files_with_storage)
            )
            traditional_sample_size = actual_sample_size - storage_sample_size
            sample_files = (
                files_with_storage[:storage_sample_size]
                + files_without_storage[:traditional_sample_size]
            )
        else:
            # Fall back to original sampling if insufficient userStorage files
            sample_files = files_with_albums[:actual_sample_size]

        files_found = 0

        for item in sample_files:
            file_record = item["file"]
            content_id = file_record["contentID"]

            # Enhanced file finding with userStorage support
            file_name = file_record.get("name")
            storage_id = file_record.get("storageID")
            # Calculate database path correctly based on files_dir structure
            # files_dir is typically: .../restsdk/data/files
            # database is at: .../restsdk/data/db/index.db
            db_file_path = files_dir.parent / "db" / "index.db"

            source_path = find_source_file(
                files_dir, content_id, file_name, storage_id, db_file_path
            )
            if source_path and source_path.exists():
                files_found += 1

        recovery_rate = (files_found / actual_sample_size) * 100

        print(
            f"📊 File availability: {recovery_rate:.1f}% ({files_found}/{actual_sample_size} found)"
        )

        if recovery_rate >= 90:
            print("✅ Good availability - proceed with extraction")
        elif recovery_rate >= 70:
            print("⚠️  Moderate availability - some files may be missing")
        else:
            print("❌ Low availability - check file paths and disk integrity")

        return {
            "total_files": total_files,
            "files_found": files_found,
            "recovery_rate": recovery_rate,
            "sample_size": actual_sample_size,
        }
