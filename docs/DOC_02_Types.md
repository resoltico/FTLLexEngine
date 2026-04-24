---
afad: "4.0"
version: "0.165.0"
domain: TYPES
updated: "2026-04-24"
route:
  keywords: [FluentNumber, FluentValue, ParseResult, LocaleCode, CurrencyCode, TerritoryInfo, MessageIntrospection]
  questions: ["what public types does FTLLexEngine expose?", "what value types can formatting accept?", "which semantic aliases and lookup-result types exist?", "what introspection result types exist?"]
---

# Types Reference

---

## `FluentNumber`

Immutable wrapper that keeps a numeric value, its rendered string, and visible precision together.

### Signature
```python
@dataclass(frozen=True, slots=True)
class FluentNumber:
    value: int | Decimal
    formatted: str
    precision: int | None = None
```

### Constraints
- Import: `from ftllexengine import FluentNumber`
- Purpose: lets formatted numbers still participate in plural resolution and exact numeric comparisons
- Invariants: `value` must be `int | Decimal`, never `bool`; `precision` is `None` or `>= 0`
- Helpers: `decimal_value` returns exact `Decimal`; `str(value)` returns `formatted`
- Thread: safe

---

## `FluentValue`

Recursive type alias for values accepted by runtime formatting and custom functions.

### Signature
```python
type FluentValue = (
    str
    | int
    | Decimal
    | datetime
    | date
    | FluentNumber
    | None
    | Sequence["FluentValue"]
    | Mapping[str, "FluentValue"]
)
```

### Constraints
- Import: `from ftllexengine import FluentValue`
- Includes: scalar values, `FluentNumber`, nested sequences, and string-keyed mappings
- Excludes: `float` by design; `bool` is not intended even though it is an `int` subtype
- Purpose: canonical runtime boundary type for formatting and custom functions

---

## `ParseResult`

Generic return type for locale-aware parse helpers.

### Signature
```python
type ParseResult[T] = tuple[T | None, tuple[FrozenFluentError, ...]]
```

### Constraints
- Import: `from ftllexengine import ParseResult`
- Success contract: parsed value in slot 0 and empty error tuple in slot 1
- Failure contract: `None` in slot 0 and one or more `FrozenFluentError` instances in slot 1
- Used by: `parse_decimal()`, `parse_date()`, `parse_datetime()`, `parse_currency()`, `parse_fluent_number()`

---

## `LocaleCode`

Semantic alias for locale identifiers in localization APIs.

### Signature
```python
type LocaleCode = str
```

### Constraints
- Import: `from ftllexengine import LocaleCode`
- Semantics: BCP-47 or POSIX-style locale code such as `"en"`, `"lv"`, `"de-DE"`, or `"en_US"`

---

## `MessageId`

Semantic alias for Fluent message identifiers.

### Signature
```python
type MessageId = str
```

### Constraints
- Import: `from ftllexengine import MessageId`
- Semantics: message key like `"welcome"` or `"error-network"`

---

## `ResourceId`

Semantic alias for resource identifiers used by localization loaders.

### Signature
```python
type ResourceId = str
```

### Constraints
- Import: `from ftllexengine import ResourceId`
- Semantics: logical resource name such as `"main.ftl"` or `"errors.ftl"`

---

## `FTLSource`

Semantic alias for raw Fluent source text.

### Signature
```python
type FTLSource = str
```

### Constraints
- Import: `from ftllexengine import FTLSource`
- Semantics: normalized or unnormalized FTL text before parsing

---

## `CurrencyCode`

Nominal wrapper for ISO 4217 currency codes.

### Signature
```python
CurrencyCode = NewType("CurrencyCode", str)
```

### Constraints
- Import: `from ftllexengine import CurrencyCode`
- Purpose: distinguish validated currency codes from arbitrary strings
- Validation path: use `is_valid_currency_code()` or `require_currency_code()` before constructing or narrowing

---

## `TerritoryCode`

Nominal wrapper for ISO 3166-1 alpha-2 territory codes.

### Signature
```python
TerritoryCode = NewType("TerritoryCode", str)
```

### Constraints
- Import: `from ftllexengine import TerritoryCode`
- Purpose: distinguish validated territory codes from arbitrary strings
- Validation path: use `is_valid_territory_code()` or `require_territory_code()` before constructing or narrowing

---

## `CurrencyInfo`

Immutable ISO 4217 lookup result.

