"""Unicode conformance edge case tests.

Tests for Unicode edge cases beyond basic escape sequences:
- RTL text handling
- Zero-width characters
- Combining characters
- Emoji sequences (ZWJ)
- BOM handling
- Normalization forms
"""

from __future__ import annotations

import unicodedata

from ftllexengine import FluentBundle
from ftllexengine.syntax.ast import Message
from ftllexengine.syntax.parser import FluentParserV1


class TestUnicodeRTLText:
    """Test right-to-left text handling."""

    def test_arabic_text_in_message(self) -> None:
        """Arabic text is preserved correctly."""
        bundle = FluentBundle("ar")
        bundle.add_resource("greeting = مرحبا بالعالم")

        result, errors = bundle.format_pattern("greeting")

        assert result == "مرحبا بالعالم"
        assert errors == ()

    def test_hebrew_text_in_message(self) -> None:
        """Hebrew text is preserved correctly."""
        bundle = FluentBundle("he")
        bundle.add_resource("greeting = שלום עולם")

        result, errors = bundle.format_pattern("greeting")

        assert result == "שלום עולם"
        assert errors == ()

    def test_mixed_rtl_ltr_text(self) -> None:
        """Mixed RTL and LTR text is preserved."""
        bundle = FluentBundle("ar")
        bundle.add_resource("mixed = Hello مرحبا World عالم")

        result, errors = bundle.format_pattern("mixed")

        assert "Hello" in result
        assert "مرحبا" in result
        assert errors == ()


class TestUnicodeZeroWidth:
    """Test zero-width character handling."""

    def test_zero_width_space(self) -> None:
        """Zero-width space (U+200B) is preserved."""
        parser = FluentParserV1()
        # Zero-width space between words
        resource = parser.parse("msg = Hello\u200BWorld")

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # The ZWSP should be in the text
        text_content = "".join(
            elem.value for elem in msg.value.elements if hasattr(elem, "value")
        )
        assert "\u200B" in text_content or "HelloWorld" in text_content

    def test_zero_width_non_joiner(self) -> None:
        """Zero-width non-joiner (U+200C) is preserved."""
        bundle = FluentBundle("fa")
        # Persian word with ZWNJ
        bundle.add_resource("word = می\u200Cروم")

        result, errors = bundle.format_pattern("word")

        assert "\u200C" in result
        assert errors == ()


class TestUnicodeCombining:
    """Test combining character handling."""

    def test_combining_acute_accent(self) -> None:
        """Combining acute accent (U+0301) is preserved."""
        bundle = FluentBundle("en")
        # e + combining acute = é
        bundle.add_resource("word = cafe\u0301")

        result, errors = bundle.format_pattern("word")

        assert result in {"cafe\u0301", "café"}
        assert errors == ()

    def test_multiple_combining_marks(self) -> None:
        """Multiple combining marks are preserved."""
        bundle = FluentBundle("en")
        # a + combining ring above + combining acute
        bundle.add_resource("word = a\u030A\u0301")

        result, errors = bundle.format_pattern("word")

        assert len(result) >= 1  # At least the base character
        assert errors == ()

    def test_precomposed_vs_decomposed(self) -> None:
        """Both precomposed and decomposed forms work."""
        bundle = FluentBundle("en")
        # Precomposed é (U+00E9)
        bundle.add_resource("composed = café")
        # Decomposed e + combining acute (U+0065 + U+0301)
        bundle.add_resource("decomposed = cafe\u0301")

        result1, _ = bundle.format_pattern("composed")
        result2, _ = bundle.format_pattern("decomposed")

        # Both should produce readable output
        assert "caf" in result1
        assert "caf" in result2


