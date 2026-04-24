---
afad: "4.0"
version: "0.164.0"
domain: PARSING
updated: "2026-04-24"
route:
  keywords: [parse_ftl, serialize_ftl, validate_resource, FluentParserV1, Cursor, ASTVisitor, ASTTransformer, ParseError]
  questions: ["how do I parse FTL?", "what does validate_resource return?", "what syntax traversal helpers are public?", "where is the syntax parser API documented?"]
---

# Parsing Reference

This reference covers FTL syntax parsing, validation, serialization, cursor primitives, and AST traversal helpers.
Locale-aware number/date/currency parsing is documented in [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md).

## `parse_ftl`

Function that parses FTL source into a `Resource` AST.

### Signature
```python
def parse_ftl(source: str) -> Resource:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `source` | Y | Raw FTL source |

### Constraints
- Return: Parsed `Resource`
- Raises: Never for syntax junk; parse recovery is represented in the AST
- State: Pure
- Thread: Safe

---

## `parse_stream_ftl`

Function that yields parsed FTL entries from a line iterator.

### Signature
```python
def parse_stream_ftl(lines: Iterable[str]) -> Iterator[Entry]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `lines` | Y | Line-oriented FTL source |

### Constraints
- Return: Entry iterator in source order
- State: Streaming parse
- Thread: Safe

---

## `serialize_ftl`

Function that serializes a `Resource` AST back to FTL text.

### Signature
```python
def serialize_ftl(resource: Resource, *, validate: bool = True, max_depth: int = 100) -> str:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `resource` | Y | AST to serialize |
| `validate` | N | Validate before writing |
| `max_depth` | N | Serialization depth guard |

### Constraints
- Return: FTL source string
- Raises: `SerializationValidationError` or `SerializationDepthError`
- State: Pure
- Thread: Safe

---

## `validate_resource`

Function that validates FTL source without loading it into a runtime bundle.

### Signature
```python
def validate_resource(
    source: str,
    *,
    parser: FluentParserV1 | None = None,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
    known_msg_deps: Mapping[str, frozenset[str]] | None = None,
    known_term_deps: Mapping[str, frozenset[str]] | None = None,
) -> ValidationResult:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `source` | Y | Raw FTL source |
| `parser` | N | Parser override |
| `known_messages` | N | Cross-resource message ids |
| `known_terms` | N | Cross-resource term ids |
| `known_msg_deps` | N | Existing message deps |
| `known_term_deps` | N | Existing term deps |

### Constraints
- Return: `ValidationResult`
- State: Pure
- Thread: Safe

---

## `FluentParserV1`

Class that parses FTL source with configurable safety limits.

### Signature
```python
class FluentParserV1:
    def __init__(
        self,
        *,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
        max_parse_errors: int | None = None,
    ) -> None:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `max_source_size` | N | Input length bound |
| `max_nesting_depth` | N | Nesting safety bound |
| `max_parse_errors` | N | Recovery error bound |

### Constraints
- Return: Parser instance
- State: Reusable parser configuration
- Thread: Safe
- Main methods: `parse()`, `parse_stream()`

---

## `parse`

Function that aliases `ftllexengine.syntax.parse()` to `FluentParserV1.parse()`.

### Signature
```python
def parse(source: str) -> Resource:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `source` | Y | Raw FTL source |

### Constraints
- Import: `from ftllexengine.syntax import parse`
- Return: Parsed `Resource`
- Purpose: syntax-module convenience alias for parser-only tooling code
- State: Pure
- Thread: Safe

---

## `parse_stream`

Function that aliases `ftllexengine.syntax.parse_stream()` to `FluentParserV1.parse_stream()`.

### Signature
```python
def parse_stream(lines: Iterable[str]) -> Iterator[Entry]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `lines` | Y | Line-oriented FTL source |

### Constraints
- Import: `from ftllexengine.syntax import parse_stream`
- Return: Entry iterator in source order
- Purpose: syntax-module convenience alias for streaming parse workflows
- State: Streaming parse
- Thread: Safe

---

## `serialize`

Function that aliases `ftllexengine.syntax.serialize()` to the serializer implementation.

### Signature
```python
def serialize(resource: Resource, *, validate: bool = True, max_depth: int = 100) -> str:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `resource` | Y | AST to serialize |
| `validate` | N | Validate before writing |
| `max_depth` | N | Serialization depth guard |

