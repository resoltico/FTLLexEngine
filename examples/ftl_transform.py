"""FTL Transformer Example - Demonstrating AST Modification API.

PARSER-ONLY: This example works WITHOUT Babel. Install with:
    pip install ftllexengine  (no [babel] extra needed)

This example shows how to use FTLLexEngine's ASTTransformer to modify
FTL files programmatically:

- Remove all comments (documentation cleanup)
- Rename variables (refactoring)
- Extract hardcoded strings to variables
- Remove deprecated messages by prefix

Leverages Python 3.13+ features:
- Pattern matching in ASTTransformer
- Type-safe AST node construction
- Immutable transformations (original unchanged)

Python 3.13+.
"""

from __future__ import annotations

from dataclasses import replace

from ftllexengine import parse_ftl, serialize_ftl
from ftllexengine.syntax.ast import (
    Comment,
    Identifier,
    Message,
    Placeable,
    Resource,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.visitor import ASTTransformer


class RemoveCommentsTransformer(ASTTransformer):
    """Remove all comments from FTL source."""

    def visit_Comment(self, _node: Comment) -> None:  # pylint: disable=invalid-name
        """Remove comments by returning None.

        Visitor pattern: visit_* methods follow stdlib ast.NodeVisitor convention.
        """
        return


class RenameVariablesTransformer(ASTTransformer):
    """Rename variables according to mapping."""

    def __init__(self, mapping: dict[str, str]) -> None:
        """Initialize with variable name mapping.

        Args:
            mapping: Dictionary of old_name -> new_name
        """
        super().__init__()
        self.mapping = mapping

    def visit_VariableReference(self, node: VariableReference) -> VariableReference:  # pylint: disable=invalid-name
        """Rename variable if in mapping.

        Visitor pattern: visit_* methods follow stdlib ast.NodeVisitor convention.
        """
        if node.id.name in self.mapping:
            # Create new node with renamed variable (immutable transformation)
            return replace(node, id=Identifier(name=self.mapping[node.id.name]))
        return node


class ExtractVariablesTransformer(ASTTransformer):
    """Extract hardcoded text into variables.

    This transformer detects TextElement nodes whose value exactly matches
    a target string and converts them to VariableReferences.
    """

    def __init__(self, text_to_var: dict[str, str]) -> None:
        """Initialize with text extraction rules.

        Args:
            text_to_var: Dictionary of exact_text -> variable_name
        """
        super().__init__()
        self.text_to_var = text_to_var

    def visit_TextElement(self, node: TextElement) -> TextElement | Placeable:  # pylint: disable=invalid-name
        """Convert matching text to variable reference.

        Visitor pattern: visit_* methods follow stdlib ast.NodeVisitor convention.
        Only exact matches are replaced to avoid corrupting surrounding text.
        """
        stripped = node.value.strip()
        for text, var_name in self.text_to_var.items():
            if stripped == text:
                return Placeable(
                    expression=VariableReference(id=Identifier(name=var_name))
                )
        return node


class RemoveDeprecatedMessagesTransformer(ASTTransformer):
    """Remove messages whose ID starts with a given prefix."""

    def __init__(self, prefix: str) -> None:
        """Initialize with prefix to match for removal.

        Args:
            prefix: Message IDs starting with this prefix are removed.
        """
        super().__init__()
        self.prefix = prefix

    def visit_Message(self, node: Message) -> Message | None:  # pylint: disable=invalid-name
        """Remove message if its ID starts with the deprecated prefix.

        Visitor pattern: visit_* methods follow stdlib ast.NodeVisitor convention.
        """
        if node.id.name.startswith(self.prefix):
            return None  # Remove this message
        return node


# Example usage
if __name__ == "__main__":
    # Example 1: Remove comments
    print("=" * 60)
    print("Example 1: Remove All Comments")
    print("=" * 60)

    # pylint: disable=invalid-name  # Example data strings - not module constants
    ftl_with_comments = """
# This is a resource comment
## Group comment
hello = Hello, World!
# This is a standalone comment
goodbye = Goodbye!
"""

    print("BEFORE:")
    print(ftl_with_comments)

    resource = parse_ftl(ftl_with_comments)
    transformer = RemoveCommentsTransformer()
    cleaned = transformer.transform(resource)
    # transform() returns ASTNode, assert it's a Resource
    assert isinstance(cleaned, Resource), f"Expected Resource, got {type(cleaned)}"

    print("\nAFTER:")
    print(serialize_ftl(cleaned))

    # Example 2: Rename variables
    print("\n" + "=" * 60)
    print("Example 2: Rename Variables")
    print("=" * 60)

    ftl_with_vars = """
greeting = Hello, { $userName }!
farewell = Goodbye, { $userName }!
"""

    print("BEFORE:")
    print(ftl_with_vars)

    resource = parse_ftl(ftl_with_vars)
    rename_transformer = RenameVariablesTransformer({"userName": "user_name"})
    renamed_resource = rename_transformer.transform(resource)
    assert isinstance(renamed_resource, Resource), f"Expected Resource, got {type(renamed_resource)}"

    print("\nAFTER:")
    print(serialize_ftl(renamed_resource))

    # Example 3: Extract hardcoded strings
    print("\n" + "=" * 60)
    print("Example 3: Extract Hardcoded Strings to Variables")
    print("=" * 60)

    ftl_hardcoded = """
app-title = Acme Corp
welcome = Hello from Acme Corp
"""

    print("BEFORE:")
    print(ftl_hardcoded)

    resource = parse_ftl(ftl_hardcoded)
    extract_transformer = ExtractVariablesTransformer({"Acme Corp": "company_name"})
    extracted_resource = extract_transformer.transform(resource)
    assert isinstance(extracted_resource, Resource), f"Expected Resource, got {type(extracted_resource)}"

    print("\nAFTER (exact match 'Acme Corp' → { $company_name }):")
    print(serialize_ftl(extracted_resource))

    # Example 4: Remove deprecated messages
    print("\n" + "=" * 60)
    print("Example 4: Remove Deprecated Messages")
    print("=" * 60)

    ftl_with_deprecated = """
hello = Hello!
deprecated-old-greeting = Hi there!
welcome = Welcome!
deprecated-legacy-farewell = See you!
"""

    print("BEFORE:")
    print(ftl_with_deprecated)

    resource = parse_ftl(ftl_with_deprecated)
    remove_deprecated = RemoveDeprecatedMessagesTransformer("deprecated-")
    filtered_resource = remove_deprecated.transform(resource)
    assert isinstance(filtered_resource, Resource), f"Expected Resource, got {type(filtered_resource)}"

    print("\nAFTER (messages with 'deprecated-' prefix removed):")
    print(serialize_ftl(filtered_resource))

    # Example 5: Chain multiple transformers
    print("\n" + "=" * 60)
    print("Example 5: Chain Multiple Transformations")
    print("=" * 60)

    complex_ftl = """
# Old variable naming convention
## Legacy code

user-greeting = Hello, { $userName }!
# Needs refactoring
admin-greeting = Hello, { $userName }!
"""

    print("BEFORE:")
    print(complex_ftl)

    # Apply transformations in sequence
    resource = parse_ftl(complex_ftl)

    # Step 1: Remove comments
    result = RemoveCommentsTransformer().transform(resource)
    assert isinstance(result, Resource), f"Expected Resource, got {type(result)}"
    resource = result

    # Step 2: Rename variables
    result = RenameVariablesTransformer({"userName": "user_name"}).transform(resource)
    assert isinstance(result, Resource), f"Expected Resource, got {type(result)}"
    resource = result

    print("\nAFTER (comments removed + variables renamed):")
    print(serialize_ftl(resource))

    # Example 6: Real-world use case - Modernize legacy FTL
    print("\n" + "=" * 60)
    print("Example 6: Modernize Legacy FTL (Real-World)")
    print("=" * 60)

    legacy_ftl = """
# Legacy FTL file from 2019
# Uses old variable naming (camelCase instead of snake_case)

welcomeMessage = Welcome, { $firstName }!
userProfile = { $firstName } { $lastName }
accountBalance = Balance: { NUMBER($currentBalance) }

# TODO: Refactor variable names
# TODO: Remove obsolete messages
"""

    print("BEFORE:")
    print(legacy_ftl)

    resource = parse_ftl(legacy_ftl)

    # Modern FTL: snake_case variables
    modernizer = RenameVariablesTransformer({
        "firstName": "first_name",
        "lastName": "last_name",
        "currentBalance": "current_balance",
    })

    modernized_resource = modernizer.transform(resource)
    assert isinstance(modernized_resource, Resource), f"Expected Resource, got {type(modernized_resource)}"

    # Remove comments for production
    comment_remover = RemoveCommentsTransformer()
    production_resource = comment_remover.transform(modernized_resource)
    assert isinstance(production_resource, Resource), f"Expected Resource, got {type(production_resource)}"

    print("\nAFTER (modernized + production-ready):")
    print(serialize_ftl(production_resource))

    print("\n" + "=" * 60)
    print("[SUCCESS] Transformer examples complete!")
    print("=" * 60)
