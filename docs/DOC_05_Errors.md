---
afad: "3.3"
version: "0.127.0"
domain: ERRORS
updated: "2026-02-22"
route:
  keywords: [FrozenFluentError, ErrorCategory, FrozenErrorContext, ImmutabilityViolationError, DataIntegrityError, SyntaxIntegrityError, FormattingIntegrityError, ValidationResult, DiagnosticCode, Diagnostic]
  questions: ["what errors can occur?", "how to handle errors?", "what are the error codes?", "how to format diagnostics?", "what exceptions do parsing functions raise?", "how to verify error integrity?", "what is SyntaxIntegrityError?", "what is FormattingIntegrityError?"]
---

# Errors Reference

---

## `ErrorCategory`

Error categorization string enum replacing the exception class hierarchy.

### Signature
```python
class ErrorCategory(StrEnum):
    REFERENCE = "reference"
    RESOLUTION = "resolution"
    CYCLIC = "cyclic"
    PARSE = "parse"
    FORMATTING = "formatting"
```

### Parameters
| Value | Description |
|:------|:------------|
| `REFERENCE` | Unknown message, term, or variable reference. |
| `RESOLUTION` | Runtime resolution failure (depth exceeded, function error). |
| `CYCLIC` | Cyclic reference detected (e.g., `hello = { hello }`). |
| `PARSE` | Bi-directional parsing failure (number, date, currency). |
| `FORMATTING` | Locale-aware formatting failure. |

### Constraints
- Type: `StrEnum` — each member IS a `str`; `ErrorCategory.REFERENCE == "reference"` is `True`
- String repr: `str(ErrorCategory.REFERENCE) == "reference"` (not `"ErrorCategory.REFERENCE"`)
- Value: `.value` is still the plain string (`"reference"`, `"resolution"`, etc.)
- Usage: Check category instead of using isinstance() on subclasses.
- Import: `from ftllexengine.diagnostics import ErrorCategory`

---

## `FrozenFluentError`

Immutable, content-addressable Fluent error for financial-grade data integrity.

### Signature
```python
@final
class FrozenFluentError(Exception):
    def __init__(
        self,
        message: str,
        category: ErrorCategory,
        diagnostic: Diagnostic | None = None,
        context: FrozenErrorContext | None = None,
    ) -> None: ...

    def verify_integrity(self) -> bool: ...

    @property
    def message(self) -> str: ...
    @property
    def category(self) -> ErrorCategory: ...
    @property
    def diagnostic(self) -> Diagnostic | None: ...
    @property
    def context(self) -> FrozenErrorContext | None: ...
    @property
    def content_hash(self) -> bytes: ...
    @property
    def fallback_value(self) -> str: ...
    @property
    def input_value(self) -> str: ...
    @property
    def locale_code(self) -> str: ...
    @property
    def parse_type(self) -> str: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message` | `str` | Y | Human-readable error description. |
| `category` | `ErrorCategory` | Y | Error categorization (replaces subclass hierarchy). |
| `diagnostic` | `Diagnostic \| None` | N | Structured diagnostic information. |
| `context` | `FrozenErrorContext \| None` | N | Additional context for parse/formatting errors. |

### Constraints
- Immutable: All attributes frozen after construction. Mutation raises `ImmutabilityViolationError`.
- Exception Attributes: Python exception mechanism attributes (`__traceback__`, `__context__`, `__cause__`, `__suppress_context__`, `__notes__`) are allowed even after freeze to support exception chaining and Python 3.11+ exception groups.
- Sealed: Cannot be subclassed. Use `ErrorCategory` for classification.
- Content-Addressed: BLAKE2b-128 hash computed at construction for integrity verification.
- Hashable: Can be used in sets and as dict keys. Hash based on content, not identity.
- Convenience Properties: `input_value`, `locale_code`, `parse_type` delegate to `context` (return empty string if context is None).
- Hash Composition: Content hash includes ALL fields for complete audit trail integrity:
  - Core: `message`, `category.value`
  - Diagnostic (if present): `code.name`, `message`, `span` (start/end/line/column), `hint`, `help_url`, `function_name`, `argument_name`, `expected_type`, `received_type`, `ftl_location`, `severity`, `resolution_path`
  - Context (if present): `input_value`, `locale_code`, `parse_type`, `fallback_value`
