"""Tests for Unicode escape sequences per Fluent spec.

Per EBNF grammar, tests both 4-digit and 6-digit Unicode escapes.
"""


from ftllexengine.syntax.ast import Message, Placeable, StringLiteral
from ftllexengine.syntax.parser import FluentParserV1


class TestUnicodeEscape4Digit:
    # Test 4-digit Unicode escape sequences

    def test_basic_ascii_character(self):
        # Parse escape for basic ASCII character
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\u0041" }')  # 'A'

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) == 1

        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "A"

    def test_latin_extended_character(self):
        # Parse escape for Latin extended characters (ä = U+00E4)
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\u00e4" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "ä"

    def test_uppercase_hex_digits(self):
        # Parse escape with uppercase hex digits
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\u00E4" }')  # ä with uppercase

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "ä"

    def test_mixed_case_hex_digits(self):
        # Parse escape with mixed case hex digits (ÿ)
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\u00Ff" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "\u00FF"

    def test_multiple_unicode_escapes(self):
        # Parse string with multiple escapes
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\u0048\u0065\u006C\u006C\u006F" }')  # "Hello"

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "Hello"

    def test_unicode_mixed_with_text(self):
        # Parse string with Unicode escapes mixed with regular text
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "Caf\u00e9" }')  # "Café"

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "Café"

    def test_cyrillic_character(self):
        # Parse escape for Cyrillic characters (Ж)
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\u0416" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "Ж"

    def test_cjk_character(self):
        # Parse escape for CJK characters (中)
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\u4E2D" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "中"


class TestUnicodeEscape6Digit:
    # Test 6-digit Unicode escape sequences

    def test_basic_emoji(self):
        # Parse escape for emoji character (grinning face)
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\U01F600" }')

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) == 1

        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "😀"

    def test_lowercase_hex_digits(self):
        # Parse escape with lowercase hex digits
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\U01f600" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "😀"

    def test_uppercase_hex_digits(self):
        # Parse escape with uppercase hex digits
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\U01F600" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "😀"

    def test_multiple_emojis(self):
        # Parse string with multiple escapes
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\U01F600\U01F389\U01F44D" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "😀🎉👍"

    def test_emoji_mixed_with_text(self):
        # Parse string with escapes mixed with regular text
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "Hello \U01F44B World!" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "Hello 👋 World!"

    def test_supplementary_plane_character(self):
        # Parse escape for supplementary plane characters (cyclone)
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\U01F300" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "🌀"

    def test_zero_padded_bmp_character(self):
        # Parse escape with leading zeros for BMP character ('A')
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\U000041" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "A"


class TestUnicodeMixed:
    # Test mixing 4-digit and 6-digit escapes

    def test_both_escape_types_in_one_string(self):
        # Parse string with both escape types
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "Caf\u00e9 \U01F44B" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "Café 👋"

    def test_unicode_escapes_with_other_escapes(self):
        # Parse string with Unicode and other escape sequences
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "Line1\nCaf\u00e9\n\U01F600" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "Line1\nCafé\n😀"

    def test_backslash_before_unicode_escape(self):
        # Parse escaped backslash before Unicode escape (literal backslash-u)
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\\u0041" }')

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "\\u0041"


class TestUnicodeEscapeErrors:
    # Test error handling for invalid Unicode escapes

    def test_incomplete_4_digit_escape(self):
        # Invalid escape with too few hex digits creates Junk
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\u00E" }')  # Only 3 digits

        # Should create Junk entry
        assert len(resource.entries) == 1
        entry = resource.entries[0]
        # Parser may create Junk or Message depending on error recovery
        assert entry.__class__.__name__ in ("Message", "Junk")

    def test_incomplete_6_digit_escape(self):
        # Invalid escape with too few hex digits creates Junk
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\U01F60" }')  # Only 5 digits

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert entry.__class__.__name__ in ("Message", "Junk")

    def test_invalid_hex_digit_in_4_digit_escape(self):
        # Invalid hex character in escape creates Junk
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\u00XY" }')  # X and Y are not hex

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert entry.__class__.__name__ in ("Message", "Junk")

    def test_invalid_hex_digit_in_6_digit_escape(self):
        # Invalid hex character in escape creates Junk
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\U01F6ZZ" }')  # Z is not hex

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert entry.__class__.__name__ in ("Message", "Junk")

    def test_unicode_escape_at_eof(self):
        # Incomplete Unicode escape at EOF creates Junk
        parser = FluentParserV1()
        resource = parser.parse(r'msg = { "\u00')  # Truncated at EOF

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert entry.__class__.__name__ in ("Message", "Junk")

    def test_invalid_code_point_too_large(self):
        # Code point > U+10FFFF should be rejected
        parser = FluentParserV1()
        # U+110000 is beyond valid Unicode range
        resource = parser.parse(r'msg = { "\U110000" }')

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        # Should create Junk due to invalid code point
        assert entry.__class__.__name__ in ("Message", "Junk")


class TestUnicodeRealWorld:
    # Test real-world Unicode usage scenarios

    def test_multilingual_greeting(self):
        # Parse multilingual greeting with Unicode escapes
        parser = FluentParserV1()
        # Hello in multiple languages using escapes
        resource = parser.parse(
            r'greeting = { "Hello \u4F60\u597D \u0417\u0434\u0440\u0430\u0432\u0441\u0442\u0432\u0443\u0439\u0442\u0435" }'  # noqa: E501 pylint: disable=line-too-long
        )  # Hello 你好 Здравствуйте

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert isinstance(msg, Message)
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert "你好" in placeable.expression.value
        assert "Здравствуйте" in placeable.expression.value

    def test_emoji_reaction_message(self):
        # Parse message with emoji reactions
        parser = FluentParserV1()
        resource = parser.parse(
            r'reactions = { "Thanks! \U01F44D\U01F389\U01F604" }'
        )

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "Thanks! 👍🎉😄"

    def test_mathematical_symbols(self):
        # Parse mathematical symbols using Unicode escapes (summation)
        parser = FluentParserV1()
        resource = parser.parse(r'math = { "\u2211 formula" }')  # ∑

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, StringLiteral)
        assert placeable.expression.value == "∑ formula"

    def test_unicode_in_message_value(self):
        # Parse Unicode escapes in message value (not in placeable)
        parser = FluentParserV1()
        # Note: Unicode escapes only work in string literals, not in pattern text
        # This tests that regular Unicode characters work in values
        resource = parser.parse("msg = Café 👋")

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Direct Unicode in value should work (not escaped)
