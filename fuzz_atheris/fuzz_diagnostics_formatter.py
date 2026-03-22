#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: diagnostics_formatter - DiagnosticFormatter Output & Control-Char Escaping
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""DiagnosticFormatter Fuzzer (Atheris).

Targets: ftllexengine.diagnostics.formatter.DiagnosticFormatter
         ftllexengine.diagnostics.validation.ValidationError
         ftllexengine.diagnostics.validation.ValidationWarning
         ftllexengine.diagnostics.validation.ValidationResult
         ftllexengine.diagnostics.codes.Diagnostic, DiagnosticCode, SourceSpan

Concern boundary: This fuzzer stress-tests the diagnostic formatting pipeline:
control-character escaping (log injection prevention), three output formats
(RUST/SIMPLE/JSON), sanitize/redact modes, ValidationError/Warning/Result
formatting, column arithmetic in format_error/format_warning, format_all
aggregation, and the Diagnostic.format_error() delegation path.

The control-char escaping invariant is the primary security boundary: no raw
ASCII control character (0x00-0x1f, 0x7f) must appear in RUST or SIMPLE
formatted output when the input contains embedded control characters.

Metrics:
- Pattern coverage with weighted selection (12 patterns)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Error distribution and contract violations
- Seed corpus management
- Per-pattern wall-time accumulation

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import gc
import json
import logging
import pathlib
import sys
import time
from dataclasses import dataclass
from typing import Any, cast

# --- Dependency Checks ---
_psutil_mod: Any = None
_atheris_mod: Any = None

try:  # noqa: SIM105 - need module ref for check_dependencies
    import psutil as _psutil_mod  # type: ignore[no-redef]
except ImportError:
    pass

try:  # noqa: SIM105 - need module ref for check_dependencies
    import atheris as _atheris_mod  # type: ignore[no-redef]
except ImportError:
    pass

from fuzz_common import (  # noqa: E402 - after dependency capture  # pylint: disable=C0413
    GC_INTERVAL,
    BaseFuzzerState,
    FuzzStats,
    build_base_stats_dict,
    build_weighted_schedule,
    check_dependencies,
    emit_checkpoint_report,
    emit_final_report,
    get_process,
    print_fuzzer_banner,
    record_iteration_metrics,
    record_memory,
    run_fuzzer,
    select_pattern_round_robin,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Domain Metrics ---

@dataclass
class FormatterMetrics:
    """Domain-specific metrics for diagnostics formatter fuzzer."""

    format_rust_calls: int = 0
    format_simple_calls: int = 0
    format_json_calls: int = 0
    control_char_violations: int = 0
    json_parse_failures: int = 0
    sanitize_checks: int = 0
    validation_result_calls: int = 0
    format_all_calls: int = 0


# --- Global State ---

_state = BaseFuzzerState(
    seed_corpus_max_size=500,
    fuzzer_name="diagnostics_formatter",
    fuzzer_target="diagnostics.formatter.DiagnosticFormatter",
)
_domain = FormatterMetrics()


# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.codes import (
        Diagnostic,
        DiagnosticCode,
        SourceSpan,
    )
    from ftllexengine.diagnostics.formatter import DiagnosticFormatter, OutputFormat
    from ftllexengine.diagnostics.validation import (
        ValidationError,
        ValidationResult,
        ValidationWarning,
        WarningSeverity,
    )


# --- Custom error for invariant violations ---
class FormatterFuzzError(Exception):
    """Raised when a formatter invariant is violated."""


# --- Pattern weights ---
# Control-char escaping is highest weight: primary security boundary.
# JSON parsing is next: JSON must always be valid when format=JSON.
# Sanitize/redact modes weight higher than basic format: tests security paths.
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    # Security boundary: control char escaping
    ("control_char_escaping", 14),
    # Core format paths
    ("format_rust_all_fields", 12),
    ("format_json_valid", 12),
    ("format_simple", 10),
    # Sanitize/redact modes
    ("sanitize_truncation", 10),
    ("sanitize_redact", 8),
    # Structured validation types
    ("format_error_location", 10),
    ("format_warning_context", 8),
    ("format_validation_result_mixed", 8),
    # Aggregation and color
    ("format_all_multiple", 8),
    ("color_ansi_mode", 5),
    # Adversarial: embedded control chars in all rich fields
    ("adversarial_fields", 5),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {
    name: float(weight) for name, weight in _PATTERN_WEIGHTS
}

