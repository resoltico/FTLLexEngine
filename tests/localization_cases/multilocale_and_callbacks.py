# mypy: ignore-errors
from __future__ import annotations

from pathlib import Path

from ftllexengine import FluentBundle
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.localization import (
    FallbackInfo,
    FluentLocalization,
    PathResourceLoader,
)


class TestMultiLocaleFileLoading:
    """Tests for multi-locale file loading workflows.

    These tests verify the end-to-end workflow of loading FTL files
    from disk across multiple locales with proper fallback behavior.
    """

    def test_load_multiple_files_per_locale(self, tmp_path: Path) -> None:
        """Multiple FTL files per locale are loaded and merged correctly."""
        locales_dir = tmp_path / "locales"

        # Create en locale with multiple files
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text("welcome = Welcome!", encoding="utf-8")
        (en_dir / "errors.ftl").write_text("error-404 = Not Found", encoding="utf-8")
        (en_dir / "buttons.ftl").write_text("submit = Submit", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(
            ["en"], ["main.ftl", "errors.ftl", "buttons.ftl"], loader
        )

        # All messages from all files should be available
        welcome, _ = l10n.format_value("welcome")
        error, _ = l10n.format_value("error-404")
        submit, _ = l10n.format_value("submit")

        assert welcome == "Welcome!"
        assert error == "Not Found"
        assert submit == "Submit"

    def test_fallback_across_multiple_files(self, tmp_path: Path) -> None:
        """Fallback works correctly across multiple files and locales."""
        locales_dir = tmp_path / "locales"

        # Create en locale (complete)
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text("home = Home\nabout = About", encoding="utf-8")
        (en_dir / "errors.ftl").write_text("error-404 = Not Found", encoding="utf-8")

        # Create de locale (partial - missing errors.ftl)
        de_dir = locales_dir / "de"
        de_dir.mkdir(parents=True)
        (de_dir / "main.ftl").write_text("home = Startseite\nabout = Uber uns", encoding="utf-8")
        # Note: de/errors.ftl intentionally missing

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["de", "en"], ["main.ftl", "errors.ftl"], loader)

        # de messages should come from de
        home, _ = l10n.format_value("home")
        assert home == "Startseite"

        # error should fall back to en (de/errors.ftl missing)
        error, _ = l10n.format_value("error-404")
        assert error == "Not Found"

    def test_partial_translation_within_file(self, tmp_path: Path) -> None:
        """Partial translations within a file fall back correctly."""
        locales_dir = tmp_path / "locales"

        # Create en locale (complete)
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text(
            "home = Home\nabout = About\ncontact = Contact", encoding="utf-8"
        )

        # Create fr locale (partial translations)
        fr_dir = locales_dir / "fr"
        fr_dir.mkdir(parents=True)
        (fr_dir / "main.ftl").write_text("home = Accueil", encoding="utf-8")
        # Note: about and contact missing in fr

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["fr", "en"], ["main.ftl"], loader)

        # fr message from fr
        home, _ = l10n.format_value("home")
        assert home == "Accueil"

        # missing fr messages fall back to en
        about, _ = l10n.format_value("about")
        contact, _ = l10n.format_value("contact")
        assert about == "About"
        assert contact == "Contact"

    def test_three_locale_fallback_chain(self, tmp_path: Path) -> None:
        """Three-locale fallback chain works correctly."""
        locales_dir = tmp_path / "locales"

        # en has all messages
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text(
            "level1 = English One\nlevel2 = English Two\nlevel3 = English Three",
            encoding="utf-8"
        )

        # de has two messages
        de_dir = locales_dir / "de"
        de_dir.mkdir(parents=True)
        (de_dir / "main.ftl").write_text(
            "level1 = Deutsch Eins\nlevel2 = Deutsch Zwei",
            encoding="utf-8"
        )

        # fr has one message
        fr_dir = locales_dir / "fr"
        fr_dir.mkdir(parents=True)
        (fr_dir / "main.ftl").write_text("level1 = Francais Un", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["fr", "de", "en"], ["main.ftl"], loader)

        # level1 from fr (first locale)
        level1, _ = l10n.format_value("level1")
        assert level1 == "Francais Un"

        # level2 from de (second locale, fr doesn't have it)
        level2, _ = l10n.format_value("level2")
        assert level2 == "Deutsch Zwei"

        # level3 from en (third locale, fr and de don't have it)
        level3, _ = l10n.format_value("level3")
        assert level3 == "English Three"

    def test_unicode_content_in_files(self, tmp_path: Path) -> None:
        """FTL files containing CJK and accented Unicode characters load correctly."""
        locales_dir = tmp_path / "locales"

        ja_dir = locales_dir / "ja"
        ja_dir.mkdir(parents=True)
        (ja_dir / "main.ftl").write_text(
            "greeting = \u3053\u3093\u306b\u3061\u306f\u4e16\u754c", encoding="utf-8"
        )

        lv_dir = locales_dir / "lv"
        lv_dir.mkdir(parents=True)
        (lv_dir / "main.ftl").write_text("greeting = Sveiki, pasaule!", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))

        l10n_ja = FluentLocalization(["ja"], ["main.ftl"], loader)
        l10n_lv = FluentLocalization(["lv"], ["main.ftl"], loader)

        ja_greeting, _ = l10n_ja.format_value("greeting")
        lv_greeting, _ = l10n_lv.format_value("greeting")

        assert "\u3053\u3093\u306b\u3061\u306f" in ja_greeting
        assert lv_greeting == "Sveiki, pasaule!"

    def test_missing_locale_directory_falls_back(self, tmp_path: Path) -> None:
        """Missing locale directory gracefully falls back to next locale."""
        locales_dir = tmp_path / "locales"

        # Only create en directory (no de)
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text("greeting = Hello!", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        # de is first but doesn't exist
        l10n = FluentLocalization(["de", "en"], ["main.ftl"], loader)

        # Should fall back to en
        greeting, _ = l10n.format_value("greeting")
        assert greeting == "Hello!"

    def test_empty_file_handled_gracefully(self, tmp_path: Path) -> None:
        """Empty FTL files are handled without errors."""
        locales_dir = tmp_path / "locales"

        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "empty.ftl").write_text("", encoding="utf-8")
        (en_dir / "main.ftl").write_text("greeting = Hello!", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["en"], ["empty.ftl", "main.ftl"], loader)

        # Should still work - empty file just adds no messages
        greeting, _ = l10n.format_value("greeting")
        assert greeting == "Hello!"

    def test_file_with_only_comments(self, tmp_path: Path) -> None:
        """FTL files with only comments are handled correctly."""
        locales_dir = tmp_path / "locales"

        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "comments.ftl").write_text(
            "# This file has only comments\n## Section comment\n### Resource comment",
            encoding="utf-8"
        )
        (en_dir / "main.ftl").write_text("greeting = Hello!", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["en"], ["comments.ftl", "main.ftl"], loader)

        # Should work - comments file adds no messages
        greeting, _ = l10n.format_value("greeting")
        assert greeting == "Hello!"

    def test_variables_in_file_loaded_messages(self, tmp_path: Path) -> None:
        """Variables work correctly in file-loaded messages."""
        locales_dir = tmp_path / "locales"

        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text(
            "greeting = Hello, { $name }!\ncount = You have { $n } items.",
            encoding="utf-8"
        )

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["en"], ["main.ftl"], loader, use_isolating=False)

        greeting, _ = l10n.format_value("greeting", {"name": "World"})
        count, _ = l10n.format_value("count", {"n": 42})

        assert greeting == "Hello, World!"
        assert "42" in count

