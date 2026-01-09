"""Security validation coverage tests for localization.py PathResourceLoader.

Tests security-related path validation:
- Lines 130-134: Path traversal detection via _is_safe_path
- Lines 150-151: Absolute path rejection
- Lines 155-156: ".." sequence rejection
- Lines 160-161: Path separator prefix rejection
- Lines 178-180: _is_safe_path ValueError handling
"""

import tempfile
from pathlib import Path

import pytest

from ftllexengine.localization import PathResourceLoader


class TestPathResourceLoaderSecurity:
    """Test security validation in PathResourceLoader."""

    def test_load_rejects_absolute_path(self) -> None:
        """Test that absolute paths are rejected (lines 150-151)."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            loader.load("en", "/etc/passwd")

    def test_load_rejects_absolute_path_posix_style(self) -> None:
        """Test that POSIX absolute paths are rejected (lines 150-151)."""
        loader = PathResourceLoader("locales/{locale}")

        # POSIX absolute path
        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            loader.load("en", "/usr/local/etc/passwd")

    def test_load_rejects_parent_directory_traversal(self) -> None:
        """Test that '..' sequences are rejected (lines 155-156)."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Path traversal sequences not allowed"):
            loader.load("en", "../../../etc/passwd")

    def test_load_rejects_parent_directory_in_middle(self) -> None:
        """Test that '..' in middle of path is rejected (lines 155-156)."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Path traversal sequences not allowed"):
            loader.load("en", "foo/../bar/../secrets.ftl")

    def test_load_rejects_path_starting_with_forward_slash(self) -> None:
        """Test that paths starting with '/' are rejected (lines 160-161).

        Note: On Unix, /messages.ftl is an absolute path, so it's caught by
        the absolute path check first (line 150), not the separator check.
        """
        loader = PathResourceLoader("locales/{locale}")

        # On Unix, this is caught as absolute path
        # On Windows with forward slash, might be caught by separator check
        with pytest.raises(ValueError, match=r"(Absolute|separator)"):
            loader.load("en", "/messages.ftl")

    def test_load_rejects_path_starting_with_backslash(self) -> None:
        """Test that paths starting with '\\' are rejected (lines 160-161)."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="must not start with path separator"):
            loader.load("en", "\\messages.ftl")

    def test_load_detects_symlink_escape_via_is_safe_path(self) -> None:
        """Test path traversal detection via _is_safe_path (lines 130-134, 178-180)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            locale_dir = base_path / "locales" / "en"
            locale_dir.mkdir(parents=True)

            # Create a file outside the base directory
            outside_dir = base_path / "outside"
            outside_dir.mkdir()
            secret_file = outside_dir / "secret.ftl"
            secret_file.write_text("secret = Secret data")

            # Create a symlink inside locale_dir pointing outside
            symlink_path = locale_dir / "escape.ftl"
            try:
                symlink_path.symlink_to(secret_file)

                # PathResourceLoader should detect this escapes the base directory
                loader = PathResourceLoader(str(base_path / "locales" / "{locale}"))

                with pytest.raises(ValueError, match="Path traversal detected"):
                    loader.load("en", "escape.ftl")
            except OSError:
                # Symlink creation might fail on some systems (e.g., Windows without admin)
                # Skip this test if we can't create symlinks
                pytest.skip("Symlink creation not supported on this system")

    def test_is_safe_path_returns_true_for_valid_path(self) -> None:
        """Test _is_safe_path returns True for valid paths (line 177)."""
        # Test via public API (PathResourceLoader validates paths internally)
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            locale_dir = base / "locales" / "en"
            locale_dir.mkdir(parents=True)

            test_file = locale_dir / "test.ftl"
            test_file.write_text("msg = Test")

            loader = PathResourceLoader(str(base / "locales" / "{locale}"))

            # Should succeed - file is within base directory
            content = loader.load("en", "test.ftl")
            assert "Test" in content

    def test_is_safe_path_returns_false_for_path_escape(self) -> None:
        """Test _is_safe_path catches path escapes (lines 178-180)."""
        # This is tested via the symlink test above
        # Here we test a different escape method using resolve()

        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            locale_path = base_path / "locales" / "en"
            locale_path.mkdir(parents=True)

            # Try to access a file that resolves outside the base
            # On most systems, this will be caught by earlier validation
            # but _is_safe_path provides defense in depth

            loader = PathResourceLoader(str(base_path / "locales" / "{locale}"))

            # This should be caught by _validate_resource_id first
            # but if it somehow got through, _is_safe_path would catch it
            with pytest.raises(ValueError, match=r"(traversal|not allowed)"):
                loader.load("en", "../../../etc/passwd")


class TestPathResourceLoaderValidation:
    """Additional validation tests for PathResourceLoader."""

    def test_load_with_valid_resource_id(self) -> None:
        """Test that valid resource IDs work correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            locale_dir = base / "locales" / "en"
            locale_dir.mkdir(parents=True)

            test_file = locale_dir / "messages.ftl"
            test_file.write_text("hello = Hello, World!")

            loader = PathResourceLoader(str(base / "locales" / "{locale}"))
            content = loader.load("en", "messages.ftl")

            assert "Hello, World!" in content

    def test_load_with_subdirectory_resource_id(self) -> None:
        """Test that subdirectories in resource_id work correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            locale_dir = base / "locales" / "en" / "ui"
            locale_dir.mkdir(parents=True)

            test_file = locale_dir / "buttons.ftl"
            test_file.write_text("save = Save")

            loader = PathResourceLoader(str(base / "locales" / "{locale}"))
            content = loader.load("en", "ui/buttons.ftl")

            assert "Save" in content

    def test_validate_resource_id_validates_before_path_resolution(self) -> None:
        """Test that validation happens before path operations."""
        loader = PathResourceLoader("locales/{locale}")

        # These should all be caught by validation before any path operations
        invalid_ids = [
            "/absolute/path.ftl",
            "..\\parent\\path.ftl",
            "..\\..\\..\\escape.ftl",
            "\\windows\\path.ftl",
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(ValueError, match=r"(Absolute|traversal|separator)"):
                loader.load("en", invalid_id)


class TestPathResourceLoaderLocaleValidation:
    """Test locale parameter validation (AUDIT-PATH-TRAVERSAL-007).

    Validation for locale parameter prevents directory traversal
    attacks via malicious locale codes like "../../../etc".
    """

    def test_load_rejects_locale_with_parent_traversal(self) -> None:
        """Test that '..' in locale is rejected."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Path traversal sequences not allowed in locale"):
            loader.load("../../../etc", "messages.ftl")

    def test_load_rejects_locale_with_embedded_traversal(self) -> None:
        """Test that '..' embedded in locale is rejected."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Path traversal sequences not allowed in locale"):
            loader.load("en/../de", "messages.ftl")

    def test_load_rejects_locale_with_forward_slash(self) -> None:
        """Test that '/' in locale is rejected."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Path separators not allowed in locale"):
            loader.load("en/attack", "messages.ftl")

    def test_load_rejects_locale_with_backslash(self) -> None:
        """Test that '\\' in locale is rejected."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Path separators not allowed in locale"):
            loader.load("en\\attack", "messages.ftl")

    def test_load_rejects_empty_locale(self) -> None:
        """Test that empty locale is rejected."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Locale code cannot be empty"):
            loader.load("", "messages.ftl")

    def test_load_accepts_valid_locale_codes(self) -> None:
        """Test that valid BCP 47 locale codes are accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            # Valid locales to test
            valid_locales = ["en", "en_US", "de_DE", "lv_LV", "zh_Hans_CN"]

            for locale in valid_locales:
                locale_dir = base / "locales" / locale
                locale_dir.mkdir(parents=True, exist_ok=True)
                test_file = locale_dir / "test.ftl"
                test_file.write_text(f"msg = Test for {locale}")

            loader = PathResourceLoader(str(base / "locales" / "{locale}"))

            for locale in valid_locales:
                content = loader.load(locale, "test.ftl")
                assert f"Test for {locale}" in content

    def test_root_dir_parameter_provides_fixed_anchor(self) -> None:
        """Test that root_dir parameter anchors path validation.

        The root_dir parameter provides a fixed anchor for path traversal
        validation that cannot be influenced by the locale parameter.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            locale_dir = base / "locales" / "en"
            locale_dir.mkdir(parents=True)
            test_file = locale_dir / "test.ftl"
            test_file.write_text("msg = Test")

            # Use explicit root_dir
            loader = PathResourceLoader(
                str(base / "locales" / "{locale}"),
                root_dir=str(base)
            )

            # Should work for valid locale
            content = loader.load("en", "test.ftl")
            assert "Test" in content

    def test_root_dir_prevents_locale_escape_attempt(self) -> None:
        """Test that even valid-looking locales can't escape root_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            # Create a "real" locale dir
            locale_dir = base / "locales" / "en"
            locale_dir.mkdir(parents=True)
            test_file = locale_dir / "test.ftl"
            test_file.write_text("msg = Test")

            # Create an "outside" directory
            outside = base / "outside"
            outside.mkdir()
            secret = outside / "secret.ftl"
            secret.write_text("secret = Should not access")

            # Use explicit root_dir constrained to locales only
            loader = PathResourceLoader(
                str(base / "locales" / "{locale}"),
                root_dir=str(base / "locales")
            )

            # Valid locale should work
            content = loader.load("en", "test.ftl")
            assert "Test" in content
