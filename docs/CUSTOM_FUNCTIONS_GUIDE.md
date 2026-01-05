---
afad: "3.1"
version: "0.54.0"
domain: custom-functions
updated: "2026-01-04"
route:
  keywords: [custom functions, add_function, fluent functions, factory pattern, locale-aware, formatting functions]
  questions: ["how to create custom function?", "how to add custom function?", "how to make locale-aware function?"]
---

# Advanced Custom Functions Guide

**Purpose**: Extend FTLLexEngine with custom formatting functions.
**Prerequisites**: Basic FluentBundle usage.

---

## Table of Contents

1. [Introduction](#introduction)
2. [When to Use Custom Functions](#when-to-use-custom-functions)
3. [Function Naming Conventions](#function-naming-conventions)
4. [Parameter Conventions](#parameter-conventions)
5. [Error Handling Patterns](#error-handling-patterns)
6. [Locale-Aware Functions (Factory Pattern)](#locale-aware-functions-factory-pattern)
7. [Integration with Babel for i18n](#integration-with-babel-for-i18n)
8. [Complete Examples](#complete-examples)
9. [Testing Custom Functions](#testing-custom-functions)
10. [Best Practices and Pitfalls](#best-practices-and-pitfalls)

---

## Introduction

FTLLexEngine includes built-in functions for common formatting needs:
- **NUMBER()**: Locale-aware number formatting
- **DATETIME()**: Locale-aware date/time formatting
- **CURRENCY()**: Locale-aware currency formatting

However, domain-specific applications often require custom formatters for specialized data types. This guide shows you how to implement custom functions that integrate seamlessly with FTLLexEngine's i18n infrastructure.

**What You'll Learn**:
- How to create custom functions that follow FTL conventions
- How to make functions locale-aware using the factory pattern
- How to integrate with Babel for CLDR-compliant formatting
- Best practices for error handling and thread safety

---

## When to Use Custom Functions

### Use Custom Functions For:
- **Domain-specific formatting**: Phone numbers, file sizes, durations, credit cards
- **Business logic**: Loyalty points, shipping estimates, inventory status
- **Rich text rendering**: Markdown, HTML sanitization, custom markup
- **Specialized localization**: Industry-specific terminology, custom plural rules

### Use Built-in Functions For:
- **Numbers**: Always use `NUMBER()` instead of Python's `format()`
- **Dates/Times**: Always use `DATETIME()` instead of `strftime()`
- **Currency**: Always use `CURRENCY()` instead of custom implementations

**Why?** Built-in functions use Babel for CLDR-compliant formatting, which handles:
- Locale-specific separators (1,234.56 vs 1.234,56 vs 1 234,56)
- Currency-specific decimal places (JPY: 0, BHD: 3)
- Symbol placement (en_US: "$1.23" vs lv_LV: "1,23 €")
- Right-to-left language support (Arabic, Hebrew)

---

## Function Naming Conventions

### FTL Naming Convention: UPPERCASE (Recommended)

By convention, FTL functions use UPPERCASE names to distinguish them from message references:

```python
# RECOMMENDED - FTL convention (UPPERCASE)
def FILESIZE(bytes_count: int | float) -> str:
    ...

def PHONE(number: str) -> str:
    ...

def MARKDOWN(text: str) -> str:
    ...
```

```python
# VALID BUT NOT RECOMMENDED - lowercase/camelCase works but breaks convention
def filesize(bytes_count: int | float) -> str:  # Works, but unconventional
    ...

def phoneNumber(number: str) -> str:  # Works, but unconventional
    ...
```

**Rationale**: FTL syntax is case-sensitive. UPPERCASE names are a convention that:
1. Visually distinguishes functions from message references in FTL code
2. Matches the style of built-in functions (NUMBER, DATETIME)
3. Makes function calls immediately recognizable

**Note**: Function names can use any case (lowercase, camelCase, UPPERCASE). UPPERCASE remains the recommended convention for consistency with built-in functions.

### Python Linters

Disable naming warnings for FTL functions:

```python
def FILESIZE(bytes_count: int | float) -> str:  # noqa: N802
    """Format file size."""
    ...

# Or use pylint disable
def PHONE(number: str) -> str:  # pylint: disable=invalid-name
    """Format phone number."""
    ...
```

---

## Parameter Conventions

### Positional vs Keyword Arguments

FTL function calls use **named parameters** for all arguments except the first:

```ftl
# FTL syntax
file-size = { FILESIZE($bytes, precision: 2) }
phone = { PHONE($number, format_style: "international") }
```

**Python implementation must use keyword-only arguments** after the first parameter:

```python
# CORRECT - Uses * to enforce keyword-only args
def FILESIZE(bytes_count: int | float, *, precision: int = 2) -> str:
    """Format file size in human-readable format.

    Args:
        bytes_count: Number of bytes (positional)
        precision: Decimal precision (keyword-only with default)
    """
    ...

def PHONE(number: str, *, format_style: str = "international") -> str:
    """Format phone number.

    Args:
        number: Phone number (positional)
        format_style: Format type (keyword-only with default)
    """
    ...
```

```python
# WRONG - Missing * separator
def FILESIZE(bytes_count: int | float, precision: int = 2) -> str:  # ❌ Wrong
    ...
```

### Parameter Naming: snake_case

Use Python's `snake_case` convention for parameter names:

```python
# CORRECT
def PHONE(number: str, *, format_style: str = "international") -> str:
    ...

# WRONG - Don't use camelCase
def PHONE(number: str, *, formatStyle: str = "international") -> str:  # ❌ Wrong
    ...
```

**Why?** FunctionRegistry automatically bridges FTL's camelCase to Python's snake_case:

```ftl
# FTL uses camelCase
phone = { PHONE($number, formatStyle: "international") }
```

```python
# Python receives snake_case
def PHONE(number: str, *, format_style: str = "international") -> str:
    # format_style receives "international"
    ...
```

**Supported conversions**:
- `formatStyle` → `format_style`
- `currencyDisplay` → `currency_display`
- `minimumFractionDigits` → `minimum_fraction_digits`

---

## Error Handling Patterns

### Rule #1: Custom Functions MUST NEVER Raise Exceptions

Fluent's error model requires graceful degradation:

```python
# CORRECT - Returns fallback on error
def FILESIZE(bytes_count: int | float, *, precision: int = 2) -> str:
    """Format file size."""
    try:
        bytes_count = float(bytes_count)
        # ... formatting logic ...
        return f"{bytes_count:.{precision}f} {unit}"
    except (ValueError, TypeError):
        # Graceful fallback for invalid input
        return f"{bytes_count} bytes"
    except Exception:
        # Catch-all for unexpected errors
        return str(bytes_count)
```

```python
# WRONG - Raising exceptions crashes the application
def FILESIZE(bytes_count: int | float, *, precision: int = 2) -> str:
    if not isinstance(bytes_count, (int, float)):
        raise TypeError("bytes_count must be numeric")  # ❌ NEVER do this
    ...
```

### Rule #2: Return Readable Fallbacks

When errors occur, return a fallback that helps developers debug:

```python
# GOOD - Descriptive fallback
def CURRENCY_CUSTOM(amount: float, *, currency_code: str = "USD") -> str:
    try:
        from babel import numbers
        return numbers.format_currency(amount, currency_code, locale="en_US")
    except ImportError:
        return f"{currency_code} {amount:.2f}"  # Shows what failed
    except Exception:
        return f"{currency_code} {amount}"  # Minimal fallback
```

```python
# BAD - Useless fallback
def CURRENCY_CUSTOM(amount: float, *, currency_code: str = "USD") -> str:
    try:
        ...
    except Exception:
        return "???"  # ❌ Not helpful for debugging
```

### Rule #3: Log Debug Information (Optional)

For production deployments, log unexpected errors:

```python
import logging

logger = logging.getLogger(__name__)

def PHONE(number: str, *, format_style: str = "international") -> str:
    """Format phone number."""
    try:
        # ... formatting logic ...
        return formatted_number
    except Exception as e:
        logger.debug(f"PHONE formatting failed: {e}")
        return str(number)
```

**Note**: Use `logger.debug()`, not `logger.warning()`, since formatting errors are expected in normal operation (e.g., user input).

---

## Locale-Aware Functions (Factory Pattern)

### Problem: Functions Need Bundle's Locale

Custom functions often need to format differently based on the bundle's locale:

```python
# How do we make GREETING() use the bundle's locale?
bundle = FluentBundle("lv_LV")
bundle.add_function("GREETING", ???)  # Need access to "lv_LV"
```

### Solution: Factory Pattern

Create a **factory function** that captures the bundle's locale in a closure:

```python
def make_greeting_function(bundle_locale: str) -> Callable:
    """Factory for locale-aware greeting function.

    Args:
        bundle_locale: The bundle's locale string (e.g., "lv_LV", "de_DE")

    Returns:
        GREETING function customized for the locale
    """
    def GREETING(name: str, *, formal: str = "false") -> str:
        """Locale-aware greeting.

        Args:
            name: Person's name
            formal: "true" for formal greeting, "false" for informal

        Returns:
            Localized greeting
        """
        is_formal = formal.lower() == "true"
        locale_lower = bundle_locale.lower()

        if locale_lower.startswith("lv"):
            return f"Labdien, {name}!" if is_formal else f"Sveiki, {name}!"
        if locale_lower.startswith("de"):
            return f"Guten Tag, {name}!" if is_formal else f"Hallo, {name}!"
        if locale_lower.startswith("pl"):
            return f"Dzień dobry, {name}!" if is_formal else f"Cześć, {name}!"
        return f"Good day, {name}!" if is_formal else f"Hello, {name}!"

    return GREETING
```

### Usage

```python
# Create locale-specific greeting function
bundle_en = FluentBundle("en_US")
bundle_en.add_function("GREETING", make_greeting_function(bundle_en.locale))

bundle_lv = FluentBundle("lv_LV")
bundle_lv.add_function("GREETING", make_greeting_function(bundle_lv.locale))

# FTL usage (same in all locales)
bundle_en.add_resource('greet = { GREETING($name, formal: "false") }')
bundle_lv.add_resource('greet = { GREETING($name, formal: "false") }')

# Different output based on locale
result, _ = bundle_en.format_pattern("greet", {"name": "Alice"})
# → "Hello, Alice!"

result, _ = bundle_lv.format_pattern("greet", {"name": "Anna"})
# → "Sveiki, Anna!"
```

### Alternative: Automatic Locale Injection

Instead of using the factory pattern, use the `@fluent_function` decorator for automatic locale injection:

```python
from ftllexengine import FluentBundle, fluent_function


@fluent_function(inject_locale=True)
def GREETING(name: str, locale_code: str, /, *, formal: str = "false") -> str:
    """Locale-aware greeting with automatic locale injection.

    Args:
        name: Person's name (positional, from FTL)
        locale_code: Bundle's locale (auto-injected by runtime)
        formal: "true" for formal greeting, "false" for informal (keyword)

    Returns:
        Localized greeting
    """
    is_formal = formal.lower() == "true"
    locale_lower = locale_code.lower()

    if locale_lower.startswith("lv"):
        return f"Labdien, {name}!" if is_formal else f"Sveiki, {name}!"
    if locale_lower.startswith("de"):
        return f"Guten Tag, {name}!" if is_formal else f"Hallo, {name}!"
    return f"Good day, {name}!" if is_formal else f"Hello, {name}!"


# Register - locale will be injected automatically
bundle = FluentBundle("lv_LV")
bundle.add_function("GREETING", GREETING)

bundle.add_resource('greet = { GREETING($name, formal: "false") }')
result, _ = bundle.format_pattern("greet", {"name": "Anna"})
# → "Sveiki, Anna!"
```

**How it works:**
1. Apply `@fluent_function(inject_locale=True)` to your function
2. The runtime checks for this via `FunctionRegistry.should_inject_locale()`
3. When calling the function, the bundle's locale is injected as the second positional argument

**When to use which approach:**

| Approach | Use When |
|:---------|:---------|
| Factory pattern | Function needs locale at definition time (closures) |
| `@fluent_function(inject_locale=True)` | Function accepts locale as parameter at call time |
| Neither | Function doesn't need locale (e.g., FILESIZE) |

### Alternative: Use Babel Locale

For CLDR-compliant formatting, create a LocaleContext inside the function:

```python
def make_date_range_function(bundle_locale: str) -> Callable:
    """Factory for locale-aware date range formatter."""
    def DATE_RANGE(start: str, end: str) -> str:
        """Format date range with locale-specific formatting."""
        from ftllexengine.runtime.locale_context import LocaleContext
        from datetime import datetime

        try:
            ctx = LocaleContext(bundle_locale)
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)

            # Use Babel for locale-aware formatting
            from babel.dates import format_date

            start_formatted = format_date(start_dt, format="medium", locale=ctx.babel_locale)
            end_formatted = format_date(end_dt, format="medium", locale=ctx.babel_locale)

            return f"{start_formatted} – {end_formatted}"
        except Exception:
            return f"{start} – {end}"

    return DATE_RANGE
```

---

## Integration with Babel for i18n

### When to Use Babel

Use Babel for **international data types** where formatting rules vary by locale:
- Dates and times
- Numbers and percentages
- Currency
- Units (distances, weights, volumes)
- Lists and conjunctions

### Example: Locale-Aware Custom Currency (Educational Only)

**NOTE**: FTLLexEngine has a built-in `CURRENCY()` function. This example is for educational purposes only, demonstrating how to integrate Babel in custom functions.

```python
def CURRENCY_CUSTOM_EXAMPLE(amount: float, *, currency_code: str = "USD", locale: str = "en_US") -> str:
    """Format currency with CLDR-compliant locale-aware formatting.

    EDUCATIONAL EXAMPLE ONLY - Use built-in CURRENCY() function instead!

    This demonstrates proper Babel integration for i18n-aware formatting.

    Args:
        amount: Monetary amount
        currency_code: ISO 4217 currency code (USD, EUR, JPY, BHD, etc.)
        locale: Babel locale identifier for formatting

    Returns:
        Formatted currency string using CLDR rules

    Why the naive approach is wrong:
        - Hardcoded symbol placement (always before amount) - wrong for many locales
        - Hardcoded 2 decimals - wrong for JPY (0 decimals), BHD (3 decimals)
        - Ignored locale-specific spacing and formatting rules
        - Did not use CLDR data
    """
    try:
        from babel import numbers

        # Use Babel's format_currency for proper CLDR compliance
        return numbers.format_currency(amount, currency_code, locale=locale)
    except ImportError:
        # Fallback if Babel not installed (should never happen in FTLLexEngine env)
        return f"{currency_code} {amount:.2f}"
    except Exception:
        # Fluent functions must never crash
        return f"{currency_code} {amount}"
```

### Why Babel Integration Matters

```python
# WRONG - Naive implementation
def CURRENCY_NAIVE(amount: float, *, currency_code: str = "USD") -> str:
    symbols = {"USD": "$", "EUR": "€", "JPY": "¥"}
    symbol = symbols.get(currency_code, currency_code)
    return f"{symbol}{amount:,.2f}"  # ❌ Many problems!

# Problems with naive approach:
# 1. Always puts symbol before amount (wrong for lv_LV, de_DE)
# 2. Always uses 2 decimals (wrong for JPY: 0, BHD: 3)
# 3. Uses English thousand separators (wrong for de_DE: period, lv_LV: space)
# 4. Missing currency codes (180+ currencies in ISO 4217)
```

```python
# CORRECT - Babel integration
from babel import numbers

def CURRENCY_CORRECT(amount: float, *, currency_code: str = "USD", locale: str = "en_US") -> str:
    try:
        return numbers.format_currency(amount, currency_code, locale=locale)
    except Exception:
        return f"{currency_code} {amount}"

# Benefits:
# ✅ CLDR-compliant symbol placement
# ✅ Currency-specific decimal places
# ✅ Locale-specific grouping and separators
# ✅ Supports all ISO 4217 currencies
# ✅ Handles RTL languages (Arabic, Hebrew)
```

---

## Complete Examples

### Example 1: PHONE Formatting

```python
def PHONE(number: str, *, format_style: str = "international") -> str:
    """Format phone number.

    Args:
        number: Phone number (digits only or with separators)
        format_style: "international", "national", or "compact"

    Returns:
        Formatted phone number
    """
    # Remove non-digits
    digits = "".join(c for c in str(number) if c.isdigit())

    if format_style == "international" and len(digits) >= 10:
        # US/Canada format: +1 (555) 123-4567
        return f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    if format_style == "national" and len(digits) >= 10:
        # (555) 123-4567
        return f"({digits[-10:-7]}) {digits[-7:-4]}-{digits[-4:]}"
    if format_style == "compact":
        # 5551234567
        return digits
    return number  # Fallback
```

**Usage**:
```python
bundle.add_function("PHONE", PHONE)
bundle.add_resource("""
support-phone = Call us at { PHONE($number, format_style: "international") }
""")

result, _ = bundle.format_pattern("support-phone", {"number": "15551234567"})
# → "Call us at +1 (555) 123-4567"
```

---

### Example 2: MARKDOWN Rendering

```python
import re

def MARKDOWN(text: str, *, render: str = "html") -> str:
    """Render markdown to HTML (simplified).

    Args:
        text: Markdown text
        render: Output format ("html" or "plain")

    Returns:
        Rendered text
    """
    if render == "plain":
        # Strip markdown syntax
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # Remove **bold**
        text = re.sub(r"\*(.*?)\*", r"\1", text)  # Remove *italic*
        return re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)  # Remove [links](url)

    # Simple HTML rendering
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)  # **bold**
    text = re.sub(r"\*(.*?)\*", r"<em>\1</em>", text)  # *italic*
    return re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', text)  # [text](url)
```

**Usage**:
```python
bundle.add_function("MARKDOWN", MARKDOWN)
bundle.add_resource("""
welcome-html = { MARKDOWN($text, render: "html") }
welcome-plain = { MARKDOWN($text, render: "plain") }
""")

result, _ = bundle.format_pattern("welcome-html", {
    "text": "Welcome to **FTLLexEngine**! Visit [our site](https://example.com)."
})
# → "Welcome to <strong>FTLLexEngine</strong>! Visit <a href=\"https://example.com\">our site</a>."
```

---

### Example 3: FILESIZE Formatting

```python
def FILESIZE(bytes_count: int | float, *, precision: int = 2) -> str:
    """Format file size in human-readable format.

    Args:
        bytes_count: Number of bytes
        precision: Decimal precision

    Returns:
        Human-readable file size (e.g., "1.23 MB")
    """
    try:
        bytes_count = float(bytes_count)
        units = ["B", "KB", "MB", "GB", "TB", "PB"]

        for unit in units:
            if bytes_count < 1024.0:
                return f"{bytes_count:.{precision}f} {unit}"
            bytes_count /= 1024.0

        return f"{bytes_count:.{precision}f} EB"
    except (ValueError, TypeError):
        return f"{bytes_count} bytes"
```

**Usage**:
```python
bundle.add_function("FILESIZE", FILESIZE)
bundle.add_resource("""
file-info = { $filename } ({ FILESIZE($bytes) })
""")

result, _ = bundle.format_pattern("file-info", {
    "filename": "video.mp4",
    "bytes": 157286400
})
# → "video.mp4 (150.00 MB)"
```

---

### Example 4: DURATION Formatting

```python
def DURATION(seconds: int | float, *, format_style: str = "long") -> str:
    """Format duration in human-readable format.

    Args:
        seconds: Duration in seconds
        format_style: "long", "short", or "compact"

    Returns:
        Formatted duration
    """
    try:
        seconds = int(seconds)
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, secs = divmod(remainder, 60)

        if format_style == "long":
            parts = []
            if days > 0:
                parts.append(f"{days} day{'s' if days != 1 else ''}")
            if hours > 0:
                parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes > 0:
                parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            if secs > 0 or not parts:
                parts.append(f"{secs} second{'s' if secs != 1 else ''}")
            return ", ".join(parts)

        if format_style == "short":
            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0:
                parts.append(f"{hours}h")
            if minutes > 0:
                parts.append(f"{minutes}m")
            if secs > 0 or not parts:
                parts.append(f"{secs}s")
            return " ".join(parts)

        # Compact
        if days > 0:
            return f"{days}d{hours}h"
        if hours > 0:
            return f"{hours}h{minutes}m"
        if minutes > 0:
            return f"{minutes}m{secs}s"
        return f"{secs}s"
    except (ValueError, TypeError):
        return str(seconds)
```

**Usage**:
```python
bundle.add_function("DURATION", DURATION)
bundle.add_resource("""
video-duration = Duration: { DURATION($seconds, format_style: "short") }
""")

result, _ = bundle.format_pattern("video-duration", {"seconds": 3725})
# → "Duration: 1h 2m 5s"
```

---

## Testing Custom Functions

### Unit Tests

```python
import pytest
from ftllexengine import FluentBundle

class TestFileSizeFunction:
    """Test FILESIZE custom function."""

    def test_filesize_bytes(self) -> None:
        """Test file size in bytes."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_function("FILESIZE", FILESIZE)
        bundle.add_resource('size = { FILESIZE($bytes) }')

        result, errors = bundle.format_pattern("size", {"bytes": 512})
        assert result == "512.00 B"
        assert not errors

    def test_filesize_megabytes(self) -> None:
        """Test file size in megabytes."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_function("FILESIZE", FILESIZE)
        bundle.add_resource('size = { FILESIZE($bytes) }')

        result, errors = bundle.format_pattern("size", {"bytes": 157286400})
        assert result == "150.00 MB"
        assert not errors

    def test_filesize_precision(self) -> None:
        """Test file size with custom precision."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_function("FILESIZE", FILESIZE)
        bundle.add_resource('size = { FILESIZE($bytes, precision: 4) }')

        result, errors = bundle.format_pattern("size", {"bytes": 1536})
        assert result == "1.5000 KB"
        assert not errors

    def test_filesize_error_handling(self) -> None:
        """Test file size error handling."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_function("FILESIZE", FILESIZE)
        bundle.add_resource('size = { FILESIZE($bytes) }')

        result, errors = bundle.format_pattern("size", {"bytes": "invalid"})
        assert "bytes" in result  # Should return fallback
        assert not errors  # Function handles error gracefully
```

### Property-Based Testing with Hypothesis

```python
from hypothesis import given, strategies as st, settings

class TestFileSizeHypothesis:
    """Property-based tests for FILESIZE function."""

    @given(bytes_count=st.integers(min_value=0, max_value=10**15))
    @settings(max_examples=100)
    def test_filesize_never_crashes(self, bytes_count: int) -> None:
        """FILESIZE must never crash for any valid byte count."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_function("FILESIZE", FILESIZE)
        bundle.add_resource('size = { FILESIZE($bytes) }')

        result, errors = bundle.format_pattern("size", {"bytes": bytes_count})
        assert isinstance(result, str)
        assert len(result) > 0
        assert not errors

    @given(
        bytes_count=st.integers(min_value=0, max_value=10**15),
        precision=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=100)
    def test_filesize_precision_never_crashes(self, bytes_count: int, precision: int) -> None:
        """FILESIZE with precision must never crash."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_function("FILESIZE", FILESIZE)
        bundle.add_resource('size = { FILESIZE($bytes, precision: $prec) }')

        result, errors = bundle.format_pattern("size", {
            "bytes": bytes_count,
            "prec": precision
        })
        assert isinstance(result, str)
        assert len(result) > 0
```

---

## Best Practices and Pitfalls

### ✅ Best Practices

1. **Use `*` for keyword-only arguments**
   ```python
   def CUSTOM(value: str, *, option: str = "default") -> str:
       ...
   ```

2. **Return type must be `str`**
   ```python
   def CUSTOM(value: int) -> str:  # ✅ Returns str
       return str(value)
   ```

3. **Never raise exceptions**
   ```python
   def CUSTOM(value: str) -> str:
       try:
           return process(value)
       except Exception:
           return value  # ✅ Graceful fallback
   ```

4. **Use factory pattern for locale-aware functions**
   ```python
   def make_custom_function(bundle_locale: str) -> Callable:
       def CUSTOM(value: str) -> str:
           # Use bundle_locale here
           ...
       return CUSTOM

   bundle.add_function("CUSTOM", make_custom_function(bundle.locale))
   ```

5. **Integrate with Babel for i18n data types**
   ```python
   from babel import numbers, dates

   def CUSTOM(value: float, *, locale: str = "en_US") -> str:
       return numbers.format_decimal(value, locale=locale)
   ```

6. **Write comprehensive tests**
   - Unit tests for expected behavior
   - Property-based tests with Hypothesis for robustness
   - Error handling tests

7. **Document parameters clearly**
   ```python
   def CUSTOM(value: str, *, format_style: str = "default") -> str:
       """Short description.

       Args:
           value: Description of value parameter
           format_style: Description of format_style parameter

       Returns:
           Description of return value
       """
       ...
   ```

---

### ❌ Common Pitfalls

1. **Raising exceptions**
   ```python
   # WRONG
   def CUSTOM(value: int) -> str:
       if value < 0:
           raise ValueError("Negative values not allowed")  # ❌ Crashes!
       return str(value)

   # CORRECT
   def CUSTOM(value: int) -> str:
       if value < 0:
           return "0"  # ✅ Graceful fallback
       return str(value)
   ```

2. **Not using keyword-only arguments**
   ```python
   # WRONG
   def CUSTOM(value: str, option: str = "default") -> str:  # ❌ Missing *
       ...

   # CORRECT
   def CUSTOM(value: str, *, option: str = "default") -> str:  # ✅ Uses *
       ...
   ```

3. **Returning non-string types**
   ```python
   # WRONG
   def CUSTOM(value: int) -> int:  # ❌ Returns int
       return value * 2

   # CORRECT
   def CUSTOM(value: int) -> str:  # ✅ Returns str
       return str(value * 2)
   ```

4. **Using camelCase for parameters**
   ```python
   # WRONG
   def CUSTOM(value: str, *, formatStyle: str = "default") -> str:  # ❌ camelCase
       ...

   # CORRECT
   def CUSTOM(value: str, *, format_style: str = "default") -> str:  # ✅ snake_case
       ...
   ```

5. **Hardcoding locale-specific formatting**
   ```python
   # WRONG - Only works for US locale
   def CUSTOM_NUMBER(value: float) -> str:
       return f"${value:,.2f}"  # ❌ Always uses $ and US formatting

   # CORRECT - Uses Babel for locale-aware formatting
   def CUSTOM_NUMBER(value: float, *, locale: str = "en_US") -> str:
       from babel import numbers
       return numbers.format_currency(value, "USD", locale=locale)
   ```

6. **Not handling invalid input**
   ```python
   # WRONG - Crashes on invalid input
   def FILESIZE(bytes_count: int) -> str:
       return f"{bytes_count / 1024:.2f} KB"  # ❌ Crashes if bytes_count is string

   # CORRECT - Handles invalid input
   def FILESIZE(bytes_count: int | float) -> str:
       try:
           return f"{float(bytes_count) / 1024:.2f} KB"
       except (ValueError, TypeError):
           return f"{bytes_count} bytes"  # ✅ Fallback
   ```

7. **Ignoring thread safety**
   ```python
   # WRONG - Using global mutable state
   _cache = {}  # ❌ Not thread-safe!

   def CUSTOM(value: str) -> str:
       if value not in _cache:
           _cache[value] = expensive_computation(value)
       return _cache[value]

   # CORRECT - Use immutable data or thread-local storage
   import threading

   _thread_local = threading.local()

   def CUSTOM(value: str) -> str:
       if not hasattr(_thread_local, 'cache'):
           _thread_local.cache = {}
       if value not in _thread_local.cache:
           _thread_local.cache[value] = expensive_computation(value)
       return _thread_local.cache[value]
   ```

---

## Summary

**Key Takeaways**:

1. **Use built-in functions** for common data types (NUMBER, DATETIME, CURRENCY)
2. **Create custom functions** for domain-specific formatting needs
3. **Follow naming conventions**: UPPERCASE for function names, snake_case for parameters
4. **Never raise exceptions** - always return graceful fallbacks
5. **Use factory pattern** for locale-aware functions
6. **Integrate with Babel** for CLDR-compliant i18n formatting
7. **Test comprehensively** with unit tests and property-based tests

**For More Examples**:
- See [examples/custom_functions.py](../examples/custom_functions.py) for complete working code
- See [tests/test_custom_functions.py](../tests/test_custom_functions.py) for test patterns

**Questions?**
- Open an issue: https://github.com/resoltico/ftllexengine/issues
- Read the full API docs: [DOC_00_Index.md](DOC_00_Index.md)

---

**Python Requirement**: 3.13+