- Length-Prefixing: All string fields are length-prefixed (4-byte big-endian) before hashing. This prevents collision attacks where `("ab", "c")` and `("a", "bc")` would hash identically.
- Import: `from ftllexengine.diagnostics import FrozenFluentError`

---

## `FrozenFluentError.verify_integrity`

Verify error content hasn't been corrupted.

### Signature
```python
def verify_integrity(self) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: True if content hash matches, False if corrupted.
- Method: Recomputes BLAKE2b-128 hash and compares using constant-time comparison.
- Security: Defense against timing attacks via `hmac.compare_digest()`.

---

## `FrozenErrorContext`

Immutable context for parse/formatting errors.

### Signature
```python
@dataclass(frozen=True, slots=True)
class FrozenErrorContext:
    input_value: str
    locale_code: str
    parse_type: str
    fallback_value: str
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `input_value` | `str` | Y | String that failed parsing/formatting. |
| `locale_code` | `str` | Y | Locale used for parsing/formatting. |
| `parse_type` | `str` | Y | Type (number/decimal/date/datetime/currency). |
| `fallback_value` | `str` | Y | Value to use when formatting fails. |

### Constraints
- Immutable: Frozen dataclass, cannot be modified.
- Usage: Passed to `FrozenFluentError` for PARSE/FORMATTING errors.
- Import: `from ftllexengine.diagnostics import FrozenErrorContext`

---

## `DataIntegrityError`

Base exception for data integrity violations.

### Signature
```python
class DataIntegrityError(Exception):
    def __init__(self, message: str) -> None: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message` | `str` | Y | Error description. |

### Constraints
- Purpose: Base class for integrity-related exceptions.
- Import: `from ftllexengine.integrity import DataIntegrityError`

---

## `ImmutabilityViolationError`

Attempt to mutate an immutable object.

### Signature
```python
class ImmutabilityViolationError(DataIntegrityError):
    def __init__(self, message: str) -> None: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message` | `str` | Y | Description of mutation attempt. |

### Constraints
- Purpose: Raised when code attempts to modify a frozen FrozenFluentError or cache entry.
- Raised By: `FrozenFluentError.__setattr__()`, `FrozenFluentError.__delattr__()`.
- Import: `from ftllexengine.integrity import ImmutabilityViolationError`

---

## `SyntaxIntegrityError`

Syntax errors detected in strict mode during FTL source loading.

### Signature
```python
@final
class SyntaxIntegrityError(DataIntegrityError):
    def __init__(
        self,
        message: str,
        context: IntegrityContext | None = None,
        *,
        junk_entries: tuple[Junk, ...] = (),
        source_path: str | None = None,
    ) -> None: ...

    @property
    def junk_entries(self) -> tuple[Junk, ...]: ...
    @property
    def source_path(self) -> str | None: ...
    @property
    def context(self) -> IntegrityContext | None: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message` | `str` | Y | Human-readable error description. |
| `context` | `IntegrityContext \| None` | N | Structured diagnostic context. |
| `junk_entries` | `tuple[Junk, ...]` | N | Junk AST nodes representing syntax errors. |
| `source_path` | `str \| None` | N | Path to source file for error context. |

### Constraints
- Purpose: Raised by `FluentBundle.add_resource()` in strict mode when syntax errors (Junk entries) are detected.
- Immutable: All attributes frozen after construction. Mutation raises `ImmutabilityViolationError`.
- Sealed: `@final` decorator prevents subclassing.
- Financial: Financial applications require fail-fast behavior. Silent failures during FTL source loading are unacceptable for monetary formatting.
- Import: `from ftllexengine.integrity import SyntaxIntegrityError` or `from ftllexengine import SyntaxIntegrityError`

---

## `FormattingIntegrityError`

Formatting errors detected in strict mode during message formatting.

