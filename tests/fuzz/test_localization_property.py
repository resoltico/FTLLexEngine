"""Property-based tests for FluentLocalization orchestration layer.

Covers multi-locale orchestration, data type invariants, fallback semantics,
and API surface completeness using Hypothesis strategies from
tests/strategies/localization.

Fuzz module: all @given tests emit hypothesis.event() for HypoFuzz guidance.

Python 3.13+.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from ftllexengine.localization import (
    FluentLocalization,
    LoadStatus,
    LoadSummary,
    PathResourceLoader,
    ResourceLoadResult,
)
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.syntax.ast import Junk, Span
from tests.strategies.localization import (
    DictResourceLoader,
    FailingResourceLoader,
    ftl_messages_with_attributes,
    ftl_messages_with_terms,
    ftl_resource_sets,
    locale_chains,
    message_ids,
    resource_loaders,
)

pytestmark = pytest.mark.fuzz


# ---------------------------------------------------------------------------
# ResourceLoadResult property invariants
# ---------------------------------------------------------------------------


class TestResourceLoadResultProperties:
    """Property invariants for ResourceLoadResult data class."""

    @given(
        status=st.sampled_from(list(LoadStatus)),
        locale=st.sampled_from(["en", "de", "fr", "lv"]),
        resource_id=st.sampled_from(["main.ftl", "ui.ftl"]),
    )
    def test_status_properties_are_mutually_exclusive(
        self, status: LoadStatus, locale: str, resource_id: str,
    ) -> None:
        """Exactly one status property is True for any LoadStatus."""
        event(f"status={status.value}")
        result = ResourceLoadResult(
            locale=locale, resource_id=resource_id, status=status,
        )
        flags = [result.is_success, result.is_not_found, result.is_error]
        assert sum(flags) == 1

    @given(
        junk_count=st.integers(min_value=0, max_value=5),
    )
    def test_has_junk_iff_junk_entries_nonempty(
        self, junk_count: int,
    ) -> None:
        """has_junk is True iff junk_entries is non-empty."""
        event(f"junk_count={junk_count}")
        junk_entries = tuple(
            Junk(
                content=f"invalid{i}",
                span=Span(start=i * 10, end=i * 10 + 7),
            )
            for i in range(junk_count)
        )
        result = ResourceLoadResult(
            locale="en", resource_id="test.ftl",
            status=LoadStatus.SUCCESS, junk_entries=junk_entries,
        )
        assert result.has_junk == (junk_count > 0)


# ---------------------------------------------------------------------------
# LoadSummary aggregation invariants
# ---------------------------------------------------------------------------


class TestLoadSummaryAggregation:
    """Property invariants for LoadSummary post_init aggregation."""

    @given(
        success_n=st.integers(min_value=0, max_value=5),
        not_found_n=st.integers(min_value=0, max_value=5),
        error_n=st.integers(min_value=0, max_value=5),
    )
    def test_status_counts_sum_to_total(
        self, success_n: int, not_found_n: int, error_n: int,
    ) -> None:
        """successful + not_found + errors == total_attempted."""
        total = success_n + not_found_n + error_n
        event(f"total={total}")
        results: list[ResourceLoadResult] = []
        for i in range(success_n):
            results.append(ResourceLoadResult(
                f"en{i}", f"s{i}.ftl", LoadStatus.SUCCESS,
            ))
        for i in range(not_found_n):
            results.append(ResourceLoadResult(
                f"nf{i}", f"n{i}.ftl", LoadStatus.NOT_FOUND,
            ))
        for i in range(error_n):
            results.append(ResourceLoadResult(
                f"er{i}", f"e{i}.ftl", LoadStatus.ERROR,
                error=OSError(f"fail{i}"),
            ))

        summary = LoadSummary(results=tuple(results))
        assert summary.total_attempted == total
        assert summary.successful == success_n
        assert summary.not_found == not_found_n
        assert summary.errors == error_n
        assert summary.successful + summary.not_found + summary.errors == total

    @given(
        junk_per_result=st.lists(
            st.integers(min_value=0, max_value=3),
            min_size=1, max_size=5,
        ),
    )
    def test_junk_count_is_total_across_results(
        self, junk_per_result: list[int],
    ) -> None:
        """junk_count sums junk_entries lengths across all results."""
        expected_total = sum(junk_per_result)
        event(f"total_junk={expected_total}")
        results: list[ResourceLoadResult] = []
        for idx, jc in enumerate(junk_per_result):
            junk = tuple(
                Junk(
                    content=f"j{idx}_{j}",
                    span=Span(start=0, end=1),
                )
                for j in range(jc)
            )
            results.append(ResourceLoadResult(
                "en", f"f{idx}.ftl", LoadStatus.SUCCESS,
                junk_entries=junk,
            ))

        summary = LoadSummary(results=tuple(results))
        assert summary.junk_count == expected_total
        assert summary.has_junk == (expected_total > 0)

    @given(
        success_n=st.integers(min_value=0, max_value=3),
        not_found_n=st.integers(min_value=0, max_value=3),
        error_n=st.integers(min_value=0, max_value=3),
    )
    def test_filter_methods_partition_results(
        self, success_n: int, not_found_n: int, error_n: int,
    ) -> None:
        """get_errors + get_not_found + get_successful == all results."""
        event(f"error_n={error_n}")
        results: list[ResourceLoadResult] = []
        for i in range(success_n):
            results.append(ResourceLoadResult(
                "en", f"s{i}.ftl", LoadStatus.SUCCESS,
            ))
        for i in range(not_found_n):
            results.append(ResourceLoadResult(
                "de", f"n{i}.ftl", LoadStatus.NOT_FOUND,
            ))
        for i in range(error_n):
            results.append(ResourceLoadResult(
                "fr", f"e{i}.ftl", LoadStatus.ERROR,
                error=OSError("fail"),
            ))

        summary = LoadSummary(results=tuple(results))
        assert len(summary.get_successful()) == success_n
        assert len(summary.get_not_found()) == not_found_n
        assert len(summary.get_errors()) == error_n

    @given(
        locale=st.sampled_from(["en", "de", "fr"]),
        n=st.integers(min_value=0, max_value=4),
    )
    def test_get_by_locale_filters_correctly(
        self, locale: str, n: int,
    ) -> None:
        """get_by_locale returns only matching-locale results."""
        event(f"filter_count={n}")
        results: list[ResourceLoadResult] = []
        for i in range(n):
            results.append(ResourceLoadResult(
                locale, f"f{i}.ftl", LoadStatus.SUCCESS,
            ))
        # Add results for other locales
        results.append(ResourceLoadResult(
            "xx", "other.ftl", LoadStatus.SUCCESS,
        ))

        summary = LoadSummary(results=tuple(results))
        filtered = summary.get_by_locale(locale)
        assert len(filtered) == n
        assert all(r.locale == locale for r in filtered)

    @given(
        junk_counts=st.lists(
            st.integers(min_value=0, max_value=3),
            min_size=1, max_size=4,
        ),
    )
    def test_get_all_junk_flattens_correctly(
        self, junk_counts: list[int],
    ) -> None:
        """get_all_junk returns flattened tuple of all Junk entries."""
        expected_total = sum(junk_counts)
        event(f"flatten_total={expected_total}")
        results: list[ResourceLoadResult] = []
        all_junk: list[Junk] = []
        for idx, jc in enumerate(junk_counts):
            junk_entries = tuple(
                Junk(
                    content=f"j{idx}_{j}",
                    span=Span(start=0, end=1),
                )
                for j in range(jc)
            )
            all_junk.extend(junk_entries)
            results.append(ResourceLoadResult(
                "en", f"f{idx}.ftl", LoadStatus.SUCCESS,
                junk_entries=junk_entries,
            ))

        summary = LoadSummary(results=tuple(results))
        flattened = summary.get_all_junk()
        assert len(flattened) == expected_total
        for j in all_junk:
            assert j in flattened

    @given(
        has_errors=st.booleans(),
        has_not_found=st.booleans(),
        has_junk=st.booleans(),
    )
    def test_all_successful_and_all_clean_semantics(
        self, has_errors: bool, has_not_found: bool, has_junk: bool,
    ) -> None:
        """all_successful ignores junk; all_clean requires zero junk."""
        event(f"errors={has_errors}")
        event(f"not_found={has_not_found}")
        results: list[ResourceLoadResult] = []
        # Always add at least one success
        junk = (
            (Junk(content="j", span=Span(start=0, end=1)),)
            if has_junk else ()
        )
        results.append(ResourceLoadResult(
            "en", "main.ftl", LoadStatus.SUCCESS, junk_entries=junk,
        ))
        if has_errors:
            results.append(ResourceLoadResult(
                "de", "err.ftl", LoadStatus.ERROR, error=OSError("f"),
            ))
        if has_not_found:
            results.append(ResourceLoadResult(
                "fr", "nf.ftl", LoadStatus.NOT_FOUND,
            ))

        summary = LoadSummary(results=tuple(results))

        expected_all_successful = not has_errors and not has_not_found
        assert summary.all_successful == expected_all_successful

        expected_all_clean = (
            not has_errors and not has_not_found and not has_junk
        )
        assert summary.all_clean == expected_all_clean

    @given(
        has_errors=st.booleans(),
    )
    def test_has_errors_property(self, has_errors: bool) -> None:
        """has_errors is True iff errors > 0."""
        event(f"has_errors={has_errors}")
        results: list[ResourceLoadResult] = [
            ResourceLoadResult("en", "ok.ftl", LoadStatus.SUCCESS),
        ]
        if has_errors:
            results.append(ResourceLoadResult(
                "de", "err.ftl", LoadStatus.ERROR, error=OSError("f"),
            ))
        summary = LoadSummary(results=tuple(results))
        assert summary.has_errors == has_errors


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
        locale=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"),
                blacklist_characters="/\\.",
            ),
            min_size=1, max_size=10,
        ),
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
        with pytest.raises(ValueError, match="not allowed in locale"):
            PathResourceLoader._validate_locale(locale)

    @given(st.just(""))
    def test_empty_locale_rejected(self, locale: str) -> None:
        """Empty locale string is rejected."""
        event("outcome=empty_locale")
        with pytest.raises(ValueError, match="cannot be empty"):
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

    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
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


# ---------------------------------------------------------------------------
# FluentLocalization orchestration invariants
# ---------------------------------------------------------------------------


class TestFluentLocalizationOrchestration:
    """Property invariants for FluentLocalization fallback behavior."""

    @given(locales=locale_chains(min_size=1, max_size=5))
    def test_deduplication_preserves_order(
        self, locales: list[str],
    ) -> None:
        """Locale deduplication preserves first-occurrence order."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        expected = tuple(dict.fromkeys(locales))
        assert l10n.locales == expected

    @given(locales=locale_chains(min_size=1, max_size=3))
    def test_locales_property_returns_same_instance(
        self, locales: list[str],
    ) -> None:
        """locales property is referentially identical across calls."""
        event("outcome=identity_check")
        l10n = FluentLocalization(locales)
        assert l10n.locales is l10n.locales

    @given(
        locales=locale_chains(min_size=2, max_size=4),
        mid=message_ids(),
    )
    def test_primary_locale_takes_precedence(
        self, locales: list[str], mid: str,
    ) -> None:
        """First locale with message wins in fallback chain."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales, use_isolating=False)
        for locale in locales:
            l10n.add_resource(locale, f"{mid} = from-{locale}")
        result, errors = l10n.format_value(mid)
        assert not errors
        assert result == f"from-{locales[0]}"

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        mid=message_ids(),
    )
    def test_has_message_consistent_with_format_value(
        self, locales: list[str], mid: str,
    ) -> None:
        """has_message True iff format_value finds the message."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], f"{mid} = test")
        has = l10n.has_message(mid)
        _, errors = l10n.format_value(mid)
        if has:
            assert not any(
                "not found in any locale" in str(e) for e in errors
            )
        else:
            assert any(
                "not found in any locale" in str(e) for e in errors
            )

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        mid=message_ids(),
    )
    def test_format_value_deterministic(
        self, locales: list[str], mid: str,
    ) -> None:
        """Repeated format_value calls return identical results."""
        event("outcome=determinism")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], f"{mid} = stable")
        r1, _ = l10n.format_value(mid)
        r2, _ = l10n.format_value(mid)
        assert r1 == r2

    @given(mid=message_ids())
    def test_missing_message_returns_braced_id(self, mid: str) -> None:
        """Missing message returns {message_id} per Fluent convention."""
        event("outcome=missing_message")
        l10n = FluentLocalization(["en"])
        result, errors = l10n.format_value(mid)
        assert result == f"{{{mid}}}"
        assert len(errors) == 1

    @given(mid=st.just(""))
    def test_empty_message_id_returns_fallback(self, mid: str) -> None:
        """Empty message ID returns {???} fallback."""
        event("outcome=empty_id")
        l10n = FluentLocalization(["en"])
        result, errors = l10n.format_value(mid)
        assert result == "{???}"
        assert len(errors) == 1

    @given(locales=locale_chains(min_size=1, max_size=3))
    def test_repr_contains_locales_and_bundles(
        self, locales: list[str],
    ) -> None:
        """__repr__ always includes locales and bundle count."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        r = repr(l10n)
        assert "FluentLocalization" in r
        assert "locales=" in r
        assert "bundles=" in r


# ---------------------------------------------------------------------------
# FluentLocalization API methods (coverage targets)
# ---------------------------------------------------------------------------


class TestFluentLocalizationHasAttribute:
    """Tests for has_attribute method (lines 1126-1130)."""

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        ftl=ftl_messages_with_attributes(),
    )
    def test_has_attribute_from_generated_resource(
        self, locales: list[str], ftl: str,
    ) -> None:
        """has_attribute detects attributes in generated resources."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], ftl)

        # Extract message ID from generated FTL
        first_line = ftl.split("\n", maxsplit=1)[0]
        mid = first_line.split("=")[0].strip()

        # Check for attr0 (present if attributes were generated)
        if ".attr0" in ftl:
            assert l10n.has_attribute(mid, "attr0") is True
            event("outcome=attribute_found")
        else:
            assert l10n.has_attribute(mid, "attr0") is False
            event("outcome=no_attributes")

    @given(locales=locale_chains(min_size=2, max_size=4))
    def test_has_attribute_fallback_chain(
        self, locales: list[str],
    ) -> None:
        """has_attribute searches across fallback chain."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        # Attribute only in last locale
        l10n.add_resource(
            locales[-1], "btn = Click\n    .tooltip = Help text\n",
        )
        assert l10n.has_attribute("btn", "tooltip") is True

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_has_attribute_missing_returns_false(
        self, locales: list[str],
    ) -> None:
        """has_attribute returns False for nonexistent attributes."""
        event("outcome=not_found")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], "msg = No attributes\n")
        assert l10n.has_attribute("msg", "nonexistent") is False
        assert l10n.has_attribute("missing", "attr") is False


class TestFluentLocalizationGetMessageIds:
    """Tests for get_message_ids method (lines 1142-1150)."""

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        resources=ftl_resource_sets(),
    )
    def test_get_message_ids_returns_union(
        self, locales: list[str], resources: dict[str, str],
    ) -> None:
        """get_message_ids returns union of IDs across all locales."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        all_expected: set[str] = set()
        for locale in locales:
            if locale in resources:
                l10n.add_resource(locale, resources[locale])
                # Parse message IDs from FTL
                for line in resources[locale].split("\n"):
                    if "=" in line and not line.startswith(
                        ("#", " ", "-"),
                    ):
                        mid = line.split("=")[0].strip()
                        if mid:
                            all_expected.add(mid)

        ids = l10n.get_message_ids()
        assert set(ids) == all_expected
        # No duplicates
        assert len(ids) == len(set(ids))

    @given(locales=locale_chains(min_size=2, max_size=3))
    def test_get_message_ids_primary_locale_first(
        self, locales: list[str],
    ) -> None:
        """get_message_ids orders primary locale IDs first."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], "alpha = A\n")
        l10n.add_resource(
            locales[-1], "alpha = A2\nbeta = B\n",
        )
        ids = l10n.get_message_ids()
        # alpha from primary appears before beta from fallback
        assert ids.index("alpha") < ids.index("beta")

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_get_message_ids_empty_when_no_resources(
        self, locales: list[str],
    ) -> None:
        """get_message_ids returns empty list when no resources loaded."""
        event("outcome=empty")
        l10n = FluentLocalization(locales)
        assert l10n.get_message_ids() == []


class TestFluentLocalizationGetMessageVariables:
    """Tests for get_message_variables method (lines 1169-1174)."""

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_get_message_variables_returns_variable_names(
        self, locales: list[str],
    ) -> None:
        """get_message_variables extracts variable names from message."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(
            locales[0],
            "greeting = Hello { $firstName } { $lastName }!\n",
        )
        variables = l10n.get_message_variables("greeting")
        assert "firstName" in variables
        assert "lastName" in variables

    @given(locales=locale_chains(min_size=2, max_size=3))
    def test_get_message_variables_fallback(
        self, locales: list[str],
    ) -> None:
        """get_message_variables searches fallback chain."""
        event("outcome=fallback_search")
        l10n = FluentLocalization(locales)
        l10n.add_resource(
            locales[-1], "msg = Value { $count }\n",
        )
        variables = l10n.get_message_variables("msg")
        assert "count" in variables

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_get_message_variables_raises_for_missing(
        self, locales: list[str],
    ) -> None:
        """get_message_variables raises KeyError for missing message."""
        event("outcome=key_error")
        l10n = FluentLocalization(locales)
        with pytest.raises(KeyError, match="not found"):
            l10n.get_message_variables("nonexistent")


