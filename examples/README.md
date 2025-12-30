# ftllexengine Examples

Comprehensive examples demonstrating all FTLLexEngine features.

**Requirements**: Python 3.13+

## Note on Bidi Isolation Marks

By default, FTLLexEngine wraps interpolated variables in Unicode bidi isolation marks (FSI U+2068 and PDI U+2069). You may see `⁨` and `⁩` characters in terminal output like: `"Sveiki, ⁨Anna⁩!"` These marks are:
- **Critical for RTL languages** (Arabic, Hebrew, Persian, Urdu) - prevents text corruption
- **Invisible in proper Unicode rendering** (browsers, most GUI apps)
- **May appear as symbols** in some terminals (this is a terminal limitation, not a bug)
- **Recommended to keep enabled** (`use_isolating=True`, the default) unless your app will only ever support LTR languages

**Important:** Examples in this directory use `use_isolating=False` for cleaner terminal demonstrations. **Never disable bidi isolation in production applications** that may support RTL languages.

## Common Import Patterns

All FTLLexEngine APIs are available as top-level imports for maximum convenience:

### Core Message Formatting

```python
from ftllexengine import FluentBundle, FluentLocalization

# Single locale
bundle = FluentBundle("en")

# Multi-locale fallback
l10n = FluentLocalization(['lv', 'en'])
```

### Resource Loading

```python
from ftllexengine.localization import PathResourceLoader, ResourceLoader

# File system loader
loader = PathResourceLoader("locales/{locale}")
ftl_source = loader.load("en", "main.ftl")

# Custom loader (implement ResourceLoader protocol)
class MyLoader:
    def load(self, locale: str, resource_id: str) -> str:
        # Your custom loading logic
        ...
```

### AST Manipulation (Linters, Transformers)

```python
from ftllexengine import parse_ftl, serialize_ftl
from ftllexengine.syntax import ASTVisitor, ASTTransformer
from ftllexengine.syntax.ast import Message, Term, VariableReference

# Parse FTL to AST
resource = parse_ftl(ftl_source)

# Traverse AST
class MyVisitor(ASTVisitor):
    def visit_Message(self, node):
        print(f"Found message: {node.id.name}")

# Serialize back to FTL
ftl_output = serialize_ftl(resource)
```

### Error Handling

```python
from ftllexengine import (
    FluentError,
    FluentSyntaxError,
    FluentReferenceError,
    FluentResolutionError,
)
from ftllexengine.diagnostics import FluentCyclicReferenceError

# Robust error handling
result, errors = bundle.format_pattern("msg", {"var": value})
if errors:
    for error in errors:
        if isinstance(error, FluentReferenceError):
            logger.warning(f"Missing translation: {error}")
        elif isinstance(error, FluentResolutionError):
            logger.error(f"Runtime error: {error}")
```

### Advanced - Function Registry

```python
from ftllexengine import FluentBundle
from ftllexengine.runtime.functions import create_default_registry

# Create custom registry (v0.18.0+)
registry = create_default_registry()

# Register custom function
def UPPER(text: str) -> str:
    return text.upper()

registry.register(UPPER, ftl_name="UPPER")

# Pass registry to bundle (isolated, no global state)
bundle = FluentBundle("en", functions=registry)
```

**Recommended Pattern**: Use `create_default_registry()` and pass to `FluentBundle` constructor for isolated function registries. For single-bundle functions, use `bundle.add_function()` method.

**Note**: The global `FUNCTION_REGISTRY` was removed in v0.18.0. Use `create_default_registry()` instead.

### Introspection

```python
from ftllexengine import parse_ftl
from ftllexengine.introspection import introspect_message, extract_variables

# Module-level introspection (works with AST nodes)
resource = parse_ftl(ftl_source)
msg = resource.entries[0]
variables = extract_variables(msg)

# Bundle method (works with message IDs)
bundle = FluentBundle("en")
bundle.add_resource(ftl_source)
info = bundle.introspect_message("welcome")
print(info.get_variable_names())
```

**Note**: All examples in this directory use these top-level imports. 

## Available Examples

### [quickstart.py](quickstart.py)

