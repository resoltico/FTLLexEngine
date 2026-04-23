"""Parser-Only Example - FTL Parsing In A Parser-Only Install.

PARSER-ONLY INSTALL: This example is designed for:
    pip install ftllexengine

Demonstrates everything you can do with FTLLexEngine's parser-only mode:

0. Access zero-dependency runtime/localization helper facades
1. Parse FTL source to AST
2. Inspect message structure
3. Extract variables and function references
4. Validate FTL syntax
5. Serialize AST back to FTL
6. Roundtrip validation

Use cases:
- Build tools (linters, formatters, extractors)
- IDE integrations (syntax highlighting, autocomplete)
- CI/CD pipelines (validation, migration)
- Documentation generators

Python 3.13+.
"""

from __future__ import annotations


def example_0_zero_dependency_facades() -> None:
    """Show helper facades that stay importable in parser-only installs."""
    from decimal import Decimal

    from ftllexengine import CacheConfig, FluentNumber, LoadSummary, PathResourceLoader

    print("=" * 60)
    print("Example 0: Zero-Dependency Helper Facades")
    print("=" * 60)

    cache = CacheConfig(size=10)
    manual = FluentNumber(value=Decimal("12.50"), formatted="12.50", precision=2)
    loader = PathResourceLoader("locales/{locale}")
    summary = LoadSummary(results=())

    print(f"CacheConfig.size: {cache.size}")
    print(f"FluentNumber: {manual!s}")
    print(f"PathResourceLoader template: {loader.base_path}")
    print(f"Empty LoadSummary all_clean: {summary.all_clean}")
    print()


def example_1_basic_parsing() -> None:
    """Parse FTL source and inspect the AST."""
    from ftllexengine import parse_ftl
    from ftllexengine.syntax.ast import Message, Term

    print("=" * 60)
    print("Example 1: Basic Parsing")
    print("=" * 60)

    ftl_source = """
# Welcome message for the application
welcome = Welcome to { -brand-name }!
    .tooltip = Click to learn more

# User greeting with variable
hello = Hello, { $name }!

# Pluralized item count
items = { $count ->
    [one] You have one item
   *[other] You have { $count } items
}

# Brand term
-brand-name = FTLLexEngine
"""

    resource = parse_ftl(ftl_source)

    print(f"Parsed {len(resource.entries)} entries:")
    for entry in resource.entries:
        match entry:
            case Message(id=identifier, attributes=attrs):
                attr_info = f" ({len(attrs)} attributes)" if attrs else ""
                print(f"  Message: {identifier.name}{attr_info}")
            case Term(id=identifier):
                print(f"  Term: -{identifier.name}")
            case _:
                print(f"  Other: {type(entry).__name__}")

    print()


def example_2_variable_extraction() -> None:
    """Extract variables and functions from messages."""
    from ftllexengine import parse_ftl
    from ftllexengine.introspection import introspect_message
    from ftllexengine.syntax.ast import Message

    print("=" * 60)
    print("Example 2: Variable and Function Extraction")
    print("=" * 60)

    ftl_source = """
order-summary = { $customer } ordered { CURRENCY($total, currency: "USD") }
    on { DATETIME($date, dateStyle: "long") }
"""

    resource = parse_ftl(ftl_source)
    message = resource.entries[0]
    assert isinstance(message, Message)

    info = introspect_message(message)

    print(f"Message ID: {info.message_id}")
    print(f"Variables: {info.get_variable_names()}")
    print(f"Functions: {info.get_function_names()}")
    print(f"Has selectors: {info.has_selectors}")
    print()


def example_3_validation() -> None:
    """Validate FTL source for errors and warnings."""
    from ftllexengine import validate_resource

    print("=" * 60)
    print("Example 3: Validation")
    print("=" * 60)

    # Valid FTL
    valid_ftl = """
greeting = Hello, { $name }!
-brand = MyApp
welcome = Welcome to { -brand }
"""

    result = validate_resource(valid_ftl)
    assert result.is_valid
    assert result.error_count == 0
    assert result.warning_count == 0
    print(f"Valid FTL: is_valid={result.is_valid}, errors={result.error_count}")

    # Warning-only FTL: semantic issues do not change is_valid
    warning_ftl = """
greeting = Hello, { $name }!
greeting = Duplicate ID!
missing-ref = Uses { -undefined-term }
"""

    result = validate_resource(warning_ftl)
    assert result.is_valid
    assert result.warning_count == 2
    print(f"Warning-only FTL: is_valid={result.is_valid}, warnings={result.warning_count}")
    for warning in result.warnings:
        print(f"  - {warning.code.name}: {warning.message}")
    print("[PASS] Warning-only validation semantics verified")

    # Invalid syntax FTL: parser annotations make the result invalid
    invalid_syntax_ftl = """
greeting = Hello, { $name !
"""

    result = validate_resource(invalid_syntax_ftl)
    assert not result.is_valid
    assert result.error_count > 0 or result.annotation_count > 0
    print(f"Invalid syntax FTL: is_valid={result.is_valid}, errors={result.error_count}")
    print("[PASS] Invalid syntax semantics verified")

    print()


