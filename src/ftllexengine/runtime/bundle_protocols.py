"""Type-checking protocols for FluentBundle mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ftllexengine.core.semantic_types import LocaleCode
    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
    from ftllexengine.diagnostics.codes import DiagnosticCode
    from ftllexengine.runtime.bundle_registration import _PendingRegistration
    from ftllexengine.runtime.cache import IntegrityCache
    from ftllexengine.runtime.cache_config import CacheConfig
    from ftllexengine.runtime.function_bridge import FunctionRegistry
    from ftllexengine.runtime.resolver import FluentResolver
    from ftllexengine.runtime.rwlock import RWLock
    from ftllexengine.syntax import Junk, Message, Resource, Term
    from ftllexengine.syntax.parser import FluentParserV1


class BundleStateProtocol(Protocol):
    """Structural contract implemented by FluentBundle for its mixins."""

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

    def _collect_pending_entries(self, resource: Resource) -> _PendingRegistration:
        ...  # pragma: no cover - typing-only protocol declaration

    def _register_resource(
        self, resource: Resource, source_path: str | None
    ) -> tuple[Junk, ...]:
        ...  # pragma: no cover - typing-only protocol declaration

    def _create_resolver(self) -> FluentResolver:
        ...  # pragma: no cover - typing-only protocol declaration

    def _raise_strict_error(
        self,
        message_id: str,
        fallback_value: str,
        errors: tuple[FrozenFluentError, ...],
    ) -> NoReturn:
        ...  # pragma: no cover - typing-only protocol declaration

    def _invalid_request_result(
        self,
        message_id: str,
        fallback_value: str,
        *,
        category: ErrorCategory,
        code: DiagnosticCode,
        message: str,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        ...  # pragma: no cover - typing-only protocol declaration

    def _validate_format_request(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]] | None:
        ...  # pragma: no cover - typing-only protocol declaration

    def _lookup_cached_pattern(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]] | None:
        ...  # pragma: no cover - typing-only protocol declaration

    def _format_pattern_impl(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        ...  # pragma: no cover - typing-only protocol declaration