class TestFluentLocalizationGetAllMessageVariables:
    """Tests for get_all_message_variables (lines 1188-1196)."""

    @given(locales=locale_chains(min_size=1, max_size=3))
    def test_get_all_message_variables_returns_dict(
        self, locales: list[str],
    ) -> None:
        """get_all_message_variables returns dict of msg_id -> variables."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(
            locales[0],
            "msg1 = { $name }\nmsg2 = Static text\n",
        )
        all_vars = l10n.get_all_message_variables()
        assert isinstance(all_vars, dict)
        assert "msg1" in all_vars
        assert "name" in all_vars["msg1"]
        assert "msg2" in all_vars

    @given(locales=locale_chains(min_size=2, max_size=3))
    def test_primary_locale_variables_take_precedence(
        self, locales: list[str],
    ) -> None:
        """Primary locale's variables win for duplicate message IDs."""
        event("outcome=precedence")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], "msg = { $primary }\n")
        l10n.add_resource(locales[-1], "msg = { $fallback }\n")
        all_vars = l10n.get_all_message_variables()
        assert "primary" in all_vars["msg"]


class TestFluentLocalizationIntrospectTerm:
    """Tests for introspect_term method (lines 1211-1217)."""

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_introspect_term_found(
        self, locales: list[str],
    ) -> None:
        """introspect_term returns introspection for existing term."""
        event("outcome=term_found")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], "-brand = Firefox\n")
        info = l10n.introspect_term("brand")
        assert info is not None

    @given(locales=locale_chains(min_size=2, max_size=3))
    def test_introspect_term_fallback(
        self, locales: list[str],
    ) -> None:
        """introspect_term searches fallback chain."""
        event("outcome=term_fallback")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[-1], "-product = App\n")
        info = l10n.introspect_term("product")
        assert info is not None

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_introspect_term_not_found(
        self, locales: list[str],
    ) -> None:
        """introspect_term returns None for missing term."""
        event("outcome=term_not_found")
        l10n = FluentLocalization(locales)
        info = l10n.introspect_term("nonexistent")
        assert info is None


