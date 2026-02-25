---
afad: "3.3"
version: "0.137.0"
domain: INDEX
updated: "2026-02-25"
route:
  keywords: [api reference, documentation, exports, imports, fluentbundle, fluentlocalization, fiscal, iso, territory, currency]
  questions: ["what classes are available?", "how to import ftllexengine?", "what are the module exports?", "how to import fiscal calendar?", "how to import ISO introspection?"]
---

# FTLLexEngine API Reference Index

## Module Exports

### Root Exports (`from ftllexengine import ...`)
```python
from ftllexengine import (
    # Core API
    FluentBundle,
    FluentLocalization,
    CacheConfig,       # Cache configuration dataclass
    parse_ftl,
    serialize_ftl,
    validate_resource,  # FTL resource validation (no Babel required)
    FluentValue,       # Type alias for function argument values
    fluent_function,   # Decorator for custom functions
    clear_all_caches,  # Clear all library caches
    # Errors
    FrozenFluentError,  # Immutable error type with ErrorCategory
    ErrorCategory,      # Error classification enum
    FrozenErrorContext,  # Context for parse/formatting errors
    # Data Integrity
    DataIntegrityError,
    FormattingIntegrityError,
    ImmutabilityViolationError,
    SyntaxIntegrityError,
    CacheCorruptionError,
    WriteConflictError,
    IntegrityCheckFailedError,
    IntegrityContext,
    # Fiscal calendar (no Babel required)
    FiscalCalendar,
    FiscalDelta,
    FiscalPeriod,
    MonthEndPolicy,
    fiscal_quarter,
    fiscal_year,
    fiscal_month,
    fiscal_year_start,
    fiscal_year_end,
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
    parse, serialize,
    SerializationValidationError, SerializationDepthError,
)
```

### Errors & Validation (`from ftllexengine.diagnostics import ...`)
```python
from ftllexengine.diagnostics import (
    FrozenFluentError, ErrorCategory, FrozenErrorContext,
    Diagnostic, DiagnosticCode,
    ValidationResult, ValidationError, ValidationWarning, WarningSeverity,
    DiagnosticFormatter, OutputFormat,
)
```

### Introspection (`from ftllexengine.introspection import ...`)
```python
from ftllexengine.introspection import (
    # Message introspection
    introspect_message, MessageIntrospection,
    extract_variables, extract_references, extract_references_by_attribute,
    clear_introspection_cache,
    VariableInfo, FunctionCallInfo, ReferenceInfo,
    # ISO introspection (requires Babel)
    TerritoryCode, CurrencyCode,  # Type aliases
    TerritoryInfo, CurrencyInfo,  # Data classes
    get_territory, get_currency, list_territories, list_currencies,
    get_territory_currencies,  # Lookup functions
    is_valid_territory_code, is_valid_currency_code,  # Type guards
    clear_iso_cache,  # Cache management
    BabelImportError,  # Exception
    get_cldr_version,  # Babel/CLDR diagnostics
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
from ftllexengine.analysis import detect_cycles, entry_dependency_set, make_cycle_key
```

### Validation (`from ftllexengine.validation import ...`)
```python
from ftllexengine.validation import validate_resource
```

### Core Utilities (`from ftllexengine.core import ...`)
```python
from ftllexengine.core import (
    DepthGuard, depth_clamp,  # Depth limiting
    # Fiscal calendar (no Babel required)
    FiscalCalendar, FiscalDelta, FiscalPeriod, MonthEndPolicy,
    fiscal_quarter, fiscal_year, fiscal_month, fiscal_year_start, fiscal_year_end,
)
from ftllexengine.core.babel_compat import (
    BabelImportError, require_babel,        # Babel availability checking
    is_babel_available, get_locale_class,   # Babel introspection
    get_cldr_version,                       # CLDR version
)
```

### Runtime (`from ftllexengine.runtime import ...`)
```python
from ftllexengine.runtime import (
    FluentBundle, FluentResolver, FunctionRegistry, ResolutionContext,
    create_default_registry, get_shared_registry,
    number_format, datetime_format, currency_format,
    select_plural_category,
)
```

