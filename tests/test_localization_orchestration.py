"""Tests for FluentLocalization orchestration API surface.

Covers FluentLocalization methods not exercised by the main integration tests:
- has_attribute: attribute existence across fallback chain
- get_message_ids: union of IDs across all locales
- get_message_variables: variable extraction with fallback
- get_all_message_variables: merged variable map
- introspect_term: term introspection with fallback
- __enter__/__exit__: context manager protocol
- get_load_summary: resource load tracking
- get_cache_stats: aggregate cache metrics branch

Also covers data type invariants for ResourceLoadResult, LoadSummary,
and PathResourceLoader initialization edge cases.

Python 3.13+.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ftllexengine.localization import (
    FluentLocalization,
    LoadStatus,
    LoadSummary,
    PathResourceLoader,
    ResourceLoadResult,
)
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import Junk, Span


class TestResourceLoadResultStatusProperties:
    """ResourceLoadResult status predicates are mutually exclusive."""

    @pytest.mark.parametrize("status", list(LoadStatus))
    def test_status_properties_exclusive(self, status: LoadStatus) -> None:
        """Exactly one of is_success/is_not_found/is_error is True."""
        result = ResourceLoadResult("en", "main.ftl", status)
        flags = [result.is_success, result.is_not_found, result.is_error]
        assert sum(flags) == 1

    def test_has_junk_true_when_junk_present(self) -> None:
        """has_junk is True when junk_entries is non-empty."""
        junk = Junk(content="bad", span=Span(start=0, end=3))
        result = ResourceLoadResult(
            "en", "test.ftl", LoadStatus.SUCCESS,
            junk_entries=(junk,),
        )
        assert result.has_junk is True

    def test_has_junk_false_when_empty(self) -> None:
        """has_junk is False when junk_entries is empty."""
        result = ResourceLoadResult(
            "en", "test.ftl", LoadStatus.SUCCESS, junk_entries=(),
        )
        assert result.has_junk is False




class TestLoadSummaryStatistics:
    """LoadSummary post_init and filtering methods."""

    def _make_summary(self) -> LoadSummary:
        """Build a LoadSummary with all three status types and junk."""
        junk = Junk(content="j", span=Span(start=0, end=1))
        results = (
            ResourceLoadResult("en", "ok.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult(
                "en", "junk.ftl", LoadStatus.SUCCESS,
                junk_entries=(junk,),
            ),
            ResourceLoadResult("de", "nf.ftl", LoadStatus.NOT_FOUND),
            ResourceLoadResult(
                "fr", "err.ftl", LoadStatus.ERROR,
                error=OSError("fail"),
            ),
        )
        return LoadSummary(results=results)

    def test_post_init_calculates_counts(self) -> None:
        """__post_init__ calculates all aggregate counts."""
        summary = self._make_summary()
        assert summary.total_attempted == 4
        assert summary.successful == 2
        assert summary.not_found == 1
        assert summary.errors == 1
        assert summary.junk_count == 1

    def test_get_errors_returns_error_results(self) -> None:
        """get_errors returns only ERROR status results."""
        summary = self._make_summary()
        errors = summary.get_errors()
        assert len(errors) == 1
        assert errors[0].locale == "fr"

    def test_get_not_found_returns_not_found_results(self) -> None:
        """get_not_found returns only NOT_FOUND status results."""
        summary = self._make_summary()
        not_found = summary.get_not_found()
        assert len(not_found) == 1
        assert not_found[0].locale == "de"

    def test_get_successful_returns_success_results(self) -> None:
        """get_successful returns only SUCCESS status results."""
        summary = self._make_summary()
        successful = summary.get_successful()
        assert len(successful) == 2

    def test_get_by_locale_filters_correctly(self) -> None:
        """get_by_locale returns results for specified locale only."""
        summary = self._make_summary()
        en_results = summary.get_by_locale("en")
        assert len(en_results) == 2
        assert all(r.locale == "en" for r in en_results)

    def test_get_with_junk_returns_junk_results(self) -> None:
        """get_with_junk returns results with non-empty junk_entries."""
        summary = self._make_summary()
        junk_results = summary.get_with_junk()
        assert len(junk_results) == 1
        assert junk_results[0].resource_id == "junk.ftl"

    def test_get_all_junk_flattens_entries(self) -> None:
        """get_all_junk returns flattened tuple of all Junk entries."""
        summary = self._make_summary()
        all_junk = summary.get_all_junk()
        assert len(all_junk) == 1

    def test_has_errors_property(self) -> None:
        """has_errors reflects errors count."""
        summary = self._make_summary()
        assert summary.has_errors is True

        clean = LoadSummary(results=(
            ResourceLoadResult("en", "ok.ftl", LoadStatus.SUCCESS),
        ))
        assert clean.has_errors is False

    def test_has_junk_property(self) -> None:
        """has_junk reflects junk_count."""
        summary = self._make_summary()
        assert summary.has_junk is True

    def test_all_successful_ignores_junk(self) -> None:
        """all_successful is True even with junk, if no errors/not_found."""
        junk = Junk(content="j", span=Span(start=0, end=1))
        summary = LoadSummary(results=(
            ResourceLoadResult(
                "en", "ok.ftl", LoadStatus.SUCCESS,
                junk_entries=(junk,),
            ),
        ))
        assert summary.all_successful is True

    def test_all_clean_requires_zero_junk(self) -> None:
        """all_clean is False when junk exists even if all_successful."""
        junk = Junk(content="j", span=Span(start=0, end=1))
        summary = LoadSummary(results=(
            ResourceLoadResult(
                "en", "ok.ftl", LoadStatus.SUCCESS,
                junk_entries=(junk,),
            ),
        ))
        assert summary.all_successful is True
        assert summary.all_clean is False

    def test_all_clean_true_when_no_issues(self) -> None:
        """all_clean is True when no errors, not_found, or junk."""
        summary = LoadSummary(results=(
            ResourceLoadResult("en", "ok.ftl", LoadStatus.SUCCESS),
        ))
        assert summary.all_clean is True



class TestPathResourceLoaderInit:
    """PathResourceLoader initialization edge cases."""

    def test_empty_static_prefix_uses_cwd(self) -> None:
        """base_path starting with {locale} uses cwd as root."""
        loader = PathResourceLoader("{locale}/resources")
        assert loader._resolved_root == Path.cwd().resolve()

    def test_explicit_root_dir_overrides(self) -> None:
        """Explicit root_dir overrides base_path derivation."""
        loader = PathResourceLoader(
            "any/{locale}/path", root_dir="/tmp",
        )
        assert loader._resolved_root == Path("/tmp").resolve()

    def test_trailing_separators_stripped(self) -> None:
        """Trailing separators stripped from static prefix."""
        loader = PathResourceLoader("locales/{locale}////")
        assert loader._resolved_root == Path("locales").resolve()

    def test_multiple_locale_placeholders(self) -> None:
        """Multiple {locale} placeholders use first split part."""
        loader = PathResourceLoader("root/{locale}/sub/{locale}")
        assert loader._resolved_root == Path("root").resolve()



class TestHasAttribute:
    """Tests for has_attribute fallback chain search."""

    def test_attribute_in_primary_locale(self) -> None:
        """has_attribute finds attribute in primary locale."""
        l10n = FluentLocalization(["en", "de"])
        l10n.add_resource("en", "btn = Click\n    .tooltip = Help\n")
        assert l10n.has_attribute("btn", "tooltip") is True

    def test_attribute_in_fallback_locale(self) -> None:
        """has_attribute finds attribute in fallback locale."""
        l10n = FluentLocalization(["de", "en"])
        l10n.add_resource("en", "btn = Click\n    .tooltip = Help\n")
        assert l10n.has_attribute("btn", "tooltip") is True

    def test_attribute_not_found(self) -> None:
        """has_attribute returns False for nonexistent attribute."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "msg = No attrs\n")
        assert l10n.has_attribute("msg", "nonexistent") is False

    def test_message_not_found(self) -> None:
        """has_attribute returns False for nonexistent message."""
        l10n = FluentLocalization(["en"])
        assert l10n.has_attribute("missing", "attr") is False



