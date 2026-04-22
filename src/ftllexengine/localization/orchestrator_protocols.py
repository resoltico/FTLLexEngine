"""Type-checking protocols for FluentLocalization mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from ftllexengine.core.semantic_types import LocaleCode, MessageId
    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.diagnostics import FrozenFluentError
    from ftllexengine.introspection import MessageVariableValidationResult
    from ftllexengine.localization.loading import (
        FallbackInfo,
        LoadSummary,
        ResourceLoadResult,
    )
    from ftllexengine.runtime.bundle import FluentBundle
    from ftllexengine.runtime.cache_config import CacheConfig
    from ftllexengine.runtime.rwlock import RWLock
    from ftllexengine.syntax import Message


class LocalizationStateProtocol(Protocol):
    """Structural contract implemented by FluentLocalization for its mixins."""

    _bundles: dict[LocaleCode, FluentBundle]
    _cache_config: CacheConfig | None
    _load_results: list[ResourceLoadResult]
    _locales: tuple[LocaleCode, ...]
    _lock: RWLock
    _on_fallback: Callable[[FallbackInfo], None] | None
    _pending_functions: dict[str, Callable[..., FluentValue]]
    _primary_locale: LocaleCode
    _strict: bool
    _use_isolating: bool

    def _create_bundle(self, locale: LocaleCode) -> FluentBundle:
        ...  # pragma: no cover - typing-only protocol declaration

    def _get_or_create_bundle(self, locale: LocaleCode) -> FluentBundle:
        ...  # pragma: no cover - typing-only protocol declaration

    @staticmethod
    def _check_mapping_arg(
        args: Mapping[str, FluentValue] | None,
        errors: list[FrozenFluentError],
    ) -> bool:
        ...  # pragma: no cover - typing-only protocol declaration

    def get_message(self, message_id: MessageId) -> Message | None:
        ...  # pragma: no cover - typing-only protocol declaration

    def _handle_message_not_found(
        self,
        message_id: MessageId,
        errors: list[FrozenFluentError],
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        ...  # pragma: no cover - typing-only protocol declaration

    def format_pattern(
        self,
        message_id: MessageId,
        args: Mapping[str, FluentValue] | None = None,
        *,
        attribute: str | None = None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        ...  # pragma: no cover - typing-only protocol declaration

    def _raise_strict_error(
        self,
        message_id: MessageId,
        fallback_value: str,
        error: FrozenFluentError,
    ) -> NoReturn:
        ...  # pragma: no cover - typing-only protocol declaration

    def get_load_summary(self) -> LoadSummary:
        ...  # pragma: no cover - typing-only protocol declaration

    @staticmethod
    def _describe_unclean_load_result(result: ResourceLoadResult) -> tuple[str, str]:
        ...  # pragma: no cover - typing-only protocol declaration

    def _raise_integrity_check_failed(
        self,
        operation: str,
        message: str,
        *,
        key: str | None = None,
        expected: str | None = None,
        actual: str | None = None,
    ) -> NoReturn:
        ...  # pragma: no cover - typing-only protocol declaration

    @staticmethod
    def _format_schema_difference(
        validation: MessageVariableValidationResult,
    ) -> str:
        ...  # pragma: no cover - typing-only protocol declaration

    def _resolve_message_schema_validation(
        self,
        message_id: MessageId,
        expected_variables: frozenset[str] | set[str],
    ) -> MessageVariableValidationResult | None:
        ...  # pragma: no cover - typing-only protocol declaration
