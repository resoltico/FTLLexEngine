"""Function Introspection Example - Demonstrating FunctionRegistry Introspection API.

This example demonstrates:
1. Listing all registered functions
2. Checking if functions exist before use
3. Getting function metadata (parameter mappings, Python names)
4. Iterating over registered functions
5. Generating function documentation automatically
6. Validating required functions are present

Use Cases:
- Auto-generating function reference documentation
- Debugging function registration issues
- Validating function presence before using in FTL
- Building IDE auto-complete for FTL functions

WARNING: Examples use use_isolating=False for cleaner terminal output.
NEVER disable bidi isolation in production applications that support RTL languages.

Python 3.13+.
"""

from __future__ import annotations

from ftllexengine import FluentBundle


def demonstrate_basic_introspection() -> None:
    """Demonstrate basic introspection operations."""
    print("=" * 70)
    print("Example 1: Basic Introspection")
    print("=" * 70)

    bundle = FluentBundle("en_US", use_isolating=False)

    # Access the function registry
    registry = bundle.function_registry

    print("\n[OPERATION] List all registered functions")
    functions = registry.list_functions()
    print(f"Registered functions: {functions}")
    print(f"Total count: {len(registry)}")
    # Output: Registered functions: ['NUMBER', 'DATETIME', 'CURRENCY']
    # Output: Total count: 3

    print("\n[OPERATION] Check if function exists")
    print(f"NUMBER exists: {'NUMBER' in registry}")
    print(f"CUSTOM exists: {'CUSTOM' in registry}")
    # Output: NUMBER exists: True
    # Output: CUSTOM exists: False

    print("\n[OPERATION] Iterate over functions")
    for func_name in registry:
        print(f"  - {func_name}")
    # Output:
    #   - NUMBER
    #   - DATETIME
    #   - CURRENCY


def demonstrate_function_metadata() -> None:
    """Demonstrate getting function metadata."""
    print("\n" + "=" * 70)
    print("Example 2: Function Metadata Inspection")
    print("=" * 70)

    bundle = FluentBundle("en_US", use_isolating=False)
    registry = bundle.function_registry

    print("\n[OPERATION] Get NUMBER function metadata")
    info = registry.get_function_info("NUMBER")

    if info:
        print(f"FTL name: {info.ftl_name}")
        print(f"Python name: {info.python_name}")
        print(f"Callable: {callable(info.callable)}")
        print("\nParameter mappings (FTL camelCase → Python snake_case):")
        # param_mapping is immutable tuple[tuple[str, str], ...] - already sorted
        for ftl_param, python_param in info.param_mapping:
            print(f"  {ftl_param:25s} → {python_param}")
    # Output:
    # FTL name: NUMBER
    # Python name: number_format
    # Callable: True
    #
    # Parameter mappings (FTL camelCase → Python snake_case):
    #   localeCode               → locale_code
    #   maximumFractionDigits    → maximum_fraction_digits
    #   minimumFractionDigits    → minimum_fraction_digits
    #   useGrouping              → use_grouping
    #   value                    → value


def demonstrate_custom_function_introspection() -> None:
    """Demonstrate introspection with custom functions."""
    print("\n" + "=" * 70)
    print("Example 3: Custom Function Introspection")
    print("=" * 70)

    bundle = FluentBundle("en_US", use_isolating=False)

    # Register custom functions
    def VAT_CALCULATION(amount: float, *, vat_rate: float = 0.21) -> str:  # pylint: disable=invalid-name
        """Calculate VAT for Latvian/EU invoices."""
        vat = amount * vat_rate
        return f"{vat:.2f}"

    def FORMAT_PERCENTAGE(value: float, *, decimal_places: int = 1) -> str:  # pylint: disable=invalid-name
        """Format value as percentage."""
        return f"{value:.{decimal_places}f}%"

    bundle.add_function("VAT_CALCULATION", VAT_CALCULATION)
    bundle.add_function("FORMAT_PERCENTAGE", FORMAT_PERCENTAGE)

    registry = bundle.function_registry

    print("\n[OPERATION] List all functions (built-in + custom)")
    print(f"Total functions: {len(registry)}")
    for func_name in sorted(registry):
        info = registry.get_function_info(func_name)
        if info:
            print(f"  {func_name:20s} → {info.python_name}")
    # Output:
    # Total functions: 5
    #   CURRENCY             → currency_format
    #   DATETIME             → datetime_format
    #   FORMAT_PERCENTAGE    → FORMAT_PERCENTAGE
    #   NUMBER               → number_format
    #   VAT_CALCULATION      → VAT_CALCULATION

    print("\n[OPERATION] Inspect custom function parameters")
    info = registry.get_function_info("VAT_CALCULATION")
    if info:
        print(f"\nFunction: {info.ftl_name}")
        print("Parameter mappings:")
        # param_mapping is immutable tuple[tuple[str, str], ...] - already sorted
        for ftl_param, python_param in info.param_mapping:
            print(f"  {ftl_param:15s} → {python_param}")
    # Output:
    # Function: VAT_CALCULATION
    # Parameter mappings:
    #   amount          → amount
    #   vatRate         → vat_rate


