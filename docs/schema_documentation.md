# ibi Database Schema Documentation

## Overview

This document provides complete schema documentation for ibi device databases recovered from data recovery operations. This information enables others to create parsers, recovery tools, and analysis scripts for ibi data.

## Database Information

- **Database Type**: SQLite 3
- **Location**: `/restsdk/data/db/index.db`
- **Backup Location**: `/restsdk/data/dbBackup/index.db`
- **Device Info DB**: `/restsdk-info/data/db/index.db`

## File Storage System

### Physical Storage Structures

#### Traditional Storage (Pre-2020)

```
/restsdk/data/files/
├── a/               # Files with contentID starting with 'a'
│   ├── aB1C2D3E...  # Actual file (contentID as filename)
│   └── aF4G5H6I...
├── b/               # Files with contentID starting with 'b'
├── ...
└── z/
```

#### UserStorage Structure (Post-2020)

```
/userStorage/
├── auth0|user1_id/          # User-specific directories
│   ├── Album Name/          # Organized by album/backup folders
│   │   ├── photo1.jpg
│   │   └── video1.mp4
│   └── Another Album/
└── auth0|user2_id/
    └── Camera Backup/
        └── IMG_12345.jpg
```

### Storage Resolution Formula

#### Traditional Files (storageID = "local" or NULL)

- **File Path**: `/files/{contentID[0]}/{contentID}`
- **Example**: contentID `jT9JduP8vIHpwuY32gLQ` → `/files/j/jT9JduP8vIHpwuY32gLQ`

#### UserStorage Files (storageID from Filesystems table)

- **File Path**: `/userStorage/{userID}/{albumPath}/{filename}`
- **Resolution**: Query Filesystems table for path mapping, search recursively in subdirectories
- **Example**: `auth0|5aa6ecdb83fef129ce546335/Google Pixel 2 Camera Backup/IMG_20150613_175329.jpg`

## Security and Encryption

### File Encryption Status

**Files are NOT encrypted** - they are stored in plaintext format:

- **Evidence**: File headers intact (JPEG files start with `FFD8FF`, MP4 files contain `ftyp`)
- **Hash Fields**: `contentHash` field used for integrity verification, not encryption
- **Direct Access**: Files can be opened and read normally without decryption
- **Recovery Impact**: Direct file copying works without additional decryption steps

### Multi-User Support

**Automatic multi-user recovery** supported for unlimited users:

- **User Discovery**: Automatic via `Filesystems` table queries
- **Path Resolution**: Dual-strategy approach handles both storage types
- **Scalability**: Works regardless of number of users on device
- **No Configuration**: Zero manual setup required for multi-user devices

## Core Tables Schema

### Files Table (Primary Content)