def example_4_serialization() -> None:
    """Serialize AST back to FTL source."""
    from ftllexengine import parse_ftl, serialize_ftl

    print("=" * 60)
    print("Example 4: Serialization (Roundtrip)")
    print("=" * 60)

    original = """
hello = Hello, World!
greeting = Welcome, { $name }!
"""

    # Parse to AST
    resource = parse_ftl(original)
    print(f"Parsed {len(resource.entries)} messages")

    # Serialize back to FTL
    serialized = serialize_ftl(resource)
    print("Serialized output:")
    print(serialized)

    # Roundtrip validation
    reparsed = parse_ftl(serialized)
    print(f"Roundtrip: {len(reparsed.entries)} messages (same as original)")
    print()


def example_5_ast_inspection() -> None:
    """Deep AST inspection for tooling."""
    from ftllexengine import parse_ftl
    from ftllexengine.syntax.ast import (
        Message,
        Placeable,
        SelectExpression,
        TextElement,
        VariableReference,
    )

    print("=" * 60)
    print("Example 5: Deep AST Inspection")
    print("=" * 60)

    ftl_source = """
items = { $count ->
    [one] One item
   *[other] { $count } items
}
"""

    resource = parse_ftl(ftl_source)
    message = resource.entries[0]
    assert isinstance(message, Message)

    print(f"Message: {message.id.name}")

    if message.value:
        for element in message.value.elements:
            match element:
                case TextElement(value=text):
                    print(f"  TextElement: {text!r}")
                case Placeable(expression=expr):
                    match expr:
                        case SelectExpression(variants=variants):
                            print(f"  SelectExpression with {len(variants)} variants")
                            for variant in variants:
                                default = " (default)" if variant.default else ""
                                print(f"    [{variant.key}]{default}")
                        case VariableReference(id=var_id):
                            print(f"  VariableReference: ${var_id.name}")
                        case _:
                            print(f"  Placeable: {type(expr).__name__}")

    print()


def example_6_visitor_pattern() -> None:
    """Use visitor pattern for AST traversal."""
    from ftllexengine import parse_ftl
    from ftllexengine.syntax.ast import (
        FunctionReference,
        TermReference,
        VariableReference,
    )
    from ftllexengine.syntax.visitor import ASTVisitor

    print("=" * 60)
    print("Example 6: Visitor Pattern")
    print("=" * 60)

    class ReferenceCollector(ASTVisitor):
        """Collect all references in an FTL resource."""

        def __init__(self) -> None:
            super().__init__()
            self.variables: set[str] = set()
            self.terms: set[str] = set()
            self.functions: set[str] = set()

        def visit_VariableReference(self, node: VariableReference) -> None:
            self.variables.add(node.id.name)
            self.generic_visit(node)

        def visit_TermReference(self, node: TermReference) -> None:
            self.terms.add(node.id.name)
            self.generic_visit(node)

        def visit_FunctionReference(self, node: FunctionReference) -> None:
            self.functions.add(node.id.name)
            self.generic_visit(node)

    ftl_source = """
welcome = Welcome, { $user }!
order = { CURRENCY($total, currency: "EUR") } for { -brand }
date = { DATETIME($when, dateStyle: "short") }
"""

    resource = parse_ftl(ftl_source)
    collector = ReferenceCollector()
    collector.visit(resource)

    print(f"Variables found: {collector.variables}")
    print(f"Terms found: {collector.terms}")
    print(f"Functions found: {collector.functions}")
    print()


def main() -> None:
    """Run all parser-only examples."""
    print()
    print("FTLLexEngine Parser-Only Examples")
    print("Parser-only install surface - pure Python parsing!")
    print()

    example_0_zero_dependency_facades()
    example_1_basic_parsing()
    example_2_variable_extraction()
    example_3_validation()
    example_4_serialization()
    example_5_ast_inspection()
    example_6_visitor_pattern()

    print("=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
