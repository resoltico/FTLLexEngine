"""Tests for AST Parser Tooling API.

Validates the public AST parser API for tooling ecosystem:
- parse_ftl() and serialize_ftl() functions
- ASTVisitor for read-only traversal
- ASTTransformer for in-place modifications
- AST node types exported in public API

Tests leverage Python 3.13+ features.
"""

from __future__ import annotations

from dataclasses import replace

from ftllexengine import parse_ftl, serialize_ftl
from ftllexengine.syntax import (
    ASTTransformer,
    ASTVisitor,
    Comment,
    Identifier,
    Message,
    Resource,
    VariableReference,
)


class TestParseFTLFunction:
    """Test parse_ftl() public API function."""

    def test_parse_ftl_simple_message(self) -> None:
        """Parse simple message using parse_ftl()."""
        resource = parse_ftl("hello = Hello, World!")

        assert isinstance(resource, Resource)
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)
        assert resource.entries[0].id.name == "hello"

    def test_parse_ftl_multiple_messages(self) -> None:
        """Parse multiple messages."""
        ftl = """
hello = Hello!
goodbye = Goodbye!
"""
        resource = parse_ftl(ftl)

        assert len(resource.entries) == 2
        assert isinstance(resource.entries[0], Message)
        assert isinstance(resource.entries[1], Message)
        assert resource.entries[0].id.name == "hello"
        assert resource.entries[1].id.name == "goodbye"

    def test_parse_ftl_with_variables(self) -> None:
        """Parse message with variables."""
        resource = parse_ftl("greeting = Hello, { $name }!")

        message = resource.entries[0]
        assert isinstance(message, Message)
        assert message.value is not None

    def test_parse_ftl_with_comments(self) -> None:
        """Parse FTL with comments attached to message per Fluent spec."""
        ftl = """
# Resource comment
hello = Hello!
"""
        resource = parse_ftl(ftl)

        # Per Fluent spec: Single-hash comment preceding message (no blank line)
        # is attached to the message's comment field
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)
        # Comment attached to message
        assert resource.entries[0].comment is not None
        assert resource.entries[0].comment.content == "Resource comment"


class TestSerializeFTLFunction:
    """Test serialize_ftl() public API function."""

    def test_serialize_ftl_simple_message(self) -> None:
        """Serialize simple message."""
        resource = parse_ftl("hello = Hello, World!")
        serialized = serialize_ftl(resource)

        assert "hello = Hello, World!" in serialized

    def test_serialize_ftl_roundtrip(self) -> None:
        """Parse → serialize → parse should be idempotent."""
        original = "hello = Hello, World!\ngoodbye = Goodbye!"

        # First roundtrip
        resource1 = parse_ftl(original)
        serialized1 = serialize_ftl(resource1)

        # Second roundtrip
        resource2 = parse_ftl(serialized1)
        serialized2 = serialize_ftl(resource2)

        # Should be stable
        assert serialized1 == serialized2


class TestASTVisitorPattern:
    """Test ASTVisitor for read-only AST traversal."""

    def test_visitor_counts_messages(self) -> None:
        """Visitor can count messages."""
        class CountMessagesVisitor(ASTVisitor):
            def __init__(self) -> None:
                super().__init__()
                self.count = 0

            def visit_Message(self, node: Message) -> None:
                self.count += 1
                self.generic_visit(node)

        ftl = """
hello = Hello!
goodbye = Goodbye!
welcome = Welcome!
"""
        resource = parse_ftl(ftl)
        visitor = CountMessagesVisitor()
        visitor.visit(resource)

        assert visitor.count == 3

    def test_visitor_collects_message_ids(self) -> None:
        """Visitor can collect all message IDs."""
        class CollectIDsVisitor(ASTVisitor):
            def __init__(self) -> None:
                super().__init__()
                self.ids: list[str] = []

            def visit_Message(self, node: Message) -> None:
                self.ids.append(node.id.name)
                self.generic_visit(node)

        ftl = """
first = First
second = Second
third = Third
"""
        resource = parse_ftl(ftl)
        visitor = CollectIDsVisitor()
        visitor.visit(resource)

        assert visitor.ids == ["first", "second", "third"]

    def test_visitor_finds_variables(self) -> None:
        """Visitor can find all variable references."""
        class FindVariablesVisitor(ASTVisitor):
            def __init__(self) -> None:
                super().__init__()
                self.variables: set[str] = set()

            def visit_VariableReference(self, node: VariableReference) -> None:
                self.variables.add(node.id.name)
                self.generic_visit(node)

        ftl = """
greeting = Hello, { $name }!
profile = { $firstName } { $lastName }
"""
        resource = parse_ftl(ftl)
        visitor = FindVariablesVisitor()
        visitor.visit(resource)

        assert visitor.variables == {"name", "firstName", "lastName"}


