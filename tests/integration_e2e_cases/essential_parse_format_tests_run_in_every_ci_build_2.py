# mypy: ignore-errors
"""Split test cases from tests/test_integration_e2e.py."""

from tests.integration_e2e_cases import *  # noqa: F403 - shared split test support


class TestParseFormatIsolation:
    """Tests for Unicode bidi isolation in parse->format workflow."""

    def test_use_isolating_true_adds_marks(self) -> None:
        """use_isolating=True wraps placeables in bidi isolation marks."""
        ftl_source = "msg = Hello, { $name }!"

        bundle = FluentBundle("en-US", use_isolating=True)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("msg", {"name": "World"})

        # Should contain FSI (First Strong Isolate) and PDI (Pop Directional Isolate)
        assert "\u2068" in result
        assert "\u2069" in result

    def test_use_isolating_false_no_marks(self) -> None:
        """use_isolating=False does not add bidi isolation marks."""
        ftl_source = "msg = Hello, { $name }!"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("msg", {"name": "World"})

        # Should NOT contain isolation marks
        assert "\u2068" not in result
        assert "\u2069" not in result


class TestCommentPreservation:
    """Tests for comment handling in parse->format."""

    def test_comments_dont_affect_formatting(self) -> None:
        """Comments in FTL don't affect message formatting."""
        ftl_source = """
# This is a comment
## Group comment
### Resource comment
hello = Hello!
# Another comment
world = World!
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        hello, _ = bundle.format_pattern("hello")
        world, _ = bundle.format_pattern("world")

        assert hello == "Hello!"
        assert world == "World!"
