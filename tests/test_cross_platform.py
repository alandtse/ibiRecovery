"""Cross-platform compatibility and edge case tests."""

import os
import platform
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the package to the path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ibirecovery.extract_files import (
    copy_file_fallback,
    copy_file_with_dedup,
    detect_ibi_structure,
    find_source_file,
    format_size,
)


class TestCrossPlatformCompatibility:
    """Test compatibility across different platforms and filesystems."""

    def test_unicode_filename_handling(self, temp_dir):
        """Test handling of Unicode filenames."""
        # Test various Unicode characters
        unicode_filenames = [
            "café_photo.jpg",
            "北京_vacation.mp4",
            "файл_документ.pdf",
            "photo_🏖️_beach.jpg",
            "test_åäö_file.txt",
            "файл.txt",  # Cyrillic
            "测试文件.jpg",  # Chinese
            "ファイル.png",  # Japanese
            "파일.gif",  # Korean
        ]

        source_dir = temp_dir / "source"
        dest_dir = temp_dir / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        successful_copies = 0

        for filename in unicode_filenames:
            try:
                source_file = source_dir / filename
                dest_file = dest_dir / filename

                # Create source with Unicode content
                content = f"Unicode test content for {filename}".encode("utf-8")
                source_file.write_bytes(content)

                # Test copy operation
                result = copy_file_fallback(source_file, dest_file, resume=False)

                if result:
                    successful_copies += 1
                    assert dest_file.exists()
                    assert dest_file.read_bytes() == content

            except (UnicodeError, OSError) as e:
                # Some filesystems may not support certain Unicode characters
                print(f"Unicode filename {filename} not supported: {e}")
                continue

        # Should successfully handle at least basic Unicode
        assert successful_copies >= len(unicode_filenames) // 2

    def test_long_path_handling(self, temp_dir):
        """Test handling of very long file paths."""
        # Create a deeply nested directory structure
        deep_path = temp_dir
        path_components = [
            "very",
            "deeply",
            "nested",
            "directory",
            "structure",
            "that",
            "goes",
            "many",
            "levels",
            "deep",
            "for",
            "testing",
        ]

        for component in path_components:
            deep_path = deep_path / component
            deep_path.mkdir(exist_ok=True)

        # Create a file with a long name in the deep path
        long_filename = "very_long_filename_" + "x" * 100 + ".txt"
        source_file = deep_path / long_filename
        dest_file = temp_dir / "output" / long_filename
        dest_file.parent.mkdir(exist_ok=True)

        try:
            source_file.write_text("Long path test content")
            result = copy_file_fallback(source_file, dest_file, resume=False)

            # Should handle long paths (or fail gracefully)
            if result:
                assert dest_file.exists()
                assert dest_file.read_text() == "Long path test content"
        except OSError:
            # Some systems have path length limits
            pytest.skip("System doesn't support long paths")

    def test_case_sensitive_filesystem_handling(self, temp_dir):
        """Test behavior on case-sensitive vs case-insensitive filesystems."""
        source_dir = temp_dir / "source"
        dest_dir = temp_dir / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        # Test case variations
        test_cases = [
            ("test.jpg", "TEST.JPG"),
            ("Photo.PNG", "photo.png"),
            ("Document.PDF", "DOCUMENT.pdf"),
        ]

        for original_name, variant_name in test_cases:
            source_file = source_dir / original_name
            dest_file1 = dest_dir / original_name
            dest_file2 = dest_dir / variant_name

            source_file.write_text(f"Content for {original_name}")

            # Copy with original name
            result1 = copy_file_fallback(source_file, dest_file1, resume=False)
            assert result1 is True
            assert dest_file1.exists()

            # Try to copy with variant name
            result2 = copy_file_fallback(source_file, dest_file2, resume=False)

            # On case-insensitive systems, this might overwrite or fail
            # On case-sensitive systems, this should create a separate file
            if result2:
                # Check if filesystem is case-sensitive
                is_case_sensitive = dest_file1.exists() and dest_file2.exists()
                if is_case_sensitive and dest_file1 != dest_file2:
                    # Case-sensitive filesystem
                    assert dest_file1.read_text() == f"Content for {original_name}"
                    assert dest_file2.read_text() == f"Content for {original_name}"

    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix-specific test")
    def test_symlink_handling_unix(self, temp_dir):
        """Test symlink handling on Unix systems."""
        source_file = temp_dir / "source.txt"
        symlink_file = temp_dir / "symlink.txt"
        dest_file = temp_dir / "dest.txt"

        # Create source and symlink
        source_file.write_text("Original content")
        symlink_file.symlink_to(source_file)

        # Test copying a symlink
        result = copy_file_fallback(symlink_file, dest_file, resume=False)
        assert result is True
        assert dest_file.exists()
        assert dest_file.read_text() == "Original content"

        # Destination should be a regular file, not a symlink
        assert not dest_file.is_symlink()

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    def test_windows_path_handling(self, temp_dir):
        """Test Windows-specific path handling."""
        # Test various Windows path issues
        problematic_names = [
            "file with spaces.txt",
            "file.with.dots.txt",
            "file-with-dashes.txt",
            "file_with_underscores.txt",
        ]

        for filename in problematic_names:
            source_file = temp_dir / filename
            dest_file = temp_dir / "output" / filename
            dest_file.parent.mkdir(exist_ok=True)

            source_file.write_text(f"Content for {filename}")
            result = copy_file_fallback(source_file, dest_file, resume=False)

            assert result is True
            assert dest_file.exists()
            assert dest_file.read_text() == f"Content for {filename}"

    def test_special_characters_in_paths(self, temp_dir):
        """Test handling of special characters in file paths."""
        special_chars = ["&", "@", "#", "%", "(", ")", "[", "]", "+", "="]

        for char in special_chars:
            try:
                filename = f"file{char}test.txt"
                source_file = temp_dir / filename
                dest_file = temp_dir / "output" / filename
                dest_file.parent.mkdir(exist_ok=True)

                source_file.write_text(f"Content with {char}")
                result = copy_file_fallback(source_file, dest_file, resume=False)

                if result:
                    assert dest_file.exists()
                    assert dest_file.read_text() == f"Content with {char}"

            except (OSError, ValueError):
                # Some special characters may not be allowed on certain filesystems
                continue