### Signature
```python
@final
class FormattingIntegrityError(DataIntegrityError):
    def __init__(
        self,
        message: str,
        context: IntegrityContext | None = None,
        *,
        fluent_errors: tuple[FrozenFluentError, ...] = (),
        fallback_value: str = "",
        message_id: str = "",
    ) -> None: ...

    @property
    def fluent_errors(self) -> tuple[FrozenFluentError, ...]: ...
    @property
    def fallback_value(self) -> str: ...
    @property
    def message_id(self) -> str: ...
    @property
    def context(self) -> IntegrityContext | None: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message` | `str` | Y | Human-readable error description. |
| `context` | `IntegrityContext \| None` | N | Structured diagnostic context. |
| `fluent_errors` | `tuple[FrozenFluentError, ...]` | N | Original Fluent errors that triggered exception. |
| `fallback_value` | `str` | N | Fallback value that would have been returned in non-strict mode. |
| `message_id` | `str` | N | Message ID that failed to format. |

### Constraints
- Purpose: Raised by `FluentBundle.format_pattern()` in strict mode when formatting errors occur.
- Immutable: All attributes frozen after construction. Mutation raises `ImmutabilityViolationError`.
- Sealed: `@final` decorator prevents subclassing.
- Financial: Financial applications require fail-fast behavior. Silent fallback values are unacceptable when formatting monetary amounts.
- Import: `from ftllexengine.integrity import FormattingIntegrityError` or `from ftllexengine import FormattingIntegrityError`

---

## `BabelImportError`

### Signature
```python
class BabelImportError(ImportError):
    feature: str

    def __init__(self, feature: str) -> None: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `feature` | `str` | Y | Feature name requiring Babel (e.g., "parse_date"). |

### Constraints
- Purpose: Raised when Babel is required but not installed.
- Behavior: Provides installation instructions in error message.
- Raised by: `parse_number()`, `parse_decimal()`, `parse_date()`, `parse_datetime()`, `parse_currency()`, `select_plural_category()`, `LocaleContext.create()`, `get_cldr_version()`, `get_territory()`, `get_currency()`, `list_territories()`, `list_currencies()`, `get_territory_currencies()`, `is_valid_territory_code()`, `is_valid_currency_code()`.
- Import: `from ftllexengine.core.babel_compat import BabelImportError`

---

## `SerializationValidationError`

### Signature
```python
class SerializationValidationError(ValueError): ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Purpose: AST validation errors during serialization.
- Raised: When `serialize(validate=True)` detects invalid AST.
- Common: Identifier names violating `[a-zA-Z][a-zA-Z0-9_-]*`, duplicate named argument names, named argument values not StringLiteral or NumberLiteral.
- Import: `from ftllexengine.syntax import SerializationValidationError`

---

## `SerializationDepthError`

### Signature
```python
class SerializationDepthError(ValueError): ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Purpose: AST nesting exceeds maximum serialization depth.
- Cause: Adversarial input, malformed AST, or deep Placeable nesting.
- Raised: When AST depth exceeds `max_depth` parameter (default: 100).
- Security: Prevents stack overflow from adversarially constructed ASTs.
- Import: `from ftllexengine.syntax import SerializationDepthError`

---

## `ValidationResult`

### Signature
```python
@dataclass(frozen=True, slots=True)
class ValidationResult:
    errors: tuple[ValidationError, ...]
    warnings: tuple[ValidationWarning, ...]
    annotations: tuple[Annotation, ...]

    @property
    def is_valid(self) -> bool: ...
    @property
    def error_count(self) -> int: ...       # len(self.errors) only
    @property
    def annotation_count(self) -> int: ...  # len(self.annotations) only
    @property
    def warning_count(self) -> int: ...
    @staticmethod
    def valid() -> ValidationResult: ...
    @staticmethod
    def invalid(...) -> ValidationResult: ...
    @staticmethod
    def from_annotations(annotations: tuple[Annotation, ...]) -> ValidationResult: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `errors` | `tuple[ValidationError, ...]` | Y | Syntax validation errors. |
| `warnings` | `tuple[ValidationWarning, ...]` | Y | Semantic warnings. |
| `annotations` | `tuple[Annotation, ...]` | Y | Parser annotations. |

### Constraints
- Return: Immutable validation result.
- State: Frozen dataclass.
- `error_count`: Count of `ValidationError` entries only (syntax errors); does not include annotations.
- `annotation_count`: Count of `Annotation` entries only (parser informational notes); does not include syntax errors.
- `is_valid`: True iff `error_count == 0`; annotations do not affect validity.