class TestFluentLocalizationContextManager:
    """Tests for __enter__/__exit__ (lines 1221-1222, 1231)."""

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_context_manager_protocol(
        self, locales: list[str],
    ) -> None:
        """FluentLocalization supports with statement."""
        event("outcome=context_manager")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], "msg = Hello\n")
        with l10n as ctx:
            assert ctx is l10n
            result, _ = ctx.format_value("msg")
            assert result == "Hello"

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_context_manager_releases_lock_on_exception(
        self, locales: list[str],
    ) -> None:
        """Lock released even if exception occurs inside with block."""
        event("outcome=exception_release")
        l10n = FluentLocalization(locales)
        try:
            with l10n:
                msg = "test error"
                raise ValueError(msg)
        except ValueError:
            pass
        # Lock should be released - this call should not deadlock
        l10n.add_resource(locales[0], "msg = Works\n")
        result, _ = l10n.format_value("msg")
        assert result == "Works"


# ---------------------------------------------------------------------------
# Resource loading and load summary
# ---------------------------------------------------------------------------


class TestFluentLocalizationResourceLoading:
    """Tests for resource loading and load summary."""

    @given(
        loader_tuple=resource_loaders(),
    )
    def test_load_summary_tracks_all_attempts(
        self,
        loader_tuple: tuple[
            DictResourceLoader | FailingResourceLoader,
            list[str],
            list[str],
        ],
    ) -> None:
        """get_load_summary reflects all load attempts from init."""
        loader, locales, resource_ids = loader_tuple
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(
            locales, resource_ids, loader,
        )
        summary = l10n.get_load_summary()
        assert summary.total_attempted == len(locales) * len(resource_ids)

    @given(locales=locale_chains(min_size=1, max_size=3))
    def test_custom_loader_source_path_format(
        self, locales: list[str],
    ) -> None:
        """Non-PathResourceLoader uses locale/resource_id as source_path."""
        event("outcome=custom_loader_path")
        resources = {
            loc: {"main.ftl": f"msg = {loc}\n"}
            for loc in locales
        }
        loader = DictResourceLoader(resources)
        l10n = FluentLocalization(locales, ["main.ftl"], loader)
        summary = l10n.get_load_summary()
        for result in summary.results:
            # Custom loader uses "locale/resource_id" format
            assert "/" in result.source_path  # type: ignore[operator]

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_oserror_during_load_recorded_as_error(
        self, locales: list[str],
    ) -> None:
        """OSError during resource loading recorded with ERROR status."""
        event("outcome=oserror_recorded")
        loader = FailingResourceLoader(OSError, "Permission denied")
        l10n = FluentLocalization(locales, ["main.ftl"], loader)
        summary = l10n.get_load_summary()
        assert summary.errors > 0
        for result in summary.get_errors():
            assert isinstance(result.error, OSError)

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_valueerror_during_load_recorded_as_error(
        self, locales: list[str],
    ) -> None:
        """ValueError during resource loading recorded with ERROR status."""
        event("outcome=valueerror_recorded")
        loader = FailingResourceLoader(ValueError, "Path traversal")
        l10n = FluentLocalization(locales, ["main.ftl"], loader)
        summary = l10n.get_load_summary()
        assert summary.errors > 0
        for result in summary.get_errors():
            assert isinstance(result.error, ValueError)


