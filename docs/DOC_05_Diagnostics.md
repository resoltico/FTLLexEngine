---
afad: "3.5"
version: "0.164.0"
domain: DIAGNOSTICS
updated: "2026-04-23"
route:
  keywords: [ParserAnnotation, ValidationResult, ValidationError, ValidationWarning, DiagnosticCode, DiagnosticFormatter, OutputFormat, SourceSpan]
  questions: ["what validation result types exist?", "how do I format diagnostics output?", "where are diagnostic codes and source spans documented?"]
---

# Diagnostics Reference

This reference covers validation result types, diagnostic codes, spans, and formatter APIs.
Immutable Fluent errors and integrity exceptions live in [DOC_05_Errors.md](DOC_05_Errors.md).

## `WarningSeverity`

Severity levels for validation warnings.

### Signature
```python
class WarningSeverity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
```

### Constraints
- Import: `from ftllexengine import WarningSeverity`
- Type: `StrEnum`
- Used by: `ValidationWarning.severity`

---

## `ValidationError`

Structured validation error for invalid resource content.

### Signature
```python
@dataclass(frozen=True, slots=True)
class ValidationError:
    code: DiagnosticCode
    message: str
    content: str
    line: int | None = None
    column: int | None = None
```

### Constraints
- Import: `from ftllexengine.diagnostics import ValidationError`
- Produced by: `validate_resource()`
- Formatting helper: `.format()` delegates to `DiagnosticFormatter`
- Security note: `content` may contain source text; use sanitizing formatter options for multi-tenant logs

---

## `ValidationWarning`

Structured semantic warning returned by resource validation.

### Signature
```python
@dataclass(frozen=True, slots=True)
class ValidationWarning:
    code: DiagnosticCode
    message: str
    context: str | None = None
    line: int | None = None
    column: int | None = None
    severity: WarningSeverity = WarningSeverity.WARNING
```

### Constraints
- Import: `from ftllexengine.diagnostics import ValidationWarning`
- Produced by: `validate_resource()`
- Formatting helper: `.format()` delegates to `DiagnosticFormatter`

---

## `ParserAnnotation`

Structural protocol for parser annotations stored inside `ValidationResult.annotations`.

### Signature
```python
class ParserAnnotation(Protocol):
    code: str
    message: str
    arguments: tuple[tuple[str, str], ...] | None
    span: object | None
```

### Constraints
- Import: `from ftllexengine.diagnostics import ParserAnnotation`
- Purpose: allows `ValidationResult` to store parser-produced annotations by structural contract, not one concrete implementation class
- Typical producer: `ftllexengine.syntax.ast.Annotation`

---

## `ValidationResult`

Unified immutable validation result.

### Signature
```python
@dataclass(frozen=True, slots=True)
class ValidationResult:
    errors: tuple[ValidationError, ...]
    warnings: tuple[ValidationWarning, ...]
    annotations: tuple[ParserAnnotation, ...]
```

### Constraints
- Import: `from ftllexengine.diagnostics import ValidationResult`
- Produced by: `validate_resource()`
- Properties: `is_valid`, `error_count`, `warning_count`, `annotation_count`
- Factories: `valid()`, `invalid()`, `from_annotations()`
- Annotation contract: stores any object satisfying `ParserAnnotation`; parser AST `Annotation` nodes are the common implementation
- Formatting helper: `.format()` delegates to `DiagnosticFormatter`

---

## `DiagnosticCode`

Enum of stable diagnostic identifiers.

### Signature
```python
class DiagnosticCode(Enum): ...
```

### Constraints
- Import: `from ftllexengine.diagnostics import DiagnosticCode`
- Coverage: reference, resolution, syntax, parsing, and validation categories
- Stability: intended for programmatic handling and log/search indexing

---

## `SourceSpan`

Immutable source location for diagnostics.

### Signature
```python
@dataclass(frozen=True, slots=True)
class SourceSpan:
    start: int
    end: int
    line: int
    column: int
```

### Constraints
- Import: `from ftllexengine.diagnostics import SourceSpan`
- Semantics: `start`/`end` are character offsets, `line`/`column` are 1-indexed
- Invariants: `start >= 0`, `end >= start`, `line >= 1`, `column >= 1`

---

## `Diagnostic`

Structured diagnostic payload for tool and human consumption.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: DiagnosticCode
    message: str
    span: SourceSpan | None = None
    hint: str | None = None
    help_url: str | None = None
    function_name: str | None = None
    argument_name: str | None = None
    expected_type: str | None = None
    received_type: str | None = None
    ftl_location: str | None = None
    severity: Literal["error", "warning"] = "error"
    resolution_path: tuple[str, ...] | None = None
```

### Constraints
- Import: `from ftllexengine.diagnostics import Diagnostic`
- Purpose: single structured payload for rich error reporting
- Helper: `format_error()` delegates to `DiagnosticFormatter`

---

## `OutputFormat`

Enum of supported diagnostic formatter output styles.

### Signature
```python
class OutputFormat(StrEnum):
    RUST = "rust"
    SIMPLE = "simple"
    JSON = "json"
```

### Constraints
- Import: `from ftllexengine.diagnostics import OutputFormat`
- Type: `StrEnum`
- Used by: `DiagnosticFormatter.output_format`

---

## `DiagnosticFormatter`

Central formatting service for diagnostics and validation output.

### Signature
```python
@dataclass(frozen=True, slots=True)
class DiagnosticFormatter:
    output_format: OutputFormat = OutputFormat.RUST
    sanitize: bool = False
    redact_content: bool = False
    color: bool = False
    max_content_length: int = 100
```

### Constraints
- Import: `from ftllexengine.diagnostics import DiagnosticFormatter`
- Main methods: `format()`, `format_all()`, `format_error()`, `format_warning()`, `format_validation_result()`
- Output styles: Rust-style multi-line, simple one-line, and JSON
- Sanitization: can truncate or redact source-bearing fields before output
