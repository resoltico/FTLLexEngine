---
afad: "3.1"
version: "0.116.0"
domain: TYPES
updated: "2026-02-20"
route:
  keywords: [Resource, Message, Term, Pattern, Attribute, Placeable, AST, dataclass, FluentValue, TerritoryInfo, CurrencyInfo, ISO 3166, ISO 4217]
  questions: ["what AST nodes exist?", "how is FTL represented?", "what is the Resource structure?", "what types can FluentValue hold?", "how to get territory info?", "how to get currency info?"]
---

# AST Types Reference

---

## `Resource`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Resource:
    entries: tuple[Entry, ...]
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `entries` | `tuple[Entry, ...]` | Y | All top-level entries. |

### Constraints
- Return: Immutable root AST node.
- State: Frozen dataclass.

---

## `Message`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Message:
    id: Identifier
    value: Pattern | None
    attributes: tuple[Attribute, ...]
    comment: Comment | None = None
    span: Span | None = None

    @staticmethod
    def guard(entry: object) -> TypeIs[Message]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `id` | `Identifier` | Y | Message identifier. |
| `value` | `Pattern \| None` | Y | Message value pattern. |
| `attributes` | `tuple[Attribute, ...]` | Y | Message attributes. |
| `comment` | `Comment \| None` | N | Associated comment. |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable message node.
- State: Frozen dataclass.
- Validation: `__post_init__` validates that value or attributes is non-empty. Raises `ValueError` if both value is None and attributes is empty.

---

## `Term`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Term:
    id: Identifier
    value: Pattern
    attributes: tuple[Attribute, ...]
    comment: Comment | None = None
    span: Span | None = None

    @staticmethod
    def guard(entry: object) -> TypeIs[Term]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `id` | `Identifier` | Y | Term identifier (without - prefix). |
| `value` | `Pattern` | Y | Term value pattern (required). |
| `attributes` | `tuple[Attribute, ...]` | Y | Term attributes. |
| `comment` | `Comment \| None` | N | Associated comment. |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable term node.
- State: Frozen dataclass.
- Validation: `__post_init__` validates that value is not None. Raises `ValueError` if value is None.

---

## `Attribute`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Attribute:
    id: Identifier
    value: Pattern
    span: Span | None = None
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `id` | `Identifier` | Y | Attribute name. |
| `value` | `Pattern` | Y | Attribute value pattern. |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable attribute node.
- State: Frozen dataclass.

---

## `Comment`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Comment:
    content: str
    type: CommentType
    span: Span | None = None

    @staticmethod
    def guard(entry: object) -> TypeIs[Comment]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `content` | `str` | Y | Comment text. |
| `type` | `CommentType` | Y | COMMENT, GROUP, or RESOURCE. |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable comment node.
- State: Frozen dataclass.

---

## `Junk`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Junk:
    content: str
    annotations: tuple[Annotation, ...] = ()
    span: Span | None = None

    @staticmethod
    def guard(entry: object) -> TypeIs[Junk]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `content` | `str` | Y | Unparseable source text. |
| `annotations` | `tuple[Annotation, ...]` | N | Parse error annotations. |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable junk node.
- State: Frozen dataclass.

---

## `Pattern`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Pattern:
    elements: tuple[PatternElement, ...]
    span: Span | None = None
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `elements` | `tuple[PatternElement, ...]` | Y | Text and placeable elements. |
| `span` | `Span \| None` | N | Source location span. |

### Constraints
- Return: Immutable pattern node.
- State: Frozen dataclass.

---

## `TextElement`