### Signature
```python
@dataclass(frozen=True, slots=True)
class CurrencyInfo:
    code: CurrencyCode
    name: str
    symbol: str
    decimal_digits: int
```

### Constraints
- Import: `from ftllexengine.introspection.iso import CurrencyInfo`
- Produced by: `get_currency()` and `list_currencies()`
- Locale note: `name` and `symbol` depend on the lookup locale; `decimal_digits` follows the embedded ISO 4217 table
- Thread: safe

---

## `TerritoryInfo`

Immutable ISO 3166-1 lookup result.

### Signature
```python
@dataclass(frozen=True, slots=True)
class TerritoryInfo:
    alpha2: TerritoryCode
    name: str
    currencies: tuple[CurrencyCode, ...]
    official_languages: tuple[str, ...]
```

### Constraints
- Import: `from ftllexengine.introspection.iso import TerritoryInfo`
- Produced by: `get_territory()` and `list_territories()`
- Locale note: `name` depends on the lookup locale; currencies and languages come from CLDR data
- Thread: safe

---

## `CommentType`

Enum of Fluent comment kinds.

### Signature
```python
class CommentType(StrEnum):
    COMMENT = "comment"
    GROUP = "group"
    RESOURCE = "resource"
```

### Constraints
- Import: `from ftllexengine.enums import CommentType`
- Used by: `syntax.ast.Comment.type`
- Type: `StrEnum`

---

## `ReferenceKind`

Enum describing whether a reference points at a message or a term.

### Signature
```python
class ReferenceKind(StrEnum):
    MESSAGE = "message"
    TERM = "term"
```

### Constraints
- Import: `from ftllexengine.enums import ReferenceKind`
- Used by: `ReferenceInfo.kind`
- Type: `StrEnum`

---

## `VariableContext`

Enum describing where a variable appears inside a message.

### Signature
```python
class VariableContext(StrEnum):
    PATTERN = "pattern"
    SELECTOR = "selector"
    VARIANT = "variant"
    FUNCTION_ARG = "function_arg"
```

### Constraints
- Import: `from ftllexengine.enums import VariableContext`
- Used by: `VariableInfo.context`
- Type: `StrEnum`

---

## `VariableInfo`

Immutable metadata about a variable occurrence discovered during introspection.

### Signature
```python
@dataclass(frozen=True, slots=True)
class VariableInfo:
    name: str
    context: VariableContext
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.introspection.message import VariableInfo`
- Produced by: `introspect_message()`

---

## `FunctionCallInfo`

Immutable metadata about a function call discovered during introspection.

### Signature
```python
@dataclass(frozen=True, slots=True)
class FunctionCallInfo:
    name: str
    positional_arg_vars: tuple[str, ...]
    named_args: frozenset[str]
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.introspection.message import FunctionCallInfo`
- Produced by: `introspect_message()`
- `positional_arg_vars` contains only variable names, not literal argument values

---

## `ReferenceInfo`

Immutable metadata about a message or term dependency discovered during introspection.

### Signature
```python
@dataclass(frozen=True, slots=True)
class ReferenceInfo:
    id: str
    kind: ReferenceKind
    attribute: str | None
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.introspection.message import ReferenceInfo`
- Produced by: `introspect_message()` and reference extraction helpers

---

## `MessageIntrospection`

Complete immutable summary of a message or term's variables, function calls, and references.

### Signature
```python
@dataclass(frozen=True, slots=True)
class MessageIntrospection:
    message_id: str
    variables: frozenset[VariableInfo]
    functions: frozenset[FunctionCallInfo]
    references: frozenset[ReferenceInfo]
    has_selectors: bool
```

### Constraints
- Import: `from ftllexengine.introspection.message import MessageIntrospection`
- Produced by: `introspect_message()`
- Helpers: `get_variable_names()`, `requires_variable()`, `get_function_names()`
- Cached: module-level weak-reference cache memoizes results per `Message` or `Term`

---

## `MessageVariableValidationResult`

Structured diff between the variables a message declares and the variables you expect it to declare.

### Signature
```python
@dataclass(frozen=True, slots=True)
class MessageVariableValidationResult:
    message_id: str
    is_valid: bool
    declared_variables: frozenset[str]
    missing_variables: frozenset[str]
    extra_variables: frozenset[str]
```

### Constraints
- Import: `from ftllexengine import MessageVariableValidationResult`
- Produced by: `validate_message_variables()`
- Valid when: both `missing_variables` and `extra_variables` are empty
