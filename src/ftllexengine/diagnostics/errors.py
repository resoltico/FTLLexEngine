"""Fluent exception hierarchy with financial-grade data integrity.

Provides FrozenFluentError: a sealed, immutable, content-addressable exception
for financial applications requiring guaranteed data safety.

Design Principles:
    - Immutability: All attributes frozen after construction
    - Sealed Type: No subclassing allowed (prevents invariant violations)
    - Content Addressing: BLAKE2b hash for integrity verification
    - Exhaustive Categorization: ErrorCategory enum replaces inheritance

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING, final

from .codes import Diagnostic, ErrorCategory, FrozenErrorContext

if TYPE_CHECKING:
    pass

# ruff: noqa: RUF022 - __all__ organized by category for readability, not alphabetically
__all__ = [
    "FrozenFluentError",
    # Re-export for convenience
    "ErrorCategory",
    "FrozenErrorContext",
]


@final
class FrozenFluentError(Exception):
    """Immutable, content-addressable Fluent error for financial-grade integrity.

    This exception class provides strong guarantees for data integrity:

    1. IMMUTABILITY: All attributes frozen after __init__ completes.
       Any mutation attempt raises ImmutabilityViolationError.

    2. SEALED TYPE: Cannot be subclassed. The @final decorator provides
       static analysis enforcement, and __init_subclass__ provides runtime
       enforcement. This prevents invariant violations via malicious subclasses.

    3. CONTENT ADDRESSING: A BLAKE2b-128 hash of all content is computed
       at construction and cached. verify_integrity() detects any corruption.

    4. HASHABLE: Can be used in sets and as dict keys. Hash is stable
       and based on content, not object identity.

    Attributes:
        message: Human-readable error description
        category: Error categorization (replaces subclass hierarchy)
        diagnostic: Structured diagnostic information (optional)
        context: Additional context for parse/formatting errors (optional)

    Example:
        >>> error = FrozenFluentError(
        ...     "Message 'hello' not found",
        ...     ErrorCategory.REFERENCE,
        ...     diagnostic=some_diagnostic,
        ... )
        >>> error.category == ErrorCategory.REFERENCE
        True
        >>> error.verify_integrity()
        True
        >>> # Attempting mutation raises:
        >>> error._message = "modified"  # Raises ImmutabilityViolationError
    """

    __slots__ = (
        "_category",
        "_content_hash",
        "_context",
        "_diagnostic",
        "_frozen",
        "_message",
    )

    # Type annotations for __slots__ attributes (mypy requirement)
    _category: ErrorCategory
    _content_hash: bytes
    _context: FrozenErrorContext | None
    _diagnostic: Diagnostic | None
    _frozen: bool
    _message: str

    def __init__(
        self,
        message: str,
        category: ErrorCategory,
        diagnostic: Diagnostic | None = None,
        context: FrozenErrorContext | None = None,
    ) -> None:
        """Initialize FrozenFluentError.

        Args:
            message: Human-readable error description
            category: Error categorization (REFERENCE, RESOLUTION, CYCLIC, PARSE, FORMATTING)
            diagnostic: Structured diagnostic information (optional)
            context: Additional context for parse/formatting errors (optional)
        """
        # Set attributes before freezing
        object.__setattr__(self, "_message", message)
        object.__setattr__(self, "_category", category)
        object.__setattr__(self, "_diagnostic", diagnostic)
        object.__setattr__(self, "_context", context)

        # Compute content hash for integrity verification
        content_hash = self._compute_content_hash(message, category, diagnostic, context)
        object.__setattr__(self, "_content_hash", content_hash)

        # Freeze the object - all subsequent mutations will raise
        object.__setattr__(self, "_frozen", True)

        # Initialize Exception base class
        super().__init__(message)

    @staticmethod
    def _compute_content_hash(
        message: str,
        category: ErrorCategory,
        diagnostic: Diagnostic | None,
        context: FrozenErrorContext | None,
    ) -> bytes:
        """Compute BLAKE2b-128 hash of error content.

        Uses BLAKE2b for speed (faster than SHA-256) while maintaining
        cryptographic security. 128-bit digest is sufficient for integrity
        verification (not cryptographic security).

        Hash Composition:
            The content hash covers ALL error fields for complete integrity:
            1. message: Error description (UTF-8 encoded)
            2. category: Error category value
            3. diagnostic (if present): ALL fields including:
               - code.name, message
               - span (start, end, line, column as 4-byte big-endian)
               - hint, help_url, function_name, argument_name
               - expected_type, received_type, ftl_location
               - severity
               - resolution_path (each element)
            4. context (if present): input_value, locale_code, parse_type, fallback_value

        Args:
            message: Error message
            category: Error category
            diagnostic: Diagnostic object (optional)
            context: Error context (optional)

        Returns:
            16-byte BLAKE2b digest
        """
        h = hashlib.blake2b(digest_size=16)
        # Use surrogatepass to handle invalid Unicode surrogates in input
        # This ensures hashing works for any Python string, including those
        # containing unpaired surrogates from malformed user input
        h.update(message.encode("utf-8", errors="surrogatepass"))
        h.update(category.value.encode("utf-8"))

        if diagnostic is not None:
            # Hash ALL diagnostic fields for complete audit trail integrity
            # Core fields
            h.update(diagnostic.code.name.encode("utf-8"))
            h.update(diagnostic.message.encode("utf-8", errors="surrogatepass"))

            # Source location (span)
            if diagnostic.span is not None:
                h.update(diagnostic.span.start.to_bytes(4, "big", signed=True))
                h.update(diagnostic.span.end.to_bytes(4, "big", signed=True))
                h.update(diagnostic.span.line.to_bytes(4, "big", signed=True))
                h.update(diagnostic.span.column.to_bytes(4, "big", signed=True))
            else:
                # Hash sentinel for None to distinguish from span with zeros
                h.update(b"\x00\x00\x00\x00NOSPAN")

            # Optional string fields (use sentinel for None distinction)
            for field_value in (
                diagnostic.hint,
                diagnostic.help_url,
                diagnostic.function_name,
                diagnostic.argument_name,
                diagnostic.expected_type,
                diagnostic.received_type,
                diagnostic.ftl_location,
            ):
                if field_value is not None:
                    h.update(field_value.encode("utf-8", errors="surrogatepass"))
                else:
                    h.update(b"\x00NONE")

            # Severity (always present, required field)
            h.update(diagnostic.severity.encode("utf-8"))

            # Resolution path (tuple of strings or None)
            if diagnostic.resolution_path is not None:
                h.update(len(diagnostic.resolution_path).to_bytes(4, "big"))
                for path_element in diagnostic.resolution_path:
                    h.update(path_element.encode("utf-8", errors="surrogatepass"))
            else:
                h.update(b"\x00NOPATH")

        if context is not None:
            h.update(context.input_value.encode("utf-8", errors="surrogatepass"))
            h.update(context.locale_code.encode("utf-8", errors="surrogatepass"))
            h.update(context.parse_type.encode("utf-8", errors="surrogatepass"))
            h.update(context.fallback_value.encode("utf-8", errors="surrogatepass"))

        return h.digest()

    def __setattr__(self, name: str, value: object) -> None:
        """Reject all attribute mutations after initialization.

        Raises:
            ImmutabilityViolationError: Always, if object is frozen
        """
        if getattr(self, "_frozen", False):

            from ftllexengine.integrity import ImmutabilityViolationError  # noqa: PLC0415

            msg = f"Cannot modify frozen error attribute: {name}"
            raise ImmutabilityViolationError(msg)
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        """Reject all attribute deletions.

        Raises:
            ImmutabilityViolationError: Always
        """

        from ftllexengine.integrity import ImmutabilityViolationError  # noqa: PLC0415

        msg = f"Cannot delete frozen error attribute: {name}"
        raise ImmutabilityViolationError(msg)

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Prevent subclassing at runtime.

        The @final decorator provides static analysis enforcement.
        This method provides runtime enforcement.

        Raises:
            TypeError: Always - FrozenFluentError cannot be subclassed
        """
        msg = (
            "FrozenFluentError cannot be subclassed. "
            "Use ErrorCategory enum for error classification."
        )
        raise TypeError(msg)

    def __hash__(self) -> int:
        """Return hash based on content, not object identity.

        Returns:
            Integer hash derived from content hash
        """
        return int.from_bytes(self._content_hash[:8], "big")

    def __eq__(self, other: object) -> bool:
        """Compare errors by content.

        Args:
            other: Object to compare

        Returns:
            True if other is a FrozenFluentError with identical content
        """
        if not isinstance(other, FrozenFluentError):
            return NotImplemented
        return self._content_hash == other._content_hash

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"FrozenFluentError("
            f"message={self._message!r}, "
            f"category={self._category!r}, "
            f"diagnostic={self._diagnostic!r}, "
            f"context={self._context!r})"
        )

    def verify_integrity(self) -> bool:
        """Verify error content hasn't been corrupted.

        Recomputes content hash and compares to stored hash using
        constant-time comparison (defense against timing attacks).

        Returns:
            True if content hash matches, False if corrupted
        """
        expected = self._compute_content_hash(
            self._message, self._category, self._diagnostic, self._context
        )
        return hmac.compare_digest(self._content_hash, expected)

    @property
    def message(self) -> str:
        """Human-readable error description."""
        return self._message

    @property
    def category(self) -> ErrorCategory:
        """Error categorization."""
        return self._category

    @property
    def diagnostic(self) -> Diagnostic | None:
        """Structured diagnostic information."""
        return self._diagnostic

    @property
    def context(self) -> FrozenErrorContext | None:
        """Additional context for parse/formatting errors."""
        return self._context

    @property
    def content_hash(self) -> bytes:
        """BLAKE2b-128 hash of error content."""
        return self._content_hash

    # Convenience properties for common context fields
    @property
    def fallback_value(self) -> str:
        """Fallback value for formatting errors (empty string if not applicable)."""
        if self._context is not None:
            return self._context.fallback_value
        return ""

    @property
    def input_value(self) -> str:
        """Input value that caused parse error (empty string if not applicable)."""
        if self._context is not None:
            return self._context.input_value
        return ""

    @property
    def locale_code(self) -> str:
        """Locale code for parse/formatting error (empty string if not applicable)."""
        if self._context is not None:
            return self._context.locale_code
        return ""

    @property
    def parse_type(self) -> str:
        """Parse type for parse error (empty string if not applicable)."""
        if self._context is not None:
            return self._context.parse_type
        return ""
