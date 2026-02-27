---
afad: "3.3"
version: "0.142.0"
domain: reference
updated: "2026-02-27"
route:
  keywords: [cheat sheet, quick reference, examples, code snippets, patterns, copy paste, BabelImportError, cache, clear cache, CacheConfig]
  questions: ["how to format message?", "how to parse number?", "how to use bundle?", "what exceptions can occur?", "how to clear cache?", "how to enable cache audit?"]
---

# FTLLexEngine Quick Reference

**One-page cheat sheet for common tasks**

Python 3.13+ | [Full API Documentation](DOC_00_Index.md) | [Examples](../examples/)

---

## Installation

```bash
# Parser-only (no external dependencies)
pip install ftllexengine

# Full runtime with locale formatting
pip install ftllexengine[babel]
```

**Requirements**: Python 3.13+ | Babel>=2.18.0 (optional for locale formatting)

---

## Parser-Only Usage (No Babel Required)

```python
from ftllexengine import parse_ftl, serialize_ftl, validate_resource

# Parse FTL source to AST
resource = parse_ftl("""
hello = Hello, World!
greeting = Welcome, { $name }!
""")

# Inspect AST
for entry in resource.entries:
    print(f"Message: {entry.id.name}")

# Validate FTL source (syntax and semantic checks)
result = validate_resource("""
hello = Hello, World!
greeting = Welcome, { $name }!
""")
if result.errors:
    print(f"Errors: {result.errors}")

# Serialize back to FTL string
ftl_source = serialize_ftl(resource)
```

---

## Basic Usage

### Single Locale Application

```python
from ftllexengine import FluentBundle

# Create bundle
bundle = FluentBundle("en_US")

# Load translations
bundle.add_resource("""
hello = Hello, World!
welcome = Welcome, { $name }!
emails = You have { $count ->
    [one] one email
   *[other] { $count } emails
}.
""")

# Format messages
result, errors = bundle.format_pattern("hello")
# → "Hello, World!"

result, errors = bundle.format_pattern("welcome", {"name": "Alice"})
# → "Welcome, Alice!"

result, errors = bundle.format_pattern("emails", {"count": 5})
# → "You have 5 emails."
```

---

### Multi-Locale Application (with fallback)

```python
from ftllexengine import FluentLocalization

# Create with fallback chain: Latvian → English
l10n = FluentLocalization(['lv', 'en'])

# Add translations
l10n.add_resource('lv', """
welcome = Laipni lūdzam, { $name }!
cart = Grozs
""")

l10n.add_resource('en', """
welcome = Welcome, { $name }!
cart = Cart
checkout = Checkout
""")

# Format with automatic fallback
result, errors = l10n.format_value('welcome', {'name': 'Anna'})
# → "Laipni lūdzam, Anna!" (from Latvian)

result, errors = l10n.format_value('checkout')
# → "Checkout" (falls back to English)
```

---

### Loading from Files

```python
from pathlib import Path
from ftllexengine import FluentBundle

# Read .ftl file
ftl_source = Path("locales/en/main.ftl").read_text(encoding="utf-8")

# Add to bundle
bundle = FluentBundle("en")
bundle.add_resource(ftl_source)

result, errors = bundle.format_pattern("message-id")
```

---

### Loading from Directory Structure

```python
from ftllexengine import FluentLocalization
from ftllexengine.localization import PathResourceLoader

# Directory structure:
#   locales/en/main.ftl
#   locales/en/errors.ftl
#   locales/lv/main.ftl

loader = PathResourceLoader("locales/{locale}")
l10n = FluentLocalization(['lv', 'en'], ['main.ftl', 'errors.ftl'], loader)

result, errors = l10n.format_value('welcome')
```

---

## Common Patterns

### Error Handling (Production Pattern)

```python
# ALWAYS check errors in production
result, errors = bundle.format_pattern("msg", {"var": value})

if errors:
    for error in errors:
        logger.warning(f"Translation error: {error}")
        # error is FrozenFluentError; use error.category for classification

print(result)  # Always returns usable fallback
```

### Error Handling (Test Pattern)

```python
# In tests/examples, use underscore to explicitly ignore errors
# (When errors are not relevant to what you're testing)
result, _ = bundle.format_pattern("msg", {"var": value})
assert result == "Expected output"
```

---

### Accessing Attributes

