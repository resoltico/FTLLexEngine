"""Quickstart example for ftllexengine.

This example demonstrates basic usage of ftllexengine for localization.

WARNING: Examples use use_isolating=False for cleaner terminal output.
NEVER disable bidi isolation in production applications that support RTL languages.
Always use the default use_isolating=True for production code.

Note: Examples ignore the 'errors' return value for brevity. In production,
always check errors and log/report translation issues.
"""

import tempfile
from pathlib import Path

from ftllexengine import FluentBundle

# Example 1: Simple message
print("=" * 50)
print("Example 1: Simple Message")
print("=" * 50)

bundle = FluentBundle("en", use_isolating=False)
bundle.add_resource("""
hello = Hello, World!
welcome = Welcome to ftllexengine!
""")

result, _ = bundle.format_pattern("hello")
print(result)
# Output: Hello, World!

result, _ = bundle.format_pattern("welcome")
print(result)
# Output: Welcome to ftllexengine!

# Example 2: Variables
print("\n" + "=" * 50)
print("Example 2: Variable Interpolation")
print("=" * 50)

bundle.add_resource("""
greeting = Hello, { $name }!
user-info = { $firstName } { $lastName } (Age: { $age })
""")

result, _ = bundle.format_pattern("greeting", {"name": "Alice"})
print(result)
# Output: Hello, Alice!

result, _ = bundle.format_pattern("user-info", {
    "firstName": "Bob",
    "lastName": "Smith",
    "age": 30
})
print(result)
# Output: Bob Smith (Age: 30)

# Example 3: Plurals (English)
print("\n" + "=" * 50)
print("Example 3: Plural Forms (English)")
print("=" * 50)

bundle.add_resource("""
emails = You have { $count ->
    [one] one email
   *[other] { $count } emails
}.
""")

result, _ = bundle.format_pattern("emails", {"count": 0})
print(result)
# Output: You have 0 emails.

result, _ = bundle.format_pattern("emails", {"count": 1})
print(result)
# Output: You have one email.

result, _ = bundle.format_pattern("emails", {"count": 5})
print(result)
# Output: You have 5 emails.

# Example 4: Plurals (Latvian - 3 forms!)
print("\n" + "=" * 50)
print("Example 4: Latvian Plurals (3 forms)")
print("=" * 50)

lv_bundle = FluentBundle("lv", use_isolating=False)
lv_bundle.add_resource("""
items = { $count ->
    [zero] { $count } vienību
    [one] viena vienība
   *[other] { $count } vienības
}
""")

result, _ = lv_bundle.format_pattern("items", {"count": 0})
print(result)
# Output: 0 vienību

result, _ = lv_bundle.format_pattern("items", {"count": 1})
print(result)
# Output: viena vienība

result, _ = lv_bundle.format_pattern("items", {"count": 5})
print(result)
# Output: 5 vienības

result, _ = lv_bundle.format_pattern("items", {"count": 21})
print(result)
# Output: viena vienība (21 ends in 1, uses "one" category per Latvian CLDR rules)

# Example 5: Select Expressions
print("\n" + "=" * 50)
print("Example 5: Select Expressions (Gender)")
print("=" * 50)

bundle.add_resource("""
greeting-formal = { $gender ->
    [male] Mr. { $name }
    [female] Ms. { $name }
   *[other] { $name }
}
""")

result, _ = bundle.format_pattern("greeting-formal", {"gender": "male", "name": "Johnson"})
print(result)
# Output: Mr. Johnson

result, _ = bundle.format_pattern("greeting-formal", {"gender": "female", "name": "Williams"})
print(result)
# Output: Ms. Williams

result, _ = bundle.format_pattern("greeting-formal", {"gender": "neutral", "name": "Taylor"})
print(result)
# Output: Taylor

# Example 6: Number Formatting
print("\n" + "=" * 50)
print("Example 6: Number Formatting")
print("=" * 50)

bundle.add_resource("""
price = Price: { NUMBER($amount, minimumFractionDigits: 2) } EUR
discount = Discount: { NUMBER($percent, maximumFractionDigits: 0) }%
""")

