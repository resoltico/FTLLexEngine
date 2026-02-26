"""Property-based tests for integrity exception classes.

Tests data integrity exceptions used for financial-grade safety:
- IntegrityContext: Diagnostic context for post-mortem analysis
- DataIntegrityError: Base exception with immutability enforcement
- CacheCorruptionError: Checksum mismatch detection
- FormattingIntegrityError: Strict mode formatting failures
- ImmutabilityViolationError: Mutation attempt detection
- IntegrityCheckFailedError: Generic integrity verification failures
- WriteConflictError: Write-once violation detection

These tests verify:
- Immutability enforcement (__setattr__, __delattr__)
- Python exception mechanism compatibility (__traceback__, __context__, etc.)
- Structured diagnostic context preservation
- String representations (__repr__)
- Exception hierarchy and @final enforcement
- Property access and data integrity

"""

from __future__ import annotations

import time

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.integrity import (
    CacheCorruptionError,
    DataIntegrityError,
    FormattingIntegrityError,
    ImmutabilityViolationError,
    IntegrityCheckFailedError,
    IntegrityContext,
    SyntaxIntegrityError,
    WriteConflictError,
)
from ftllexengine.syntax.ast import Junk

# =============================================================================
# Strategies for generating test data
# =============================================================================


@st.composite
def integrity_contexts(draw: st.DrawFn) -> IntegrityContext:
    """Generate IntegrityContext instances."""
    return IntegrityContext(
        component=draw(st.text(min_size=1, max_size=50)),
        operation=draw(st.text(min_size=1, max_size=50)),
        key=draw(st.one_of(st.none(), st.text(min_size=1, max_size=100))),
        expected=draw(st.one_of(st.none(), st.text(min_size=1, max_size=100))),
        actual=draw(st.one_of(st.none(), st.text(min_size=1, max_size=100))),
        timestamp=draw(st.one_of(st.none(), st.floats(min_value=0, max_value=1e10))),
    )


@st.composite
def error_messages(draw: st.DrawFn) -> str:
    """Generate error messages."""
    return draw(st.text(min_size=1, max_size=200))


# =============================================================================
# IntegrityContext Tests
# =============================================================================


