---
afad: "3.1"
version: "0.74.0"
domain: PARSING
updated: "2026-01-15"
route:
  keywords: [parse, serialize, validate_resource, FluentParserV1, parse_ftl, serialize_ftl, syntax, validation, BabelImportError]
  questions: ["how to parse FTL?", "how to serialize AST?", "how to validate FTL?", "what parser options exist?", "what exceptions do parsing functions raise?"]
---

# Parsing Reference

---

## `parse`

### Signature
```python
def parse(source: str) -> Resource:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `source` | `str` | Y | FTL source code. |

### Constraints
- Return: Resource AST containing parsed entries.
- Raises: Never (robustness principle: invalid syntax becomes Junk nodes).
- State: None.
- Thread: Safe.

---

## `serialize`

### Signature
```python
def serialize(
    resource: Resource,
    *,
    validate: bool = True,
    max_depth: int = MAX_DEPTH,
) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `resource` | `Resource` | Y | Resource AST node. |
| `validate` | `bool` | N | Validate AST before serialization (default: True). |
| `max_depth` | `int` | N | Maximum nesting depth (default: 100). |

### Constraints
- Return: FTL source string.
- Raises: `SerializationValidationError` when `validate=True` and AST invalid:
  - SelectExpression without default variant
  - Identifier names violating grammar `[a-zA-Z][a-zA-Z0-9_-]*`
  - Duplicate named argument names within CallArguments
  - Named argument values not StringLiteral or NumberLiteral per FTL EBNF
- Raises: `SerializationDepthError` when AST exceeds `max_depth` during validation or serialization.
- State: None.
- Thread: Safe.
- Security: DepthGuard prevents stack overflow from adversarial ASTs. Identifier validation prevents invalid FTL output from programmatic AST construction.
- Version: Named argument validation added in v0.74.0.

---

## `validate_resource`

Function validating FTL resource for syntax and semantic errors.

### Signature
```python
def validate_resource(
    source: str,
    *,
    parser: FluentParserV1 | None = None,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
) -> ValidationResult:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `source` | `str` | Y | FTL source code to validate |
| `parser` | `FluentParserV1 \| None` | N | Custom parser instance |
| `known_messages` | `frozenset[str] \| None` | N | Known message IDs from other resources |
| `known_terms` | `frozenset[str] \| None` | N | Known term IDs from other resources |

### Constraints
- Return: ValidationResult with errors (syntax), warnings (semantic), metadata
- Raises: Never (errors and warnings collected in ValidationResult)
- State: Read-only
- Thread: Safe
- Complexity: O(n) where n is AST node count

### Usage
- When: Validate FTL files in CI/CD pipelines without runtime bundle
- Prefer: This over FluentBundle.validate_resource for parser-only workflows
- Avoid: Repeatedly parsing same resource (cache parsed AST instead)

### Notes
- Available at top-level: `from ftllexengine import validate_resource`
- No Babel dependency (uses AST inspection only)

---

## `FluentParserV1`

### Signature
```python
class FluentParserV1:
    def __init__(
        self,
        *,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
        max_parse_errors: int | None = None,
    ) -> None: ...
    def parse(self, source: str) -> Resource: ...
    @property
    def max_source_size(self) -> int: ...
    @property
    def max_nesting_depth(self) -> int: ...
    @property
    def max_parse_errors(self) -> int: ...