### Signature
```python
@dataclass(frozen=True, slots=True)
class TextElement:
    value: str
    span: Span | None = None

    @staticmethod
    def guard(elem: object) -> TypeIs[TextElement]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `str` | Y | Plain text content. |
| `span` | `Span \| None` | N | Source location span. |

### Constraints
- Return: Immutable text element.
- State: Frozen dataclass.

---

## `Placeable`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Placeable:
    expression: Expression
    span: Span | None = None

    @staticmethod
    def guard(elem: object) -> TypeIs[Placeable]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `expression` | `Expression` | Y | Contained expression. |
| `span` | `Span \| None` | N | Source location span. |

### Constraints
- Return: Immutable placeable node.
- State: Frozen dataclass.

---

## `SelectExpression`

### Signature
```python
@dataclass(frozen=True, slots=True)
class SelectExpression:
    selector: InlineExpression
    variants: tuple[Variant, ...]
    span: Span | None = None

    @staticmethod
    def guard(expr: object) -> TypeIs[SelectExpression]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `selector` | `InlineExpression` | Y | Value to select on. |
| `variants` | `tuple[Variant, ...]` | Y | Selection variants. |
| `span` | `Span \| None` | N | Source position (start/end). |

### Constraints
- Return: Immutable select expression.
- State: Frozen dataclass.
- Validation: `__post_init__` validates that variants is non-empty and exactly one default variant exists. Raises `ValueError` on constraint violation.

---

## `Variant`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Variant:
    key: VariantKey
    value: Pattern
    default: bool = False
    span: Span | None = None
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `key` | `VariantKey` | Y | Variant key (Identifier or NumberLiteral). |
| `value` | `Pattern` | Y | Variant pattern. |
| `default` | `bool` | N | True for default variant (*). |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable variant node.
- State: Frozen dataclass.

---

## `StringLiteral`

### Signature
```python
@dataclass(frozen=True, slots=True)
class StringLiteral:
    value: str
    span: Span | None = None

    @staticmethod
    def guard(key: object) -> TypeIs[StringLiteral]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `str` | Y | String content (without quotes). |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable string literal.
- State: Frozen dataclass.
- Guard: `StringLiteral.guard(obj)` returns `TypeIs[StringLiteral]` for type narrowing.

---

## `NumberLiteral`

### Signature
```python
from decimal import Decimal

@dataclass(frozen=True, slots=True)
class NumberLiteral:
    value: int | Decimal
    raw: str
    span: Span | None = None

    @staticmethod
    def guard(key: object) -> TypeIs[NumberLiteral]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `int \| Decimal` | Y | Parsed numeric value (int for integers, Decimal for decimals). |
| `raw` | `str` | Y | Original source representation for serialization. |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable number literal.
- State: Frozen dataclass.
- Precision: Integer literals use `int` for memory efficiency. Decimal literals use `Decimal` for financial-grade precision, eliminating float rounding errors (0.1 + 0.2 = 0.3, not 0.30000000000000004).
- Invariant: AST transformers creating new nodes must ensure raw represents value. Parser guarantees consistency at construction.

---

## `VariableReference`

### Signature
```python
@dataclass(frozen=True, slots=True)
class VariableReference:
    id: Identifier
    span: Span | None = None

    @staticmethod
    def guard(expr: object) -> TypeIs[VariableReference]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `id` | `Identifier` | Y | Variable identifier (without $). |
| `span` | `Span \| None` | N | Source position for IDE integration. |

### Constraints
- Return: Immutable variable reference.
- State: Frozen dataclass.
- Span: Populated by parser for source-tracked ASTs.

---

## `MessageReference`

### Signature
```python
@dataclass(frozen=True, slots=True)
class MessageReference:
    id: Identifier
    attribute: Identifier | None = None
    span: Span | None = None

    @staticmethod
    def guard(expr: object) -> TypeIs[MessageReference]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `id` | `Identifier` | Y | Message identifier. |
| `attribute` | `Identifier \| None` | N | Attribute name if present. |
| `span` | `Span \| None` | N | Source position for IDE integration. |

### Constraints
- Return: Immutable message reference.
- State: Frozen dataclass.
- Span: Populated by parser for source-tracked ASTs.

---

## `TermReference`

