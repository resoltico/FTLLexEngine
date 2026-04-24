"""Lifecycle and configuration helpers for FluentBundle."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from ftllexengine.constants import (
    DEFAULT_MAX_EXPANSION_SIZE,
    MAX_DEPTH,
    MAX_SOURCE_SIZE,
)
from ftllexengine.core.depth_guard import depth_clamp
from ftllexengine.core.locale_utils import get_system_locale, require_locale_code
from ftllexengine.syntax.parser import FluentParserV1

from .cache import IntegrityCache
from .function_bridge import FunctionRegistry
from .functions import get_shared_registry
from .locale_context import LocaleContext
from .rwlock import RWLock

if TYPE_CHECKING:
    from ftllexengine.core.semantic_types import LocaleCode
    from ftllexengine.syntax import Message, Term

    from .bundle import FluentBundle
    from .bundle_protocols import BundleStateProtocol
    from .cache_config import CacheConfig

logger = logging.getLogger("ftllexengine.runtime.bundle")


class _BundleLifecycleMixin:
    """Construction, configuration, and identity behavior for FluentBundle."""

    def __init__(
        self: BundleStateProtocol,
        locale: str,
        /,
        *,
        use_isolating: bool = True,
        cache: CacheConfig | None = None,
        functions: FunctionRegistry | None = None,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
        max_expansion_size: int | None = None,
        strict: bool = True,
    ) -> None:
        """Initialize bundle state for one locale."""
        canonical_locale = require_locale_code(locale, "locale")
        locale_context = LocaleContext.create_or_raise(canonical_locale)
        self._locale = locale_context.locale_code
        self._use_isolating = use_isolating
        self._strict = strict
        self._messages: dict[str, Message] = {}
        self._terms: dict[str, Term] = {}
        self._msg_deps: dict[str, frozenset[str]] = {}
        self._term_deps: dict[str, frozenset[str]] = {}

        self._max_source_size = max_source_size if max_source_size is not None else MAX_SOURCE_SIZE
        requested_depth = max_nesting_depth if max_nesting_depth is not None else MAX_DEPTH
        self._max_nesting_depth = depth_clamp(requested_depth)
        self._max_expansion_size = (
            max_expansion_size if max_expansion_size is not None else DEFAULT_MAX_EXPANSION_SIZE
        )
        self._parser = FluentParserV1(
            max_source_size=self._max_source_size,
            max_nesting_depth=self._max_nesting_depth,
        )
        self._rwlock = RWLock()

        provided_functions: object = functions
        if provided_functions is not None:
            if not isinstance(provided_functions, FunctionRegistry):
                msg = (
                    f"functions must be FunctionRegistry, not {type(provided_functions).__name__}. "
                    "Use create_default_registry() or FunctionRegistry() to create one."
                )
                raise TypeError(msg)
            self._function_registry = provided_functions.copy()
            self._owns_registry = True
        else:
            self._function_registry = get_shared_registry()
            self._owns_registry = False

        self._cache_config = cache
        self._cache: IntegrityCache | None = None
        if cache is not None:
            self._cache = IntegrityCache(
                maxsize=cache.size,
                max_entry_weight=cache.max_entry_weight,
                max_errors_per_entry=cache.max_errors_per_entry,
                write_once=cache.write_once,
                strict=cache.integrity_strict and strict,
                enable_audit=cache.enable_audit,
                max_audit_entries=cache.max_audit_entries,
            )

        self._resolver = self._create_resolver()
        logger.info(
            "FluentBundle initialized for locale: %s (use_isolating=%s, cache=%s, strict=%s)",
            self._locale,
            use_isolating,
            "enabled" if cache is not None else "disabled",
            strict,
        )

    @property
    def locale(self: BundleStateProtocol) -> LocaleCode:
        """Get the canonical locale code for this bundle."""
        return self._locale

    @property
    def use_isolating(self: BundleStateProtocol) -> bool:
        """Get whether Unicode bidi isolation is enabled."""
        return self._use_isolating

    @property
    def strict(self: BundleStateProtocol) -> bool:
        """Get whether strict mode is enabled."""
        return self._strict

    @property
    def cache_enabled(self: BundleStateProtocol) -> bool:
        """Get whether format caching is enabled."""
        return self._cache is not None

    @property
    def cache_config(self: BundleStateProtocol) -> CacheConfig | None:
        """Get cache configuration."""
        return self._cache_config

    @property
    def cache_usage(self: BundleStateProtocol) -> int:
        """Get current number of cached format results."""
        if self._cache is None:
            return 0
        return self._cache.size

    @property
    def max_source_size(self: BundleStateProtocol) -> int:
        """Maximum FTL source size in characters."""
        return self._max_source_size

    @property
    def max_nesting_depth(self: BundleStateProtocol) -> int:
        """Maximum placeable nesting depth."""
        return self._max_nesting_depth

    @property
    def max_expansion_size(self: BundleStateProtocol) -> int:
        """Maximum total characters produced during resolution."""
        return self._max_expansion_size

    @property
    def function_registry(self: BundleStateProtocol) -> FunctionRegistry:
        """Get the function registry for this bundle."""
        return self._function_registry

    @classmethod
    def for_system_locale(
        cls,
        *,
        use_isolating: bool = True,
        cache: CacheConfig | None = None,
        functions: FunctionRegistry | None = None,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
        max_expansion_size: int | None = None,
        strict: bool = True,
    ) -> FluentBundle:
        """Factory method to create a FluentBundle using the system locale."""
        system_locale = get_system_locale(raise_on_failure=True)
        return cast(
            "FluentBundle",
            cls(
                system_locale,
                use_isolating=use_isolating,
                cache=cache,
                functions=functions,
                max_source_size=max_source_size,
                max_nesting_depth=max_nesting_depth,
                max_expansion_size=max_expansion_size,
                strict=strict,
            ),
        )

    def __repr__(self: BundleStateProtocol) -> str:
        """Return string representation for debugging."""
        with self._rwlock.read():
            return (
                f"FluentBundle(locale={self._locale!r}, "
                f"messages={len(self._messages)}, "
                f"terms={len(self._terms)})"
            )

    def get_babel_locale(self: BundleStateProtocol) -> str:
        """Get the Babel locale identifier for this bundle."""
        ctx = LocaleContext.create_or_raise(self._locale)
        return str(ctx.babel_locale)