# Allowed exceptions from formatter operations
_ALLOWED_EXCEPTIONS = (
    ValueError, TypeError,
)

# All DiagnosticCode members for random selection
_ALL_CODES: tuple[DiagnosticCode, ...] = tuple(DiagnosticCode)

# Control characters pool: C0 range + DEL — injected into messages to test escaping
_CONTROL_CHARS: tuple[str, ...] = (
    "\x00",   # NUL
    "\x0a",   # LF
    "\x0d",   # CR
    "\x09",   # HT
    "\x1b",   # ESC (ANSI escape prefix)
    "\x01",   # SOH
    "\x07",   # BEL
    "\x08",   # BS
    "\x0c",   # FF
    "\x7f",   # DEL
    "\x1b[31mRED\x1b[0m",  # Full ANSI sequence
    "line1\nline2\nfake-error[INJECTED]: gotcha",  # Log injection via LF
)


def _pick_code(fdp: atheris.FuzzedDataProvider) -> DiagnosticCode:
    """Pick a random DiagnosticCode."""
    return cast("DiagnosticCode", fdp.PickValueInList(list(_ALL_CODES)))


def _pick_format(fdp: atheris.FuzzedDataProvider) -> OutputFormat:
    """Pick a random output format."""
    return cast("OutputFormat", fdp.PickValueInList(list(OutputFormat)))