# ---------------------------------------------------------------------------
# Cache stats aggregation branch coverage
# ---------------------------------------------------------------------------


class TestCacheStatsAggregation:
    """Tests for get_cache_stats aggregation (branch 1327->1325)."""

    @given(
        locales=locale_chains(min_size=2, max_size=4),
    )
    def test_cache_stats_aggregates_across_bundles(
        self, locales: list[str],
    ) -> None:
        """get_cache_stats sums metrics across all initialized bundles."""
        event(f"bundle_count={len(locales)}")
        l10n = FluentLocalization(
            locales, cache=CacheConfig(),
        )
        # Initialize all bundles with resources
        for locale in locales:
            l10n.add_resource(locale, f"msg = {locale}\n")

        # Format to create cache entries
        l10n.format_value("msg")

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["bundle_count"] == len(locales)
        assert l10n.cache_config is not None
        assert stats["maxsize"] == l10n.cache_config.size * len(locales)

    @given(
        locales=locale_chains(min_size=1, max_size=2),
    )
    def test_cache_stats_none_when_disabled(
        self, locales: list[str],
    ) -> None:
        """get_cache_stats returns None when caching disabled."""
        event("outcome=cache_disabled")
        l10n = FluentLocalization(locales)
        assert l10n.get_cache_stats() is None


