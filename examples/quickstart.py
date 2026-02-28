"""Quickstart example for ftllexengine.

This example demonstrates basic usage of ftllexengine for localization.

WARNING: Examples use use_isolating=False for cleaner terminal output.
NEVER disable bidi isolation in production applications that support RTL languages.
Always use the default use_isolating=True for production code.

Note: Examples ignore the 'errors' return value for brevity. In production,
always check errors and log/report translation issues.
"""

import tempfile
from decimal import Decimal
from pathlib import Path

from ftllexengine import CacheConfig, FluentBundle, validate_resource
from ftllexengine.integrity import FormattingIntegrityError

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

result, _ = bundle.format_pattern("price", {"amount": Decimal("19.5")})
print(result)
# Output: Price: 19.50 EUR

result, _ = bundle.format_pattern("price", {"amount": 100})
print(result)
# Output: Price: 100.00 EUR

result, _ = bundle.format_pattern("discount", {"percent": Decimal("15.75")})
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

# strict=False: soft error recovery mode - format_pattern returns (fallback, errors)
# instead of raising FormattingIntegrityError. Required here to demonstrate
# error inspection via the returned errors tuple.
error_bundle = FluentBundle("en", use_isolating=False, strict=False)
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
        if error.diagnostic:
            print(f"  {error.diagnostic.format_error()}")
        else:
            print(f"  {error.category.name}: {error.message}")
else:
    print(f"[OK] {result}")

# Missing variable example
result, errors = error_bundle.format_pattern("missing-var")
if errors:
    print("\n[WARN] Translation errors for 'missing-var':")
    for error in errors:
        if error.diagnostic:
            print(f"  {error.diagnostic.format_error()}")
        else:
            print(f"  {error.category.name}: {error.message}")
print(f"Result with fallback: {result}")

# Circular reference example
result, errors = error_bundle.format_pattern("circular-a")
if errors:
    print("\n[ERROR] Translation errors for 'circular-a':")
    for error in errors:
        if error.diagnostic:
            print(f"  {error.diagnostic.format_error()}")
        else:
            print(f"  {error.category.name}: {error.message}")
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

# Example 10: Strict Mode (Fail-Fast) - the default
print("\n" + "=" * 50)
print("Example 10: Strict Mode (Fail-Fast)")
print("=" * 50)

# strict=True is the DEFAULT. ANY formatting error raises FormattingIntegrityError
# instead of returning a fallback string. Use strict=False only when soft error
# recovery (returning fallback + errors tuple) is explicitly needed.

strict_bundle = FluentBundle("en", use_isolating=False)  # strict=True is the default
strict_bundle.add_resource("""
amount = Total: { $value }
""")

# Successful formatting works normally
result, errors = strict_bundle.format_pattern("amount", {"value": "1,234.56"})
print(f"[OK] Formatted: {result}")

# Missing variable in strict mode raises exception
try:
    strict_bundle.format_pattern("amount", {})  # Missing $value
except FormattingIntegrityError as e:
    print(f"[FAIL-FAST] {e.message_id}: {len(e.fluent_errors)} error(s)")
    print(f"  Fallback would have been: {e.fallback_value!r}")

# Example 11: Resource Introspection
print("\n" + "=" * 50)
print("Example 11: Resource Introspection")
print("=" * 50)

# FluentBundle provides introspection APIs for auditing and validation
intr_bundle = FluentBundle("en", use_isolating=False)
intr_bundle.add_resource("""
greeting = Hello, { $name }!
farewell = Goodbye, { $name }!
-app-name = MyApp
""")

# Enumerate all message IDs (terms starting with - are excluded)
message_ids = intr_bundle.get_message_ids()
print(f"Message IDs: {sorted(message_ids)}")
# Output: ['farewell', 'greeting']

# Check if specific messages exist
print(f"has greeting: {intr_bundle.has_message('greeting')}")
print(f"has missing: {intr_bundle.has_message('missing')}")

# Validate FTL source before loading into a bundle
valid_result = validate_resource("valid = Hello, { $name }!\n")
print(f"Valid FTL: {valid_result.is_valid}")

invalid_result = validate_resource("broken = { }")  # Empty placeable
print(f"Invalid FTL: {invalid_result.is_valid}, errors: {len(invalid_result.errors)}")

print("[OK] Resource introspection APIs working")

# Example 12: Cache Security Parameters (Financial-Grade)
print("\n" + "=" * 50)
print("Example 12: Cache Security Parameters")
print("=" * 50)

# Financial applications can use cache security features:
# - write_once: Prevents cache overwrites (data race prevention)
# - integrity_strict: Raise on cache corruption/write conflicts
# - enable_audit: Maintains audit trail of cache operations
# - strict (bundle): Raises exceptions on formatting errors

financial_bundle = FluentBundle(
    "en",
    use_isolating=False,
    cache=CacheConfig(
        write_once=True,            # Prevent data races
        integrity_strict=True,      # Raise on corruption (default)
        enable_audit=True,          # Compliance audit trail
        max_entry_weight=5000,      # Memory protection
        max_errors_per_entry=10,    # Error bloat protection
    ),
    strict=True,                    # Fail-fast on ANY formatting error
)

financial_bundle.add_resource("""
balance = Account balance: { NUMBER($amount, minimumFractionDigits: 2) } USD
transaction = { $type } of { NUMBER($amount, minimumFractionDigits: 2) } on { $date }
""")

# Format with financial values
result, _ = financial_bundle.format_pattern("balance", {"amount": Decimal("12345.67")})
print(f"[FINANCIAL] {result}")

result, _ = financial_bundle.format_pattern("transaction", {
    "type": "Deposit",
    "amount": Decimal("500.00"),
    "date": "2026-01-21",
})
print(f"[FINANCIAL] {result}")

# Check cache configuration
print("\nCache security settings:")
cfg = financial_bundle.cache_config
if cfg is not None:
    print(f"  write_once: {cfg.write_once}")
    print(f"  integrity_strict: {cfg.integrity_strict}")
    print(f"  audit_enabled: {cfg.enable_audit}")
    print(f"  max_entry_weight: {cfg.max_entry_weight}")
    print(f"  max_errors_per_entry: {cfg.max_errors_per_entry}")

# Get cache stats including audit entries
stats = financial_bundle.get_cache_stats()
if stats:
    print(f"  audit_entries: {stats.get('audit_entries', 0)}")
    print(f"  cache_hits: {stats.get('hits', 0)}")
    print(f"  cache_misses: {stats.get('misses', 0)}")

print("\n" + "=" * 50)
print("[SUCCESS] All examples completed successfully!")
print("=" * 50)
