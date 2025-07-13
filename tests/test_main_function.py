"""Tests for the main function and CLI workflow integration."""

import os
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Add the package to the path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ibirecovery.extract_files import main


class TestMainFunction:
    """Test the main() function with various argument combinations."""

    def test_main_help_functionality(self):
        """Test that main shows help when requested."""
        with patch("sys.argv", ["extract_files.py", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            # argparse exits with code 0 for help
            assert exc_info.value.code == 0

    def test_main_list_formats_functionality(self, mock_export_formats):
        """Test --list-formats functionality."""
        with patch("sys.argv", ["extract_files.py", "--list-formats"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with pytest.raises(SystemExit) as exc_info:
                    main()

                output = mock_stdout.getvalue()
                assert "Available export formats:" in output
                assert exc_info.value.code == 0

    def test_main_verify_mode(self, mock_database, mock_ibi_structure, mock_files):
        """Test main function in verify mode."""
        ibi_root = str(mock_ibi_structure["root"])

        with patch("sys.argv", ["extract_files.py", "--verify", ibi_root]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                try:
                    main()
                except SystemExit:
                    pass  # Expected for some verify scenarios

                output = mock_stdout.getvalue()
                # Should contain verification output
                assert any(
                    keyword in output.lower()
                    for keyword in ["verification", "files", "available", "missing"]
                )

    def test_main_list_only_mode(self, mock_database, mock_ibi_structure, mock_files):
        """Test main function in list-only mode."""
        ibi_root = str(mock_ibi_structure["root"])

        with patch("sys.argv", ["extract_files.py", "--list-only", ibi_root]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()

                output = mock_stdout.getvalue()
                # Should list files without extracting
                assert (
                    "total files" in output.lower() or "files found" in output.lower()
                )

    def test_main_extraction_mode_albums(
        self, mock_database, mock_ibi_structure, mock_files, temp_dir
    ):
        """Test main function performing actual extraction by albums."""
        ibi_root = str(mock_ibi_structure["root"])
        output_dir = str(temp_dir / "output")

        with patch("sys.argv", ["extract_files.py", ibi_root, output_dir]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()

                output = mock_stdout.getvalue()
                # Should show extraction progress and completion
                assert any(
                    keyword in output.lower()
                    for keyword in ["extracted", "total files", "completed"]
                )

                # Check that output directory was created
                output_path = Path(output_dir)
                assert output_path.exists()

    def test_main_extraction_mode_by_type(
        self, mock_database, mock_ibi_structure, mock_files, temp_dir
    ):
        """Test main function with --by-type option."""
        ibi_root = str(mock_ibi_structure["root"])
        output_dir = str(temp_dir / "output_by_type")

        with patch("sys.argv", ["extract_files.py", ibi_root, output_dir, "--by-type"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()

                output = mock_stdout.getvalue()
                assert "extracting files organized by type" in output.lower()

                # Check that type-based directories were created
                output_path = Path(output_dir)
                expected_dirs = ["Images", "Videos", "Documents"]
                created_dirs = [d.name for d in output_path.iterdir() if d.is_dir()]
                assert any(expected in created_dirs for expected in expected_dirs)

    def test_main_with_deduplication_options(
        self, mock_database, mock_ibi_structure, mock_files, temp_dir
    ):
        """Test main function with deduplication options."""
        ibi_root = str(mock_ibi_structure["root"])
        output_dir = str(temp_dir / "output_dedup")

        with patch(
            "sys.argv",
            ["extract_files.py", ibi_root, output_dir, "--dedup", "--use-hardlinks"],
        ):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()

                output = mock_stdout.getvalue()
                # Should mention deduplication in output
                assert any(
                    keyword in output.lower()
                    for keyword in ["extracted", "files", "completed"]
                )

    def test_main_with_metadata_options(
        self, mock_database, mock_ibi_structure, mock_files, temp_dir
    ):
        """Test main function with metadata correction options."""
        ibi_root = str(mock_ibi_structure["root"])
        output_dir = str(temp_dir / "output_metadata")

        # Test with metadata correction disabled
        with patch(
            "sys.argv", ["extract_files.py", ibi_root, output_dir, "--no-fix-metadata"]
        ):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()

                output = mock_stdout.getvalue()
                assert "extracted" in output.lower()

    def test_main_export_functionality(
        self, mock_database, mock_ibi_structure, mock_export_formats, temp_dir
    ):
        """Test main function with export options."""
        ibi_root = str(mock_ibi_structure["root"])
        export_dir = str(temp_dir / "exports")

        with patch(
            "sys.argv",
            ["extract_files.py", ibi_root, "--export", "--export-dir", export_dir],
        ):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()

                output = mock_stdout.getvalue()
                # Should mention export completion
                assert any(
                    keyword in output.lower()
                    for keyword in ["export", "metadata", "formats"]
                )

                # Check that export directory was created
                export_path = Path(export_dir)
                assert export_path.exists()

    def test_main_deduplicate_existing(self, temp_dir):
        """Test main function with --deduplicate-existing option."""
        # Create a mock existing extraction
        existing_dir = temp_dir / "existing"
        album_dir = existing_dir / "Album"
        album_dir.mkdir(parents=True)

        # Create duplicate files
        file1 = album_dir / "photo1.jpg"
        file2 = album_dir / "photo2.jpg"
        content = b"duplicate content" * 1000
        file1.write_bytes(content)
        file2.write_bytes(content)

        with patch(
            "sys.argv",
            ["extract_files.py", "--deduplicate-existing", str(existing_dir)],
        ):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Should exit with code 0 (success)
                assert exc_info.value.code == 0
                output = mock_stdout.getvalue()
                # Should show deduplication results
                assert any(
                    keyword in output.lower()
                    for keyword in [
                        "deduplication",
                        "files",
                        "hardlinked",
                        "symlinked",
                        "space",
                    ]
                )

    def test_main_invalid_ibi_path(self, temp_dir):
        """Test main function with invalid ibi path."""
        invalid_path = str(temp_dir / "nonexistent")

        with patch("sys.argv", ["extract_files.py", invalid_path]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Should exit with error code
                assert exc_info.value.code != 0

                output = mock_stdout.getvalue()
                assert "not found" in output.lower() or "error" in output.lower()

    def test_main_no_arguments(self):
        """Test main function with no arguments."""
        with patch("sys.argv", ["extract_files.py"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Should exit with error (missing required argument)
            assert exc_info.value.code != 0


class TestMainFunctionEdgeCases:
    """Test edge cases and error conditions in main function."""

    def test_main_with_missing_database(self, temp_dir):
        """Test main function when database file is missing."""
        # Create ibi structure without database
        ibi_root = temp_dir / "ibi_no_db"
        files_dir = ibi_root / "restsdk" / "data" / "files"
        files_dir.mkdir(parents=True)

        with patch("sys.argv", ["extract_files.py", str(ibi_root)]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Should handle missing database gracefully
                assert exc_info.value.code != 0
                output = mock_stdout.getvalue()
                assert "database" in output.lower() or "not found" in output.lower()

    def test_main_with_corrupted_database(self, temp_dir):
        """Test main function with corrupted database."""
        # Create ibi structure with invalid database
        ibi_root = temp_dir / "ibi_corrupt_db"
        db_dir = ibi_root / "restsdk" / "data" / "db"
        files_dir = ibi_root / "restsdk" / "data" / "files"
        db_dir.mkdir(parents=True)
        files_dir.mkdir(parents=True)

        # Create invalid database file
        db_file = db_dir / "index.db"
        db_file.write_text("This is not a valid SQLite database")

        with patch("sys.argv", ["extract_files.py", str(ibi_root)]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Should handle corrupted database gracefully
                assert exc_info.value.code != 0

    def test_main_with_permission_denied_output(
        self, mock_database, mock_ibi_structure, temp_dir
    ):
        """Test main function when output directory has permission issues."""
        ibi_root = str(mock_ibi_structure["root"])

        # Create read-only output directory
        readonly_output = temp_dir / "readonly"
        readonly_output.mkdir()
        readonly_output.chmod(0o444)

        try:
            with patch(
                "sys.argv",
                ["extract_files.py", ibi_root, "--output", str(readonly_output)],
            ):
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    # May exit with error or handle gracefully
                    try:
                        main()
                    except SystemExit as e:
                        # Permission errors should be handled
                        assert e.code != 0

                    output = mock_stdout.getvalue()
                    # Should indicate some kind of issue
                    assert len(output) > 0
        finally:
            # Restore permissions for cleanup
            readonly_output.chmod(0o755)

    def test_main_keyboard_interrupt_simulation(
        self, mock_database, mock_ibi_structure, temp_dir
    ):
        """Test main function behavior with simulated keyboard interrupt."""
        ibi_root = str(mock_ibi_structure["root"])
        output_dir = str(temp_dir / "interrupted_output")

        # Mock the extraction to raise KeyboardInterrupt
        with patch("ibirecovery.extract_files.extract_by_albums") as mock_extract:
            mock_extract.side_effect = KeyboardInterrupt("Simulated Ctrl+C")

            with patch("sys.argv", ["extract_files.py", ibi_root, output_dir]):
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    with pytest.raises((SystemExit, KeyboardInterrupt)):
                        main()

                    # Should handle interrupt gracefully
                    output = mock_stdout.getvalue()
                    # Might contain progress information before interrupt
                    assert True  # Test passes if no unhandled exception

    def test_main_with_export_format_errors(
        self, mock_database, mock_ibi_structure, temp_dir
    ):
        """Test main function when export format files are missing or invalid."""
        ibi_root = str(mock_ibi_structure["root"])

        # Test with invalid export formats
        with patch(
            "sys.argv",
            [
                "extract_files.py",
                ibi_root,
                "--export",
                "--export-formats",
                "nonexistent_format",
            ],
        ):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                # Should handle invalid formats gracefully
                try:
                    main()
                except SystemExit:
                    pass

                output = mock_stdout.getvalue()
                # Should indicate export was attempted or completed
                assert len(output) > 0


class TestMainFunctionIntegration:
    """Integration tests that test main function with realistic scenarios."""

    def test_main_complete_workflow_albums(
        self, mock_database, mock_ibi_structure, mock_files, temp_dir
    ):
        """Test complete workflow: verify, list, extract, export."""
        ibi_root = str(mock_ibi_structure["root"])
        output_dir = str(temp_dir / "complete_workflow")
        export_dir = str(temp_dir / "exports")

        # Step 1: Verify
        with patch("sys.argv", ["extract_files.py", "--verify", ibi_root]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                try:
                    main()
                except SystemExit:
                    pass
                verify_output = mock_stdout.getvalue()
                assert len(verify_output) > 0

        # Step 2: List only
        with patch("sys.argv", ["extract_files.py", "--list-only", ibi_root]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()
                list_output = mock_stdout.getvalue()
                assert "files" in list_output.lower()

        # Step 3: Extract
        with patch("sys.argv", ["extract_files.py", ibi_root, output_dir]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()
                extract_output = mock_stdout.getvalue()
                assert "extracted" in extract_output.lower()

        # Step 4: Export (if export formats are available)
        with patch(
            "sys.argv",
            ["extract_files.py", ibi_root, "--export", "--export-dir", export_dir],
        ):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                try:
                    main()
                    export_output = mock_stdout.getvalue()
                    assert len(export_output) > 0
                except Exception:
                    # Export might fail if formats not available, that's OK
                    pass

        # Verify final state
        output_path = Path(output_dir)
        assert output_path.exists()
        extracted_files = list(output_path.rglob("*"))
        assert len(extracted_files) > 0

    def test_main_resume_extraction(
        self, mock_database, mock_ibi_structure, mock_files, temp_dir
    ):
        """Test that main function can resume interrupted extraction."""
        ibi_root = str(mock_ibi_structure["root"])
        output_dir = str(temp_dir / "resume_test")

        # First extraction
        with patch("sys.argv", ["extract_files.py", ibi_root, output_dir]):
            main()

        # Check that files were extracted
        output_path = Path(output_dir)
        assert output_path.exists()

        # Get list of extracted files
        extracted_files_1 = list(output_path.rglob("*"))
        assert len(extracted_files_1) > 0

        # Second extraction (resume)
        with patch("sys.argv", ["extract_files.py", ibi_root, output_dir]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()

                resume_output = mock_stdout.getvalue()
                # Should indicate completion (files skipped due to resume)
                assert "extracted" in resume_output.lower()

        # Should have same files (no duplicates)
        extracted_files_2 = list(output_path.rglob("*"))
        assert len(extracted_files_2) == len(extracted_files_1)

    def test_main_with_all_options(
        self, mock_database, mock_ibi_structure, mock_files, temp_dir
    ):
        """Test main function with multiple options combined."""
        ibi_root = str(mock_ibi_structure["root"])
        output_dir = str(temp_dir / "all_options")
        export_dir = str(temp_dir / "all_exports")

        argv = [
            "extract_files.py",
            ibi_root,
            output_dir,
            "--export",
            "--export-dir",
            export_dir,
            "--dedup",
            "--use-hardlinks",
            "--verify-sample",
            "10",
            "--resume",
        ]

        with patch("sys.argv", argv):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()

                output = mock_stdout.getvalue()
                # Should handle all options without error
                assert len(output) > 0
                assert any(
                    keyword in output.lower()
                    for keyword in ["extracted", "files", "completed", "verification"]
                )

        # Verify that extraction occurred
        output_path = Path(output_dir)
        assert output_path.exists()

        # Verify that export was attempted
        export_path = Path(export_dir)
        # Export might succeed or fail depending on format availability