# ---------------------------------------------------------------------------
# Fallback callback
# ---------------------------------------------------------------------------


class TestFallbackCallback:
    """Tests for on_fallback callback with property-based inputs."""

    @given(
        locales=locale_chains(min_size=2, max_size=4),
        mid=message_ids(),
    )
    def test_fallback_callback_invoked_for_non_primary(
        self, locales: list[str], mid: str,
    ) -> None:
        """on_fallback invoked when message resolved from non-primary."""
        event(f"locale_count={len(locales)}")
        from ftllexengine.localization import FallbackInfo  # noqa: PLC0415
        events: list[FallbackInfo] = []
        l10n = FluentLocalization(
            locales, on_fallback=events.append,
        )
        # Only add to last locale
        l10n.add_resource(locales[-1], f"{mid} = fallback\n")
        l10n.format_value(mid)
        if len(locales) > 1:
            assert len(events) == 1
            assert events[0].requested_locale == locales[0]
            assert events[0].resolved_locale == locales[-1]
            assert events[0].message_id == mid

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        mid=message_ids(),
    )
    def test_no_fallback_when_primary_has_message(
        self, locales: list[str], mid: str,
    ) -> None:
        """on_fallback not invoked when primary locale has message."""
        event("outcome=no_fallback")
        from ftllexengine.localization import FallbackInfo  # noqa: PLC0415
        events: list[FallbackInfo] = []
        l10n = FluentLocalization(
            locales, on_fallback=events.append,
        )
        l10n.add_resource(locales[0], f"{mid} = primary\n")
        l10n.format_value(mid)
        assert len(events) == 0


