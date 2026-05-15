"""Formatting helpers for FluentBundle."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, NoReturn

from ftllexengine.constants import FALLBACK_INVALID, FALLBACK_MISSING_MESSAGE
from ftllexengine.core.identifier_validation import is_valid_identifier
from ftllexengine.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    ErrorTemplate,
    FrozenFluentError,
)
from ftllexengine.integrity import FormattingIntegrityError, IntegrityContext
from ftllexengine.runtime.resolution_context import ResolutionContext
from ftllexengine.runtime.resolver import FluentResolver

if TYPE_CHECKING:
    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.runtime.bundle_protocols import BundleStateProtocol

logger = logging.getLogger("ftllexengine.runtime.bundle")


class _BundleFormattingMixin:
    """Formatting behavior for FluentBundle."""

    @staticmethod
    def _validate_nested_mapping_keys(
        value: object,
        *,
        path: str,
        seen: set[int],
    ) -> str | None:
        """Reject non-string nested mapping keys before cache shaping sees them."""
        object_id = id(value)
        if object_id in seen:
            return None
        seen.add(object_id)
        try:
            if isinstance(value, Mapping):
                for nested_key, nested_value in value.items():
                    if not isinstance(nested_key, str):
                        return (
                            f"Invalid nested mapping key at {path}: expected str, got "
                            f"{type(nested_key).__name__}"
                        )
                    nested_error = _BundleFormattingMixin._validate_nested_mapping_keys(
                        nested_value,
                        path=f"{path}[{nested_key!r}]",
                        seen=seen,
                    )
                    if nested_error is not None:
                        return nested_error
                return None

            if isinstance(value, Sequence) and not isinstance(
                value, (str, bytes, bytearray)
            ):
                for index, item in enumerate(value):
                    nested_error = _BundleFormattingMixin._validate_nested_mapping_keys(
                        item,
                        path=f"{path}[{index}]",
                        seen=seen,
                    )
                    if nested_error is not None:
                        return nested_error
            return None
        finally:
            seen.discard(object_id)

    def _invalid_request_result(
        self: BundleStateProtocol,
        message_id: str,
        fallback_value: str,
        *,
        category: ErrorCategory,
        code: DiagnosticCode,
        message: str,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Build a one-error failure result for invalid formatting input."""
        diagnostic = Diagnostic(code=code, message=message)
        error = FrozenFluentError(str(diagnostic), category, diagnostic=diagnostic)
        if self._strict:
            self._raise_strict_error(message_id, fallback_value, (error,))
        return (fallback_value, (error,))

    def _validate_format_request(
        self: BundleStateProtocol,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]] | None:
        """Validate top-level format_pattern inputs."""
        if invalid_result := _BundleFormattingMixin._validate_message_id(self, message_id):
            return invalid_result
        if invalid_result := _BundleFormattingMixin._validate_args(self, message_id, args):
            return invalid_result
        return _BundleFormattingMixin._validate_attribute(self, message_id, attribute)

    def _validate_message_id(
        self: BundleStateProtocol,
        message_id: str,
    ) -> tuple[str, tuple[FrozenFluentError, ...]] | None:
        """Validate the message identifier before cache or resolver work."""
        if message_id and isinstance(message_id, str):
            return None
        logger.warning("Invalid message ID: empty or non-string")
        return self._invalid_request_result(
            "<empty>",
            FALLBACK_INVALID,
            category=ErrorCategory.REFERENCE,
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Invalid message ID: empty or non-string",
        )

    def _validate_args(
        self: BundleStateProtocol,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]] | None:
        """Validate formatting arguments before key shaping or resolution."""
        raw_args: object = args
        if raw_args is not None and not isinstance(raw_args, Mapping):
            arg_type = type(raw_args).__name__
            logger.warning("Invalid args type: expected Mapping or None, got %s", arg_type)
            return self._invalid_request_result(
                message_id,
                FALLBACK_INVALID,
                category=ErrorCategory.RESOLUTION,
                code=DiagnosticCode.INVALID_ARGUMENT,
                message=f"Invalid args type: expected Mapping or None, got {arg_type}",
            )

        if raw_args is None:
            return None

        for arg_key, arg_value in raw_args.items():
            invalid_result = _BundleFormattingMixin._validate_arg_key(self, message_id, arg_key)
            if invalid_result is not None:
                return invalid_result
            nested_mapping_error = _BundleFormattingMixin._validate_nested_mapping_keys(
                arg_value,
                path=f"args[{arg_key!r}]",
                seen=set(),
            )
            if nested_mapping_error is not None:
                logger.warning(nested_mapping_error)
                return self._invalid_request_result(
                    message_id,
                    FALLBACK_INVALID,
                    category=ErrorCategory.RESOLUTION,
                    code=DiagnosticCode.INVALID_ARGUMENT,
                    message=nested_mapping_error,
                )
        return None

    def _validate_arg_key(
        self: BundleStateProtocol,
        message_id: str,
        arg_key: object,
    ) -> tuple[str, tuple[FrozenFluentError, ...]] | None:
        """Validate one top-level formatting argument key."""
        if not isinstance(arg_key, str):
            key_type = type(arg_key).__name__
            logger.warning("Invalid args key type: expected str, got %s", key_type)
            return self._invalid_request_result(
                message_id,
                FALLBACK_INVALID,
                category=ErrorCategory.RESOLUTION,
                code=DiagnosticCode.INVALID_ARGUMENT,
                message=f"Invalid args key type: expected str, got {key_type}",
            )
        if is_valid_identifier(arg_key):
            return None
        logger.warning("Invalid args key name: %s", arg_key)
        return self._invalid_request_result(
            message_id,
            FALLBACK_INVALID,
            category=ErrorCategory.RESOLUTION,
            code=DiagnosticCode.INVALID_ARGUMENT,
            message=(
                f"Invalid args key name: {arg_key!r}. "
                "Keys must be valid Fluent identifiers."
            ),
        )

    def _validate_attribute(
        self: BundleStateProtocol,
        message_id: str,
        attribute: str | None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]] | None:
        """Validate the optional attribute selector."""
        raw_attribute: object = attribute
        if raw_attribute is None or isinstance(raw_attribute, str):
            return None
        attribute_type = type(raw_attribute).__name__
        logger.warning(
            "Invalid attribute type: expected str or None, got %s",
            attribute_type,
        )
        return self._invalid_request_result(
            message_id,
            FALLBACK_INVALID,
            category=ErrorCategory.RESOLUTION,
            code=DiagnosticCode.INVALID_ARGUMENT,
            message=f"Invalid attribute type: expected str or None, got {attribute_type}",
        )

    def _lookup_cached_pattern(
        self: BundleStateProtocol,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]] | None:
        """Return a cached formatting result when available."""
        if self._cache is None:
            return None

        cached_entry = self._cache.get(
            message_id,
            args,
            attribute,
            self._locale,
            use_isolating=self._use_isolating,
            function_generation=self._function_registry.cache_generation,
        )
        if cached_entry is None:
            return None

        result, errors_tuple = cached_entry.as_result()
        if errors_tuple and self._strict:
            self._raise_strict_error(message_id, result, errors_tuple)
        return (result, errors_tuple)

    def _raise_strict_error(
        self: BundleStateProtocol,
        message_id: str,
        fallback_value: str,
        errors: tuple[FrozenFluentError, ...],
    ) -> NoReturn:
        """Raise FormattingIntegrityError for strict formatting failures."""
        error_summary = "; ".join(str(error) for error in errors[:3])
        if len(errors) > 3:
            error_summary += f" (and {len(errors) - 3} more)"

        context = IntegrityContext(
            component="bundle",
            operation="format_pattern",
            key=message_id,
            expected="<no errors>",
            actual=f"<{len(errors)} error(s)>",
            timestamp=time.monotonic(),
            wall_time_unix=time.time(),
        )
        msg = (
            f"Strict mode: formatting '{message_id}' produced {len(errors)} error(s): "
            f"{error_summary}"
        )
        raise FormattingIntegrityError(
            msg,
            context=context,
            fluent_errors=errors,
            fallback_value=fallback_value,
            message_id=message_id,
        )

    def _create_resolver(self: BundleStateProtocol) -> FluentResolver:
        """Create a resolver bound to the current bundle state."""
        return FluentResolver(
            locale=self._locale,
            messages=self._messages,
            terms=self._terms,
            function_registry=self._function_registry,
            reentry_gate=self._resolution_gate,
            use_isolating=self._use_isolating,
            max_nesting_depth=self._max_nesting_depth,
            max_expansion_size=self._max_expansion_size,
        )

    def _format_pattern_impl(
        self: BundleStateProtocol,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Format a message without acquiring bundle locks."""
        invalid_result = self._validate_format_request(message_id, args, attribute)
        if invalid_result is not None:
            return invalid_result

        cached_result = self._lookup_cached_pattern(message_id, args, attribute)
        if cached_result is not None:
            return cached_result

        if message_id not in self._messages:
            (logger.warning if self._strict else logger.debug)(
                "Message '%s' not found",
                message_id,
            )
            diag = ErrorTemplate.message_not_found(message_id)
            error = FrozenFluentError(str(diag), ErrorCategory.REFERENCE, diagnostic=diag)
            fallback = FALLBACK_MISSING_MESSAGE.format(id=message_id)
            if self._strict:
                self._raise_strict_error(message_id, fallback, (error,))
            return (fallback, (error,))

        message = self._messages[message_id]
        resolver = self._resolver
        context = ResolutionContext(
            max_depth=self._max_nesting_depth,
            max_expression_depth=self._max_nesting_depth,
            max_expansion_size=self._max_expansion_size,
        )
        result, errors_tuple = resolver.resolve_message(
            message,
            args,
            attribute,
            context=context,
        )

        if errors_tuple:
            log_fn = logger.warning if self._strict else logger.debug
            log_fn(
                "Message resolution errors for '%s': %d error(s)",
                message_id,
                len(errors_tuple),
            )
            for error in errors_tuple:
                logger.debug("  - %s: %s", type(error).__name__, error)
        else:
            logger.debug("Resolved message '%s' successfully", message_id)

        if self._cache is not None:
            if context.cacheable_output:
                self._cache.put(
                    message_id,
                    args,
                    attribute,
                    self._locale,
                    use_isolating=self._use_isolating,
                    function_generation=self._function_registry.cache_generation,
                    formatted=result,
                    errors=errors_tuple,
                )
            else:
                self._cache.note_uncacheable_result(
                    message_id,
                    args,
                    attribute,
                    self._locale,
                    use_isolating=self._use_isolating,
                    function_generation=self._function_registry.cache_generation,
                )

        if errors_tuple and self._strict:
            self._raise_strict_error(message_id, result, errors_tuple)

        return (result, errors_tuple)