### Signature
```python
@dataclass(frozen=True, slots=True)
class TermReference:
    id: Identifier
    attribute: Identifier | None = None
    arguments: CallArguments | None = None
    span: Span | None = None

    @staticmethod
    def guard(expr: object) -> TypeIs[TermReference]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `id` | `Identifier` | Y | Term identifier (without -). |
| `attribute` | `Identifier \| None` | N | Attribute name if present. |
| `arguments` | `CallArguments \| None` | N | Parameterized term args. |
| `span` | `Span \| None` | N | Source position for IDE integration. |

### Constraints
- Return: Immutable term reference.
- State: Frozen dataclass.
- Span: Populated by parser for source-tracked ASTs.

---

## `FunctionReference`

### Signature
```python
@dataclass(frozen=True, slots=True)
class FunctionReference:
    id: Identifier
    arguments: CallArguments
    span: Span | None = None

    @staticmethod
    def guard(expr: object) -> TypeIs[FunctionReference]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `id` | `Identifier` | Y | Function name (e.g., NUMBER). |
| `arguments` | `CallArguments` | Y | Function arguments. |
| `span` | `Span \| None` | N | Source position for IDE integration. |

### Constraints
- Return: Immutable function reference.
- State: Frozen dataclass.
- Span: Populated by parser for source-tracked ASTs.

---

## `CallArguments`

### Signature
```python
@dataclass(frozen=True, slots=True)
class CallArguments:
    positional: tuple[InlineExpression, ...]
    named: tuple[NamedArgument, ...]
    span: Span | None = None
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `positional` | `tuple[InlineExpression, ...]` | Y | Positional arguments. |
| `named` | `tuple[NamedArgument, ...]` | Y | Named arguments. |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable call arguments.
- State: Frozen dataclass.
- Validation: `serialize(validate=True)` rejects duplicate named argument names.

---

## `NamedArgument`

### Signature
```python
@dataclass(frozen=True, slots=True)
class NamedArgument:
    name: Identifier
    value: InlineExpression
    span: Span | None = None
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `name` | `Identifier` | Y | Argument name. |
| `value` | `InlineExpression` | Y | Argument value. |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable named argument.
- State: Frozen dataclass.
- FTL EBNF: `NamedArgument ::= Identifier blank? ":" blank? (StringLiteral | NumberLiteral)`.
- Validation: `serialize(validate=True)` rejects values that are not StringLiteral or NumberLiteral.

---

## `Identifier`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Identifier:
    name: str
    span: Span | None = None

    @staticmethod
    def guard(key: object) -> TypeIs[Identifier]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `name` | `str` | Y | Identifier string. |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable identifier.
- State: Frozen dataclass.

---

## `Span`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `start` | `int` | Y | Start character offset (inclusive). |
| `end` | `int` | Y | End character offset (exclusive). |

### Constraints
- Return: Immutable span.
- Raises: `ValueError` if start < 0 or end < start.
- State: Frozen dataclass.
- Note: Positions are character offsets (code points), not bytes.

---

## `Annotation`

### Signature
```python
@dataclass(frozen=True, slots=True)
class Annotation:
    code: str
    message: str
    arguments: tuple[tuple[str, str], ...] | None = None
    span: Span | None = None
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `code` | `str` | Y | Error code. |
| `message` | `str` | Y | Error message. |
| `arguments` | `tuple[tuple[str, str], ...] \| None` | N | Additional context as key-value pairs. |
| `span` | `Span \| None` | N | Error location. |

### Constraints
- Return: Immutable annotation.
- State: Frozen dataclass.

---

## `ASTVisitor`

### Signature
```python
class ASTVisitor[T = ASTNode]:
    def __init__(self, *, max_depth: int | None = None) -> None: ...
    def visit(self, node: ASTNode) -> T: ...
    def generic_visit(self, node: ASTNode) -> T: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `max_depth` | `int \| None` | N | Maximum traversal depth (default: 100). |

### Constraints
- Return: Visited/transformed node.
- State: Maintains dispatch cache and depth guard.
- Thread: Not thread-safe (instance state).
- Subclass: MUST call `super().__init__()` to initialize depth guard.
- Raises: `FrozenFluentError` (category=RESOLUTION) when traversal exceeds max_depth.
- Depth: Guard in `visit()` protects all traversals (bypass-proof).

