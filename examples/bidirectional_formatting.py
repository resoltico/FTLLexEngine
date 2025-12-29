"""Bi-Directional Localization Examples.

FTLLexEngine provides full bi-directional localization:
- Format: data -> display (FluentBundle + CURRENCY/NUMBER functions)
- Parse: display -> data (parsing module)

This enables locale-aware forms, invoices, and financial applications.

API Notes:
- Type guards (is_valid_decimal, is_valid_number) accept None for simplified patterns
- All parse functions return tuple[result, tuple[FluentParseError, ...]] (immutable)
- Functions never raise exceptions - errors returned in immutable tuple

Implementation:
- Number/currency parsing: Babel's parse_decimal() (CLDR-compliant)
- Date/datetime parsing: Python 3.13 stdlib (strptime, fromisoformat) with Babel CLDR patterns
- Zero external date libraries - pure Python 3.13 + Babel
- Thread-safe, fast ISO 8601 path, pattern fallback chains
"""

from decimal import Decimal

from ftllexengine import FluentBundle
from ftllexengine.parsing import (
    is_valid_decimal,
    parse_currency,
    parse_date,
    parse_decimal,
)


def example_invoice_processing() -> None:
    """Invoice processing with bi-directional localization."""
    print("[Example 1] Invoice Processing (Latvian Locale)")
    print("-" * 60)

    # Create bundle for Latvian locale
    bundle = FluentBundle("lv_LV", use_isolating=False)
    bundle.add_resource(
        """
subtotal = Summa: { CURRENCY($amount, currency: "EUR") }
vat = PVN (21%): { CURRENCY($vat, currency: "EUR") }
total = Kopa: { CURRENCY($total, currency: "EUR") }
"""
    )

    # Parse user input (subtotal)
    user_input = "1 234,56"
    print(f"User input (subtotal): {user_input}")

    # Type guards accept None - simplified pattern
    subtotal, _ = parse_decimal(user_input, "lv_LV")
    if not is_valid_decimal(subtotal):
        print("Failed to parse subtotal")
        return
    print(f"Parsed to Decimal: {subtotal}")

    # Calculate VAT (financial precision with Decimal)
    vat_rate = Decimal("0.21")
    vat = subtotal * vat_rate
    total = subtotal + vat

    print("\nCalculations (Decimal precision):")
    print(f"  VAT (21%): {vat}")
    print(f"  Total: {total}")

    # Format for display
    subtotal_display, _ = bundle.format_pattern("subtotal", {"amount": float(subtotal)})
    vat_display, _ = bundle.format_pattern("vat", {"vat": float(vat)})
    total_display, _ = bundle.format_pattern("total", {"total": float(total)})

    print("\nFormatted for display (Latvian):")
    print(f"  {subtotal_display}")
    print(f"  {vat_display}")
    print(f"  {total_display}")

    # Roundtrip validation
    print("\nRoundtrip validation:")
    parsed_back, errors = parse_decimal("1 234,56", "lv_LV")
    if not errors:
        print(f"  Original: {subtotal}")
        print(f"  Parsed back: {parsed_back}")
        print(f"  Match: {subtotal == parsed_back}")


def example_form_validation() -> None:
    """Form input validation with locale-aware parsing."""
    print("\n[Example 2] Form Validation (German Locale)")
    print("-" * 60)

    bundle = FluentBundle("de_DE", use_isolating=False)
    bundle.add_resource('price = Preis: { CURRENCY($amount, currency: "EUR") }')

    # Simulate user input in German format
    user_inputs = [
        "123,45",  # Valid
        "1.234,56",  # Valid (with thousand separator)
        "invalid",  # Invalid
        "",  # Empty
    ]

    for user_input in user_inputs:
        print(f"\nUser input: '{user_input}'")

        # Validate and parse
        if not user_input.strip():
            print("  Error: Amount is required")
            continue

        # Returns tuple (result, errors)
        amount, errors = parse_decimal(user_input, "de_DE")
        if errors:
            print(f"  Error: {errors[0]}")
            continue

        print(f"  Parsed: {amount}")

        # Range validation
        if amount is not None and amount <= 0:
            print("  Error: Amount must be positive")
            continue

        if amount is not None and amount > Decimal("1000000"):
            print("  Error: Amount exceeds maximum")
            continue

        # Format for display
        assert amount is not None, "Amount should not be None after error checks"
        formatted, _ = bundle.format_pattern("price", {"amount": float(amount)})
        print(f"  Display: {formatted}")
        print("  Status: Valid")


def example_currency_parsing() -> None:
    """Currency parsing with automatic symbol detection."""
    print("\n[Example 3] Currency Parsing (Multiple Locales)")
    print("-" * 60)

    test_cases = [
        ("EUR 123.45", "en_US"),
        ("1 234,56 EUR", "lv_LV"),
        ("1.234,56 EUR", "de_DE"),
        ("USD 1,234.56", "en_US"),
        ("GBP 99.99", "en_GB"),
        ("JPY 12,345", "ja_JP"),
    ]

    for user_input, locale in test_cases:
        print(f"\nInput: {user_input:15} | Locale: {locale}")

        # Returns tuple (result, errors)
        result, errors = parse_currency(user_input, locale)
        if errors:
            print(f"  Error: {errors[0]}")
            continue

        if result is not None:
            amount, currency = result
            print(f"  Amount: {amount:12} | Currency: {currency}")

            # Format back in same locale
            bundle = FluentBundle(locale, use_isolating=False)
            bundle.add_resource("formatted = { CURRENCY($amount, currency: $curr) }")

            # Create select expression for dynamic currency
            ftl_source = """
formatted = { $curr ->
    [EUR] { CURRENCY($amount, currency: "EUR") }
    [USD] { CURRENCY($amount, currency: "USD") }
    [GBP] { CURRENCY($amount, currency: "GBP") }
    [JPY] { CURRENCY($amount, currency: "JPY") }
   *[other] { $amount } { $curr }
}
"""
            bundle.add_resource(ftl_source)
            formatted, _ = bundle.format_pattern(
                "formatted", {"amount": float(amount), "curr": currency}
            )
            print(f"  Formatted: {formatted}")
        else:
            print("  Error: Could not parse currency")


