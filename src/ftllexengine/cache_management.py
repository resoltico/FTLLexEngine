"""Unified cache-clearing helpers for module-level caches.

This module backs the public ``ftllexengine.clear_module_caches()`` facade.
It validates component selectors before clearing caches so cache maintenance
fails explicitly on typos instead of silently leaving stale state behind.
"""

from __future__ import annotations

from typing import Literal

from .core.babel_compat import is_babel_available

type CacheComponentName = Literal[
    "parsing.currency",
    "parsing.dates",
    "locale",
    "runtime.locale_context",
    "introspection.message",
    "introspection.iso",
]

_KNOWN_CACHE_COMPONENTS: frozenset[CacheComponentName] = frozenset({
    "introspection.iso",
    "introspection.message",
    "locale",
    "parsing.currency",
    "parsing.dates",
    "runtime.locale_context",
})

__all__ = ["clear_module_caches"]


def _validate_cache_components(components: frozenset[str] | None) -> frozenset[str] | None:
    """Validate requested cache component selectors.

    Raises:
        ValueError: If any selector is unknown.
    """
    if components is None:
        return None

    unknown = sorted(set(components) - set(_KNOWN_CACHE_COMPONENTS))
    if not unknown:
        return components

    unknown_display = ", ".join(repr(name) for name in unknown)
    known_display = ", ".join(repr(name) for name in sorted(_KNOWN_CACHE_COMPONENTS))
    msg = (
        "Unknown cache component selector(s): "
        f"{unknown_display}. Known selectors: {known_display}"
    )
    raise ValueError(msg)


def clear_module_caches(
    components: frozenset[str] | None = None,
) -> None:
    """Clear module-level caches in the library.

    Provides unified cache management for long-running applications. With
    ``components=None`` (the default), clears all caches:

    - ``'parsing.currency'``: CLDR currency data caches
    - ``'parsing.dates'``: CLDR date/datetime pattern caches
    - ``'locale'``: Babel locale object cache (locale_utils)
    - ``'runtime.locale_context'``: LocaleContext instance cache
    - ``'introspection.message'``: Message introspection result cache
    - ``'introspection.iso'``: ISO territory/currency introspection cache

    Pass a ``frozenset`` of component names to clear only specific caches.
    This is useful when certain caches (for example Babel locale data) are
    expensive to repopulate and should not be cleared during routine trimming.

    Args:
        components: Set of component names to clear. When ``None``, clears all
            caches. Unknown names raise ValueError so selector typos fail fast.

    Useful for:
        - Memory reclamation in long-running server applications
        - Testing scenarios requiring fresh cache state
        - After Babel/CLDR data updates

    Thread-safe. Each underlying cache uses its own locking mechanism.

    Note:
        This function does NOT require Babel. It clears caches regardless
        of whether Babel-dependent modules have been imported. Caches that
        have not been populated yet are simply no-ops.

        FluentBundle instances maintain their own IntegrityCache which is NOT
        cleared by this function. To clear a bundle's format cache, call
        ``bundle.clear_cache()``.
    """
    validated = _validate_cache_components(components)
    babel_available = is_babel_available()

    clear_all = validated is None
    selected: frozenset[str] = frozenset() if validated is None else validated

    def _want(name: CacheComponentName) -> bool:
        return clear_all or name in selected

    if babel_available and _want("parsing.currency"):
        from .parsing.currency import (  # noqa: PLC0415 - imported only when Babel is available
            clear_currency_caches,
        )

        clear_currency_caches()

    if babel_available and _want("parsing.dates"):
        from .parsing.dates import (  # noqa: PLC0415 - imported only when Babel is available
            clear_date_caches,
        )

        clear_date_caches()

    if _want("locale"):
        from .core.locale_utils import (  # noqa: PLC0415 - imported only when cache clearing runs
            clear_locale_cache,
        )

        clear_locale_cache()

    if babel_available and _want("runtime.locale_context"):
        from .runtime.locale_context import (  # noqa: PLC0415 - imported only when Babel is available
            LocaleContext,
        )

        LocaleContext.clear_cache()

    if _want("introspection.message"):
        from .introspection import (  # noqa: PLC0415 - imported only when cache clearing runs
            clear_introspection_cache,
        )

        clear_introspection_cache()

    if _want("introspection.iso"):
        from .introspection import (  # noqa: PLC0415 - imported only when cache clearing runs
            clear_iso_cache,
        )

        clear_iso_cache()