```

### Parameters
| Parameter | Type | Req | Semantics |
|:----------|:-----|:----|:----------|
| `max_source_size` | `int \| None` | N | Maximum source size in characters (default: 10M). |
| `max_nesting_depth` | `int \| None` | N | Maximum nesting depth (default: 100); must be positive if specified. |
| `max_parse_errors` | `int \| None` | N | Maximum Junk entries before parser aborts (default: 100). Set to 0 to disable limit. |

### Constraints
- Return: Parser instance.
- Raises: `ValueError` if max_nesting_depth is specified and <= 0.
- State: Stores max_source_size, max_nesting_depth, and max_parse_errors configuration.
- Thread: Safe for concurrent parse() calls.
- Security: Validates source size, nesting depth, and error accumulation (DoS prevention). After max_parse_errors Junk entries, parse() aborts to prevent memory exhaustion from malformed input. Setting max_parse_errors=0 disables the limit (not recommended for production).
- Depth Validation: max_nesting_depth automatically clamped to sys.getrecursionlimit() - 50. Logs warning if clamped.

---

## `FluentParserV1.parse`

### Signature
```python
def parse(self, source: str) -> Resource:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `source` | `str` | Y | FTL source code. |

### Constraints
- Return: Resource AST containing parsed entries.
- Raises: `ValueError` if source exceeds max_source_size.
- State: None.
- Thread: Safe.
- Security: Enforces input size limit.

---

## `get_last_parse_error`

### Signature
```python
def get_last_parse_error() -> ParseErrorContext | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: ParseErrorContext with error details, or None.
- Raises: None.
- State: Reads thread-local error storage.
- Thread: Thread-safe (thread-local storage).
- Import: `from ftllexengine.syntax.parser.primitives import get_last_parse_error`

---

## `clear_parse_error`

### Signature
```python
def clear_parse_error() -> None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: None.
- Raises: None.
- State: Clears thread-local error storage.
- Thread: Thread-safe.
- Import: `from ftllexengine.syntax.parser.primitives import clear_parse_error`

---

## `ParseErrorContext`

### Signature
```python
@dataclass(frozen=True, slots=True)
class ParseErrorContext:
    message: str
    position: int
    expected: tuple[str, ...] = ()
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `message` | `str` | Human-readable error description. |
| `position` | `int` | Character position in source. |
| `expected` | `tuple[str, ...]` | Expected tokens (optional). |

### Constraints
- Immutable: Frozen dataclass.
- Thread: Safe (immutable).
- Import: `from ftllexengine.syntax.parser.primitives import ParseErrorContext`

---

## `ParseContext`

### Signature
```python
@dataclass(slots=True)
class ParseContext:
    max_nesting_depth: int = MAX_DEPTH
    current_depth: int = 0

    def is_depth_exceeded(self) -> bool: ...
    def enter_nesting(self) -> ParseContext: ...
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `max_nesting_depth` | `int` | Maximum nesting depth for placeables and function calls. |
| `current_depth` | `int` | Current nesting depth (0 = top level). |

### Constraints
- Immutable: Uses slots for memory efficiency.
- Thread: Safe (explicit parameter passing, no global state).
- Purpose: Replaces thread-local state for async/concurrent compatibility.
- Security: Tracks depth for BOTH placeables and function calls (DoS prevention).
- Import: `from ftllexengine.syntax.parser import ParseContext`

---

## `ParseContext.is_depth_exceeded`

### Signature
```python
def is_depth_exceeded(self) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: True if current_depth >= max_nesting_depth.
- State: Read-only.
- Thread: Safe.

---

## `ParseContext.enter_nesting`

### Signature
```python
def enter_nesting(self) -> ParseContext:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: New ParseContext with incremented depth.
- State: None (returns new instance).
- Thread: Safe.
- Usage: Called when entering placeables, function calls, or term calls with arguments.

---

## `parse_number`

