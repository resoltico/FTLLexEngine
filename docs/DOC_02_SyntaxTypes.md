---
afad: "4.0"
version: "0.165.0"
domain: SYNTAX_TYPES
updated: "2026-04-24"
route:
  keywords: [AST, Resource, Message, Term, Pattern, Span, Annotation, syntax nodes]
  questions: ["how is FTL represented in the AST?", "which public AST container and declaration node types exist?", "where are spans and parser annotations documented?"]
---

# Syntax Types Reference

This reference covers the core AST containers and declaration nodes.
Pattern/expression/reference nodes and union aliases are documented in [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md).

## `Span`

Immutable source span in normalized character offsets.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int
```

### Constraints
- Import: `from ftllexengine.syntax import Span`
- Semantics: `start` is inclusive and `end` is exclusive, both in normalized character offsets
- Invariants: `start >= 0` and `end >= start`

---

## `Annotation`

Parser annotation attached to `Junk` nodes.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Annotation:
    code: str
    message: str
    arguments: tuple[tuple[str, str], ...] | None = None
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import Annotation`
- Purpose: preserves parser error metadata during recovery
- Used by: `Junk.annotations` and `ValidationResult.annotations`

---

## `Identifier`

Immutable AST node for Fluent identifiers.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Identifier:
    name: str
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import Identifier`
- Purpose: wraps identifier text so AST nodes can retain spans
- Helper: `Identifier.guard()` performs runtime narrowing

---

## `Resource`

Root AST node returned by `parse_ftl()`.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Resource:
    entries: tuple[Entry, ...]
```

### Constraints
- Import: `from ftllexengine.syntax import Resource`
- Purpose: immutable container for top-level Fluent entries in source order

---

## `Message`

AST node for a public Fluent message.

### Signature
```python
@dataclass(frozen=True, slots=True, weakref_slot=True)
class Message:
    id: Identifier
    value: Pattern | None
    attributes: tuple[Attribute, ...]
    comment: Comment | None = None
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import Message`
- Invariant: a message must have `value`, `attributes`, or both
- Helper: `Message.guard()` performs runtime narrowing

---

## `Term`

AST node for a private Fluent term.

### Signature
```python
@dataclass(frozen=True, slots=True, weakref_slot=True)
class Term:
    id: Identifier
    value: Pattern
    attributes: tuple[Attribute, ...]
    comment: Comment | None = None
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import Term`
- Invariant: a term always has a `value`
- Helper: `Term.guard()` performs runtime narrowing

---

## `Attribute`

AST node for a message or term attribute.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Attribute:
    id: Identifier
    value: Pattern
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import Attribute`
- Used on: `Message.attributes` and `Term.attributes`

---

## `Comment`

AST node for Fluent comments.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Comment:
    content: str
    type: CommentType
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import Comment`
- `type` uses `CommentType`
- Helper: `Comment.guard()` performs runtime narrowing

---

## `Junk`

AST node for unparseable content preserved during recovery.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Junk:
    content: str
    annotations: tuple[Annotation, ...] = ()
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import Junk`
- Purpose: keeps invalid source and its parser annotations available to tooling
- Helper: `Junk.guard()` performs runtime narrowing

---

## `Pattern`

AST node for a sequence of literal text and placeables.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Pattern:
    elements: tuple[PatternElement, ...]
    span: Span | None = None
```

### Constraints
- Import: `from ftllexengine.syntax import Pattern`
- Used by: `Message.value`, `Term.value`, `Attribute.value`, `Variant.value`

---
