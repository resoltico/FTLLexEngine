"""Tests for the bundle-owned resolution re-entry gate."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from ftllexengine.diagnostics import DiagnosticCode, FrozenFluentError
from ftllexengine.runtime._resolution_gate import ResolutionReentryGate


class TestResolutionReentryGate:
    """Cross-thread custom-function re-entry must be rejected explicitly."""

    def test_blocks_fresh_cross_thread_entry_during_custom_function_scope(self) -> None:
        """A new thread must not bypass the shared resolution budget."""
        gate = ResolutionReentryGate()

        def attempt_reentry() -> None:
            with gate.format_call():
                pass

        with gate.custom_function_scope(), ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(attempt_reentry)
            with pytest.raises(FrozenFluentError) as exc_info:
                future.result()

        diagnostic = exc_info.value.diagnostic
        assert diagnostic is not None
        assert diagnostic.code == DiagnosticCode.REENTRANT_FORMATTING_BLOCKED
        assert "Cross-thread format_pattern() re-entry" in diagnostic.message

    def test_same_session_nested_format_call_is_allowed(self) -> None:
        """Nested work on the same logical formatting session should proceed."""
        gate = ResolutionReentryGate()

        with gate.format_call(), gate.custom_function_scope(), gate.format_call():
            pass
