# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ibiRecovery is a comprehensive toolkit for recovering photos, videos, and metadata from discontinued SanDisk ibi device databases. The project extracts files while preserving AI-generated content tags, user album organization, GPS/EXIF metadata, and provides export capabilities to 12+ popular photo management software formats.

## Development Commands

### Setup

```bash
make setup                    # Complete development setup (poetry install + pre-commit hooks)
poetry install --with dev --extras metadata  # Manual dependency installation
```

### Testing

```bash
make test                     # Run all tests
make test-cov                 # Run tests with coverage reporting
python run_tests.py          # Run all tests (alternative)
python run_tests.py database # Run database operation tests only
python run_tests.py export   # Run export functionality tests only
python run_tests.py cli      # Run CLI interface tests only
python run_tests.py --coverage # Run with coverage reporting

# Run specific test files
pytest tests/test_database_operations.py
pytest tests/test_export_functionality.py -v
pytest -m "unit"             # Run only unit tests
pytest -m "integration"      # Run integration tests
pytest -m "slow"             # Run slow tests
```

### Running the Main Tool

```bash
# Using poetry (recommended during development)
poetry run ibi-extract --verify /path/to/ibi_root
poetry run ibi-extract /path/to/ibi_root ./output --export

# Direct script execution
python -m ibirecovery.extract_files --verify /path/to/ibi_root
python ibirecovery/extract_files.py /path/to/ibi_root ./output
```

### Code Quality

Pre-commit hooks handle formatting automatically, but manual commands:

```bash
poetry run black .           # Format code
poetry run isort .           # Sort imports
poetry run flake8 .          # Lint (currently disabled due to existing code)
poetry run mypy ibirecovery/ # Type checking (currently disabled)
```

## Architecture

### Core Components

**Main Extraction Tool** (`ibirecovery/extract_files.py`):

- Single 2200+ line file containing the complete extraction workflow
- Handles auto-detection of ibi directory structure
- Provides progress tracking, resumable operations, metadata correction
- Contains all export format generation logic
- Supports both album-based and type-based extraction modes

**Reference Implementation** (`docs/reference_implementation.py`):

- Clean, documented API for building custom tools
- Provides `IbiDatabaseParser` class with simple methods
- Separate from the main tool for developer clarity
- Used by tests and as documentation example

**Export System** (`export_formats.json`):

- Declarative configuration for 12+ export formats
- Supports CSV, JSON, XML, and NFO output types
- Configurable field mappings and data transformations
- Used by both main tool and reference implementation

### Data Flow Architecture

1. **Database Access**: SQLite database at `/restsdk/data/db/index.db` contains all metadata
2. **File Storage**: Physical files stored in `/restsdk/data/files/{first_char}/{content_id}`
3. **Extraction Modes**:
   - Album-based: Preserves user organization structure
   - Type-based: Groups by file type (images/videos/documents)
   - Always includes orphaned files not in albums
4. **Metadata Pipeline**: Database → Python objects → Export format transformations

### Database Schema

- 37 documented tables with relationships
- Key tables: Files, FileGroups (albums), FilesTags, FilesMetadata
- Schema version 166, SQLite format 300
- Contains AI-generated tags, GPS data, camera metadata, user albums

### Test Architecture

- **Unit Tests**: Fast, isolated tests for individual functions
- **Integration Tests**: End-to-end workflows with sample data
- **CLI Tests**: Command-line interface validation
- **Cross-platform Tests**: Unicode handling, path limits, permissions
- **Export Tests**: All 12 export formats validated
- Test markers: `unit`, `integration`, `cli`, `database`, `export`, `slow`, `requires_pillow`

## Key Implementation Details

### File Deduplication System

The tool implements space-saving deduplication using hardlinks (or symlinks as fallback):

- Detects identical files by content signature during extraction
- Creates hardlinks to save disk space while preserving access
- Includes post-processing function to deduplicate existing extractions
- Python 3.9 compatibility: uses `os.link()` instead of `Path.hardlink_to()`

### Metadata Correction Pipeline

File timestamps are corrected during extraction with priority order:

1. `imageDate`/`videoDate` (highest priority - camera capture time)
2. `cTime` (creation time)
3. `birthTime` (file birth time)
   Uses `os.utime()` to set both access and modification times.

### Progress Tracking

Dual-mode progress system:

- `tqdm` library when available (rich progress bars)
- Fallback custom implementation with ETA calculation
- Handles large datasets (8500+ files) with rate limiting

### Export Format System

Declarative format configuration supports:

- **Field Mapping**: Database fields → export columns
- **Data Transformations**: Date formatting, GPS coordinates, tag joining
- **Multiple Output Types**: CSV (various delimiters), JSON, XML, NFO
- **Software-Specific**: Lightroom, digiKam, Apple Photos, Plex, Jellyfin, etc.

## Development Considerations

### Optional Dependencies

Handle optional features gracefully:

- `pillow`: Required for `--verify-metadata` flag
- `exifread`: Used for EXIF data extraction
- `tqdm`: Enhanced progress bars (fallback implementation included)

### Git Data Protection

The `data/` directory is gitignored to prevent accidental commit of personal recovery data. Multiple layers of protection:

- Directory pattern: `data`
- File patterns: `*.json`, `*.db`, `*.sqlite*`
- Specific patterns: `complete_audit.json`, `query.sql`, `analysis.md`

### Cross-Platform Compatibility

- Handles Unicode filenames correctly
- Windows long path support considerations
- File permission handling across operating systems
- Rsync with shutil fallback for file operations

### Performance Considerations

- Database queries are optimized for large datasets
- File operations use rsync when available for efficiency
- Memory-conscious processing of large file collections
- Progress tracking with minimal overhead

## Testing Strategy

Tests are organized by functionality with comprehensive coverage:

- **Database Operations**: Query validation, schema compatibility
- **File Operations**: Extraction, verification, deduplication
- **Export Functionality**: All 12 formats with sample data validation
- **CLI Interface**: Argument parsing, help text, error handling
- **Cross-Platform**: Unicode handling, long paths, permissions
- **Integration**: End-to-end workflows with realistic scenarios

Run specific test categories during development to focus on areas of change.