# ---------------------------------------------------------------------------
# add_function deferred application
# ---------------------------------------------------------------------------


class TestAddFunctionDeferred:
    """Tests for add_function deferred/immediate application."""

    @given(locales=locale_chains(min_size=1, max_size=3))
    def test_function_applied_to_existing_bundles(
        self, locales: list[str],
    ) -> None:
        """add_function applies to already-created bundles."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales, use_isolating=False)
        # Create bundles by adding resources
        for locale in locales:
            l10n.add_resource(locale, "msg = { UPPER($x) }\n")

        def upper_fn(value: str) -> str:
            return value.upper()

        l10n.add_function("UPPER", upper_fn)
        result, _ = l10n.format_value("msg", {"x": "test"})
        assert "TEST" in result

    @given(locales=locale_chains(min_size=2, max_size=3))
    def test_function_stored_for_lazy_bundles(
        self, locales: list[str],
    ) -> None:
        """add_function stored for bundles created later."""
        event("outcome=deferred")
        l10n = FluentLocalization(locales, use_isolating=False)

        def lower_fn(value: str) -> str:
            return value.lower()

        l10n.add_function("LOWER", lower_fn)
        # Add resource and format after function registration
        l10n.add_resource(locales[0], "msg = { LOWER($x) }\n")
        result, _ = l10n.format_value("msg", {"x": "HELLO"})
        assert "hello" in result


# ---------------------------------------------------------------------------
# Validation edge cases
# ---------------------------------------------------------------------------


class TestValidationEdgeCases:
    """Validation and defensive checks."""

    @given(
        locale=st.sampled_from(["en", "de"]),
        ws=st.sampled_from([" ", "\t", "\n"]),
        position=st.sampled_from(["leading", "trailing"]),
    )
    def test_add_resource_whitespace_locale_rejected(
        self, locale: str, ws: str, position: str,
    ) -> None:
        """add_resource rejects locales with leading/trailing whitespace."""
        event(f"position={position}")
        padded = ws + locale if position == "leading" else locale + ws
        l10n = FluentLocalization([locale])
        with pytest.raises(ValueError, match="whitespace"):
            l10n.add_resource(padded, "msg = test")

    @given(
        locale=st.sampled_from(["en", "de"]),
        invalid_args=st.sampled_from([42, "str", [1, 2], True]),
    )
    def test_format_value_invalid_args_type(
        self, locale: str, invalid_args: int | str | list[int] | bool,
    ) -> None:
        """format_value with non-Mapping args returns error."""
        event("outcome=invalid_args")
        l10n = FluentLocalization([locale])
        l10n.add_resource(locale, "msg = test")
        result, errors = l10n.format_value(
            "msg", invalid_args,  # type: ignore[arg-type]
        )
        assert result == "{???}"
        assert len(errors) > 0

    @given(
        locale=st.sampled_from(["en", "de"]),
        invalid_attr=st.sampled_from([42, 3.14, ["a"], {"k": "v"}]),
    )
    def test_format_pattern_invalid_attribute_type(
        self,
        locale: str,
        invalid_attr: int | float | list[str] | dict[str, str],
    ) -> None:
        """format_pattern with non-str attribute returns error."""
        event("outcome=invalid_attr")
        l10n = FluentLocalization([locale])
        l10n.add_resource(locale, "msg = test\n    .a = v")
        result, errors = l10n.format_pattern(
            "msg", None,
            attribute=invalid_attr,  # type: ignore[arg-type]
        )
        assert result == "{???}"
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Terms with Hypothesis strategies
# ---------------------------------------------------------------------------


class TestTermsWithStrategies:
    """Tests using ftl_messages_with_terms strategy."""

    @given(
        locales=locale_chains(min_size=1, max_size=2),
        ftl=ftl_messages_with_terms(),
    )
    def test_terms_parsed_and_resolvable(
        self, locales: list[str], ftl: str,
    ) -> None:
        """Generated terms are parsed without errors."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales, use_isolating=False)
        junk = l10n.add_resource(locales[0], ftl)
        # Should parse without junk
        assert len(junk) == 0