```python
# FTL with attributes
bundle.add_resource("""
submit-button = Submit
    .tooltip = Click to submit form
    .aria-label = Submit button
""")

# Access attribute
result, errors = bundle.format_pattern("submit-button", attribute="tooltip")
# → "Click to submit form"

# Access value (default)
result, errors = bundle.format_pattern("submit-button")
# → "Submit"
```

---

### Validation Before Loading

```python
from pathlib import Path

bundle = FluentBundle("en")
ftl_source = Path("locale/main.ftl").read_text()

# Validate before adding
result = bundle.validate_resource(ftl_source)

if not result.is_valid:
    print(f"Found {result.error_count} syntax errors:")
    for error in result.errors:
        location = f"line {error.line}" if error.line else "unknown"
        print(f"  - {location}: {error.message[:80]}")
    sys.exit(1)

if result.warning_count > 0:
    print(f"Found {result.warning_count} warnings:")
    for warning in result.warnings:
        location = f"line {warning.line}" if warning.line else "unknown"
        print(f"  - {location}: {warning.message}")

# Safe to add
bundle.add_resource(ftl_source)
```

---

### Custom Functions

```python
# Define custom function (FILESIZE example)
def FILESIZE(bytes_count: int, *, precision: int = 2) -> str:
    """Format file size in human-readable format."""
    size = float(bytes_count)
    units = ["B", "KB", "MB", "GB", "TB"]

    for unit in units:
        if size < 1024.0:
            return f"{size:.{precision}f} {unit}"
        size /= 1024.0
    return f"{size:.{precision}f} PB"

# Register function
bundle = FluentBundle("en")
bundle.add_function("FILESIZE", FILESIZE)

# Use in FTL
bundle.add_resource("""
file-info = { $filename } ({ FILESIZE($bytes) })
""")

result, errors = bundle.format_pattern("file-info", {"filename": "video.mp4", "bytes": 157286400})
# → "video.mp4 (150.00 MB)"
```

**Note**: For currency formatting, use the built-in `CURRENCY()` function instead of custom implementations. See Built-in Functions section below.

---

### Locale-Aware Custom Functions (Factory Pattern)

```python
def make_greeting_function(locale: str):
    """Factory for locale-aware custom function."""
    def GREETING(name: str, *, formal: str = "false") -> str:
        is_formal = formal.lower() == "true"
        if locale.startswith("lv"):
            return f"Labdien, {name}!" if is_formal else f"Sveiki, {name}!"
        return f"Good day, {name}!" if is_formal else f"Hello, {name}!"
    return GREETING

bundle = FluentBundle("lv_LV")
bundle.add_function("GREETING", make_greeting_function(bundle.locale))

bundle.add_resource('msg = { GREETING($name, formal: "false") }')
result, errors = bundle.format_pattern("msg", {"name": "Anna"})
# → "Sveiki, Anna!"
```

---

## Core API Reference

### FluentBundle

**Constructor**:
```python
FluentBundle(
    locale: str,
    /,
    *,
    use_isolating: bool = True,
    cache: CacheConfig | None = None,
    functions: FunctionRegistry | None = None,
    max_source_size: int | None = None,
    max_nesting_depth: int | None = None,
    max_expansion_size: int | None = None,
    strict: bool = True,
)
```

**Factory Methods**:
```python
# Auto-detect system locale (from LC_ALL, LC_MESSAGES, LANG)
bundle = FluentBundle.for_system_locale()

# Context manager support (no-op: use for structured scoping only)
with FluentBundle("en", cache=CacheConfig()) as bundle:
    bundle.add_resource("hello = Hello!")  # Cache cleared immediately
    result, _ = bundle.format_pattern("hello")  # Cache populated
```

**Key Methods**:
```python
bundle.add_resource(ftl_source: str) -> tuple[Junk, ...]
bundle.format_pattern(message_id, args=None, *, attribute=None) -> tuple[str, tuple[FrozenFluentError, ...]]
bundle.validate_resource(ftl_source: str) -> ValidationResult
bundle.has_message(message_id: str) -> bool
bundle.has_attribute(message_id: str, attribute: str) -> bool
bundle.get_message_ids() -> list[str]
bundle.get_message_variables(message_id: str) -> frozenset[str]
bundle.get_all_message_variables() -> dict[str, frozenset[str]]
bundle.introspect_message(message_id: str) -> MessageIntrospection
bundle.introspect_term(term_id: str) -> MessageIntrospection
bundle.add_function(name: str, func: Callable) -> None
bundle.clear_cache() -> None
bundle.get_cache_stats() -> CacheStats | None
bundle.get_babel_locale() -> str
```