```sql
CREATE TABLE Files(
    id TEXT NOT NULL PRIMARY KEY,                    -- Unique file identifier
    parentID TEXT REFERENCES Files(id),              -- Directory structure
    contentID TEXT UNIQUE,                           -- Maps to physical file storage
    version INTEGER NOT NULL,                        -- File version number
    name TEXT NOT NULL,                              -- Original filename
    birthTime INTEGER NOT NULL,                      -- Creation time (ms since epoch)
    cTime INTEGER NOT NULL,                          -- Data creation time
    uTime INTEGER,                                   -- Update time
    mTime INTEGER,                                   -- Data modification time
    size INTEGER NOT NULL DEFAULT 0,                 -- File size in bytes
    mimeType TEXT NOT NULL DEFAULT '',               -- MIME type
    storageID TEXT NOT NULL,                         -- Storage backend ('local' or userStorage ID)
    hidden INTEGER NOT NULL DEFAULT 1,               -- Visibility flag
    description TEXT NOT NULL DEFAULT '',            -- User description
    custom TEXT NOT NULL DEFAULT '',                 -- Internal hash/tracking
    creatorEntityID TEXT REFERENCES Entities(id),   -- User who created file

    -- Image metadata
    imageDate INTEGER,                               -- Image capture date (ms)
    imageWidth INTEGER NOT NULL DEFAULT 0,
    imageHeight INTEGER NOT NULL DEFAULT 0,
    imageCameraMake TEXT NOT NULL DEFAULT '',
    imageCameraModel TEXT NOT NULL DEFAULT '',
    imageAperture REAL NOT NULL DEFAULT 0,
    imageExposureTime REAL NOT NULL DEFAULT 0,
    imageISOSpeed INTEGER NOT NULL DEFAULT 0,
    imageFocalLength REAL NOT NULL DEFAULT 0,
    imageFlashFired INTEGER,
    imageOrientation INTEGER NOT NULL DEFAULT 0,
    imageLatitude REAL,                              -- GPS coordinates
    imageLongitude REAL,
    imageAltitude REAL,
    imageCity TEXT NOT NULL DEFAULT '',              -- Location names
    imageProvince TEXT NOT NULL DEFAULT '',
    imageCountry TEXT NOT NULL DEFAULT '',

    -- Video metadata
    videoDate INTEGER,                               -- Video capture date (ms)
    videoCodec TEXT NOT NULL DEFAULT '',
    videoWidth INTEGER NOT NULL DEFAULT 0,
    videoHeight INTEGER NOT NULL DEFAULT 0,
    videoDuration REAL NOT NULL DEFAULT 0,           -- Duration in seconds
    videoOrientation INTEGER NOT NULL DEFAULT 0,
    videoLatitude REAL,                              -- GPS coordinates
    videoLongitude REAL,
    videoAltitude REAL,
    videoCity TEXT NOT NULL DEFAULT '',              -- Location names
    videoProvince TEXT NOT NULL DEFAULT '',
    videoCountry TEXT NOT NULL DEFAULT '',

    -- Audio metadata
    audioDuration REAL NOT NULL DEFAULT 0,
    audioTitle TEXT NOT NULL DEFAULT '',
    audioAlbum TEXT NOT NULL DEFAULT '',
    audioArtist TEXT NOT NULL DEFAULT '',

    -- Additional fields...
    category INTEGER,                                -- File categorization
    month INTEGER NOT NULL DEFAULT 0,               -- Time grouping
    week INTEGER NOT NULL DEFAULT 0
);
```

#### Directory Metadata Entries

**Important**: The Files table contains organizational metadata entries with `mimeType: 'application/x.wd.dir'` that represent directory structure rather than actual extractable files.

**Types of Directory Entries**:

- **User Account Boundaries**: Format `auth0|{userID}` representing individual users in multi-user systems
- **Device Groupings**: Names like `Samsung SM-G960U Camera Backup`, `iPhone Camera Roll Backup` for device-specific uploads  
- **System Containers**: `Trash` for deleted items, empty entries for organizational placeholders

**Database Analysis Example**:
```sql
SELECT name, mimeType, contentID FROM Files WHERE mimeType = 'application/x.wd.dir';
```

Typical results (8 directory entries out of 9,434 total):
- `Trash` (system container)
- `auth0|5aa6ecdb83fef129ce546335` → maps to 613 actual files
- `auth0|5bb3b9d2f4cee6307c85560e` → maps to 8,813 actual files
- `Samsung SM-G960U Camera Backup` (device grouping)
- `Google Pixel 2 Camera Backup` (device grouping)

**Extraction Behavior**: Recovery tools should filter these entries using:
```sql
WHERE f.contentID IS NOT NULL AND f.contentID != '' AND f.mimeType != 'application/x.wd.dir'
```

This prevents confusing "Source file not found" warnings for organizational metadata that has no corresponding physical files.

### Filesystems Table (UserStorage Mappings)

```sql
CREATE TABLE Filesystems(
    id TEXT NOT NULL PRIMARY KEY,                   -- Storage identifier (matches Files.storageID)
    name TEXT NOT NULL,                             -- User identifier (e.g., auth0|user_id)
    path TEXT NOT NULL,                             -- Original mount path in device
    -- Example: /data/wd/diskVolume0/userStorage/auth0|5aa6ecdb83fef129ce546335
    cTime INTEGER NOT NULL,                         -- Creation time (ms)
    mTime INTEGER                                   -- Modification time (ms)
);
```