---

## `ASTTransformer`

### Signature
```python
class ASTTransformer(ASTVisitor[ASTNode | None | list[ASTNode]]):
    def __init__(self, *, max_depth: int | None = None) -> None: ...
    def transform(self, node: ASTNode) -> ASTNode | None | list[ASTNode]: ...
    def generic_visit(self, node: ASTNode) -> ASTNode | None | list[ASTNode]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `max_depth` | `int \| None` | N | Maximum traversal depth (default: 100). |

### Constraints
- Return: Modified node, None (removes from optional fields or collections), or list (expands in collections).
- State: Maintains dispatch cache and depth guard.
- Thread: Not thread-safe (instance state).
- Subclass: MUST call `super().__init__()` to initialize depth guard.
- Raises: `FrozenFluentError` (category=RESOLUTION) when traversal exceeds max_depth. `TypeError` if visit method returns None for required scalar field, list for any scalar field, or a node whose type does not match the field's expected types.
- Depth: Guard inherited from ASTVisitor.visit() (bypass-proof).
- Immutable: Uses `dataclasses.replace()` for node modifications.
- Type Validation: `_transform_list` validates that each transformed node matches the field's expected types. For example, `Pattern.elements` accepts only `TextElement | Placeable`; producing a `Message` raises `TypeError` identifying the field and unexpected type.
- Required Fields: `Message.id`, `Term.id`, `Term.value`, `Placeable.expression`, `Variant.key`, `Variant.value`, etc. require single ASTNode return. Returning None or list raises TypeError.
- Optional Fields: `Message.comment`, `Message.value`, `Term.comment`, `MessageReference.attribute`, `TermReference.attribute`, `TermReference.arguments` accept None returns for node removal. Returning list still raises TypeError.

---

## `MessageIntrospection`

### Signature
```python
@dataclass(frozen=True, slots=True)
class MessageIntrospection:
    message_id: str
    variables: frozenset[VariableInfo]
    functions: frozenset[FunctionCallInfo]
    references: frozenset[ReferenceInfo]
    has_selectors: bool

    def get_variable_names(self) -> frozenset[str]: ...
    def requires_variable(self, name: str) -> bool: ...
    def get_function_names(self) -> frozenset[str]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier. |
| `variables` | `frozenset[VariableInfo]` | Y | Variable references. |
| `functions` | `frozenset[FunctionCallInfo]` | Y | Function calls. |
| `references` | `frozenset[ReferenceInfo]` | Y | Message/term references. |
| `has_selectors` | `bool` | Y | Uses select expressions. |

### Constraints
- Return: Immutable introspection result.
- State: Frozen dataclass.
- Import: `from ftllexengine.introspection import MessageIntrospection`

---

## `introspect_message`

Function that extracts complete metadata from a Message or Term AST node.

### Signature
```python
def introspect_message(
    message: Message | Term,
    *,
    use_cache: bool = True,
) -> MessageIntrospection:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message` | `Message \| Term` | Y | AST node to introspect. |
| `use_cache` | `bool` | N | Use WeakKeyDictionary cache (default: True). |

### Constraints
- Return: MessageIntrospection with variables, functions, references.
- Raises: `TypeError` if message is not Message or Term.
- State: Caches result in WeakKeyDictionary when use_cache=True.
- Thread: Safe (worst case: redundant computation on cache miss).
- Cache: WeakKeyDictionary auto-cleans when AST nodes garbage collected.
- Import: `from ftllexengine.introspection import introspect_message`

---

## `clear_introspection_cache`

Function that clears the introspection WeakKeyDictionary cache.

