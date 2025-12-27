---
spec_version: AFAD-v1
project_version: 0.35.0
context: INDEX
last_updated: 2025-12-26T18:00:00Z
maintainer: claude-opus-4-5
retrieval_hints:
  keywords: [api reference, documentation, exports, imports, fluentbundle, fluentlocalization]
  answers: [api documentation, what classes available, how to import, module exports]
  related: [DOC_01_Core.md, DOC_02_Types.md, DOC_03_Parsing.md, DOC_04_Runtime.md, DOC_05_Errors.md, DOC_06_Testing.md]
---

# FTLLexEngine API Reference Index

## Module Exports

### Root Exports (`from ftllexengine import ...`)
```python
from ftllexengine import (
    # Core API
    FluentBundle,
    FluentLocalization,
    parse_ftl,
    serialize_ftl,
    # Errors
    FluentError,
    FluentSyntaxError,
    FluentReferenceError,
    FluentResolutionError,
    # Metadata
    __version__,
    __fluent_spec_version__,
    __spec_url__,
    __recommended_encoding__,
)
```

### AST Types (`from ftllexengine.syntax.ast import ...`)
```python
from ftllexengine.syntax.ast import (
    Resource, Message, Term, Pattern, Attribute,
    Placeable, TextElement, Identifier, Junk, Comment,
    VariableReference, MessageReference, TermReference, FunctionReference,
    SelectExpression, Variant, NumberLiteral, StringLiteral,
    CallArguments, NamedArgument, Span, Annotation,
    # Type aliases (PEP 695)
    Entry, Expression, PatternElement, InlineExpression, VariantKey,
)
```

### Syntax Utilities (`from ftllexengine.syntax import ...`)
```python
from ftllexengine.syntax import (
    FluentParserV1, ASTVisitor, ASTTransformer,
    Cursor, ParseError, ParseResult,
    parse, serialize, SerializationValidationError,
)
```

### Errors & Validation (`from ftllexengine.diagnostics import ...`)
```python
from ftllexengine.diagnostics import (
    FluentError, FluentSyntaxError, FluentReferenceError,
    FluentResolutionError, FluentCyclicReferenceError,
    ValidationResult, ValidationError, ValidationWarning,
    DiagnosticFormatter, OutputFormat,  # v0.31.0+
)
```

### Introspection (`from ftllexengine.introspection import ...`)
```python
from ftllexengine.introspection import (
    introspect_message, MessageIntrospection,
    extract_variables, extract_references,
    ReferenceExtractor, IntrospectionVisitor,
    VariableInfo, FunctionCallInfo, ReferenceInfo,
)
```

### Enums (`from ftllexengine.enums import ...`)
```python
from ftllexengine.enums import (
    CommentType,       # COMMENT, GROUP, RESOURCE
    VariableContext,   # PATTERN, SELECTOR, VARIANT, FUNCTION_ARG
    ReferenceKind,     # MESSAGE, TERM
)
```

### Analysis (`from ftllexengine.analysis import ...`)
```python
from ftllexengine.analysis import detect_cycles
from ftllexengine.analysis.graph import build_dependency_graph
```

### Validation (`from ftllexengine.validation import ...`)
```python
from ftllexengine.validation import validate_resource
```

### Visitor (`from ftllexengine.syntax.visitor import ...`)
```python
from ftllexengine.syntax.visitor import ASTVisitor
```

### Runtime (`from ftllexengine.runtime import ...`)
```python
from ftllexengine.runtime import (
    FluentBundle, FluentResolver, FunctionRegistry, ResolutionContext,
    create_default_registry, get_shared_registry,  # v0.31.0+
    number_format, datetime_format, currency_format,
    select_plural_category,
)
```

### Localization (`from ftllexengine.localization import ...`)
```python
from ftllexengine.localization import (
    FluentLocalization, PathResourceLoader, ResourceLoader,
    LoadStatus, LoadSummary, ResourceLoadResult,  # v0.31.0+
    MessageId, LocaleCode, ResourceId, FTLSource,
)
```

---

## File Routing Table

