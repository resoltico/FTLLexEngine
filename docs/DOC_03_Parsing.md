---
spec_version: AFAD-v1
project_version: 0.32.0
context: PARSING
last_updated: 2025-12-24T12:00:00Z
maintainer: claude-opus-4-5
---

# Parsing Reference

---

## `parse_ftl`

### Signature
```python
def parse_ftl(source: str) -> Resource:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `source` | `str` | Y | FTL source code. |

### Constraints
- Return: Resource AST containing parsed entries.
- Raises: `FluentSyntaxError` on critical parse error.
- State: None.
- Thread: Safe.

---

## `serialize_ftl`

### Signature
```python
def serialize_ftl(resource: Resource, *, validate: bool = False) -> str:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `resource` | `Resource` | Y | Resource AST node. |
| `validate` | `bool` | N | Validate AST before serialization (default: False). |

### Constraints
- Return: FTL source string.
- Raises: `SerializationValidationError` when `validate=True` and AST invalid.
- State: None.
- Thread: Safe.

---

## `FluentParserV1`

### Signature
```python
class FluentParserV1:
    def __init__(self, *, max_source_size: int | None = None) -> None: ...
    def parse(self, source: str) -> Resource: ...
    @property
    def max_source_size(self) -> int: ...
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `max_source_size` | `int \| None` | N | Maximum source size in bytes (default: 10 MB). |

### Constraints
- Return: Parser instance.
- State: Stores max_source_size configuration.
- Thread: Safe for concurrent parse() calls.
- Security: Validates source size before parsing (DoS prevention).

---

## `FluentParserV1.parse`

### Signature
```python
def parse(self, source: str) -> Resource:
```

### Contract
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

## `FluentParserV1.max_nesting_depth`

### Signature
```python
def __init__(
    self,
    *,
    max_source_size: int | None = None,
    max_nesting_depth: int | None = None,
) -> None:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `max_source_size` | `int \| None` | N | Maximum source size in bytes. |
| `max_nesting_depth` | `int \| None` | N | Maximum nesting depth (default: 100). |

### Constraints
- Return: None.
- State: Per-instance configuration.
- Thread: Each parser instance has independent limit.
- Security: Prevents DoS via deeply nested placeables.
- Import: `from ftllexengine.syntax.parser import FluentParserV1`

---

## `get_last_parse_error`

### Signature
```python
def get_last_parse_error() -> ParseErrorContext | None:
```

### Contract
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

### Contract
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

### Contract
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
    max_nesting_depth: int = DEFAULT_MAX_NESTING_DEPTH
    current_depth: int = 0

    def is_depth_exceeded(self) -> bool: ...
    def enter_placeable(self) -> ParseContext: ...
```

### Contract
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

### Contract
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

### Contract
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

### Contract
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

### Contract
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

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `str` | Y | Locale-formatted date string. |
| `locale_code` | `str` | Y | BCP 47 locale identifier. |

### Constraints
- Return: Tuple of (date or None, errors).
- Raises: Never.
- State: None.
- Thread: Safe.

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

### Contract
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

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `str` | Y | Currency string with amount and symbol. |
| `locale_code` | `str` | Y | BCP 47 locale identifier. |
| `default_currency` | `str \| None` | N | Fallback currency for ambiguous symbols ($, kr). |
| `infer_from_locale` | `bool` | N | Infer currency from locale if symbol ambiguous. |

### Constraints
- Return: Tuple of ((amount, currency_code) or None, errors).
- Raises: Never.
- State: None.
- Thread: Safe.

---

## `is_valid_number`

### Signature
```python
def is_valid_number(value: float | None) -> TypeIs[float]:
```

### Contract
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

### Contract
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

### Contract
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

### Contract
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

### Contract
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

### `DEFAULT_MAX_NESTING_DEPTH`

```python
DEFAULT_MAX_NESTING_DEPTH: int = 100
```

| Attribute | Value |
|:----------|:------|
| Type | `int` |
| Value | 100 |
| Location | `ftllexengine.syntax.parser.expressions` |

- Purpose: Default maximum nesting depth for placeable parsing.
- Usage: Default value for ParseContext.max_nesting_depth and FluentParserV1.
- Security: Prevents DoS attacks via deeply nested placeables.

---
