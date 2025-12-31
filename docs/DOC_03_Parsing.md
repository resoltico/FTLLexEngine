---
afad: "3.1"
version: "0.45.0"
domain: PARSING
updated: "2025-12-30"
route:
  keywords: [parse, serialize, FluentParserV1, parse_ftl, serialize_ftl, syntax]
  questions: ["how to parse FTL?", "how to serialize AST?", "what parser options exist?"]
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
    validate: bool = False,
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
- Raises: `SerializationValidationError` when `validate=True` and AST invalid.
- Raises: `SerializationDepthError` when AST exceeds `max_depth`.
- State: None.
- Thread: Safe.
- Security: DepthGuard prevents stack overflow from adversarial ASTs.

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
    ) -> None: ...
    def parse(self, source: str) -> Resource: ...
    @property
    def max_source_size(self) -> int: ...
    @property
    def max_nesting_depth(self) -> int: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `max_source_size` | `int \| None` | N | Maximum source size in characters (default: 10M). |
| `max_nesting_depth` | `int \| None` | N | Maximum nesting depth for placeables (default: 100). |

### Constraints
- Return: Parser instance.
- State: Stores max_source_size and max_nesting_depth configuration.
- Thread: Safe for concurrent parse() calls.
- Security: Validates source size and nesting depth (DoS prevention).

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
    def enter_placeable(self) -> ParseContext: ...
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `max_nesting_depth` | `int` | Maximum allowed nesting depth for placeables. |
| `current_depth` | `int` | Current nesting depth (0 = top level). |

### Constraints
- Immutable: Uses slots for memory efficiency.
- Thread: Safe (explicit parameter passing, no global state).
- Purpose: Replaces thread-local state for async/concurrent compatibility.
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

## `ParseContext.enter_placeable`

### Signature
```python
def enter_placeable(self) -> ParseContext:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: New ParseContext with incremented depth.
- State: None (returns new instance).
- Thread: Safe.

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
- Raises: Never.
- State: None.
- Thread: Safe.

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
- Raises: Never.
- State: None.
- Thread: Safe.

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
- Raises: Never.
- State: None.
- Thread: Safe.
- Preprocessing: Era strings (AD, BC, etc.) stripped. Timezone pattern tokens stripped from format.

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
- Raises: Never.
- State: None.
- Thread: Safe.
- Preprocessing: Era strings (AD, BC, etc.) stripped. Timezone pattern tokens stripped from format.

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
- Raises: Never.
- State: None.
- Thread: Safe.
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