### Localization (`from ftllexengine.localization import ...`)
```python
from ftllexengine.localization import (
    FluentLocalization, PathResourceLoader, ResourceLoader,
    LoadStatus, LoadSummary, ResourceLoadResult, FallbackInfo,
    MessageId, LocaleCode, ResourceId, FTLSource,
)
```

### Parsing (`from ftllexengine.parsing import ...`)

> **Babel required** for this entire module. For fiscal calendar without Babel,
> use `from ftllexengine import FiscalCalendar` or `from ftllexengine.core import FiscalCalendar`.

```python
from ftllexengine.parsing import (
    # Parse functions (require Babel)
    parse_decimal, parse_date, parse_datetime, parse_currency,
    # Type guards
    is_valid_decimal, is_valid_date, is_valid_datetime, is_valid_currency,
    # Type alias
    ParseResult,
    # Cache management
    clear_date_caches, clear_currency_caches,
    # Fiscal calendar (re-exported from ftllexengine.core; Babel required for this module)
    FiscalCalendar, FiscalDelta, FiscalPeriod, MonthEndPolicy,
    fiscal_quarter, fiscal_year, fiscal_month, fiscal_year_start, fiscal_year_end,
)
```

---

## File Routing Table

| Query Pattern | Target File | Domain |
|:--------------|:------------|:-------|
| FluentBundle, FluentLocalization, add_resource, format_pattern | [DOC_01_Core.md](DOC_01_Core.md) | Core API |
| Message, Term, Pattern, Resource, AST, Identifier, FTLLiteral, NamedArgument, dataclass | [DOC_02_Types.md](DOC_02_Types.md) | AST Types |
| parse, serialize, parse_ftl, serialize_ftl, parse_decimal, parse_date, parse_currency | [DOC_03_Parsing.md](DOC_03_Parsing.md) | Parsing |
| FiscalCalendar, FiscalDelta, FiscalPeriod, MonthEndPolicy, fiscal_quarter, fiscal_year, fiscal_month | [DOC_03_Parsing.md](DOC_03_Parsing.md) | Fiscal Calendar |
| NUMBER, DATETIME, CURRENCY, add_function, FunctionRegistry | [DOC_04_Runtime.md](DOC_04_Runtime.md) | Runtime |
| FrozenFluentError, ErrorCategory, FrozenErrorContext, BabelImportError, DepthGuard, ValidationResult, Diagnostic, DiagnosticCode | [DOC_05_Errors.md](DOC_05_Errors.md) | Errors |
| detect_cycles, entry_dependency_set, make_cycle_key, validate_resource | [DOC_04_Runtime.md](DOC_04_Runtime.md) | Analysis |
| extract_variables, extract_references, extract_references_by_attribute, introspect_message, MessageIntrospection | [DOC_02_Types.md](DOC_02_Types.md) | Message Introspection |
| TerritoryInfo, CurrencyInfo, get_territory, get_currency, ISO 3166, ISO 4217 | [DOC_02_Types.md](DOC_02_Types.md) | ISO Introspection |

---

## Submodule Structure

