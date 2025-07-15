# SPDX-License-Identifier: GPL-3.0-or-later
"""
ibiRecovery Core Modules

Core functionality modules for the ibiRecovery toolkit.

Copyright (C) 2024 ibiRecovery Contributors
Licensed under GPL-3.0-or-later
"""

__version__ = "1.0.0"
__author__ = "Alan Tse"
__email__ = "alandtse@gmail.com"
__license__ = "GPL-3.0-or-later"

# Import main functionality for easy access
from .database import (
    connect_db,
    detect_ibi_structure,
    get_all_files_with_albums,
    get_comprehensive_export_data,
    get_merged_files_with_albums,
)
from .export import MetadataExporter, export_metadata_formats
from .file_operations import (
    check_rsync_available,
    copy_file_fallback,
    copy_file_rsync,
    get_best_timestamp,
    get_time_organized_path,
    set_file_metadata,
)
from .orphan_filter import OrphanFileFilter
from .utils import find_source_file, format_size
from .verification import (
    comprehensive_audit,
    scan_files_directory,
    verify_file_availability,
)

__all__ = [
    "connect_db",
    "detect_ibi_structure",
    "get_all_files_with_albums",
    "get_merged_files_with_albums",
    "copy_file_fallback",
    "copy_file_rsync",
    "get_best_timestamp",
    "get_time_organized_path",
    "set_file_metadata",
    "format_size",
    "find_source_file",
    "verify_file_availability",
    "comprehensive_audit",
    "export_metadata_formats",
    "MetadataExporter",
    "OrphanFileFilter",
    "scan_files_directory",
    "check_rsync_available",
]
