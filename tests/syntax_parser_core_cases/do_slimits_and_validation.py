# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_core.py."""

from tests.syntax_parser_core_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TestDoSLimitsAndValidation
# ============================================================================


class TestDoSLimitsAndValidation:
    """DoS protection: nesting depth, source size, parameter validation.

    Verifies nesting depth clamping, source size limits, and
    constructor parameter validation.
    """

    # -- Nesting depth exceeded --------------------------------------------

    def test_depth_exceeded_specific_annotation(self) -> None:
        """Nesting depth exceeded produces specific diagnostic."""
        parser = FluentParserV1(max_nesting_depth=1)
        source = "msg = { { $var } }\n"
        result = parser.parse(source)
        assert len(result.entries) == 1
        junk_entry = result.entries[0]
        assert isinstance(junk_entry, Junk)
        assert len(junk_entry.annotations) == 1
        annotation = junk_entry.annotations[0]
        assert (
            annotation.code
            == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
        )
        assert "Nesting depth limit exceeded" in annotation.message
        assert "max: 1" in annotation.message

    # -- Recursion limit clamping ------------------------------------------

    def test_clamps_excessive_nesting_depth(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Excessive max_nesting_depth is clamped to safe limit."""
        recursion_limit = sys.getrecursionlimit()
        max_safe_depth = recursion_limit - 50
        excessive_depth = recursion_limit + 100
        with caplog.at_level(
            logging.WARNING,
            logger="ftllexengine.syntax.parser.core",
        ):
            parser = FluentParserV1(max_nesting_depth=excessive_depth)
        assert parser.max_nesting_depth == max_safe_depth
        assert parser.max_nesting_depth < excessive_depth
        assert len(caplog.records) == 1
        warning = caplog.records[0]
        assert warning.levelname == "WARNING"
        assert "max_nesting_depth" in warning.message
        assert "exceeds Python recursion limit" in warning.message
        assert "Clamping to" in warning.message

    def test_accepts_depth_within_recursion_limit(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """No warning when nesting depth is within safe limit."""
        with caplog.at_level(
            logging.WARNING,
            logger="ftllexengine.syntax.parser.core",
        ):
            parser = FluentParserV1(max_nesting_depth=50)
        assert parser.max_nesting_depth == 50
        assert len(caplog.records) == 0

    # -- Source size validation --------------------------------------------

    def test_max_source_size_default(self) -> None:
        """Default max_source_size equals MAX_SOURCE_SIZE constant."""
        parser = FluentParserV1()
        assert parser.max_source_size == MAX_SOURCE_SIZE

    def test_max_source_size_custom(self) -> None:
        """Custom max_source_size is stored."""
        parser = FluentParserV1(max_source_size=5000)
        assert parser.max_source_size == 5000

    def test_max_source_size_disabled(self) -> None:
        """max_source_size=0 disables the limit."""
        parser = FluentParserV1(max_source_size=0)
        assert parser.max_source_size == 0

    def test_oversized_source_raises_value_error(self) -> None:
        """parse() raises ValueError when source exceeds limit."""
        parser = FluentParserV1(max_source_size=100)
        oversized = "a" * 101
        with pytest.raises(
            ValueError,
            match=(
                r"Source length \(101 characters\) "
                r"exceeds maximum \(100 characters\)"
            ),
        ):
            parser.parse(oversized)

    def test_oversized_error_includes_config_hint(self) -> None:
        """ValueError includes configuration hint."""
        parser = FluentParserV1(max_source_size=50)
        with pytest.raises(
            ValueError,
            match="Configure max_source_size in FluentParserV1",
        ):
            parser.parse("x" * 51)

    def test_source_at_exact_limit(self) -> None:
        """parse() allows source exactly at size limit."""
        parser = FluentParserV1(max_source_size=100)
        result = parser.parse(("msg = value\n" * 8)[:100])
        assert result is not None

    def test_disabled_limit_accepts_large_source(self) -> None:
        """max_source_size=0 accepts arbitrarily large source."""
        parser = FluentParserV1(max_source_size=0)
        result = parser.parse("msg = " + ("x" * 100000))
        assert result is not None

    def test_none_limit_accepts_large_source(self) -> None:
        """max_source_size=None accepts arbitrarily large source."""
        parser = FluentParserV1(max_source_size=None)
        result = parser.parse("msg = " + ("y" * 100000))
        assert result is not None

    # -- Parameter validation ----------------------------------------------

    def test_rejects_zero_nesting_depth(self) -> None:
        """max_nesting_depth=0 raises ValueError."""
        with pytest.raises(
            ValueError,
            match=r"max_nesting_depth must be positive \(got 0\)",
        ):
            FluentParserV1(max_nesting_depth=0)

    def test_rejects_negative_nesting_depth(self) -> None:
        """max_nesting_depth=-1 raises ValueError."""
        with pytest.raises(
            ValueError,
            match=r"max_nesting_depth must be positive \(got -1\)",
        ):
            FluentParserV1(max_nesting_depth=-1)

    def test_accepts_positive_nesting_depth(self) -> None:
        """Positive max_nesting_depth is accepted."""
        parser = FluentParserV1(max_nesting_depth=50)
        assert parser.max_nesting_depth == 50

    def test_accepts_none_nesting_depth(self) -> None:
        """None max_nesting_depth uses default."""
        parser = FluentParserV1(max_nesting_depth=None)
        assert parser.max_nesting_depth > 0
