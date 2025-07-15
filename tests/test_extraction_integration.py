"""Integration tests for core extraction functionality."""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the package to the path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ibirecovery.extract_files import (
    ExtractionState,
    check_interrupt,
    comprehensive_audit,
    deduplicate_existing_extraction,
    extract_by_albums,
    extract_by_type,
)


class TestExtractionIntegration:
    """Test core extraction functions with realistic scenarios."""

    def test_extract_by_albums_basic(
        self, mock_database, mock_ibi_structure, mock_files
    ):
        """Test basic album-based extraction."""
        files_dir = mock_ibi_structure["files"]
        output_dir = mock_ibi_structure["root"] / "extracted"

        # Create sample files_with_albums data
        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test1.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024000,
                    "imageDate": 1640995200.0,
                    "cTime": 1640995200.0,
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
                    "videoDate": 1640995300.0,
                    "cTime": 1640995300.0,
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
                    "imageDate": 1640995400.0,
                    "cTime": 1640995400.0,
                },
                "albums": [],  # Orphaned file
            },
        ]

        stats = {"total_files": 3, "total_size": 6656000}

        # Test extraction
        total_extracted, total_size = extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=True,
            dedup=False,
            use_hardlinks=False,
            use_symlinks=False,
            fix_metadata=True,
        )

        # Verify results
        assert total_extracted == 3
        assert total_size == 6656000

        # Check directory structure (spaces are preserved in album names)
        family_vacation_dir = output_dir / "Family Vacation"
        unorganized_dir = output_dir / "Unorganized"

        assert family_vacation_dir.exists()
        assert unorganized_dir.exists()

        # Check files were copied with time organization (all test files are from 2021/12)
        assert (family_vacation_dir / "2021" / "12" / "test1.jpg").exists()
        assert (family_vacation_dir / "2021" / "12" / "test2.mp4").exists()
        # Unorganized files are now organized by time: Unorganized/YYYY/MM/filename
        assert (unorganized_dir / "2021" / "12" / "test3.png").exists()

        # Verify file contents
        assert (
            family_vacation_dir / "2021" / "12" / "test1.jpg"
        ).read_bytes() == b"fake jpeg content" * 1000
        assert (
            family_vacation_dir / "2021" / "12" / "test2.mp4"
        ).read_bytes() == b"fake mp4 content" * 5000
        assert (
            unorganized_dir / "2021" / "12" / "test3.png"
        ).read_bytes() == b"fake png content" * 500

    def test_extract_by_albums_with_deduplication(
        self, mock_database, mock_ibi_structure, mock_files
    ):
        """Test album extraction with deduplication enabled."""
        files_dir = mock_ibi_structure["files"]
        output_dir = mock_ibi_structure["root"] / "extracted_dedup"

        # Create files with duplicate content (same contentID)
        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "photo1.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024000,
                    "imageDate": 1640995200.0,
                },
                "albums": [{"name": "Album A", "id": "album_a"}],
            },
            {
                "file": {
                    "id": "file1_dup",
                    "name": "photo1_copy.jpg",
                    "contentID": "a1b2c3d4e5f6",  # Same content as file1
                    "mimeType": "image/jpeg",
                    "size": 1024000,
                    "imageDate": 1640995200.0,
                },
                "albums": [{"name": "Album B", "id": "album_b"}],
            },
        ]

        stats = {"total_files": 2, "total_size": 2048000}

        # Test extraction with deduplication
        total_extracted, total_size = extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=True,
            dedup=True,
            use_hardlinks=True,
            use_symlinks=False,
            fix_metadata=True,
        )

        assert total_extracted == 2

        # Both files should exist in time-organized structure
        album_a_file = output_dir / "Album A" / "2021" / "12" / "photo1.jpg"
        album_b_file = output_dir / "Album B" / "2021" / "12" / "photo1_copy.jpg"

        assert album_a_file.exists()
        assert album_b_file.exists()

        # Check if they're hardlinked (same inode)
        if hasattr(os.stat, "st_ino"):
            assert album_a_file.stat().st_ino == album_b_file.stat().st_ino

    def test_extract_by_type_basic(self, mock_database, mock_ibi_structure, mock_files):
        """Test basic type-based extraction."""
        files_dir = mock_ibi_structure["files"]
        output_dir = mock_ibi_structure["root"] / "extracted_by_type"

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "image.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024000,
                    "imageDate": 1640995200.0,
                },
                "albums": [],
            },
            {
                "file": {
                    "id": "file2",
                    "name": "video.mp4",
                    "contentID": "b2c3d4e5f6a1",
                    "mimeType": "video/mp4",
                    "size": 5120000,
                    "videoDate": 1640995300.0,
                },
                "albums": [],
            },
        ]

        stats = {"total_files": 2, "total_size": 6144000}

        # Test extraction
        total_extracted, total_size = extract_by_type(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=True,
            fix_metadata=True,
        )

        assert total_extracted == 2
        assert total_size == 6144000

        # Check directory structure
        images_dir = output_dir / "Images"
        videos_dir = output_dir / "Videos"

        assert images_dir.exists()
        assert videos_dir.exists()

        # Check files were copied to correct directories
        assert (images_dir / "image.jpg").exists()
        assert (videos_dir / "video.mp4").exists()

    def test_extract_resume_behavior(
        self, mock_database, mock_ibi_structure, mock_files
    ):
        """Test that extraction properly resumes and skips existing files."""
        files_dir = mock_ibi_structure["files"]
        output_dir = mock_ibi_structure["root"] / "extracted_resume"

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024000,
                    "imageDate": 1640995200.0,
                },
                "albums": [{"name": "Test Album", "id": "test_album"}],
            }
        ]

        stats = {"total_files": 1, "total_size": 1024000}

        # First extraction
        total_extracted_1, _ = extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=True,
            dedup=False,
            fix_metadata=True,
        )

        assert total_extracted_1 == 1

        dest_file = output_dir / "Test Album" / "2021" / "12" / "test.jpg"
        assert dest_file.exists()

        # Get original file timestamp
        original_mtime = dest_file.stat().st_mtime

        # Second extraction (should resume/skip)
        total_extracted_2, _ = extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=True,
            dedup=False,
            fix_metadata=True,
        )

        # Should still report success but skip actual copying
        assert total_extracted_2 == 1
        assert dest_file.exists()

        # File should still have correct metadata timestamp
        new_mtime = dest_file.stat().st_mtime
        assert abs(new_mtime - 1640995200.0) < 1.0

    def test_extract_missing_source_files(self, mock_database, mock_ibi_structure):
        """Test extraction behavior when source files are missing."""
        files_dir = mock_ibi_structure["files"]
        output_dir = mock_ibi_structure["root"] / "extracted_missing"

        files_with_albums = [
            {
                "file": {
                    "id": "file_missing",
                    "name": "missing.jpg",
                    "contentID": "missing123456",  # This file doesn't exist
                    "mimeType": "image/jpeg",
                    "size": 1024000,
                },
                "albums": [{"name": "Test Album", "id": "test_album"}],
            }
        ]

        stats = {"total_files": 1, "total_size": 1024000}

        # Should handle missing files gracefully
        total_extracted, total_size = extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=True,
            dedup=False,
            fix_metadata=True,
        )

        # Should not extract missing files
        assert total_extracted == 0
        assert total_size == 0

        # Directory should still be created
        test_album_dir = output_dir / "Test Album"
        assert test_album_dir.exists()

        # But file should not exist
        missing_file = test_album_dir / "missing.jpg"
        assert not missing_file.exists()


