# ibi Database Recovery Tools & Documentation

[![License: GPL v3](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://alandtse.github.io/ibiRecovery/)

Complete toolkit for recovering photos, videos, and metadata from ibi device databases. Includes full schema documentation, recovery tools, and export utilities for popular photo management software.

**⚠️ Critical**: SanDisk ibi support officially ended August 31, 2024. Remote access no longer works and devices will lose functionality over time. This toolkit helps families recover their precious photos before data becomes permanently inaccessible.

## 🎯 What This Recovers

- ✅ **8,500+ files** with 99-100% recovery rate
- ✅ **5,312+ AI content tags** (automatic "person", "child", "beach" categorization)
- ✅ **50+ family albums** with meaningful names ("Lily's graduation", "Hawaii 2018")
- ✅ **Complete GPS/location data** from geotagged photos
- ✅ **Full camera EXIF metadata** (make, model, settings)
- ✅ **Export to any photo software** (Lightroom, Apple Photos, digiKam, etc.)

## ⚠️ Why This Project Exists

**SanDisk ibi End of Life**: On August 31, 2024, Western Digital [officially ended support](https://support-en.wd.com/app/answers/detailweb/a_id/51848) for all ibi devices. As stated by WD: *"WD is focused on providing exceptional customer experiences with our products. With that focus, from time to time we retire legacy products."*

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

#### Using Scripts Directly
```bash
# 1. Verify what can be recovered
python tools/extract_files.py --verify /path/to/ibi_root

# 2. Export metadata for your photo software
python tools/extract_files.py --export /path/to/ibi_root

# 3. Extract organized by albums with orphaned files (recommended)
python tools/extract_files.py /path/to/ibi_root ./my_recovered_photos

# 4. Extract files + export metadata in one command
python tools/extract_files.py /path/to/ibi_root ./output --export
```

### For Developers (Build Recovery Tools)

```python
from community.reference_implementation import IbiDatabaseParser

parser = IbiDatabaseParser('index.db', 'files/')
parser.connect()

# Get all files with metadata
files = parser.get_all_files()

# Get AI content tags
tags = parser.get_content_tags_summary()

# Verify recovery rate
recovery = parser.verify_file_recovery_rate()
```

## 📁 Repository Structure

```
ibiRecovery/
├── docs/                           # Complete schema documentation
│   ├── schema_documentation.md     # Full database schema
│   ├── api_specification.json      # Machine-readable API spec
│   └── metadata_strategy.md        # Best practices guide
├── community/                      # Community resources
│   ├── COMMUNITY_SHARING.md        # How to use/contribute
│   └── reference_implementation.py # Clean parser implementation
├── tools/                          # Recovery & export tools
│   ├── extract_files.py           # Main tool: extract + verify + export + progress + resume
│   ├── audit_files.py             # Comprehensive file auditing
│   └── verify_existing_metadata.py # Check existing metadata in files
├── examples/                       # Usage examples
└── personal_analysis/             # Personal analysis (not shared)
```

## 📖 Documentation

- **[ibi Discontinuation Details](docs/ibi_discontinuation.md)** - Official timeline and impact analysis
- **[Complete Schema Documentation](docs/schema_documentation.md)** - Full database structure
- **[Community Guide](community/COMMUNITY_SHARING.md)** - For developers and researchers
- **[Metadata Strategy](docs/metadata_strategy.md)** - What to preserve vs. what to filter
- **[API Specification](docs/api_specification.json)** - Machine-readable format spec
- **[Disk Analysis Methodology](docs/disk_analysis_methodology.md)** - Technical recovery process

## 🛠️ Available Tools

### Main Tool

- **`extract_files.py`** - Complete solution with extraction, verification, metadata export, progress bars, and resume capability

### Utility Tools

- **`audit_files.py`** - Comprehensive file auditing and verification  
- **`verify_existing_metadata.py`** - Check what metadata is already in files (requires pillow)

## 📊 What Makes This Special

### Complete Recovery Beyond Just Files

Most data recovery tools just extract files. This toolkit recovers:

- **Organized photo libraries** with original album structure
- **Searchable content** via 5,312+ AI-generated tags
- **Geographic context** through GPS and location data
- **Technical metadata** for photo management software

### Universal Compatibility

Export metadata to any photo management software:

- Adobe Lightroom (Keywords CSV)
- digiKam (Hierarchical metadata)
- Apple Photos (Simple format)
- XMP Sidecar files (Universal standard)

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

## 🤝 Contributing

This is a community resource released under GPLv3:

- ✅ Use freely with source code sharing
- ✅ Build recovery services (must open source improvements)
- ✅ Academic research
- ✅ Extend the tools (contributions must be GPLv3)

**Ways to contribute:**

- Share schema variations from different ibi versions
- Improve export format compatibility
- Add support for additional photo software
- Extend the reference implementation

## 📜 License

**SPDX-License-Identifier: GPL-3.0-or-later**

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

The goal is to help families recover their precious photos and advance the data recovery community's capabilities.

## 🆘 Support

- **Documentation**: See [docs/](docs/) for complete technical details  
- **Community**: [COMMUNITY_SHARING.md](community/COMMUNITY_SHARING.md) for developers
- **Issues**: [GitHub Issues](https://github.com/alandtse/ibiRecovery/issues) for bugs or feature requests
- **Examples**: Check [examples/](examples/) for usage patterns
- **Repository**: [github.com/alandtse/ibiRecovery](https://github.com/alandtse/ibiRecovery)

---

_This toolkit transforms ibi data recovery from "just getting files back" to "complete photo library reconstruction" with organization, metadata, and universal software compatibility._
