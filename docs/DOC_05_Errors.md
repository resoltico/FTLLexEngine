---
afad: "3.5"
version: "0.163.0"
domain: ERRORS
updated: "2026-04-22"
route:
  keywords: [FrozenFluentError, ErrorCategory, FrozenErrorContext, DataIntegrityError, BabelImportError, ErrorTemplate]
  questions: ["what errors does FTLLexEngine expose?", "how do parse and format failures surface?", "what integrity exceptions exist?", "how does missing Babel surface?"]
---

# Errors Reference

This reference covers immutable Fluent errors, optional-dependency failures, and fail-fast integrity exceptions.
Validation result types and formatter infrastructure are documented in [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md).

## `ErrorCategory`

Enum that classifies `FrozenFluentError` instances.

### Signature
```python
class ErrorCategory(StrEnum):
    REFERENCE = "reference"
    RESOLUTION = "resolution"
    CYCLIC = "cyclic"
    PARSE = "parse"
    FORMATTING = "formatting"
```

### Constraints
- Import: `from ftllexengine import ErrorCategory`
- Type: `StrEnum`
- Purpose: replaces a subclass hierarchy for normal Fluent errors

---

## `ParseTypeLiteral`

Closed literal set for parse/format context.

### Signature
```python
type ParseTypeLiteral = Literal["", "currency", "date", "datetime", "decimal", "number"]
```

### Constraints
- Import: `from ftllexengine import ParseTypeLiteral`
- `""` is the sentinel meaning "not applicable"
- Used by: `FrozenErrorContext.parse_type`

---

## `FrozenErrorContext`

Immutable context attached to parse and formatting failures.

### Signature
```python
@dataclass(frozen=True, slots=True)
class FrozenErrorContext:
    input_value: str = ""
    locale_code: str = ""
    parse_type: ParseTypeLiteral = ""
    fallback_value: str = ""
```

### Constraints
- Import: `from ftllexengine import FrozenErrorContext`
- Purpose: keeps parse/format metadata immutable and hashable
- Typical use: attached to `FrozenFluentError.context`

---

## `FrozenFluentError`

Sealed, immutable, content-addressable Fluent error type.

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
```

### Constraints
- Import: `from ftllexengine import FrozenFluentError`
- Purpose: normal parse, formatting, resolution, and reference failures
- Integrity: stores a BLAKE2b-128 `content_hash` and exposes `verify_integrity()`
- Immutability: attribute mutation or deletion raises `ImmutabilityViolationError`
- Sealed: runtime and static checks prevent subclassing
- Convenience properties: `input_value`, `locale_code`, `parse_type`, and `fallback_value` proxy `context`

---

## `BabelImportError`

Exception raised when a Babel-backed feature is called in a parser-only installation.

### Signature
```python
class BabelImportError(ImportError):
    def __init__(self, feature: str) -> None: ...
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `feature` | Y | Missing Babel feature label |

### Constraints
- Import: `from ftllexengine.introspection import BabelImportError`
- Purpose: consistent optional-dependency failure for CLDR-backed features
- Trigger: only for genuinely missing Babel in parser-only installs
- Broken-install path: internal Babel import failures bubble their original `ImportError`
- Message: instructs callers to install `ftllexengine[babel]`

---

## `ErrorTemplate`

Class namespace that builds standardized `Diagnostic` objects for common runtime failures.

### Signature
```python
class ErrorTemplate: ...
```

### Constraints
- Import: `from ftllexengine.diagnostics import ErrorTemplate`
- Purpose: centralized diagnostic-message construction instead of ad-hoc exception strings
- Output: returns `Diagnostic` objects from named factory methods such as `message_not_found()` and `plural_support_unavailable()`
- State: Stateless factory namespace

---

## `DataIntegrityError`

Base exception for system integrity failures, distinct from normal Fluent errors.

### Signature
```python
class DataIntegrityError(Exception):
    def __init__(
        self,
        message: str,
        context: IntegrityContext | None = None,
    ) -> None: ...
```

### Constraints
- Import: `from ftllexengine import DataIntegrityError`
- Purpose: corruption, strict-mode violations, or mutation attempts that should fail fast
- Domain boundary: not a `FrozenFluentError` subclass
- Immutability: frozen after initialization; mutation raises `ImmutabilityViolationError`

---

## `IntegrityContext`

Structured context for `DataIntegrityError` instances.

### Signature
```python
@dataclass(frozen=True, slots=True)
class IntegrityContext:
    component: str
    operation: str
    key: str | None = None
    expected: str | None = None
    actual: str | None = None
    timestamp: float | None = None
    wall_time_unix: float | None = None
```

### Constraints
- Import: `from ftllexengine import IntegrityContext`
- Purpose: post-mortem metadata for cache, formatting, and strict-load failures
- Timestamps: `timestamp` is monotonic-process time; `wall_time_unix` is wall-clock correlation time

---

## `CacheCorruptionError`

Raised when cached content fails checksum verification.

### Signature
```python
@final
class CacheCorruptionError(DataIntegrityError): ...
```

### Constraints
- Import: `from ftllexengine import CacheCorruptionError`
- Typical meaning: corruption, tampering, or checksum mismatch in cached data

---

## `ImmutabilityViolationError`

Raised when frozen error or integrity objects are mutated.

### Signature
```python
@final
class ImmutabilityViolationError(DataIntegrityError): ...
```

### Constraints
- Import: `from ftllexengine import ImmutabilityViolationError`
- Triggered by: invalid mutation attempts on `FrozenFluentError`, `DataIntegrityError`, or related frozen evidence

---

## `IntegrityCheckFailedError`

Generic integrity-verification failure when no narrower subtype applies.

### Signature
```python
@final
class IntegrityCheckFailedError(DataIntegrityError): ...
```

### Constraints
- Import: `from ftllexengine import IntegrityCheckFailedError`
- Used for: verification failures that are not specifically checksum, write-conflict, syntax, or formatting failures

---

## `WriteConflictError`

Raised when write-once cache mode rejects an overwrite.

### Signature
```python
@final
class WriteConflictError(DataIntegrityError):
    def __init__(
        self,
        message: str,
        context: IntegrityContext | None = None,
        *,
        existing_seq: int = 0,
        new_seq: int = 0,
    ) -> None: ...
```

### Constraints
- Import: `from ftllexengine import WriteConflictError`
- Extra properties: `existing_seq` and `new_seq`
- Typical meaning: concurrent or forbidden overwrite in write-once cache mode

---

## `FormattingIntegrityError`

Strict-mode formatting failure that carries the underlying Fluent errors.

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
```

### Constraints
- Import: `from ftllexengine import FormattingIntegrityError`
- Extra properties: `fluent_errors`, `fallback_value`, `message_id`
- Raised by: strict formatting paths that refuse to return fallback text

---

## `SyntaxIntegrityError`

Strict-load failure raised when resource loading encounters syntax junk.

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
```

### Constraints
- Import: `from ftllexengine import SyntaxIntegrityError`
- Extra properties: `junk_entries`, `source_path`
- Raised by: strict boot and resource-loading paths that reject partial parse success

---
