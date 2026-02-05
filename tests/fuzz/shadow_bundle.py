"""Shadow Bundle - Reference implementation for differential testing.

This module provides a deliberately simple, unoptimized implementation of
Fluent message formatting for use in oracle-based fuzzing. The shadow model
prioritizes correctness and simplicity over performance.

Key characteristics:
- No caching (compute everything fresh)
- No optimizations (simple recursive traversal)
- Explicit error handling (no silent failures)
- Matches FluentBundle API surface

Usage with Hypothesis RuleBasedStateMachine:
    class BundleOracle(RuleBasedStateMachine):
        def __init__(self):
            self.real = FluentBundle("en_US")
            self.shadow = ShadowBundle("en_US")

        @rule(source=ftl_simple_messages())
        def add_resource(self, source):
            real_junk = self.real.add_resource(source)
            shadow_junk = self.shadow.add_resource(source)
            # Compare results...

Python 3.13+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ftllexengine.syntax.ast import (
    Comment,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    MessageReference,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.parser import FluentParserV1

if TYPE_CHECKING:
    from ftllexengine.syntax.ast import InlineExpression


@dataclass
class ShadowError:
    """Simple error representation for shadow model."""

    kind: str
    message: str
    message_id: str | None = None

    def __str__(self) -> str:
        if self.message_id:
            return f"{self.kind}: {self.message} (in {self.message_id})"
        return f"{self.kind}: {self.message}"


@dataclass
class ShadowBundle:
    """Simple reference implementation of FluentBundle for differential testing.

    This implementation prioritizes correctness and simplicity:
    - No caching
    - No optimizations
    - No thread safety (not needed for testing)
    - Explicit recursive resolution
    - Clear error tracking

    The goal is to serve as an oracle: if the real FluentBundle produces
    different results, that's a potential bug.
    """

    locale: str
    _messages: dict[str, Message] = field(default_factory=dict)
    _terms: dict[str, Term] = field(default_factory=dict)
    _parser: FluentParserV1 = field(default_factory=FluentParserV1)

    # Resolution state tracking (reset per format call)
    _resolution_stack: list[str] = field(default_factory=list)
    _max_depth: int = 100

    def add_resource(self, source: str) -> tuple[Junk, ...]:
        """Add FTL resource to bundle.

        Args:
            source: FTL source text

        Returns:
            Tuple of Junk entries (parse errors)
        """
        resource = self._parser.parse(source)
        junk_entries: list[Junk] = []

        for entry in resource.entries:
            match entry:
                case Message() as msg:
                    self._messages[msg.id.name] = msg
                case Term() as term:
                    self._terms[term.id.name] = term
                case Comment():
                    pass  # Ignore comments
                case Junk() as junk:
                    junk_entries.append(junk)

        return tuple(junk_entries)

    def has_message(self, message_id: str) -> bool:
        """Check if message exists."""
        return message_id in self._messages

    def get_message_ids(self) -> frozenset[str]:
        """Get all message IDs."""
        return frozenset(self._messages.keys())

    def format_pattern(
        self,
        message_id: str,
        args: dict[str, str | int | float] | None = None,
    ) -> tuple[str, tuple[ShadowError, ...]]:
        """Format a message pattern.

        Args:
            message_id: Message identifier (may include .attribute suffix)
            args: Variable arguments

        Returns:
            Tuple of (formatted_string, errors)
        """
        # Reset resolution state
        self._resolution_stack = []
        errors: list[ShadowError] = []

        # Handle attribute access (msg.attr)
        attribute_name: str | None = None
        if "." in message_id:
            message_id, attribute_name = message_id.split(".", 1)

        # Check if message exists
        if message_id not in self._messages:
            errors.append(
                ShadowError(
                    kind="missing_message",
                    message=f"Message not found: {message_id}",
                    message_id=message_id,
                )
            )
            return f"{{{message_id}}}", tuple(errors)

        message = self._messages[message_id]

        # Get pattern (from attribute or message value)
        pattern: Pattern | None = None
        if attribute_name:
            for attr in message.attributes:
                if attr.id.name == attribute_name:
                    pattern = attr.value
                    break
            if pattern is None:
                errors.append(
                    ShadowError(
                        kind="missing_attribute",
                        message=f"Attribute not found: {message_id}.{attribute_name}",
                        message_id=message_id,
                    )
                )
                return f"{{{message_id}.{attribute_name}}}", tuple(errors)
        else:
            pattern = message.value

        if pattern is None:
            errors.append(
                ShadowError(
                    kind="no_value",
                    message=f"Message has no value: {message_id}",
                    message_id=message_id,
                )
            )
            return f"{{{message_id}}}", tuple(errors)

        # Resolve pattern
        result, resolve_errors = self._resolve_pattern(
            pattern, args or {}, message_id
        )
        errors.extend(resolve_errors)

        return result, tuple(errors)

    def _resolve_pattern(
        self,
        pattern: Pattern,
        args: dict[str, str | int | float],
        context_id: str,
    ) -> tuple[str, list[ShadowError]]:
        """Resolve a pattern to a string."""
        parts: list[str] = []
        errors: list[ShadowError] = []

        for element in pattern.elements:
            match element:
                case TextElement(value=text):
                    parts.append(text)
                case Placeable(expression=expr):
                    result, expr_errors = self._resolve_expression(
                        expr, args, context_id
                    )
                    parts.append(result)
                    errors.extend(expr_errors)

        return "".join(parts), errors

    def _resolve_expression(  # noqa: PLR0911, PLR0912, PLR0915
        self,
        expr: InlineExpression | SelectExpression,
        args: dict[str, str | int | float],
        context_id: str,
    ) -> tuple[str, list[ShadowError]]:
        """Resolve an expression to a string."""
        errors: list[ShadowError] = []

        # Depth check
        if len(self._resolution_stack) > self._max_depth:
            errors.append(
                ShadowError(
                    kind="depth_exceeded",
                    message=f"Max resolution depth exceeded: {self._max_depth}",
                    message_id=context_id,
                )
            )
            return "{???}", errors

        match expr:
            case StringLiteral(value=value):
                return value, errors

            case NumberLiteral(value=value):
                return str(value), errors

            case VariableReference(id=Identifier(name=name)):
                if name in args:
                    return str(args[name]), errors
                errors.append(
                    ShadowError(
                        kind="missing_variable",
                        message=f"Variable not provided: ${name}",
                        message_id=context_id,
                    )
                )
                return f"{{${name}}}", errors

            case MessageReference(id=Identifier(name=ref_id), attribute=attr):
                # Cycle detection
                ref_key = f"msg:{ref_id}"
                if ref_key in self._resolution_stack:
                    errors.append(
                        ShadowError(
                            kind="cyclic_reference",
                            message=f"Cyclic reference: {ref_id}",
                            message_id=context_id,
                        )
                    )
                    return f"{{{ref_id}}}", errors

                self._resolution_stack.append(ref_key)
                try:
                    full_ref = ref_id
                    if attr:
                        full_ref = f"{ref_id}.{attr.name}"
                    result, ref_errors = self.format_pattern(full_ref, args)
                    errors.extend(ref_errors)
                    return result, errors
                finally:
                    self._resolution_stack.pop()

            case TermReference(id=Identifier(name=term_id), attribute=attr):
                # Cycle detection
                ref_key = f"term:{term_id}"
                if ref_key in self._resolution_stack:
                    errors.append(
                        ShadowError(
                            kind="cyclic_reference",
                            message=f"Cyclic term reference: -{term_id}",
                            message_id=context_id,
                        )
                    )
                    return f"{{-{term_id}}}", errors

                if term_id not in self._terms:
                    errors.append(
                        ShadowError(
                            kind="missing_term",
                            message=f"Term not found: -{term_id}",
                            message_id=context_id,
                        )
                    )
                    return f"{{-{term_id}}}", errors

                self._resolution_stack.append(ref_key)
                try:
                    term = self._terms[term_id]
                    pattern: Pattern | None = None

                    if attr:
                        for term_attr in term.attributes:
                            if term_attr.id.name == attr.name:
                                pattern = term_attr.value
                                break
                        if pattern is None:
                            errors.append(
                                ShadowError(
                                    kind="missing_attribute",
                                    message=f"Term attribute not found: -{term_id}.{attr.name}",
                                    message_id=context_id,
                                )
                            )
                            return f"{{-{term_id}.{attr.name}}}", errors
                    else:
                        pattern = term.value

                    result, term_errors = self._resolve_pattern(
                        pattern, args, context_id
                    )
                    errors.extend(term_errors)
                    return result, errors
                finally:
                    self._resolution_stack.pop()

            case FunctionReference(id=Identifier(name=func_name)):
                # Simple function handling - just format as placeholder
                # Real implementation would call registered functions
                errors.append(
                    ShadowError(
                        kind="function_not_implemented",
                        message=f"Function not implemented in shadow: {func_name}",
                        message_id=context_id,
                    )
                )
                return f"{{!{func_name}}}", errors

            case SelectExpression(selector=selector, variants=variants):
                # Resolve selector
                selector_result, sel_errors = self._resolve_expression(
                    selector, args, context_id
                )
                errors.extend(sel_errors)

                # Find matching variant
                default_variant = None
                matched_variant = None

                for variant in variants:
                    if variant.default:
                        default_variant = variant

                    # Get variant key
                    key_str: str
                    match variant.key:
                        case Identifier(name=name):
                            key_str = name
                        case NumberLiteral(value=value):
                            key_str = str(value)

                    if key_str == selector_result:
                        matched_variant = variant
                        break

                # Use matched or default
                chosen = matched_variant or default_variant
                if chosen is None:
                    errors.append(
                        ShadowError(
                            kind="no_variant",
                            message="No matching variant and no default",
                            message_id=context_id,
                        )
                    )
                    return "{???}", errors

                result, var_errors = self._resolve_pattern(
                    chosen.value, args, context_id
                )
                errors.extend(var_errors)
                return result, errors

            case Placeable(expression=inner):
                # Nested placeable
                return self._resolve_expression(inner, args, context_id)

    def clear(self) -> None:
        """Clear all messages and terms."""
        self._messages.clear()
        self._terms.clear()


def compare_bundles(
    real_result: tuple[str, tuple[object, ...]],
    shadow_result: tuple[str, tuple[ShadowError, ...]],
    *,
    ignore_function_errors: bool = True,
) -> tuple[bool, str]:
    """Compare results from real FluentBundle and ShadowBundle.

    Args:
        real_result: (formatted_string, errors) from FluentBundle
        shadow_result: (formatted_string, errors) from ShadowBundle
        ignore_function_errors: Don't fail on function-related differences
            (shadow doesn't implement functions)

    Returns:
        Tuple of (match, explanation)
    """
    real_str, real_errors = real_result
    shadow_str, shadow_errors = shadow_result

    # Filter function errors if requested
    if ignore_function_errors:
        shadow_errors = tuple(
            e for e in shadow_errors if e.kind != "function_not_implemented"
        )

    # Compare strings
    if real_str != shadow_str:
        return False, f"String mismatch: real={real_str!r}, shadow={shadow_str!r}"

    # Compare error counts (rough check)
    if len(real_errors) != len(shadow_errors):
        return False, (
            f"Error count mismatch: real={len(real_errors)}, shadow={len(shadow_errors)}"
        )

    return True, "Match"