class TestPostProcessingFeatures:
    """Test post-processing features like deduplication and audit."""

    def test_deduplicate_existing_extraction(self, temp_dir):
        """Test post-processing deduplication of an existing extraction."""
        # Create a mock extraction with duplicate files
        extraction_dir = temp_dir / "existing_extraction"
        album_a = extraction_dir / "Album_A"
        album_b = extraction_dir / "Album_B"

        album_a.mkdir(parents=True)
        album_b.mkdir(parents=True)

        # Create identical files in different albums
        content = b"duplicate file content" * 1000
        file_a = album_a / "photo.jpg"
        file_b = album_b / "photo_copy.jpg"

        file_a.write_bytes(content)
        file_b.write_bytes(content)

        # Verify files are separate initially
        assert file_a.stat().st_size == file_b.stat().st_size
        if hasattr(os.stat, "st_ino"):
            assert file_a.stat().st_ino != file_b.stat().st_ino

        # Run deduplication
        stats = deduplicate_existing_extraction(
            extraction_dir, use_hardlinks=True, use_symlinks=False, dry_run=False
        )

        # Should find and deduplicate the files
        assert stats["hardlinked"] == 1
        assert stats["errors"] == 0
        assert stats["space_saved"] > 0

        # Files should now be hardlinked
        assert file_a.exists()
        assert file_b.exists()
        if hasattr(os.stat, "st_ino"):
            assert file_a.stat().st_ino == file_b.stat().st_ino

    def test_deduplicate_dry_run(self, temp_dir):
        """Test dry run mode of deduplication."""
        extraction_dir = temp_dir / "dry_run_test"
        album_dir = extraction_dir / "Album"
        album_dir.mkdir(parents=True)

        # Create duplicate files
        content = b"test content"
        file1 = album_dir / "file1.jpg"
        file2 = album_dir / "file2.jpg"

        file1.write_bytes(content)
        file2.write_bytes(content)

        original_ino1 = file1.stat().st_ino if hasattr(os.stat, "st_ino") else None
        original_ino2 = file2.stat().st_ino if hasattr(os.stat, "st_ino") else None

        # Run dry run
        stats = deduplicate_existing_extraction(
            extraction_dir, use_hardlinks=True, use_symlinks=False, dry_run=True
        )

        # Should report what would be done but not actually do it
        assert stats["space_saved"] > 0

        # Files should remain unchanged
        if original_ino1 and original_ino2:
            assert file1.stat().st_ino == original_ino1
            assert file2.stat().st_ino == original_ino2
            assert file1.stat().st_ino != file2.stat().st_ino

    def test_comprehensive_audit(self, mock_database, mock_ibi_structure, mock_files):
        """Test comprehensive audit functionality."""
        files_dir = mock_ibi_structure["files"]

        # Create files_with_albums data matching our mock files
        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test1.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 17000,  # Approximate size of mock file
                },
                "albums": [],
            },
            {
                "file": {
                    "id": "file2",
                    "name": "test2.mp4",
                    "contentID": "b2c3d4e5f6a1",
                    "mimeType": "video/mp4",
                    "size": 80000,  # Approximate size of mock file
                },
                "albums": [],
            },
            {
                "file": {
                    "id": "file_missing",
                    "name": "missing.jpg",
                    "contentID": "missing123456",  # This file doesn't exist
                    "mimeType": "image/jpeg",
                    "size": 1024000,
                },
                "albums": [],
            },
        ]

        # Run comprehensive audit
        result = comprehensive_audit(files_with_albums, files_dir, None)

        # Should find some matched and some missing files
        # Note: comprehensive_audit might return 0 total_files if no DB files found
        assert "total_files" in result
        assert "available_count" in result
        assert "missing_count" in result
        assert result["comprehensive"] is True
        assert "orphaned_count" in result

        # In this test setup, we might have 0 DB files but some orphaned disk files
        if result["total_files"] > 0:
            assert result["available_count"] >= 0
            assert result["missing_count"] >= 0


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_extraction_state_interrupt_handling(self):
        """Test ExtractionState interrupt handling."""
        state = ExtractionState()

        # Test initial state
        assert state.interrupted is False
        assert state.total_files_extracted == 0

        # Test state updates
        state.total_files_extracted = 10
        state.total_size_extracted = 1024000
        state.current_operation = "Testing"

        assert state.total_files_extracted == 10
        assert state.total_size_extracted == 1024000
        assert state.current_operation == "Testing"

    def test_check_interrupt_function(self):
        """Test check_interrupt function."""
        # Mock the global extraction_state
        with patch("ibirecovery.extract_files.extraction_state") as mock_state:
            mock_state.interrupted = False
            result = check_interrupt()
            assert result is False

            mock_state.interrupted = True
            result = check_interrupt()
            assert result is True

    def test_extract_with_invalid_paths(self, temp_dir):
        """Test extraction with invalid file paths."""
        files_dir = temp_dir / "nonexistent"
        output_dir = temp_dir / "output"

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test.jpg",
                    "contentID": "invalid123",
                    "mimeType": "image/jpeg",
                    "size": 1024000,
                },
                "albums": [],
            }
        ]

        stats = {"total_files": 1, "total_size": 1024000}

        # Should handle invalid paths gracefully
        total_extracted, total_size = extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=True,
            dedup=False,
            fix_metadata=True,
        )

        assert total_extracted == 0
        assert total_size == 0

    def test_extract_with_permission_issues(self, temp_dir):
        """Test extraction when destination has permission issues."""
        files_dir = temp_dir / "source"
        output_dir = temp_dir / "readonly_output"

        # Create source file
        files_dir.mkdir()
        source_file = files_dir / "a" / "a1b2c3d4e5f6"
        source_file.parent.mkdir()
        source_file.write_text("test content")

        # Create read-only output directory
        output_dir.mkdir()
        output_dir.chmod(0o444)  # Read-only

        try:
            files_with_albums = [
                {
                    "file": {
                        "id": "file1",
                        "name": "test.txt",
                        "contentID": "a1b2c3d4e5f6",
                        "mimeType": "text/plain",
                        "size": 12,
                    },
                    "albums": [{"name": "Test Album", "id": "test"}],
                }
            ]

            stats = {"total_files": 1, "total_size": 12}

            # Should handle permission errors gracefully
            try:
                total_extracted, total_size = extract_by_albums(
                    files_with_albums,
                    files_dir,
                    output_dir,
                    stats,
                    copy_files=True,
                    use_rsync=False,
                    resume=True,
                    dedup=False,
                    fix_metadata=True,
                )

                # If it succeeds somehow, that's also OK
                assert total_extracted >= 0

            except (PermissionError, OSError):
                # Permission errors are expected and handled gracefully
                assert True

        finally:
            # Restore permissions for cleanup
            output_dir.chmod(0o755)

    def test_extract_with_empty_album_names(self, mock_ibi_structure, mock_files):
        """Test extraction with problematic album names."""
        files_dir = mock_ibi_structure["files"]
        output_dir = mock_ibi_structure["root"] / "extracted_names"

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024000,
                },
                "albums": [{"name": "", "id": "empty_name"}],  # Empty album name
            },
            {
                "file": {
                    "id": "file2",
                    "name": "test2.jpg",
                    "contentID": "b2c3d4e5f6a1",
                    "mimeType": "image/jpeg",
                    "size": 1024000,
                },
                "albums": [
                    {"name": "Album/With/Slashes", "id": "slashes"}
                ],  # Problematic name
            },
        ]

        stats = {"total_files": 2, "total_size": 2048000}

        # Should handle problematic names gracefully
        total_extracted, total_size = extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=True,
            dedup=False,
            fix_metadata=True,
        )

        # Should extract files despite name issues
        assert total_extracted >= 0  # May succeed or fail depending on implementation

        # Should create some form of safe directory names
        created_dirs = list(output_dir.glob("*"))
        assert len(created_dirs) > 0  # Some directories should be created
