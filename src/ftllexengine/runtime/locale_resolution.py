"""Locale resolution helpers shared by ``LocaleContext`` creation paths."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, Literal

from ftllexengine.constants import MAX_LOCALE_CODE_LENGTH
from ftllexengine.core.babel_compat import (
    get_babel_global_func,
    get_locale_identifiers_func,
    require_babel,
)
from ftllexengine.core.locale_utils import normalize_locale

if TYPE_CHECKING:
    from babel import Locale

UNKNOWN_LOCALE_WARNING_LIMIT = 8

logger = logging.getLogger("ftllexengine.runtime.locale_context")


@dataclass(slots=True)
class _LocaleResolutionState:
    known_locales: frozenset[str] | None = None
    known_languages: frozenset[str] | None = None
    fallback_babel_locale: Locale | None = None
    fallback_warning_count: int = 0
    fallback_warning_suppressed: bool = False


_state_lock = Lock()
_state = _LocaleResolutionState()


def reset_locale_resolution_state() -> None:
    """Reset cached locale metadata and fallback-warning state."""
    with _state_lock:
        _state.known_locales = None
        _state.known_languages = None
        _state.fallback_babel_locale = None
        _state.fallback_warning_count = 0
        _state.fallback_warning_suppressed = False


def is_definitely_unknown_locale(normalized_locale: str) -> bool:
    """Return True when Babel locale parsing cannot possibly succeed."""
    known_locales, known_languages = _get_locale_metadata()
    if normalized_locale in known_locales:
        return False

    primary_language = normalized_locale.split("_", 1)[0]
    return primary_language not in known_languages


def get_fallback_babel_locale(locale_class: type[Locale]) -> Locale:
    """Return the shared Babel fallback locale."""
    with _state_lock:
        if _state.fallback_babel_locale is None:
            _state.fallback_babel_locale = locale_class.parse("en_US")
        return _state.fallback_babel_locale


def log_fallback_warning(
    *,
    normalized_locale: str,
    exceeds_typical_length: bool,
    detail: str,
    kind: Literal["invalid", "unknown"],
) -> None:
    """Emit a bounded warning for fallback locale handling."""
    emit_detail, emit_suppression = _reserve_fallback_warning_slot()
    if emit_detail:
        label = "Unknown locale" if kind == "unknown" else "Invalid locale format"
        if exceeds_typical_length:
            logger.warning(
                "%s '%s' (exceeds %d chars): %s. Falling back to en_US",
                label,
                normalized_locale,
                MAX_LOCALE_CODE_LENGTH,
                detail,
            )
        else:
            logger.warning(
                "%s '%s': %s. Falling back to en_US",
                label,
                normalized_locale,
                detail,
            )
        return

    if emit_suppression:
        logger.warning(
            "Additional locale fallback warnings suppressed after %d events; "
            "most recent locale was '%s'.",
            UNKNOWN_LOCALE_WARNING_LIMIT,
            normalized_locale,
        )


def _get_locale_metadata() -> tuple[frozenset[str], frozenset[str]]:
    """Load normalized locale and language metadata used by ``LocaleContext``."""
    with _state_lock:
        if _state.known_locales is not None and _state.known_languages is not None:
            return _state.known_locales, _state.known_languages

    require_babel("LocaleContext locale metadata")
    locale_identifiers_fn = get_locale_identifiers_func()
    get_global = get_babel_global_func()

    known_locales = frozenset(
        normalize_locale(locale_id) for locale_id in locale_identifiers_fn()
    )
    known_languages = {
        locale_id.split("_", 1)[0] for locale_id in known_locales
    }
    known_languages.update(
        normalize_locale(alias)
        for alias in get_global("language_aliases")
    )

    with _state_lock:
        _state.known_locales = known_locales
        _state.known_languages = frozenset(known_languages)
        return _state.known_locales, _state.known_languages


def _reserve_fallback_warning_slot() -> tuple[bool, bool]:
    """Return whether to emit a detailed or suppression warning."""
    with _state_lock:
        if _state.fallback_warning_count < UNKNOWN_LOCALE_WARNING_LIMIT:
            _state.fallback_warning_count += 1
            return True, False

        if not _state.fallback_warning_suppressed:
            _state.fallback_warning_suppressed = True
            return False, True

    return False, False
