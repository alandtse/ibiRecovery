# ibi Database Recovery Tools & Documentation

[![License: GPL v3](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://alandtse.github.io/ibiRecovery/)

Complete toolkit for recovering photos, videos, and metadata from ibi device databases. Includes full schema documentation, recovery tools, and export utilities for popular photo management software.

## 🎯 What This Recovers

Based on my own needs:

- ✅ **8,500+ files** with 99-100% recovery rate
- ✅ **5,312+ AI content tags** (automatic "person", "child", "beach" categorization)
- ✅ **50+ family albums** with meaningful names ("Jon's graduation", "Hawaii 2010")
- ✅ **Complete GPS/location data** from geotagged photos
- ✅ **Full camera EXIF metadata** (make, model, settings)
- ✅ **Export to any photo software** (Lightroom, Apple Photos, digiKam, etc.)

## ⚠️ Why This Project Exists

**SanDisk ibi End of Life**: On August 31, 2024, Western Digital [officially ended support](https://support-en.wd.com/app/answers/detailweb/a_id/51848) for all ibi devices. As stated by WD: _"WD is focused on providing exceptional customer experiences with our products. With that focus, from time to time we retire legacy products."_

**What Stopped Working**:

- ❌ Remote access to your ibi device
- ❌ Mobile apps and web interface
- ❌ Cloud imports and scheduled backups
- ❌ Security updates and technical support

**Why Recovery is Urgent**:

- Local access only works if enabled before August 31, 2024
- Factory resets or Wi-Fi changes can permanently lock you out
- No official recovery tools provided by Western Digital
- Professional data recovery services cost hundreds of dollars

**This toolkit provides the free, open-source solution families need to recover their photos before they're lost forever.**

## 🔧 Prerequisites: Getting Access to Your ibi Data

**⚠️ CRITICAL**: You need **direct access to the ibi device's hard drive** - network/Wi-Fi access is NOT sufficient.

### 📂 What You Need to Find

The ibi data is stored in this directory structure on the device:

```
/restsdk/data/
├── db/
│   └── index.db          # SQLite database with all metadata
├── dbBackup/
│   └── index.db          # Backup database (optional, additional recovery)
└── files/
    ├── 0/                # Files starting with '0'
    ├── 1/                # Files starting with '1'
    ├── ...
    └── f/                # Files starting with 'f'
```

### 🛠️ Access Methods

#### Method 1: Full Drive Imaging (Recommended)

**⚠️ IMPORTANT**: ibi devices often have corrupted partition tables that require recovery tools. A full disk image is the safest approach:

1. **Power down** your ibi device safely
2. **Remove the hard drive** from the device enclosure
3. **Connect to a computer** using a USB-to-SATA adapter or external dock
4. **Create a full drive image** for safety:
   ```bash
   # Create complete backup (replace /dev/sdX with your drive)
   sudo dd if=/dev/sdX of=ibi_drive_image.img bs=1M status=progress
   ```
5. **Use partition recovery tools** to access the data partition:

   ```bash
   # Use testdisk to analyze and recover partitions
   sudo testdisk ibi_drive_image.img

   # Mount the recovered partition (offset varies by device)
   sudo mount -o ro,loop,offset=$((SECTOR * 512)) ibi_drive_image.img /mnt/ibi_recovery
   ```

See our [Disk Analysis Methodology](docs/disk_analysis_methodology.md) for detailed partition recovery steps using `testdisk`.

#### Method 2: Direct Drive Access (If Partition Table Is Intact)

If the partition table is not corrupted, you may be able to mount directly:

1. **Connect the drive** using a USB-to-SATA adapter
2. **Mount the ext4 data partition** (typically the largest partition)
3. **Navigate to** `/restsdk/data/` on the mounted drive
4. **Copy the entire directory** to your recovery computer

**Professional Recovery Services**: If you're not comfortable with drive removal, data recovery services can extract the files (typically $200-500).

### ✅ Verify Your Access

Once you have access, verify the structure:

```bash
# Check for required files
ls /path/to/your/ibi_data/restsdk/data/db/index.db       # Main database file
ls /path/to/your/ibi_data/restsdk/data/dbBackup/index.db # Backup database (optional)
ls /path/to/your/ibi_data/restsdk/data/files/            # Files directory

# Quick verification with this toolkit
poetry run ibi-extract --verify /path/to/your/ibi_data
```

## 🚀 Quick Start

### Option 1: Install Package (Recommended)

```bash
# Install directly from GitHub
pip install git+https://github.com/alandtse/ibiRecovery.git

# Or clone and install with poetry
git clone https://github.com/alandtse/ibiRecovery.git
cd ibiRecovery
poetry install
```

### Option 2: Use Scripts Directly

```bash
# Clone the repository
git clone https://github.com/alandtse/ibiRecovery.git
cd ibiRecovery
```

### For Families (Recover Your Photos)

#### Using Installed Commands

```bash
# If installed globally
ibi-extract /path/to/ibi_root ./my_recovered_photos

# If installed with poetry (run from project directory)
poetry run ibi-extract --verify /path/to/ibi_root               # Verify what can be recovered
poetry run ibi-extract --export /path/to/ibi_root               # Export metadata only
poetry run ibi-extract /path/to/ibi_root ./my_recovered_photos  # Extract files
poetry run ibi-extract /path/to/ibi_root ./output --export      # Extract + export metadata
```

#### Alternative: Direct Script Usage

```bash
# If not using poetry, run the package scripts directly:
python -m ibirecovery.extract_files --verify /path/to/ibi_root
python -m ibirecovery.extract_files --export /path/to/ibi_root
python -m ibirecovery.extract_files /path/to/ibi_root ./output --export
```

### For Developers (Build Recovery Tools)

Use the clean reference implementation to build custom tools:

```python
from docs.reference_implementation import IbiDatabaseParser

# Connect to database
parser = IbiDatabaseParser('/path/to/index.db', '/path/to/files/')
parser.connect()

# Get comprehensive data export
data = parser.export_comprehensive_data()

# Or specific queries:
files = parser.get_all_files()              # All files with metadata
tags = parser.get_content_tags_summary()   # AI content analysis
albums = parser.get_all_albums()           # Album organization
recovery = parser.verify_file_recovery_rate() # File availability
```

## 📁 Repository Structure

```
ibiRecovery/
├── docs/                           # Complete documentation & developer resources
│   ├── schema_documentation.md     # Full database schema
│   ├── api_specification.json      # Machine-readable API spec
│   ├── reference_implementation.py # Clean parser API for developers
│   ├── developer_guide.md          # How to build custom tools
│   └── metadata_strategy.md        # Best practices guide
├── ibirecovery/                    # Python package (installable)
│   └── extract_files.py           # Complete tool: extract + verify + audit + metadata verification + export + progress + resume
└── export_formats.json            # Export format specifications
```

## 📖 Documentation

- **[ibi Discontinuation Details](docs/ibi_discontinuation.md)** - Official timeline and impact analysis
- **[Complete Schema Documentation](docs/schema_documentation.md)** - Full database structure
- **[Developer Guide](docs/developer_guide.md)** - For developers and researchers
- **[Reference Implementation](docs/reference_implementation.py)** - Clean parser API for building tools
- **[Metadata Strategy](docs/metadata_strategy.md)** - What to preserve vs. what to filter
- **[API Specification](docs/api_specification.json)** - Machine-readable format spec
- **[Disk Analysis Methodology](docs/disk_analysis_methodology.md)** - Technical recovery process

## 🛠️ Available Tools

### Main Tool

- **`ibi-extract`** - Complete solution with extraction, verification, metadata export (12 formats), progress bars, and resume capability

### CLI Commands (via poetry install)

- **`ibi-extract`** - Complete tool for extraction, verification, auditing, metadata verification, and export

### Optional Features

- **Metadata Verification**: Use `--verify-metadata` to compare existing file metadata with database (requires: `pip install pillow`)

## 📊 What Makes This Special

### Complete Recovery Beyond Just Files

Most data recovery tools just extract files. This toolkit recovers:

- **Organized photo libraries** with original album structure
- **Searchable content** via 5,312+ AI-generated tags
- **Geographic context** through GPS and location data
- **Technical metadata** for photo management software
- **Backup database recovery** - automatically finds and merges additional files from backup databases

### Universal Compatibility

Export metadata to any photo/video management software:

**Photo Management**:

- Adobe Lightroom (LR/Transporter CSV)
- digiKam (IPTC-compliant CSV)
- Apple Photos (Simple CSV format)
- PhotoPrism (WebDAV-compatible CSV)
- XMP Sidecar files (Universal standard)

**Video Management**:

- Jellyfin (NFO metadata files)
- Plex (CSV import format)
- IPTC Video Metadata Hub (Professional standard)

**Universal Formats**:

- ExifTool CSV (Industry standard)
- Google Takeout JSON (Cloud migration)
- JSON Metadata (API integration)

### Clean, Portable Data

Filters out ibi-specific vendor lock-in data while preserving valuable content:

- ✅ AI content analysis → Portable keywords
- ✅ User albums → Folder organization
- ✅ GPS/EXIF → Standard metadata
- ❌ ibi sharing systems → Removed
- ❌ Internal permissions → Filtered out

## 🔬 For Researchers & Developers

This project provides:

- **Complete reverse-engineered schema** for ibi databases
- **37 documented tables** with relationships and field descriptions
- **Reference implementation** for building tools
- **Real-world dataset insights** (2017-2023 timeframe)
- **AI content analysis data** for research

### Version Compatibility

- **Database Schema Version**: 166
- **SQLite Version**: 3.x (schema version 300)
- **Feature Set**: AI tagging, multi-user, GPS integration
- **Time Period**: 2017-2023 data compatibility verified

## 🧪 Testing & Development

Comprehensive test suite and development tools ensure reliability and code quality:

### Quick Start

```bash
# Complete development setup
make setup

# Run all tests
make test

# Code formatting/linting happens automatically on commit via pre-commit hooks
git commit -m "your changes"  # Automatically formats and checks code
```

### Testing Options

```bash
# Run all tests
python run_tests.py

# Run specific test categories
python run_tests.py database    # Database operations
python run_tests.py export      # Export functionality
python run_tests.py cli         # Command-line interface

# Run with coverage reporting
python run_tests.py --coverage

# Using pytest directly
pytest                          # All tests
pytest tests/test_database_operations.py  # Specific test file
```

### Code Quality

Code quality is handled automatically by pre-commit hooks:

- **Formatting** (black, isort) - runs on every commit
- **Linting** (flake8, mypy) - prevents bad commits
- **Security** (bandit) - scans for vulnerabilities
- **Documentation** (pydocstyle) - enforces docstring standards

Manual quality checks (if needed):

```bash
# Run all pre-commit checks manually
poetry run pre-commit run --all-files

# Individual tools
poetry run black .      # Format code
poetry run flake8 .     # Lint code
poetry run mypy ibirecovery/  # Type check
```

**Test Coverage:**

- Database operations and querying (✅ 95%+ coverage)
- File verification and extraction (✅ 90%+ coverage)
- Export functionality for all 12 formats (✅ 85%+ coverage)
- CLI interface and argument parsing (✅ 80%+ coverage)
- Reference implementation API (✅ 90%+ coverage)

See [tests/README.md](tests/README.md) for detailed testing documentation.

## 🤝 Contributing

This is a community resource released under GPLv3:

- ✅ Use freely with source code sharing
- ✅ Build recovery services (must open source improvements)
- ✅ Academic research
- ✅ Extend the tools (contributions must be GPLv3)

**Development Setup:**

```bash
# Install dependencies and setup pre-commit hooks
make setup

# Make changes and test
make test

# All commits automatically formatted and checked
git commit -m "your changes"
```

**Ways to contribute:**

- Share schema variations from different ibi versions
- Improve export format compatibility
- Add support for additional photo software
- Extend the reference implementation
- Improve test coverage and add test cases
- Enhance documentation and examples

## 📜 License

**SPDX-License-Identifier: GPL-3.0-or-later**

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

The goal is to help families recover their precious photos and advance the data recovery community's capabilities.

## 🆘 Support

- **Documentation**: See [docs/](docs/) for complete technical details
- **Developer Guide**: [developer_guide.md](docs/developer_guide.md) for building custom tools
- **Reference API**: [reference_implementation.py](docs/reference_implementation.py) for clean parser code
- **Issues**: [GitHub Issues](https://github.com/alandtse/ibiRecovery/issues) for bugs or feature requests
- **Repository**: [github.com/alandtse/ibiRecovery](https://github.com/alandtse/ibiRecovery)

## 🏃‍♂️ Quick Commands Reference

```bash
# Quick verification (sample of 100 files)
poetry run ibi-extract --verify /path/to/ibi_root

# Comprehensive audit (all files)
poetry run ibi-extract --verify --verify-sample 0 /path/to/ibi_root

# Comprehensive audit with detailed reports
poetry run ibi-extract --verify --verify-sample 0 --audit-report ./audit_output /path/to/ibi_root

# Verify metadata completeness (requires pillow)
poetry run ibi-extract --verify-metadata /path/to/ibi_root

# List all available export formats
poetry run ibi-extract --list-formats

# Extract files with albums + export metadata
poetry run ibi-extract /path/to/ibi_root ./output --export

# Export specific formats only
poetry run ibi-extract --export --export-formats lightroom_csv plex_csv /path/to/ibi_root
```

> **💡 Tip**: Create a `data/` directory for your personal recovery work - it's automatically ignored by git to keep your private files safe.

---

_This toolkit transforms ibi data recovery from "just getting files back" to "complete photo library reconstruction" with organization, metadata, and universal software compatibility._