### Constraints
- Import: `from ftllexengine.syntax import serialize`
- Return: FTL source string
- Raises: `SerializationValidationError` or `SerializationDepthError`
- Purpose: syntax-module serializer entry point
- State: Pure
- Thread: Safe

---

## `Cursor`

Class that tracks an immutable parse position inside LF-normalized source text.

### Signature
```python
class Cursor:
    def __init__(self, source: str, pos: int) -> None:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `source` | Y | LF-normalized source text |
| `pos` | Y | Character offset |

### Constraints
- Import: `from ftllexengine.syntax import Cursor`
- Purpose: parser-building primitive for forward-only source traversal
- Invariants: `0 <= pos <= len(source)`
- Helpers: `is_eof`, `current`, `peek()`, `advance()`, `compute_line_col()`
- State: Immutable
- Thread: Safe

---

## `ftllexengine.syntax.ParseResult`

Generic syntax-parser result object carrying both a parsed value and the next cursor.

### Signature
```python
@dataclass(frozen=True, slots=True)
class ParseResult[T]:
    value: T
    cursor: Cursor
```

### Constraints
- Import: `from ftllexengine.syntax import ParseResult`
- Distinct from: root `ParseResult[T]`, which is the locale-parsing `(value, errors)` alias
- Purpose: low-level parser-combinator result for syntax internals and tooling
- State: Immutable
- Thread: Safe

---

## `ParseError`

Immutable syntax parse error carrying a `Cursor` and optional expected-token list.

### Signature
```python
@dataclass(frozen=True, slots=True)
class ParseError:
    message: str
    cursor: Cursor
    expected: tuple[str, ...] = ()
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `message` | Y | Human-readable failure message |
| `cursor` | Y | Error location |
| `expected` | N | Expected token spellings |

### Constraints
- Import: `from ftllexengine.syntax import ParseError`
- Helpers: `format_error()`, `format_with_context()`
- Purpose: parser-building error object for tooling and low-level syntax helpers
- State: Immutable
- Thread: Safe

---

## `SerializationValidationError`

Exception raised when an AST would serialize into invalid Fluent syntax.

### Signature
```python
class SerializationValidationError(ValueError): ...
```

### Constraints
- Import: `from ftllexengine.syntax import SerializationValidationError`
- Typical triggers: invalid identifiers, duplicate named arguments, or non-literal named-argument values
- Raised by: `serialize()` when `validate=True`

---

## `SerializationDepthError`

Exception raised when serialization exceeds the configured AST nesting limit.

### Signature
```python
class SerializationDepthError(ValueError): ...
```

### Constraints
- Import: `from ftllexengine.syntax import SerializationDepthError`
- Typical trigger: adversarial or malformed AST nesting beyond `max_depth`
- Raised by: `serialize()`

---

## `ASTVisitor`

Generic base visitor class for read-only Fluent AST traversal.

### Signature
```python
class ASTVisitor[T = ASTNode]:
    def __init__(self, *, max_depth: int | None = None) -> None:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `max_depth` | N | Traversal depth guard |

### Constraints
- Import: `from ftllexengine.syntax import ASTVisitor`
- Purpose: subclass and override `visit_NodeType()` methods for analysis or linting
- Helpers: `visit()` dispatches by node type; `generic_visit()` traverses child nodes
- Depth: protected by `DepthGuard`
- Thread: Safe for independent visitor instances

---

## `ASTTransformer`

Generic base visitor class for Fluent AST rewrite passes.

### Signature
```python
class ASTTransformer(ASTVisitor[ASTNode | None | list[ASTNode]]):
    def __init__(self, *, max_depth: int | None = None) -> None:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `max_depth` | N | Traversal depth guard |

### Constraints
- Import: `from ftllexengine.syntax import ASTTransformer`
- Purpose: return replacement nodes, `None`, or node lists while walking the AST
- Typical use: transforms, migrations, or source-to-source rewrites before `serialize()`
- Depth: protected by `DepthGuard`
- Thread: Safe for independent transformer instances

---