result, _ = bundle.format_pattern("price", {"amount": 19.5})
print(result)
# Output: Price: 19.50 EUR

result, _ = bundle.format_pattern("price", {"amount": 100})
print(result)
# Output: Price: 100.00 EUR

result, _ = bundle.format_pattern("discount", {"percent": 15.75})
print(result)
# Output: Discount: 16%

# Example 7: Loading from File
print("\n" + "=" * 50)
print("Example 7: Loading from File")
print("=" * 50)

# Create a temporary FTL file
with tempfile.NamedTemporaryFile(mode="w", suffix=".ftl", delete=False, encoding="utf-8") as tmp:
    tmp.write("""
# Sample FTL file
app-name = FTLLexEngine Demo
app-tagline = Best-in-class FTL localization for Python

about = { app-name } - { app-tagline }
""")
    sample_ftl = Path(tmp.name)

# Load from file
ftl_content = sample_ftl.read_text(encoding="utf-8")
file_bundle = FluentBundle("en", use_isolating=False)
file_bundle.add_resource(ftl_content)

result, _ = file_bundle.format_pattern("about")
print(result)
# Output: FTLLexEngine Demo - Best-in-class FTL localization for Python

# Clean up
sample_ftl.unlink()

# Example 8: Proper Error Handling (Production Pattern)
print("\n" + "=" * 50)
print("Example 8: Proper Error Handling")
print("=" * 50)

error_bundle = FluentBundle("en", use_isolating=False)
error_bundle.add_resource("""
welcome = Hello, { $name }!
missing-var = Value: { $undefined }
circular-a = { circular-b }
circular-b = { circular-a }
""")

# Production pattern: ALWAYS check errors and log them
result, errors = error_bundle.format_pattern("welcome", {"name": "Alice"})
if errors:
    print("[ERROR] Translation errors for 'welcome':")
    for error in errors:
        print(f"  - {type(error).__name__}: {error}")
else:
    print(f"[OK] {result}")

# Missing variable example
result, errors = error_bundle.format_pattern("missing-var")
if errors:
    print("\n[WARN] Translation errors for 'missing-var':")
    for error in errors:
        print(f"  - {type(error).__name__}: {error}")
print(f"Result with fallback: {result}")

# Circular reference example
result, errors = error_bundle.format_pattern("circular-a")
if errors:
    print("\n[ERROR] Translation errors for 'circular-a':")
    for error in errors:
        print(f"  - {type(error).__name__}: {error}")
print(f"Result with fallback: {result}")

# Example 9: Factory Methods
print("\n" + "=" * 50)
print("Example 9: System Locale Detection")
print("=" * 50)

# for_system_locale() auto-detects system locale via locale.getlocale()
system_bundle = FluentBundle.for_system_locale(use_isolating=False)
system_bundle.add_resource("""
system-locale = Detected system locale: { $locale }
""")

result, _ = system_bundle.format_pattern("system-locale", {"locale": system_bundle.locale})
print(result)
# Output: Detected system locale: en_US (or your system locale)

# Example 10: Context Manager Support
print("\n" + "=" * 50)
print("Example 10: Context Manager Support")
print("=" * 50)

# Context manager clears format cache on exit but preserves messages/terms
# Bundle remains fully usable after exiting the with block
with FluentBundle("en", use_isolating=False, enable_cache=True) as ctx_bundle:
    ctx_bundle.add_resource("""
ctx-hello = Hello from context manager!
ctx-goodbye = Goodbye, { $name }!
""")

    result, _ = ctx_bundle.format_pattern("ctx-hello")
    print(result)
    # Output: Hello from context manager!

    result, _ = ctx_bundle.format_pattern("ctx-goodbye", {"name": "World"})
    print(result)
    # Output: Goodbye, World!

# Bundle remains usable after exiting - only cache is cleared
result, _ = ctx_bundle.format_pattern("ctx-hello")
print(f"After with block: {result}")
# Output: Hello from context manager!

print("[OK] Context manager exited cleanly (cache cleared, messages preserved)")

print("\n" + "=" * 50)
print("[SUCCESS] All examples completed successfully!")
print("=" * 50)
