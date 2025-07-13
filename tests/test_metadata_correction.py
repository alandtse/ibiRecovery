"""Test metadata correction functionality during file extraction."""

import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest

# Add the package to the path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ibirecovery.extract_files import (
    copy_file_fallback,
    copy_file_with_dedup,
    set_file_metadata,
)


class TestMetadataCorrection:
    """Test file metadata timestamp correction functionality."""

    def test_set_file_metadata_image_date(self, temp_dir):
        """Test setting metadata using imageDate for image files."""
        # Create a test file
        test_file = temp_dir / "test_image.jpg"
        test_file.write_text("fake image content")

        # Target timestamp (2022-01-01 12:00:00 UTC)
        target_timestamp = 1640962800.0

        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": target_timestamp,
            "videoDate": None,
            "cTime": 1640962900.0,  # Should not be used since imageDate exists
            "birthTime": 1640962950.0,
        }

        # Apply metadata correction
        result = set_file_metadata(test_file, file_metadata)
        assert result is True

        # Verify the timestamp was set correctly
        file_stat = test_file.stat()
        assert abs(file_stat.st_mtime - target_timestamp) < 1.0
        assert abs(file_stat.st_atime - target_timestamp) < 1.0

    def test_set_file_metadata_video_date(self, temp_dir):
        """Test setting metadata using videoDate for video files."""
        test_file = temp_dir / "test_video.mp4"
        test_file.write_text("fake video content")

        target_timestamp = 1640962800.0

        file_metadata = {
            "mimeType": "video/mp4",
            "imageDate": None,
            "videoDate": target_timestamp,
            "cTime": 1640962900.0,  # Should not be used since videoDate exists
            "birthTime": 1640962950.0,
        }

        result = set_file_metadata(test_file, file_metadata)
        assert result is True

        file_stat = test_file.stat()
        assert abs(file_stat.st_mtime - target_timestamp) < 1.0

    def test_set_file_metadata_fallback_to_ctime(self, temp_dir):
        """Test fallback to cTime when imageDate/videoDate not available."""
        test_file = temp_dir / "test_document.pdf"
        test_file.write_text("fake document content")

        target_timestamp = 1640962800.0

        file_metadata = {
            "mimeType": "application/pdf",
            "imageDate": None,
            "videoDate": None,
            "cTime": target_timestamp,
            "birthTime": 1640962950.0,
        }

        result = set_file_metadata(test_file, file_metadata)
        assert result is True

        file_stat = test_file.stat()
        assert abs(file_stat.st_mtime - target_timestamp) < 1.0

    def test_set_file_metadata_fallback_to_birthtime(self, temp_dir):
        """Test fallback to birthTime when other timestamps not available."""
        test_file = temp_dir / "test_file.txt"
        test_file.write_text("fake content")

        target_timestamp = 1640962800.0

        file_metadata = {
            "mimeType": "text/plain",
            "imageDate": None,
            "videoDate": None,
            "cTime": None,
            "birthTime": target_timestamp,
        }

        result = set_file_metadata(test_file, file_metadata)
        assert result is True

        file_stat = test_file.stat()
        assert abs(file_stat.st_mtime - target_timestamp) < 1.0

    def test_set_file_metadata_no_timestamps(self, temp_dir):
        """Test behavior when no valid timestamps are available."""
        test_file = temp_dir / "test_file.txt"
        test_file.write_text("fake content")

        file_metadata = {
            "mimeType": "text/plain",
            "imageDate": None,
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        result = set_file_metadata(test_file, file_metadata)
        assert result is False  # Should return False when no timestamp available

    def test_set_file_metadata_missing_file(self, temp_dir):
        """Test error handling when file doesn't exist."""
        missing_file = temp_dir / "missing.jpg"

        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": 1640962800.0,
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        result = set_file_metadata(missing_file, file_metadata)
        assert result is False  # Should return False on error


class TestCopyWithMetadataCorrection:
    """Test copy functions with metadata correction integration."""

    def test_copy_file_fallback_with_metadata(self, temp_dir):
        """Test copy_file_fallback applies metadata correction."""
        source_file = temp_dir / "source.jpg"
        dest_file = temp_dir / "dest.jpg"
        source_file.write_text("fake image content")

        target_timestamp = 1640962800.0
        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": target_timestamp,
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        # Copy with metadata correction enabled
        result = copy_file_fallback(
            source_file,
            dest_file,
            resume=False,
            file_metadata=file_metadata,
            fix_metadata=True,
        )
        assert result is True
        assert dest_file.exists()

        # Verify metadata was applied
        file_stat = dest_file.stat()
        assert abs(file_stat.st_mtime - target_timestamp) < 1.0

    def test_copy_file_fallback_no_metadata_correction(self, temp_dir):
        """Test copy_file_fallback when metadata correction is disabled."""
        source_file = temp_dir / "source.jpg"
        dest_file = temp_dir / "dest.jpg"
        source_file.write_text("fake image content")

        original_mtime = time.time() - 3600  # 1 hour ago
        os.utime(source_file, (original_mtime, original_mtime))

        target_timestamp = 1640962800.0  # Much older timestamp
        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": target_timestamp,
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        # Copy with metadata correction disabled
        result = copy_file_fallback(
            source_file,
            dest_file,
            resume=False,
            file_metadata=file_metadata,
            fix_metadata=False,
        )
        assert result is True
        assert dest_file.exists()

        # Verify metadata was NOT applied (should be close to source file time)
        file_stat = dest_file.stat()
        source_stat = source_file.stat()
        assert (
            abs(file_stat.st_mtime - source_stat.st_mtime) < 2.0
        )  # Should be very close
        assert (
            abs(file_stat.st_mtime - target_timestamp) > 100.0
        )  # Should be very different

    def test_copy_file_fallback_resume_with_metadata(self, temp_dir):
        """Test that resume mode still applies metadata correction."""
        source_file = temp_dir / "source.jpg"
        dest_file = temp_dir / "dest.jpg"

        # Create source and destination with same content/size
        content = "fake image content"
        source_file.write_text(content)
        dest_file.write_text(content)

        # Set destination to wrong timestamp
        wrong_time = time.time() - 3600
        os.utime(dest_file, (wrong_time, wrong_time))

        target_timestamp = 1640962800.0
        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": target_timestamp,
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        # Copy with resume enabled (should skip copy but fix metadata)
        result = copy_file_fallback(
            source_file,
            dest_file,
            resume=True,
            file_metadata=file_metadata,
            fix_metadata=True,
        )
        assert result is True

        # Verify metadata was corrected even though file wasn't copied
        file_stat = dest_file.stat()
        assert abs(file_stat.st_mtime - target_timestamp) < 1.0

    def test_copy_file_with_dedup_metadata_correction(self, temp_dir):
        """Test copy_file_with_dedup applies metadata correction."""
        source_file = temp_dir / "source.jpg"
        dest_file = temp_dir / "dest.jpg"
        source_file.write_text("fake image content")

        target_timestamp = 1640962800.0
        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": target_timestamp,
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        copy_tracker = {}

        # First copy with deduplication
        success, action = copy_file_with_dedup(
            source_file,
            dest_file,
            resume=False,
            use_hardlinks=True,
            use_symlinks=False,
            copy_tracker=copy_tracker,
            file_metadata=file_metadata,
            fix_metadata=True,
        )

        assert success is True
        assert action == "copied"
        assert dest_file.exists()

        # Verify metadata was applied
        file_stat = dest_file.stat()
        assert abs(file_stat.st_mtime - target_timestamp) < 1.0


class TestMetadataStructureCompatibility:
    """Test metadata correction with realistic ibi database structures."""

    def test_metadata_with_comprehensive_export_structure(self, temp_dir):
        """Test metadata correction with data structure from get_comprehensive_export_data."""
        test_file = temp_dir / "test.jpg"
        test_file.write_text("fake content")

        # Structure matching get_comprehensive_export_data output
        file_record = {
            "id": "file1",
            "name": "test.jpg",
            "contentID": "a1b2c3d4e5f6",
            "mimeType": "image/jpeg",
            "size": 1024000,
            "imageDate": 1640995200.0,  # 2022-01-01 00:00:00
            "videoDate": None,
            "cTime": 1640995200.0,
            "birthTime": 1640995200.0,
            "imageLatitude": 37.7749,
            "imageLongitude": -122.4194,
            "imageAltitude": None,
            "imageCity": "San Francisco",
            "imageProvince": "CA",
            "imageCountry": "USA",
            "imageCameraMake": "Canon",
            "imageCameraModel": "EOS R5",
            "description": "A test image",
        }

        result = set_file_metadata(test_file, file_record)
        assert result is True

        file_stat = test_file.stat()
        assert abs(file_stat.st_mtime - 1640995200.0) < 1.0

    def test_metadata_with_files_with_albums_structure(self, temp_dir):
        """Test metadata correction with data structure from get_all_files_with_albums."""
        test_file = temp_dir / "test.mp4"
        test_file.write_text("fake content")

        # Structure matching get_all_files_with_albums output (nested in 'file' key)
        item = {
            "file": {
                "id": "file2",
                "name": "test.mp4",
                "contentID": "b2c3d4e5f6a1",
                "mimeType": "video/mp4",
                "size": 5120000,
                "imageDate": None,
                "videoDate": 1640995300.0,  # 2022-01-01 00:01:40
                "cTime": 1640995300.0,
                "birthTime": 1640995300.0,
            },
            "albums": [{"name": "Family Vacation", "id": "album1"}],
        }

        # Test with the nested file record
        result = set_file_metadata(test_file, item["file"])
        assert result is True

        file_stat = test_file.stat()
        assert abs(file_stat.st_mtime - 1640995300.0) < 1.0

    def test_metadata_priority_order(self, temp_dir):
        """Test that metadata timestamp priority works correctly."""
        # Test image file: imageDate should win over videoDate
        image_file = temp_dir / "test.jpg"
        image_file.write_text("fake content")

        image_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": 1640995200.0,  # Should be used
            "videoDate": 1640995300.0,  # Should be ignored for images
            "cTime": 1640995400.0,  # Should be ignored when imageDate exists
            "birthTime": 1640995500.0,  # Should be ignored when imageDate exists
        }

        set_file_metadata(image_file, image_metadata)
        image_stat = image_file.stat()
        assert abs(image_stat.st_mtime - 1640995200.0) < 1.0

        # Test video file: videoDate should win over imageDate
        video_file = temp_dir / "test.mp4"
        video_file.write_text("fake content")

        video_metadata = {
            "mimeType": "video/mp4",
            "imageDate": 1640995200.0,  # Should be ignored for videos
            "videoDate": 1640995300.0,  # Should be used
            "cTime": 1640995400.0,  # Should be ignored when videoDate exists
            "birthTime": 1640995500.0,  # Should be ignored when videoDate exists
        }

        set_file_metadata(video_file, video_metadata)
        video_stat = video_file.stat()
        assert abs(video_stat.st_mtime - 1640995300.0) < 1.0

    def test_timestamp_overflow_error(self, temp_dir):
        """Test that timestamp overflow errors are handled gracefully."""
        test_file = temp_dir / "test_overflow.jpg"
        test_file.write_text("fake content")

        # Store original timestamp for comparison
        original_stat = test_file.stat()
        original_mtime = original_stat.st_mtime

        # Test with extremely large timestamp that causes OverflowError
        # This simulates the real-world bug from the error report
        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": 9999999999999999999,  # Way beyond platform limits
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        # Should return False but not crash
        result = set_file_metadata(test_file, file_metadata)
        assert result is False

        # File should still exist and timestamp should be unchanged
        assert test_file.exists()
        current_stat = test_file.stat()
        # Timestamp should be unchanged (within a small tolerance for file system precision)
        assert abs(current_stat.st_mtime - original_mtime) < 1.0

    def test_timestamp_negative_overflow(self, temp_dir):
        """Test handling of negative timestamps that might cause overflow."""
        test_file = temp_dir / "test_negative.jpg"
        test_file.write_text("fake content")

        original_stat = test_file.stat()
        original_mtime = original_stat.st_mtime

        # Test with extremely negative timestamp
        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": -9999999999999999999,  # Extremely negative
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        # Should return False but not crash
        result = set_file_metadata(test_file, file_metadata)
        assert result is False

        # File should still exist and timestamp should be unchanged
        assert test_file.exists()
        current_stat = test_file.stat()
        assert abs(current_stat.st_mtime - original_mtime) < 1.0

    def test_timestamp_platform_limits(self, temp_dir):
        """Test edge cases around platform timestamp limits."""
        test_file = temp_dir / "test_limits.jpg"
        test_file.write_text("fake content")

        # Test with various problematic timestamps
        problematic_timestamps = [
            float("inf"),  # Infinity
            float("-inf"),  # Negative infinity
            float("nan"),  # NaN
            2**63,  # Likely beyond many platform limits
            -(2**63),  # Large negative number
        ]

        for bad_timestamp in problematic_timestamps:
            original_stat = test_file.stat()
            original_mtime = original_stat.st_mtime

            file_metadata = {
                "mimeType": "image/jpeg",
                "imageDate": bad_timestamp,
                "videoDate": None,
                "cTime": None,
                "birthTime": None,
            }

            # Should handle gracefully without crashing
            result = set_file_metadata(test_file, file_metadata)
            assert result is False

            # File should still exist
            assert test_file.exists()

    def test_timestamp_milliseconds_conversion(self, temp_dir):
        """Test that millisecond timestamps are properly converted to seconds."""
        test_file = temp_dir / "test_milliseconds.jpg"
        test_file.write_text("fake content")

        # Test with millisecond timestamp (like the ones from the user's error)
        # 1673995478000 ms = 1673995478 s = 2023-01-17 21:04:38 UTC
        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": 1673995478000,  # Milliseconds since epoch
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        # Should convert and succeed
        result = set_file_metadata(test_file, file_metadata)
        assert result is True

        # Verify the timestamp was set correctly (converted to seconds)
        file_stat = test_file.stat()
        expected_timestamp = 1673995478.0  # Seconds since epoch
        assert abs(file_stat.st_mtime - expected_timestamp) < 1.0

    def test_timestamp_microseconds_conversion(self, temp_dir):
        """Test that microsecond timestamps are properly converted to seconds."""
        test_file = temp_dir / "test_microseconds.jpg"
        test_file.write_text("fake content")

        # Test with microsecond timestamp
        # 1673995478000000 μs = 1673995478 s = 2023-01-17 21:04:38 UTC
        file_metadata = {
            "mimeType": "image/jpeg",
            "imageDate": 1673995478000000,  # Microseconds since epoch
            "videoDate": None,
            "cTime": None,
            "birthTime": None,
        }

        # Should convert and succeed
        result = set_file_metadata(test_file, file_metadata)
        assert result is True

        # Verify the timestamp was set correctly (converted to seconds)
        file_stat = test_file.stat()
        expected_timestamp = 1673995478.0  # Seconds since epoch
        assert abs(file_stat.st_mtime - expected_timestamp) < 1.0
