"""Tests for orphan file filtering functionality."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ibirecovery.core.orphan_filter import OrphanFileFilter, format_size


class TestOrphanFileFilter:
    """Test orphan file filtering and classification."""

    def test_orphan_filter_initialization(self, temp_dir):
        """Test OrphanFileFilter initialization."""
        files_dir = temp_dir / "files"
        db_path = temp_dir / "test.db"

        # Test without database
        filter_no_db = OrphanFileFilter(files_dir)
        assert filter_no_db.files_dir == files_dir
        assert filter_no_db.db_path is None

        # Test with database
        filter_with_db = OrphanFileFilter(files_dir, db_path)
        assert filter_with_db.files_dir == files_dir
        assert filter_with_db.db_path == db_path

    def test_hash_file_fast(self, temp_dir):
        """Test fast file hashing functionality."""
        filter_obj = OrphanFileFilter(temp_dir)

        # Create test files
        file1 = temp_dir / "test1.txt"
        file2 = temp_dir / "test2.txt"
        file3 = temp_dir / "test1_copy.txt"

        file1.write_text("Hello, World!")
        file2.write_text("Different content")
        file3.write_text("Hello, World!")  # Same as file1

        hash1 = filter_obj.hash_file_fast(file1)
        hash2 = filter_obj.hash_file_fast(file2)
        hash3 = filter_obj.hash_file_fast(file3)

        # Same content should have same hash
        assert hash1 == hash3
        # Different content should have different hash
        assert hash1 != hash2

    def test_size_based_filtering(self, temp_dir):
        """Test size-based filtering logic."""
        filter_obj = OrphanFileFilter(temp_dir)

        # Test zero-byte file
        zero_file = temp_dir / "empty.txt"
        zero_file.touch()
        skip, reason = filter_obj.is_size_based_skip(zero_file, 0)
        assert skip is True
        assert reason == "zero_byte_file"

        # Test tiny file
        tiny_file = temp_dir / "tiny.txt"
        tiny_file.write_text("x")
        skip, reason = filter_obj.is_size_based_skip(tiny_file, 500)
        assert skip is True
        assert reason == "tiny_file_likely_metadata"

        # Test small file with thumbnail name
        thumb_file = temp_dir / "photo_thumb.jpg"
        thumb_file.write_text("x" * 5000)
        skip, reason = filter_obj.is_size_based_skip(thumb_file, 5000)
        assert skip is True
        assert reason == "small_file_with_thumbnail_name"

        # Test normal file
        normal_file = temp_dir / "photo.jpg"
        skip, reason = filter_obj.is_size_based_skip(normal_file, 100000)
        assert skip is False
        assert reason == ""

    def test_pattern_based_filtering(self, temp_dir):
        """Test pattern-based filtering logic."""
        filter_obj = OrphanFileFilter(temp_dir)

        # Test various skip patterns
        test_files = [
            ("photo_thumb.jpg", True),
            ("image_preview.png", True),
            ("cache_file.dat", True),
            ("temp_file.tmp", True),
            ("document.temp", True),
            ("._resource_fork", True),
            (".DS_Store", True),
            ("Thumbs.db", True),
            ("photo_150x150.jpg", True),
            ("normal_photo.jpg", False),
            ("document.pdf", False),
            ("video.mp4", False),
        ]

        for filename, should_skip in test_files:
            file_path = temp_dir / filename
            skip, reason = filter_obj.is_pattern_based_skip(file_path)
            assert (
                skip == should_skip
            ), f"File {filename} should {'be skipped' if should_skip else 'not be skipped'}"

    def test_content_duplicate_detection(self, temp_dir):
        """Test content duplicate detection."""
        filter_obj = OrphanFileFilter(temp_dir)

        # Create files with identical content
        file1 = temp_dir / "original.txt"
        file2 = temp_dir / "duplicate.txt"
        file3 = temp_dir / "different.txt"

        content = "This is test content for duplicate detection"
        file1.write_text(content)
        file2.write_text(content)
        file3.write_text("Different content")

        # First file should not be marked as duplicate
        skip1, reason1, dup_path1 = filter_obj.is_content_duplicate(file1)
        assert skip1 is False
        assert reason1 == ""
        assert dup_path1 is None

        # Second file should be marked as duplicate of first
        skip2, reason2, dup_path2 = filter_obj.is_content_duplicate(file2)
        assert skip2 is True
        assert reason2 == "content_duplicate"
        assert dup_path2 == file1

        # Third file has different content, not a duplicate
        skip3, reason3, dup_path3 = filter_obj.is_content_duplicate(file3)
        assert skip3 is False
        assert reason3 == ""
        assert dup_path3 is None

    def test_database_orphan_detection(self, temp_dir):
        """Test database orphan detection with known content IDs."""
        # Create test database
        db_path = temp_dir / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE Files(
                id TEXT PRIMARY KEY,
                contentID TEXT
            )
        """
        )
        conn.execute(
            "INSERT INTO Files (id, contentID) VALUES ('1', 'known_content_id')"
        )
        conn.commit()
        conn.close()

        filter_obj = OrphanFileFilter(temp_dir, db_path)

        # Load known content IDs
        conn = sqlite3.connect(db_path)
        filter_obj.load_known_content_ids(conn)
        conn.close()

        # Test files
        known_file = temp_dir / "known_content_id"
        orphan_file = temp_dir / "unknown_content_id"

        assert not filter_obj.is_database_orphan(known_file)  # Not an orphan
        assert filter_obj.is_database_orphan(orphan_file)  # Is an orphan

    def test_classify_orphan_file_comprehensive(self, temp_dir):
        """Test comprehensive orphan file classification."""
        # Create test database
        db_path = temp_dir / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE Files(
                id TEXT PRIMARY KEY,
                contentID TEXT
            )
        """
        )
        conn.execute("INSERT INTO Files (id, contentID) VALUES ('1', 'known_file')")
        conn.commit()
        conn.close()

        filter_obj = OrphanFileFilter(temp_dir, db_path)

        # Load database content
        conn = sqlite3.connect(db_path)
        filter_obj.load_known_content_ids(conn)
        conn.close()

        # Test various file types

        # 1. Non-orphan file (in database)
        known_file = temp_dir / "known_file"
        known_file.write_text("Known content")
        result = filter_obj.classify_orphan_file(known_file)
        assert result["skip"] is True
        assert result["reason"] == "not_orphan_has_database_entry"
        assert result["is_true_orphan"] is False

        # 2. Zero-byte orphan file
        zero_file = temp_dir / "zero_orphan"
        zero_file.touch()
        result = filter_obj.classify_orphan_file(zero_file)
        assert result["skip"] is True
        assert result["reason"] == "zero_byte_file"
        assert result["is_true_orphan"] is True

        # 3. Thumbnail file (small size gets filtered first)
        thumb_file = temp_dir / "photo_thumb.jpg"
        thumb_file.write_text("x" * 1000)
        result = filter_obj.classify_orphan_file(thumb_file)
        assert result["skip"] is True
        # Small files get caught by size filter before pattern filter
        assert result["reason"] in [
            "tiny_file_likely_metadata",
            "small_file_with_thumbnail_name",
        ]
        assert result["is_true_orphan"] is True

        # 4. Legitimate orphan file
        legit_file = temp_dir / "legitimate_photo.jpg"
        legit_file.write_text("x" * 100000)
        result = filter_obj.classify_orphan_file(legit_file)
        assert result["skip"] is False
        assert result["reason"] == "legitimate_orphan"
        assert result["is_true_orphan"] is True

    def test_filter_orphan_files_comprehensive(self, temp_dir):
        """Test comprehensive orphan filtering with statistics."""
        # Create test database
        db_path = temp_dir / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE Files(
                id TEXT PRIMARY KEY,
                contentID TEXT
            )
        """
        )
        conn.execute("INSERT INTO Files (id, contentID) VALUES ('1', 'known_file')")
        conn.commit()
        conn.close()

        filter_obj = OrphanFileFilter(temp_dir, db_path)

        # Create test files
        test_files = []

        # Known file (not orphan)
        known_file = temp_dir / "known_file"
        known_file.write_text("Known content")
        test_files.append(known_file)

        # Zero-byte orphan
        zero_file = temp_dir / "zero_orphan"
        zero_file.touch()
        test_files.append(zero_file)

        # Thumbnail orphan
        thumb_file = temp_dir / "photo_thumb.jpg"
        thumb_file.write_text("x" * 1000)
        test_files.append(thumb_file)

        # Duplicate orphan files (make them larger to avoid tiny file filter)
        dup1_file = temp_dir / "duplicate1.txt"
        dup2_file = temp_dir / "duplicate2.txt"
        dup_content = "Duplicate content " * 1000  # Make it larger
        dup1_file.write_text(dup_content)
        dup2_file.write_text(dup_content)
        test_files.extend([dup1_file, dup2_file])

        # Legitimate orphan
        legit_file = temp_dir / "legitimate_photo.jpg"
        legit_file.write_text("x" * 100000)
        test_files.append(legit_file)

        # Run filtering
        results = filter_obj.filter_orphan_files(test_files)

        # Verify results
        assert results["total_orphans"] == 6
        assert results["skip_count"] == 4  # known + zero + thumb + dup2
        assert results["keep_count"] == 2  # legitimate file + dup1 (first duplicate)
        assert results["skip_percentage"] > 60  # Most files skipped

        # Verify skip reasons
        assert "not_orphan_has_database_entry" in results["skip_reasons"]
        assert "zero_byte_file" in results["skip_reasons"]
        # Small thumbnail files get caught by size filter first
        assert (
            "tiny_file_likely_metadata" in results["skip_reasons"]
            or "small_file_with_thumbnail_name" in results["skip_reasons"]
        )
        assert "content_duplicate" in results["skip_reasons"]

        # Verify duplicates found
        assert len(results["duplicates_found"]) == 1

    def test_get_filtered_orphan_paths(self, temp_dir):
        """Test getting filtered list of orphan paths to keep."""
        filter_obj = OrphanFileFilter(temp_dir)

        # Create test files
        legit_file = temp_dir / "photo.jpg"
        thumb_file = temp_dir / "photo_thumb.jpg"
        zero_file = temp_dir / "empty.txt"

        legit_file.write_text("x" * 100000)
        thumb_file.write_text("x" * 1000)
        zero_file.touch()

        test_files = [legit_file, thumb_file, zero_file]

        # Get filtered paths
        filtered_paths = filter_obj.get_filtered_orphan_paths(test_files)

        # Should only return legitimate file
        assert len(filtered_paths) == 1
        assert filtered_paths[0] == legit_file

    def test_filter_with_missing_database(self, temp_dir):
        """Test filtering when database is missing or inaccessible."""
        non_existent_db = temp_dir / "missing.db"
        filter_obj = OrphanFileFilter(temp_dir, non_existent_db)

        # Create test file
        test_file = temp_dir / "test.jpg"
        test_file.write_text("x" * 100000)

        # Should work without database (all files treated as orphans)
        result = filter_obj.classify_orphan_file(test_file)
        assert result["is_true_orphan"] is True  # No database to check against
        assert result["skip"] is False  # Legitimate file
        assert result["reason"] == "legitimate_orphan"