class TestOnFallbackCallback:
    """on_fallback callback is invoked when a message resolves from a fallback locale."""

    def test_on_fallback_invoked_on_format_value(self) -> None:
        """on_fallback callback invoked when message resolved from fallback locale."""
        fallback_events: list[FallbackInfo] = []

        def record_fallback(info: FallbackInfo) -> None:
            fallback_events.append(info)

        l10n = FluentLocalization(["lv", "en"], on_fallback=record_fallback)

        # Add message only to fallback locale (en)
        l10n.add_resource("en", "fallback-msg = English fallback")

        # Request message - should trigger fallback
        result, _ = l10n.format_value("fallback-msg")

        assert result == "English fallback"
        assert len(fallback_events) == 1
        assert fallback_events[0].requested_locale == normalize_locale("lv")
        assert fallback_events[0].resolved_locale == normalize_locale("en")
        assert fallback_events[0].message_id == "fallback-msg"

    def test_on_fallback_invoked_on_format_pattern(self) -> None:
        """on_fallback callback invoked in format_pattern when using fallback locale."""
        fallback_events: list[FallbackInfo] = []

        def record_fallback(info: FallbackInfo) -> None:
            fallback_events.append(info)

        l10n = FluentLocalization(["de", "en"], on_fallback=record_fallback)

        # Add message only to fallback locale (en)
        l10n.add_resource("en", "pattern-msg = Pattern from fallback")

        # Request message via format_pattern - should trigger fallback
        result, _ = l10n.format_pattern("pattern-msg")

        assert result == "Pattern from fallback"
        assert len(fallback_events) == 1
        assert fallback_events[0].requested_locale == normalize_locale("de")
        assert fallback_events[0].resolved_locale == normalize_locale("en")
        assert fallback_events[0].message_id == "pattern-msg"

    def test_on_fallback_not_invoked_for_primary_locale(self) -> None:
        """on_fallback not invoked when message found in primary locale."""
        fallback_events: list[FallbackInfo] = []

        def record_fallback(info: FallbackInfo) -> None:
            fallback_events.append(info)

        l10n = FluentLocalization(["fr", "en"], on_fallback=record_fallback)

        # Add message to primary locale (fr)
        l10n.add_resource("fr", "french-msg = Message en francais")

        result, _ = l10n.format_value("french-msg")

        assert result == "Message en francais"
        assert len(fallback_events) == 0  # No fallback occurred

    def test_on_fallback_none_does_not_raise(self) -> None:
        """on_fallback=None (default) works without errors."""
        l10n = FluentLocalization(["lv", "en"])

        l10n.add_resource("en", "msg = No callback")

        # Should not raise even without callback
        result, _ = l10n.format_value("msg")
        assert result == "No callback"

    def test_on_fallback_multiple_calls(self) -> None:
        """on_fallback invoked for each fallback resolution."""
        fallback_events: list[FallbackInfo] = []

        def record_fallback(info: FallbackInfo) -> None:
            fallback_events.append(info)

        l10n = FluentLocalization(["it", "en"], on_fallback=record_fallback)

        l10n.add_resource("en", "msg1 = First\nmsg2 = Second")

        l10n.format_value("msg1")
        l10n.format_value("msg2")

        assert len(fallback_events) == 2
        assert fallback_events[0].message_id == "msg1"
        assert fallback_events[1].message_id == "msg2"

    def test_on_fallback_with_format_pattern_and_attribute(self) -> None:
        """on_fallback invoked in format_pattern with attribute access."""
        fallback_events: list[FallbackInfo] = []

        def record_fallback(info: FallbackInfo) -> None:
            fallback_events.append(info)

        l10n = FluentLocalization(["es", "en"], on_fallback=record_fallback)

        l10n.add_resource(
            "en",
            """
button = Click
    .tooltip = Button tooltip
""",
        )

        # Request attribute via format_pattern
        result, _ = l10n.format_pattern("button", attribute="tooltip")

        assert result == "Button tooltip"
        assert len(fallback_events) == 1
        assert fallback_events[0].message_id == "button"

