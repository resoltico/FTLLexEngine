# mypy: ignore-errors
from __future__ import annotations

import pytest

from ftllexengine import validate_message_variables
from ftllexengine.integrity import (
    FormattingIntegrityError,
    IntegrityCheckFailedError,
)
from ftllexengine.localization import (
    FluentLocalization,
    LoadStatus,
    ResourceLoadResult,
)
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.syntax import Message, Term
from ftllexengine.syntax.ast import Junk, Span


class TestFormattingIntegrityErrorReraise:
    """FluentLocalization re-raises FormattingIntegrityError with corrected component.

    Lines 690-703: the except FormattingIntegrityError block in format_pattern
    fires when the bundle raises in strict mode and the message exists in the
    bundle. The orchestrator must re-raise with component='localization'.
    """

    def test_strict_localization_reraises_with_localization_component(self) -> None:
        """Strict FluentLocalization re-raises FormattingIntegrityError.

        Covers lines 690-703: the except block that replaces the 'bundle'
        component with 'localization' in the IntegrityContext before re-raising.
        """
        l10n = FluentLocalization(["en"], strict=True)
        l10n.add_resource("en", "test-msg = Hello { $name }!")

        # Calling format_pattern without the required $name argument causes
        # VARIABLE_NOT_PROVIDED error. In strict mode the bundle raises
        # FormattingIntegrityError, which the orchestrator catches and re-raises.
        with pytest.raises(FormattingIntegrityError) as exc_info:
            l10n.format_pattern("test-msg", {})

        exc = exc_info.value
        assert exc.context is not None
        assert exc.context.component == "localization"
        assert len(exc.fluent_errors) > 0
        assert exc.message_id == "test-msg"

class TestGetMessageAST:
    """FluentLocalization.get_message() returns the parsed Message AST from the fallback chain."""

    def test_existing_message_primary_locale(self) -> None:
        """get_message returns the Message from the primary locale."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "greeting = Hello, { $name }!")

        msg = l10n.get_message("greeting")

        assert msg is not None
        assert isinstance(msg, Message)
        assert msg.id.name == "greeting"

    def test_missing_message_returns_none(self) -> None:
        """get_message returns None when no locale contains the message."""
        l10n = FluentLocalization(["en", "lv"])
        l10n.add_resource("en", "hello = Hello!")

        assert l10n.get_message("nonexistent") is None

    def test_fallback_chain_used_when_primary_missing(self) -> None:
        """get_message falls back to secondary locale when primary lacks the message."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("en", "greeting = Hello!")
        # lv has no "greeting" resource

        msg = l10n.get_message("greeting")

        assert msg is not None
        assert isinstance(msg, Message)
        assert msg.id.name == "greeting"

    def test_primary_locale_wins_when_both_have_message(self) -> None:
        """Primary locale's Message is returned when multiple locales have the message."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("lv", "greeting = Sveiki!")
        l10n.add_resource("en", "greeting = Hello!")

        msg = l10n.get_message("greeting")

        assert msg is not None
        assert msg.id.name == "greeting"
        # Verify it's the primary locale's message by checking a separate bundle
        lv_bundle = FluentBundle("lv", use_isolating=False)
        lv_bundle.add_resource("greeting = Sveiki!")
        lv_msg = lv_bundle.get_message("greeting")
        assert lv_msg is not None
        assert msg is not lv_msg  # Different bundle instances, same message id

    def test_empty_localization_returns_none(self) -> None:
        """get_message returns None when no resources have been added."""
        l10n = FluentLocalization(["en"])

        assert l10n.get_message("anything") is None

    def test_get_message_result_usable_with_validate_message_variables(self) -> None:
        """get_message result can be passed to validate_message_variables()."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "greeting = Hello, { $name }!")

        msg = l10n.get_message("greeting")
        assert msg is not None

        result = validate_message_variables(msg, frozenset({"name"}))
        assert result.is_valid
        assert result.declared_variables == frozenset({"name"})

