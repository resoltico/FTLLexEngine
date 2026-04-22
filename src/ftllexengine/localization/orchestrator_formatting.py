"""Formatting and mutation helpers for FluentLocalization."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, NoReturn

from ftllexengine.constants import FALLBACK_INVALID, FALLBACK_MISSING_MESSAGE
from ftllexengine.core.locale_utils import require_locale_code
from ftllexengine.diagnostics.codes import Diagnostic, DiagnosticCode
from ftllexengine.diagnostics.errors import ErrorCategory, FrozenFluentError
from ftllexengine.integrity import FormattingIntegrityError, IntegrityContext
from ftllexengine.localization.loading import FallbackInfo

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from ftllexengine.core.semantic_types import FTLSource, LocaleCode, MessageId
    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.localization.orchestrator_protocols import LocalizationStateProtocol
    from ftllexengine.syntax import Junk


class _LocalizationFormattingMixin:
    """Formatting and mutation behavior for FluentLocalization."""

    def add_resource(
        self: LocalizationStateProtocol, locale: LocaleCode, ftl_source: FTLSource
    ) -> tuple[Junk, ...]:
        """Add FTL resource to a specific locale bundle."""
        normalized_locale = require_locale_code(locale, "locale")

        with self._lock.write():
            if normalized_locale not in self._locales:
                msg = f"Locale '{normalized_locale}' not in fallback chain {self._locales}"
                raise ValueError(msg)

            if normalized_locale not in self._bundles:
                self._create_bundle(normalized_locale)
            return self._bundles[normalized_locale].add_resource(ftl_source)

    def add_resource_stream(
        self: LocalizationStateProtocol,
        locale: LocaleCode,
        lines: Iterable[str],
        *,
        source_path: str | None = None,
    ) -> tuple[Junk, ...]:
        """Add FTL resource to a locale bundle from a line-oriented stream."""
        normalized_locale = require_locale_code(locale, "locale")

        with self._lock.write():
            if normalized_locale not in self._locales:
                msg = f"Locale '{normalized_locale}' not in fallback chain {self._locales}"
                raise ValueError(msg)

            if normalized_locale not in self._bundles:
                self._create_bundle(normalized_locale)
            return self._bundles[normalized_locale].add_resource_stream(
                lines, source_path=source_path
            )

    def _handle_message_not_found(
        self: LocalizationStateProtocol,
        message_id: MessageId,
        errors: list[FrozenFluentError],
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Handle missing-message fallbacks consistently."""
        match message_id:
            case str() if message_id:
                diagnostic = Diagnostic(
                    code=DiagnosticCode.MESSAGE_NOT_FOUND,
                    message=f"Message '{message_id}' not found in any locale",
                )
                error = FrozenFluentError(
                    str(diagnostic), ErrorCategory.REFERENCE, diagnostic=diagnostic
                )
                errors.append(error)
                fallback = FALLBACK_MISSING_MESSAGE.format(id=message_id)
            case _:
                diagnostic = Diagnostic(
                    code=DiagnosticCode.MESSAGE_NOT_FOUND,
                    message="Empty or invalid message ID",
                )
                error = FrozenFluentError(
                    str(diagnostic), ErrorCategory.REFERENCE, diagnostic=diagnostic
                )
                errors.append(error)
                fallback = FALLBACK_INVALID

        errors_tuple = tuple(errors)
        if self._strict:
            self._raise_strict_error(message_id, fallback, error)
        return (fallback, errors_tuple)

    def _raise_strict_error(
        self: LocalizationStateProtocol,
        message_id: MessageId,
        fallback_value: str,
        error: FrozenFluentError,
    ) -> NoReturn:
        """Raise FormattingIntegrityError for localization-level failures."""
        context = IntegrityContext(
            component="localization",
            operation="format_pattern",
            key=str(message_id),
            expected="<no errors>",
            actual="<1 error>",
            timestamp=time.monotonic(),
            wall_time_unix=time.time(),
        )
        msg = f"Strict mode: '{message_id}' failed: {error}"
        raise FormattingIntegrityError(
            msg,
            context=context,
            fluent_errors=(error,),
            fallback_value=fallback_value,
            message_id=str(message_id),
        )

    def format_value(
        self: LocalizationStateProtocol,
        message_id: MessageId,
        args: Mapping[str, FluentValue] | None = None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Format a value by delegating to ``format_pattern``."""
        return self.format_pattern(message_id, args)

    def has_message(self: LocalizationStateProtocol, message_id: MessageId) -> bool:
        """Return whether any locale in the chain contains ``message_id``."""
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            if bundle.has_message(message_id):
                return True
        return False

    def format_pattern(
        self: LocalizationStateProtocol,
        message_id: MessageId,
        args: Mapping[str, FluentValue] | None = None,
        *,
        attribute: str | None = None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Format a message with fallback-chain semantics."""
        errors: list[FrozenFluentError] = []

        if not self._check_mapping_arg(args, errors):
            if self._strict:
                self._raise_strict_error(message_id, FALLBACK_INVALID, errors[-1])
            return (FALLBACK_INVALID, tuple(errors))

        raw_attribute: object = attribute
        if raw_attribute is not None and not isinstance(raw_attribute, str):
            attr_type = type(raw_attribute).__name__
            diagnostic = Diagnostic(
                code=DiagnosticCode.INVALID_ARGUMENT,
                message=f"Invalid attribute type: expected str or None, got {attr_type}",
            )
            attr_error = FrozenFluentError(
                str(diagnostic), ErrorCategory.RESOLUTION, diagnostic=diagnostic
            )
            errors.append(attr_error)
            if self._strict:
                self._raise_strict_error(message_id, FALLBACK_INVALID, attr_error)
            return (FALLBACK_INVALID, tuple(errors))

        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            if not bundle.has_message(message_id):
                continue

            try:
                value, bundle_errors = bundle.format_pattern(message_id, args, attribute=attribute)
            except FormattingIntegrityError as exc:
                old_ctx = exc.context
                err_count = len(exc.fluent_errors)
                new_ctx = IntegrityContext(
                    component="localization",
                    operation=old_ctx.operation if old_ctx else "format_pattern",
                    key=old_ctx.key if old_ctx else str(message_id),
                    expected=old_ctx.expected if old_ctx else "<no errors>",
                    actual=old_ctx.actual if old_ctx else f"<{err_count} error(s)>",
                    timestamp=old_ctx.timestamp if old_ctx else time.monotonic(),
                    wall_time_unix=old_ctx.wall_time_unix if old_ctx else time.time(),
                )
                raise FormattingIntegrityError(
                    str(exc),
                    context=new_ctx,
                    fluent_errors=exc.fluent_errors,
                    fallback_value=exc.fallback_value,
                    message_id=exc.message_id,
                ) from exc

            errors.extend(bundle_errors)

            if self._on_fallback is not None and locale != self._primary_locale:
                self._on_fallback(
                    FallbackInfo(
                        requested_locale=self._primary_locale,
                        resolved_locale=locale,
                        message_id=message_id,
                    )
                )

            return (value, tuple(errors))

        return self._handle_message_not_found(message_id, errors)

    def add_function(
        self: LocalizationStateProtocol, name: str, func: Callable[..., FluentValue]
    ) -> None:
        """Register a custom function on current and future bundles."""
        with self._lock.write():
            self._pending_functions[name] = func
            for bundle in self._bundles.values():
                bundle.add_function(name, func)