class TestCrossFileDepthValidation:
    """Reference depth limits are enforced even when the chain spans multiple add_resource calls."""

    def test_deep_reference_chain_across_resources(self) -> None:
        """Reference chains spanning multiple resources respect depth limits.

        When messages reference each other across multiple add_resource calls,
        the total depth limit should still be enforced.
        """
        l10n = FluentLocalization(["en"], use_isolating=False)

        # Add resources separately - chain: level5 -> level4 -> level3 -> level2 -> level1 -> base
        l10n.add_resource("en", "base = Base value")
        l10n.add_resource("en", "level1 = L1: { base }")
        l10n.add_resource("en", "level2 = L2: { level1 }")
        l10n.add_resource("en", "level3 = L3: { level2 }")
        l10n.add_resource("en", "level4 = L4: { level3 }")
        l10n.add_resource("en", "level5 = L5: { level4 }")

        # Should resolve successfully (depth 6 is within default limit of 50)
        result, errors = l10n.format_value("level5")

        assert not errors
        assert "Base value" in result
        assert "L1:" in result
        assert "L5:" in result

    def test_very_deep_reference_chain_is_limited(self) -> None:
        """Reference chains exceeding max_nesting_depth produce errors, not stack overflow."""
        bundle = FluentBundle("en", use_isolating=False, max_nesting_depth=10, strict=False)

        # Build a chain deeper than max_nesting_depth
        bundle.add_resource("level0 = Base")
        for i in range(1, 15):  # 15 levels, exceeds max_depth of 10
            bundle.add_resource(f"level{i} = Chain {{ level{i-1} }}")

        # Resolving the deepest level should hit depth limit
        result, errors = bundle.format_pattern("level14")

        # Depth limit exceeded must produce resolution errors
        assert len(errors) > 0, f"Expected depth limit errors; got result={result!r}"

    def test_cross_file_term_reference_depth(self) -> None:
        """Term references across resources are tracked for depth.

        Terms (-name syntax) referenced across multiple resources
        should also respect depth limits.
        """
        l10n = FluentLocalization(["en"], use_isolating=False)

        # Add terms and messages across resources
        l10n.add_resource("en", "-brand = Firefox")
        l10n.add_resource("en", "-product = { -brand } Browser")
        l10n.add_resource("en", "title = Welcome to { -product }")
        l10n.add_resource("en", "subtitle = { title } - Get Started")

        result, errors = l10n.format_value("subtitle")

        assert not errors
        assert "Firefox" in result
        assert "Browser" in result
        assert "Welcome" in result

    def test_cross_locale_depth_isolation(self) -> None:
        """Depth limits are applied per-resolution, not accumulating across locales.

        When falling back through locales, each resolution attempt
        should have its own depth counter, not share state.
        """
        l10n = FluentLocalization(["de", "en"], use_isolating=False)

        # German has deep chain
        l10n.add_resource("de", "a = DE-A")
        l10n.add_resource("de", "b = DE-B: { a }")
        l10n.add_resource("de", "c = DE-C: { b }")

        # English has different chain (also deep)
        l10n.add_resource("en", "x = EN-X")
        l10n.add_resource("en", "y = EN-Y: { x }")

        # Resolve German chain
        result_c, errors_c = l10n.format_value("c")
        assert not errors_c
        assert "DE-A" in result_c

        # Resolve English chain (falls back since not in de)
        result_y, errors_y = l10n.format_value("y")
        assert not errors_y
        assert "EN-X" in result_y

    def test_circular_reference_detection_across_resources(self) -> None:
        """Circular references across resources are detected.

        Even when circular references are created by adding resources
        separately, the resolver should detect and break the cycle.
        """
        l10n = FluentLocalization(["en"], use_isolating=False, strict=False)

        # Create circular reference: msg1 -> msg2 -> msg3 -> msg1
        l10n.add_resource("en", "msg1 = Start: { msg2 }")
        l10n.add_resource("en", "msg2 = Middle: { msg3 }")
        l10n.add_resource("en", "msg3 = End: { msg1 }")  # Circular!

        # Resolution should detect cycle and not stack overflow
        result, errors = l10n.format_value("msg1")

        # Should have errors (cycle detected) or produce partial result
        # The key is it doesn't hang or crash
        assert isinstance(result, str)
        assert len(errors) > 0 or "{" in result  # Either errors or unresolved placeholder

    def test_select_expression_depth_across_resources(self) -> None:
        """Select expressions in cross-resource chains respect depth.

        Complex patterns with select expressions referenced across
        resources should not bypass depth limits.
        """
        l10n = FluentLocalization(["en"], use_isolating=False)

        l10n.add_resource(
            "en",
            """
base = { $type ->
    [a] Type A
    [b] Type B
   *[other] Unknown
}
""",
        )
        l10n.add_resource("en", "wrapper = Result: { base }")
        l10n.add_resource("en", "outer = Final: { wrapper }")

        result, errors = l10n.format_value("outer", {"type": "a"})

        assert not errors
        assert "Type A" in result
        assert "Final:" in result
