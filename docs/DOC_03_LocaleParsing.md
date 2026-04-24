---
afad: "4.0"
version: "0.164.0"
domain: LOCALE_PARSING
updated: "2026-04-24"
route:
  keywords: [parse_decimal, parse_fluent_number, parse_date, parse_datetime, parse_currency, is_valid_decimal, clear_date_caches]
  questions: ["how do I parse localized numbers and dates?", "what do the locale-aware parse helpers return?", "which parsing type guards and cache-clear helpers are public?"]
---

# Locale Parsing Reference

This reference covers locale-aware parsing helpers from `ftllexengine.parsing`, including type guards and cache lifecycle utilities.
FTL syntax parsing and AST traversal helpers live in [DOC_03_Parsing.md](DOC_03_Parsing.md).

## `parse_decimal`

Function that parses a localized number string into `Decimal`.

### Signature
```python
def parse_decimal(value: str, locale_code: str) -> ParseResult[Decimal]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `value` | Y | Localized numeric input |
| `locale_code` | Y | Locale for parsing |

### Constraints
- Return: Parsed `Decimal` or `None` with errors
- Raises: `BabelImportError` when Babel is unavailable
- State: Pure
- Thread: Safe

---

## `parse_fluent_number`

Function that parses a localized number into `FluentNumber`.

### Signature
```python
def parse_fluent_number(value: str, locale_code: str) -> ParseResult[FluentNumber]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `value` | Y | Localized numeric input |
| `locale_code` | Y | Locale for parsing |

### Constraints
- Return: Parsed `FluentNumber` or `None` with errors
- Raises: `BabelImportError` when Babel is unavailable
- State: Pure
- Thread: Safe

---

## `parse_date`

Function that parses a localized date string into `datetime.date`.

### Signature
```python
def parse_date(value: str, locale_code: str) -> tuple[date | None, tuple[FrozenFluentError, ...]]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `value` | Y | Localized date input |
| `locale_code` | Y | Locale for parsing |

### Constraints
- Return: Parsed `date` or `None` with errors
- Raises: `BabelImportError` when Babel is unavailable
- State: Pure
- Thread: Safe

---

## `parse_datetime`

Function that parses a localized datetime string into `datetime.datetime`.

### Signature
```python
def parse_datetime(
    value: str,
    locale_code: str,
    *,
    tzinfo: timezone | None = None,
) -> tuple[datetime | None, tuple[FrozenFluentError, ...]]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `value` | Y | Localized datetime input |
| `locale_code` | Y | Locale for parsing |
| `tzinfo` | N | Fallback timezone |

### Constraints
- Return: Parsed `datetime` or `None` with errors
- Raises: `BabelImportError` when Babel is unavailable
- State: Pure
- Thread: Safe

---

## `parse_currency`

Function that parses localized money input into `(Decimal, ISO code)`.

### Signature
```python
def parse_currency(
    value: str,
    locale_code: str,
    *,
    default_currency: str | None = None,
    infer_from_locale: bool = False,
) -> tuple[tuple[Decimal, str] | None, tuple[FrozenFluentError, ...]]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `value` | Y | Localized money input |
| `locale_code` | Y | Locale for parsing |
| `default_currency` | N | Explicit ISO code |
| `infer_from_locale` | N | Infer ISO code from locale |

### Constraints
- Return: `(amount, code)` or `None` with errors
- Raises: `BabelImportError` when Babel is unavailable
- State: Pure
- Thread: Safe

---

## `is_valid_decimal`

Function that acts as a `TypeIs[Decimal]` guard for parsed decimal results.

### Signature
```python
def is_valid_decimal(value: Decimal | None) -> TypeIs[Decimal]:
```

### Constraints
- Return: `True` only for usable decimal results
- State: Pure

---

## `is_valid_date`

Function that acts as a `TypeIs[date]` guard for parsed date results.

### Signature
```python
def is_valid_date(value: date | None) -> TypeIs[date]:
```

### Constraints
- Return: `True` only for usable date results
- State: Pure

---

## `is_valid_datetime`

Function that acts as a `TypeIs[datetime]` guard for parsed datetime results.

### Signature
```python
def is_valid_datetime(value: datetime | None) -> TypeIs[datetime]:
```

### Constraints
- Return: `True` only for usable datetime results
- State: Pure

---

## `is_valid_currency`

Function that acts as a `TypeIs[tuple[Decimal, str]]` guard for parsed currency results.

### Signature
```python
def is_valid_currency(value: tuple[Decimal, str] | None) -> TypeIs[tuple[Decimal, str]]:
```

### Constraints
- Return: `True` only for usable currency results
- State: Pure

---

## `clear_date_caches`

Function that clears cached locale-specific date parsing patterns.

### Signature
```python
def clear_date_caches() -> None:
```

### Constraints
- State: Mutates module cache state
- Thread: Safe

---

## `clear_currency_caches`

Function that clears cached locale-specific currency parsing data.

### Signature
```python
def clear_currency_caches() -> None:
```

### Constraints
- State: Mutates module cache state
- Thread: Safe