**Basic usage of FluentBundle** - Start here for single-locale applications.

Demonstrates:
1. Simple messages
2. Variable interpolation
3. English plurals (one, other)
4. Latvian plurals (zero, one, other)
5. Select expressions
6. Number formatting
7. Loading from files
8. **Proper error handling** (production pattern with error logging)

**Run**: `python examples/quickstart.py`

---

### [locale_fallback.py](locale_fallback.py)

**Multi-locale with fallback chains** - Use this for applications supporting multiple languages.

Demonstrates:
1. Basic two-locale fallback (Latvian → English)
2. Three-locale fallback chains (Latvian → Lithuanian → English)
3. Disk-based resource loading with PathResourceLoader
4. Custom in-memory resource loaders
5. Database/cache resource loaders (production pattern with Redis example)
6. Realistic e-commerce application example
7. Checking message availability
8. Iterating through bundles for introspection

**Run**: `python examples/locale_fallback.py`

---

### [bidirectional_formatting.py](bidirectional_formatting.py)

**Bi-directional localization (v0.5.0+, Breaking change in v0.8.0)** - Parse locale-formatted strings back to Python types.

**v0.8.0 BREAKING CHANGE**: All parse functions now return `tuple[result, list[FluentParseError]]`.

Demonstrates:
1. Invoice processing with bi-directional localization (Latvian)
2. Form input validation with locale-aware parsing (German)
3. Currency parsing with automatic symbol detection (multiple locales)
4. Date parsing with locale-aware format detection (US vs European)
5. Roundtrip validation (format → parse → format)
6. CSV data import with locale-aware parsing

**Run**: `python examples/bidirectional_formatting.py`

**Key Features**:
- Number/currency parsing via Babel (CLDR-compliant)
- Date/datetime parsing via Python 3.13 stdlib with Babel CLDR patterns
- Financial precision with Decimal type
- Form validation patterns
- Import/export workflows
- **v0.8.0 API**: Use `has_parse_errors()` and type guards from `ftllexengine.parsing.guards`
- **Note**: Babel's `parse_decimal()` accepts `NaN`, `Infinity`, and `Inf` (case-insensitive) as valid Decimal values - use `is_valid_decimal()` to reject these for financial data

---

### [ftl_transform.py](ftl_transform.py)

**AST transformation and manipulation** - Build tools that modify FTL files programmatically.

Demonstrates:
1. Removing comments from FTL source
2. Renaming variables (refactoring)
3. Extracting hardcoded strings to variables
4. Removing empty messages
5. Chaining multiple transformations
6. Real-world modernization workflow (camelCase → snake_case)

**Run**: `python examples/ftl_transform.py`

---

### [ftl_linter.py](ftl_linter.py)

**Static analysis and linting** - Build quality tools for FTL files.

Demonstrates:
1. Detecting duplicate message IDs
2. Finding undefined variables
3. Validating function calls
4. Checking message/term references
5. Identifying messages without values
6. Building custom lint rules with ASTVisitor

**Run**: `python examples/ftl_linter.py`

---

### [custom_functions.py](custom_functions.py)

**Custom formatting functions** - Extend FTLLexEngine with domain-specific formatters.

Demonstrates:
1. CURRENCY formatting with symbols
2. PHONE number formatting
3. MARKDOWN rendering (simplified)
4. FILESIZE human-readable formatting
5. DURATION time formatting
6. Locale-aware custom functions using factory pattern

**Run**: `python examples/custom_functions.py`

**See also**: [CUSTOM_FUNCTIONS_GUIDE.md](../docs/CUSTOM_FUNCTIONS_GUIDE.md) - Comprehensive guide to custom function development including error handling patterns, Babel integration, testing strategies, and best practices.

---

### [function_introspection.py](function_introspection.py)

**Runtime function discovery and introspection** - Discover and inspect functions at runtime.

Demonstrates:
1. Basic introspection operations (list, iterate, check membership)
2. Function metadata inspection (parameter mappings, Python names)
3. Custom function introspection workflows
4. Financial application validation patterns
5. Auto-documentation generation
6. Safe function usage with existence checks
7. Registry copying for isolated customization

