# ibi Database Recovery Documentation

Welcome to the complete documentation for ibi database recovery tools and schema analysis.

## Documentation Overview

### 📖 Schema & API Documentation
- **[ibi Discontinuation Details](ibi_discontinuation.md)** - Official end-of-life timeline and impact
- **[Complete Schema Documentation](schema_documentation.md)** - Full database structure with all 37 tables
- **[API Specification](api_specification.json)** - Machine-readable format for tool development
- **[Metadata Strategy](metadata_strategy.md)** - What to preserve vs. what to filter out

### 🛠️ Analysis Documents  
- **[Developer Guide](developer_guide.md)** - How to build custom recovery tools
- **[Metadata Summary](metadata_summary.md)** - Overview of available metadata types
- **[Metadata Embedding Guide](metadata_embedding_guide.md)** - Technical implementation workflows
- **[Disk Analysis Methodology](disk_analysis_methodology.md)** - Technical recovery process

## Quick Reference

### Database Version Information
- **Schema Version**: 166 (ibi internal version)
- **SQLite Version**: 3.x (PRAGMA schema_version: 300)
- **Total Tables**: 37 in main database
- **Time Period**: 2017-2023 data compatibility

### Core Statistics
- **Files**: 8,500+ typical dataset
- **AI Tags**: 5,312+ content recognition instances  
- **Albums**: 40-60 user-created collections
- **Recovery Rate**: 99-100% verified

### File Storage Formula
```
Physical file path = /files/{contentID[0]}/{contentID}
Example: contentID "jT9JduP8vIHpwuY32gLQ" → /files/j/jT9JduP8vIHpwuY32gLQ
```

## Key Tables Schema

### Files Table (Primary Content)
- **Primary Key**: `id` (TEXT)
- **Storage Key**: `contentID` (maps to physical files)
- **Metadata**: Complete EXIF, GPS, video, audio metadata
- **AI Integration**: Links to FilesTags for content analysis

### FileGroups Table (Albums)
- **Primary Key**: `id` (TEXT) 
- **User Data**: `name` (album names like "Jon's graduation")
- **Statistics**: `estCount`, `estMinTime`, `estMaxTime`

### FilesTags Table (AI Content Analysis)
- **Foreign Key**: `fileID` → Files.id
- **Content**: `tag` (e.g., "person", "child", "beach")
- **Type**: `auto` (1 = AI-generated, 0 = manual)

## Export Formats Supported

- **Adobe Lightroom**: Keywords CSV import
- **digiKam**: Hierarchical metadata CSV
- **Apple Photos**: Simple CSV format
- **XMP Sidecar**: Universal XML metadata
- **Photo Mechanic**: IPTC data CSV

## For Developers

Use the [reference implementation](reference_implementation.py) to get started:

```python
from docs.reference_implementation import IbiDatabaseParser

parser = IbiDatabaseParser('path/to/index.db')
parser.connect()
files = parser.get_all_files()
```

See the [Developer Guide](developer_guide.md) for detailed development information.

## Repository & Community

- **GitHub Repository**: [github.com/alandtse/ibiRecovery](https://github.com/alandtse/ibiRecovery)
- **Issues & Support**: [GitHub Issues](https://github.com/alandtse/ibiRecovery/issues)
- **Documentation**: [GitHub Pages](https://alandtse.github.io/ibiRecovery/)