class TestGetMessageIds:
    """Tests for get_message_ids union across locales."""

    def test_returns_union_of_ids(self) -> None:
        """get_message_ids returns union across all locales."""
        l10n = FluentLocalization(["en", "de"])
        l10n.add_resource("en", "msg-a = A\nmsg-b = B\n")
        l10n.add_resource("de", "msg-b = B2\nmsg-c = C\n")
        ids = l10n.get_message_ids()
        assert set(ids) == {"msg-a", "msg-b", "msg-c"}

    def test_no_duplicates(self) -> None:
        """get_message_ids has no duplicate IDs."""
        l10n = FluentLocalization(["en", "de"])
        l10n.add_resource("en", "msg = A\n")
        l10n.add_resource("de", "msg = B\n")
        ids = l10n.get_message_ids()
        assert len(ids) == len(set(ids))

    def test_primary_locale_ids_first(self) -> None:
        """Primary locale IDs appear before fallback IDs."""
        l10n = FluentLocalization(["en", "de"])
        l10n.add_resource("en", "alpha = A\n")
        l10n.add_resource("de", "alpha = A2\nbeta = B\n")
        ids = l10n.get_message_ids()
        assert ids.index("alpha") < ids.index("beta")

    def test_empty_when_no_resources(self) -> None:
        """get_message_ids is empty when no resources loaded."""
        l10n = FluentLocalization(["en"])
        assert l10n.get_message_ids() == []