**Run**: `python examples/function_introspection.py`

**Note**: Uses the new FunctionRegistry introspection API (`list_functions()`, `get_function_info()`, `__iter__`, `__len__`, `__contains__`) added in v0.4.0 for runtime function discovery.

---

### [thread_safety.py](thread_safety.py)

**Thread-safe FluentBundle usage** - Patterns for multi-threaded applications.

Demonstrates:
1. Single-threaded initialization (recommended for static resources)
2. Concurrent read operations with ThreadPoolExecutor
3. Thread-local bundles (for per-thread customization)
4. Dynamic resource loading (always thread-safe as of v0.42.0)

**Run**: `python examples/thread_safety.py`

**Note**: As of v0.42.0, FluentBundle is always thread-safe. No manual locks or special parameters needed.

---

### [benchmark_loaders.py](benchmark_loaders.py)

**Performance benchmarks for resource loaders** - Compare different loader implementations.

Demonstrates:
1. In-memory loader benchmarks (baseline performance)
2. Disk loader benchmarks (PathResourceLoader)
3. Database loader benchmarks without cache (worst case)
4. Database loader benchmarks with cache (production pattern)
5. Cache hit rate analysis
6. Throughput and latency measurements
7. Production recommendations based on app size and requirements

**Run**: `python examples/benchmark_loaders.py`

**Output**: Comprehensive performance comparison with initialization times, throughput metrics, and best practice recommendations for choosing the optimal loader pattern.

---

### [property_based_testing.py](property_based_testing.py)

**Property-based testing with Hypothesis** - Advanced testing techniques for discovering edge cases.

Demonstrates:
1. Testing universal properties (format_pattern never raises exceptions)
2. Testing idempotence (parse → serialize → parse roundtrip)
3. Testing invariants (message count consistency)
4. Testing symmetry (fallback chain locale precedence)
5. Testing batch operations equivalence (batch vs individual introspection)
6. Stateful property testing with RuleBasedStateMachine (advanced)
7. Custom Hypothesis strategies for valid FTL generation

**Run**: `python examples/property_based_testing.py`

**Note**: This example demonstrates advanced testing techniques using property-based testing, which generates hundreds of random test cases to verify universal properties of the library. Excellent for discovering edge cases and verifying API contracts.

---

## Running All Examples

```bash
# Run each example individually
python examples/quickstart.py
python examples/locale_fallback.py
python examples/bidirectional_formatting.py
python examples/ftl_transform.py
python examples/ftl_linter.py
python examples/custom_functions.py
python examples/function_introspection.py
python examples/thread_safety.py
python examples/benchmark_loaders.py
python examples/property_based_testing.py
```

## Basic Usage

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en")
bundle.add_resource("""
my-message = Hello, { $name }!
""")

result, errors = bundle.format_pattern("my-message", {"name": "World"})
print(result)  # Hello, World!
```

## Loading from Files

```python
from pathlib import Path
from ftllexengine import FluentBundle

ftl_source = Path("locales/en/messages.ftl").read_text(encoding="utf-8")
bundle = FluentBundle("en")
bundle.add_resource(ftl_source)
result, errors = bundle.format_pattern("welcome")
print(result)
```

## FTL File Example

`locales/en/messages.ftl`:

```ftl
hello = Hello, World!
greeting = Hello, { $name }!

emails = You have { NUMBER($count) ->
    [one] one email
   *[other] { $count } emails
}.

greeting-formal = { $gender ->
    [male] Mr. { $name }
    [female] Ms. { $name }
   *[other] { $name }
}

price = Price: { NUMBER($amount, minimumFractionDigits: 2) } EUR
```

## See Also

- [docs/DOC_00_Index.md](../docs/DOC_00_Index.md) - Complete API reference
- [README.md](../README.md) - Project overview and getting started guide
- [CUSTOM_FUNCTIONS_GUIDE.md](../docs/CUSTOM_FUNCTIONS_GUIDE.md) - Comprehensive guide to extending FTLLexEngine with custom formatting functions
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines for developers
