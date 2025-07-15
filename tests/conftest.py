"""Pytest configuration and fixtures for ibi recovery tests."""

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_ibi_structure(temp_dir):
    """Create a mock ibi directory structure for testing."""
    ibi_root = temp_dir / "ibi_root"
    data_dir = ibi_root / "restsdk" / "data"
    db_dir = data_dir / "db"
    files_dir = data_dir / "files"

    # Create directories
    db_dir.mkdir(parents=True)
    files_dir.mkdir(parents=True)

    # Create subdirectories for files (a-f for testing)
    for subdir in ["a", "b", "c", "d", "e", "f"]:
        (files_dir / subdir).mkdir()

    return {"root": ibi_root, "data": data_dir, "db": db_dir, "files": files_dir}


@pytest.fixture
def mock_database(mock_ibi_structure):
    """Create a mock SQLite database with test data."""
    db_path = mock_ibi_structure["db"] / "index.db"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create Files table matching the real ibi database schema from documentation
    cursor.execute(
        """
        CREATE TABLE Files(
            id TEXT NOT NULL PRIMARY KEY,
            parentID TEXT REFERENCES Files(id),
            contentID TEXT UNIQUE,
            version INTEGER NOT NULL,
            name TEXT NOT NULL,
            birthTime INTEGER NOT NULL,
            cTime INTEGER NOT NULL,
            uTime INTEGER,
            mTime INTEGER,
            size INTEGER NOT NULL DEFAULT 0,
            mimeType TEXT NOT NULL DEFAULT '',
            storageID TEXT NOT NULL,
            hidden INTEGER NOT NULL DEFAULT 1,
            description TEXT NOT NULL DEFAULT '',
            custom TEXT NOT NULL DEFAULT '',
            creatorEntityID TEXT REFERENCES Entities(id),

            -- Image metadata
            imageDate INTEGER,
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
            imageLatitude REAL,
            imageLongitude REAL,
            imageAltitude REAL,
            imageCity TEXT NOT NULL DEFAULT '',
            imageProvince TEXT NOT NULL DEFAULT '',
            imageCountry TEXT NOT NULL DEFAULT '',

            -- Video metadata
            videoDate INTEGER,
            videoCodec TEXT NOT NULL DEFAULT '',
            videoWidth INTEGER NOT NULL DEFAULT 0,
            videoHeight INTEGER NOT NULL DEFAULT 0,
            videoDuration REAL NOT NULL DEFAULT 0,
            videoOrientation INTEGER NOT NULL DEFAULT 0,
            videoLatitude REAL,
            videoLongitude REAL,
            videoAltitude REAL,
            videoCity TEXT NOT NULL DEFAULT '',
            videoProvince TEXT NOT NULL DEFAULT '',
            videoCountry TEXT NOT NULL DEFAULT '',

            -- Audio metadata
            audioDuration REAL NOT NULL DEFAULT 0,
            audioTitle TEXT NOT NULL DEFAULT '',
            audioAlbum TEXT NOT NULL DEFAULT '',
            audioArtist TEXT NOT NULL DEFAULT '',

            -- Additional fields
            category INTEGER,
            month INTEGER NOT NULL DEFAULT 0,
            week INTEGER NOT NULL DEFAULT 0
        )
    """
    )

    # Create FileGroups table matching the real schema
    cursor.execute(
        """
        CREATE TABLE FileGroups(
            id TEXT NOT NULL PRIMARY KEY,
            name TEXT NOT NULL,
            previewFileID TEXT REFERENCES Files(id),
            cTime INTEGER NOT NULL,
            mTime INTEGER,
            description TEXT NOT NULL DEFAULT '',
            estCount INTEGER NOT NULL DEFAULT 0,
            estMinTime INTEGER,
            estMaxTime INTEGER,
            creatorEntityID TEXT REFERENCES Entities(id),
            post INTEGER NOT NULL DEFAULT 0,
            commentsCount INTEGER NOT NULL DEFAULT 0
        )
    """
    )

    # Create FileGroupFiles table matching the real schema
    cursor.execute(
        """
        CREATE TABLE FileGroupFiles(
            id TEXT NOT NULL PRIMARY KEY,
            fileID TEXT NOT NULL REFERENCES Files(id),
            fileGroupID TEXT NOT NULL REFERENCES FileGroups(id),
            fileCTime INTEGER NOT NULL,
            cTime INTEGER NOT NULL,
            changeID INTEGER NOT NULL DEFAULT 0,
            creatorEntityID TEXT REFERENCES Entities(id),
            commentsCount INTEGER NOT NULL DEFAULT 0
        )
    """
    )

    # Create Entities table (referenced by foreign keys)
    cursor.execute(
        """
        CREATE TABLE Entities(
            id TEXT NOT NULL PRIMARY KEY,
            extID TEXT NOT NULL,
            type INTEGER NOT NULL,
            rootID TEXT REFERENCES Files(id),
            cTime INTEGER NOT NULL,
            version INTEGER NOT NULL,
            timeZoneName TEXT NOT NULL DEFAULT '',
            lang TEXT NOT NULL DEFAULT ''
        )
    """
    )

    # Create FilesTags table (AI content tags)
    cursor.execute(
        """
        CREATE TABLE FilesTags (
            fileID TEXT,
            tag TEXT,
            auto INTEGER,
            FOREIGN KEY (fileID) REFERENCES Files(id)
        )
    """
    )

    # Insert test data matching the real schema structure
    test_files = [
        {
            "id": "file1",
            "parentID": None,
            "contentID": "a1b2c3d4e5f6",
            "version": 1,
            "name": "test1.jpg",
            "birthTime": 1640995200000,  # Convert to milliseconds
            "cTime": 1640995200000,
            "uTime": 1640995100000,
            "mTime": 1640995150000,
            "size": 1024000,
            "mimeType": "image/jpeg",
            "storageID": "local",
            "hidden": 0,
            "description": "A test image",
            "custom": "",
            "creatorEntityID": None,
            "imageDate": 1640995200000,
            "imageWidth": 1920,
            "imageHeight": 1080,
            "imageCameraMake": "Canon",
            "imageCameraModel": "EOS R5",
            "imageAperture": 2.8,
            "imageExposureTime": 0.001,
            "imageISOSpeed": 200,
            "imageFocalLength": 85.0,
            "imageFlashFired": 0,
            "imageOrientation": 1,
            "imageLatitude": 37.7749,
            "imageLongitude": -122.4194,
            "imageAltitude": None,
            "imageCity": "San Francisco",
            "imageProvince": "CA",
            "imageCountry": "USA",
            "videoDate": None,
            "videoCodec": "",
            "videoWidth": 0,
            "videoHeight": 0,
            "videoDuration": 0,
            "videoOrientation": 0,
            "videoLatitude": None,
            "videoLongitude": None,
            "videoAltitude": None,
            "videoCity": "",
            "videoProvince": "",
            "videoCountry": "",
            "audioDuration": 0,
            "audioTitle": "",
            "audioAlbum": "",
            "audioArtist": "",
            "category": 1,
            "month": 12,
            "week": 52,
        },
        {
            "id": "file2",
            "parentID": None,
            "contentID": "b2c3d4e5f6a1",
            "version": 1,
            "name": "test2.mp4",
            "birthTime": 1640995300000,
            "cTime": 1640995300000,
            "uTime": 1640995200000,
            "mTime": 1640995250000,
            "size": 5120000,
            "mimeType": "video/mp4",
            "storageID": "local",
            "hidden": 0,
            "description": "A test video",
            "custom": "",
            "creatorEntityID": None,
            "imageDate": None,
            "imageWidth": 0,
            "imageHeight": 0,
            "imageCameraMake": "",
            "imageCameraModel": "",
            "imageAperture": 0,
            "imageExposureTime": 0,
            "imageISOSpeed": 0,
            "imageFocalLength": 0,
            "imageFlashFired": None,
            "imageOrientation": 0,
            "imageLatitude": None,
            "imageLongitude": None,
            "imageAltitude": None,
            "imageCity": "",
            "imageProvince": "",
            "imageCountry": "",
            "videoDate": 1640995300000,
            "videoCodec": "h264",
            "videoWidth": 1920,
            "videoHeight": 1080,
            "videoDuration": 30.5,
            "videoOrientation": 1,
            "videoLatitude": 37.7849,
            "videoLongitude": -122.4294,
            "videoAltitude": None,
            "videoCity": "San Francisco",
            "videoProvince": "CA",
            "videoCountry": "USA",
            "audioDuration": 30.5,
            "audioTitle": "",
            "audioAlbum": "",
            "audioArtist": "",
            "category": 2,
            "month": 12,
            "week": 52,
        },
        {
            "id": "file3",
            "parentID": None,
            "contentID": "c3d4e5f6a1b2",
            "version": 1,
            "name": "test3.png",
            "birthTime": 1640995400000,
            "cTime": 1640995400000,
            "uTime": 1640995300000,
            "mTime": 1640995350000,
            "size": 512000,
            "mimeType": "image/png",
            "storageID": "local",
            "hidden": 0,
            "description": "A test PNG",
            "custom": "",
            "creatorEntityID": None,
            "imageDate": 1640995400000,
            "imageWidth": 800,
            "imageHeight": 600,
            "imageCameraMake": "",
            "imageCameraModel": "",
            "imageAperture": 0,
            "imageExposureTime": 0,
            "imageISOSpeed": 0,
            "imageFocalLength": 0,
            "imageFlashFired": None,
            "imageOrientation": 1,
            "imageLatitude": None,
            "imageLongitude": None,
            "imageAltitude": None,
            "imageCity": "",
            "imageProvince": "",
            "imageCountry": "",
            "videoDate": None,
            "videoCodec": "",
            "videoWidth": 0,
            "videoHeight": 0,
            "videoDuration": 0,
            "videoOrientation": 0,
            "videoLatitude": None,
            "videoLongitude": None,
            "videoAltitude": None,
            "videoCity": "",
            "videoProvince": "",
            "videoCountry": "",
            "audioDuration": 0,
            "audioTitle": "",
            "audioAlbum": "",
            "audioArtist": "",
            "category": 1,
            "month": 12,
            "week": 52,
        },
        {
            "id": "file4",
            "parentID": None,
            "contentID": "d4e5f6a1b2c3",
            "version": 1,
            "name": "missing.jpg",
            "birthTime": 1640995500000,
            "cTime": 1640995500000,
            "uTime": 1640995400000,
            "mTime": 1640995450000,
            "size": 2048000,
            "mimeType": "image/jpeg",
            "storageID": "local",
            "hidden": 0,
            "description": "Missing test image",
            "custom": "",
            "creatorEntityID": None,
            "imageDate": 1640995500000,
            "imageWidth": 2048,
            "imageHeight": 1536,
            "imageCameraMake": "Sony",
            "imageCameraModel": "A7R IV",
            "imageAperture": 1.8,
            "imageExposureTime": 0.0005,
            "imageISOSpeed": 100,
            "imageFocalLength": 50.0,
            "imageFlashFired": 0,
            "imageOrientation": 1,
            "imageLatitude": 40.7128,
            "imageLongitude": -74.0060,
            "imageAltitude": None,
            "imageCity": "New York",
            "imageProvince": "NY",
            "imageCountry": "USA",
            "videoDate": None,
            "videoCodec": "",
            "videoWidth": 0,
            "videoHeight": 0,
            "videoDuration": 0,
            "videoOrientation": 0,
            "videoLatitude": None,
            "videoLongitude": None,
            "videoAltitude": None,
            "videoCity": "",
            "videoProvince": "",
            "videoCountry": "",
            "audioDuration": 0,
            "audioTitle": "",
            "audioAlbum": "",
            "audioArtist": "",
            "category": 1,
            "month": 12,
            "week": 52,
        },
    ]

    # Insert files using the complete schema
    for file_data in test_files:
        placeholders = ", ".join(["?" for _ in file_data.keys()])
        columns = ", ".join(file_data.keys())
        cursor.execute(
            f"INSERT INTO Files ({columns}) VALUES ({placeholders})",
            list(file_data.values()),
        )

    # Insert test albums matching the real schema
    test_albums = [
        {
            "id": "album1",
            "name": "Family Vacation",
            "previewFileID": "file1",
            "cTime": 1640995000000,
            "mTime": 1640995500000,
            "description": "Photos from family vacation",
            "estCount": 2,
            "estMinTime": 1640995200000,
            "estMaxTime": 1640995300000,
            "creatorEntityID": None,
            "post": 0,
            "commentsCount": 0,
        },
        {
            "id": "album2",
            "name": "Work Photos",
            "previewFileID": "file3",
            "cTime": 1640995300000,
            "mTime": 1640995400000,
            "description": "Work-related photos",
            "estCount": 1,
            "estMinTime": 1640995400000,
            "estMaxTime": 1640995400000,
            "creatorEntityID": None,
            "post": 0,
            "commentsCount": 0,
        },
    ]

    for album_data in test_albums:
        placeholders = ", ".join(["?" for _ in album_data.keys()])
        columns = ", ".join(album_data.keys())
        cursor.execute(
            f"INSERT INTO FileGroups ({columns}) VALUES ({placeholders})",
            list(album_data.values()),
        )

    # Insert album memberships matching the real schema
    album_memberships = [
        {
            "id": "membership1",
            "fileID": "file1",
            "fileGroupID": "album1",
            "fileCTime": 1640995200000,
            "cTime": 1640995000000,
            "changeID": 1,
            "creatorEntityID": None,
            "commentsCount": 0,
        },
        {
            "id": "membership2",
            "fileID": "file2",
            "fileGroupID": "album1",
            "fileCTime": 1640995300000,
            "cTime": 1640995000000,
            "changeID": 2,
            "creatorEntityID": None,
            "commentsCount": 0,
        },
        {
            "id": "membership3",
            "fileID": "file3",
            "fileGroupID": "album2",
            "fileCTime": 1640995400000,
            "cTime": 1640995300000,
            "changeID": 1,
            "creatorEntityID": None,
            "commentsCount": 0,
        },
    ]

    for membership_data in album_memberships:
        placeholders = ", ".join(["?" for _ in membership_data.keys()])
        columns = ", ".join(membership_data.keys())
        cursor.execute(
            f"INSERT INTO FileGroupFiles ({columns}) VALUES ({placeholders})",
            list(membership_data.values()),
        )

    # Insert AI tags
    test_tags = [
        ("file1", "person", 1),
        ("file1", "beach", 1),
        ("file1", "vacation", 0),  # Manual tag
        ("file2", "person", 1),
        ("file3", "document", 1),
    ]

    for tag_data in test_tags:
        cursor.execute(
            """
            INSERT INTO FilesTags (fileID, tag, auto)
            VALUES (?, ?, ?)
        """,
            tag_data,
        )

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def mock_files(mock_ibi_structure):
    """Create mock files in the files directory."""
    files_dir = mock_ibi_structure["files"]

    # Create test files (matching contentIDs from database)
    test_files = [
        ("a", "a1b2c3d4e5f6", b"fake jpeg content" * 1000),  # ~17KB
        ("b", "b2c3d4e5f6a1", b"fake mp4 content" * 5000),  # ~80KB
        ("c", "c3d4e5f6a1b2", b"fake png content" * 500),  # ~8KB
        # Note: 'd4e5f6a1b2c3' (missing.jpg) intentionally not created
    ]

    created_files = []
    for subdir, content_id, content in test_files:
        file_path = files_dir / subdir / content_id
        file_path.write_bytes(content)
        created_files.append(file_path)

    return created_files


