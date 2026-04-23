"""Helpers for Babel-backed facade exports.

Centralizes facade wiring for symbols that genuinely require the Babel-enabled
runtime at import time. Zero-dependency symbols should be imported directly by
their facade modules instead of being routed through this helper.
"""

from __future__ import annotations

from typing import NoReturn

ROOT_BABEL_OPTIONAL_ATTRS: frozenset[str] = frozenset({
    "AsyncFluentBundle",
    "FluentBundle",
    "FluentLocalization",
    "LocalizationBootConfig",
    "LocalizationCacheStats",
})

LOCALIZATION_BABEL_OPTIONAL_ATTRS: frozenset[str] = frozenset({
    "FluentLocalization",
    "LocalizationBootConfig",
    "LocalizationCacheStats",
})

RUNTIME_BABEL_OPTIONAL_ATTRS: frozenset[str] = frozenset({
    "AsyncFluentBundle",
    "create_default_registry",
    "currency_format",
    "datetime_format",
    "FluentBundle",
    "get_shared_registry",
    "number_format",
    "select_plural_category",
})


def load_root_babel_optional_exports() -> dict[str, object]:
    """Return root-facade exports that require the Babel-enabled runtime."""
    from .localization.boot import (  # noqa: PLC0415 - intentionally deferred optional import
        LocalizationBootConfig,
    )
    from .localization.orchestrator import (  # noqa: PLC0415 - intentionally deferred optional import
        FluentLocalization,
        LocalizationCacheStats,
    )
    from .runtime.async_bundle import (  # noqa: PLC0415 - intentionally deferred optional import
        AsyncFluentBundle,
    )
    from .runtime.bundle import (  # noqa: PLC0415 - intentionally deferred optional import
        FluentBundle,
    )

    return {
        "AsyncFluentBundle": AsyncFluentBundle,
        "FluentBundle": FluentBundle,
        "FluentLocalization": FluentLocalization,
        "LocalizationBootConfig": LocalizationBootConfig,
        "LocalizationCacheStats": LocalizationCacheStats,
    }


def load_localization_babel_optional_exports() -> dict[str, object]:
    """Return localization-facade exports that require the Babel runtime."""
    from ftllexengine.localization.boot import (  # noqa: PLC0415 - intentionally deferred optional import
        LocalizationBootConfig,
    )
    from ftllexengine.localization.orchestrator import (  # noqa: PLC0415 - intentionally deferred optional import
        FluentLocalization,
        LocalizationCacheStats,
    )

    return {
        "FluentLocalization": FluentLocalization,
        "LocalizationBootConfig": LocalizationBootConfig,
        "LocalizationCacheStats": LocalizationCacheStats,
    }


def load_runtime_babel_optional_exports() -> dict[str, object]:
    """Return runtime-facade exports that require the Babel runtime."""
    from .runtime.async_bundle import (  # noqa: PLC0415 - intentionally deferred optional import
        AsyncFluentBundle,
    )
    from .runtime.bundle import (  # noqa: PLC0415 - intentionally deferred optional import
        FluentBundle,
    )
    from .runtime.functions import (  # noqa: PLC0415 - intentionally deferred optional import
        create_default_registry,
        currency_format,
        datetime_format,
        get_shared_registry,
        number_format,
    )
    from .runtime.plural_rules import (  # noqa: PLC0415 - intentionally deferred optional import
        select_plural_category,
    )

    return {
        "AsyncFluentBundle": AsyncFluentBundle,
        "create_default_registry": create_default_registry,
        "currency_format": currency_format,
        "datetime_format": datetime_format,
        "FluentBundle": FluentBundle,
        "get_shared_registry": get_shared_registry,
        "number_format": number_format,
        "select_plural_category": select_plural_category,
    }


def raise_missing_babel_symbol(
    *,
    module_name: str,
    name: str,
    optional_attrs: frozenset[str],
    parser_only_hint: str | None = None,
) -> NoReturn:
    """Raise a helpful AttributeError for a Babel-backed optional symbol.

    Module attribute access uses ``AttributeError`` so Python feature probes
    such as ``hasattr()`` and ``getattr(..., default)`` treat the symbol as
    absent in parser-only installs.
    """
    if name in optional_attrs:
        message = (
            f"{name} requires the full runtime install (Babel + CLDR locale data). "
            "Install with: pip install ftllexengine[babel]"
        )
        if parser_only_hint is not None:
            message = f"{message}\n\n{parser_only_hint}"
        raise AttributeError(message)

    message = f"module {module_name!r} has no attribute {name!r}"
    raise AttributeError(message)