**Properties**:
```python
bundle.locale -> str  # Read-only
bundle.use_isolating -> bool  # Read-only
bundle.cache_config -> CacheConfig | None  # Read-only; None when caching disabled
bundle.cache_enabled -> bool  # Read-only
bundle.cache_usage -> int  # Read-only
bundle.max_source_size -> int  # Read-only
bundle.max_nesting_depth -> int  # Read-only
bundle.max_expansion_size -> int  # Read-only
bundle.strict -> bool  # Read-only
bundle.function_registry -> FunctionRegistry  # Read-only
```

---

### FluentLocalization

**Constructor**:
```python
FluentLocalization(
    locales: Iterable[str],
    resource_ids: Iterable[str] | None = None,
    resource_loader: ResourceLoader | None = None,
    *,
    use_isolating: bool = True,
    cache: CacheConfig | None = None,
    on_fallback: Callable[[FallbackInfo], None] | None = None,
    strict: bool = True,
)
```

**Key Methods**:
```python
l10n.add_resource(locale: str, ftl_source: str) -> tuple[Junk, ...]
l10n.format_pattern(message_id, args=None, *, attribute=None) -> tuple[str, tuple[FrozenFluentError, ...]]
l10n.format_value(message_id, args=None) -> tuple[str, tuple[FrozenFluentError, ...]]
l10n.validate_resource(ftl_source: str) -> ValidationResult
l10n.has_message(message_id: str) -> bool
l10n.has_attribute(message_id: str, attribute: str) -> bool
l10n.get_message_ids() -> list[str]
l10n.get_message_variables(message_id: str) -> frozenset[str]
l10n.get_all_message_variables() -> dict[str, frozenset[str]]
l10n.introspect_message(message_id: str) -> MessageIntrospection
l10n.introspect_term(term_id: str) -> MessageIntrospection | None
l10n.add_function(name: str, func: Callable) -> None
l10n.clear_cache() -> None
l10n.get_cache_stats() -> LocalizationCacheStats | None
l10n.get_load_summary() -> LoadSummary
l10n.get_bundles() -> Generator[FluentBundle]
l10n.get_babel_locale() -> str
```

**Properties**:
```python
l10n.locales -> tuple[str, ...]  # Read-only
l10n.strict -> bool  # Read-only
l10n.cache_config -> CacheConfig | None  # Read-only
l10n.cache_enabled -> bool  # Read-only
```

**Caching**: Pass `cache=CacheConfig()` for 50x speedup on repeated format calls.

---

## FTL Syntax Quick Reference

### Messages

```ftl
# Simple message
hello = Hello, World!

# With variable
welcome = Welcome, { $name }!

# Multi-line
description = This is a long message
    that spans multiple lines.
```

### Attributes

```ftl
login-button = Login
    .tooltip = Click to log in
    .aria-label = Login button
```

### Select Expressions (Plurals)

```ftl
emails = You have { $count ->
    [one] one email
   *[other] { $count } emails
}.
```

### Select Expressions (Gender/Custom)

```ftl
greeting = { $gender ->
    [male] Mr. { $name }
    [female] Ms. { $name }
    *[other] { $name }
}
```

### Terms (Reusable)

```ftl
-brand-name = Acme Corp
-product-name = Super Widget

welcome = Welcome to { -brand-name }!
about = About { -product-name }
```

### Functions

```ftl
# Built-in NUMBER function
quantity = { NUMBER($amount, minimumFractionDigits: 2) }

# Built-in DATETIME function
date = { DATETIME($timestamp, dateStyle: "short") }

# Built-in CURRENCY function
price = { CURRENCY($amount, currency: "EUR") }

# Custom function
file-size = { FILESIZE($bytes) }
```

---

## Built-in Functions

### NUMBER(value, options)

**Options**:
- `minimumFractionDigits` (int): Minimum decimal places (default: 0)
- `maximumFractionDigits` (int): Maximum decimal places (default: 3)
- `useGrouping` (bool): Use thousand separators (default: true)
- `pattern` (string): Custom number pattern (overrides other options)
**Examples**:
```ftl
price = { NUMBER($amount, minimumFractionDigits: 2) }
percent = { NUMBER($value, maximumFractionDigits: 0) }%
accounting = { NUMBER($amount, pattern: "#,##0.00;(#,##0.00)") }
```

### DATETIME(value, options)