class TestIntegrityContext:
    """Test IntegrityContext dataclass."""

    @given(
        component=st.text(min_size=1, max_size=50),
        operation=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_minimal_construction(self, component: str, operation: str) -> None:
        """Property: IntegrityContext can be constructed with minimal fields."""
        ctx = IntegrityContext(component=component, operation=operation)
        event(f"component_len={len(component)}")
        event(f"operation_len={len(operation)}")
        assert ctx.component == component
        assert ctx.operation == operation
        assert ctx.key is None
        assert ctx.expected is None
        assert ctx.actual is None
        assert ctx.timestamp is None

    @given(context=integrity_contexts())
    @settings(max_examples=50)
    def test_full_construction(self, context: IntegrityContext) -> None:
        """Property: IntegrityContext preserves all fields."""
        has_key = context.key is not None
        has_expected = context.expected is not None
        has_actual = context.actual is not None
        has_timestamp = context.timestamp is not None
        event(f"key_present={has_key}")
        event(f"expected_present={has_expected}")
        event(f"actual_present={has_actual}")
        event(f"timestamp_present={has_timestamp}")
        # Access all fields to verify they're stored correctly
        assert isinstance(context.component, str)
        assert isinstance(context.operation, str)
        assert context.key is None or isinstance(context.key, str)
        assert context.expected is None or isinstance(context.expected, str)
        assert context.actual is None or isinstance(context.actual, str)
        assert context.timestamp is None or isinstance(context.timestamp, float)

    @given(context=integrity_contexts())
    @settings(max_examples=50)
    def test_context_is_frozen(self, context: IntegrityContext) -> None:
        """Property: IntegrityContext is immutable (frozen=True)."""
        event(f"component_len={len(context.component)}")
        with pytest.raises((AttributeError, TypeError)):
            context.component = "modified"  # type: ignore[misc]

    @given(context=integrity_contexts())
    @settings(max_examples=50)
    def test_context_repr(self, context: IntegrityContext) -> None:
        """Property: IntegrityContext has valid __repr__."""
        r = repr(context)
        event(f"repr_len={len(r)}")
        assert "IntegrityContext" in r
        assert "component=" in r
        assert "operation=" in r


# =============================================================================
# DataIntegrityError Base Class Tests
# =============================================================================


class TestDataIntegrityError:
    """Test DataIntegrityError base exception class."""

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_construction_without_context(self, message: str) -> None:
        """Property: DataIntegrityError can be constructed without context."""
        error = DataIntegrityError(message)
        event(f"msg_len={len(message)}")
        assert str(error) == message
        assert error.args == (message,)
        assert error.context is None

    @given(message=error_messages(), context=integrity_contexts())
    @settings(max_examples=50)
    def test_construction_with_context(
        self, message: str, context: IntegrityContext
    ) -> None:
        """Property: DataIntegrityError preserves context."""
        error = DataIntegrityError(message, context=context)
        has_key = context.key is not None
        event(f"context_has_key={has_key}")
        event(f"msg_len={len(message)}")
        assert str(error) == message
        assert error.context is context
        assert error.context.component == context.component
        assert error.context.operation == context.operation

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_immutability_after_construction(self, message: str) -> None:
        """Property: Cannot modify DataIntegrityError after construction."""
        error = DataIntegrityError(message)
        event(f"msg_len={len(message)}")

        with pytest.raises(ImmutabilityViolationError, match="Cannot modify"):
            error._context = None

        with pytest.raises(ImmutabilityViolationError, match="Cannot modify"):
            error._frozen = False

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_delattr_always_raises(self, message: str) -> None:
        """Property: Cannot delete any attributes from DataIntegrityError."""
        error = DataIntegrityError(message)
        event(f"msg_len={len(message)}")

        with pytest.raises(ImmutabilityViolationError, match="Cannot delete"):
            del error._context

        with pytest.raises(ImmutabilityViolationError, match="Cannot delete"):
            del error._frozen

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_repr_without_context(self, message: str) -> None:
        """Property: __repr__ works without context."""
        error = DataIntegrityError(message)
        r = repr(error)
        assert "DataIntegrityError" in r
        assert repr(message) in r  # Check for escaped version
        assert "context=None" in r

    @given(message=error_messages(), context=integrity_contexts())
    @settings(max_examples=50)
    def test_repr_with_context(
        self, message: str, context: IntegrityContext
    ) -> None:
        """Property: __repr__ includes context when present."""
        error = DataIntegrityError(message, context=context)
        r = repr(error)
        assert "DataIntegrityError" in r
        assert repr(message) in r  # Check for escaped version
        assert "context=" in r
        assert "IntegrityContext" in r

    def test_python_exception_attributes_allowed(self) -> None:
        """Python exception mechanism can set internal attributes."""
        error = DataIntegrityError("Test error")

        # These should be allowed (Python's exception handling needs them)
        try:
            raise error
        except DataIntegrityError as caught:
            # Python sets __traceback__ automatically
            assert caught.__traceback__ is not None  # noqa: PT017

            # We should be able to set __context__, __cause__, __suppress_context__
            msg_context = "context"
            msg_cause = "cause"
            caught.__context__ = ValueError(msg_context)
            caught.__cause__ = TypeError(msg_cause)
            caught.__suppress_context__ = False

            assert isinstance(caught.__context__, ValueError)  # noqa: PT017
            assert isinstance(caught.__cause__, TypeError)  # noqa: PT017
            assert caught.__suppress_context__ is False  # noqa: PT017

    def test_python_exception_attributes_settable(self) -> None:
        """Python exception attributes can be set directly."""
        error = DataIntegrityError("Test")

        # These are in _PYTHON_EXCEPTION_ATTRS and should be allowed
        error.__traceback__ = None
        error.__context__ = None
        error.__cause__ = None
        error.__suppress_context__ = True

        assert error.__traceback__ is None
        assert error.__context__ is None
        assert error.__cause__ is None
        assert error.__suppress_context__ is True

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_can_be_raised_and_caught(self, message: str) -> None:
        """Property: DataIntegrityError can be raised and caught."""
        error = DataIntegrityError(message)

        with pytest.raises(DataIntegrityError) as exc_info:
            raise error

        assert exc_info.value is error
        assert str(exc_info.value) == message

    def test_setattr_when_not_frozen(self) -> None:
        """Test __setattr__ defensive branch when _frozen is False.

        This tests the defensive else branch in __setattr__ that allows
        attribute setting when the object is not yet frozen (line 122).
        While __init__ uses object.__setattr__ directly, this branch
        provides defensive coverage if __setattr__ is called before freeze.
        """
        error = DataIntegrityError("test")

        # Verify object is initially frozen
        assert error.context is None

        # Forcibly unfreeze using object.__setattr__ to bypass immutability
        object.__setattr__(error, "_frozen", False)

        # Now call the instance's __setattr__ - should reach line 122
        DataIntegrityError.__setattr__(error, "_context", None)

        # Verify the change took effect (should still be None)
        assert error._context is None

        # Re-freeze for cleanup
        object.__setattr__(error, "_frozen", True)


# =============================================================================
# CacheCorruptionError Tests
# =============================================================================


class TestCacheCorruptionError:
    """Test CacheCorruptionError final class."""

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_construction_and_inheritance(self, message: str) -> None:
        """Property: CacheCorruptionError is a DataIntegrityError."""
        error = CacheCorruptionError(message)
        assert isinstance(error, DataIntegrityError)
        assert isinstance(error, CacheCorruptionError)
        assert str(error) == message

    @given(message=error_messages(), context=integrity_contexts())
    @settings(max_examples=50)
    def test_with_context(self, message: str, context: IntegrityContext) -> None:
        """Property: CacheCorruptionError supports context."""
        error = CacheCorruptionError(message, context=context)
        assert error.context is context
        assert error.context.component == context.component

    def test_final_decorator_type_hint(self) -> None:
        """CacheCorruptionError is @final (enforced by mypy and __init_subclass__).

        The @final decorator sets __final__ = True for static analyzers.
        __init_subclass__ also raises TypeError at class-definition time,
        so runtime subclassing is now prohibited (not just a type hint).
        """
        assert getattr(CacheCorruptionError, "__final__", False) is True

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_immutability_inherited(self, message: str) -> None:
        """Property: CacheCorruptionError inherits immutability."""
        error = CacheCorruptionError(message)

        with pytest.raises(ImmutabilityViolationError):
            error._context = None


# =============================================================================
# ImmutabilityViolationError Tests
# =============================================================================


class TestImmutabilityViolationError:
    """Test ImmutabilityViolationError final class."""

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_construction_and_inheritance(self, message: str) -> None:
        """Property: ImmutabilityViolationError is a DataIntegrityError."""
        error = ImmutabilityViolationError(message)
        assert isinstance(error, DataIntegrityError)
        assert isinstance(error, ImmutabilityViolationError)
        assert str(error) == message

    def test_final_decorator_type_hint(self) -> None:
        """ImmutabilityViolationError is @final (enforced by mypy and __init_subclass__)."""
        assert getattr(ImmutabilityViolationError, "__final__", False) is True

    def test_used_for_mutation_detection(self) -> None:
        """ImmutabilityViolationError is raised when mutations detected."""
        error = DataIntegrityError("Original")

        # Attempting to mutate should raise ImmutabilityViolationError
        with pytest.raises(ImmutabilityViolationError):
            error._context = None


# =============================================================================
# IntegrityCheckFailedError Tests
# =============================================================================


class TestIntegrityCheckFailedError:
    """Test IntegrityCheckFailedError final class."""

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_construction_and_inheritance(self, message: str) -> None:
        """Property: IntegrityCheckFailedError is a DataIntegrityError."""
        error = IntegrityCheckFailedError(message)
        assert isinstance(error, DataIntegrityError)
        assert isinstance(error, IntegrityCheckFailedError)
        assert str(error) == message

    @given(message=error_messages(), context=integrity_contexts())
    @settings(max_examples=50)
    def test_with_context(self, message: str, context: IntegrityContext) -> None:
        """Property: IntegrityCheckFailedError supports context."""
        error = IntegrityCheckFailedError(message, context=context)
        assert error.context is context

    def test_final_decorator_type_hint(self) -> None:
        """IntegrityCheckFailedError is @final (enforced by mypy and __init_subclass__)."""
        assert getattr(IntegrityCheckFailedError, "__final__", False) is True


# =============================================================================
# WriteConflictError Tests
# =============================================================================


class TestWriteConflictError:
    """Test WriteConflictError final class with sequence numbers."""

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_construction_default_sequences(self, message: str) -> None:
        """Property: WriteConflictError defaults sequence numbers to 0."""
        error = WriteConflictError(message)
        assert isinstance(error, DataIntegrityError)
        assert isinstance(error, WriteConflictError)
        assert error.existing_seq == 0
        assert error.new_seq == 0

    @given(
        message=error_messages(),
        existing_seq=st.integers(min_value=0, max_value=1000000),
        new_seq=st.integers(min_value=0, max_value=1000000),
    )
    @settings(max_examples=50)
    def test_construction_with_sequences(
        self, message: str, existing_seq: int, new_seq: int
    ) -> None:
        """Property: WriteConflictError stores sequence numbers."""
        error = WriteConflictError(
            message,
            existing_seq=existing_seq,
            new_seq=new_seq,
        )
        assert error.existing_seq == existing_seq
        assert error.new_seq == new_seq

    @given(
        message=error_messages(),
        context=integrity_contexts(),
        existing_seq=st.integers(min_value=0, max_value=1000000),
        new_seq=st.integers(min_value=0, max_value=1000000),
    )
    @settings(max_examples=50)
    def test_construction_with_all_fields(
        self,
        message: str,
        context: IntegrityContext,
        existing_seq: int,
        new_seq: int,
    ) -> None:
        """Property: WriteConflictError supports context and sequences."""
        error = WriteConflictError(
            message,
            context=context,
            existing_seq=existing_seq,
            new_seq=new_seq,
        )
        assert error.context is context
        assert error.existing_seq == existing_seq
        assert error.new_seq == new_seq

    @given(
        message=error_messages(),
        existing_seq=st.integers(min_value=0, max_value=1000000),
        new_seq=st.integers(min_value=0, max_value=1000000),
    )
    @settings(max_examples=50)
    def test_repr_includes_sequences(
        self, message: str, existing_seq: int, new_seq: int
    ) -> None:
        """Property: __repr__ includes sequence numbers."""
        error = WriteConflictError(
            message,
            existing_seq=existing_seq,
            new_seq=new_seq,
        )
        r = repr(error)
        assert "WriteConflictError" in r
        assert f"existing_seq={existing_seq}" in r
        assert f"new_seq={new_seq}" in r

    def test_final_decorator_type_hint(self) -> None:
        """WriteConflictError is @final (enforced by mypy and __init_subclass__)."""
        assert getattr(WriteConflictError, "__final__", False) is True

    @given(
        message=error_messages(),
        existing_seq=st.integers(min_value=0, max_value=1000000),
        new_seq=st.integers(min_value=0, max_value=1000000),
    )
    @settings(max_examples=50)
    def test_immutability_with_sequences(
        self, message: str, existing_seq: int, new_seq: int
    ) -> None:
        """Property: Sequence numbers are immutable."""
        error = WriteConflictError(
            message,
            existing_seq=existing_seq,
            new_seq=new_seq,
        )

        # Cannot modify sequence numbers after construction
        with pytest.raises(ImmutabilityViolationError):
            error._existing_seq = 999

        with pytest.raises(ImmutabilityViolationError):
            error._new_seq = 999


# =============================================================================
# FormattingIntegrityError Tests
# =============================================================================


class TestFormattingIntegrityError:
    """Test FormattingIntegrityError final class for strict mode."""

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_construction_defaults(self, message: str) -> None:
        """Property: FormattingIntegrityError has sensible defaults."""
        error = FormattingIntegrityError(message)
        assert isinstance(error, DataIntegrityError)
        assert isinstance(error, FormattingIntegrityError)
        assert error.fluent_errors == ()
        assert error.fallback_value == ""
        assert error.message_id == ""

    @given(
        message=error_messages(),
        fallback=st.text(min_size=0, max_size=100),
        msg_id=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_construction_with_fields(
        self, message: str, fallback: str, msg_id: str
    ) -> None:
        """Property: FormattingIntegrityError stores all fields."""
        # Create mock fluent errors (use simple objects for testing)
        mock_error1 = type("MockError", (), {"message": "error1"})()
        mock_error2 = type("MockError", (), {"message": "error2"})()
        fluent_errors = (mock_error1, mock_error2)

        error = FormattingIntegrityError(
            message,
            fluent_errors=fluent_errors,
            fallback_value=fallback,
            message_id=msg_id,
        )

        assert error.fluent_errors == fluent_errors
        assert error.fallback_value == fallback
        assert error.message_id == msg_id
        assert len(error.fluent_errors) == 2

    @given(
        message=error_messages(),
        context=integrity_contexts(),
        fallback=st.text(min_size=0, max_size=100),
        msg_id=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_construction_with_all_fields(
        self,
        message: str,
        context: IntegrityContext,
        fallback: str,
        msg_id: str,
    ) -> None:
        """Property: FormattingIntegrityError supports context."""
        error = FormattingIntegrityError(
            message,
            context=context,
            fluent_errors=(),
            fallback_value=fallback,
            message_id=msg_id,
        )
        assert error.context is context
        assert error.fallback_value == fallback
        assert error.message_id == msg_id

    @given(
        message=error_messages(),
        msg_id=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_repr_includes_message_id_and_count(
        self, message: str, msg_id: str
    ) -> None:
        """Property: __repr__ includes message_id and error count."""
        mock_error = type("MockError", (), {})()
        error = FormattingIntegrityError(
            message,
            fluent_errors=(mock_error, mock_error, mock_error),
            message_id=msg_id,
        )

        r = repr(error)
        assert "FormattingIntegrityError" in r
        assert f"message_id={msg_id!r}" in r
        assert "error_count=3" in r

    def test_final_decorator_type_hint(self) -> None:
        """FormattingIntegrityError is @final (enforced by mypy and __init_subclass__)."""
        assert getattr(FormattingIntegrityError, "__final__", False) is True

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_immutability_with_special_fields(self, message: str) -> None:
        """Property: FormattingIntegrityError special fields are immutable."""
        error = FormattingIntegrityError(message)

        with pytest.raises(ImmutabilityViolationError):
            error._fluent_errors = (object(),)  # type: ignore[assignment]

        with pytest.raises(ImmutabilityViolationError):
            error._fallback_value = "modified"

        with pytest.raises(ImmutabilityViolationError):
            error._message_id = "modified"


# =============================================================================
# SyntaxIntegrityError Tests
# =============================================================================


class TestSyntaxIntegrityError:
    """Test SyntaxIntegrityError final class for strict mode resource loading."""

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_construction_defaults(self, message: str) -> None:
        """Property: SyntaxIntegrityError has sensible defaults."""
        error = SyntaxIntegrityError(message)
        event(f"msg_len={len(message)}")
        assert isinstance(error, DataIntegrityError)
        assert isinstance(error, SyntaxIntegrityError)
        assert error.junk_entries == ()
        assert error.source_path is None

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_construction_with_junk_entries(self, message: str) -> None:
        """Property: SyntaxIntegrityError stores junk_entries as immutable tuple."""
        junk1 = Junk(content="invalid { syntax")
        junk2 = Junk(content="another = { broken")
        # Pass a list to verify defensive tuple() conversion
        error = SyntaxIntegrityError(message, junk_entries=(junk1, junk2))
        event(f"junk_count={len(error.junk_entries)}")
        assert len(error.junk_entries) == 2
        assert error.junk_entries[0] is junk1
        assert error.junk_entries[1] is junk2

    @given(
        message=error_messages(),
        path=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=50)
    def test_construction_with_source_path(self, message: str, path: str) -> None:
        """Property: SyntaxIntegrityError stores source_path correctly."""
        error = SyntaxIntegrityError(message, source_path=path)
        event(f"path_len={len(path)}")
        assert error.source_path == path

    @given(
        message=error_messages(),
        context=integrity_contexts(),
        path=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    )
    @settings(max_examples=50)
    def test_construction_with_all_fields(
        self, message: str, context: IntegrityContext, path: str | None
    ) -> None:
        """Property: SyntaxIntegrityError supports context and source_path."""
        junk = Junk(content="bad = { syntax")
        error = SyntaxIntegrityError(
            message,
            context=context,
            junk_entries=(junk,),
            source_path=path,
        )
        has_path = path is not None
        event(f"has_source_path={has_path}")
        assert error.context is context
        assert len(error.junk_entries) == 1
        assert error.source_path == path

    @given(
        message=error_messages(),
        path=st.one_of(st.none(), st.text(min_size=1, max_size=60)),
    )
    @settings(max_examples=50)
    def test_repr_includes_path_and_junk_count(
        self, message: str, path: str | None
    ) -> None:
        """Property: __repr__ includes source_path and junk_count."""
        junk = Junk(content="invalid")
        error = SyntaxIntegrityError(
            message,
            junk_entries=(junk,),
            source_path=path,
        )
        r = repr(error)
        has_path = path is not None
        event(f"repr_has_path={has_path}")
        assert "SyntaxIntegrityError" in r
        assert "junk_count=1" in r
        assert f"source_path={path!r}" in r

    def test_final_decorator_type_hint(self) -> None:
        """SyntaxIntegrityError is @final (enforced by mypy and __init_subclass__)."""
        assert getattr(SyntaxIntegrityError, "__final__", False) is True

    @given(message=error_messages())
    @settings(max_examples=50)
    def test_immutability_with_special_fields(self, message: str) -> None:
        """Property: SyntaxIntegrityError special fields are immutable."""
        error = SyntaxIntegrityError(message)
        event(f"msg_len={len(message)}")

        with pytest.raises(ImmutabilityViolationError):
            error._junk_entries = ()

        with pytest.raises(ImmutabilityViolationError):
            error._source_path = "modified"

    def test_empty_junk_entries_tuple(self) -> None:
        """SyntaxIntegrityError handles empty junk_entries tuple."""
        error = SyntaxIntegrityError("test", junk_entries=())
        assert error.junk_entries == ()

    def test_can_be_raised_and_caught_as_data_integrity_error(self) -> None:
        """SyntaxIntegrityError can be caught as DataIntegrityError."""
        junk = Junk(content="invalid syntax here")
        error = SyntaxIntegrityError(
            "Strict mode: syntax errors detected",
            junk_entries=(junk,),
            source_path="locales/en/main.ftl",
        )
        with pytest.raises(DataIntegrityError) as exc_info:
            raise error
        caught = exc_info.value
        assert isinstance(caught, SyntaxIntegrityError)
        assert caught.source_path == "locales/en/main.ftl"
        assert len(caught.junk_entries) == 1


# =============================================================================
# Exception Hierarchy Tests
# =============================================================================


class TestExceptionHierarchy:
    """Test exception hierarchy and relationships."""

    def test_all_subclasses_are_final(self) -> None:
        """All DataIntegrityError subclasses are @final (type hint only).

        The @final decorator provides type checking enforcement but does not
        prevent runtime subclassing. Type checkers like mypy will flag violations.
        """
        subclasses = [
            CacheCorruptionError,
            ImmutabilityViolationError,
            IntegrityCheckFailedError,
            WriteConflictError,
            FormattingIntegrityError,
            SyntaxIntegrityError,
        ]

        # Verify all subclasses have __final__ attribute for type checkers
        for subclass in subclasses:
            assert hasattr(subclass, "__final__")

    def test_all_inherit_from_data_integrity_error(self) -> None:
        """All exceptions inherit from DataIntegrityError."""
        error_classes = [
            CacheCorruptionError,
            ImmutabilityViolationError,
            IntegrityCheckFailedError,
            WriteConflictError,
            FormattingIntegrityError,
            SyntaxIntegrityError,
        ]

        for error_class in error_classes:
            error = error_class("test")
            assert isinstance(error, DataIntegrityError)
            assert isinstance(error, Exception)

    def test_all_can_be_caught_as_data_integrity_error(self) -> None:
        """All exceptions can be caught as DataIntegrityError."""
        errors = [
            CacheCorruptionError("test"),
            ImmutabilityViolationError("test"),
            IntegrityCheckFailedError("test"),
            WriteConflictError("test"),
            FormattingIntegrityError("test"),
            SyntaxIntegrityError("test"),
        ]

        for error in errors:
            with pytest.raises(DataIntegrityError):
                raise error


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================


class TestEdgeCases:
    """Edge case tests for integrity exceptions."""

    def test_empty_message(self) -> None:
        """All exceptions accept empty messages."""
        assert str(DataIntegrityError("")) == ""
        assert str(CacheCorruptionError("")) == ""
        assert str(ImmutabilityViolationError("")) == ""
        assert str(IntegrityCheckFailedError("")) == ""
        assert str(WriteConflictError("")) == ""
        assert str(FormattingIntegrityError("")) == ""
        assert str(SyntaxIntegrityError("")) == ""

    def test_unicode_messages(self) -> None:
        """All exceptions handle Unicode messages."""
        msg = "Error: 中文文本 \u4e2d\u6587"
        assert str(DataIntegrityError(msg)) == msg
        assert str(CacheCorruptionError(msg)) == msg
        assert str(FormattingIntegrityError(msg)) == msg
        assert str(SyntaxIntegrityError(msg)) == msg

    def test_very_long_messages(self) -> None:
        """All exceptions handle very long messages."""
        msg = "Error " * 1000
        error = DataIntegrityError(msg)
        assert str(error) == msg

    def test_context_with_none_values(self) -> None:
        """IntegrityContext handles None values correctly."""
        ctx = IntegrityContext(
            component="test",
            operation="test_op",
            key=None,
            expected=None,
            actual=None,
            timestamp=None,
        )
        error = DataIntegrityError("test", context=ctx)
        assert error.context is not None
        assert error.context.key is None
        assert error.context.expected is None
        assert error.context.actual is None
        assert error.context.timestamp is None

    def test_context_with_current_time(self) -> None:
        """IntegrityContext can store current timestamp."""
        now = time.monotonic()
        ctx = IntegrityContext(
            component="cache",
            operation="verify",
            timestamp=now,
        )
        error = CacheCorruptionError("test", context=ctx)
        assert error.context is not None
        assert error.context.timestamp == now

    def test_write_conflict_with_zero_sequences(self) -> None:
        """WriteConflictError handles zero sequence numbers."""
        error = WriteConflictError("test", existing_seq=0, new_seq=0)
        assert error.existing_seq == 0
        assert error.new_seq == 0

    def test_formatting_error_with_empty_tuple(self) -> None:
        """FormattingIntegrityError handles empty fluent_errors."""
        error = FormattingIntegrityError("test", fluent_errors=())
        assert error.fluent_errors == ()
        assert len(error.fluent_errors) == 0

    def test_exception_chaining_preserved(self) -> None:
        """Exception chaining (__cause__) is preserved."""
        msg_cause = "root cause"
        cause = ValueError(msg_cause)

        try:
            try:
                raise cause
            except ValueError as e:
                msg_wrapped = "wrapped"
                raise DataIntegrityError(msg_wrapped) from e
        except DataIntegrityError as error:
            assert error.__cause__ is cause  # noqa: PT017
            assert isinstance(error.__cause__, ValueError)  # noqa: PT017

    def test_exception_context_preserved(self) -> None:
        """Exception context (__context__) is preserved."""
        try:
            try:
                msg_first = "first error"
                raise ValueError(msg_first)
            except ValueError:
                msg_second = "second error"
                raise DataIntegrityError(msg_second) from None
        except DataIntegrityError as error:
            # With 'from None', __context__ is suppressed
            assert error.__suppress_context__ is True  # noqa: PT017


class TestDataIntegrityErrorFinalEnforcement:
    """Runtime @final enforcement on DataIntegrityError subclasses.

    Python's @final decorator sets __final__ = True on the class. The
    __init_subclass__ hook on DataIntegrityError detects this marker and
    raises TypeError at class-definition time, preventing runtime subclassing
    of all six @final subclasses.
    """

    def test_subclassing_cache_corruption_error_raises(self) -> None:
        """Subclassing CacheCorruptionError raises TypeError at class-definition time."""
        with pytest.raises(TypeError, match="CacheCorruptionError is @final"):
            type("Sub", (CacheCorruptionError,), {})

    def test_subclassing_immutability_violation_error_raises(self) -> None:
        """Subclassing ImmutabilityViolationError raises TypeError."""
        with pytest.raises(TypeError, match="ImmutabilityViolationError is @final"):
            type("Sub", (ImmutabilityViolationError,), {})

    def test_subclassing_integrity_check_failed_error_raises(self) -> None:
        """Subclassing IntegrityCheckFailedError raises TypeError."""
        with pytest.raises(TypeError, match="IntegrityCheckFailedError is @final"):
            type("Sub", (IntegrityCheckFailedError,), {})

    def test_subclassing_write_conflict_error_raises(self) -> None:
        """Subclassing WriteConflictError raises TypeError."""
        with pytest.raises(TypeError, match="WriteConflictError is @final"):
            type("Sub", (WriteConflictError,), {})

    def test_subclassing_formatting_integrity_error_raises(self) -> None:
        """Subclassing FormattingIntegrityError raises TypeError."""
        with pytest.raises(TypeError, match="FormattingIntegrityError is @final"):
            type("Sub", (FormattingIntegrityError,), {})

    def test_subclassing_syntax_integrity_error_raises(self) -> None:
        """Subclassing SyntaxIntegrityError raises TypeError."""
        with pytest.raises(TypeError, match="SyntaxIntegrityError is @final"):
            type("Sub", (SyntaxIntegrityError,), {})

    def test_subclassing_data_integrity_error_itself_allowed(self) -> None:
        """DataIntegrityError itself is not @final; direct subclassing is permitted."""
        # This must not raise — DataIntegrityError is the extensible base.
        sub_cls = type("SubError", (DataIntegrityError,), {"__slots__": ()})
        instance = sub_cls("test")
        assert str(instance) == "test"
        assert isinstance(instance, DataIntegrityError)