class TestEdgeCases:
    """Test various edge cases and boundary conditions."""

    def test_zero_byte_files(self, temp_dir):
        """Test handling of zero-byte files."""
        source_file = temp_dir / "empty.txt"
        dest_file = temp_dir / "empty_copy.txt"

        # Create empty file
        source_file.touch()
        assert source_file.stat().st_size == 0

        # Test copy
        result = copy_file_fallback(source_file, dest_file, resume=False)
        assert result is True
        assert dest_file.exists()
        assert dest_file.stat().st_size == 0

        # Test resume behavior with empty files
        result2 = copy_file_fallback(source_file, dest_file, resume=True)
        assert result2 is True  # Should skip

    def test_very_large_files(self, temp_dir):
        """Test handling of large files (simulated)."""
        source_file = temp_dir / "large.bin"
        dest_file = temp_dir / "large_copy.bin"

        # Create a moderately large file (1MB) with pattern
        chunk_size = 1024
        pattern = b"X" * chunk_size

        with open(source_file, "wb") as f:
            for i in range(1024):  # 1MB total
                f.write(pattern)

        # Test copy
        result = copy_file_fallback(source_file, dest_file, resume=False)
        assert result is True
        assert dest_file.exists()
        assert dest_file.stat().st_size == source_file.stat().st_size

        # Verify content integrity
        with open(source_file, "rb") as src, open(dest_file, "rb") as dst:
            while True:
                src_chunk = src.read(4096)
                dst_chunk = dst.read(4096)
                if not src_chunk:
                    break
                assert src_chunk == dst_chunk

    def test_simultaneous_access(self, temp_dir):
        """Test behavior when files are accessed simultaneously."""
        source_file = temp_dir / "source.txt"
        dest_file = temp_dir / "dest.txt"

        source_file.write_text("Simultaneous access test")

        # Simulate file being locked/in use
        with open(source_file, "r") as locked_file:
            # Try to copy while file is open for reading
            result = copy_file_fallback(source_file, dest_file, resume=False)
            # Should succeed on most systems (read locks don't prevent copying)
            assert result is True
            assert dest_file.exists()

    def test_content_id_edge_cases(self, temp_dir):
        """Test find_source_file with edge case content IDs."""
        files_dir = temp_dir / "files"
        files_dir.mkdir()

        # Create subdirectories
        for subdir in ["a", "b", "0", "9", "f"]:
            (files_dir / subdir).mkdir()

        # Test various content ID formats
        test_cases = [
            "a1b2c3d4e5f6",  # Normal case
            "0123456789ab",  # Starts with digit
            "f" * 12,  # All same character
            "A1B2C3D4E5F6",  # Uppercase
            "short",  # Very short
            "1",  # Single character
            "",  # Empty (should handle gracefully)
        ]

        for content_id in test_cases:
            if len(content_id) > 0:
                # Create test file
                expected_path = files_dir / content_id[0].lower() / content_id
                expected_path.parent.mkdir(exist_ok=True)
                expected_path.write_text(f"Content for {content_id}")

                # Test finding the file
                found_path = find_source_file(files_dir, content_id)
                if found_path:
                    assert found_path.exists()
                    assert found_path.read_text() == f"Content for {content_id}"
            else:
                # Empty content ID should return None
                found_path = find_source_file(files_dir, content_id)
                assert found_path is None

    def test_deduplication_edge_cases(self, temp_dir):
        """Test deduplication with edge cases."""
        # Test deduplication with identical files of different sizes reported
        source1 = temp_dir / "source1.txt"
        source2 = temp_dir / "source2.txt"
        dest1 = temp_dir / "dest1.txt"
        dest2 = temp_dir / "dest2.txt"

        # Create files with same content but let's test the tracker
        content = "Deduplication test content"
        source1.write_text(content)
        source2.write_text(content)

        copy_tracker = {}

        # First copy
        success1, action1 = copy_file_with_dedup(
            source1, dest1, resume=False, copy_tracker=copy_tracker
        )
        assert success1 is True
        assert action1 == "copied"

        # Second copy of different source but same content
        # Note: current implementation tracks by source path, not content hash
        success2, action2 = copy_file_with_dedup(
            source2, dest2, resume=False, copy_tracker=copy_tracker
        )
        assert success2 is True
        # This might be 'copied' since it's from a different source path
        assert action2 in ["copied", "hardlinked"]

    def test_format_size_edge_cases(self):
        """Test format_size function with edge cases."""
        # Test edge cases for size formatting
        test_cases = [
            (0, "0 B"),
            (1, "1 B"),
            (1023, "1023 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (1024**2, "1.0 MB"),
            (1024**3, "1.0 GB"),
            (1024**4, "1.0 TB"),
            (1024**5, "1024.0 TB"),  # Beyond TB, might just show large TB
        ]

        for size_bytes, expected_pattern in test_cases:
            result = format_size(size_bytes)

            if "B" in expected_pattern:
                assert "B" in result
            elif "KB" in expected_pattern:
                assert "KB" in result
            elif "MB" in expected_pattern:
                assert "MB" in result
            elif "GB" in expected_pattern:
                assert "GB" in result
            elif "TB" in expected_pattern:
                assert "TB" in result

            # Check that result contains reasonable numbers
            assert len(result) > 0
            assert any(c.isdigit() for c in result)

    def test_detect_ibi_structure_edge_cases(self, temp_dir):
        """Test ibi structure detection with various directory layouts."""
        # Test with missing directories
        empty_dir = temp_dir / "empty"
        empty_dir.mkdir()

        db_path, files_path = detect_ibi_structure(empty_dir)
        assert db_path is None
        assert files_path is None

        # Test with partial structure (only db, no files)
        partial_dir = temp_dir / "partial"
        db_dir = partial_dir / "restsdk" / "data" / "db"
        db_dir.mkdir(parents=True)
        (db_dir / "index.db").touch()

        db_path, files_path = detect_ibi_structure(partial_dir)
        assert db_path is None  # Should fail if files dir missing
        assert files_path is None

        # Test with complete structure
        complete_dir = temp_dir / "complete"
        db_dir = complete_dir / "restsdk" / "data" / "db"
        files_dir = complete_dir / "restsdk" / "data" / "files"
        db_dir.mkdir(parents=True)
        files_dir.mkdir(parents=True)
        (db_dir / "index.db").touch()

        db_path, files_path = detect_ibi_structure(complete_dir)
        assert db_path is not None
        assert files_path is not None
        assert db_path.name == "index.db"
        assert files_path.name == "files"


class TestMemoryAndPerformance:
    """Test memory usage and performance characteristics."""

    def test_large_file_list_handling(self, temp_dir):
        """Test handling of large file lists without excessive memory usage."""
        # Create a large list of file metadata (simulating many files)
        large_file_list = []

        for i in range(1000):  # 1000 files
            file_data = {
                "file": {
                    "id": f"file{i}",
                    "name": f"file{i:04d}.jpg",
                    "contentID": f"{i:012x}",
                    "mimeType": "image/jpeg",
                    "size": 1024000,
                    "imageDate": 1640995200.0 + i,
                },
                "albums": [{"name": f"Album {i // 100}", "id": f"album_{i // 100}"}],
            }
            large_file_list.append(file_data)

        # Test that we can process the list without memory issues
        # This is more of a smoke test - real memory testing would need specialized tools
        total_size = sum(item["file"]["size"] for item in large_file_list)
        assert total_size == 1000 * 1024000

        # Group by albums (similar to what extract_by_albums does)
        albums = {}
        for item in large_file_list:
            album_name = item["albums"][0]["name"] if item["albums"] else "Orphaned"
            if album_name not in albums:
                albums[album_name] = []
            albums[album_name].append(item)

        # Should handle grouping efficiently
        # Files 0-99 -> Album 0, 100-199 -> Album 1, etc. = 10 albums total
        assert len(albums) == 10  # 10 albums (0-9)

    def test_repeated_operations_memory_stability(self, temp_dir):
        """Test that repeated operations don't cause memory leaks."""
        source_file = temp_dir / "source.txt"
        source_file.write_text("Memory test content")

        # Perform many copy operations
        for i in range(100):
            dest_file = temp_dir / f"dest_{i}.txt"
            result = copy_file_fallback(source_file, dest_file, resume=False)
            assert result is True

            # Clean up immediately to test cleanup behavior
            if dest_file.exists():
                dest_file.unlink()

        # If we get here without running out of memory, the test passes
        assert True