@pytest.fixture
def mock_export_formats():
    """Use the actual export formats configuration."""
    project_root = Path(__file__).parent.parent
    formats_file = project_root / "export_formats.json"

    # Create a minimal mock if the actual file doesn't exist
    if not formats_file.exists():
        formats_file = project_root / "test_export_formats.json"
        export_formats = {
            "formats": {
                "lightroom_csv": {
                    "name": "Test Lightroom CSV",
                    "description": "Adobe Lightroom CSV import format",
                    "file_extension": "csv",
                    "type": "csv",
                    "columns": [
                        {"name": "filename", "source": "name", "required": True},
                        {
                            "name": "keywords",
                            "source": "tags",
                            "transform": "join_tags",
                            "separator": ";",
                        },
                    ],
                },
                "json_metadata": {
                    "name": "Test JSON Metadata",
                    "description": "JSON metadata export",
                    "file_extension": "json",
                    "type": "json",
                    "structure": {
                        "files": {
                            "source": "files_array",
                            "fields": {
                                "filename": "name",
                                "tags": {"source": "tags", "transform": "tag_array"},
                            },
                        }
                    },
                },
            }
        }

        with open(formats_file, "w") as f:
            json.dump(export_formats, f, indent=2)

    return formats_file


@pytest.fixture
def sample_files_data():
    """Sample files data for testing export functions - matches expected structure."""
    return [
        {
            "file_record": {
                "id": "file1",
                "name": "test1.jpg",
                "contentID": "a1b2c3d4e5f6",
                "mimeType": "image/jpeg",
                "size": 1024000,
                "imageLatitude": 37.7749,
                "imageLongitude": -122.4194,
                "imageCameraMake": "Canon",
                "imageCameraModel": "EOS R5",
                "description": "A test image",
            },
            "tags": [
                {"tag": "person", "auto": True},
                {"tag": "beach", "auto": True},
                {"tag": "vacation", "auto": False},
            ],
            "albums": [
                {
                    "name": "Family Vacation",
                    "description": "Photos from family vacation",
                }
            ],
        },
        {
            "file_record": {
                "id": "file2",
                "name": "test2.mp4",
                "contentID": "b2c3d4e5f6a1",
                "mimeType": "video/mp4",
                "size": 5120000,
                "videoLatitude": 37.7849,
                "videoLongitude": -122.4294,
                "description": "A test video",
            },
            "tags": [{"tag": "person", "auto": True}],
            "albums": [
                {
                    "name": "Family Vacation",
                    "description": "Photos from family vacation",
                }
            ],
        },
        {
            "file_record": {
                "id": "file3",
                "name": "test3.png",
                "contentID": "c3d4e5f6a1b2",
                "mimeType": "image/png",
                "size": 512000,
                "description": "A test PNG",
            },
            "tags": [{"tag": "document", "auto": True}],
            "albums": [{"name": "Work Photos", "description": "Work-related photos"}],
        },
    ]


@pytest.fixture
def files_with_albums_data():
    """Sample files data for testing file operations - matches get_all_files_with_albums structure."""
    return [
        {
            "file": {
                "id": "file1",
                "name": "test1.jpg",
                "contentID": "a1b2c3d4e5f6",
                "mimeType": "image/jpeg",
                "size": 1024000,
            },
            "albums": [{"name": "Family Vacation", "id": "album1"}],
        },
        {
            "file": {
                "id": "file2",
                "name": "test2.mp4",
                "contentID": "b2c3d4e5f6a1",
                "mimeType": "video/mp4",
                "size": 5120000,
            },
            "albums": [{"name": "Family Vacation", "id": "album1"}],
        },
        {
            "file": {
                "id": "file3",
                "name": "test3.png",
                "contentID": "c3d4e5f6a1b2",
                "mimeType": "image/png",
                "size": 512000,
            },
            "albums": [{"name": "Work Photos", "id": "album2"}],
        },
    ]