class TestASTTransformerPattern:
    """Test ASTTransformer for AST modifications."""

    def test_transformer_removes_comments(self) -> None:
        """Transformer can remove group comments (top-level entries)."""
        class RemoveCommentsTransformer(ASTTransformer):
            def visit_Comment(self, node: Comment) -> None:
                return None  # Remove comments

        # Use group comments (##) which remain as top-level entries
        # Single-hash comments (#) are attached to following message per Fluent spec
        ftl = """
## Group comment 1
hello = Hello!

## Group comment 2
goodbye = Goodbye!
"""
        resource = parse_ftl(ftl)
        original_count = len(resource.entries)

        transformer = RemoveCommentsTransformer()
        cleaned = transformer.transform(resource)
        assert isinstance(cleaned, Resource), f"Expected Resource, got {type(cleaned)}"

        # Should have fewer entries (group comments removed)
        assert len(cleaned.entries) < original_count
        # All entries should be messages, not comments
        for entry in cleaned.entries:
            assert isinstance(entry, Message)

    def test_transformer_renames_variables(self) -> None:
        """Transformer can rename variables."""
        class RenameVariablesTransformer(ASTTransformer):
            def __init__(self, mapping: dict[str, str]) -> None:
                super().__init__()
                self.mapping = mapping

            def visit_VariableReference(self, node: VariableReference) -> VariableReference:
                if node.id.name in self.mapping:
                    return replace(node, id=Identifier(name=self.mapping[node.id.name]))
                return node

        ftl = "greeting = Hello, { $userName }!"
        resource = parse_ftl(ftl)

        transformer = RenameVariablesTransformer({"userName": "user_name"})
        renamed = transformer.transform(resource)
        assert isinstance(renamed, Resource), f"Expected Resource, got {type(renamed)}"

        serialized = serialize_ftl(renamed)
        assert "user_name" in serialized
        assert "userName" not in serialized

    def test_transformer_removes_empty_messages(self) -> None:
        """Transformer can remove messages without values."""
        class RemoveEmptyTransformer(ASTTransformer):
            def visit_Message(self, node: Message) -> Message | None:
                if not node.value and not node.attributes:
                    return None  # Remove empty message
                return node

        ftl = """
hello = Hello!
empty =
goodbye = Goodbye!
"""
        resource = parse_ftl(ftl)

        transformer = RemoveEmptyTransformer()
        filtered = transformer.transform(resource)
        assert isinstance(filtered, Resource), f"Expected Resource, got {type(filtered)}"

        # Should only have 2 messages (empty removed)
        messages = [e for e in filtered.entries if isinstance(e, Message)]
        assert len(messages) == 2
        assert messages[0].id.name == "hello"
        assert messages[1].id.name == "goodbye"

    def test_transformer_preserves_original(self) -> None:
        """Transformer does not modify original AST."""
        class ModifyTransformer(ASTTransformer):
            def visit_Comment(self, node: Comment) -> None:
                return None

        ftl = "# Comment\nhello = Hello!"
        resource = parse_ftl(ftl)
        original_count = len(resource.entries)

        transformer = ModifyTransformer()
        _modified = transformer.transform(resource)

        # Original should be unchanged
        assert len(resource.entries) == original_count


class TestASTNodeTypesExported:
    """Test that AST node types are accessible from public API."""

    def test_message_type_accessible(self) -> None:
        """Message type is accessible from ftllexengine.syntax."""
        # Already imported at module level
        assert Message is not None

    def test_resource_type_accessible(self) -> None:
        """Resource type is accessible."""
        # Already imported at module level
        assert Resource is not None

    def test_variable_reference_accessible(self) -> None:
        """VariableReference type is accessible."""
        # Already imported at module level
        assert VariableReference is not None

    def test_ast_visitor_accessible(self) -> None:
        """ASTVisitor is accessible."""
        # Already imported at module level
        assert ASTVisitor is not None

    def test_ast_transformer_accessible(self) -> None:
        """ASTTransformer is accessible."""
        # Already imported at module level
        assert ASTTransformer is not None


class TestToolingIntegration:
    """Test complete tooling workflows."""

    def test_linter_workflow(self) -> None:
        """Simulate FTL linter workflow."""
        # Step 1: Parse FTL
        ftl = """
hello = Hello, { $name }!
goodbye = Goodbye, { $unknown_var }!
"""
        resource = parse_ftl(ftl)

        # Step 2: Create visitor to find undefined variables
        class FindUnknownVarsVisitor(ASTVisitor):
            def __init__(self) -> None:
                super().__init__()
                self.undefined_vars: list[str] = []

            def visit_VariableReference(self, node: VariableReference) -> None:
                # In real linter, check against declared vars
                if "unknown" in node.id.name:
                    self.undefined_vars.append(node.id.name)
                self.generic_visit(node)

        visitor = FindUnknownVarsVisitor()
        visitor.visit(resource)

        assert "unknown_var" in visitor.undefined_vars

    def test_formatter_workflow(self) -> None:
        """Simulate FTL formatter workflow."""
        # Step 1: Parse messy FTL
        messy_ftl = "# Comment\nhello=Hello!"

        resource = parse_ftl(messy_ftl)

        # Step 2: Serialize with standard formatting
        formatted = serialize_ftl(resource)

        # Step 3: Verify formatting
        assert "hello = Hello!" in formatted

    def test_refactoring_workflow(self) -> None:
        """Simulate FTL refactoring workflow."""
        # Step 1: Parse legacy FTL
        legacy = "greeting = Hello, { $userName }!"

        resource = parse_ftl(legacy)

        # Step 2: Rename variables (modernize)
        class ModernizeTransformer(ASTTransformer):
            def visit_VariableReference(self, node: VariableReference) -> VariableReference:
                if node.id.name == "userName":
                    return replace(node, id=Identifier(name="user_name"))
                return node

        transformer = ModernizeTransformer()
        modernized = transformer.transform(resource)
        assert isinstance(modernized, Resource), f"Expected Resource, got {type(modernized)}"

        # Step 3: Serialize modernized FTL
        result = serialize_ftl(modernized)

        assert "user_name" in result
        assert "userName" not in result
