"""Loading and validation helpers for FluentLocalization."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, NoReturn

from ftllexengine.diagnostics.codes import Diagnostic, DiagnosticCode
from ftllexengine.diagnostics.errors import ErrorCategory, FrozenFluentError
from ftllexengine.enums import LoadStatus
from ftllexengine.integrity import IntegrityCheckFailedError, IntegrityContext
from ftllexengine.introspection import MessageVariableValidationResult
from ftllexengine.introspection import (
    validate_message_variables as validate_message_ast_variables,
)
from ftllexengine.localization.loading import LoadSummary, ResourceLoader, ResourceLoadResult
from ftllexengine.runtime.bundle import FluentBundle

if TYPE_CHECKING:
    from ftllexengine.core.semantic_types import LocaleCode, MessageId, ResourceId
    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.localization.orchestrator_protocols import LocalizationStateProtocol


class _LocalizationLoadingMixin:
    """Lifecycle and schema-validation behavior for FluentLocalization."""

    def _create_bundle(
        self: LocalizationStateProtocol, locale: LocaleCode
    ) -> FluentBundle:
        """Create and register a bundle for ``locale``."""
        bundle = FluentBundle(
            locale,
            use_isolating=self._use_isolating,
            cache=self._cache_config,
            strict=self._strict,
        )
        for name, func in self._pending_functions.items():
            bundle.add_function(name, func)
        self._bundles[locale] = bundle
        return bundle

    def _get_or_create_bundle(
        self: LocalizationStateProtocol, locale: LocaleCode
    ) -> FluentBundle:
        """Get an existing bundle or create it lazily."""
        with self._lock.read():
            if locale in self._bundles:
                return self._bundles[locale]

        with self._lock.write():
            if locale in self._bundles:  # pragma: no cover
                return self._bundles[locale]
            return self._create_bundle(locale)

    def _load_single_resource(
        self: LocalizationStateProtocol,
        locale: LocaleCode,
        resource_id: ResourceId,
        resource_loader: ResourceLoader,
    ) -> ResourceLoadResult:
        """Load one resource for one locale and capture the outcome."""
        source_path = resource_loader.describe_path(locale, resource_id)

        try:
            ftl_source = resource_loader.load(locale, resource_id)
            bundle = self._get_or_create_bundle(locale)
            junk_entries = bundle.add_resource(ftl_source, source_path=source_path)
            return ResourceLoadResult(
                locale=locale,
                resource_id=resource_id,
                status=LoadStatus.SUCCESS,
                source_path=source_path,
                junk_entries=junk_entries,
            )
        except FileNotFoundError:
            return ResourceLoadResult(
                locale=locale,
                resource_id=resource_id,
                status=LoadStatus.NOT_FOUND,
                source_path=source_path,
            )
        except (OSError, ValueError) as error:
            return ResourceLoadResult(
                locale=locale,
                resource_id=resource_id,
                status=LoadStatus.ERROR,
                error=error,
                source_path=source_path,
            )

    @staticmethod
    def _check_mapping_arg(
        args: Mapping[str, FluentValue] | None,
        errors: list[FrozenFluentError],
    ) -> bool:
        """Validate that ``args`` is ``None`` or a mapping."""
        raw_args: object = args
        if raw_args is not None and not isinstance(raw_args, Mapping):
            diagnostic = Diagnostic(
                code=DiagnosticCode.INVALID_ARGUMENT,
                message=(
                    f"Invalid args type: expected Mapping or None, got "
                    f"{type(raw_args).__name__}"
                ),
            )
            errors.append(
                FrozenFluentError(
                    str(diagnostic), ErrorCategory.RESOLUTION, diagnostic=diagnostic
                )
            )
            return False
        return True

    def get_load_summary(self: LocalizationStateProtocol) -> LoadSummary:
        """Return the immutable initialization load summary."""
        return LoadSummary(results=tuple(self._load_results))

    @staticmethod
    def _describe_unclean_load_result(
        result: ResourceLoadResult,
    ) -> tuple[str, str]:
        """Describe the first non-clean initialization result."""
        key = result.source_path or f"{result.locale}/{result.resource_id}"
        if result.is_error:
            error_name = type(result.error).__name__ if result.error is not None else "UnknownError"
            return (key, f"load error ({error_name})")
        if result.is_not_found:
            return (key, "resource not found")

        junk_count = len(result.junk_entries)
        noun = "entry" if junk_count == 1 else "entries"
        return (key, f"{junk_count} junk {noun}")

    def _raise_integrity_check_failed(
        self: LocalizationStateProtocol,
        operation: str,
        message: str,
        *,
        key: str | None = None,
        expected: str | None = None,
        actual: str | None = None,
    ) -> NoReturn:
        """Raise IntegrityCheckFailedError with localization-scoped context."""
        context = IntegrityContext(
            component="localization",
            operation=operation,
            key=key,
            expected=expected,
            actual=actual,
            timestamp=time.monotonic(),
            wall_time_unix=time.time(),
        )
        raise IntegrityCheckFailedError(message, context=context)

    def require_clean(self: LocalizationStateProtocol) -> LoadSummary:
        """Require a clean initialization load summary."""
        summary = self.get_load_summary()
        if summary.all_clean:
            return summary

        issue_key: str | None = None
        issue_detail: str | None = None
        for result in summary.results:  # pragma: no branch
            if result.is_error or result.is_not_found or result.has_junk:
                issue_key, issue_detail = self._describe_unclean_load_result(result)
                break

        actual = repr(summary)
        detail = (
            f" First issue: {issue_detail} at {issue_key}."
            if issue_key and issue_detail
            else ""
        )
        msg = f"Localization initialization is not clean: {actual}.{detail}"
        self._raise_integrity_check_failed(
            "require_clean",
            msg,
            key=issue_key,
            expected="LoadSummary(all_clean=True)",
            actual=actual,
        )
        raise AssertionError  # pragma: no cover

    @staticmethod
    def _format_schema_difference(
        validation: MessageVariableValidationResult,
    ) -> str:
        """Render a concise schema mismatch description."""
        parts: list[str] = []
        if validation.missing_variables:
            missing = ", ".join(sorted(validation.missing_variables))
            parts.append(f"missing {{{missing}}}")
        if validation.extra_variables:
            extra = ", ".join(sorted(validation.extra_variables))
            parts.append(f"extra {{{extra}}}")
        return "; ".join(parts)

    def _resolve_message_schema_validation(
        self: LocalizationStateProtocol,
        message_id: MessageId,
        expected_variables: frozenset[str] | set[str],
    ) -> MessageVariableValidationResult | None:
        """Resolve a message through the fallback chain and validate its schema."""
        message = self.get_message(message_id)
        if message is None:
            return None
        return validate_message_ast_variables(message, frozenset(expected_variables))

    def validate_message_variables(
        self: LocalizationStateProtocol,
        message_id: str,
        expected_variables: frozenset[str] | set[str],
    ) -> MessageVariableValidationResult:
        """Require an exact variable schema match for one fallback-resolved message."""
        validation = self._resolve_message_schema_validation(message_id, expected_variables)
        if validation is None:
            msg = f"Localization message schema validation failed: {message_id}: not found"
            self._raise_integrity_check_failed(
                "validate_message_variables",
                msg,
                key=message_id,
                expected="1 exact schema match",
                actual="missing_messages=1",
            )

        if validation.is_valid:
            return validation

        difference = self._format_schema_difference(validation)
        msg = f"Localization message schema validation failed: {message_id}: {difference}"
        self._raise_integrity_check_failed(
            "validate_message_variables",
            msg,
            key=message_id,
            expected="1 exact schema match",
            actual="schema_mismatches=1",
        )
        raise AssertionError  # pragma: no cover

    def validate_message_schemas(
        self: LocalizationStateProtocol,
        expected_schemas: Mapping[MessageId, frozenset[str] | set[str]],
    ) -> tuple[MessageVariableValidationResult, ...]:
        """Require exact variable-schema matches for specific messages."""
        results: list[MessageVariableValidationResult] = []
        mismatches: list[str] = []
        first_failure: str | None = None
        missing_messages = 0
        schema_mismatches = 0

        for message_id, expected_variables in expected_schemas.items():
            validation = self._resolve_message_schema_validation(message_id, expected_variables)
            if validation is None:
                first_failure = first_failure or str(message_id)
                missing_messages += 1
                mismatches.append(f"{message_id}: not found")
                continue

            results.append(validation)
            if validation.is_valid:
                continue

            first_failure = first_failure or message_id
            schema_mismatches += 1
            difference = self._format_schema_difference(validation)
            mismatches.append(f"{message_id}: {difference}")

        if missing_messages > 0 or schema_mismatches > 0:
            fragments = mismatches[:3]
            remaining = len(mismatches) - len(fragments)
            if remaining > 0:
                noun = "issue" if remaining == 1 else "issues"
                fragments.append(f"... {remaining} more {noun}")

            actual_parts: list[str] = []
            if missing_messages > 0:
                actual_parts.append(f"missing_messages={missing_messages}")
            if schema_mismatches > 0:
                actual_parts.append(f"schema_mismatches={schema_mismatches}")

            actual = ", ".join(actual_parts)
            summary = "; ".join(fragments)
            msg = f"Localization message schema validation failed: {summary}"
            self._raise_integrity_check_failed(
                "validate_message_schemas",
                msg,
                key=first_failure,
                expected=f"{len(expected_schemas)} exact schema match(es)",
                actual=actual,
            )

        return tuple(results)
