"""FluentBundle public type composed from focused runtime mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .bundle_formatting import _BundleFormattingMixin
from .bundle_lifecycle import _BundleLifecycleMixin
from .bundle_mutation import _BundleMutationMixin
from .bundle_queries import _BundleQueryMixin
from .bundle_registration import _BundleRegistrationMixin

__all__ = ["FluentBundle"]

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ftllexengine.core.semantic_types import LocaleCode
    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.diagnostics import FrozenFluentError
    from ftllexengine.syntax import Message, Term
    from ftllexengine.syntax.parser import FluentParserV1

    from .bundle_protocols import BundleStateProtocol
    from .cache import IntegrityCache
    from .cache_config import CacheConfig
    from .function_bridge import FunctionRegistry
    from .resolver import FluentResolver
    from .rwlock import RWLock


class FluentBundle(
    _BundleLifecycleMixin,
    _BundleQueryMixin,
    _BundleFormattingMixin,
    _BundleRegistrationMixin,
    _BundleMutationMixin,
):
    """Fluent message bundle for specific locale."""

    _cache: IntegrityCache | None
    _cache_config: CacheConfig | None
    _function_registry: FunctionRegistry
    _locale: LocaleCode
    _max_expansion_size: int
    _max_nesting_depth: int
    _max_source_size: int
    _messages: dict[str, Message]
    _msg_deps: dict[str, frozenset[str]]
    _owns_registry: bool
    _parser: FluentParserV1
    _resolver: FluentResolver
    _rwlock: RWLock
    _strict: bool
    _term_deps: dict[str, frozenset[str]]
    _terms: dict[str, Term]
    _use_isolating: bool

    __slots__ = (
        "_cache",
        "_cache_config",
        "_function_registry",
        "_locale",
        "_max_expansion_size",
        "_max_nesting_depth",
        "_max_source_size",
        "_messages",
        "_msg_deps",
        "_owns_registry",
        "_parser",
        "_resolver",
        "_rwlock",
        "_strict",
        "_term_deps",
        "_terms",
        "_use_isolating",
    )

    def format_pattern(
        self: BundleStateProtocol,
        message_id: str,
        /,
        args: Mapping[str, FluentValue] | None = None,
        *,
        attribute: str | None = None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Format one message or attribute to a string."""
        with self._rwlock.read():
            return self._format_pattern_impl(message_id, args, attribute)