### Signature
```python
def clear_introspection_cache() -> None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: None.
- Raises: Never.
- State: Clears module-level introspection cache.
- Thread: Safe.
- Usage: Testing, memory pressure. Normal usage relies on WeakKeyDictionary auto-cleanup.
- Import: `from ftllexengine.introspection import clear_introspection_cache`

---

## `extract_variables`

Function that extracts variable names from a Message or Term (simplified API).

### Signature
```python
def extract_variables(message: Message | Term) -> frozenset[str]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message` | `Message \| Term` | Y | AST node to analyze. |

### Constraints
- Return: Frozen set of variable names (without $ prefix).
- Raises: Never.
- State: Delegates to introspect_message (uses cache).
- Thread: Safe.
- Import: `from ftllexengine.introspection import extract_variables`

---

## `extract_references`

Function that extracts message and term references from a Message or Term.

### Signature
```python
def extract_references(entry: Message | Term) -> tuple[frozenset[str], frozenset[str]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `entry` | `Message \| Term` | Y | AST node to analyze. |

### Constraints
- Return: `(message_refs, term_refs)` — two frozen sets. `message_refs` may be attribute-qualified (e.g., `"msg.tooltip"`). `term_refs` are bare IDs (e.g., `"brand"`).
- Raises: Never.
- State: No cache. Traverses the AST on every call.
- Thread: Safe (no shared mutable state).
- Import: `from ftllexengine.introspection import extract_references`

```python
resource = parse_ftl("msg = { welcome } uses { -brand }")
msg_refs, term_refs = extract_references(resource.entries[0])
# msg_refs == frozenset({"welcome"})
# term_refs == frozenset({"brand"})
```

---

## `extract_references_by_attribute`

Function that extracts references per source attribute for attribute-granular analysis.

### Signature
```python
def extract_references_by_attribute(
    entry: Message | Term,
) -> dict[str | None, tuple[frozenset[str], frozenset[str]]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `entry` | `Message \| Term` | Y | AST node to analyze. |

### Constraints
- Return: `{key: (message_refs, term_refs)}`. Key is `None` for the value pattern, or the attribute name string (e.g., `"tooltip"`).
- Raises: Never.
- State: No cache. Traverses the AST on every call.
- Thread: Safe.
- Use case: Attribute-granular dependency cycle detection. Finer-grained than `extract_references`.
- Import: `from ftllexengine.introspection import extract_references_by_attribute`

```python
resource = parse_ftl("btn = Click\n    .label = { -brand } button")
refs = extract_references_by_attribute(resource.entries[0])
# refs[None] == (frozenset(), frozenset())          # value pattern
# refs["label"] == (frozenset(), frozenset({"brand"}))  # attribute
```

---

## Type Aliases

### Signature
```python
type Entry = Message | Term | Comment | Junk
type PatternElement = TextElement | Placeable
type Expression = SelectExpression | InlineExpression
type InlineExpression = (
    StringLiteral | NumberLiteral | VariableReference |
    MessageReference | TermReference | FunctionReference | Placeable
)
type VariantKey = Identifier | NumberLiteral
type ASTNode = Resource | Message | Term | ... # Union of all AST types
```

### Constraints
- PEP 695 type aliases. Cannot use with isinstance().
- Use pattern matching or .guard() methods for runtime checks.

---

## `FluentValue`

Type alias for values passable to Fluent functions and format_pattern().

### Signature
```python
type FluentValue = (
    str | int | float | bool | Decimal | datetime | date | FluentNumber | None |
    Sequence["FluentValue"] | Mapping[str, "FluentValue"]
)
```

### Parameters
| Type | Description |
|:-----|:------------|
| `str` | String arguments. |
| `int` | Integer arguments. |
| `float` | Floating-point arguments. |
| `bool` | Boolean arguments. |
| `Decimal` | Precise decimal arguments (currency). |
| `datetime` | Date-time arguments. |
| `date` | Date-only arguments. |
| `FluentNumber` | Formatted number from NUMBER() function. |
| `None` | Absent/null arguments. |
| `Sequence["FluentValue"]` | Lists, tuples of FluentValue (recursive). |
| `Mapping[str, "FluentValue"]` | Dicts with string keys (recursive). |

### Constraints
- PEP 695 recursive type alias. Export: `from ftllexengine import FluentValue`.
- Used for type-hinting resolver arguments: `args: dict[str, FluentValue]`.
- Collections: Arbitrarily nested structures supported (e.g., `{"items": [1, 2, {"nested": "value"}]}`).
- Cache: Collections handled correctly by `_make_hashable()` for cache key generation.
- Location: `runtime/value_types.py`, exported from package root.

---

## `VariableInfo`

### Signature
```python
@dataclass(frozen=True, slots=True)
class VariableInfo:
    name: str
    context: VariableContext
    span: Span | None = None
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `name` | `str` | Y | Variable name (without $ prefix). |
| `context` | `VariableContext` | Y | Context where variable appears. |
| `span` | `Span \| None` | N | Source position for IDE integration. |

### Constraints
- Return: Immutable variable metadata.
- State: Frozen dataclass.
- Span: Populated from VariableReference.span for parser-produced ASTs.
- Import: `from ftllexengine.introspection import VariableInfo`

---

## `FunctionCallInfo`

### Signature
```python
@dataclass(frozen=True, slots=True)
class FunctionCallInfo:
    name: str
    positional_arg_vars: tuple[str, ...]
    named_args: frozenset[str]
    span: Span | None = None
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `name` | `str` | Y | Function name (e.g., 'NUMBER'). |
| `positional_arg_vars` | `tuple[str, ...]` | Y | Variable names used as positional arguments (excludes literals). |
| `named_args` | `frozenset[str]` | Y | Named argument keys. |
| `span` | `Span \| None` | N | Source position for IDE integration. |

### Constraints
- Return: Immutable function call metadata.
- State: Frozen dataclass.
- Span: Populated from FunctionReference.span for parser-produced ASTs.
- positional_arg_vars: Contains only VariableReference names; literals and other expressions not included.
- Import: `from ftllexengine.introspection import FunctionCallInfo`

---

## `ReferenceInfo`

### Signature
```python
@dataclass(frozen=True, slots=True)
class ReferenceInfo:
    id: str
    kind: ReferenceKind
    attribute: str | None
    span: Span | None = None
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `id` | `str` | Y | Referenced message or term ID. |
| `kind` | `ReferenceKind` | Y | Reference type (MESSAGE or TERM). |
| `attribute` | `str \| None` | N | Attribute name if present. |
| `span` | `Span \| None` | N | Source position for IDE integration. |

### Constraints
- Return: Immutable reference metadata.
- State: Frozen dataclass.
- Span: Populated from MessageReference.span or TermReference.span for parser-produced ASTs.
- Import: `from ftllexengine.introspection import ReferenceInfo`

---

## `CommentType`

### Signature
```python
class CommentType(StrEnum):
    COMMENT = "comment"
    GROUP = "group"
    RESOURCE = "resource"
```

### Parameters
| Value | Description |
|:------|:------------|
| `COMMENT` | Standalone comment: `# text` |
| `GROUP` | Group comment: `## text` |
| `RESOURCE` | Resource comment: `### text` |

### Constraints
- StrEnum: Members ARE strings. `str(CommentType.COMMENT) == "comment"`
- Import: `from ftllexengine.enums import CommentType`

---

## `VariableContext`

### Signature
```python
class VariableContext(StrEnum):
    PATTERN = "pattern"
    SELECTOR = "selector"
    VARIANT = "variant"
    FUNCTION_ARG = "function_arg"
```

### Parameters
| Value | Description |
|:------|:------------|
| `PATTERN` | Variable in message pattern. |
| `SELECTOR` | Variable in select expression selector. |
| `VARIANT` | Variable in select variant. |
| `FUNCTION_ARG` | Variable in function argument. |

### Constraints
- StrEnum: Members ARE strings. `str(VariableContext.PATTERN) == "pattern"`
- Import: `from ftllexengine.enums import VariableContext`

---

## `ReferenceKind`

### Signature
```python
class ReferenceKind(StrEnum):
    MESSAGE = "message"
    TERM = "term"
```

### Parameters
| Value | Description |
|:------|:------------|
| `MESSAGE` | Reference to a message: `{ message-id }` |
| `TERM` | Reference to a term: `{ -term-id }` |

### Constraints
- StrEnum: Members ARE strings. `str(ReferenceKind.MESSAGE) == "message"`
- Import: `from ftllexengine.enums import ReferenceKind`

---

## ISO Introspection Types

The introspection module provides type-safe access to ISO 3166 (territories) and ISO 4217 (currencies) data via Babel CLDR. Requires Babel installation: `pip install ftllexengine[babel]`.

---

## `TerritoryCode`

Type alias for ISO 3166-1 alpha-2 territory codes.

### Signature
```python
type TerritoryCode = str
```

### Constraints
- Purpose: Type annotation for territory codes (e.g., "US", "LV", "DE").
- Validation: Use `is_valid_territory_code()` to verify.
- Import: `from ftllexengine.introspection import TerritoryCode`

---

## `CurrencyCode`

Type alias for ISO 4217 currency codes.

### Signature
```python
type CurrencyCode = str
```

### Constraints
- Purpose: Type annotation for currency codes (e.g., "USD", "EUR", "GBP").
- Validation: Use `is_valid_currency_code()` to verify.
- Import: `from ftllexengine.introspection import CurrencyCode`

---

## `TerritoryInfo`

ISO 3166-1 territory data with localized name.

### Signature
```python
@dataclass(frozen=True, slots=True)
class TerritoryInfo:
    alpha2: TerritoryCode
    name: str
    currencies: tuple[CurrencyCode, ...]
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `alpha2` | `TerritoryCode` | Y | ISO 3166-1 alpha-2 code |
| `name` | `str` | Y | Localized display name |
| `currencies` | `tuple[CurrencyCode, ...]` | Y | Currency codes in priority order (may be empty) |

### Constraints
- Return: Immutable territory data.
- State: Frozen dataclass.
- Thread: Safe.
- Hashable: Yes.
- Multi-Currency: Territories may have multiple legal tender currencies (e.g., Panama: PAB, USD).
- Import: `from ftllexengine.introspection import TerritoryInfo`

---

## `CurrencyInfo`

ISO 4217 currency data with localized presentation.

### Signature
```python
@dataclass(frozen=True, slots=True)
class CurrencyInfo:
    code: CurrencyCode
    name: str
    symbol: str
    decimal_digits: int
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `code` | `CurrencyCode` | Y | ISO 4217 currency code |
| `name` | `str` | Y | Localized display name |
| `symbol` | `str` | Y | Locale-specific symbol |
| `decimal_digits` | `int` | Y | Standard decimal places (0, 2, 3, or 4) |

### Constraints
- Return: Immutable currency data.
- State: Frozen dataclass.
- Thread: Safe.
- Hashable: Yes.
- Import: `from ftllexengine.introspection import CurrencyInfo`

---

## `get_territory`

Look up ISO 3166-1 territory by alpha-2 code.

### Signature
```python
def get_territory(
    code: str,
    locale: str = "en",
) -> TerritoryInfo | None:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `code` | `str` | Y | ISO 3166-1 alpha-2 code (case-insensitive) |
| `locale` | `str` | N | Locale for name localization (default: "en") |

### Constraints
- Return: TerritoryInfo if found, None if unknown.
- Raises: `BabelImportError` if Babel not installed.
- State: Bounded cache per normalized (code, locale) pair.
- Thread: Safe.
- Normalization: Code uppercased, locale normalized (BCP-47/POSIX/lowercase accepted).
- Import: `from ftllexengine.introspection import get_territory`

---

## `get_currency`

Look up ISO 4217 currency by code.

### Signature
```python
def get_currency(
    code: str,
    locale: str = "en",
) -> CurrencyInfo | None:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `code` | `str` | Y | ISO 4217 currency code (case-insensitive) |
| `locale` | `str` | N | Locale for name/symbol localization (default: "en") |

### Constraints
- Return: CurrencyInfo if found, None if unknown.
- Raises: `BabelImportError` if Babel not installed.
- State: Bounded cache per normalized (code, locale) pair.
- Thread: Safe.
- Normalization: Code uppercased, locale normalized (BCP-47/POSIX/lowercase accepted).
- Import: `from ftllexengine.introspection import get_currency`

---

## `list_territories`

List all known ISO 3166-1 territories.

### Signature
```python
def list_territories(
    locale: str = "en",
) -> frozenset[TerritoryInfo]:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `locale` | `str` | N | Locale for name localization (default: "en") |

### Constraints
- Return: Frozen set of all TerritoryInfo objects.
- Raises: `BabelImportError` if Babel not installed.
- State: Bounded cache per normalized locale.
- Thread: Safe.
- Normalization: Locale normalized (BCP-47/POSIX/lowercase accepted).
- Import: `from ftllexengine.introspection import list_territories`

---

## `list_currencies`

List all known ISO 4217 currencies.

### Signature
```python
def list_currencies(
    locale: str = "en",
) -> frozenset[CurrencyInfo]:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `locale` | `str` | N | Locale for name/symbol localization (default: "en") |

### Constraints
- Return: Frozen set of all CurrencyInfo objects.
- Raises: `BabelImportError` if Babel not installed.
- State: Bounded cache per normalized locale.
- Thread: Safe.
- Normalization: Locale normalized (BCP-47/POSIX/lowercase accepted).
- Consistency: Same currency count across all locales (uses English fallback for localized names).
- Import: `from ftllexengine.introspection import list_currencies`

---

## `get_territory_currencies`

Get all currencies for a territory in priority order.

### Signature
```python
def get_territory_currencies(territory: str) -> tuple[CurrencyCode, ...]:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `territory` | `str` | Y | ISO 3166-1 alpha-2 code (case-insensitive) |

### Constraints
- Return: Tuple of ISO 4217 currency codes (empty if unknown territory).
- Raises: `BabelImportError` if Babel not installed.
- State: Bounded cache per normalized territory code.
- Thread: Safe.
- Normalization: Territory code uppercased internally.
- Multi-Currency: Returns all legal tender currencies, primary first (e.g., Panama: ("PAB", "USD")).
- Import: `from ftllexengine.introspection import get_territory_currencies`
- Version: Changed from list to tuple in v0.91.0.

---

## `is_valid_territory_code`

Check if string is a valid ISO 3166-1 alpha-2 code.

### Signature
```python
def is_valid_territory_code(value: str) -> TypeIs[TerritoryCode]:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `value` | `str` | Y | String to validate |

### Constraints
- Return: True if known ISO 3166-1 alpha-2 code.
- Raises: `BabelImportError` if Babel not installed.
- State: Uses cached territory lookups.
- Thread: Safe.
- TypeIs: Narrows type in type checkers.
- Import: `from ftllexengine.introspection import is_valid_territory_code`

---

## `is_valid_currency_code`

Check if string is a valid ISO 4217 currency code.

### Signature
```python
def is_valid_currency_code(value: str) -> TypeIs[CurrencyCode]:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `value` | `str` | Y | String to validate |

### Constraints
- Return: True if known ISO 4217 currency code.
- Raises: `BabelImportError` if Babel not installed.
- State: Uses cached currency lookups.
- Thread: Safe.
- TypeIs: Narrows type in type checkers.
- Import: `from ftllexengine.introspection import is_valid_currency_code`

---

## `clear_iso_cache`

Clear all ISO introspection caches.

### Signature
```python
def clear_iso_cache() -> None:
```

### Constraints
- Return: None.
- Raises: Never.
- State: Clears all bounded ISO introspection caches.
- Thread: Safe.
- Usage: Testing, memory pressure, locale configuration changes.
- Import: `from ftllexengine.introspection import clear_iso_cache`

---
