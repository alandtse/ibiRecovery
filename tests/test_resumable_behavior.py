"""Test resumable and sync behavior of extraction."""

import os
import sys
import time
from pathlib import Path

import pytest

# Add the package to the path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ibirecovery.extract_files import copy_file_fallback, copy_file_with_dedup


class TestResumableBehavior:
    """Test that extraction can be run repeatedly with sync-like behavior."""

    def test_copy_file_fallback_sync_behavior(self, temp_dir):
        """Test that copy_file_fallback acts like sync when run repeatedly."""
        source = temp_dir / "source.jpg"
        dest = temp_dir / "dest.jpg"

        # Create source with specific content and timestamp
        content = "original image content"
        source.write_text(content)
        original_timestamp = 1640962800.0  # 2022-01-01
        os.utime(source, (original_timestamp, original_timestamp))

        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": original_timestamp,
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        # First run - should copy
        result1 = copy_file_fallback(
            source, dest, resume=True, file_metadata=file_metadata, fix_metadata=True
        )
        assert result1 is True
        assert dest.exists()
        assert dest.read_text() == content

        # Verify timestamp was set
        dest_stat = dest.stat()
        assert abs(dest_stat.st_mtime - original_timestamp) < 1.0

        # Second run - should skip but still fix metadata if needed
        # Modify dest timestamp to test metadata correction on resume
        wrong_timestamp = time.time() - 3600
        os.utime(dest, (wrong_timestamp, wrong_timestamp))

        result2 = copy_file_fallback(
            source, dest, resume=True, file_metadata=file_metadata, fix_metadata=True
        )
        assert result2 is True
        assert dest.exists()
        assert dest.read_text() == content  # Same content

        # Verify timestamp was corrected even though copy was skipped
        dest_stat = dest.stat()
        assert abs(dest_stat.st_mtime - original_timestamp) < 1.0

        # Third run - should skip and leave metadata alone
        result3 = copy_file_fallback(
            source, dest, resume=True, file_metadata=file_metadata, fix_metadata=True
        )
        assert result3 is True

        # Content and timestamp should remain correct
        assert dest.read_text() == content
        dest_stat = dest.stat()
        assert abs(dest_stat.st_mtime - original_timestamp) < 1.0

    def test_copy_file_fallback_detects_changes(self, temp_dir):
        """Test that copy_file_fallback detects when source file changes."""
        source = temp_dir / "source.txt"
        dest = temp_dir / "dest.txt"

        # First version
        content1 = "version 1"
        source.write_text(content1)

        result1 = copy_file_fallback(source, dest, resume=True)
        assert result1 is True
        assert dest.read_text() == content1

        # Change source content (different size)
        content2 = "version 2 with more content"
        source.write_text(content2)

        # Should detect change and copy new version
        result2 = copy_file_fallback(source, dest, resume=True)
        assert result2 is True
        assert dest.read_text() == content2

    def test_copy_with_dedup_sync_behavior(self, temp_dir):
        """Test that copy_file_with_dedup provides sync behavior."""
        source = temp_dir / "source.jpg"
        dest1 = temp_dir / "dest1.jpg"
        dest2 = temp_dir / "dest2.jpg"

        content = "image content"
        source.write_text(content)

        target_timestamp = 1640962800.0
        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": target_timestamp,
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        copy_tracker = {}

        # First copy
        success1, action1 = copy_file_with_dedup(
            source,
            dest1,
            resume=True,
            copy_tracker=copy_tracker,
            file_metadata=file_metadata,
            fix_metadata=True,
        )
        assert success1 is True
        assert action1 == "copied"
        assert dest1.exists()

        # Second copy of same content - should hardlink
        success2, action2 = copy_file_with_dedup(
            source,
            dest2,
            resume=True,
            copy_tracker=copy_tracker,
            file_metadata=file_metadata,
            fix_metadata=True,
        )
        assert success2 is True
        assert action2 == "hardlinked"
        assert dest2.exists()

        # Re-run first copy - should skip
        success3, action3 = copy_file_with_dedup(
            source,
            dest1,
            resume=True,
            copy_tracker=copy_tracker,
            file_metadata=file_metadata,
            fix_metadata=True,
        )
        assert success3 is True
        assert action3 == "skipped"

        # Verify all files have correct timestamps
        for dest_file in [dest1, dest2]:
            dest_stat = dest_file.stat()
            assert abs(dest_stat.st_mtime - target_timestamp) < 1.0

    def test_metadata_correction_idempotent(self, temp_dir):
        """Test that metadata correction is idempotent (can be run multiple times safely)."""
        test_file = temp_dir / "test.jpg"
        test_file.write_text("fake content")

        target_timestamp = 1640962800.0
        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": target_timestamp,
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        # Apply metadata correction multiple times
        for i in range(3):
            # Simulate resume behavior - file exists with same size
            result = copy_file_fallback(
                test_file,
                test_file,
                resume=True,
                file_metadata=file_metadata,
                fix_metadata=True,
            )
            assert result is True

            # Verify timestamp is correct each time
            file_stat = test_file.stat()
            assert abs(file_stat.st_mtime - target_timestamp) < 1.0

    def test_partial_metadata_robustness(self, temp_dir):
        """Test that extraction handles partial/missing metadata gracefully."""
        test_file = temp_dir / "test.mp4"
        test_file.write_text("fake video")

        # Test with missing imageDate/videoDate but valid cTime
        partial_metadata = {
            "mimeType": "video/mp4",
            "imageDate": None,
            "videoDate": None,  # Video file but no videoDate
            "cTime": 1640962800.0,
            "birthTime": None,
        }

        result = copy_file_fallback(
            test_file,
            test_file,
            resume=True,
            file_metadata=partial_metadata,
            fix_metadata=True,
        )
        assert result is True

        # Should fall back to cTime
        file_stat = test_file.stat()
        assert abs(file_stat.st_mtime - 1640962800.0) < 1.0

        # Test with completely missing timestamps
        empty_metadata = {
            "mimeType": "video/mp4",
            "imageDate": None,
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        # Should still succeed even if metadata correction fails
        result = copy_file_fallback(
            test_file,
            test_file,
            resume=True,
            file_metadata=empty_metadata,
            fix_metadata=True,
        )
        assert result is True
