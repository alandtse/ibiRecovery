# Metadata Embedding Guide

This guide analyzes what metadata from ibi databases can be embedded back into files versus what requires external software support.

## 📷 Images (JPEG, PNG, HEIC, etc.)

### ✅ **Embeddable Metadata**

**EXIF Data**
- **Standard**: EXIF  
- **Fields**: Camera Make/Model, Aperture, Exposure Time, ISO Speed, Focal Length, Flash Fired, Image Width/Height, Orientation, Date/Time Original
- **Support**: Universal - all photo software reads EXIF

**GPS Data**
- **Standard**: EXIF GPS tags
- **Fields**: Latitude, Longitude, Altitude  
- **Support**: Universal - Google Photos, Apple Photos, etc.

**Keywords/Tags**
- **Standard**: IPTC Keywords or XMP Subject
- **Fields**: AI-generated content tags
- **Support**: Most photo management software (Lightroom, Photos, etc.)

**Description**
- **Standard**: EXIF ImageDescription or IPTC Caption
- **Fields**: File description from database
- **Support**: Universal

### ❌ **Requires External Software**

**Album Associations**
- **Issue**: Not part of EXIF/IPTC standards
- **Solutions**: XMP sidecar files, Photo management software databases

**User Reactions/Likes** 
- **Issue**: No standard metadata field
- **Solutions**: Custom XMP tags, External database

**File Relationships**
- **Issue**: EXIF doesn't support relationships
- **Solutions**: Folder organization, Catalog software

**Version History**
- **Issue**: Not supported in image metadata
- **Solutions**: External versioning system

## 🎥 Videos (MP4, MOV, etc.)

### ✅ **Embeddable Metadata**

**Basic Metadata**
- **Standard**: QuickTime/MP4 metadata atoms
- **Fields**: Creation Date, Duration, Width/Height, Codec
- **Support**: Universal

**GPS Data**
- **Standard**: QuickTime GPS atoms
- **Fields**: Latitude, Longitude, Altitude
- **Support**: Most video players and editors

**Technical Data**
- **Standard**: Container metadata
- **Fields**: Bitrate, Framerate, Audio codec
- **Support**: Universal

### ⚠️ **Limited Support**

**Keywords/Tags**
- **Support**: Limited - some video editors support XMP
- **Note**: Not as universal as image tags

**Album/Collection Data**
- **Support**: Very limited
- **Note**: Most video software doesn't support collections in metadata

## Common Metadata Export Formats

### 📄 Adobe XMP Sidecar (.xmp)
- **Description**: XML-based metadata standard
- **Supports**: Keywords, GPS, Descriptions, Custom fields, Ratings
- **Software**: Adobe Lightroom, Adobe Bridge, darktable, digiKam
- **Pros**: Universal, Human readable, Preserves all data
- **Cons**: Separate files to manage

### 📄 IPTC/EXIF Embedding
- **Description**: Direct embedding in image files
- **Supports**: Keywords, GPS, Camera data, Descriptions
- **Software**: All photo management software
- **Pros**: Self-contained, Universal support
- **Cons**: Limited field types, May not support all AI tags

### 📄 CSV/Excel Export
- **Description**: Spreadsheet format for analysis
- **Supports**: All metadata fields, Relationships, Statistics
- **Software**: Excel, Google Sheets, Any spreadsheet app
- **Pros**: Easy analysis, Importable to databases
- **Cons**: Not linked to files, Manual process

### 📄 Photo Management Catalogs
- **Description**: Import into existing photo software
- **Supports**: All metadata, Albums, Collections, Relationships
- **Software**: Lightroom, Capture One, digiKam, Photo Mechanic
- **Pros**: Full integration, Searchable, Maintains relationships
- **Cons**: Software-specific, May need conversion

### 📄 Dublin Core XML
- **Description**: Library science metadata standard
- **Supports**: Descriptions, Subjects, Creators, Dates
- **Software**: Digital asset management systems
- **Pros**: Standards-based, Archival quality
- **Cons**: Limited photo-specific fields

## Recommended Workflows

### 🏠 Home User - Simple Organization
- **Goal**: Get photos back with basic organization
- **Metadata Strategy**: Basic EXIF/GPS embedding + folder organization
- **Steps**:
  1. Use `ibi-extract` to organize by original albums
  2. Embed GPS and basic EXIF data back into files
  3. Export to simple CSV format for basic metadata
  4. Import into Apple Photos/Google Photos

### 📸 Photography Enthusiast  
- **Goal**: Preserve all metadata for advanced management
- **Metadata Strategy**: Full EXIF/XMP embedding + sidecar files
- **Steps**:
  1. Use `ibi-extract --export` for complete extraction
  2. Generate XMP sidecar files with all AI tags
  3. Embed GPS, camera, and keyword data in files
  4. Import into Lightroom/Capture One with XMP files

### 🏛️ Archival/Professional
- **Goal**: Long-term preservation with full metadata
- **Metadata Strategy**: Standards-based metadata + original database preservation
- **Steps**:
  1. Extract with complete metadata preservation
  2. Export to IPTC-compliant formats
  3. Generate CSV catalogs for database import
  4. Maintain original database alongside files
  5. Use digital asset management system

### 🔍 Research/Analysis
- **Goal**: Searchable collection for content analysis
- **Metadata Strategy**: Database-driven with web search interface
- **Steps**:
  1. Extract all metadata to JSON format
  2. Import into database (SQLite/PostgreSQL)
  3. Create web interface for searching
  4. Link files via file paths in database

## Implementation Notes

The ibiRecovery toolkit provides 12 export formats covering all these workflows:
- **Universal formats**: ExifTool CSV, JSON metadata, XMP sidecars
- **Photo management**: Lightroom CSV, PhotoPrism, Apple Photos, digiKam
- **Video management**: Jellyfin NFO, Plex CSV, IPTC Video
- **Professional**: IPTC-compliant CSV, Google Takeout JSON

Use `ibi-extract --list-formats` to see all available options.