**Options**:
- `dateStyle`: "short" | "medium" | "long" | "full" (default: "medium")
- `timeStyle`: "short" | "medium" | "long" | "full" | null (default: null)
- `pattern` (string): Custom datetime pattern (overrides style options)
**Examples**:
```ftl
short-date = { DATETIME($timestamp, dateStyle: "short") }
full-datetime = { DATETIME($timestamp, dateStyle: "long", timeStyle: "short") }
iso-date = { DATETIME($timestamp, pattern: "yyyy-MM-dd") }
```

### CURRENCY(value, options)

**Returns**: `FluentNumber` (usable as selector in plural/select expressions).

**Options**:
- `currency` (string, **required**): ISO 4217 currency code (e.g., "USD", "EUR", "JPY")
- `currencyDisplay`: "symbol" | "code" | "name" (default: "symbol")

**Examples**:
```ftl
# Symbol display (default)
price = { CURRENCY($amount, currency: "USD") }
# en_US → "$1,234.56"
# lv_LV → "1\xa0234,56\xa0$"  (CLDR uses NBSP U+00A0)

# Code display
price-code = { CURRENCY($amount, currency: "EUR", currencyDisplay: "code") }
# en_US → "EUR1,234.56"

# Name display
price-name = { CURRENCY($amount, currency: "EUR", currencyDisplay: "name") }
# → "1,234.56 euros"
```

**CLDR Compliance**:
- Currency-specific decimals: JPY (0), BHD/KWD/OMR (3), most others (2)
- Locale-specific symbol placement: en_US (before), lv_LV/de_DE (after with space)
- Uses Babel for CLDR-compliant formatting

---

## Parsing API

**Bi-directional localization**: Parse locale-formatted strings back to Python types.

```python
from ftllexengine.parsing import parse_decimal, parse_date, parse_currency
from ftllexengine.parsing import is_valid_decimal, is_valid_date, is_valid_currency

# Parse numbers (guards accept None)
result, errors = parse_decimal("1 234,56", "lv_LV")
if is_valid_decimal(result):
    amount = result  # Decimal('1234.56')

# Parse dates
result, errors = parse_date("28.01.2025", "lv_LV")
if is_valid_date(result):
    date_value = result  # date(2025, 1, 28)

# Parse currency
result, errors = parse_currency("1 234,56 €", "lv_LV")
if is_valid_currency(result):
    amount, currency = result  # (Decimal('1234.56'), 'EUR')

# Note: Yen sign (¥) is ambiguous
# Resolves to CNY for zh_* locales, JPY otherwise
result, errors = parse_currency("¥1,234", "ja_JP")  # JPY
result, errors = parse_currency("¥1,234", "zh_CN")  # CNY

# Note: Pound sign (£) is ambiguous
# Resolves to EGP for ar_* locales, GBP otherwise
result, errors = parse_currency("£100", "en_GB", infer_from_locale=True)  # GBP
result, errors = parse_currency("£100", "ar_EG", infer_from_locale=True)  # EGP
```

**Key Functions**:
- `parse_decimal(value, locale)` → `tuple[Decimal | None, tuple[FrozenFluentError, ...]]`
- `parse_date(value, locale)` → `tuple[date | None, tuple[FrozenFluentError, ...]]`
- `parse_datetime(value, locale, tzinfo=None)` → `tuple[datetime | None, tuple[FrozenFluentError, ...]]`
- `parse_currency(value, locale)` → `tuple[tuple[Decimal, str] | None, tuple[FrozenFluentError, ...]]`

**Implementation**: Uses Babel for number parsing, Python 3.13 stdlib (`strptime`, `fromisoformat`) with Babel CLDR patterns for date parsing.

**Babel Required**: All parsing functions raise `BabelImportError` if Babel is not installed. Install with `pip install ftllexengine[babel]`.

**See**: [PARSING_GUIDE.md](PARSING_GUIDE.md) for complete guide with best practices and examples.

---

## Introspection

### Get Message Variables

```python
bundle.add_resource("welcome = Hello, { $firstName } { $lastName }!")

variables = bundle.get_message_variables("welcome")
print(variables)  # frozenset({'firstName', 'lastName'})
```

### Batch Variable Extraction

```python
bundle.add_resource("""
greeting = Hello, { $name }!
farewell = Goodbye, { $firstName } { $lastName }!
simple = No variables
""")

all_vars = bundle.get_all_message_variables()
print(all_vars["greeting"])   # frozenset({'name'})
print(all_vars["farewell"])   # frozenset({'firstName', 'lastName'})
print(all_vars["simple"])     # frozenset()
```

### Full Introspection

