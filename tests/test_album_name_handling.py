"""Tests for album name sanitization and edge cases."""

import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from ibirecovery.extract_files import extract_by_albums, sanitize_album_name


class TestSanitizeAlbumNameFunction:
    """Test the sanitize_album_name function directly."""

    def test_empty_string_handling(self):
        """Test that empty strings get descriptive names."""
        result, changed = sanitize_album_name("")
        assert result == "Unknown_Album_Empty"
        assert changed is True

    def test_whitespace_only_handling(self):
        """Test that whitespace-only strings get descriptive names."""
        test_cases = [
            "   ",  # spaces
            "\t\t",  # tabs
            "\n\n",  # newlines
            "\r\r",  # carriage returns
            " \t\n\r ",  # mixed whitespace
        ]

        for whitespace_name in test_cases:
            result, changed = sanitize_album_name(whitespace_name)
            assert result == "Unknown_Album_Whitespace"
            assert changed is True

    def test_character_replacement_preservation(self):
        """Test that problematic characters are replaced sensibly."""
        test_cases = [
            ("Album/With/Slashes", "Album_With_Slashes"),
            ("Album\\With\\Backslashes", "Album_With_Backslashes"),
            ("Album:With:Colons", "Album-With-Colons"),
            ("Album*With*Stars", "Album_star_With_star_Stars"),
            ("Album?With?Questions", "Album_With_Questions"),
            ('Album"With"Quotes', "Album'With'Quotes"),
            ("Album<With>Brackets", "Album(With)Brackets"),
            ("Album|With|Pipes", "Album_With_Pipes"),
        ]

        for original, expected in test_cases:
            result, changed = sanitize_album_name(original)
            assert (
                result == expected
            ), f"Failed for '{original}': got '{result}', expected '{expected}'"
            assert changed is True

    def test_whitespace_normalization(self):
        """Test that whitespace is normalized properly."""
        test_cases = [
            ("  Album  Name  ", "Album Name"),  # Leading/trailing spaces
            ("Album\t\tName", "Album Name"),  # Tabs to spaces
            ("Album\n\nName", "Album Name"),  # Newlines to spaces
            ("Album   Name", "Album Name"),  # Multiple spaces collapsed
        ]

        for original, expected in test_cases:
            result, changed = sanitize_album_name(original)
            assert result == expected
            assert changed is True

    def test_length_limiting(self):
        """Test that very long names are truncated sensibly."""
        long_name = "A" * 150  # Longer than 100 char limit
        result, changed = sanitize_album_name(long_name)

        assert len(result) == 100  # 97 + "..."
        assert result.endswith("...")
        assert result.startswith("A" * 97)
        assert changed is True

    def test_non_printable_character_handling(self):
        """Test handling of non-printable characters."""
        # Create name with non-printable characters
        non_printable_name = f"Album{chr(1)}{chr(2)}Name{chr(127)}"
        result, changed = sanitize_album_name(non_printable_name)

        assert result == "AlbumName"
        assert changed is True

    def test_all_non_printable_handling(self):
        """Test handling when all characters are non-printable."""
        non_printable_name = f"{chr(1)}{chr(2)}{chr(127)}"  # 3 non-printable chars
        result, changed = sanitize_album_name(non_printable_name)

        assert result == "Unknown_Album_NonPrintable_3chars"
        assert changed is True

    def test_no_changes_needed(self):
        """Test that valid names are not changed."""
        valid_names = [
            "Valid Album Name",
            "Album-With_Underscores123",
            "SimpleAlbum",
            "Album 2020",
        ]

        for name in valid_names:
            result, changed = sanitize_album_name(name)
            assert result == name
            assert changed is False

    def test_complex_mixed_case(self):
        """Test complex cases with multiple issues."""
        original = "  Album/With\\Many:Problems*?<>|  "
        expected = "Album_With_Many-Problems_star__()_"

        result, changed = sanitize_album_name(original)
        assert result == expected
        assert changed is True


