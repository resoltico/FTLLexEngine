---
afad: "4.0"
version: "0.165.0"
domain: SYNTAX_EXPRESSIONS
updated: "2026-04-24"
route:
  keywords: [TextElement, Placeable, SelectExpression, VariableReference, FunctionReference, Entry, Expression]
  questions: ["which AST node types model Fluent expressions and references?", "what public syntax union aliases exist?", "where are placeables and selectors documented?"]
---

# Syntax Expression Types Reference

This reference covers pattern elements, expression/reference nodes, call argument nodes, and public syntax union aliases.
Core resource and declaration nodes live in [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md).

## `TextElement`

AST node for literal text inside a pattern.

### Signature
```python
@dataclass(frozen=True, slots=True)
class TextElement:
    value: str
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import TextElement`
- Helper: `TextElement.guard()` performs runtime narrowing

---

## `Placeable`

AST node for `{ ... }` dynamic content inside a pattern.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Placeable:
    expression: Expression
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import Placeable`
- Helper: `Placeable.guard()` performs runtime narrowing

---

## `SelectExpression`

AST node for Fluent select expressions.

### Signature
```python
@dataclass(frozen=True, slots=True)
class SelectExpression:
    selector: SelectorExpression
    variants: tuple[Variant, ...]
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import SelectExpression`
- Invariants: at least one variant and exactly one default variant
- Selector type: restricted to the `SelectorExpression` union, not arbitrary `Expression`
- Helper: `SelectExpression.guard()` performs runtime narrowing

---

## `Variant`

AST node for one branch of a select expression.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Variant:
    key: Identifier | NumberLiteral
    value: Pattern
    default: bool = False
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import Variant`
- `default=True` marks the `*` branch

---

## `StringLiteral`

AST node for quoted string literals.

### Signature
```python
@dataclass(frozen=True, slots=True)
class StringLiteral:
    value: str
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import StringLiteral`
- Helper: `StringLiteral.guard()` performs runtime narrowing

---

## `NumberLiteral`

AST node for integer or decimal literals.

### Signature
```python
@dataclass(frozen=True, slots=True)
class NumberLiteral:
    value: int | Decimal
    raw: str
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import NumberLiteral`
- Invariants: `value` cannot be `bool`; `raw` must parse back to the same finite numeric value
- Helper: `NumberLiteral.guard()` performs runtime narrowing

---

## `VariableReference`

AST node for `$name` variable references.

### Signature
```python
@dataclass(frozen=True, slots=True)
class VariableReference:
    id: Identifier
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import VariableReference`
- Helper: `VariableReference.guard()` performs runtime narrowing

---

## `MessageReference`

AST node for message references like `hello` or `hello.attr`.

### Signature
```python
@dataclass(frozen=True, slots=True)
class MessageReference:
    id: Identifier
    attribute: Identifier | None = None
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import MessageReference`
- Helper: `MessageReference.guard()` performs runtime narrowing

---

## `TermReference`

AST node for term references like `-brand` or `-brand.attr`.

### Signature
```python
@dataclass(frozen=True, slots=True)
class TermReference:
    id: Identifier
    attribute: Identifier | None = None
    arguments: CallArguments | None = None
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import TermReference`
- Helper: `TermReference.guard()` performs runtime narrowing

---

## `FunctionReference`

AST node for function calls such as `NUMBER($count)`.

### Signature
```python
@dataclass(frozen=True, slots=True)
class FunctionReference:
    id: Identifier
    arguments: CallArguments
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import FunctionReference`
- Helper: `FunctionReference.guard()` performs runtime narrowing

---

## `CallArguments`

AST node for positional and named function arguments.

### Signature
```python
@dataclass(frozen=True, slots=True)
class CallArguments:
    positional: tuple[
        StringLiteral
        | NumberLiteral
        | VariableReference
        | MessageReference
        | TermReference
        | FunctionReference
        | Placeable,
        ...,
    ]
    named: tuple[NamedArgument, ...]
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import CallArguments`
- Used by: `FunctionReference.arguments` and optional `TermReference.arguments`

---

## `NamedArgument`

AST node for `name: literal` function arguments.

### Signature
```python
@dataclass(frozen=True, slots=True)
class NamedArgument:
    name: Identifier
    value: FTLLiteral
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import NamedArgument`
- Invariant: `value` is restricted to `FTLLiteral`, not any inline expression

---

## `Entry`

Type alias for every top-level AST entry that can appear in a `Resource`.

### Signature
```python
type Entry = Message | Term | Comment | Junk
```

### Constraints
- Import: `from ftllexengine.syntax import Entry`
- Used by: `Resource.entries` and `parse_stream()`
- Purpose: closed top-level union for syntax tooling

---

## `PatternElement`

Type alias for the elements that make up a `Pattern`.

### Signature
```python
type PatternElement = TextElement | Placeable
```

### Constraints
- Import: `from ftllexengine.syntax import PatternElement`
- Used by: `Pattern.elements`
- Purpose: restrict pattern contents to literal text or embedded expressions

---

## `Expression`

Type alias for all expression forms valid inside a `Placeable`.

### Signature
```python
type Expression = (
    SelectExpression
    | StringLiteral
    | NumberLiteral
    | VariableReference
    | MessageReference
    | TermReference
    | FunctionReference
    | Placeable
)
```

### Constraints
- Import: `from ftllexengine.syntax import Expression`
- Used by: `Placeable.expression`
- Purpose: closed union for parser, serializer, and visitor dispatch

---

## `SelectorExpression`

Type alias for expression forms valid as a `SelectExpression.selector`.

### Signature
```python
type SelectorExpression = (
    VariableReference | MessageReference | TermReference | FunctionReference | NumberLiteral
)
```

### Constraints
- Import: `from ftllexengine.syntax import SelectorExpression`
- Narrower than: `Expression`
- Purpose: encode the Fluent selector restriction at the type level

---

## `FTLLiteral`

Type alias for literal values allowed in named function and term arguments.

### Signature
```python
type FTLLiteral = StringLiteral | NumberLiteral
```

### Constraints
- Import: `from ftllexengine.syntax import FTLLiteral`
- Used by: `NamedArgument.value`
- Purpose: enforce the Fluent rule that named arguments are literal-only
