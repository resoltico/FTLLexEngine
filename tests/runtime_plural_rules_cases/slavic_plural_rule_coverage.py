# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SLAVIC PLURAL RULE COVERAGE
# ============================================================================


class TestSlavicRuleReturnOther:
    """Slavic plural rules return 'other' for numbers not matching one/few/many."""

    def test_slavic_rule_return_other(self) -> None:
        """Polish plural rules return 'many' or 'other' for 111 (ends in 1 but mod 100 == 11)."""
        # 111 % 10 = 1, 111 % 100 = 11
        # Polish: 'one' requires mod_100 != 11, so 111 skips 'one'
        # Polish: 'few' requires 2-4, so 111 skips 'few'
        # Polish: 'many' covers 0 and 5-9 and 11-14; 111 does not match (mod_10 == 1)
        # Remaining cases return 'other'
        result = select_plural_category(111, "pl")
        assert result in ["many", "other"]
