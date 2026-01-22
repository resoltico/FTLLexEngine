---
afad: "3.1"
version: "0.86.0"
domain: migration
updated: "2026-01-21"
route:
  keywords: [migration, fluent.runtime, upgrade, breaking changes, mozilla fluent, python fluent]
  questions: ["how to migrate from fluent.runtime?", "how to upgrade to ftllexengine?"]
---

# Migration Guide: fluent.runtime → FTLLexEngine

**Complete guide for migrating from Mozilla's fluent.runtime to FTLLexEngine**

**Target Audience**: Developers currently using `fluent.runtime` (Mozilla's Python implementation) who want to migrate to FTLLexEngine for Python 3.13+ features, better type safety, and improved performance.

**[IMPORTANT] REQUIREMENT: Python 3.13+**
FTLLexEngine requires Python 3.13 or later. If your project uses Python 3.12 or earlier, you must upgrade your Python version before migrating.

---

## Why Migrate?

### FTLLexEngine Advantages

1. **Python 3.13+ Modern Features**:
   - PEP 695 `type` keyword aliases
   - PEP 727 `TypeIs` type guards
   - Pattern matching for cleaner code
   - Frozen dataclasses with slots

2. **Better Type Safety**:
   - Full `mypy --strict` compatibility
   - Type-safe introspection APIs
   - Complete type annotations

3. **Single Dependency**:
   - Only requires Babel (vs fluent.runtime: fluent.syntax, attrs, babel, pytz, typing-extensions)
   - Smaller dependency footprint

4. **Simpler Architecture**:
   - Cleaner API with fewer abstractions
   - Direct imports from main package
   - No separate fluent.syntax dependency

5. **Comprehensive Documentation**:
   - 100% API coverage
   - Working examples
   - Quick reference guide
   - Migration guide (this document!)

### When to Stay with fluent.runtime

- Your project requires Python 3.6-3.12 (FTLLexEngine requires 3.13+)
- You need Mozilla's exact reference implementation behavior
- Your project is tightly integrated with Firefox/Thunderbird ecosystem
- Migration effort outweighs benefits for your use case

---

## Quick Migration Checklist

- [ ] Verify Python 3.13+ is available
- [ ] Update dependencies in requirements.txt/pyproject.toml
- [ ] Change import statements
- [ ] Update FluentBundle constructor (remove transform_func)
- [ ] Update FluentResource → parse_ftl() and add_resource()
- [ ] Update error handling (errors are already in list, not separate iteration)
- [ ] Test with existing .ftl files
- [ ] Update type annotations to use FTLLexEngine type aliases
- [ ] Run test suite and verify behavior

---

## API Comparison

### Installation

```bash
# fluent.runtime
pip install fluent.runtime

# FTLLexEngine
pip install ftllexengine
```

**Dependencies Comparison**:
```
fluent.runtime → fluent.syntax, attrs, babel, pytz, typing-extensions
FTLLexEngine   → Babel only
```

---

### Import Statements

#### fluent.runtime

```python
from fluent.runtime import FluentBundle, FluentResource
from fluent.runtime.errors import FluentFormatError
```

#### FTLLexEngine

```python
from ftllexengine import FluentBundle, parse_ftl
from ftllexengine import FluentError, FluentReferenceError, FluentResolutionError
```

**Changes**:
- ✅ Top-level imports (no `ftllexengine.runtime` submodule needed)
- ✅ All public APIs available from main package
- ⚠️ `FluentResource` → use `parse_ftl()` instead
- ⚠️ `FluentFormatError` → multiple specific exception types

---

### Creating a Bundle

#### fluent.runtime

```python
bundle = FluentBundle(['en-US'], use_isolating=True)
```

#### FTLLexEngine

```python
bundle = FluentBundle('en-US', use_isolating=True)
```

**Changes**:
- ⚠️ **Single locale string** instead of list: `'en-US'` not `['en-US']`
- ✅ `use_isolating` parameter works identically

**Migration**:
```python
# fluent.runtime
bundle = FluentBundle(['en-US'], use_isolating=True)

# FTLLexEngine - extract first locale from list
locales = ['en-US']
bundle = FluentBundle(locales[0], use_isolating=True)
```

---

### Adding Resources

#### fluent.runtime

```python
from fluent.runtime import FluentResource

# Parse resource
resource = FluentResource("""
hello = Hello, World!
""")

# Add to bundle
bundle.add_resource(resource)
```

#### FTLLexEngine

```python
# Direct string - simpler!
bundle.add_resource("""
hello = Hello, World!
""")

# If you need AST for introspection, use parse_ftl() separately
from ftllexengine import parse_ftl
resource_ast = parse_ftl("""hello = Hello, World!""")
# Inspect AST here if needed
# Then add the original string to bundle
bundle.add_resource("""hello = Hello, World!""")
```

**Changes**:
- ✅ **No FluentResource wrapper needed** - pass string directly to `add_resource()`
- ✅ Simpler API with one less step
- ℹ️ `parse_ftl()` is for AST introspection only - `add_resource()` accepts strings

**Migration**:
```python
# fluent.runtime
resource = FluentResource(ftl_source)
bundle.add_resource(resource)

# FTLLexEngine - direct string
bundle.add_resource(ftl_source)
```

---

### Formatting Messages

#### fluent.runtime

```python
# Get message first, then format pattern
msg = bundle.get_message('hello')
result, errors = bundle.format_pattern(msg.value, {})
```

#### FTLLexEngine

```python
# Direct message ID - no get_message() step needed
result, errors = bundle.format_pattern('hello', {})

# Or format_value() - identical behavior
result, errors = bundle.format_value('hello', {})
```

**Changes**:
- ✅ **Simpler API**: Direct message ID, no `get_message()` step needed
- ✅ **Same return pattern**: Both return `(result, errors)` tuple
- ✅ **Cleaner code**: One call instead of two

**Migration**:
```python
# fluent.runtime
msg = bundle.get_message('hello')
if msg:
    result, errors = bundle.format_pattern(msg.value, {})

# FTLLexEngine - simpler (no get_message step)
result, errors = bundle.format_pattern('hello', {})
```

---

### Error Handling

#### fluent.runtime

```python
from fluent.runtime.errors import FluentFormatError

# Get message first, then format
msg = bundle.get_message('hello')
result, errors = bundle.format_pattern(msg.value, {})

for error in errors:
    if isinstance(error, FluentFormatError):
        print(f"Error: {error}")
```

#### FTLLexEngine

```python
from ftllexengine import FluentError

# Direct message ID, no get_message() needed
result, errors = bundle.format_pattern('hello', {})

for error in errors:
    if isinstance(error, FluentError):
        print(f"Error: {error}")
```

**Changes**:
- ✅ **Simpler API**: Use message ID directly, no `get_message()` step
- ✅ **Same return pattern**: Both return `(result, errors)` tuple
- ⚠️ Different exception hierarchy (FluentError vs FluentFormatError)

---

### Attribute Access

#### fluent.runtime

```python
msg = bundle.get_message('login-button')
value, errors = bundle.format_pattern(msg.value, {})
tooltip, errors = bundle.format_pattern(msg.attributes['tooltip'], {})
```

#### FTLLexEngine

```python
# Value
result, errors = bundle.format_pattern('login-button')

# Attribute
result, errors = bundle.format_pattern('login-button', attribute='tooltip')
```

**Changes**:
- ✅ **Much simpler**: Use `attribute` parameter instead of `get_message().attributes[...]`
- ✅ **No manual attribute lookup**: Bundle handles it

---

### Custom Functions

#### fluent.runtime

```python
def number_formatter(num, **options):
    return str(num)

bundle.add_function('NUMBER', number_formatter)
```

#### FTLLexEngine

```python
def NUMBER(num, **options):
    return str(num)

bundle.add_function('NUMBER', NUMBER)
```

**Changes**:
- ✅ **Identical API**: Works the same way
- ✅ Function names should be UPPERCASE (convention in both)

---

### Multi-Locale Support

#### fluent.runtime

```python
from fluent.runtime import FluentLocalization, FluentResourceLoader

# Load from files with resource loader
loader = FluentResourceLoader("locales/{locale}")
l10n = FluentLocalization(['lv', 'en'], ['main.ftl'], loader)

result = l10n.format_value('hello')
```

#### FTLLexEngine

```python
from ftllexengine import FluentLocalization
from ftllexengine.localization import PathResourceLoader

# Similar API with resource loader
loader = PathResourceLoader("locales/{locale}")
l10n = FluentLocalization(['lv', 'en'], ['main.ftl'], loader)

result, errors = l10n.format_value('hello')
```

**Note**: `PathResourceLoader` is in `ftllexengine.localization`, not the main package.

**Changes**:
- ✅ **Similar API**: Both have FluentLocalization for multi-locale
- ⚠️ **CRITICAL Return difference**:
  - fluent.runtime: Returns just string: `result = l10n.format_value('hello')`
  - FTLLexEngine: Returns tuple: `result, errors = l10n.format_value('hello')` (errors is immutable tuple)
- ✅ **PathResourceLoader**: Similar to FluentResourceLoader

---

## Complete Migration Example

### Before (fluent.runtime)

```python
from fluent.runtime import FluentBundle, FluentResource
from fluent.runtime.errors import FluentFormatError

# Create bundle
bundle = FluentBundle(['en-US'], use_isolating=True)

# Load resource
resource = FluentResource("""
welcome = Welcome, { $name }!
emails = You have { $count ->
    [one] one email
   *[other] { $count } emails
}.
""")
bundle.add_resource(resource)

# Format message
msg = bundle.get_message('welcome')
if msg:
    result, errors = bundle.format_pattern(msg.value, {'name': 'Alice'})
    if errors:
        for error in errors:
            print(f"Error: {error}")
    print(result)
```

### After (FTLLexEngine)

```python
from ftllexengine import FluentBundle

# Create bundle
bundle = FluentBundle('en-US', use_isolating=True)

# Load resource - direct string, no wrapper
bundle.add_resource("""
welcome = Welcome, { $name }!
emails = You have { $count ->
    [one] one email
   *[other] { $count } emails
}.
""")

# Format message - simpler API
result, errors = bundle.format_pattern('welcome', {'name': 'Alice'})
if errors:
    for error in errors:
        print(f"Error: {error}")
print(result)
```

**Lines of Code**:
- fluent.runtime: 19 lines
- FTLLexEngine: 13 lines (32% reduction)

---

## API Mapping Table

### Core Classes

| fluent.runtime | FTLLexEngine | Notes |
|----------------|--------------|-------|
| `FluentBundle(['locale'])` | `FluentBundle('locale')` | Single locale, not list |
| `FluentResource(str)` | Direct string to `add_resource()` | No wrapper needed; use `parse_ftl(str)` only for AST introspection |
| N/A | `FluentLocalization` | Built-in multi-locale support |
| N/A | `PathResourceLoader` | File system loader |

### Methods

| fluent.runtime | FTLLexEngine | Changes |
|----------------|--------------|---------|
| `bundle.add_resource(FluentResource)` | `bundle.add_resource(str)` | Direct string, no wrapper |
| `bundle.get_message(id).value` then `format_pattern()` | `bundle.format_pattern(id, args)` | Direct formatting - no intermediate Message object needed |
| `bundle.has_message(id)` | `bundle.has_message(id)` | Identical |
| N/A | `bundle.format_value(id, args)` | Alias for format_pattern |
| N/A | `bundle.get_message_ids()` | List all messages |
| N/A | `bundle.get_message_variables(id)` | Get required variables |
| N/A | `bundle.introspect_message(id)` | Full message metadata |
| N/A | `bundle.validate_resource(str)` | Validate before loading |

### Error Types

| fluent.runtime | FTLLexEngine | Notes |
|----------------|--------------|-------|
| `FluentFormatError` | `FluentError` (base) | Base exception (main package) |
| N/A | `FluentReferenceError` | Missing messages/variables (main package) |
| N/A | `FluentResolutionError` | Runtime errors (main package) |
| N/A | `FluentCyclicReferenceError` | Circular references (`ftllexengine.diagnostics`) |

---

## Migration Patterns

### Pattern 1: Simple Single-Locale App

#### fluent.runtime
```python
from fluent.runtime import FluentBundle, FluentResource

def setup_i18n(locale):
    bundle = FluentBundle([locale])
    with open(f'locales/{locale}/main.ftl') as f:
        resource = FluentResource(f.read())
    bundle.add_resource(resource)
    return bundle

bundle = setup_i18n('en-US')
```

#### FTLLexEngine
```python
from pathlib import Path
from ftllexengine import FluentBundle

def setup_i18n(locale):
    bundle = FluentBundle(locale)
    ftl_source = Path(f'locales/{locale}/main.ftl').read_text()
    bundle.add_resource(ftl_source)
    return bundle

bundle = setup_i18n('en-US')
```

---

### Pattern 2: Multi-Locale with Manual Fallback

#### fluent.runtime
```python
from fluent.runtime import FluentLocalization, FluentResourceLoader

# Built-in multi-locale support
loader = FluentResourceLoader('locales/{locale}')
l10n = FluentLocalization(['lv', 'en'], ['main.ftl'], loader)

# Returns just the string (no error tuple)
result = l10n.format_value('welcome', {'name': 'Anna'})
```

#### FTLLexEngine
```python
from ftllexengine import FluentLocalization
from ftllexengine.localization import PathResourceLoader

# Similar API
loader = PathResourceLoader('locales/{locale}')
l10n = FluentLocalization(['lv', 'en'], ['main.ftl'], loader)

# Returns (result, errors) tuple
result, errors = l10n.format_value('welcome', {'name': 'Anna'})
```

**Benefit**: Similar API, FTLLexEngine returns errors for better handling

---

### Pattern 3: Custom Functions

#### fluent.runtime
```python
from fluent.runtime import FluentBundle

def upper_formatter(text, **options):
    return str(text).upper()

bundle = FluentBundle(['en'])
bundle.add_function('UPPER', upper_formatter)
```

#### FTLLexEngine
```python
from ftllexengine import FluentBundle

def UPPER(text, **options):
    return str(text).upper()

bundle = FluentBundle('en')
bundle.add_function('UPPER', UPPER)
```

**Identical API** - no changes needed!

---

## Type Annotations Migration

### fluent.runtime (Limited typing)

```python
from fluent.runtime import FluentBundle
from typing import Dict, Any

def format_message(bundle: FluentBundle, msg_id: str, args: Dict[str, Any]) -> str:
    msg = bundle.get_message(msg_id)
    if msg:
        result, errors = bundle.format_pattern(msg.value, args)
        return result
    return msg_id
```

### FTLLexEngine (Full mypy --strict)

```python
from ftllexengine import FluentBundle, FluentError
from ftllexengine.localization import MessageId

def format_message(bundle: FluentBundle, msg_id: MessageId, args: dict[str, object]) -> str:
    """Format message with error logging."""
    result, errors = bundle.format_pattern(msg_id, args)
    if errors:
        for error in errors:
            # error is properly typed as FluentError
            logger.warning(f"Translation error: {error}")
    return result
```

**Improvements**:
- ✅ Full type safety with `mypy --strict`
- ✅ Type aliases for clarity (`MessageId`)
- ✅ Modern Python 3.13 dict syntax (`dict[str, object]` vs `Dict[str, Any]`)

---

## Testing Migration

### Update Test Assertions

#### fluent.runtime
```python
def test_message_formatting():
    bundle = FluentBundle(['en'])
    bundle.add_resource(FluentResource("hello = Hello!"))

    # Two-step process: get_message() then format_pattern()
    msg = bundle.get_message('hello')
    result, errors = bundle.format_pattern(msg.value, {})

    assert result == "Hello!"
    assert not errors
```

#### FTLLexEngine
```python
def test_message_formatting():
    bundle = FluentBundle('en', use_isolating=False)  # Clean assertions
    bundle.add_resource("hello = Hello!")

    # One-step process: format_pattern() with message ID directly
    result, errors = bundle.format_pattern('hello')

    assert result == "Hello!"
    assert errors == ()  # Empty immutable tuple
```

**Benefits**:
- **Simpler**: One call instead of two (no `get_message()` step)
- **Cleaner**: Fewer lines, direct assertions
- **Type-safe**: Returns tuple instead of mutable error list

---

## Troubleshooting Migration

### Issue 1: "FluentBundle() takes 1 positional argument but 1 list was given"

**Cause**: Using fluent.runtime syntax with list of locales

**Solution**:
```python
# ❌ fluent.runtime syntax
bundle = FluentBundle(['en-US'])

# ✅ FTLLexEngine syntax
bundle = FluentBundle('en-US')
```

---

### Issue 2: "FluentResource is not defined"

**Cause**: Importing non-existent FluentResource

**Solution**:
```python
# ❌ fluent.runtime
from fluent.runtime import FluentResource  # Old library had wrapper class

# ✅ FTLLexEngine - no wrapper needed
bundle.add_resource(ftl_source)  # Direct string

# Or if you need AST manipulation
from ftllexengine import parse_ftl
from ftllexengine.syntax.ast import Resource
resource_ast = parse_ftl(ftl_source)
```

---

### Issue 3: "format_pattern() missing required argument: 'message_id'"

**Cause**: Using fluent.runtime pattern-first API

**Solution**:
```python
# ❌ fluent.runtime - requires get_message step
msg = bundle.get_message('hello')
result, errors = bundle.format_pattern(msg.value, {})

# ✅ FTLLexEngine - direct message ID
result, errors = bundle.format_pattern('hello', {})
```

---

### Issue 4: Import errors for specific exception types

**Cause**: Different exception hierarchy

**Solution**:
```python
# ❌ fluent.runtime
from fluent.runtime.errors import FluentFormatError

# ✅ FTLLexEngine - specific error types
from ftllexengine import (
    FluentError,              # Base
    FluentReferenceError,     # Missing messages
    FluentResolutionError,    # Runtime errors
)
# FluentCyclicReferenceError is in diagnostics submodule
from ftllexengine.diagnostics import FluentCyclicReferenceError
```

---

## Compatibility Notes

### What Works Identically

✅ Custom functions
✅ Built-in NUMBER and DATETIME functions
✅ Select expressions and plural rules
✅ Terms and message references
✅ Unicode bidi isolation
✅ Error handling philosophy (graceful degradation)

### What's Different

⚠️ Constructor takes single locale, not list
⚠️ No FluentResource wrapper - direct string to `add_resource()`
⚠️ Different exception types (but same behavior)
⚠️ Return immutable error tuples instead of mutable lists (`tuple[FluentError, ...]`)
⚠️ Python 3.13+ required (vs 3.6+)

### What's New in FTLLexEngine

✨ `FluentLocalization` for multi-locale
✨ `PathResourceLoader` for file systems
✨ `validate_resource()` for pre-flight validation
✨ `introspect_message()` for metadata
✨ `get_message_variables()` for variable discovery
✨ `get_message_ids()` for listing messages
✨ Full `mypy --strict` type safety
✨ Python 3.13 modern features
✨ **Bi-directional parsing** (not in fluent.runtime):
  - `parse_number()`, `parse_decimal()` - locale-aware number parsing
  - `parse_date()`, `parse_datetime()` - locale-aware date parsing
  - `parse_currency()` - currency parsing with symbol detection
  - Type guards: `is_valid_number()`, `is_valid_decimal()`, `is_valid_currency()`

---

## Migration Checklist

### Pre-Migration

- [ ] Verify Python 3.13+ available in all environments
- [ ] Review breaking changes section
- [ ] Identify custom function usage
- [ ] List all multi-locale fallback logic
- [ ] Backup current codebase

### During Migration

- [ ] Update `requirements.txt` or `pyproject.toml`
- [ ] Install FTLLexEngine: `pip install ftllexengine`
- [ ] Update imports: `fluent.runtime` → `ftllexengine`
- [ ] Change FluentBundle constructor (list → single locale)
- [ ] Remove FluentResource wrappers
- [ ] Update format_pattern calls (use message ID directly)
- [ ] Update error handling (tuple returns)
- [ ] Add multi-locale support with FluentLocalization
- [ ] Update type annotations

### Post-Migration

- [ ] Run full test suite
- [ ] Verify all .ftl files load correctly
- [ ] Test custom functions
- [ ] Test multi-locale fallback
- [ ] Test error handling
- [ ] Update documentation
- [ ] Update CI/CD to use Python 3.13+
- [ ] Performance testing (should be faster!)

---

## Getting Help

- **FTLLexEngine Documentation**: [docs/DOC_00_Index.md](docs/DOC_00_Index.md)
- **Examples**: [examples/](examples/)
- **Quick Reference**: [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
- **Issues**: https://github.com/resoltico/ftllexengine/issues

---

**fluent.runtime Version Referenced**: 0.4.0

**Note**: Babel is optional. Parser-only installation (`pip install ftllexengine`) works without external dependencies. For locale-aware formatting, install with `pip install ftllexengine[babel]`.

**Note**: For FTLLexEngine version-to-version upgrade guidance, see [CHANGELOG.md](../CHANGELOG.md).

**Feedback**: If you encounter migration issues not covered here, please open an issue!