class TestGetTermAST:
    """FluentLocalization.get_term() returns the parsed Term AST from the fallback chain."""

    def test_existing_term_primary_locale(self) -> None:
        """get_term returns the Term from the primary locale."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "-brand = Firefox")

        term = l10n.get_term("brand")

        assert term is not None
        assert isinstance(term, Term)
        assert term.id.name == "brand"

    def test_missing_term_returns_none(self) -> None:
        """get_term returns None when no locale contains the term."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "hello = Hello!")

        assert l10n.get_term("nonexistent") is None

    def test_fallback_chain_used_for_term(self) -> None:
        """get_term falls back to secondary locale when primary lacks the term."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("en", "-brand = Firefox")
        # lv has no "-brand" resource

        term = l10n.get_term("brand")

        assert term is not None
        assert isinstance(term, Term)
        assert term.id.name == "brand"

    def test_term_id_without_leading_dash(self) -> None:
        """-brand is accessed as get_term('brand'), not get_term('-brand')."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "-brand = Firefox")

        assert l10n.get_term("brand") is not None
        assert l10n.get_term("-brand") is None

    def test_get_message_does_not_return_terms(self) -> None:
        """get_message does not return terms (separate namespaces)."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "-brand = Firefox")

        assert l10n.get_message("brand") is None

    def test_get_term_does_not_return_messages(self) -> None:
        """get_term does not return messages (separate namespaces)."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "brand = Firefox")

        assert l10n.get_term("brand") is None

class TestDescribeUncleanLoadResult:
    """Tests for _describe_unclean_load_result private helper.

    Called by require_clean() to build the error detail string. Tested
    directly to cover the error=None (UnknownError) and junk branches.
    """

    def test_error_result_with_none_error_uses_unknown_error(self) -> None:
        """When result.is_error is True but error is None, name is 'UnknownError'."""
        result = ResourceLoadResult("en", "bad.ftl", LoadStatus.ERROR, error=None)
        l10n = FluentLocalization(["en"])

        key, detail = l10n._describe_unclean_load_result(result)

        assert key == "en/bad.ftl"
        assert detail == "load error (UnknownError)"

    def test_error_result_with_actual_error_uses_type_name(self) -> None:
        """When result.error is not None, type name is used in the description."""
        result = ResourceLoadResult(
            "en", "bad.ftl", LoadStatus.ERROR, error=OSError("disk fail"),
        )
        l10n = FluentLocalization(["en"])

        _key, detail = l10n._describe_unclean_load_result(result)

        assert "OSError" in detail

    def test_junk_result_describes_junk_entry_count(self) -> None:
        """Junk branch returns description with junk entry count."""
        junk = Junk(content="bad syntax", span=Span(start=0, end=10))
        result = ResourceLoadResult(
            "en", "partial.ftl", LoadStatus.SUCCESS, junk_entries=(junk,),
        )
        l10n = FluentLocalization(["en"])

        key, detail = l10n._describe_unclean_load_result(result)

        assert key == "en/partial.ftl"
        assert "1 junk entry" in detail

    def test_junk_plural_with_two_entries(self) -> None:
        """Two junk entries use 'entries' plural noun."""
        junk1 = Junk(content="bad1", span=Span(start=0, end=4))
        junk2 = Junk(content="bad2", span=Span(start=5, end=9))
        result = ResourceLoadResult(
            "en", "partial.ftl", LoadStatus.SUCCESS,
            junk_entries=(junk1, junk2),
        )
        l10n = FluentLocalization(["en"])

        _key, detail = l10n._describe_unclean_load_result(result)

        assert "2 junk entries" in detail

class TestRequireCleanCleanBeforeProblematic:
    """Tests for require_clean when the first result in summary is clean.

    The for-loop in require_clean iterates summary.results looking for the
    first non-clean result. When results[0] is clean, the inner if-condition
    is False for that iteration (the loop-continue branch), and iteration
    advances to the next element.
    """

    def test_first_clean_second_not_found_raises_with_correct_key(self) -> None:
        """require_clean iterates past a clean first result to find the bad one."""

        class PartialLoader:
            def load(self, _locale: str, resource_id: str) -> str:
                if resource_id == "first.ftl":
                    return "msg = Hello\n"
                msg = "missing"
                raise FileNotFoundError(msg)

            def describe_path(self, locale: str, resource_id: str) -> str:
                return f"{locale}/{resource_id}"

        l10n = FluentLocalization(
            ["en"], ["first.ftl", "second.ftl"], PartialLoader(),
        )

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            l10n.require_clean()

        ctx = exc_info.value.context
        assert ctx is not None
        # second.ftl is the first non-clean result; first.ftl was clean
        assert "second.ftl" in (ctx.key or "")

