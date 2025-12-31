"""Targeted tests for 100% coverage of localization module.

Covers specific uncovered lines identified by coverage analysis.
Focuses on PathResourceLoader initialization edge cases.
"""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.localization import PathResourceLoader


class TestPathResourceLoaderInitEdgeCases:
    """PathResourceLoader initialization edge cases (line 273 coverage)."""

    def test_base_path_without_locale_placeholder(self) -> None:
        """Base path without {locale} placeholder uses current directory."""
        # Edge case: base_path has no {locale} placeholder
        loader = PathResourceLoader(base_path="static/path")
        # Should initialize without error
        # The _resolved_root should be based on static/path or cwd
        assert loader._resolved_root is not None
        assert isinstance(loader._resolved_root, Path)

    def test_base_path_empty_after_split(self) -> None:
        """Base path that results in empty static_prefix."""
        # Edge case: template_parts[0] is empty after split
        loader = PathResourceLoader(base_path="{locale}/resources")
        # Should use cwd when static_prefix is empty
        assert loader._resolved_root is not None
        # Should be current working directory
        assert loader._resolved_root == Path.cwd().resolve()

    def test_base_path_with_trailing_separators(self) -> None:
        """Base path with trailing path separators."""
        loader = PathResourceLoader(base_path="locales/{locale}////")
        assert loader._resolved_root is not None
        # Should strip trailing separators
        expected_base = Path("locales").resolve()
        assert loader._resolved_root == expected_base

    def test_base_path_root_only(self) -> None:
        """Base path is just the root separator."""
        # This tests the edge case where static_prefix becomes empty
        loader = PathResourceLoader(base_path="/{locale}")
        assert loader._resolved_root is not None

    def test_explicit_root_dir_overrides_base_path(self) -> None:
        """Explicit root_dir overrides base_path parsing."""
        loader = PathResourceLoader(
            base_path="any/{locale}/path",
            root_dir="/explicit/root"
        )
        # Should use explicit root_dir, not derive from base_path
        assert loader._resolved_root == Path("/explicit/root").resolve()

    @given(
        prefix=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"), blacklist_characters=["/"]
            ),
            min_size=0,
            max_size=10,
        )
    )
    def test_various_base_path_prefixes(self, prefix: str) -> None:
        """Property: Various base path prefixes initialize successfully."""
        # Empty prefix results in {locale} at start
        base_path = (
            "{locale}/resources"
            if not prefix
            else f"{prefix}/{{locale}}/resources"
        )

        loader = PathResourceLoader(base_path=base_path)
        assert loader._resolved_root is not None
        assert isinstance(loader._resolved_root, Path)


class TestPathResourceLoaderTemplateEdgeCases:
    """Template parsing edge cases."""

    def test_multiple_locale_placeholders(self) -> None:
        """Multiple {locale} placeholders in path."""
        # Edge case: split on {locale} produces multiple parts
        loader = PathResourceLoader(base_path="root/{locale}/sub/{locale}")
        # Should use first part before first {locale}
        assert loader._resolved_root == Path("root").resolve()

    def test_no_locale_placeholder_uses_whole_path(self) -> None:
        """No {locale} placeholder uses whole path as static."""
        loader = PathResourceLoader(base_path="static/resources")
        # Should use the whole path as static prefix
        assert loader._resolved_root == Path("static/resources").resolve()

    def test_locale_at_start_uses_cwd(self) -> None:
        """Template starting with {locale} uses cwd."""
        loader = PathResourceLoader(base_path="{locale}/data")
        # No static prefix before {locale}, should use cwd
        assert loader._resolved_root == Path.cwd().resolve()

    def test_relative_base_path_resolution(self) -> None:
        """Relative base paths are resolved to absolute."""
        loader = PathResourceLoader(base_path="./locales/{locale}")
        # Should resolve relative path
        assert loader._resolved_root.is_absolute()

    @given(
        depth=st.integers(min_value=0, max_value=5),
        name=st.text(
            alphabet=st.characters(whitelist_categories=["Ll"]),
            min_size=1,
            max_size=8,
        ),
    )
    def test_nested_directory_structures(self, depth: int, name: str) -> None:
        """Property: Nested directory structures initialize correctly."""
        path_parts = [name] * depth + ["{locale}"]
        base_path = "/".join(path_parts)

        loader = PathResourceLoader(base_path=base_path)
        assert loader._resolved_root is not None

        if depth > 0:
            # Should use the nested path as root
            expected_parts = [name] * depth
            expected_path = Path("/".join(expected_parts)).resolve()
            assert loader._resolved_root == expected_path
        else:
            # Depth 0 means {locale} at start, should use cwd
            assert loader._resolved_root == Path.cwd().resolve()