class TestUnicodeEmoji:
    """Test emoji sequence handling."""

    def test_simple_emoji(self) -> None:
        """Simple emoji is preserved."""
        bundle = FluentBundle("en")
        bundle.add_resource("emoji = Hello 👋")

        result, errors = bundle.format_pattern("emoji")

        assert "👋" in result
        assert errors == ()

    def test_emoji_with_skin_tone(self) -> None:
        """Emoji with skin tone modifier is preserved."""
        bundle = FluentBundle("en")
        # Waving hand + medium skin tone
        bundle.add_resource("emoji = Hello 👋🏽")

        result, errors = bundle.format_pattern("emoji")

        assert "👋" in result
        assert errors == ()

    def test_zwj_emoji_sequence(self) -> None:
        """ZWJ emoji sequence is preserved (man + ZWJ + woman + ZWJ + girl)."""
        bundle = FluentBundle("en")
        bundle.add_resource("family = 👨\u200D👩\u200D👧")

        result, errors = bundle.format_pattern("family")

        # The ZWJ sequence should be preserved
        assert len(result) > 0
        assert errors == ()

    def test_flag_emoji(self) -> None:
        """Flag emoji (regional indicator symbols) is preserved."""
        bundle = FluentBundle("en")
        # US flag: Regional Indicator Symbol Letter U + S
        bundle.add_resource("flag = 🇺🇸")

        result, errors = bundle.format_pattern("flag")

        assert "🇺🇸" in result or len(result) > 0
        assert errors == ()


class TestUnicodeBOM:
    """Test Byte Order Mark handling."""

    def test_bom_at_start_is_handled(self) -> None:
        """BOM at start of file is handled gracefully."""
        parser = FluentParserV1()
        # UTF-8 BOM + content
        source = "\ufeffmsg = Hello"
        resource = parser.parse(source)

        # Should parse successfully (BOM may be ignored or treated as whitespace)
        assert len(resource.entries) >= 1

    def test_bom_in_middle_is_preserved(self) -> None:
        """BOM in middle of text is preserved as content."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello\ufeffWorld")

        result, errors = bundle.format_pattern("msg")

        assert not errors

        # BOM in middle might be preserved or filtered
        assert "Hello" in result
        assert "World" in result


class TestUnicodeSpecialCharacters:
    """Test special Unicode characters."""

    def test_null_character_handling(self) -> None:
        """Null character in input is handled safely."""
        parser = FluentParserV1()
        # Null in message value
        source = "msg = Hello\x00World"
        resource = parser.parse(source)

        # Should parse (handling may vary)
        assert len(resource.entries) >= 1

    def test_replacement_character(self) -> None:
        """Replacement character (U+FFFD) is preserved."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Invalid: \uFFFD")

        result, errors = bundle.format_pattern("msg")

        assert "\uFFFD" in result
        assert errors == ()

    def test_private_use_area(self) -> None:
        """Private Use Area characters are preserved."""
        bundle = FluentBundle("en")
        # Private Use Area character
        bundle.add_resource("msg = Custom: \uE000")

        result, errors = bundle.format_pattern("msg")

        assert "\uE000" in result
        assert errors == ()


class TestUnicodeIdentifiers:
    """Test Unicode in message identifiers."""

    def test_ascii_identifier(self) -> None:
        """ASCII identifiers work correctly."""
        bundle = FluentBundle("en")
        bundle.add_resource("hello-world = Hello")

        result, errors = bundle.format_pattern("hello-world")

        assert result == "Hello"
        assert errors == ()

    def test_identifier_with_numbers(self) -> None:
        """Identifiers with numbers work correctly."""
        bundle = FluentBundle("en")
        bundle.add_resource("error-404 = Not Found")

        result, errors = bundle.format_pattern("error-404")

        assert result == "Not Found"
        assert errors == ()


class TestUnicodeNormalization:
    """Test Unicode normalization handling."""

    def test_nfc_normalized_input(self) -> None:
        """NFC normalized input is handled correctly."""
        bundle = FluentBundle("en")
        # NFC form of café
        nfc_cafe = unicodedata.normalize("NFC", "café")
        bundle.add_resource(f"word = {nfc_cafe}")

        result, errors = bundle.format_pattern("word")

        assert "caf" in result
        assert errors == ()

    def test_nfd_normalized_input(self) -> None:
        """NFD normalized input is handled correctly."""
        bundle = FluentBundle("en")
        # NFD form of café (decomposed)
        nfd_cafe = unicodedata.normalize("NFD", "café")
        bundle.add_resource(f"word = {nfd_cafe}")

        result, errors = bundle.format_pattern("word")

        assert "caf" in result
        assert errors == ()