---

## `ValidationResult.format`

### Signature
```python
def format(
    self,
    *,
    sanitize: bool = False,
    redact_content: bool = False,
    include_warnings: bool = True,
) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `sanitize` | `bool` | N | Truncate content to prevent information leakage. |
| `redact_content` | `bool` | N | Completely redact content (requires sanitize=True). |
| `include_warnings` | `bool` | N | Include warnings in output (default: True). |

### Constraints
- Return: Formatted string with errors, annotations, optionally warnings.
- Security: Set sanitize=True for multi-tenant applications.

---

## `ValidationError`

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

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `code` | `DiagnosticCode` | Y | Structured error code. |
| `message` | `str` | Y | Error message. |
| `content` | `str` | Y | Unparseable FTL content. |
| `line` | `int \| None` | N | Line number (1-indexed). |
| `column` | `int \| None` | N | Column number (1-indexed). |

### Constraints
- Return: Immutable error record.
- State: Frozen dataclass.
- Code: `DiagnosticCode` enum, not a string. Use `.name` for the string form.

---

## `ValidationError.format`

### Signature
```python
def format(
    self,
    *,
    sanitize: bool = False,
    redact_content: bool = False,
) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `sanitize` | `bool` | N | Truncate content to prevent information leakage. |
| `redact_content` | `bool` | N | Completely redact content (requires sanitize=True). |

### Constraints
- Return: Formatted error string with location and content.
- Security: Set sanitize=True for multi-tenant applications.

---

## `WarningSeverity`

Severity levels for validation warnings.

### Signature
```python
class WarningSeverity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
```

### Parameters
| Value | Description |
|:------|:------------|
| `CRITICAL` | Will cause runtime failure (undefined reference). |
| `WARNING` | May cause issues (duplicate ID, missing value). |
| `INFO` | Informational only (style suggestions). |

### Constraints
- StrEnum: Members ARE strings. `str(WarningSeverity.CRITICAL) == "critical"`
- Usage: Filter warnings by severity in tooling.
- Import: `from ftllexengine.diagnostics import WarningSeverity`

---

## `ValidationWarning`

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

    def format(
        self,
        *,
        sanitize: bool = False,
        redact_content: bool = False,
    ) -> str: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `code` | `DiagnosticCode` | Y | Structured warning code. |
| `message` | `str` | Y | Warning message. |
| `context` | `str \| None` | N | Additional context. |
| `line` | `int \| None` | N | Line number (1-indexed). |
| `column` | `int \| None` | N | Column number (1-indexed). |
| `severity` | `WarningSeverity` | N | Severity level (default: WARNING). |

### Constraints
- Return: Immutable warning record.
- State: Frozen dataclass.
- Code: `DiagnosticCode` enum, not a string. Use `.name` for the string form.
- IDE: Line/column fields enable IDE/LSP integration for warning display.
- Severity: Enables filtering by importance (CRITICAL > WARNING > INFO).

---

## `ValidationWarning.format`

