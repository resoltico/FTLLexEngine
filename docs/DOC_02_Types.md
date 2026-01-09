---
afad: "3.1"
version: "0.64.0"
domain: TYPES
updated: "2026-01-09"
route:
  keywords: [Resource, Message, Term, Pattern, Attribute, Placeable, AST, dataclass]
  questions: ["what AST nodes exist?", "how is FTL represented?", "what is the Resource structure?"]
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
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `elements` | `tuple[PatternElement, ...]` | Y | Text and placeable elements. |

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

    @staticmethod
    def guard(elem: object) -> TypeIs[TextElement]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `str` | Y | Plain text content. |

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

    @staticmethod
    def guard(elem: object) -> TypeIs[Placeable]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `expression` | `Expression` | Y | Contained expression. |

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
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `str` | Y | String content (without quotes). |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable string literal.
- State: Frozen dataclass.

---

## `NumberLiteral`

### Signature
```python
@dataclass(frozen=True, slots=True)
class NumberLiteral:
    value: int | float
    raw: str
    span: Span | None = None

    @staticmethod
    def guard(key: object) -> TypeIs[NumberLiteral]: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `int \| float` | Y | Parsed numeric value. |
| `raw` | `str` | Y | Original source representation for serialization. |
| `span` | `Span \| None` | N | Source position. |

### Constraints
- Return: Immutable number literal.
- State: Frozen dataclass.
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
- Raises: `DepthLimitExceededError` when traversal exceeds max_depth.
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
- Return: Modified node, None (removes), or list (expands).
- State: Maintains dispatch cache and depth guard.
- Thread: Not thread-safe (instance state).
- Subclass: MUST call `super().__init__()` to initialize depth guard.
- Raises: `DepthLimitExceededError` when traversal exceeds max_depth.
- Depth: Guard inherited from ASTVisitor.visit() (bypass-proof).
- Immutable: Uses `dataclasses.replace()` for node modifications.

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

### Signature
```python
type FluentValue = str | int | float | bool | Decimal | datetime | date | FluentNumber | None
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

### Constraints
- PEP 695 type alias. Export: `from ftllexengine import FluentValue`.
- Used for type-hinting resolver arguments: `args: dict[str, FluentValue]`.
- Location: `runtime/function_bridge.py`, exported from package root.

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
    positional_args: tuple[str, ...]
    named_args: frozenset[str]
    span: Span | None = None
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `name` | `str` | Y | Function name (e.g., 'NUMBER'). |
| `positional_args` | `tuple[str, ...]` | Y | Positional argument variable names. |
| `named_args` | `frozenset[str]` | Y | Named argument keys. |
| `span` | `Span \| None` | N | Source position for IDE integration. |

### Constraints
- Return: Immutable function call metadata.
- State: Frozen dataclass.
- Span: Populated from FunctionReference.span for parser-produced ASTs.
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
