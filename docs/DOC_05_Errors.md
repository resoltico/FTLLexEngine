---
spec_version: AFAD-v1
project_version: 0.35.0
context: ERRORS
last_updated: 2025-12-26T18:00:00Z
maintainer: claude-opus-4-5
retrieval_hints:
  keywords: [FluentError, FluentSyntaxError, FluentReferenceError, FluentResolutionError, ValidationResult, ValidationError, DiagnosticCode, Diagnostic, SerializationDepthError, SerializationValidationError]
  answers: [what errors can occur, how to handle errors, error codes, validation errors, diagnostic formatting, serialization errors]
  related: [DOC_01_Core.md, DOC_03_Parsing.md]
---

# Errors Reference

---

## Exception Hierarchy

```
FluentError
  FluentSyntaxError
  FluentReferenceError
    FluentCyclicReferenceError
  FluentResolutionError
    DepthLimitExceededError
  FluentParseError
```

---

## `FluentError`

### Signature
```python
class FluentError(Exception):
    diagnostic: Diagnostic | None

    def __init__(self, message: str | Diagnostic) -> None: ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message` | `str \| Diagnostic` | Y | Error message or structured diagnostic. |

### Constraints
- Return: Exception instance.
- State: Stores optional Diagnostic.

---

## `FluentSyntaxError`

### Signature
```python
class FluentSyntaxError(FluentError): ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Purpose: FTL syntax parse errors.
- Behavior: Parser continues after errors (robustness principle).

---

## `FluentReferenceError`

### Signature
```python
class FluentReferenceError(FluentError): ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Purpose: Unknown message or term reference.
- Behavior: Returns message ID as fallback.

---

## `FluentCyclicReferenceError`

### Signature
```python
class FluentCyclicReferenceError(FluentReferenceError): ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Purpose: Cyclic reference detection (e.g., `hello = { hello }`).
- Behavior: Returns message ID as fallback.

---

## `FluentResolutionError`

### Signature
```python
class FluentResolutionError(FluentError): ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Purpose: Runtime resolution errors.
- Behavior: Returns partial result up to error point.

---

## `DepthLimitExceededError`

### Signature
```python
class DepthLimitExceededError(FluentResolutionError): ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Purpose: Maximum expression/nesting depth exceeded.
- Cause: Adversarial input, malformed AST, or deep Placeable nesting.
- Behavior: Raised immediately when limit exceeded.
- Import: `from ftllexengine.runtime.depth_guard import DepthLimitExceededError`
- Version: Added in v0.31.0.

---

## `FluentParseError`

### Signature
```python
class FluentParseError(FluentError):
    input_value: str
    locale_code: str
    parse_type: str

    def __init__(
        self,
        message: str | Diagnostic,
        *,
        input_value: str = "",
        locale_code: str = "",
        parse_type: str = "",
    ) -> None: ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message` | `str \| Diagnostic` | Y | Error message or diagnostic. |
| `input_value` | `str` | N | String that failed to parse. |
| `locale_code` | `str` | N | Locale used for parsing. |
| `parse_type` | `str` | N | Type: number, decimal, date, datetime, currency. |

### Constraints
- Purpose: Bi-directional parsing errors.
- Behavior: Returned in error list, never raised.

---

## `SerializationValidationError`

### Signature
```python
class SerializationValidationError(ValueError): ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Purpose: AST validation errors during serialization.
- Raised: When `serialize(validate=True)` detects invalid AST.
- Common: SelectExpression without exactly one default variant.
- Import: `from ftllexengine.syntax import SerializationValidationError`
- Version: Added in v0.29.0.

---

## `SerializationDepthError`

### Signature
```python
class SerializationDepthError(ValueError): ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Purpose: AST nesting exceeds maximum serialization depth.
- Cause: Adversarial input, malformed AST, or deep Placeable nesting.
- Raised: When AST depth exceeds `max_depth` parameter (default: 100).
- Security: Prevents stack overflow from adversarially constructed ASTs.
- Import: `from ftllexengine.syntax import SerializationDepthError`
- Version: Added in v0.35.0.

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
    def error_count(self) -> int: ...
    @property
    def warning_count(self) -> int: ...
    @staticmethod
    def valid() -> ValidationResult: ...
    @staticmethod
    def invalid(...) -> ValidationResult: ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `errors` | `tuple[ValidationError, ...]` | Y | Syntax validation errors. |
| `warnings` | `tuple[ValidationWarning, ...]` | Y | Semantic warnings. |
| `annotations` | `tuple[Annotation, ...]` | Y | Parser annotations. |

### Constraints
- Return: Immutable validation result.
- State: Frozen dataclass.

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

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `sanitize` | `bool` | N | Truncate content to prevent information leakage. |
| `redact_content` | `bool` | N | Completely redact content (requires sanitize=True). |
| `include_warnings` | `bool` | N | Include warnings in output (default: True). |

### Constraints
- Return: Formatted string with errors, annotations, optionally warnings.
- Security: Set sanitize=True for multi-tenant applications.
- Version: v0.27.0+

---

## `ValidationError`

### Signature
```python
@dataclass(frozen=True, slots=True)
class ValidationError:
    code: str
    message: str
    content: str
    line: int | None = None
    column: int | None = None
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `code` | `str` | Y | Error code (e.g., "parse-error"). |
| `message` | `str` | Y | Error message. |
| `content` | `str` | Y | Unparseable FTL content. |
| `line` | `int \| None` | N | Line number (1-indexed). |
| `column` | `int \| None` | N | Column number (1-indexed). |