### Signature
```python
def format(
    self,
    *,
    sanitize: bool = False,
    redact_content: bool = False,
) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `sanitize` | `bool` | N | Truncate context to prevent information leakage. |
| `redact_content` | `bool` | N | Completely redact context (requires sanitize=True). |

### Constraints
- Return: Formatted warning string with location and optional context.
- Format: `[code] at line N, column M: message (context: 'ctx')`
- Security: Set sanitize=True for multi-tenant applications.

---

## `DiagnosticCode`

### Signature
```python
class DiagnosticCode(Enum):
    # Reference errors (1000-1999)
    MESSAGE_NOT_FOUND = 1001
    ATTRIBUTE_NOT_FOUND = 1002
    TERM_NOT_FOUND = 1003
    TERM_ATTRIBUTE_NOT_FOUND = 1004
    VARIABLE_NOT_PROVIDED = 1005
    MESSAGE_NO_VALUE = 1006

    # Resolution errors (2000-2999)
    CYCLIC_REFERENCE = 2001
    NO_VARIANTS = 2002
    FUNCTION_NOT_FOUND = 2003
    FUNCTION_FAILED = 2004
    UNKNOWN_EXPRESSION = 2005
    TYPE_MISMATCH = 2006
    INVALID_ARGUMENT = 2007
    ARGUMENT_REQUIRED = 2008
    PATTERN_INVALID = 2009
    MAX_DEPTH_EXCEEDED = 2010
    FUNCTION_ARITY_MISMATCH = 2011
    TERM_POSITIONAL_ARGS_IGNORED = 2012
    PLURAL_SUPPORT_UNAVAILABLE = 2013
    FORMATTING_FAILED = 2014
    EXPANSION_BUDGET_EXCEEDED = 2015

    # Syntax errors (3000-3999)
    UNEXPECTED_EOF = 3001
    # 3002, 3003: not assigned — character/token-level errors are AST Annotation codes
    PARSE_JUNK = 3004
    PARSE_NESTING_DEPTH_EXCEEDED = 3005

    # Parsing errors (4000-4999)
    PARSE_NUMBER_FAILED = 4001
    PARSE_DECIMAL_FAILED = 4002
    PARSE_DATE_FAILED = 4003
    PARSE_DATETIME_FAILED = 4004
    PARSE_CURRENCY_FAILED = 4005
    PARSE_LOCALE_UNKNOWN = 4006
    PARSE_CURRENCY_AMBIGUOUS = 4007
    PARSE_CURRENCY_SYMBOL_UNKNOWN = 4008
    PARSE_AMOUNT_INVALID = 4009
    PARSE_CURRENCY_CODE_INVALID = 4010

    # Validation errors (5000-5099) - Fluent spec semantic validation
    VALIDATION_TERM_NO_VALUE = 5004
    VALIDATION_SELECT_NO_DEFAULT = 5005
    VALIDATION_SELECT_NO_VARIANTS = 5006
    VALIDATION_VARIANT_DUPLICATE = 5007
    VALIDATION_NAMED_ARG_DUPLICATE = 5010

    # Validation warnings (5100-5199) - Resource-level validation
    VALIDATION_PARSE_ERROR = 5100
    VALIDATION_CRITICAL_PARSE_ERROR = 5101
    VALIDATION_DUPLICATE_ID = 5102
    VALIDATION_NO_VALUE_OR_ATTRS = 5103
    VALIDATION_UNDEFINED_REFERENCE = 5104
    VALIDATION_CIRCULAR_REFERENCE = 5105
    VALIDATION_CHAIN_DEPTH_EXCEEDED = 5106
    VALIDATION_DUPLICATE_ATTRIBUTE = 5107
    VALIDATION_SHADOW_WARNING = 5108
    VALIDATION_TERM_POSITIONAL_ARGS = 5109
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Purpose: Unique error code identifiers for diagnostics.
- Ranges: 1000-1999 (reference), 2000-2999 (resolution), 3000-3999 (syntax), 4000-4999 (parsing), 5000-5199 (validation).

---

## `Diagnostic`

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

    def format_error(self) -> str: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `code` | `DiagnosticCode` | Y | Error code. |
| `message` | `str` | Y | Error description. |
| `span` | `SourceSpan \| None` | N | Source location. |
| `hint` | `str \| None` | N | Fix suggestion. |
| `help_url` | `str \| None` | N | Documentation URL. |
| `function_name` | `str \| None` | N | Function where error occurred. |
| `argument_name` | `str \| None` | N | Argument causing error. |
| `expected_type` | `str \| None` | N | Expected type. |
| `received_type` | `str \| None` | N | Actual type received. |
| `ftl_location` | `str \| None` | N | FTL file location. |
| `severity` | `Literal[...]` | N | "error" or "warning". |
| `resolution_path` | `tuple[str, ...] \| None` | N | Resolution stack for debugging nested references. |

### Constraints
- Return: Immutable diagnostic record.
- State: Frozen dataclass.
- Resolution Path: Shows message reference chain (e.g., `("welcome", "greeting", "base")`).

---

## `SourceSpan`