**Purpose**: Maps storageID values to user directories in userStorage structure

- **User Resolution**: `name` field contains Auth0 user identifier
- **Path Mapping**: `path` field shows original device mount location
- **Recovery Usage**: Used to locate files in `/userStorage/{name}/` directory structure

### FileGroups Table (Albums/Collections)

```sql
CREATE TABLE FileGroups(
    id TEXT NOT NULL PRIMARY KEY,                   -- Unique album identifier
    name TEXT NOT NULL,                             -- Album name
    previewFileID TEXT REFERENCES Files(id),       -- Preview/cover image
    cTime INTEGER NOT NULL,                         -- Creation time (ms)
    mTime INTEGER,                                  -- Modification time (ms)
    description TEXT NOT NULL DEFAULT '',          -- Album description
    estCount INTEGER NOT NULL DEFAULT 0,           -- Estimated file count
    estMinTime INTEGER,                             -- Earliest content time
    estMaxTime INTEGER,                             -- Latest content time
    creatorEntityID TEXT REFERENCES Entities(id),  -- Album creator
    post INTEGER NOT NULL DEFAULT 0,               -- Post/sharing flag
    commentsCount INTEGER NOT NULL DEFAULT 0       -- Number of comments
);
```

### FileGroupFiles Table (Many-to-Many Relationship)

```sql
CREATE TABLE FileGroupFiles(
    id TEXT NOT NULL PRIMARY KEY,                   -- Unique relationship ID
    fileID TEXT NOT NULL REFERENCES Files(id),     -- File reference
    fileGroupID TEXT NOT NULL REFERENCES FileGroups(id), -- Album reference
    fileCTime INTEGER NOT NULL,                     -- File creation time for sorting
    cTime INTEGER NOT NULL,                         -- Relationship creation time
    changeID INTEGER NOT NULL DEFAULT 0,           -- Change tracking
    creatorEntityID TEXT REFERENCES Entities(id),  -- Who added file to album
    commentsCount INTEGER NOT NULL DEFAULT 0       -- Comments on this relationship
);
```

### FilesTags Table (AI-Generated Content Tags)

```sql
CREATE TABLE FilesTags(
    fileID TEXT NOT NULL REFERENCES Files(id),     -- File reference
    tag TEXT NOT NULL,                             -- Content tag (e.g., "person", "beach")
    auto INTEGER NOT NULL                          -- 1 = AI-generated, 0 = manual
);
```

### Entities Table (Users/Devices)

```sql
CREATE TABLE Entities(
    id TEXT NOT NULL PRIMARY KEY,                   -- Internal entity ID
    extID TEXT NOT NULL,                           -- External ID (auth0, device UUID)
    type INTEGER NOT NULL,                         -- 1=user, 2=device, 4=other
    rootID TEXT REFERENCES Files(id),             -- Root directory
    cTime INTEGER NOT NULL,                        -- Creation time
    version INTEGER NOT NULL,                      -- Version number
    timeZoneName TEXT NOT NULL DEFAULT '',        -- IANA timezone (e.g., "America/Los_Angeles")
    lang TEXT NOT NULL DEFAULT ''                 -- Language code (e.g., "en-US")
);
```

## Metadata Categories

### ✅ Portable/Useful Data

- **AI Content Tags**: Computer vision analysis (5,312+ instances)
- **Album Organization**: User-created collections with meaningful names
- **GPS/Location Data**: Coordinates and place names from original photos
- **Camera EXIF**: Standard technical metadata (make, model, settings)
- **Original Timestamps**: Capture dates and times

### ❌ ibi Ecosystem-Specific (Not Portable)

- **User Authentication**: auth0 IDs, client credentials
- **Sharing System**: SharedFiles table with cloud sharing IDs
- **Permission System**: FilePerms, FileGroupPerms tables
- **Internal Tracking**: Custom hashes, version control
- **Device Management**: Internal device registration

## Common Queries

### Get All Files with Basic Info

```sql
SELECT f.id, f.name, f.contentID, f.mimeType, f.size,
       f.imageDate, f.videoDate, f.cTime
FROM Files f
WHERE f.contentID IS NOT NULL AND f.contentID != ''
ORDER BY COALESCE(f.videoDate, f.imageDate, f.cTime);
```

