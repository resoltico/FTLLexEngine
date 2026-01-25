"""Data integrity exceptions for financial-grade safety.

These exceptions indicate SYSTEM FAILURES, not user-facing Fluent errors.
They should propagate to the top level and trigger incident response.

Design:
    - NOT subclasses of FrozenFluentError (different error domain)
    - Carry diagnostic context for post-mortem analysis
    - Immutable after construction
    - @final decorator prevents subclassing

Hierarchy:
    DataIntegrityError (base - system failures)
    ├─ CacheCorruptionError (checksum mismatch)
    ├─ FormattingIntegrityError (strict mode formatting failure)
    ├─ ImmutabilityViolationError (mutation attempt on frozen object)
    ├─ IntegrityCheckFailedError (generic verification failure)
    ├─ SyntaxIntegrityError (strict mode syntax error during resource loading)
    └─ WriteConflictError (write-once violation)

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from ftllexengine.diagnostics import FrozenFluentError
    from ftllexengine.syntax.ast import Junk

__all__ = [
    "CacheCorruptionError",
    "DataIntegrityError",
    "FormattingIntegrityError",
    "ImmutabilityViolationError",
    "IntegrityCheckFailedError",
    "IntegrityContext",
    "SyntaxIntegrityError",
    "WriteConflictError",
]


@dataclass(frozen=True, slots=True)
class IntegrityContext:
    """Context for integrity error diagnosis.

    Provides structured information for post-mortem analysis of
    data integrity failures.

    Attributes:
        component: System component where error occurred (cache, error, bundle)
        operation: Operation being performed (get, put, verify, mutate)
        key: Cache key or identifier involved (optional)
        expected: Expected value/hash (optional)
        actual: Actual value/hash found (optional)
        timestamp: Time of error detection (time.monotonic())
    """

    component: str
    operation: str
    key: str | None = None
    expected: str | None = None
    actual: str | None = None
    timestamp: float | None = None


class DataIntegrityError(Exception):
    """Base exception for all data integrity failures.

    NOT a FrozenFluentError subclass. These are SYSTEM failures, not
    user-facing Fluent errors. They indicate corruption, bugs, or
    security incidents that should propagate to the top level.

    This exception is immutable after construction to prevent
    tampering with error evidence.

    Subclasses are @final to prevent further inheritance.

    Attributes:
        context: Structured diagnostic context for post-mortem analysis
    """

    __slots__ = ("_context", "_frozen")

    # Type annotations for __slots__ attributes (mypy requirement)
    _context: IntegrityContext | None
    _frozen: bool

    def __init__(
        self,
        message: str,
        context: IntegrityContext | None = None,
    ) -> None:
        """Initialize DataIntegrityError.

        Args:
            message: Human-readable error description
            context: Structured diagnostic context (optional)
        """
        super().__init__(message)
        object.__setattr__(self, "_context", context)
        object.__setattr__(self, "_frozen", True)

    # Python's exception handling sets these attributes when propagating exceptions.
    # __notes__ was added in Python 3.11 for Exception Groups (PEP 654/678).
    _PYTHON_EXCEPTION_ATTRS: frozenset[str] = frozenset(
        ("__traceback__", "__context__", "__cause__", "__suppress_context__", "__notes__")
    )

    def __setattr__(self, name: str, value: object) -> None:
        """Reject all attribute mutations after initialization.

        Python's exception mechanism must be able to set __traceback__,
        __context__, __cause__, and __suppress_context__ during propagation.
        These are allowed even after freeze.

        Raises:
            ImmutabilityViolationError: If attempting to modify after construction
        """
        # Allow Python's internal exception handling attributes
        if name in self._PYTHON_EXCEPTION_ATTRS:
            object.__setattr__(self, name, value)
            return
        if getattr(self, "_frozen", False):
            msg = f"Cannot modify integrity error attribute: {name}"
            raise ImmutabilityViolationError(msg)
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        """Reject all attribute deletions.

        Raises:
            ImmutabilityViolationError: Always
        """
        msg = f"Cannot delete integrity error attribute: {name}"
        raise ImmutabilityViolationError(msg)

    @property
    def context(self) -> IntegrityContext | None:
        """Structured diagnostic context."""
        return self._context

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return f"{self.__class__.__name__}({self.args[0]!r}, context={self._context!r})"


@final
class CacheCorruptionError(DataIntegrityError):
    """Checksum mismatch detected in cache entry.

    Raised when a cached value's checksum doesn't match the stored checksum.
    This indicates memory corruption, hardware fault, or tampering.

    This is a CRITICAL error that should trigger immediate investigation.
    The cache entry should be evicted and the operation retried.
    """



@final
class ImmutabilityViolationError(DataIntegrityError):
    """Attempt to mutate an immutable object.

    Raised when code attempts to modify a frozen FrozenFluentError,
    DataIntegrityError, or cache entry.

    This typically indicates a programming error or malicious code
    attempting to tamper with error evidence.
    """



@final
class IntegrityCheckFailedError(DataIntegrityError):
    """Generic integrity verification failure.

    Raised when an integrity check fails but doesn't fall into a more
    specific category. Examples:
        - Newly created cache entry fails immediate verification
        - Write log integrity check fails
        - Error verification fails
    """



@final
class WriteConflictError(DataIntegrityError):
    """Write-once violation in cache.

    Raised when attempting to overwrite an existing cache entry
    in write-once mode. This is a security feature for financial
    applications where cache overwrites could mask data races.

    Attributes:
        existing_seq: Sequence number of existing entry
        new_seq: Sequence number of rejected write attempt
    """

    __slots__ = ("_existing_seq", "_new_seq")

    # Type annotations for __slots__ attributes (mypy requirement)
    _existing_seq: int
    _new_seq: int

    def __init__(
        self,
        message: str,
        context: IntegrityContext | None = None,
        *,
        existing_seq: int = 0,
        new_seq: int = 0,
    ) -> None:
        """Initialize WriteConflictError.

        Args:
            message: Human-readable error description
            context: Structured diagnostic context (optional)
            existing_seq: Sequence number of existing entry
            new_seq: Sequence number of rejected write attempt
        """
        # Must set these before calling super().__init__ which freezes
        object.__setattr__(self, "_existing_seq", existing_seq)
        object.__setattr__(self, "_new_seq", new_seq)
        super().__init__(message, context)

    @property
    def existing_seq(self) -> int:
        """Sequence number of existing cache entry."""
        return self._existing_seq

    @property
    def new_seq(self) -> int:
        """Sequence number of rejected write attempt."""
        return self._new_seq

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"WriteConflictError({self.args[0]!r}, "
            f"existing_seq={self._existing_seq}, "
            f"new_seq={self._new_seq})"
        )


@final
class FormattingIntegrityError(DataIntegrityError):
    """Formatting errors in strict mode.

    Raised in strict mode when format_pattern encounters ANY errors.
    Financial applications require fail-fast behavior - silent fallback
    values are unacceptable when formatting monetary amounts or
    critical business data.

    This exception carries the original Fluent errors for inspection
    and the fallback value that would have been returned in non-strict mode.

    Attributes:
        fluent_errors: Tuple of FrozenFluentError instances that triggered this exception
        fallback_value: The fallback string that would have been returned in non-strict mode
        message_id: The message ID that failed to format
    """

    __slots__ = ("_fallback_value", "_fluent_errors", "_message_id")

    # Type annotations for __slots__ attributes (mypy requirement)
    _fluent_errors: tuple[FrozenFluentError, ...]
    _fallback_value: str
    _message_id: str

    def __init__(
        self,
        message: str,
        context: IntegrityContext | None = None,
        *,
        fluent_errors: tuple[FrozenFluentError, ...] = (),
        fallback_value: str = "",
        message_id: str = "",
    ) -> None:
        """Initialize FormattingIntegrityError.

        Args:
            message: Human-readable error description
            context: Structured diagnostic context (optional)
            fluent_errors: Tuple of FrozenFluentError instances
            fallback_value: Fallback value that would have been returned
            message_id: Message ID that failed to format
        """
        # Must set these before calling super().__init__ which freezes
        # Defensive tuple() conversion ensures immutability even if caller passes list
        object.__setattr__(self, "_fluent_errors", tuple(fluent_errors))
        object.__setattr__(self, "_fallback_value", fallback_value)
        object.__setattr__(self, "_message_id", message_id)
        super().__init__(message, context)

    @property
    def fluent_errors(self) -> tuple[FrozenFluentError, ...]:
        """Original Fluent errors that triggered this exception."""
        return self._fluent_errors

    @property
    def fallback_value(self) -> str:
        """Fallback value that would have been returned in non-strict mode."""
        return self._fallback_value

    @property
    def message_id(self) -> str:
        """Message ID that failed to format."""
        return self._message_id

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"FormattingIntegrityError({self.args[0]!r}, "
            f"message_id={self._message_id!r}, "
            f"error_count={len(self._fluent_errors)})"
        )


@final
class SyntaxIntegrityError(DataIntegrityError):
    """Syntax errors in strict mode during resource loading.

    Raised in strict mode when add_resource() encounters syntax errors
    (Junk entries). Financial applications require fail-fast behavior -
    loading partially valid FTL resources is unacceptable when formatting
    monetary amounts or critical business data.

    This exception carries the Junk entries that caused the failure,
    enabling detailed error reporting and recovery strategies.

    Attributes:
        junk_entries: Tuple of Junk AST nodes representing syntax errors
        source_path: Optional path to the source file (for error context)
    """

    __slots__ = ("_junk_entries", "_source_path")

    # Type annotations for __slots__ attributes (mypy requirement)
    _junk_entries: tuple[Junk, ...]
    _source_path: str | None

    def __init__(
        self,
        message: str,
        context: IntegrityContext | None = None,
        *,
        junk_entries: tuple[Junk, ...] = (),
        source_path: str | None = None,
    ) -> None:
        """Initialize SyntaxIntegrityError.

        Args:
            message: Human-readable error description
            context: Structured diagnostic context (optional)
            junk_entries: Tuple of Junk AST nodes from failed parse
            source_path: Optional path to source file for context
        """
        # Must set these before calling super().__init__ which freezes
        # Defensive tuple() conversion ensures immutability even if caller passes list
        object.__setattr__(self, "_junk_entries", tuple(junk_entries))
        object.__setattr__(self, "_source_path", source_path)
        super().__init__(message, context)

    @property
    def junk_entries(self) -> tuple[Junk, ...]:
        """Junk AST nodes representing syntax errors."""
        return self._junk_entries

    @property
    def source_path(self) -> str | None:
        """Optional path to the source file."""
        return self._source_path

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"SyntaxIntegrityError({self.args[0]!r}, "
            f"source_path={self._source_path!r}, "
            f"junk_count={len(self._junk_entries)})"
        )