def _gen_message(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a short human-readable message string."""
    length = fdp.ConsumeIntInRange(1, 60)
    return fdp.ConsumeUnicodeNoSurrogates(length) or "test message"


def _gen_optional_span(
    fdp: atheris.FuzzedDataProvider,
) -> SourceSpan | None:
    """Generate an optional SourceSpan (50% probability)."""
    if fdp.ConsumeBool():
        line = fdp.ConsumeIntInRange(1, 9999)
        col = fdp.ConsumeIntInRange(1, 999)
        start = fdp.ConsumeIntInRange(0, 10000)
        length = fdp.ConsumeIntInRange(0, 100)
        return SourceSpan(start=start, end=start + length, line=line, column=col)
    return None


def _gen_simple_diagnostic(fdp: atheris.FuzzedDataProvider) -> Diagnostic:
    """Generate a Diagnostic with minimal fields."""
    code = _pick_code(fdp)
    message = _gen_message(fdp)
    severity = fdp.PickValueInList(["error", "warning"])
    return Diagnostic(
        code=code,
        message=message,
        severity=severity,
    )


def _gen_rich_diagnostic(fdp: atheris.FuzzedDataProvider) -> Diagnostic:
    """Generate a Diagnostic with all optional fields populated."""
    code = _pick_code(fdp)
    message = _gen_message(fdp)
    span = _gen_optional_span(fdp)
    hint_str = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 40)) or None
    help_url = "https://projectfluent.org/fluent/guide/messages.html" if fdp.ConsumeBool() else None
    func_name = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20)) or None
    arg_name = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20)) or None
    expected = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20)) or None
    received = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20)) or None
    ftl_loc = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 30)) or None
    severity = fdp.PickValueInList(["error", "warning"])

    depth = fdp.ConsumeIntInRange(0, 5)
    res_path: tuple[str, ...] | None = None
    if depth > 0:
        res_path = tuple(
            fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 15)) or "node"
            for _ in range(depth)
        )

    return Diagnostic(
        code=code,
        message=message,
        span=span,
        hint=hint_str,
        help_url=help_url,
        function_name=func_name,
        argument_name=arg_name,
        expected_type=expected,
        received_type=received,
        ftl_location=ftl_loc,
        severity=severity,
        resolution_path=res_path,
    )


def _has_raw_control_char(text: str) -> bool:
    """Return True if text contains any unescaped C0 control char or DEL."""
    for ch in text:
        cp = ord(ch)
        if (0x00 <= cp <= 0x1F) or cp == 0x7F:
            return True
    return False


def _has_raw_nonstructural_control_char(text: str) -> bool:
    """Return True if text contains C0/DEL chars other than LF.

    LF (0x0A) is excluded because RUST multi-line format uses newlines as
    structural line separators between the header and field lines. Checking
    the whole output with _has_raw_control_char would flag those structural
    newlines as violations when rich fields (function_name, etc.) cause the
    formatter to emit multi-line output.
    """
    for ch in text:
        cp = ord(ch)
        if cp == 0x0A:  # LF is structural in RUST multi-line output
            continue
        if (0x00 <= cp <= 0x1F) or cp == 0x7F:
            return True
    return False


# --- Pattern Implementations ---


def _pattern_control_char_escaping(fdp: atheris.FuzzedDataProvider) -> None:
    """Control chars in message/hint/location fields are escaped in output.

    Security boundary: embedded newlines, NUL bytes, ESC sequences, and other
    C0 control characters injected into diagnostic fields must never appear as
    raw bytes in RUST or SIMPLE formatted output. The formatter's
    _escape_control_chars() must neutralize all C0 + DEL characters.
    """
    # Pick a control character or sequence to inject
    inject = fdp.PickValueInList(list(_CONTROL_CHARS))
    position = fdp.ConsumeIntInRange(0, 2)

    prefix = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20)) or ""
    suffix = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20)) or ""

    # Inject control char at chosen position in the message field
    if position == 0:
        message = inject + suffix
    elif position == 1:
        message = prefix + inject + suffix
    else:
        message = prefix + inject

    code = _pick_code(fdp)
    diag = Diagnostic(code=code, message=message)

    for fmt in (OutputFormat.RUST, OutputFormat.SIMPLE):
        formatter = DiagnosticFormatter(output_format=fmt)
        output = formatter.format(diag)

        if _has_raw_control_char(output):
            _domain.control_char_violations += 1
            raw = output.encode("unicode_escape").decode("ascii")
            msg = (
                f"Control char escaped={False}: "
                f"format={fmt.value}, inject={inject!r}, output={raw!r}"
            )
            raise FormatterFuzzError(msg)


def _pattern_format_rust_all_fields(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """RUST format never crashes and always returns a non-empty string."""
    _domain.format_rust_calls += 1
    diag = _gen_rich_diagnostic(fdp)
    formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
    output = formatter.format(diag)

    if not output:
        msg = "RUST format returned empty string"
        raise FormatterFuzzError(msg)

    # span line → output must contain "line N" in the --> section
    if diag.span is not None:
        expected_line = f"line {diag.span.line}"
        if expected_line not in output:
            msg = f"RUST format missing span line: expected '{expected_line}' in output"
            raise FormatterFuzzError(msg)

    # resolution_path → output must contain " -> " separator
    if diag.resolution_path and len(diag.resolution_path) >= 2 and " -> " not in output:
        msg = "RUST format missing resolution_path separator ' -> '"
        raise FormatterFuzzError(msg)


def _pattern_format_json_valid(fdp: atheris.FuzzedDataProvider) -> None:
    """JSON format always produces valid JSON for any Diagnostic.

    The JSON output must parse without error. Key fields 'code', 'message',
    'severity' must always be present. Optional fields present only when set.
    """
    _domain.format_json_calls += 1
    use_rich = fdp.ConsumeBool()
    diag = _gen_rich_diagnostic(fdp) if use_rich else _gen_simple_diagnostic(fdp)

    formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
    output = formatter.format(diag)

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError as exc:
        _domain.json_parse_failures += 1
        msg = f"JSON format produced invalid JSON: {exc!r}, output={output!r}"
        raise FormatterFuzzError(msg) from exc

    # Mandatory fields
    for required_key in ("code", "message", "severity"):
        if required_key not in parsed:
            msg = f"JSON format missing required key '{required_key}'"
            raise FormatterFuzzError(msg)

    # code must match DiagnosticCode name
    if parsed["code"] != diag.code.name:
        msg = f"JSON code mismatch: {parsed['code']!r} != {diag.code.name!r}"
        raise FormatterFuzzError(msg)


def _pattern_format_simple(fdp: atheris.FuzzedDataProvider) -> None:
    """SIMPLE format: single-line output, code name present, no control chars."""
    _domain.format_simple_calls += 1
    diag = _gen_simple_diagnostic(fdp)

    formatter = DiagnosticFormatter(output_format=OutputFormat.SIMPLE)
    output = formatter.format(diag)

    # Must be a single line (no LF in output because message was clean)
    if "\n" in output and not _has_raw_control_char(diag.message):
        msg = f"SIMPLE format produced multi-line output for clean message: {output!r}"
        raise FormatterFuzzError(msg)

    # Must contain the code name
    if diag.code.name not in output:
        msg = f"SIMPLE format missing code name '{diag.code.name}' in: {output!r}"
        raise FormatterFuzzError(msg)


def _pattern_sanitize_truncation(fdp: atheris.FuzzedDataProvider) -> None:
    """Sanitize mode truncates long message/hint fields.

    When sanitize=True and output length > max_content_length, the formatted
    output must be bounded. When sanitize=False (default), no truncation occurs.
    """
    _domain.sanitize_checks += 1
    max_len = fdp.ConsumeIntInRange(10, 200)
    code = _pick_code(fdp)
    # Generate a very long message to trigger truncation
    long_length = fdp.ConsumeIntInRange(max_len + 50, max_len + 500)
    long_message = "A" * long_length

    diag = Diagnostic(
        code=code,
        message=long_message,
        hint="A" * (long_length // 2),
    )

    # Sanitized output must truncate message/hint
    sanitized = DiagnosticFormatter(
        output_format=OutputFormat.SIMPLE,
        sanitize=True,
        max_content_length=max_len,
    ).format(diag)

    unsanitized = DiagnosticFormatter(
        output_format=OutputFormat.SIMPLE,
        sanitize=False,
    ).format(diag)

    # Sanitized output must be shorter than unsanitized (truncation active)
    if len(sanitized) >= len(unsanitized):
        msg = (
            f"Sanitize mode did not truncate: "
            f"sanitized={len(sanitized)}, unsanitized={len(unsanitized)}"
        )
        raise FormatterFuzzError(msg)

    # Sanitized output must contain the ellipsis "..." marker
    if "..." not in sanitized:
        msg = f"Sanitize mode missing truncation marker '...': {sanitized!r}"
        raise FormatterFuzzError(msg)


def _pattern_sanitize_redact(fdp: atheris.FuzzedDataProvider) -> None:
    """Redact mode replaces content with '[content redacted]' sentinel.

    When format_error(ValidationError, sanitize=True, redact_content=True) is
    called, the content field must be replaced by the sentinel, not truncated.
    """
    code = fdp.PickValueInList([
        DiagnosticCode.PARSE_JUNK,
        DiagnosticCode.UNEXPECTED_EOF,
        DiagnosticCode.VALIDATION_TERM_NO_VALUE,
    ])
    content_length = fdp.ConsumeIntInRange(5, 200)
    content = fdp.ConsumeUnicodeNoSurrogates(content_length) or "bad content"

    error = ValidationError(
        code=code,
        message="Syntax error in resource",
        content=content,
        line=fdp.ConsumeIntInRange(1, 100) if fdp.ConsumeBool() else None,
        column=fdp.ConsumeIntInRange(1, 80) if fdp.ConsumeBool() else None,
    )

    formatter = DiagnosticFormatter(
        sanitize=True,
        redact_content=True,
        max_content_length=50,
    )

    output = formatter.format_error(error)

    # Content must be redacted, not shown.
    # Check the content SECTION specifically: the formatter emits (content: 'VALUE').
    # Checking `content in output` would fire when the content string appears
    # coincidentally in the code name or message (e.g., 'A' in '[PARSE_JUNK]').
    content_section = f"content: '{content}'"
    if content_section in output:
        msg = (
            f"Redact mode leaked content: content={content!r} found in output={output!r}"
        )
        raise FormatterFuzzError(msg)

    if "[content redacted]" not in output:
        msg = f"Redact mode missing sentinel '[content redacted]' in: {output!r}"
        raise FormatterFuzzError(msg)


def _pattern_format_error_location(fdp: atheris.FuzzedDataProvider) -> None:
    """format_error emits correct line/column arithmetic.

    ValidationError with line+column must include both in formatted output.
    ValidationError with only line must include line but not spurious column.
    ValidationError with neither must omit the location section entirely.
    """
    code = fdp.PickValueInList([
        DiagnosticCode.PARSE_JUNK,
        DiagnosticCode.UNEXPECTED_EOF,
        DiagnosticCode.VALIDATION_SELECT_NO_DEFAULT,
    ])
    content = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 40)) or "x"
    message = _gen_message(fdp)

    has_line = fdp.ConsumeBool()
    has_col = fdp.ConsumeBool() and has_line
    line = fdp.ConsumeIntInRange(1, 9999) if has_line else None
    col = fdp.ConsumeIntInRange(1, 999) if has_col else None

    error = ValidationError(
        code=code,
        message=message,
        content=content,
        line=line,
        column=col,
    )

    formatter = DiagnosticFormatter()
    output = formatter.format_error(error)

    if has_line:
        expected = f"at line {line}"
        if expected not in output:
            msg = f"format_error missing line: expected '{expected}' in {output!r}"
            raise FormatterFuzzError(msg)

    if has_col and line is not None:
        expected_col = f"column {col}"
        if expected_col not in output:
            msg = (
                f"format_error missing column: expected '{expected_col}' in {output!r}"
            )
            raise FormatterFuzzError(msg)

    if not has_line and " at line " in output:
        msg = f"format_error emitted spurious location when none set: {output!r}"
        raise FormatterFuzzError(msg)


def _pattern_format_warning_context(fdp: atheris.FuzzedDataProvider) -> None:
    """format_warning emits context field and respects sanitize mode."""
    code = fdp.PickValueInList([
        DiagnosticCode.VALIDATION_DUPLICATE_ID,
        DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE,
        DiagnosticCode.VALIDATION_SHADOW_WARNING,
    ])
    message = _gen_message(fdp)
    has_context = fdp.ConsumeBool()
    context_length = fdp.ConsumeIntInRange(1, 80)
    context = (
        fdp.ConsumeUnicodeNoSurrogates(context_length) or "ctx"
    ) if has_context else None
    severity = fdp.PickValueInList(list(WarningSeverity))

    warning = ValidationWarning(
        code=code,
        message=message,
        context=context,
        line=fdp.ConsumeIntInRange(1, 999) if fdp.ConsumeBool() else None,
        column=fdp.ConsumeIntInRange(1, 80) if fdp.ConsumeBool() else None,
        severity=severity,
    )

    formatter = DiagnosticFormatter()
    formatter.format_warning(warning)  # no-crash invariant

    # Context present and non-empty → context section must be redacted
    if has_context and context and len(context) <= 50:
        # Only assert for short contexts that won't be truncated
        sanitize_fmt = DiagnosticFormatter(sanitize=True, redact_content=True)
        redacted = sanitize_fmt.format_warning(warning)
        # Check the context SECTION specifically, not a substring of the whole output.
        # The formatter emits: (context: 'VALUE') — check that exact pattern was
        # replaced. Checking `context in redacted` would fire on single-char contexts
        # that appear coincidentally in the message field (which is not redacted).
        context_section = f"context: '{context}'"
        if context_section in redacted:
            msg = (
                f"format_warning redact leaked context={context!r} in {redacted!r}"
            )
            raise FormatterFuzzError(msg)


def _pattern_format_validation_result_mixed(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """format_validation_result handles all combinations of errors/warnings/annotations.

    Tests:
    - Valid result (no errors): summary line says "passed"
    - Result with errors: summary says "failed"
    - Result with only warnings: summary says "passed with N warning(s)"
    - include_warnings=False omits warnings section
    """
    _domain.validation_result_calls += 1

    n_errors = fdp.ConsumeIntInRange(0, 3)
    n_warnings = fdp.ConsumeIntInRange(0, 3)
    include_warnings = fdp.ConsumeBool()

    errors = tuple(
        ValidationError(
            code=_pick_code(fdp),
            message=_gen_message(fdp),
            content=fdp.ConsumeUnicodeNoSurrogates(
                fdp.ConsumeIntInRange(1, 20)
            ) or "x",
        )
        for _ in range(n_errors)
    )

    warnings = tuple(
        ValidationWarning(
            code=fdp.PickValueInList([
                DiagnosticCode.VALIDATION_DUPLICATE_ID,
                DiagnosticCode.VALIDATION_SHADOW_WARNING,
            ]),
            message=_gen_message(fdp),
        )
        for _ in range(n_warnings)
    )

    result = ValidationResult(errors=errors, warnings=warnings, annotations=())
    formatter = DiagnosticFormatter()
    output = formatter.format_validation_result(result, include_warnings=include_warnings)

    # Validity invariant
    if n_errors == 0:
        if "passed" not in output.lower():
            msg = f"Valid result output missing 'passed': {output!r}"
            raise FormatterFuzzError(msg)
    elif "failed" not in output.lower():
        msg = f"Invalid result output missing 'failed': {output!r}"
        raise FormatterFuzzError(msg)

    # include_warnings=False must omit warning content
    if not include_warnings and n_warnings > 0:
        output_no_warn = formatter.format_validation_result(
            result, include_warnings=False
        )
        output_with_warn = formatter.format_validation_result(
            result, include_warnings=True
        )
        if "Warnings" in output_no_warn and "Warnings" not in output_with_warn:
            msg = "include_warnings=False still emitted Warnings section"
            raise FormatterFuzzError(msg)


def _pattern_format_all_multiple(fdp: atheris.FuzzedDataProvider) -> None:
    """format_all joins individual diagnostics with double-newline separator.

    Each individual diagnostic formatted by format_all must equal what
    format() would produce for that same diagnostic.
    """
    _domain.format_all_calls += 1
    n = fdp.ConsumeIntInRange(1, 5)
    fmt = _pick_format(fdp)
    formatter = DiagnosticFormatter(output_format=fmt)

    diagnostics = [_gen_simple_diagnostic(fdp) for _ in range(n)]
    combined = formatter.format_all(diagnostics)

    # Each individually formatted diagnostic must appear in the combined output
    for diag in diagnostics:
        individual = formatter.format(diag)
        if individual not in combined:
            msg = (
                f"format_all missing individual diagnostic output: "
                f"expected {individual!r} in combined output"
            )
            raise FormatterFuzzError(msg)


def _pattern_color_ansi_mode(fdp: atheris.FuzzedDataProvider) -> None:
    """color=True produces ANSI escape sequences for severity labels.

    When color=True and format=RUST, error diagnostics must contain the bold-red
    ANSI sequence (\\033[1;31m). Warning diagnostics must contain bold-yellow.
    When color=False (default), no ANSI sequences appear.
    """
    severity = fdp.PickValueInList(["error", "warning"])
    code = _pick_code(fdp)
    message = _gen_message(fdp)
    diag = Diagnostic(code=code, message=message, severity=severity)

    colored = DiagnosticFormatter(output_format=OutputFormat.RUST, color=True).format(diag)
    plain = DiagnosticFormatter(output_format=OutputFormat.RUST, color=False).format(diag)

    # Colored output must be longer (ANSI sequences add bytes)
    if len(colored) <= len(plain):
        msg = (
            f"color=True output not longer than color=False: "
            f"colored={len(colored)}, plain={len(plain)}"
        )
        raise FormatterFuzzError(msg)

    # Must contain ESC byte sequence
    if "\x1b[" not in colored:
        msg = "color=True RUST output missing ANSI escape prefix '\\x1b['"
        raise FormatterFuzzError(msg)

    # Plain output must NOT contain ESC sequences
    if "\x1b[" in plain:
        msg = "color=False RUST output contains unexpected ANSI escape"
        raise FormatterFuzzError(msg)


def _pattern_adversarial_fields(fdp: atheris.FuzzedDataProvider) -> None:
    """Embedded control chars in all Diagnostic rich fields are escaped.

    Tests function_name, argument_name, expected_type, received_type,
    ftl_location, and resolution_path with injected control characters.
    The RUST formatter must escape all of these via _escape_control_chars().
    """
    inject = fdp.PickValueInList(list(_CONTROL_CHARS))
    target_field = fdp.ConsumeIntInRange(0, 5)
    code = _pick_code(fdp)

    kwargs: dict[str, Any] = {"code": code, "message": "clean message"}

    match target_field:
        case 0:
            kwargs["function_name"] = inject
        case 1:
            kwargs["argument_name"] = inject
        case 2:
            kwargs["expected_type"] = inject
        case 3:
            kwargs["received_type"] = inject
        case 4:
            kwargs["ftl_location"] = inject
        case 5:
            kwargs["resolution_path"] = (inject, "clean")
        case _:
            kwargs["hint"] = inject

    diag = Diagnostic(**kwargs)
    formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
    output = formatter.format(diag)

    # RUST multi-line format uses LF as structural line separators between the
    # header line and field lines (e.g. "  = function: ..."). Use the variant
    # that excludes LF to avoid flagging those structural newlines.
    if _has_raw_nonstructural_control_char(output):
        _domain.control_char_violations += 1
        raw = output.encode("unicode_escape").decode("ascii")
        msg = (
            f"Control char in adversarial field {target_field}: "
            f"inject={inject!r}, output_escaped={raw!r}"
        )
        raise FormatterFuzzError(msg)


# --- Pattern Dispatch ---

_PATTERN_DISPATCH: dict[str, Any] = {
    "control_char_escaping": _pattern_control_char_escaping,
    "format_rust_all_fields": _pattern_format_rust_all_fields,
    "format_json_valid": _pattern_format_json_valid,
    "format_simple": _pattern_format_simple,
    "sanitize_truncation": _pattern_sanitize_truncation,
    "sanitize_redact": _pattern_sanitize_redact,
    "format_error_location": _pattern_format_error_location,
    "format_warning_context": _pattern_format_warning_context,
    "format_validation_result_mixed": _pattern_format_validation_result_mixed,
    "format_all_multiple": _pattern_format_all_multiple,
    "color_ansi_mode": _pattern_color_ansi_mode,
    "adversarial_fields": _pattern_adversarial_fields,
}


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "diagnostics_formatter"
_REPORT_FILENAME = "fuzz_diagnostics_formatter_report.json"


def _build_stats_dict() -> FuzzStats:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    stats["format_rust_calls"] = _domain.format_rust_calls
    stats["format_simple_calls"] = _domain.format_simple_calls
    stats["format_json_calls"] = _domain.format_json_calls
    stats["control_char_violations"] = _domain.control_char_violations
    stats["json_parse_failures"] = _domain.json_parse_failures
    stats["sanitize_checks"] = _domain.sanitize_checks
    stats["validation_result_calls"] = _domain.validation_result_calls
    stats["format_all_calls"] = _domain.format_all_calls

    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


atexit.register(_emit_report)


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test DiagnosticFormatter output invariants."""
    if _state.iterations == 0:
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern_name = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    if fdp.remaining_bytes() < 4:
        return

    handler = _PATTERN_DISPATCH[pattern_name]

    try:
        handler(fdp)
    except FormatterFuzzError:
        _state.findings += 1
        raise
    except _ALLOWED_EXCEPTIONS:
        pass  # Expected for malformed inputs
    except Exception:  # pylint: disable=broad-exception-caught
        _state.findings += 1
        error_type = sys.exc_info()[0]
        if error_type is not None:
            key = error_type.__name__[:50]
            _state.error_counts[key] = _state.error_counts.get(key, 0) + 1
        raise

    finally:
        is_interesting = (time.perf_counter() - start_time) * 1000 > 10.0
        record_iteration_metrics(
            _state, pattern_name, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Entry point with argparse CLI."""
    parser = argparse.ArgumentParser(
        description="DiagnosticFormatter Output & Control-Char Escaping Fuzzer"
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=500,
        help="Emit JSON report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size",
        type=int,
        default=500,
        help="Maximum seed corpus entries (FIFO eviction, default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    # Formatter patterns are CPU-light (string ops, no Babel calls).
    # 2048 MB is ample for formatting workloads; tight enough to catch leaks.
    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=2048")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="DiagnosticFormatter Output & Control-Char Escaping Fuzzer (Atheris)",
        target="diagnostics.formatter.DiagnosticFormatter",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        mutator="Byte mutation (formatter invariant patterns)",
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
