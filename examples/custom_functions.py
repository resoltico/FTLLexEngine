"""Custom Functions Example - Demonstrating FluentBundle.add_function() API.

    FTLLexEngine includes built-in CURRENCY() function.
    The CURRENCY example below is for EDUCATIONAL PURPOSES ONLY to demonstrate
    how custom functions can properly integrate with Babel for i18n.

    In production, use the built-in CURRENCY() function instead:
        price = { CURRENCY($amount, currency: "EUR") }

This example shows how to extend FTLLexEngine with custom formatting functions
for domain-specific needs:

1. CURRENCY formatting (EDUCATIONAL - shows proper Babel integration, use built-in instead!)
2. PHONE number formatting
3. MARKDOWN rendering
4. FILESIZE human-readable formatting
5. DURATION time formatting
6. Locale-aware custom functions using factory pattern (capturing bundle.locale)

WARNING: Examples use use_isolating=False for cleaner terminal output.
NEVER disable bidi isolation in production applications that support RTL languages.

Python 3.13+.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from ftllexengine import FluentBundle


# Example 1: CURRENCY Formatting (EDUCATIONAL - Use Built-in CURRENCY() Instead!)
def CURRENCY_CUSTOM_EXAMPLE(  # pylint: disable=invalid-name
    amount: int | Decimal, *, currency_code: str = "USD", locale: str = "en_US"
) -> str:
    """Format currency with CLDR-compliant locale-aware formatting.

    EDUCATIONAL EXAMPLE ONLY - FTLLexEngine has built-in CURRENCY() function!

    This example demonstrates how to properly implement currency formatting
    using Babel for i18n, handling locale-specific symbol placement, decimal
    precision, and spacing.

    DO NOT USE THIS IN PRODUCTION - use the built-in CURRENCY() function instead:
        bundle.add_resource('price = { CURRENCY($amount, currency: "EUR") }')

    FTL function naming convention: UPPERCASE names match FTL spec.

    Args:
        amount: Monetary amount
        currency_code: ISO 4217 currency code (USD, EUR, GBP, JPY, BHD, etc.)
        locale: Babel locale identifier for formatting

    Returns:
        Formatted currency string using CLDR rules

    Note:
        The built-in CURRENCY() function uses the bundle's locale automatically.
        This example shows how custom functions can leverage Babel for i18n.

    Why the old example was broken:
        - Hardcoded symbol placement (always before amount) - wrong for many locales
        - Hardcoded 2 decimals - wrong for JPY (0 decimals), BHD (3 decimals)
        - Ignored locale-specific spacing and formatting rules
        - Did not use CLDR data
    """
    try:
        # Import Babel inside function to keep example self-contained
        from babel import numbers  # pylint: disable=import-outside-toplevel

        # Use Babel's format_currency for proper CLDR compliance
        return numbers.format_currency(amount, currency_code, locale=locale)
    except ImportError:
        # Fallback if Babel not installed (should never happen in FTLLexEngine env)
        return f"{currency_code} {amount:.2f}"
    except Exception:  # pylint: disable=broad-exception-caught
        # Fluent functions must never crash
        return f"{currency_code} {amount}"


# Example 2: PHONE Formatting
def PHONE(number: str, *, format_style: str = "international") -> str:  # pylint: disable=invalid-name
    """Format phone number.

    FTL function naming convention: UPPERCASE name.

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
    return number


# Example 3: MARKDOWN Rendering (Simple)
def MARKDOWN(text: str, *, render: str = "html") -> str:  # pylint: disable=invalid-name
    """Render markdown to HTML (simplified).

    FTL function naming convention: UPPERCASE name.

    Args:
        text: Markdown text
        render: Output format ("html" or "plain")

    Returns:
        Rendered text
    """
    if render == "plain":
        # Strip markdown syntax
        # Remove **bold**
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        # Remove *italic*
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        # Remove [links](url)
        return re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    # Simple HTML rendering
    # **bold** → <strong>bold</strong>
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    # *italic* → <em>italic</em>
    text = re.sub(r"\*(.*?)\*", r"<em>\1</em>", text)
    # [text](url) → <a href="url">text</a>
    return re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', text)


# Example 4: FILESIZE Formatting
def FILESIZE(bytes_count: int | Decimal, *, precision: int = 2) -> str:  # pylint: disable=invalid-name
    """Format file size in human-readable format.

    FTL function naming convention: UPPERCASE name.

    Args:
        bytes_count: Number of bytes
        precision: Decimal precision

    Returns:
        Human-readable file size (e.g., "1.23 MB")
    """
    size = Decimal(bytes_count) if isinstance(bytes_count, int) else bytes_count
    units = ["B", "KB", "MB", "GB", "TB", "PB"]

    for unit in units:
        if size < Decimal("1024"):
            return f"{size:.{precision}f} {unit}"
        size /= Decimal("1024")

    return f"{size:.{precision}f} EB"


# Example 5: DURATION Formatting
def DURATION(seconds: int | Decimal, *, format_style: str = "long") -> str:  # noqa: PLR0912  # pylint: disable=invalid-name,too-many-branches
    """Format duration in human-readable format.

    FTL function naming convention: UPPERCASE name.
    Branch complexity unavoidable for comprehensive time formatting.

    Args:
        seconds: Duration in seconds
        format_style: "long", "short", or "compact"

    Returns:
        Formatted duration
    """
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
    if days > 0:
        return f"{days}d{hours}h"
    if hours > 0:
        return f"{hours}h{minutes}m"
    if minutes > 0:
        return f"{minutes}m{secs}s"
    return f"{secs}s"


