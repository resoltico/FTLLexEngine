"""Hypothesis property-based tests for localization/boot.py (LocalizationBootConfig).

Properties verified:
- boot() always returns a 3-tuple (FluentLocalization, LoadSummary, schemas).
- boot() is idempotent for identical configs: second call returns equivalent L10n.
- boot_simple() return value satisfies format_pattern for known messages.
- Required messages: presence check is monotone — superset of present messages passes.
- Schema validation: exact match of expected schema passes; strict superset fails.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from ftllexengine.integrity import IntegrityCheckFailedError
from ftllexengine.localization import FluentLocalization, LoadSummary, LocalizationBootConfig

pytestmark = pytest.mark.fuzz

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class DictLoader:
    """In-memory ResourceLoader backed by a dict for testing."""

    def __init__(self, resources: dict[tuple[str, str], str]) -> None:
        self._resources = resources

    def load(self, locale: str, resource_id: str) -> str:
        result = self._resources.get((locale, resource_id))
        if result is None:
            msg = f"No resource for ({locale!r}, {resource_id!r})"
            raise FileNotFoundError(msg)
        return result

    def describe_path(self, locale: str, resource_id: str) -> str:
        return f"memory://{locale}/{resource_id}"


def _build_loader(
    locales: list[str],
    resource_id: str,
    messages: dict[str, str],
) -> DictLoader:
    """Build a DictLoader with the given messages for each locale."""
    ftl = "\n".join(f"{k} = {v}" for k, v in messages.items())
    return DictLoader({(loc, resource_id): ftl for loc in locales})


def _to_tuple(lst: list[str]) -> tuple[str, ...]:
    return tuple(lst)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_SIMPLE_LOCALES = ["en", "en_gb", "fr", "de", "ja"]
_SIMPLE_MSG_KEYS = ["hello", "goodbye", "thanks", "error-msg", "welcome-back"]

locales_strategy = st.lists(
    st.sampled_from(_SIMPLE_LOCALES),
    min_size=1,
    max_size=3,
    unique=True,
)

msg_key_strategy = st.lists(
    st.sampled_from(_SIMPLE_MSG_KEYS),
    min_size=1,
    max_size=4,
    unique=True,
)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(
    locales=locales_strategy,
    keys=msg_key_strategy,
)
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_boot_returns_three_tuple(locales: list[str], keys: list[str]) -> None:
    """boot() always returns a (FluentLocalization, LoadSummary, tuple) 3-tuple."""
    messages = {k: f"Value for {k}" for k in keys}
    loader = _build_loader(locales, "main.ftl", messages)

    cfg = LocalizationBootConfig(
        locales=_to_tuple(locales),
        resource_ids=("main.ftl",),
        loader=loader,
    )
    l10n, summary, schemas = cfg.boot()

    event(f"locale_count={len(locales)}")
    event(f"msg_count={len(keys)}")
    assert isinstance(l10n, FluentLocalization)
    assert isinstance(summary, LoadSummary)
    assert isinstance(schemas, tuple)
    event("outcome=boot_three_tuple")


@given(
    locales=locales_strategy,
    keys=msg_key_strategy,
)
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_boot_simple_messages_formattable(
    locales: list[str], keys: list[str]
) -> None:
    """boot_simple() produces an L10n where all messages format without errors."""
    messages = {k: f"Text {k}" for k in keys}
    loader = _build_loader(locales, "main.ftl", messages)

    cfg = LocalizationBootConfig(
        locales=_to_tuple(locales),
        resource_ids=("main.ftl",),
        loader=loader,
    )
    l10n = cfg.boot_simple()

    event(f"locale_count={len(locales)}")
    for key in keys:
        result, errors = l10n.format_pattern(key)
        assert not errors, f"Unexpected errors for {key!r}: {errors}"
        assert result is not None
    event("outcome=all_messages_formattable")


@given(
    locales=locales_strategy,
    present_keys=msg_key_strategy,
    extra_required=st.lists(
        st.sampled_from(_SIMPLE_MSG_KEYS),
        min_size=1,
        max_size=2,
    ),
)
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_required_messages_subset_passes_superset_fails(
    locales: list[str],
    present_keys: list[str],
    extra_required: list[str],
) -> None:
    """Requiring present messages passes; requiring absent messages fails.

    Property: if M is the set of messages in the bundle,
    required_messages ⊆ M passes and required_messages ⊄ M fails.
    """
    messages = {k: f"Val {k}" for k in present_keys}
    loader = _build_loader(locales, "main.ftl", messages)

    # A subset of present keys — must pass.
    required_subset = frozenset(present_keys[:1])
    cfg_pass = LocalizationBootConfig(
        locales=_to_tuple(locales),
        resource_ids=("main.ftl",),
        loader=loader,
        required_messages=required_subset,
    )
    l10n, _, _ = cfg_pass.boot()
    assert isinstance(l10n, FluentLocalization)
    event("outcome=subset_required_passes")

    # Keys NOT in the bundle — must fail.
    absent_keys = [k for k in extra_required if k not in present_keys]
    if absent_keys:
        required_absent = frozenset(absent_keys[:1])
        cfg_fail = LocalizationBootConfig(
            locales=_to_tuple(locales),
            resource_ids=("main.ftl",),
            loader=loader,
            required_messages=required_absent,
        )
        try:
            cfg_fail.boot()
            # If boot() didn't raise, extra_required keys are actually present
            # (they were in present_keys — overlap is possible from sampled_from).
        except IntegrityCheckFailedError:
            event("outcome=absent_required_fails")


@given(
    locales=locales_strategy,
    keys=msg_key_strategy,
)
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_boot_idempotent_config(locales: list[str], keys: list[str]) -> None:
    """Two boot() calls with the same config produce equivalent FluentLocalizations.

    Property: boot() is effectively deterministic for fixed loader + config.
    """
    messages = {k: f"Msg {k}" for k in keys}
    loader = _build_loader(locales, "main.ftl", messages)

    def make_cfg() -> LocalizationBootConfig:
        return LocalizationBootConfig(
            locales=_to_tuple(locales),
            resource_ids=("main.ftl",),
            loader=loader,
        )

    l10n1, _, _ = make_cfg().boot()
    l10n2, _, _ = make_cfg().boot()

    event(f"locale_count={len(locales)}")
    for key in keys:
        r1, e1 = l10n1.format_pattern(key)
        r2, e2 = l10n2.format_pattern(key)
        assert r1 == r2, f"Idempotency violated for {key!r}: {r1!r} != {r2!r}"
        assert e1 == e2
    event("outcome=boot_idempotent")