def demonstrate_validation_workflow() -> None:
    """Demonstrate validation workflow for financial applications."""
    print("\n" + "=" * 70)
    print("Example 4: Financial App Validation Workflow")
    print("=" * 70)

    bundle = FluentBundle("lv_LV", use_isolating=False)
    registry = bundle.function_registry

    print("\n[VALIDATION] Ensure required financial functions are present")

    required_functions = {
        "NUMBER": "Format numbers with locale-specific separators",
        "CURRENCY": "Format monetary amounts",
    }

    print("\nRequired functions for financial app:")
    all_present = True
    for func_name, description in required_functions.items():
        present = func_name in registry
        status = "[OK]" if present else "[MISSING]"
        print(f"  {status} {func_name:15s} - {description}")
        if not present:
            all_present = False

    if all_present:
        print("\n[SUCCESS] All required functions are available!")
    else:
        print("\n[ERROR] Missing required functions!")
    # Output:
    #   [OK] NUMBER          - Format numbers with locale-specific separators
    #   [OK] CURRENCY        - Format monetary amounts
    #
    # [SUCCESS] All required functions are available!


def demonstrate_auto_documentation() -> None:
    """Demonstrate automatic documentation generation."""
    print("\n" + "=" * 70)
    print("Example 5: Auto-Generate Function Documentation")
    print("=" * 70)

    bundle = FluentBundle("en_US", use_isolating=False)

    # Add custom function
    def IBAN_FORMAT(iban: str, *, format_style: str = "grouped") -> str:  # pylint: disable=invalid-name
        """Format IBAN for display."""
        if format_style == "grouped" and len(iban) >= 4:
            # Group in blocks of 4
            return " ".join(iban[i:i+4] for i in range(0, len(iban), 4))
        return iban

    bundle.add_function("IBAN_FORMAT", IBAN_FORMAT)

    registry = bundle.function_registry

    print("\n[DOCUMENTATION] Function Reference (Auto-Generated)")
    print("-" * 70)

    for func_name in sorted(registry):
        info = registry.get_function_info(func_name)
        if not info:
            continue

        print(f"\nFunction: {info.ftl_name}()")
        print(f"Python implementation: {info.python_name}()")

        if info.param_mapping:
            print("Parameters (FTL → Python):")
            # param_mapping is immutable tuple[tuple[str, str], ...] - already sorted
            for ftl_param, python_param in info.param_mapping:
                print(f"  - {ftl_param} → {python_param}")
        else:
            print("Parameters: None")

        print("\nUsage in FTL:")
        # Generate sample FTL usage
        if info.ftl_name == "NUMBER":
            print(f"  price = {{ {info.ftl_name}($amount, minimumFractionDigits: 2) }}")
        elif info.ftl_name == "CURRENCY":
            print(f'  price = {{ {info.ftl_name}($amount, currency: "EUR") }}')
        elif info.ftl_name == "IBAN_FORMAT":
            print(f'  account = {{ {info.ftl_name}($iban, formatStyle: "grouped") }}')
        else:
            print(f"  result = {{ {info.ftl_name}($value) }}")
    # Output: Auto-generated reference documentation for all functions