### Constraints
- Return: Immutable error record.
- State: Frozen dataclass.

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

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `sanitize` | `bool` | N | Truncate content to prevent information leakage. |
| `redact_content` | `bool` | N | Completely redact content (requires sanitize=True). |

### Constraints
- Return: Formatted error string with location and content.
- Security: Set sanitize=True for multi-tenant applications.
- Version: v0.27.0+

---

## `ValidationWarning`

### Signature
```python
@dataclass(frozen=True, slots=True)
class ValidationWarning:
    code: str
    message: str
    context: str | None = None
    line: int | None = None
    column: int | None = None

    def format(self) -> str: ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `code` | `str` | Y | Warning code (e.g., "duplicate-id"). |
| `message` | `str` | Y | Warning message. |
| `context` | `str \| None` | N | Additional context. |
| `line` | `int \| None` | N | Line number (1-indexed). |
| `column` | `int \| None` | N | Column number (1-indexed). |

### Constraints
- Return: Immutable warning record.
- State: Frozen dataclass.
- IDE: Line/column fields enable IDE/LSP integration for warning display.
- Version: line/column fields added in v0.30.0.

---

## `ValidationWarning.format`

### Signature
```python
def format(self) -> str:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Formatted warning string with location (if available).
- Format: `[code] at line N, column M: message (context: 'ctx')`
- Version: v0.30.0+

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

    # Syntax errors (3000-3999)
    UNEXPECTED_EOF = 3001
    INVALID_CHARACTER = 3002
    EXPECTED_TOKEN = 3003
    PARSE_JUNK = 3004

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
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Purpose: Unique error code identifiers.
- State: Enum values.

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

    def format_error(self) -> str: ...
```

### Contract
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

### Constraints
- Return: Immutable diagnostic record.
- State: Frozen dataclass.

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

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `start` | `int` | Y | Start byte offset. |
| `end` | `int` | Y | End byte offset (exclusive). |
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

### Contract
| Value | Description |
|:------|:------------|
| `RUST` | Rust compiler-style output with hints and help URLs. |
| `SIMPLE` | Single-line format (code: message). |
| `JSON` | JSON format for tooling integration. |

### Constraints
- StrEnum: Members ARE strings. `str(OutputFormat.RUST) == "rust"`
- Import: `from ftllexengine.diagnostics import OutputFormat`
- Version: Added in v0.31.0.

---

## `DiagnosticFormatter`

### Signature
```python
@dataclass(frozen=True, slots=True)
class DiagnosticFormatter:
    output_format: OutputFormat = OutputFormat.RUST
    sanitize: bool = False
    color: bool = False
    max_content_length: int = 100

    def format(self, diagnostic: Diagnostic) -> str: ...
    def format_all(self, diagnostics: Iterable[Diagnostic]) -> str: ...
    def format_validation_result(self, result: ValidationResult) -> str: ...
```

### Contract
| Field | Type | Description |
|:------|:-----|:------------|
| `output_format` | `OutputFormat` | Output style (rust, simple, json). |
| `sanitize` | `bool` | Truncate content to prevent information leakage. |
| `color` | `bool` | Enable ANSI color codes (for terminal output). |
| `max_content_length` | `int` | Maximum content length when sanitizing. |

### Constraints
- Return: Immutable formatter instance.
- State: Frozen dataclass.
- Thread: Safe.
- Import: `from ftllexengine.diagnostics import DiagnosticFormatter`
- Version: Added in v0.31.0.

---

## `DiagnosticFormatter.format`

### Signature
```python
def format(self, diagnostic: Diagnostic) -> str:
```

### Contract
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

### Contract
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
def format_validation_result(self, result: ValidationResult) -> str:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `result` | `ValidationResult` | Y | Validation result to format. |

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
- SelectExpression fallback shows selector context (v0.23.0+).
- All fallbacks wrapped in braces for visual distinction.

---