def example_date_parsing() -> None:
    """Date parsing with locale-aware format detection."""
    print("\n[Example 4] Date Parsing (Locale-Specific Patterns)")
    print("-" * 60)

    # US format uses slashes: M/d/yy (2-digit year per CLDR)
    us_string = "1/2/25"
    us_date, errors = parse_date(us_string, "en_US")
    print(f"US input: {us_string}")
    if not errors:
        print(f"  Parsed (M/d/yy): {us_date}  # January 2, 2025")
    else:
        print(f"  US format error: {errors[0]}")

    # European format uses dots: dd.MM.yy (2-digit year per CLDR)
    eu_string = "02.01.25"
    eu_date, errors = parse_date(eu_string, "lv_LV")
    print(f"\nEU input: {eu_string}")
    if not errors:
        print(f"  Parsed (dd.MM.yy): {eu_date}  # January 2, 2025")
    else:
        print(f"  EU format error: {errors[0]}")

    # ISO 8601 (unambiguous, works for any locale)
    iso_string = "2025-01-02"
    iso_date, errors = parse_date(iso_string, "en_US")
    print(f"\nISO 8601: {iso_string}")
    if not errors:
        print(f"  Always unambiguous: {iso_date}  # January 2, 2025")
    else:
        print(f"  ISO format error: {errors[0]}")

    print("\nNote: CLDR patterns are locale-specific. Use ISO 8601 for interchange.")


def example_roundtrip_validation() -> None:
    """Roundtrip validation: format -> parse -> format."""
    print("\n[Example 5] Roundtrip Validation")
    print("-" * 60)

    locales = ["en_US", "lv_LV", "de_DE", "ja_JP"]
    original_value = Decimal("1234.56")

    print(f"Original value: {original_value}\n")

    for locale in locales:
        bundle = FluentBundle(locale, use_isolating=False)
        bundle.add_resource('price = { CURRENCY($amount, currency: "EUR") }')

        # Format -> Parse -> Format
        formatted1, _ = bundle.format_pattern("price", {"amount": float(original_value)})

        # Returns tuple (result, errors)
        result, errors = parse_currency(formatted1, locale)
        if errors:
            print(f"Locale: {locale} - Parse failed: {errors[0]}")
            continue

        if result is not None:
            parsed_amount, parsed_currency = result
            formatted2, _ = bundle.format_pattern("price", {"amount": float(parsed_amount)})

            print(f"Locale: {locale}")
            print(f"  Format 1:  {formatted1}")
            print(f"  Parsed:    {parsed_amount} {parsed_currency}")
            print(f"  Format 2:  {formatted2}")
            print(f"  Preserved: {parsed_amount == original_value}")
        else:
            print(f"Locale: {locale} - Parse failed")


def example_csv_import() -> None:
    """CSV data import with locale-aware parsing."""
    print("\n[Example 6] CSV Import (Latvian Locale)")
    print("-" * 60)

    # Simulated CSV data (Latvian format)
    csv_data = [
        ("2025-01-15", "Prece A", "123,45"),
        ("2025-01-16", "Prece B", "1 234,56"),
        ("2025-01-17", "Prece C", "invalid"),  # Error
    ]

    locale = "lv_LV"
    transactions = []
    import_errors = []

    print(f"Importing transactions (locale: {locale}):\n")

    for row_num, (date_str, description, amount_str) in enumerate(csv_data, start=2):
        print(f"Row {row_num}: {date_str} | {description} | {amount_str}")

        # Parse date (ISO format - unambiguous)
        # Returns tuple (result, errors)
        date_result, errors = parse_date(date_str, locale)
        if errors:
            error_msg = f"Row {row_num}: Invalid date '{date_str}'"
            import_errors.append(error_msg)
            print(f"  Error: {error_msg}")
            continue

        # Parse amount (Latvian format)
        # Returns tuple (result, errors)
        amount, errors = parse_decimal(amount_str, locale)
        if errors:
            error_msg = f"Row {row_num}: Invalid amount '{amount_str}'"
            import_errors.append(error_msg)
            print(f"  Error: {error_msg}")
            continue

        transactions.append({
            "date": date_result,
            "description": description,
            "amount": amount,
        })
        print(f"  Imported: {date_result} | {description} | {amount}")

    print("\nImport summary:")
    print(f"  Successful: {len(transactions)}")
    print(f"  Errors: {len(import_errors)}")


if __name__ == "__main__":
    print("=" * 60)
    print("Bi-Directional Localization Examples")
    print("FTLLexEngine Bi-Directional Localization")
    print("=" * 60)

    example_invoice_processing()
    example_form_validation()
    example_currency_parsing()
    example_date_parsing()
    example_roundtrip_validation()
    example_csv_import()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)
