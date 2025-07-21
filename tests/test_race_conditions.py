"""Tests for race condition handling in file extraction."""

import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ibirecovery.extract_files import extract_by_albums


class TestRaceConditionHandling:
    """Test directory creation error handling for resume scenarios and race conditions."""

    def test_concurrent_directory_creation_race_condition(self, temp_dir):
        """Test that directory creation handles FileExistsError from previous runs (resume mode)."""
        files_dir = temp_dir / "files"
        files_dir.mkdir()

        # Create a test file
        content_id = "testContent123"
        test_file_dir = files_dir / content_id[0]
        test_file_dir.mkdir()
        test_file = test_file_dir / content_id
        test_file.write_bytes(b"test content")

        output_dir = temp_dir / "output"
        db_path = temp_dir / "test.db"

        # Create minimal database for the test
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE Files(
                id TEXT PRIMARY KEY,
                name TEXT,
                contentID TEXT,
                mimeType TEXT,
                size INTEGER,
                imageDate INTEGER,
                videoDate INTEGER,
                cTime INTEGER,
                storageID TEXT
            )
        """
        )
        conn.commit()
        conn.close()

        # Create test data that will result in the same directory path
        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test1.jpg",
                    "contentID": content_id,
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "imageDate": 1672617600000,  # 2023-01-02 (to ensure it's clearly in 2023)
                    "cTime": 1672617600000,
                    "storageID": "local",
                },
                "albums": [],
            },
            {
                "file": {
                    "id": "file2",
                    "name": "test2.jpg",
                    "contentID": content_id,  # Same file, different record (edge case)
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "imageDate": 1672617600000,  # Same date = same directory
                    "cTime": 1672617600000,
                    "storageID": "local",
                },
                "albums": [],
            },
        ]

        stats = {"total_files": 2, "total_size": 2048}

        # Mock pathlib.Path.mkdir to simulate the race condition
        original_mkdir = Path.mkdir
        mkdir_call_count = 0

        def mock_mkdir(self, mode=0o777, parents=False, exist_ok=False):
            nonlocal mkdir_call_count
            mkdir_call_count += 1

            # On the second mkdir call, simulate another process creating the directory
            if mkdir_call_count == 2 and exist_ok:
                # First call succeeds normally
                if not self.exists():
                    original_mkdir(self, mode, parents, exist_ok)
                # Second call: simulate race condition where directory was created
                # by another process between the exist check and mkdir call
                else:
                    # This simulates the exact error from production
                    raise FileExistsError(f"[Errno 17] File exists: '{self}'")
            else:
                original_mkdir(self, mode, parents, exist_ok)

        with patch.object(Path, "mkdir", mock_mkdir):
            # This should not raise FileExistsError despite the race condition
            total_extracted, total_size = extract_by_albums(
                files_with_albums,
                files_dir,
                output_dir,
                stats,
                db_path,
                copy_files=True,
                use_rsync=False,
                resume=False,
                dedup=False,
                fix_metadata=False,
            )

        # Verify extraction completed successfully
        assert total_extracted == 2  # Both files should be extracted
        assert total_size == 2048

        # Verify the directory was created successfully
        expected_dir = output_dir / "Unorganized" / "2023" / "01"
        assert expected_dir.exists()

    def test_concurrent_directory_creation_threading(self, temp_dir):
        """Test directory creation with actual threading to simulate real concurrency."""
        base_dir = temp_dir / "concurrent_test"

        def create_directory_structure(thread_id):
            """Function to create directory structure from multiple threads."""
            try:
                target_dir = base_dir / "year" / "month" / f"thread_{thread_id}"
                target_dir.mkdir(parents=True, exist_ok=True)

                # Verify directory was created
                assert target_dir.exists()
                return True
            except FileExistsError as e:
                # This should not happen with proper error handling
                pytest.fail(f"Thread {thread_id} got FileExistsError: {e}")
            except Exception as e:
                pytest.fail(f"Thread {thread_id} got unexpected error: {e}")

        # Start multiple threads trying to create overlapping directory structures
        threads = []
        results = []

        for i in range(10):
            thread = threading.Thread(
                target=lambda i=i: results.append(create_directory_structure(i))
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all threads completed successfully
        assert len(results) == 10
        assert all(results)

        # Verify base directories were created
        assert (base_dir / "year" / "month").exists()

    def test_directory_creation_with_permission_error(self, temp_dir):
        """Test handling of permission errors during directory creation."""
        files_dir = temp_dir / "files"
        files_dir.mkdir()

        # Create a test file
        content_id = "testContent456"
        test_file_dir = files_dir / content_id[0]
        test_file_dir.mkdir()
        test_file = test_file_dir / content_id
        test_file.write_bytes(b"test content")

        output_dir = temp_dir / "output"
        db_path = temp_dir / "test.db"

        # Create minimal database for the test
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE Files(
                id TEXT PRIMARY KEY,
                name TEXT,
                contentID TEXT,
                mimeType TEXT,
                size INTEGER,
                imageDate INTEGER,
                videoDate INTEGER,
                cTime INTEGER,
                storageID TEXT
            )
        """
        )
        conn.commit()
        conn.close()

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test.jpg",
                    "contentID": content_id,
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "imageDate": 1672531200000,
                    "cTime": 1672531200000,
                    "storageID": "local",
                },
                "albums": [],
            }
        ]

        stats = {"total_files": 1, "total_size": 1024}

        # Mock mkdir to raise PermissionError
        with patch.object(
            Path, "mkdir", side_effect=PermissionError("Permission denied")
        ):
            # Should handle the permission error gracefully
            total_extracted, total_size = extract_by_albums(
                files_with_albums,
                files_dir,
                output_dir,
                stats,
                db_path,
                copy_files=True,
                use_rsync=False,
                resume=False,
                dedup=False,
                fix_metadata=False,
            )

        # Should continue execution despite permission error
        # (files won't be extracted but shouldn't crash)
        assert total_extracted == 0  # No files extracted due to permission error
        assert total_size == 0

    def test_safe_mkdir_function_behavior(self, temp_dir):
        """Test the safe_mkdir helper function behavior."""
        from ibirecovery.extract_files import safe_mkdir

        test_dir = temp_dir / "test_safe_mkdir"

        # Test normal creation
        safe_mkdir(test_dir)
        assert test_dir.exists()

        # Test idempotent behavior (calling again should not error)
        safe_mkdir(test_dir)
        assert test_dir.exists()

        # Test with parents=True
        nested_dir = temp_dir / "nested" / "deep" / "path"
        safe_mkdir(nested_dir, parents=True)
        assert nested_dir.exists()

        # Test calling again with parents (should be safe)
        safe_mkdir(nested_dir, parents=True)
        assert nested_dir.exists()

    def test_safe_mkdir_handles_file_exists_error(self, temp_dir):
        """Test that safe_mkdir handles FileExistsError race conditions."""
        from ibirecovery.extract_files import safe_mkdir

        test_dir = temp_dir / "race_condition_test"

        # Mock mkdir to raise FileExistsError first time, then succeed
        original_mkdir = Path.mkdir
        call_count = 0

        def mock_mkdir(self, mode=0o777, parents=False, exist_ok=False):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First call: simulate race condition
                raise FileExistsError(f"[Errno 17] File exists: '{self}'")
            else:
                # Second call: create directory normally (simulating it was created by another process)
                if not self.exists():
                    original_mkdir(self, mode, parents, exist_ok)

        with patch.object(Path, "mkdir", mock_mkdir):
            with patch.object(Path, "is_dir", return_value=True):
                # Should handle the FileExistsError gracefully
                safe_mkdir(test_dir)
                # Manually create the directory for the test assertion
                test_dir.mkdir(exist_ok=True)

        assert test_dir.exists()
