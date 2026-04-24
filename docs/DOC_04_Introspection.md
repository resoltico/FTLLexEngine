---
afad: "4.0"
version: "0.165.0"
domain: INTROSPECTION
updated: "2026-04-24"
route:
  keywords: [introspection, validate_message_variables, extract_variables, extract_references, ISO 4217, ISO 3166, get_currency, get_territory]
  questions: ["how do I inspect a message's variables and references?", "which ISO lookup helpers exist?", "how do I validate message-variable schemas?", "which Babel-backed introspection helpers are public?"]
---

# Introspection Reference

---

## `validate_message_variables`

Function that checks a parsed message or term against an expected variable schema.

### Signature
```python
def validate_message_variables(
    message: Message | Term,
    expected_variables: frozenset[str] | set[str],
) -> MessageVariableValidationResult:
```

### Constraints
- Return: `MessageVariableValidationResult`
- Purpose: boot-time or CI enforcement that messages declare exactly the variables the caller expects
- Babel: not required; operates on AST only

---

## `introspect_message`

Function that extracts variables, function calls, references, and selector presence from a `Message` or `Term`.

### Signature
```python
def introspect_message(
    message: Message | Term,
    *,
    use_cache: bool = True,
) -> MessageIntrospection:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `message` | Y | Message or term AST node |
| `use_cache` | N | Enable weak-reference memoization |

### Constraints
- Return: `MessageIntrospection`
- Raises: `TypeError` when `message` is not a `Message` or `Term`
- Cache: weak-reference cache keyed by AST node identity
- Babel: not required; operates on AST only

---

## `extract_variables`

Function that returns the declared variable names for a `Message` or `Term`.

### Signature
```python
def extract_variables(message: Message | Term) -> frozenset[str]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `message` | Y | Message or term AST node |

### Constraints
- Return: variable names without `$` prefixes
- Purpose: simplified convenience wrapper over `introspect_message()`
- Babel: not required; operates on AST only

---

## `extract_references`

Function that returns all referenced message ids and term ids from a `Message` or `Term`.

### Signature
```python
def extract_references(entry: Message | Term) -> tuple[frozenset[str], frozenset[str]]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `entry` | Y | Message or term AST node |

### Constraints
- Return: `(message_refs, term_refs)` with attribute-qualified ids preserved
- Purpose: dependency analysis and impact assessment
- Babel: not required; operates on AST only

---

## `extract_references_by_attribute`

Function that returns message and term references grouped by source attribute.

### Signature
```python
def extract_references_by_attribute(
    entry: Message | Term,
) -> dict[str | None, tuple[frozenset[str], frozenset[str]]]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `entry` | Y | Message or term AST node |

### Constraints
- Return: mapping from attribute name, or `None` for the value pattern, to reference sets
- Purpose: attribute-granular dependency and cycle analysis
- Babel: not required; operates on AST only

---

## `clear_introspection_cache`

Function that clears the message-introspection weak-reference cache.

### Signature
```python
def clear_introspection_cache() -> None:
```

### Constraints
- State: Mutates module cache state
- Purpose: testing, benchmarking, or manual memory-pressure relief
- Thread: Safe

---

## `require_currency_code`

Boundary validator for ISO 4217 currency codes.

### Signature
```python
def require_currency_code(value: object, field_name: str) -> CurrencyCode:
```

### Constraints
- Return: canonical uppercase `CurrencyCode`
- Raises: `TypeError` for non-strings; `ValueError` for invalid codes; `BabelImportError` when Babel is unavailable
- Purpose: validated currency boundary input for formatting and domain models

---

## `require_territory_code`

Boundary validator for ISO 3166-1 alpha-2 territory codes.

### Signature
```python
def require_territory_code(value: object, field_name: str) -> TerritoryCode:
```

### Constraints
- Return: canonical uppercase `TerritoryCode`
- Raises: `TypeError` for non-strings; `ValueError` for invalid codes; `BabelImportError` when Babel is unavailable
- Purpose: validated territory boundary input for locale-aware domain logic

---

