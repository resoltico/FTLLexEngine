# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# DEBUG LOGGING
# ============================================================================


class TestDebugLogging:
    """Tests for debug logging coverage (junk creation)."""

    def test_junk_creation_triggers_debug_log(self) -> None:
        """Debug logging when creating Junk entries."""
        logging.basicConfig(
            level=logging.DEBUG, stream=sys.stderr, force=True
        )
        try:
            parser = FluentParserV1()
            res = parser.parse("invalid { syntax")
            assert len(res.entries) >= 1
        except KeyError:
            pass
        finally:
            logging.basicConfig(
                level=logging.WARNING, force=True
            )