### Get Files with AI Tags

```sql
SELECT f.name, ft.tag
FROM Files f
JOIN FilesTags ft ON f.id = ft.fileID
WHERE ft.auto = 1
ORDER BY f.name, ft.tag;
```

### Get Album Contents

```sql
SELECT fg.name AS album_name, f.name AS filename
FROM FileGroups fg
JOIN FileGroupFiles fgf ON fg.id = fgf.fileGroupID
JOIN Files f ON fgf.fileID = f.id
ORDER BY fg.name, fgf.fileCTime;
```

### Get Files with GPS Data

```sql
SELECT f.name, f.imageLatitude, f.imageLongitude,
       f.imageCity, f.imageCountry
FROM Files f
WHERE f.imageLatitude IS NOT NULL
   AND f.imageLongitude IS NOT NULL;
```

## Statistics (Typical Dataset)

- **Total Files**: 8,500+ files
- **Images**: ~6,700 (JPEG, PNG, HEIC, GIF)
- **Videos**: ~1,800 (MP4, QuickTime)
- **Albums**: ~50 user-created collections
- **AI Tags**: 5,300+ content recognition instances
- **GPS-tagged Files**: Variable (depends on camera settings)

## File Recovery Process

1. **Database Connection**: Open `/restsdk/data/db/index.db`
2. **File Mapping**: Use `contentID` to locate physical files
3. **Metadata Extraction**: Join Files, FilesTags, FileGroups tables
4. **File Retrieval**: Copy from `/files/{contentID[0]}/{contentID}`

## Version Information

This schema documentation is based on analysis of recovered ibi databases with the following identified characteristics:

### Database Version Identifiers

- **SQLite Schema Version**: 300 (PRAGMA schema_version)
- **ibi Internal Version**: "166" (from Info.version field)
- **Total Tables**: 37 tables in main database
- **Database Type**: SQLite 3.x with row_factory support

### Feature Set Detected

- **AI Content Tagging**: Computer vision analysis (5,312+ tag instances)
- **Album Organization**: User-created collections with metadata
- **GPS Integration**: Coordinate and location name storage
- **Multi-format Support**: Images, videos, audio with technical metadata
- **File Versioning**: Internal change tracking system
- **User Management**: Multi-user/device support (30 entities)

### Time Period

- **Data Range**: 2017-2023 based on file timestamps
- **Peak Activity**: Heavy usage 2018-2020 timeframe
- **Latest Activity**: Files dated up to 2023

### Hardware/Platform Indicators

- **Storage Backend**: Dual-mode (Traditional "local" + UserStorage filesystems)
- **Timezone Data**: America/Los_Angeles primary, UTC secondary
- **Language**: en-US primary locale
- **Device Types**: Mix of user accounts (type=1) and devices (type=2)

**Note**: This represents ibi software that was in use during 2017-2023 with database schema version 166. Different ibi versions may have different schemas, but this documentation covers the format found in typical consumer ibi devices from this era.

## Complete Table List

Core tables: `Files`, `FileGroups`, `FileGroupFiles`, `FilesTags`, `Entities`

Supporting tables: `CategoriesStats`, `Changes`, `Comments`, `DevicePerms`, `ExtraContents`, `FilesKeywords`, `Filesystems`, `Info`, `MediaTimeGroups`, `Reactions`, `Settings`, `SharedFiles`, `Volumes`

ibi-specific: `CloudFilesystems`, `CloudFilesystemFiles`, `DeletedContent`, `FilePerms`, `FileGroupPerms`, `ResumableFiles`, `PendingFilePermUpdates`

Search/indexing: `FilesFTS`, `FilesFTS_*` (Full-text search tables)

## Usage License

This schema documentation is released under CC0 (Public Domain) to benefit the data recovery community. Use freely for:

- Creating recovery tools
- Building parsers for ibi data
- Academic research on photo management systems
- Helping users recover their family photos

## Contributing

If you discover additional schema details, variations, or corrections, please contribute back to help others in the data recovery community.