class TestPathResourceLoaderSecurityEdgeCases:
    """Security-related edge cases for path validation."""

    def test_load_rejects_path_traversal_in_locale(self) -> None:
        """Locale with path traversal is rejected."""
        loader = PathResourceLoader(base_path="locales/{locale}")

        with pytest.raises(ValueError, match="Path traversal"):
            loader.load("../etc", "passwd")

    def test_load_rejects_absolute_resource_id(self) -> None:
        """Absolute path in resource_id is rejected."""
        loader = PathResourceLoader(base_path="locales/{locale}")

        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            loader.load("en", "/etc/passwd")

    def test_load_rejects_parent_dir_in_resource_id(self) -> None:
        """Parent directory reference in resource_id is rejected."""
        loader = PathResourceLoader(base_path="locales/{locale}")

        with pytest.raises(ValueError, match="Path traversal"):
            loader.load("en", "../sensitive.ftl")

    def test_load_rejects_path_separator_in_locale(self) -> None:
        """Path separator in locale is rejected."""
        loader = PathResourceLoader(base_path="locales/{locale}")

        with pytest.raises(ValueError, match="Path traversal"):
            loader.load("en/../../etc", "main.ftl")

    def test_load_rejects_empty_locale(self) -> None:
        """Empty locale is rejected."""
        loader = PathResourceLoader(base_path="locales/{locale}")

        with pytest.raises(ValueError, match="Locale code cannot be empty"):
            loader.load("", "main.ftl")

    def test_safe_path_validation_prevents_escape(self, tmp_path: Path) -> None:
        """Safe path validation prevents directory escape."""
        # Create a test directory structure
        base_dir = tmp_path / "locales"
        base_dir.mkdir()
        (base_dir / "en").mkdir()
        (base_dir / "en" / "main.ftl").write_text("test = Test", encoding="utf-8")

        loader = PathResourceLoader(
            base_path=str(base_dir / "{locale}"),
            root_dir=str(base_dir)
        )

        # Valid load should work
        content = loader.load("en", "main.ftl")
        assert "test = Test" in content

        # Attempt to escape should fail
        with pytest.raises((ValueError, FileNotFoundError)):
            # Even with symlinks or other tricks, should not escape root
            loader.load("en", "../../../etc/passwd")

    @given(
        locale_attempt=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"),
                blacklist_characters=["/", "\\", "."],
            ),
            min_size=1,
            max_size=10,
        )
    )
    def test_valid_locale_codes_accepted(self, locale_attempt: str) -> None:
        """Property: Valid locale codes without special chars are accepted."""
        loader = PathResourceLoader(base_path="locales/{locale}")

        # Should not raise during validation
        try:
            loader._validate_locale(locale_attempt)
        except ValueError as e:
            # Should only fail on empty, which Hypothesis won't generate (min_size=1)
            pytest.fail(f"Valid locale rejected: {locale_attempt}, error: {e}")


class TestPathResourceLoaderRootDirHandling:
    """Root directory handling in PathResourceLoader."""

    def test_root_dir_none_derives_from_base_path(self) -> None:
        """When root_dir is None, derives from base_path."""
        loader = PathResourceLoader(base_path="custom/{locale}")
        # Should derive root from "custom" prefix
        assert loader._resolved_root == Path("custom").resolve()

    def test_root_dir_explicit_overrides_derivation(self) -> None:
        """Explicit root_dir overrides base_path derivation."""
        loader = PathResourceLoader(
            base_path="path/{locale}",
            root_dir="explicit_root"
        )
        assert loader._resolved_root == Path("explicit_root").resolve()

    def test_root_dir_absolute_path(self, tmp_path: Path) -> None:
        """Absolute root_dir is used as-is."""
        root = tmp_path / "absolute_root"
        root.mkdir()

        loader = PathResourceLoader(
            base_path="any/{locale}",
            root_dir=str(root)
        )
        assert loader._resolved_root == root.resolve()

    def test_root_dir_relative_path_resolved(self) -> None:
        """Relative root_dir is resolved to absolute."""
        loader = PathResourceLoader(
            base_path="any/{locale}",
            root_dir="./relative"
        )
        assert loader._resolved_root.is_absolute()
        assert loader._resolved_root == Path("./relative").resolve()


class TestResourceIdValidation:
    """Resource ID validation tests."""

    def test_validate_resource_id_rejects_leading_slash(self) -> None:
        """Resource ID starting with / is rejected."""
        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            PathResourceLoader._validate_resource_id("/main.ftl")

    def test_validate_resource_id_rejects_leading_backslash(self) -> None:
        """Resource ID starting with \\ is rejected."""
        with pytest.raises(ValueError, match="must not start with path separator"):
            PathResourceLoader._validate_resource_id("\\main.ftl")

    def test_validate_resource_id_accepts_subdirectory(self) -> None:
        """Resource ID with subdirectory is accepted."""
        # Should not raise - returns None on success
        result = PathResourceLoader._validate_resource_id("subdir/main.ftl")
        assert result is None  # Validation methods return None on success

    @given(
        filename=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"),
                blacklist_characters=[".", "/", "\\"],
            ),
            min_size=1,
            max_size=20,
        )
    )
    def test_valid_resource_ids_accepted(self, filename: str) -> None:
        """Property: Valid filenames without special chars are accepted."""
        resource_id = f"{filename}.ftl"
        # Should not raise
        try:
            PathResourceLoader._validate_resource_id(resource_id)
        except ValueError as e:
            pytest.fail(f"Valid resource ID rejected: {resource_id}, error: {e}")