### Signature
```python
@dataclass(frozen=True, slots=True)
class SourceSpan:
    start: int
    end: int
    line: int
    column: int
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `start` | `int` | Y | Start character offset (0-indexed). |
| `end` | `int` | Y | End character offset (exclusive, 0-indexed). |
| `line` | `int` | Y | Line number (1-indexed). |
| `column` | `int` | Y | Column number (1-indexed). |

### Constraints
- Return: Immutable span record.
- State: Frozen dataclass.

---

## `OutputFormat`

### Signature
```python
class OutputFormat(StrEnum):
    RUST = "rust"
    SIMPLE = "simple"
    JSON = "json"
```

### Parameters
| Value | Description |
|:------|:------------|
| `RUST` | Rust compiler-style output with hints and help URLs. |
| `SIMPLE` | Single-line format (code: message). |
| `JSON` | JSON format for tooling integration. |

### Constraints
- StrEnum: Members ARE strings. `str(OutputFormat.RUST) == "rust"`
- Import: `from ftllexengine.diagnostics import OutputFormat`

---

## `DiagnosticFormatter`

### Signature
```python
@dataclass(frozen=True, slots=True)
class DiagnosticFormatter:
    output_format: OutputFormat = OutputFormat.RUST
    sanitize: bool = False
    redact_content: bool = False
    color: bool = False
    max_content_length: int = 100

    def format(self, diagnostic: Diagnostic) -> str: ...
    def format_all(self, diagnostics: Iterable[Diagnostic]) -> str: ...
    def format_validation_result(self, result: ValidationResult) -> str: ...
    def format_error(self, error: ValidationError) -> str: ...
    def format_warning(self, warning: ValidationWarning) -> str: ...
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `output_format` | `OutputFormat` | Output style (rust, simple, json). |
| `sanitize` | `bool` | Truncate content to prevent information leakage. |
| `redact_content` | `bool` | Completely redact content (requires sanitize=True). |
| `color` | `bool` | Enable ANSI color codes (for terminal output). |
| `max_content_length` | `int` | Maximum content length when sanitizing. |

### Constraints
- Return: Immutable formatter instance.
- State: Frozen dataclass.
- Thread: Safe.
- Security: All formatted output passes through `_escape_control_chars()` (full C0 range 0x00–0x1f and DEL 0x7f) to prevent log injection via embedded control characters in diagnostic messages.
- Import: `from ftllexengine.diagnostics import DiagnosticFormatter`

---

## `DiagnosticFormatter.format`

### Signature
```python
def format(self, diagnostic: Diagnostic) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `diagnostic` | `Diagnostic` | Y | Diagnostic to format. |

### Constraints
- Return: Formatted diagnostic string.
- State: Read-only.
- Thread: Safe.

---

## `DiagnosticFormatter.format_all`

### Signature
```python
def format_all(self, diagnostics: Iterable[Diagnostic]) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `diagnostics` | `Iterable[Diagnostic]` | Y | Diagnostics to format. |

### Constraints
- Return: Formatted string with all diagnostics separated by newlines.
- State: Read-only.
- Thread: Safe.

---

## `DiagnosticFormatter.format_validation_result`

### Signature
```python
def format_validation_result(
    self,
    result: ValidationResult,
    *,
    include_warnings: bool = True,
) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `result` | `ValidationResult` | Y | Validation result to format. |
| `include_warnings` | `bool` | N | Include warnings in output (default: True). |

### Constraints
- Return: Formatted string with summary, errors, warnings, and annotations.
- State: Read-only.
- Thread: Safe.

---

## Error Fallback Formats

When resolution errors occur, FTLLexEngine returns readable fallback strings instead of raising exceptions. The fallback format varies by expression type.

### Fallback Format Table

| Expression Type | Fallback Format | Example |
|:----------------|:----------------|:--------|
| `VariableReference` | `{$name}` | `{$count}` |
| `MessageReference` | `{message-id}` | `{welcome}` |
| `TermReference` | `{-term-id}` | `{-brand}` |
| `FunctionReference` | `{FUNC(...)}` | `{NUMBER(...)}` |
| `SelectExpression` | `{{selector} -> ...}` | `{{$count} -> ...}` |
| Unknown expression | `{???}` | `{???}` |

### Constraints
- Fallbacks preserve FTL-like syntax for debugging.
- SelectExpression fallback shows selector context.
- All fallbacks wrapped in braces for visual distinction.

---