```python
bundle.add_resource("""
msg = Hello, { $name }! You have { NUMBER($count) } items.
""")

info = bundle.introspect_message("msg")

print(info.get_variable_names())
# → frozenset({'name', 'count'})

print(info.get_function_names())
# → frozenset({'NUMBER'})
```

### Function Introspection

```python
# Access the function registry (read-only property)
registry = bundle.function_registry

# List all available functions
functions = registry.list_functions()
print(functions)  # ["NUMBER", "DATETIME", "CURRENCY"]

# Check if function exists
if "CURRENCY" in registry:
    print("CURRENCY available")

# Get function metadata
info = registry.get_function_info("NUMBER")
print(f"Python name: {info.python_name}")
print(f"Parameters: {info.param_mapping}")

# Iterate over all functions
for func_name in registry:
    info = registry.get_function_info(func_name)
    print(f"{func_name}: {info.python_name}")
```

---

## Type Annotations

```python
from ftllexengine import FluentBundle, FluentValue
from ftllexengine.localization import MessageId, LocaleCode, FTLSource

def format_message(
    bundle: FluentBundle,
    msg_id: MessageId,
    args: dict[str, FluentValue] | None = None,
) -> str:
    """Format message with error logging."""
    result, errors = bundle.format_pattern(msg_id, args)
    if errors:
        for error in errors:
            logger.warning(f"Translation error: {error}")
    return result

def create_bundle(locale: LocaleCode, ftl_source: FTLSource) -> FluentBundle:
    """Create and populate bundle."""
    bundle = FluentBundle(locale)
    bundle.add_resource(ftl_source)
    return bundle
```

**`FluentValue`**: Type-hint for resolver arguments. Union of `str | int | Decimal | datetime | date | FluentNumber | None | Sequence[FluentValue] | Mapping[str, FluentValue]`. (`bool` is absent: it is an `int` subtype accepted by raw interpolation but rejected by numeric formatting functions; convert explicitly with `int(flag)` or `str(flag)`.)

**`ParseResult[T]`**: Type-hint for parsing function returns. Alias for `tuple[T | None, tuple[FrozenFluentError, ...]]`. Import from `ftllexengine.parsing`.

---

## Thread Safety

**FluentBundle and FluentLocalization are always thread-safe**. All public methods are synchronized via internal RWLock (readers-writer lock). Multiple concurrent read operations execute in parallel; write operations acquire exclusive access.

### Pattern 1: Shared Bundle (Recommended)

```python
# Create bundle once, share across threads
bundle = FluentBundle("en_US")
bundle.add_resource(ftl_source)

# All operations are thread-safe (reads AND writes)
bundle.add_resource(more_ftl)  # Thread-safe
bundle.add_function("CUSTOM", my_function)  # Thread-safe
result, errors = bundle.format_pattern("msg")  # Thread-safe
```

### Pattern 2: Task-Local Bundles (Per-Task Customization)

```python
from contextvars import ContextVar

_bundle_var: ContextVar[FluentBundle | None] = ContextVar("_bundle_var", default=None)

def get_bundle() -> FluentBundle:
    bundle = _bundle_var.get()
    if bundle is None:
        bundle = FluentBundle("en_US")
        bundle.add_resource(ftl_source)
        _bundle_var.set(bundle)
    return bundle
```

`ContextVar` provides automatic isolation per thread and per async task, with no dynamic attribute access.

---

## Cache Management

Clear module-level caches for testing, hot-reload, or memory management.

```python
from ftllexengine import clear_module_caches

# Clear all library caches in one call
clear_module_caches()
```

**Individual Cache Clear Functions**:
```python
from ftllexengine.core.locale_utils import clear_locale_cache
from ftllexengine.parsing import clear_date_caches, clear_currency_caches
from ftllexengine.introspection import clear_introspection_cache, clear_iso_cache
from ftllexengine.runtime.locale_context import LocaleContext

# Clear specific caches
clear_locale_cache()           # Babel locale objects
clear_date_caches()            # Date/datetime patterns
clear_currency_caches()        # Currency maps and patterns
clear_introspection_cache()    # Message introspection results
clear_iso_cache()              # ISO territory/currency data
LocaleContext.clear_cache()    # Locale context instances
```

---

## Common Checks

### Check if Message Exists

```python
if bundle.has_message("premium-feature"):
    result, _ = bundle.format_pattern("premium-feature")
else:
    print("Feature not available")
```

### List All Messages