| Query Pattern | Target File | Domain |
|:--------------|:------------|:-------|
| FluentBundle, FluentLocalization, add_resource, format_pattern, format_value | [DOC_01_Core.md](DOC_01_Core.md) | Core API |
| Message, Term, Pattern, Resource, AST, Identifier, dataclass | [DOC_02_Types.md](DOC_02_Types.md) | AST Types |
| parse, serialize, parse_ftl, serialize_ftl, parse_number, parse_decimal, parse_date, parse_currency | [DOC_03_Parsing.md](DOC_03_Parsing.md) | Parsing |
| NUMBER, DATETIME, CURRENCY, add_function, FunctionRegistry | [DOC_04_Runtime.md](DOC_04_Runtime.md) | Runtime |
| FluentError, FluentReferenceError, ValidationResult, diagnostic | [DOC_05_Errors.md](DOC_05_Errors.md) | Errors |
| detect_cycles, extract_references, ReferenceExtractor, dependency graph | [DOC_02_Types.md](DOC_02_Types.md) | Analysis |

---

## Submodule Structure

```
ftllexengine/
  __init__.py              # Public API exports
  enums.py                 # CommentType, VariableContext, ReferenceKind
  localization.py          # FluentLocalization, PathResourceLoader
  introspection.py         # MessageIntrospection, introspect_message, extract_references
  analysis/
    __init__.py            # Analysis API exports
    graph.py               # detect_cycles, build_dependency_graph
  syntax/
    __init__.py            # AST exports, parse(), serialize()
    ast.py                 # AST node definitions
    cursor.py              # Cursor, ParseError, ParseResult
    visitor.py             # ASTVisitor, ASTTransformer
    serializer.py          # FluentSerializer
    parser/
      __init__.py          # FluentParserV1, ParseContext
      core.py              # Parser main entry point
      primitives.py        # get_last_parse_error, clear_parse_error, ParseErrorContext
      rules.py             # ParseContext, DEFAULT_MAX_NESTING_DEPTH, pattern/expression parsing
      entries.py           # Message, Term, Comment parsing
      whitespace.py        # Whitespace handling
  runtime/
    __init__.py            # Runtime exports
    bundle.py              # FluentBundle
    resolver.py            # FluentResolver, ResolutionContext, MAX_RESOLUTION_DEPTH
    functions.py           # Built-in functions, create_default_registry, get_shared_registry
    function_bridge.py     # FunctionRegistry
    plural_rules.py        # select_plural_category
    depth_guard.py         # DepthGuard, DepthLimitExceededError, MAX_EXPRESSION_DEPTH
  parsing/
    __init__.py            # Parsing API exports
    numbers.py             # parse_number, parse_decimal
    dates.py               # parse_date, parse_datetime
    currency.py            # parse_currency
    guards.py              # Type guards
  diagnostics/
    __init__.py            # Error exports
    errors.py              # FluentError hierarchy
    codes.py               # DiagnosticCode, Diagnostic, SourceSpan
    templates.py           # ErrorTemplate
    validation.py          # ValidationResult, ValidationError, ValidationWarning
    formatter.py           # DiagnosticFormatter, OutputFormat
  validation/
    __init__.py            # validate_resource
    resource.py            # Standalone resource validation
```

---

## Type Alias Quick Reference

| Alias | Definition | Location |
|:------|:-----------|:---------|
| `FluentValue` | `str \| int \| float \| bool \| Decimal \| datetime \| date \| None` | runtime/resolver.py (exported from root) |
| `MessageId` | `str` | localization.py |
| `LocaleCode` | `str` | localization.py |
| `ResourceId` | `str` | localization.py |
| `FTLSource` | `str` | localization.py |
| `Entry` | `Message \| Term \| Comment \| Junk` | syntax/ast.py |
| `PatternElement` | `TextElement \| Placeable` | syntax/ast.py |
| `Expression` | `SelectExpression \| InlineExpression` | syntax/ast.py |
| `InlineExpression` | Union of inline AST types | syntax/ast.py |
| `VariantKey` | `Identifier \| NumberLiteral` | syntax/ast.py |

---

## Cross-Reference: Non-Reference Documentation

| File | Purpose | Audience |
|:-----|:--------|:---------|
| [README.md](../README.md) | Entry point, installation, quick start | Humans |
| [QUICK_REFERENCE.md](QUICK_REFERENCE.md) | Cheat sheet, common patterns | Humans |
| [PARSING_GUIDE.md](PARSING_GUIDE.md) | Bi-directional parsing tutorial | Humans |
| [TYPE_HINTS_GUIDE.md](TYPE_HINTS_GUIDE.md) | Python 3.13 type patterns | Humans |
| [TERMINOLOGY.md](TERMINOLOGY.md) | Glossary, disambiguation | Both |
| [MIGRATION.md](MIGRATION.md) | fluent.runtime migration guide | Humans |
| [CUSTOM_FUNCTIONS_GUIDE.md](CUSTOM_FUNCTIONS_GUIDE.md) | Custom function tutorial | Humans |

---