```
ftllexengine/
  __init__.py              # Public API exports
  constants.py             # MAX_DEPTH, MAX_IDENTIFIER_LENGTH, MAX_LOCALE_LENGTH_HARD_LIMIT, cache limits, fallback strings, ISO_4217_DECIMAL_DIGITS
  enums.py                 # CommentType, VariableContext, ReferenceKind, LoadStatus
  integrity.py             # DataIntegrityError hierarchy, IntegrityContext
  localization/
    __init__.py            # FluentLocalization, PathResourceLoader, ResourceLoader, LoadStatus, LoadSummary, ResourceLoadResult, FallbackInfo, type aliases
    types.py               # PEP 695 type aliases: MessageId, LocaleCode, ResourceId, FTLSource
    loading.py             # ResourceLoader protocol, PathResourceLoader, LoadSummary, ResourceLoadResult, FallbackInfo
    orchestrator.py        # FluentLocalization class, LocalizationCacheStats
  introspection/
    __init__.py            # Introspection API exports (message + ISO)
    message.py             # MessageIntrospection, introspect_message, extract_variables, extract_references, extract_references_by_attribute
    iso.py                 # TerritoryInfo, CurrencyInfo, get_territory, get_currency (requires Babel)
  core/
    __init__.py            # Core exports (BabelImportError, DepthGuard, FrozenFluentError, fiscal types)
    babel_compat.py        # BabelImportError, Babel lazy import infrastructure
    depth_guard.py         # DepthGuard, depth_clamp
    errors.py              # ErrorCategory, FrozenErrorContext, FrozenFluentError (re-exports)
    fiscal.py              # FiscalCalendar, FiscalDelta, FiscalPeriod, MonthEndPolicy (no Babel)
    identifier_validation.py  # FTL identifier validation utilities
    locale_utils.py        # get_system_locale, normalize_locale, get_babel_locale, clear_locale_cache
  analysis/
    __init__.py            # Analysis API exports
    graph.py               # detect_cycles, entry_dependency_set, make_cycle_key
  syntax/
    __init__.py            # AST exports, parse(), serialize()
    ast.py                 # AST node definitions
    cursor.py              # Cursor, ParseError, ParseResult
    position.py            # Source position tracking
    validation_helpers.py  # Shared validation helper functions
    validator.py           # SemanticValidator (AST node-level validation)
    visitor.py             # ASTVisitor, ASTTransformer
    serializer.py          # FluentSerializer
    parser/
      __init__.py          # FluentParserV1, ParseContext
      core.py              # Parser main entry point
      primitives.py        # Parser primitive operations (identifier, number, string literal parsing)
      rules.py             # ParseContext, pattern/expression parsing
      whitespace.py        # Whitespace handling
  runtime/
    __init__.py            # Runtime exports
    bundle.py              # FluentBundle
    cache.py               # IntegrityCache, IntegrityCacheEntry, CacheStats
    function_bridge.py     # FunctionRegistry, fluent_function
    function_metadata.py   # Function metadata helpers (requires_locale_injection, etc.)
    functions.py           # Built-in functions, create_default_registry, get_shared_registry
    locale_context.py      # Locale context for runtime formatting
    plural_rules.py        # select_plural_category
    resolution_context.py  # GlobalDepthGuard, ResolutionContext
    resolver.py            # FluentResolver
    rwlock.py              # RWLock (readers-writer lock)
    value_types.py         # FluentNumber, FluentValue, FluentFunction, FunctionSignature
  parsing/
    __init__.py            # Parsing API exports (requires Babel; re-exports fiscal from core)
    numbers.py             # parse_decimal
    dates.py               # parse_date, parse_datetime
    currency.py            # parse_currency
    guards.py              # Type guards
  diagnostics/
    __init__.py            # Error exports
    errors.py              # FrozenFluentError, ErrorCategory, FrozenErrorContext
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
| `FluentValue` | `str \| int \| Decimal \| datetime \| date \| FluentNumber \| None \| Sequence[FluentValue] \| Mapping[str, FluentValue]` | runtime/value_types.py (exported from root) |
| `ParseResult[T]` | `tuple[T \| None, tuple[FrozenFluentError, ...]]` | parsing/__init__.py |
| `MessageId` | `str` | localization.py |
| `LocaleCode` | `str` | localization.py |
| `ResourceId` | `str` | localization.py |
| `FTLSource` | `str` | localization.py |
| `TerritoryCode` | `str` | introspection/iso.py |
| `CurrencyCode` | `str` | introspection/iso.py |
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
| [LOCALE_GUIDE.md](LOCALE_GUIDE.md) | Locale formatting behavior (str vs NUMBER) | Humans |
| [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md) | Validation architecture and responsibility matrix | Humans |
| [THREAD_SAFETY.md](THREAD_SAFETY.md) | Thread safety architectural decisions | Humans |

---