# Example 6: Locale-Aware Custom Function (Factory Pattern)
def make_greeting_function(bundle_locale: str) -> Any:
    """Factory for locale-aware greeting function.

    Args:
        bundle_locale: The bundle's locale string

    Returns:
        Greeting function customized for the locale
    """
    def GREETING(name: str, *, formal: str = "false") -> str:  # pylint: disable=invalid-name
        """Locale-aware greeting.

        FTL function naming convention: UPPERCASE name.

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


# Demonstration
if __name__ == "__main__":
    print("=" * 60)
    print("Custom Functions Example")
    print("=" * 60)

    bundle = FluentBundle("en_US", use_isolating=False)

    # Register custom functions
    # NOTE: CURRENCY is NOW BUILT-IN! Use the built-in CURRENCY() function instead
    # The CURRENCY_CUSTOM_EXAMPLE is shown for educational purposes only
    # bundle.add_function("CURRENCY_CUSTOM_EXAMPLE", CURRENCY_CUSTOM_EXAMPLE)  # Don't use!

    bundle.add_function("PHONE", PHONE)
    bundle.add_function("MARKDOWN", MARKDOWN)
    bundle.add_function("FILESIZE", FILESIZE)
    bundle.add_function("DURATION", DURATION)
    # Create locale-aware function for English
    bundle.add_function("GREETING", make_greeting_function(bundle.locale))

    # Add FTL resource using built-in and custom functions.
    # FTL named argument convention: multi-word parameter names use camelCase.
    # The registry maps FTL camelCase → Python snake_case automatically.
    # Example: FTL formatStyle → Python format_style
    bundle.add_resource("""
# E-commerce examples (using BUILT-IN CURRENCY function)
product-price = { CURRENCY($amount, currency: "EUR") }
support-phone = Call us at { PHONE($number, formatStyle: "international") }

# File management
file-info = { $filename } ({ FILESIZE($bytes) })

# Video player
video-duration = Duration: { DURATION($seconds, formatStyle: "short") }

# Rich text
welcome-message = { MARKDOWN($text, render: "html") }
welcome-plain = { MARKDOWN($text, render: "plain") }

# Locale-aware greeting
greet = { GREETING($name, formal: "false") }
greet-formal = { GREETING($name, formal: "true") }
""")

    # Example 1: Currency (using BUILT-IN CURRENCY function)
    print("\n" + "-" * 60)
    print("Example 1: CURRENCY Formatting (BUILT-IN)")
    print("-" * 60)
    result, _ = bundle.format_pattern("product-price", {"amount": Decimal("1234.56")})
    print(f"Product price: {result}")
    print("Note: Using built-in CURRENCY() function with CLDR-compliant formatting")
    # Output: Product price: €1,234.56

    # Example 2: Phone
    print("\n" + "-" * 60)
    print("Example 2: PHONE Formatting")
    print("-" * 60)
    result, _ = bundle.format_pattern("support-phone", {"number": "15551234567"})
    print(f"Support: {result}")
    # Output: Support: Call us at +1 (555) 123-4567

    # Example 3: File size
    print("\n" + "-" * 60)
    print("Example 3: FILESIZE Formatting")
    print("-" * 60)
    result, _ = bundle.format_pattern("file-info", {
        "filename": "video.mp4",
        "bytes": 157286400  # ~150 MB
    })
    print(f"File: {result}")
    # Output: File: video.mp4 (150.00 MB)

    # Example 4: Duration
    print("\n" + "-" * 60)
    print("Example 4: DURATION Formatting")
    print("-" * 60)
    result, _ = bundle.format_pattern("video-duration", {"seconds": 3725})
    print(f"Video: {result}")
    # Output: Video: Duration: 1h 2m 5s

    # Example 5: Markdown
    print("\n" + "-" * 60)
    print("Example 5: MARKDOWN Rendering")
    print("-" * 60)
    result_html, _ = bundle.format_pattern("welcome-message", {
        "text": "Welcome to **FTLLexEngine**! Visit [our site](https://example.com)."
    })
    print(f"HTML: {result_html}")
    # Output: HTML: Welcome to <strong>FTLLexEngine</strong>!
    # Visit <a href="https://example.com">our site</a>.

    result_plain, _ = bundle.format_pattern("welcome-plain", {
        "text": "Welcome to **FTLLexEngine**! Visit [our site](https://example.com)."
    })
    print(f"Plain: {result_plain}")
    # Output: Plain: Welcome to FTLLexEngine! Visit our site.

    # Example 6: Locale-aware greeting
    print("\n" + "-" * 60)
    print("Example 6: GREETING (Locale-Aware)")
    print("-" * 60)
    result, _ = bundle.format_pattern("greet", {"name": "Alice"})
    print(f"Informal: {result}")
    # Output: Informal: Hello, Alice!

    result, _ = bundle.format_pattern("greet-formal", {"name": "Dr. Smith"})
    print(f"Formal: {result}")
    # Output: Formal: Good day, Dr. Smith!

    # Test with different locale - demonstrating factory pattern for locale awareness
    print("\nTesting with Latvian locale:")
    lv_bundle = FluentBundle("lv", use_isolating=False)
    # Create locale-specific GREETING function using factory
    lv_bundle.add_function("GREETING", make_greeting_function(lv_bundle.locale))
    lv_bundle.add_resource('greet = { GREETING($name, formal: "false") }')
    result, errors = lv_bundle.format_pattern("greet", {"name": "Anna"})
    if errors:
        for error in errors:
            diag = error.diagnostic
            print(f"Error: {diag.message if diag else error.message}")
    print(f"Latvian informal: {result}")
    # Output: Latvian informal: Sveiki, Anna!

    print("\n" + "=" * 60)
    print("[SUCCESS] All custom function examples completed!")
    print("=" * 60)