## `is_valid_currency_code`

Type guard for ISO 4217 currency codes.

### Signature
```python
def is_valid_currency_code(value: str) -> TypeIs[CurrencyCode]:
```

### Constraints
- Return: `True` only for known ISO 4217 codes
- Raises: `BabelImportError` when Babel is unavailable
- Purpose: runtime narrowing from `str` to `CurrencyCode`

---

## `is_valid_territory_code`

Type guard for ISO 3166-1 alpha-2 territory codes.

### Signature
```python
def is_valid_territory_code(value: str) -> TypeIs[TerritoryCode]:
```

### Constraints
- Return: `True` only for known ISO 3166-1 alpha-2 codes
- Raises: `BabelImportError` when Babel is unavailable
- Purpose: runtime narrowing from `str` to `TerritoryCode`

---

## `get_currency_decimal_digits`

Function that returns the embedded ISO 4217 decimal precision for a currency code.

### Signature
```python
def get_currency_decimal_digits(code: str) -> int | None:
```

### Constraints
- Return: decimal precision for a known code, otherwise `None`
- Babel: not required; uses the embedded ISO 4217 tables
- Purpose: authoritative ISO currency exponent lookup

---

## `get_cldr_version`

Function that reports the Babel CLDR data version.

### Signature
```python
def get_cldr_version() -> str:
```

### Constraints
- Return: CLDR version string from Babel
- Raises: `BabelImportError` when Babel is unavailable

---

## `get_territory`

Function that looks up localized ISO 3166-1 territory metadata.

### Signature
```python
def get_territory(code: str, locale: str = "en") -> TerritoryInfo | None:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `code` | Y | ISO alpha-2 territory code |
| `locale` | N | Localization locale |

### Constraints
- Return: `TerritoryInfo`, or `None` for unknown codes
- Raises: `BabelImportError` when Babel is unavailable
- Cache: cached per normalized `(code, locale)` pair
- Thread: Safe

---

## `get_currency`

Function that looks up localized ISO 4217 currency metadata.

### Signature
```python
def get_currency(code: str, locale: str = "en") -> CurrencyInfo | None:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `code` | Y | ISO currency code |
| `locale` | N | Localization locale |

### Constraints
- Return: `CurrencyInfo`, or `None` for unknown codes
- Raises: `BabelImportError` when Babel is unavailable
- Cache: cached per normalized `(code, locale)` pair
- Thread: Safe

---

## `list_territories`

Function that lists all known territories for a locale.

### Signature
```python
def list_territories(locale: str = "en") -> frozenset[TerritoryInfo]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `locale` | N | Localization locale |

### Constraints
- Return: `frozenset[TerritoryInfo]`
- Raises: `BabelImportError` when Babel is unavailable
- Cache: cached per normalized locale
- Thread: Safe

---

## `list_currencies`

Function that lists all known currencies for a locale.

### Signature
```python
def list_currencies(locale: str = "en") -> frozenset[CurrencyInfo]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `locale` | N | Localization locale |

### Constraints
- Return: `frozenset[CurrencyInfo]`
- Raises: `BabelImportError` when Babel is unavailable
- Completeness: returns the full ISO 4217 set, falling back to English names when CLDR localization is missing
- Cache: cached per normalized locale
- Thread: Safe

---

## `get_territory_currencies`

Function that returns the active legal-tender ISO currency codes for a territory.

### Signature
```python
def get_territory_currencies(territory: str) -> tuple[CurrencyCode, ...]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `territory` | Y | ISO alpha-2 territory code |

### Constraints
- Return: tuple of active ISO 4217 currency codes, or `()` for unknown territories
- Raises: `BabelImportError` when Babel is unavailable
- Cache: cached per normalized territory code
- Thread: Safe

---

## `clear_iso_cache`

Function that clears the ISO lookup caches used by territory and currency introspection.

### Signature
```python
def clear_iso_cache() -> None:
```

### Constraints
- State: Mutates module cache state
- Purpose: testing, benchmarking, or manual memory-pressure relief
- Thread: Safe