class TestAlbumNameSanitization:
    """Test album name sanitization and fallback behavior."""

    @pytest.fixture
    def temp_structure(self):
        """Create temporary directory structure for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            files_dir = temp_path / "files"
            output_dir = temp_path / "output"

            files_dir.mkdir()
            output_dir.mkdir()

            # Create a test file
            test_file = files_dir / "a" / "a1b2c3d4e5f6"
            test_file.parent.mkdir(parents=True)
            test_file.write_bytes(b"test file content")

            yield {
                "files_dir": files_dir,
                "output_dir": output_dir,
                "test_file": test_file,
            }

    def test_empty_album_name_uses_fallback(self, temp_structure):
        """Test that empty album names fall back to Unknown_Album_Empty."""
        files_dir = temp_structure["files_dir"]
        output_dir = temp_structure["output_dir"]

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "cTime": 1640995200000,
                },
                "albums": [{"name": "", "id": "empty_album"}],  # Empty name
            }
        ]

        stats = {"total_files": 1, "total_size": 1024}

        # Extract files
        total_extracted, total_size = extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=False,
            dedup=False,
            fix_metadata=False,
        )

        # Should successfully extract
        assert total_extracted == 1

        # Should create Unknown_Album_Empty directory, not extract to root
        unknown_album_dir = output_dir / "Unknown_Album_Empty"
        assert unknown_album_dir.exists()
        assert unknown_album_dir.is_dir()

        # Should NOT create files directly in output_dir root
        root_files = [f for f in output_dir.iterdir() if f.is_file()]
        assert len(root_files) == 0, f"Found unexpected files in root: {root_files}"

        # File should be in Unknown_Album_Empty with time structure
        extracted_files = list(unknown_album_dir.rglob("test.jpg"))
        assert len(extracted_files) == 1

    def test_whitespace_only_album_name_uses_fallback(self, temp_structure):
        """Test that whitespace-only album names fall back to Unknown_Album."""
        files_dir = temp_structure["files_dir"]
        output_dir = temp_structure["output_dir"]

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "cTime": 1640995200000,
                },
                "albums": [
                    {"name": "   \t\n  ", "id": "whitespace_album"}
                ],  # Whitespace only
            }
        ]

        stats = {"total_files": 1, "total_size": 1024}

        # Extract files
        extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=False,
            dedup=False,
            fix_metadata=False,
        )

        # Should create Unknown_Album directory
        unknown_album_dir = output_dir / "Unknown_Album"
        assert unknown_album_dir.exists()

        # Should NOT create directories with whitespace names
        whitespace_dirs = [
            d for d in output_dir.iterdir() if d.is_dir() and not d.name.strip()
        ]
        assert len(whitespace_dirs) == 0

    def test_special_characters_only_album_name_uses_fallback(self, temp_structure):
        """Test that albums with only special characters fall back to Unknown_Album."""
        files_dir = temp_structure["files_dir"]
        output_dir = temp_structure["output_dir"]

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "cTime": 1640995200000,
                },
                "albums": [
                    {"name": "!@#$%^&*()", "id": "special_chars"}
                ],  # Special chars only
            }
        ]

        stats = {"total_files": 1, "total_size": 1024}

        # Extract files
        extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=False,
            dedup=False,
            fix_metadata=False,
        )

        # Should create Unknown_Album directory
        unknown_album_dir = output_dir / "Unknown_Album"
        assert unknown_album_dir.exists()

    def test_valid_album_name_with_leading_trailing_spaces(self, temp_structure):
        """Test that valid album names with spaces are trimmed properly."""
        files_dir = temp_structure["files_dir"]
        output_dir = temp_structure["output_dir"]

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "cTime": 1640995200000,
                },
                "albums": [
                    {"name": "  Valid Album  ", "id": "valid_album"}
                ],  # Spaces around valid name
            }
        ]

        stats = {"total_files": 1, "total_size": 1024}

        # Extract files
        extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=False,
            dedup=False,
            fix_metadata=False,
        )

        # Should create properly trimmed album directory
        valid_album_dir = output_dir / "Valid Album"
        assert valid_album_dir.exists()

        # Should NOT create directory with leading/trailing spaces
        spaced_dirs = [
            d
            for d in output_dir.iterdir()
            if d.name.startswith(" ") or d.name.endswith(" ")
        ]
        assert len(spaced_dirs) == 0

    def test_multiple_empty_albums_consolidate_to_same_fallback(self, temp_structure):
        """Test that multiple empty album names all use the same Unknown_Album directory."""
        files_dir = temp_structure["files_dir"]
        output_dir = temp_structure["output_dir"]

        # Create multiple test files
        for i in range(2, 4):  # files 2 and 3
            test_file = files_dir / "a" / f"a1b2c3d4e5f{i}"
            test_file.write_bytes(f"test file {i} content".encode())

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test1.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "cTime": 1640995200000,
                },
                "albums": [{"name": "", "id": "empty_album1"}],  # Empty name
            },
            {
                "file": {
                    "id": "file2",
                    "name": "test2.jpg",
                    "contentID": "a1b2c3d4e5f2",
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "cTime": 1640995200000,
                },
                "albums": [{"name": "   ", "id": "empty_album2"}],  # Whitespace only
            },
            {
                "file": {
                    "id": "file3",
                    "name": "test3.jpg",
                    "contentID": "a1b2c3d4e5f3",
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "cTime": 1640995200000,
                },
                "albums": [{"name": "!@#", "id": "empty_album3"}],  # Special chars only
            },
        ]

        stats = {"total_files": 3, "total_size": 3072}

        # Extract files
        extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=False,
            dedup=False,
            fix_metadata=False,
        )

        # Should create only ONE Unknown_Album directory
        unknown_album_dirs = [
            d for d in output_dir.iterdir() if d.name == "Unknown_Album"
        ]
        assert len(unknown_album_dirs) == 1

        # All files should be in that directory
        unknown_album_dir = output_dir / "Unknown_Album"
        extracted_files = list(unknown_album_dir.rglob("*.jpg"))
        assert len(extracted_files) == 3

    def test_album_name_sanitization_preserves_safe_characters(self, temp_structure):
        """Test that valid characters are preserved in album names."""
        files_dir = temp_structure["files_dir"]
        output_dir = temp_structure["output_dir"]

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "cTime": 1640995200000,
                },
                "albums": [
                    {"name": "Album-Name_With123 Safe-Chars", "id": "safe_album"}
                ],
            }
        ]

        stats = {"total_files": 1, "total_size": 1024}

        # Extract files
        extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=False,
            dedup=False,
            fix_metadata=False,
        )

        # Should preserve safe characters
        expected_dir = output_dir / "Album-Name_With123 Safe-Chars"
        assert expected_dir.exists()

    def test_album_name_sanitization_removes_unsafe_characters(self, temp_structure):
        """Test that unsafe characters are removed from album names."""
        files_dir = temp_structure["files_dir"]
        output_dir = temp_structure["output_dir"]

        files_with_albums = [
            {
                "file": {
                    "id": "file1",
                    "name": "test.jpg",
                    "contentID": "a1b2c3d4e5f6",
                    "mimeType": "image/jpeg",
                    "size": 1024,
                    "cTime": 1640995200000,
                },
                "albums": [
                    {"name": "Album/With\\Bad:Chars*?<>|", "id": "unsafe_album"}
                ],
            }
        ]

        stats = {"total_files": 1, "total_size": 1024}

        # Extract files
        extract_by_albums(
            files_with_albums,
            files_dir,
            output_dir,
            stats,
            copy_files=True,
            use_rsync=False,
            resume=False,
            dedup=False,
            fix_metadata=False,
        )

        # Should create directory with unsafe characters removed
        expected_dir = output_dir / "AlbumWithBadChars"
        assert expected_dir.exists()

        # Should NOT create directories with unsafe characters
        unsafe_dirs = [
            d
            for d in output_dir.iterdir()
            if any(char in d.name for char in "/\\:*?<>|")
        ]
        assert len(unsafe_dirs) == 0