def demonstrate_safe_function_use() -> None:
    """Demonstrate safe function usage with existence check."""
    print("\n" + "=" * 70)
    print("Example 6: Safe Function Usage Pattern")
    print("=" * 70)

    bundle = FluentBundle("en_US", use_isolating=False)
    registry = bundle.function_registry

    print("\n[PATTERN] Check function exists before using in FTL")

    # Check if CURRENCY function exists before using
    if "CURRENCY" in registry:
        print("[OK] CURRENCY function available, safe to use")
        bundle.add_resource('price = { CURRENCY($amount, currency: "USD") }')
        result, errors = bundle.format_pattern("price", {"amount": 123.45})
        if not errors:
            print(f"Result: {result}")
        else:
            for error in errors:
                diag = error.diagnostic
                print(f"Error: {diag.message if diag else error.message}")
    else:
        print("[ERROR] CURRENCY function not available!")
        print("Fallback: using plain number formatting")
        bundle.add_resource("price = ${$amount}")

    # Output:
    # [OK] CURRENCY function available, safe to use
    # Result: $123.45


def demonstrate_registry_copy() -> None:
    """Demonstrate registry creation and copying for isolation."""
    print("\n" + "=" * 70)
    print("Example 7: Registry Creation and Copying for Isolation")
    print("=" * 70)

    # Create registry with built-in functions using factory
    from ftllexengine.runtime.functions import create_default_registry

    # Each call creates a fresh, isolated registry
    original_registry = create_default_registry()

    print(f"\n[ORIGINAL] Original registry has {len(original_registry)} functions")
    print(f"Functions: {original_registry.list_functions()}")

    # Copy registry for further customization
    print("\n[OPERATION] Creating copy for customization")
    custom_registry = original_registry.copy()

    # Add custom function to copy only
    def CUSTOM(value: str) -> str:  # pylint: disable=invalid-name
        return value.upper()

    custom_registry.register(CUSTOM, ftl_name="CUSTOM")

    print(f"\n[CUSTOM] Custom registry has {len(custom_registry)} functions")
    print(f"Functions: {custom_registry.list_functions()}")

    print(f"\n[VERIFICATION] Original registry still has {len(original_registry)} functions")
    print(f"Functions: {original_registry.list_functions()}")
    print(f"CUSTOM in original: {'CUSTOM' in original_registry}")
    print(f"CUSTOM in copy: {'CUSTOM' in custom_registry}")

    # Demonstrate using custom registry with FluentBundle
    print("\n[BUNDLE] Using custom registry with FluentBundle")
    bundle = FluentBundle("en_US", use_isolating=False, functions=custom_registry)
    bundle.add_resource("greeting = { CUSTOM($name) }")
    result, errors = bundle.format_pattern("greeting", {"name": "world"})
    if not errors:
        print(f"Result: {result}")
    # Output:
    # [ORIGINAL] Original registry has 3 functions
    # Functions: ['NUMBER', 'DATETIME', 'CURRENCY']
    #
    # [CUSTOM] Custom registry has 4 functions
    # Functions: ['NUMBER', 'DATETIME', 'CURRENCY', 'CUSTOM']
    #
    # [VERIFICATION] Original registry still has 3 functions
    # Functions: ['NUMBER', 'DATETIME', 'CURRENCY']
    # CUSTOM in original: False
    # CUSTOM in copy: True
    #
    # [BUNDLE] Using custom registry with FluentBundle
    # Result: WORLD


# Main execution
if __name__ == "__main__":
    print("\n")
    print("#" * 70)
    print("# FTLLexEngine Function Introspection API Examples")
    print("#" * 70)

    demonstrate_basic_introspection()
    demonstrate_function_metadata()
    demonstrate_custom_function_introspection()
    demonstrate_validation_workflow()
    demonstrate_auto_documentation()
    demonstrate_safe_function_use()
    demonstrate_registry_copy()

    print("\n" + "=" * 70)
    print("[SUCCESS] All introspection examples completed!")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("  1. Use list_functions() to discover available functions")
    print("  2. Use 'in' operator to check function existence")
    print("  3. Use get_function_info() for parameter mappings")
    print("  4. Use len() to count registered functions")
    print("  5. Iterate over registry to process all functions")
    print("  6. Use copy() for isolated customization")
    print("\nAPI Reference: https://github.com/resoltico/ftllexengine")
    print("=" * 70)
    print()
