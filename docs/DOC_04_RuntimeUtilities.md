---
afad: "4.0"
version: "0.165.0"
domain: RUNTIME_UTILITIES
updated: "2026-04-24"
route:
  keywords: [normalize_locale, get_system_locale, require_locale_code, __version__, require_date, require_datetime, require_fluent_number]
  questions: ["where are root-level runtime utility exports documented?", "what package metadata constants are public?", "which boundary validators and locale helpers are exported from the root package?"]
---

# Runtime Utilities Reference

This reference covers root-level runtime-adjacent utilities, package metadata constants, locale helpers, and boundary validators.
Formatting functions, registries, cache configuration, and audit entry types live in [DOC_04_Runtime.md](DOC_04_Runtime.md). Dependency-graph helpers live in [DOC_04_Analysis.md](DOC_04_Analysis.md).

## `normalize_locale`

Function that canonicalizes locale codes to lowercase POSIX form.

### Signature
```python
def normalize_locale(locale_code: str) -> str:
```

### Constraints
- Return: lowercase locale code with hyphens converted to underscores
- Purpose: canonical cache key and comparison form for locale handling
- State: Pure
- Thread: Safe

---

## `get_system_locale`

Function that detects the process locale from Python and environment variables.

### Signature
```python
def get_system_locale(*, raise_on_failure: bool = False) -> str:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `raise_on_failure` | N | Raise instead of falling back to `"en_us"` |

### Constraints
- Return: normalized POSIX-style locale string
- Fallback: returns `"en_us"` when detection fails and `raise_on_failure` is false
- Raises: `RuntimeError` when `raise_on_failure` is true and detection fails
- State: Pure with respect to library state; reads OS process locale and env vars

---

## `require_locale_code`

Boundary validator for locale-code inputs.

### Signature
```python
def require_locale_code(value: object, field_name: str) -> LocaleCode:
```

### Constraints
- Return: canonical normalized locale code
- Raises: `TypeError` for non-strings; `ValueError` for blank, overlong, or structurally invalid codes
- Purpose: system-boundary validation before locale lookup or cache-key creation

---

## `__version__`

Package version string for the installed `ftllexengine` distribution.

### Signature
```python
__version__: str
```

### Constraints
- Return: Installed package version from distribution metadata, or `"0.0.0+dev"` when running from an uninstalled development checkout
- Purpose: Runtime-visible package version for diagnostics, tooling, and support reporting

---

## `__fluent_spec_version__`

Constant declaring the Fluent specification version targeted by the package.

### Signature
```python
__fluent_spec_version__: str = "1.0"
```

### Constraints
- Return: `"1.0"`
- Purpose: Exposes the Fluent spec baseline used by the runtime and parser

---

## `__spec_url__`

Constant pointing to the upstream Fluent grammar/specification reference.

### Signature
```python
__spec_url__: str = "https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf"
```

### Constraints
- Return: Canonical upstream Fluent EBNF/spec URL string
- Purpose: Lets tooling and diagnostics point back to the normative grammar source

---

## `__recommended_encoding__`

Constant declaring the recommended encoding for Fluent resource files.

### Signature
```python
__recommended_encoding__: str = "UTF-8"
```

### Constraints
- Return: `"UTF-8"`
- Purpose: Mirrors the package guidance and upstream Fluent recommendation for `.ftl` resources

---

## `require_date`

Boundary validator for strict calendar-date values.

### Signature
```python
def require_date(value: object, field_name: str) -> date:
```

### Constraints
- Return: validated `date`
- Raises: `TypeError` for non-dates and for `datetime` instances specifically
- Purpose: reject accidental time-bearing values at system boundaries

---

## `require_datetime`

Boundary validator for strict `datetime` values.

### Signature
```python
def require_datetime(value: object, field_name: str) -> datetime:
```

### Constraints
- Return: validated `datetime`
- Raises: `TypeError` for non-`datetime` values, including plain `date`

---

## `require_fluent_number`

Boundary validator for `FluentNumber` values.

### Signature
```python
def require_fluent_number(value: object, field_name: str) -> FluentNumber:
```

### Constraints
- Return: validated `FluentNumber`
- Raises: `TypeError` for all other values
- Purpose: domain-boundary validation for preformatted numeric values