### Signature
```python
def parse_number(
    value: str,
    locale_code: str,
) -> tuple[float | None, tuple[FluentParseError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `str` | Y | Locale-formatted number string. |
| `locale_code` | `str` | Y | BCP 47 locale identifier. |

### Constraints
- Return: Tuple of (float or None, errors).
- Raises: `BabelImportError` if Babel not installed.
- State: None.
- Thread: Safe.
- Dependency: Requires Babel for CLDR data.

---

## `parse_decimal`

### Signature
```python
def parse_decimal(
    value: str,
    locale_code: str,
) -> tuple[Decimal | None, tuple[FluentParseError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `str` | Y | Locale-formatted number string. |
| `locale_code` | `str` | Y | BCP 47 locale identifier. |

### Constraints
- Return: Tuple of (Decimal or None, errors).
- Raises: `BabelImportError` if Babel not installed.
- State: None.
- Thread: Safe.
- Dependency: Requires Babel for CLDR data.

---

## `parse_date`

### Signature
```python
def parse_date(
    value: str,
    locale_code: str,
) -> tuple[date | None, tuple[FluentParseError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `str` | Y | Locale-formatted date string. |
| `locale_code` | `str` | Y | BCP 47 locale identifier. |

### Constraints
- Return: Tuple of (date or None, errors).
- Raises: `BabelImportError` if Babel not installed.
- State: None.
- Thread: Safe.
- Dependency: Requires Babel for CLDR data.
- Preprocessing: Era strings stripped (English defaults + localized from Babel CLDR). Timezone pattern tokens stripped from format. Leading/trailing whitespace normalized after pattern conversion.

---

## `parse_datetime`

### Signature
```python
def parse_datetime(
    value: str,
    locale_code: str,
    *,
    tzinfo: timezone | None = None,
) -> tuple[datetime | None, tuple[FluentParseError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `str` | Y | Locale-formatted datetime string. |
| `locale_code` | `str` | Y | BCP 47 locale identifier. |
| `tzinfo` | `timezone \| None` | N | Timezone to assign. |

### Constraints
- Return: Tuple of (datetime or None, errors).
- Raises: `BabelImportError` if Babel not installed.
- State: None.
- Thread: Safe.
- Dependency: Requires Babel for CLDR data.
- Preprocessing: Era strings stripped (English defaults + localized from Babel CLDR). Timezone pattern tokens stripped from format. Leading/trailing whitespace normalized after pattern conversion.

---

## `parse_currency`

### Signature
```python
def parse_currency(
    value: str,
    locale_code: str,
    *,
    default_currency: str | None = None,
    infer_from_locale: bool = False,
) -> tuple[tuple[Decimal, str] | None, tuple[FluentParseError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `str` | Y | Currency string with amount and symbol. |
| `locale_code` | `str` | Y | BCP 47 locale identifier. |
| `default_currency` | `str \| None` | N | Fallback currency for ambiguous symbols ($, kr, ¥). |
| `infer_from_locale` | `bool` | N | Infer currency from locale if symbol ambiguous. |

### Constraints
- Return: Tuple of ((amount, currency_code) or None, errors).
- Raises: `BabelImportError` if Babel not installed.
- State: None.
- Thread: Safe.
- Dependency: Requires Babel for CLDR data.
- Validation: ISO 4217 codes validated against CLDR data.
- Ambiguous: Yen sign (`¥`) resolves to CNY for `zh_*` locales, JPY otherwise.
- Ambiguous: Pound sign (`£`) resolves to EGP for `ar_*` locales, GBP otherwise.
- Resolution: With `infer_from_locale=True`, ambiguous symbols use locale-aware defaults.

---

## `is_valid_number`

### Signature
```python
def is_valid_number(value: float | None) -> TypeIs[float]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `float \| None` | Y | Float to validate (may be None). |

### Constraints
- Return: True if finite float, False if None/NaN/Infinity.
- Raises: None.
- State: None.
- Thread: Safe.

---

## `is_valid_decimal`

### Signature
```python
def is_valid_decimal(value: Decimal | None) -> TypeIs[Decimal]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `Decimal \| None` | Y | Decimal to validate (may be None). |

### Constraints
- Return: True if finite Decimal, False if None/NaN/Infinity.
- Raises: None.
- State: None.
- Thread: Safe.

---

## `is_valid_date`

### Signature
```python
def is_valid_date(value: date | None) -> TypeIs[date]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `date \| None` | Y | Date to validate. |

### Constraints
- Return: True if not None.
- Raises: None.
- State: None.

---

## `is_valid_datetime`

### Signature
```python
def is_valid_datetime(value: datetime | None) -> TypeIs[datetime]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `datetime \| None` | Y | Datetime to validate. |

### Constraints
- Return: True if not None.
- Raises: None.
- State: None.

---

## `is_valid_currency`

### Signature
```python
def is_valid_currency(
    value: tuple[Decimal, str] | None,
) -> TypeIs[tuple[Decimal, str]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `tuple[Decimal, str] \| None` | Y | Currency tuple to validate. |

### Constraints
- Return: True if not None and amount is finite.
- Raises: None.
- State: None.

---

## Module Constants

### `ISO_CURRENCY_CODE_LENGTH`

```python
ISO_CURRENCY_CODE_LENGTH: int = 3
```

| Attribute | Value |
|:----------|:------|
| Type | `int` |
| Value | 3 |
| Location | `ftllexengine.parsing.currency` |

- Purpose: ISO 4217 currency codes are exactly 3 uppercase ASCII letters.
- Usage: Validation of currency code format in parsing functions.

---

### `MAX_DEPTH`

```python
MAX_DEPTH: int = 100
```

| Attribute | Value |
|:----------|:------|
| Type | `int` |
| Value | 100 |
| Location | `ftllexengine.constants` |

- Purpose: Unified depth limit for parser, resolver, serializer, and validators.
- Usage: Default for ParseContext.max_nesting_depth, FluentParserV1, serialize(max_depth=...).
- Security: Prevents DoS via deeply nested placeables and stack overflow from adversarial ASTs.

---

### `MAX_PARSE_ERRORS`

```python
MAX_PARSE_ERRORS: int = 100
```

| Attribute | Value |
|:----------|:------|
| Type | `int` |
| Value | 100 |
| Location | `ftllexengine.constants` |

- Purpose: Maximum Junk entries before parser aborts to prevent memory exhaustion.
- Usage: Default for FluentParserV1.max_parse_errors. Set to 0 to disable limit.
- Security: Prevents DoS via malformed input generating excessive errors.

---

### `MAX_LOCALE_LENGTH_HARD_LIMIT`

```python
MAX_LOCALE_LENGTH_HARD_LIMIT: int = 1000
```

| Attribute | Value |
|:----------|:------|
| Type | `int` |
| Value | 1000 |
| Location | `ftllexengine.constants` |

- Purpose: Hard limit on locale code length for DoS prevention.
- Usage: FluentBundle input validation. Codes exceeding limit are rejected.
- Security: Prevents memory exhaustion from extremely long locale strings.
- Note: MAX_LOCALE_CODE_LENGTH (35) triggers warnings; this limit triggers rejection.

---

## Parsing Behavior

### Line Ending Normalization

Parser normalizes all line endings to LF before parsing.

### Constraints
- Normalization: CRLF (`\r\n`) and CR (`\r`) converted to LF (`\n`).
- Timing: Applied before any parsing occurs.
- Scope: Affects all line/column tracking and comment merging.
- Rationale: Per Fluent spec, ensures consistent AST representation across platforms.

---

### Column-1 Enforcement

Top-level entries must start at column 1 (beginning of line).

### Constraints
- Rule: Messages, terms, and comments must start at column 1.
- Indented: Indented content at top level becomes Junk entry.
- Error: Junk annotation includes "Entry must start at column 1".
- Rationale: Per Fluent spec for message/term/comment positioning.

---

### Pattern Whitespace Handling

Patterns have leading/trailing blank lines trimmed.

### Constraints
- Leading: Leading whitespace/blank lines removed from first TextElement.
- Trailing: Trailing blank lines removed (but trailing spaces on content lines preserved).
- Continuation: Multi-line patterns joined with newline (`\n`), not space.
- Implementation: `_trim_pattern_blank_lines()` post-processes pattern elements.
- Rationale: Per Fluent spec whitespace handling rules.

---