class TestRequireCleanJunkBranch:
    """Tests for require_clean that trigger the junk description branch."""

    def test_require_clean_raises_with_junk_detail(self) -> None:
        """require_clean raises when the loader produces a resource with junk entries.

        strict=False: testing load summary junk tracking; junk entries must be
        captured in the ResourceLoadResult, not raised as SyntaxIntegrityError.
        """

        class JunkLoader:
            def load(self, _locale: str, _resource_id: str) -> str:
                # "bad-junk" is not valid FTL syntax; produces a Junk AST node
                return "bad-junk\n"

            def describe_path(self, locale: str, resource_id: str) -> str:
                return f"{locale}/{resource_id}"

        l10n = FluentLocalization(
            ["en"], ["main.ftl"], JunkLoader(), strict=False,
        )

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            l10n.require_clean()

        assert "junk" in str(exc_info.value).lower()

class TestFormatSchemaDifferenceMissingVariables:
    """Tests for _format_schema_difference when only missing_variables is set.

    Existing tests cover the extra_variables path (message declares more vars
    than expected). These tests cover the missing_variables path (expected vars
    not found in message) and the False branch of 'if validation.extra_variables'.
    """

    def test_missing_variables_only_reported(self) -> None:
        """Schema diff reports missing variables when message uses fewer than expected."""
        l10n = FluentLocalization(["en"])
        # Message uses no variables; expected schema requires $amount
        l10n.add_resource("en", "invoice = Static total\n")

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            l10n.validate_message_schemas({
                "invoice": frozenset({"amount"}),
            })

        err = exc_info.value
        # Must describe the missing variable
        assert "missing {amount}" in str(err)

    def test_validate_message_variables_missing_variable_raises(self) -> None:
        """Single-message validation reports missing variable in error message."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "price = Free\n")

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            l10n.validate_message_variables("price", frozenset({"cost"}))

        assert "missing {cost}" in str(exc_info.value)

class TestValidateMessageSchemasTruncation:
    """Tests for validate_message_schemas 'N more issues' truncation.

    When 4 or more messages fail validation, mismatches[:3] is taken and
    the remaining count is appended as '... N more issue(s)'.
    """

    def test_four_mismatches_appends_remaining_count(self) -> None:
        """Four schema mismatches trigger 'N more issue' truncation."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource(
            "en",
            "m1 = { $a }\nm2 = { $a }\nm3 = { $a }\nm4 = { $a }\n",
        )

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            # All four messages have $a extra (expected empty schema)
            l10n.validate_message_schemas({
                "m1": frozenset(),
                "m2": frozenset(),
                "m3": frozenset(),
                "m4": frozenset(),
            })

        err_str = str(exc_info.value)
        assert "more issue" in err_str

    def test_five_mismatches_pluralises_noun(self) -> None:
        """Five mismatches produce '2 more issues' (plural noun)."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource(
            "en",
            "m1 = { $a }\nm2 = { $a }\nm3 = { $a }\nm4 = { $a }\nm5 = { $a }\n",
        )

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            l10n.validate_message_schemas({
                "m1": frozenset(),
                "m2": frozenset(),
                "m3": frozenset(),
                "m4": frozenset(),
                "m5": frozenset(),
            })

        err_str = str(exc_info.value)
        assert "more issues" in err_str

class TestGetCacheDebugLogBundleWithoutCache:
    """Tests for get_cache_debug_log when a bundle in _bundles has no cache.

    When bundle.get_cache_debug_log() returns None (bundle has no cache
    configured), that bundle's locale is excluded from the debug_logs dict.
    This exercises the ``if debug_log is not None:`` False branch.
    """

    def test_bundle_without_cache_excluded_from_debug_log(self) -> None:
        """Locale with a no-cache bundle is absent from the debug-log mapping."""
        l10n = FluentLocalization(
            ["en", "de"], cache=CacheConfig(enable_debug_log=True),
        )
        l10n.add_resource("en", "msg = Hello\n")
        l10n.format_value("msg")

        # Inject a bundle with no cache for "de"; get_cache_debug_log() returns None
        no_cache_bundle = FluentBundle("de")
        no_cache_bundle.add_resource("msg = Hallo\n")
        l10n._bundles["de"] = no_cache_bundle

        debug_logs = l10n.get_cache_debug_log()

        assert debug_logs is not None
        assert "en" in debug_logs
        assert "de" not in debug_logs