class TestGetMessageVariables:
    """Tests for get_message_variables with fallback."""

    def test_returns_variable_names(self) -> None:
        """get_message_variables returns frozenset of variable names."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource(
            "en", "greeting = Hello { $firstName } { $lastName }!\n",
        )
        variables = l10n.get_message_variables("greeting")
        assert isinstance(variables, frozenset)
        assert "firstName" in variables
        assert "lastName" in variables

    def test_fallback_chain_search(self) -> None:
        """get_message_variables searches fallback chain."""
        l10n = FluentLocalization(["de", "en"])
        l10n.add_resource("en", "msg = Value { $count }\n")
        variables = l10n.get_message_variables("msg")
        assert "count" in variables

    def test_raises_for_missing_message(self) -> None:
        """get_message_variables raises KeyError for missing message."""
        l10n = FluentLocalization(["en"])
        with pytest.raises(KeyError, match="not found"):
            l10n.get_message_variables("nonexistent")



class TestGetAllMessageVariables:
    """Tests for get_all_message_variables merged map."""

    def test_returns_dict_of_variable_sets(self) -> None:
        """get_all_message_variables returns dict mapping id -> frozenset."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource(
            "en", "msg1 = { $name }\nmsg2 = Static\n",
        )
        all_vars = l10n.get_all_message_variables()
        assert isinstance(all_vars, dict)
        assert "msg1" in all_vars
        assert "name" in all_vars["msg1"]
        assert "msg2" in all_vars

    def test_primary_locale_takes_precedence(self) -> None:
        """Primary locale variables win for duplicate message IDs."""
        l10n = FluentLocalization(["en", "de"])
        l10n.add_resource("en", "msg = { $primary }\n")
        l10n.add_resource("de", "msg = { $fallback }\n")
        all_vars = l10n.get_all_message_variables()
        assert "primary" in all_vars["msg"]

    def test_includes_fallback_only_messages(self) -> None:
        """Messages only in fallback locales are included."""
        l10n = FluentLocalization(["en", "de"])
        l10n.add_resource("en", "en-only = { $x }\n")
        l10n.add_resource("de", "de-only = { $y }\n")
        all_vars = l10n.get_all_message_variables()
        assert "en-only" in all_vars
        assert "de-only" in all_vars



class TestIntrospectTerm:
    """Tests for introspect_term with fallback chain."""

    def test_found_in_primary(self) -> None:
        """introspect_term returns introspection from primary locale."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "-brand = Firefox\n")
        info = l10n.introspect_term("brand")
        assert info is not None

    def test_found_in_fallback(self) -> None:
        """introspect_term searches fallback chain."""
        l10n = FluentLocalization(["de", "en"])
        l10n.add_resource("en", "-product = App\n")
        info = l10n.introspect_term("product")
        assert info is not None

    def test_not_found_returns_none(self) -> None:
        """introspect_term returns None for missing term."""
        l10n = FluentLocalization(["en"])
        info = l10n.introspect_term("nonexistent")
        assert info is None



class TestContextManager:
    """Tests for FluentLocalization context manager protocol."""

    def test_enter_returns_self(self) -> None:
        """__enter__ returns the FluentLocalization instance."""
        l10n = FluentLocalization(["en"])
        with l10n as ctx:
            assert ctx is l10n

    def test_lock_held_inside_context(self) -> None:
        """Lock is acquired inside context and released after."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "msg = Hello\n")
        with l10n:
            result, _ = l10n.format_value("msg")
            assert result == "Hello"

    def test_lock_released_on_exception(self) -> None:
        """Lock released even if exception occurs in context."""
        l10n = FluentLocalization(["en"])
        try:
            with l10n:
                msg = "test"
                raise ValueError(msg)
        except ValueError:
            pass
        # Should not deadlock
        l10n.add_resource("en", "msg = Works\n")
        result, _ = l10n.format_value("msg")
        assert result == "Works"