class TestFormatSize:
    """Test file size formatting utility."""

    def test_format_size_various_units(self):
        """Test size formatting for different units."""
        assert format_size(0) == "0.0 B"
        assert format_size(512) == "512.0 B"
        assert format_size(1024) == "1.0 KB"
        assert format_size(1536) == "1.5 KB"
        assert format_size(1024 * 1024) == "1.0 MB"
        assert format_size(1024 * 1024 * 1024) == "1.0 GB"
        assert format_size(1024 * 1024 * 1024 * 1024) == "1.0 TB"

    def test_format_size_large_values(self):
        """Test size formatting for very large values."""
        large_size = 5.5 * 1024 * 1024 * 1024  # 5.5 GB
        result = format_size(int(large_size))
        assert "5.5 GB" in result


class TestOrphanFilterIntegration:
    """Test integration scenarios for orphan filtering."""

    def test_realistic_orphan_scenario(self, temp_dir):
        """Test filtering in a realistic scenario with many orphan types."""
        # Create realistic file structure
        files_dir = temp_dir / "files"
        files_dir.mkdir()

        # Create subdirectories (a-z)
        for letter in "abcdef":
            (files_dir / letter).mkdir()

        # Create test database
        db_path = temp_dir / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE Files(
                id TEXT PRIMARY KEY,
                contentID TEXT
            )
        """
        )
        # Add some known files
        for i in range(10):
            conn.execute(
                f"INSERT INTO Files (id, contentID) VALUES ('{i}', 'known_{i}')"
            )
        conn.commit()
        conn.close()

        filter_obj = OrphanFileFilter(files_dir, db_path)

        # Create various types of files
        test_files = []

        # Known files (not orphans)
        for i in range(10):
            known_file = files_dir / "a" / f"known_{i}"
            known_file.write_text(f"Known content {i}")
            test_files.append(known_file)

        # Legitimate orphan photos
        for i in range(50):
            photo = files_dir / "b" / f"photo_{i}.jpg"
            photo.write_text("x" * (100000 + i * 1000))  # Various sizes
            test_files.append(photo)

        # Thumbnail files
        for i in range(100):
            thumb = files_dir / "c" / f"photo_{i}_thumb.jpg"
            thumb.write_text("x" * (5000 + i * 10))  # Small thumbnails
            test_files.append(thumb)

        # Cache files
        for i in range(20):
            cache = files_dir / "d" / f"cache_{i}.tmp"
            cache.write_text("x" * 1000)
            test_files.append(cache)

        # System files
        system_files = [
            files_dir / "e" / ".DS_Store",
            files_dir / "e" / "Thumbs.db",
            files_dir / "e" / "._hidden_file",
        ]
        for sys_file in system_files:
            sys_file.write_text("system data")
            test_files.append(sys_file)

        # Zero-byte files
        for i in range(10):
            zero_file = files_dir / "f" / f"empty_{i}"
            zero_file.touch()
            test_files.append(zero_file)

        # Run filtering
        results = filter_obj.filter_orphan_files(test_files)

        # Verify massive reduction in orphan files
        assert results["total_orphans"] == len(test_files)
        assert results["keep_count"] == 50  # Only legitimate orphan photos
        assert results["skip_count"] > 130  # Everything else
        assert results["skip_percentage"] > 70  # Significant reduction

        # Verify various skip reasons are present
        assert results["skip_reasons"]["not_orphan_has_database_entry"] == 10
        assert results["skip_reasons"]["small_file_with_thumbnail_name"] == 100
        assert results["skip_reasons"]["zero_byte_file"] == 10

        print(
            f"Filtered {results['skip_count']} out of {results['total_orphans']} files ({results['skip_percentage']:.1f}%)"
        )
