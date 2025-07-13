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

    # Create Files table with all fields expected by comprehensive export
    cursor.execute(
        """
        CREATE TABLE Files (
            id TEXT PRIMARY KEY,
            name TEXT,
            contentID TEXT,
            mimeType TEXT,
            size INTEGER,
            createdTime REAL,
            modifiedTime REAL,
            imageDate REAL,
            videoDate REAL,
            cTime REAL,
            birthTime REAL,
            imageLatitude REAL,
            imageLongitude REAL,
            imageAltitude REAL,
            imageCity TEXT,
            imageProvince TEXT,
            imageCountry TEXT,
            videoLatitude REAL,
            videoLongitude REAL,
            videoAltitude REAL,
            videoCity TEXT,
            videoProvince TEXT,
            videoCountry TEXT,
            imageCameraMake TEXT,
            imageCameraModel TEXT,
            description TEXT
        )
    """
    )

    # Create FileGroups table (albums) with description field
    cursor.execute(
        """
        CREATE TABLE FileGroups (
            id TEXT PRIMARY KEY,
            name TEXT,
            type TEXT,
            estCount INTEGER,
            description TEXT
        )
    """
    )

    # Create FileGroupFiles table (album membership)
    cursor.execute(
        """
        CREATE TABLE FileGroupFiles (
            fileGroupID TEXT,
            fileID TEXT,
            FOREIGN KEY (fileGroupID) REFERENCES FileGroups(id),
            FOREIGN KEY (fileID) REFERENCES Files(id)
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

    # Insert test data with all required fields
    test_files = [
        (
            "file1",
            "test1.jpg",
            "a1b2c3d4e5f6",
            "image/jpeg",
            1024000,
            1640995200.0,
            1640995200.0,
            1640995200.0,
            None,
            1640995200.0,
            1640995200.0,
            37.7749,
            -122.4194,
            None,
            "San Francisco",
            "CA",
            "USA",
            None,
            None,
            None,
            None,
            None,
            None,
            "Canon",
            "EOS R5",
            "A test image",
        ),
        (
            "file2",
            "test2.mp4",
            "b2c3d4e5f6a1",
            "video/mp4",
            5120000,
            1640995300.0,
            1640995300.0,
            None,
            1640995300.0,
            1640995300.0,
            1640995300.0,
            None,
            None,
            None,
            None,
            None,
            None,
            37.7849,
            -122.4294,
            None,
            "San Francisco",
            "CA",
            "USA",
            None,
            None,
            "A test video",
        ),
        (
            "file3",
            "test3.png",
            "c3d4e5f6a1b2",
            "image/png",
            512000,
            1640995400.0,
            1640995400.0,
            1640995400.0,
            None,
            1640995400.0,
            1640995400.0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "A test PNG",
        ),
        (
            "file4",
            "missing.jpg",
            "d4e5f6a1b2c3",
            "image/jpeg",
            2048000,
            1640995500.0,
            1640995500.0,
            1640995500.0,
            None,
            1640995500.0,
            1640995500.0,
            40.7128,
            -74.0060,
            None,
            "New York",
            "NY",
            "USA",
            None,
            None,
            None,
            None,
            None,
            None,
            "Sony",
            "A7R IV",
            "Missing test image",
        ),
    ]

    for file_data in test_files:
        cursor.execute(
            """
            INSERT INTO Files (id, name, contentID, mimeType, size, createdTime, modifiedTime, imageDate, videoDate, cTime, birthTime, imageLatitude, imageLongitude, imageAltitude, imageCity, imageProvince, imageCountry, videoLatitude, videoLongitude, videoAltitude, videoCity, videoProvince, videoCountry, imageCameraMake, imageCameraModel, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            file_data,
        )

    # Insert test albums with descriptions
    test_albums = [
        ("album1", "Family Vacation", "user", 2, "Photos from family vacation"),
        ("album2", "Work Photos", "user", 1, "Work-related photos"),
    ]

    for album_data in test_albums:
        cursor.execute(
            """
            INSERT INTO FileGroups (id, name, type, estCount, description)
            VALUES (?, ?, ?, ?, ?)
        """,
            album_data,
        )

    # Insert album memberships
    cursor.execute(
        "INSERT INTO FileGroupFiles (fileGroupID, fileID) VALUES ('album1', 'file1')"
    )
    cursor.execute(
        "INSERT INTO FileGroupFiles (fileGroupID, fileID) VALUES ('album1', 'file2')"
    )
    cursor.execute(
        "INSERT INTO FileGroupFiles (fileGroupID, fileID) VALUES ('album2', 'file3')"
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
