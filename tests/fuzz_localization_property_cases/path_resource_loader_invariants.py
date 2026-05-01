# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# PathResourceLoader invariants
# ---------------------------------------------------------------------------


class TestPathResourceLoaderInvariants:
    """Property invariants for PathResourceLoader."""

    @given(
        prefix=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu"),
            ),
            min_size=0, max_size=8,
        ),
    )
    def test_init_resolves_root_from_static_prefix(
        self, prefix: str,
    ) -> None:
        """Root directory is derived from static prefix before {locale}."""
        base_path = (
            f"{prefix}/{{locale}}/resources"
            if prefix
            else "{locale}/resources"
        )
        event(f"prefix_len={len(prefix)}")
        loader = PathResourceLoader(base_path=base_path)
        assert loader._resolved_root is not None
        assert loader._resolved_root.is_absolute()
        if not prefix:
            assert loader._resolved_root == Path.cwd().resolve()

    @given(st.just("static/path"))
    def test_missing_locale_placeholder_raises(self, path: str) -> None:
        """base_path without {locale} raises ValueError."""
        event("outcome=validation_error")
        with pytest.raises(ValueError, match="must contain"):
            PathResourceLoader(base_path=path)

    @given(
        root_dir=st.just("/tmp/test_root"),
    )
    def test_explicit_root_dir_overrides_derivation(
        self, root_dir: str,
    ) -> None:
        """Explicit root_dir takes precedence over base_path derivation."""
        event("outcome=root_override")
        loader = PathResourceLoader(
            base_path="any/{locale}/path", root_dir=root_dir,
        )
        assert loader._resolved_root == Path(root_dir).resolve()

    @given(
        locale=st.from_regex(r"[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)*", fullmatch=True),
    )
    def test_valid_locales_pass_validation(self, locale: str) -> None:
        """Locale codes without path separators or .. pass validation."""
        event(f"locale_len={len(locale)}")
        # Should not raise
        PathResourceLoader._validate_locale(locale)

    @given(
        locale=st.sampled_from([
            "../etc", "en/US", "en\\US", "..", "a/../b",
        ]),
    )
    def test_unsafe_locales_rejected(self, locale: str) -> None:
        """Locales with path traversal or separators are rejected."""
        event("outcome=locale_rejected")
        with pytest.raises(ValueError, match=r"Invalid locale:"):
            PathResourceLoader._validate_locale(locale)

    @given(st.just(""))
    def test_empty_locale_rejected(self, locale: str) -> None:
        """Empty locale string is rejected."""
        event("outcome=empty_locale")
        with pytest.raises(ValueError, match="locale cannot be blank"):
            PathResourceLoader._validate_locale(locale)

    @given(
        resource_id=st.sampled_from([
            " main.ftl", "main.ftl ", "\tmain.ftl",
        ]),
    )
    def test_whitespace_resource_id_rejected(
        self, resource_id: str,
    ) -> None:
        """Resource IDs with leading/trailing whitespace are rejected."""
        event("outcome=whitespace_rejected")
        with pytest.raises(ValueError, match="whitespace"):
            PathResourceLoader._validate_resource_id(resource_id)

    @given(
        resource_id=st.sampled_from([
            "/etc/passwd", "\\windows\\sys", "../secret.ftl",
        ]),
    )
    def test_unsafe_resource_id_rejected(
        self, resource_id: str,
    ) -> None:
        """Resource IDs with traversal or absolute paths are rejected."""
        event("outcome=resource_rejected")
        with pytest.raises(ValueError, match="not allowed in resource_id"):
            PathResourceLoader._validate_resource_id(resource_id)

    @given(
        filename=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"),
                blacklist_characters="./\\ \t\n",
            ),
            min_size=1, max_size=15,
        ),
    )
    def test_valid_resource_ids_accepted(self, filename: str) -> None:
        """Clean resource IDs pass validation."""
        rid = f"{filename}.ftl"
        event(f"rid_len={len(rid)}")
        PathResourceLoader._validate_resource_id(rid)

    @settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        locale=st.sampled_from(["en", "de", "fr"]),
        content=st.text(
            min_size=1, max_size=100,
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),
            ),
        ),
    )
    def test_load_roundtrip_preserves_content(
        self, tmp_path: Path, locale: str, content: str,
    ) -> None:
        """PathResourceLoader.load returns exact file content."""
        event(f"locale={locale}")
        locale_dir = tmp_path / "locales" / locale
        locale_dir.mkdir(parents=True, exist_ok=True)
        (locale_dir / "test.ftl").write_text(content, encoding="utf-8")

        loader = PathResourceLoader(
            str(tmp_path / "locales" / "{locale}"),
        )
        loaded = loader.load(locale, "test.ftl")
        assert loaded == content