class TestResourceLoadingErrors:
    """Tests for error handling during resource loading."""

    def test_custom_loader_source_path_format(self) -> None:
        """Non-PathResourceLoader uses locale/resource_id format."""

        class DictLoader:
            def load(self, locale: str, _resource_id: str) -> str:
                return f"msg = Hello from {locale}\n"

        l10n = FluentLocalization(
            ["en", "de"], ["main.ftl"], DictLoader(),
        )
        summary = l10n.get_load_summary()
        assert summary.total_attempted == 2
        for result in summary.results:
            assert result.source_path is not None
            assert "/" in result.source_path

    def test_oserror_recorded_as_error(self) -> None:
        """OSError during loading recorded with ERROR status."""

        class FailLoader:
            def load(
                self, _locale: str, _resource_id: str,
            ) -> str:
                msg = "Permission denied"
                raise OSError(msg)

        l10n = FluentLocalization(["en"], ["main.ftl"], FailLoader())
        summary = l10n.get_load_summary()
        assert summary.errors == 1
        assert isinstance(summary.get_errors()[0].error, OSError)

    def test_valueerror_recorded_as_error(self) -> None:
        """ValueError during loading recorded with ERROR status."""

        class FailLoader:
            def load(
                self, _locale: str, _resource_id: str,
            ) -> str:
                msg = "Path traversal"
                raise ValueError(msg)

        l10n = FluentLocalization(["en"], ["main.ftl"], FailLoader())
        summary = l10n.get_load_summary()
        assert summary.errors == 1
        assert isinstance(summary.get_errors()[0].error, ValueError)

    def test_file_not_found_recorded_as_not_found(self) -> None:
        """FileNotFoundError recorded as NOT_FOUND status."""

        class MissingLoader:
            def load(
                self, _locale: str, _resource_id: str,
            ) -> str:
                msg = "Not found"
                raise FileNotFoundError(msg)

        l10n = FluentLocalization(["en"], ["main.ftl"], MissingLoader())
        summary = l10n.get_load_summary()
        assert summary.not_found == 1

    def test_get_load_summary_returns_summary(self) -> None:
        """get_load_summary returns LoadSummary from init phase."""
        l10n = FluentLocalization(["en"])
        summary = l10n.get_load_summary()
        assert isinstance(summary, LoadSummary)
        assert summary.total_attempted == 0  # No resource_ids provided



class TestCacheStatsBranch:
    """Tests for get_cache_stats aggregation branch."""

    def test_aggregates_across_multiple_bundles(self) -> None:
        """get_cache_stats sums metrics across all bundles."""
        l10n = FluentLocalization(
            ["en", "de"], enable_cache=True, cache_size=500,
        )
        l10n.add_resource("en", "msg = Hello\n")
        l10n.add_resource("de", "msg = Hallo\n")

        # Format to create cache entries
        l10n.format_value("msg")

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["bundle_count"] == 2
        assert stats["maxsize"] == 1000  # 500 * 2

    def test_empty_bundles_returns_zero_stats(self) -> None:
        """get_cache_stats returns zero stats with no initialized bundles."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["bundle_count"] == 0
        assert stats["size"] == 0

    def test_hit_rate_calculated_correctly(self) -> None:
        """Hit rate is hits/(hits+misses)*100."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello\n")
        l10n.format_value("msg")  # miss
        l10n.format_value("msg")  # hit
        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["hit_rate"] == 50.0

    def test_skips_bundle_with_no_cache(self) -> None:
        """Bundles returning None from get_cache_stats are skipped."""
        l10n = FluentLocalization(
            ["en", "de"], enable_cache=True, cache_size=100,
        )
        # Create cached bundle for "en"
        l10n.add_resource("en", "msg = Hello\n")
        l10n.format_value("msg")

        # Inject a no-cache bundle for "de" directly
        no_cache_bundle = FluentBundle("de", enable_cache=False)
        no_cache_bundle.add_resource("msg = Hallo\n")
        l10n._bundles["de"] = no_cache_bundle

        stats = l10n.get_cache_stats()
        assert stats is not None
        # Only "en" bundle contributes stats
        assert stats["bundle_count"] == 2
        assert stats["maxsize"] == 100  # Only en's maxsize



class TestRepr:
    """Tests for __repr__ format."""

    def test_includes_locales_and_bundle_count(self) -> None:
        """__repr__ shows locales and initialized/total bundles."""
        l10n = FluentLocalization(["en", "de"])
        r = repr(l10n)
        assert "FluentLocalization" in r
        assert "locales=('en', 'de')" in r
        assert "bundles=0/2" in r

    def test_bundle_count_updates_after_access(self) -> None:
        """__repr__ bundle count reflects initialized bundles."""
        l10n = FluentLocalization(["en", "de"])
        l10n.add_resource("en", "msg = test")
        r = repr(l10n)
        assert "bundles=1/2" in r