```python
message_ids = bundle.get_message_ids()
print(f"Loaded {len(message_ids)} messages")
for msg_id in sorted(message_ids):
    print(f"  - {msg_id}")
```

### Check Required Variables

```python
required = bundle.get_message_variables("welcome")
provided = {"firstName": "John", "lastName": "Doe"}

missing = required - set(provided.keys())
if missing:
    print(f"Missing variables: {missing}")
```

---

## Important Warnings

### RTL Languages Require use_isolating=True

```python
# WRONG - Breaks Arabic/Hebrew
bundle = FluentBundle("ar_EG", use_isolating=False)

# CORRECT - Default is safe
bundle = FluentBundle("ar_EG")  # use_isolating=True by default
```

**Rule**: Only use `use_isolating=False` for:
- Documentation examples (cleaner output)
- Unit tests (exact assertions)
- LTR-only applications (verifiable constraint)

### Errors Raise in Strict Mode (Default)

```python
# In strict mode (default), format_pattern() raises FormattingIntegrityError on ANY error
# In non-strict mode (strict=False), format_pattern() returns (result, errors) tuple
bundle = FluentBundle("en", strict=False)  # opt in to soft-error recovery
result, errors = bundle.format_pattern("missing-message")
# result → "{missing-message}"  # Readable fallback
# errors → (FrozenFluentError(...),)  # category=ErrorCategory.REFERENCE

# Always check errors in non-strict production code
if errors:
    logger.warning(f"Translation errors: {errors}")
```

---

## Exception Types

```python
from ftllexengine import (
    FrozenFluentError,        # Immutable error (returned in errors tuple)
    ErrorCategory,            # Error classification: REFERENCE, RESOLUTION, CYCLIC, PARSE, FORMATTING
)

from ftllexengine.core.babel_compat import BabelImportError  # Raised when Babel not installed
```

**Note**: `FrozenFluentError` instances are returned in the errors tuple, NOT raised. Use `error.category` to classify errors (e.g., `ErrorCategory.REFERENCE` for missing messages). `BabelImportError` is raised when parsing functions are called without Babel installed.

---

## AST Manipulation (Advanced)

### Parse and Serialize

```python
from ftllexengine import parse_ftl, serialize_ftl
from ftllexengine.syntax.ast import Message

# Parse FTL to AST
resource = parse_ftl(ftl_source)

# Inspect AST
for entry in resource.entries:
    if isinstance(entry, Message):
        print(f"Message: {entry.id.name}")

# Serialize back to FTL
ftl_output = serialize_ftl(resource)

# Validate AST before serialization
from ftllexengine.syntax import SerializationValidationError

try:
    ftl_output = serialize_ftl(resource, validate=True)
except SerializationValidationError as e:
    print(f"Invalid AST: {e}")

# Depth guard prevents stack overflow from malicious ASTs
from ftllexengine.syntax import SerializationDepthError

try:
    ftl_output = serialize_ftl(resource, max_depth=100)  # default
except SerializationDepthError as e:
    print(f"AST too deep: {e}")
```

### Visitor Pattern

```python
from ftllexengine import parse_ftl
from ftllexengine.syntax.ast import Message
from ftllexengine.syntax.visitor import ASTVisitor

class MessageCollector(ASTVisitor):
    def __init__(self):
        super().__init__()
        self.messages = []

    def visit_Message(self, node: Message):
        self.messages.append(node.id.name)
        return self.generic_visit(node)

resource = parse_ftl(ftl_source)
collector = MessageCollector()
collector.visit(resource)
print(f"Found messages: {collector.messages}")
```

---

## Supported Locales

**CLDR plural rules via Babel**: 200+ locales with full Unicode CLDR compliance. Includes all major languages (English, Spanish, French, German, Chinese, Japanese, Arabic, Russian, etc.) plus regional variants. Unsupported locales fall back to English-style one/other rules.

---

## Getting Help

- **Full API Documentation**: [DOC_00_Index.md](DOC_00_Index.md)
- **Examples**: [examples/](../examples/)
- **Contributing**: [CONTRIBUTING.md](../CONTRIBUTING.md)
- **Issues**: https://github.com/resoltico/ftllexengine/issues

---

## Version Info

```python
from ftllexengine import (
    __version__,                # Package version
    __fluent_spec_version__,   # FTL spec version (1.0)
    __spec_url__,              # Spec URL
    __recommended_encoding__,  # UTF-8
)

print(f"FTLLexEngine {__version__}")
print(f"Fluent Specification {__fluent_spec_version__}")
```

---

**Python Requirement**: 3.13+
