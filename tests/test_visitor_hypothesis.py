"""Hypothesis property-based tests for AST visitor pattern.

Critical areas tested:
- ASTVisitor traversal completeness and correctness
- ASTTransformer node replacement, removal, and expansion
- Visitor dispatch mechanism
- Recursive transformation properties
- Immutability preservation during transformations
"""

from __future__ import annotations

from typing import Any

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax import parse
from ftllexengine.syntax.ast import (
    Comment,
    Identifier,
    Message,
    Placeable,
    Resource,
    SelectExpression,
    Term,
    VariableReference,
)
from ftllexengine.syntax.visitor import ASTTransformer, ASTVisitor

# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================

# Use st.from_regex for FTL identifiers (hypothesis.md insight)
ftl_identifiers = st.from_regex(r"[a-z][a-z0-9_-]*", fullmatch=True)

# Valid FTL pattern text: must contain at least one non-whitespace character.
# Per Fluent spec, Pattern ::= PatternElement+, and whitespace before pattern
# is consumed as blank_inline, so patterns need visible content.
# Constructed by definition: core guarantees visibility.
_ftl_visible_char = st.characters(
    blacklist_categories=("Cc", "Cs", "Z"),  # Exclude control, surrogate, separator
    blacklist_characters="{}[]*$->\n\r ",  # Exclude FTL syntax and space
)
_ftl_padding_char = st.sampled_from(" \t")

ftl_text = st.builds(
    lambda prefix, core, suffix: prefix + core + suffix,
    prefix=st.text(alphabet=_ftl_padding_char, max_size=3),
    core=st.text(alphabet=_ftl_visible_char, min_size=1, max_size=44),
    suffix=st.text(alphabet=_ftl_padding_char, max_size=3),
)


# ============================================================================
# HELPER VISITORS
# ============================================================================


class CountingVisitor(ASTVisitor):
    """Counts all node visits."""

    def __init__(self) -> None:
        """Initialize counter."""
        super().__init__()
        self.count = 0
        self.node_types: set[str] = set()

    def visit(self, node: Any) -> Any:
        """Count each visit."""
        self.count += 1
        self.node_types.add(type(node).__name__)
        return super().visit(node)


class TypeCollectorVisitor(ASTVisitor):
    """Collects all node types encountered."""

    def __init__(self) -> None:
        """Initialize collector."""
        super().__init__()
        self.types: list[str] = []

    def visit(self, node: Any) -> Any:
        """Collect node type."""
        self.types.append(type(node).__name__)
        return super().visit(node)


class IdentityTransformer(ASTTransformer):
    """Transform that returns nodes unchanged (uses base class default behavior)."""


class RemoveCommentsTransformer(ASTTransformer):
    """Remove all comments from AST."""

    def visit_Comment(self, node: Comment) -> None:
        """Remove comment node."""
        return


class RenameVariablesTransformer(ASTTransformer):
    """Rename variables according to mapping."""

    def __init__(self, mapping: dict[str, str]) -> None:
        """Initialize with variable mapping."""
        super().__init__()
        self.mapping = mapping

    def visit_VariableReference(self, node: VariableReference) -> VariableReference:
        """Rename variable if in mapping."""
        if node.id.name in self.mapping:
            return VariableReference(
                id=Identifier(name=self.mapping[node.id.name])
            )
        return node


# ============================================================================
# PROPERTY TESTS - VISITOR TRAVERSAL
# ============================================================================


class TestVisitorTraversal:
    """Property tests for ASTVisitor traversal."""

    @given(msg_id=ftl_identifiers, value=ftl_text)
    @settings(max_examples=100)
    def test_visitor_visits_all_nodes(self, msg_id: str, value: str) -> None:
        """PROPERTY: Visitor visits every node in tree."""
        # Filter out values that would create invalid FTL (whitespace-only values)
        assume(value.strip() != "")

        ftl_source = f"{msg_id} = {value}"
        resource = parse(ftl_source)

        visitor = CountingVisitor()
        visitor.visit(resource)

        # Must visit at least: Resource, Message, Identifier, Pattern, TextElement
        assert visitor.count >= 5
        assert "Resource" in visitor.node_types
        assert "Message" in visitor.node_types
        assert "Identifier" in visitor.node_types

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
    )
    @settings(max_examples=50)
    def test_visitor_visits_placeable_children(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Visitor visits children of placeables."""
        ftl_source = f"{msg_id} = Value: {{ ${var_name} }}"
        resource = parse(ftl_source)

        visitor = TypeCollectorVisitor()
        visitor.visit(resource)

        # Must visit placeable and its variable reference
        assert "Placeable" in visitor.types
        assert "VariableReference" in visitor.types
        assert "Identifier" in visitor.types

    @given(
        msg_id=ftl_identifiers,
        term_id=ftl_identifiers,
        term_value=ftl_text,
    )
    @settings(max_examples=50)
    def test_visitor_visits_term_references(
        self, msg_id: str, term_id: str, term_value: str
    ) -> None:
        """PROPERTY: Visitor visits term references and their components."""
        ftl_source = f"-{term_id} = {term_value}\n{msg_id} = Use {{ -{term_id} }}"
        resource = parse(ftl_source)

        visitor = TypeCollectorVisitor()
        visitor.visit(resource)

        assert "Term" in visitor.types
        assert "TermReference" in visitor.types
        assert visitor.types.count("Identifier") >= 2

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        key1=ftl_identifiers,
        key2=ftl_identifiers,
    )
    @settings(max_examples=50)
    def test_visitor_visits_select_expression_variants(
        self, msg_id: str, var_name: str, key1: str, key2: str
    ) -> None:
        """PROPERTY: Visitor visits all variants in select expression."""
        ftl_source = (
            f"{msg_id} = {{ ${var_name} ->\n"
            f"        [{key1}] First\n"
            f"       *[{key2}] Second\n"
            "    }"
        )
        resource = parse(ftl_source)

        visitor = TypeCollectorVisitor()
        visitor.visit(resource)

        assert "SelectExpression" in visitor.types
        assert visitor.types.count("Variant") == 2
        assert "VariableReference" in visitor.types


# ============================================================================
# PROPERTY TESTS - TRANSFORMER IDENTITY
# ============================================================================


class TestTransformerIdentity:
    """Property tests for identity transformations."""

    @given(msg_id=ftl_identifiers, value=ftl_text)
    @settings(max_examples=100)
    def test_identity_transform_preserves_structure(
        self, msg_id: str, value: str
    ) -> None:
        """PROPERTY: Identity transform returns equivalent AST."""
        ftl_source = f"{msg_id} = {value}"
        resource = parse(ftl_source)

        transformer = IdentityTransformer()
        transformed = transformer.transform(resource)

        # Structure must be preserved
        assert isinstance(transformed, Resource)
        assert len(transformed.entries) == len(resource.entries)

        if resource.entries:
            original_entry = resource.entries[0]
            transformed_entry = transformed.entries[0]
            assert isinstance(original_entry, Message)
            assert isinstance(transformed_entry, Message)
            assert original_entry.id.name == transformed_entry.id.name

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
    )
    @settings(max_examples=50)
    def test_identity_transform_preserves_placeables(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Identity transform preserves placeable structure."""
        ftl_source = f"{msg_id} = Text {{ ${var_name} }} more"
        resource = parse(ftl_source)

        transformer = IdentityTransformer()
        transformed = transformer.transform(resource)
        assert isinstance(transformed, Resource), f"Expected Resource, got {type(transformed)}"

        original_msg = resource.entries[0]
        transformed_msg = transformed.entries[0]

        assert isinstance(original_msg, Message)
        assert isinstance(transformed_msg, Message)
        assert original_msg.value is not None
        assert transformed_msg.value is not None
        assert len(original_msg.value.elements) == len(
            transformed_msg.value.elements
        )


# ============================================================================
# PROPERTY TESTS - TRANSFORMER NODE REMOVAL
# ============================================================================


class TestTransformerRemoval:
    """Property tests for node removal transformations."""

    @given(msg_id=ftl_identifiers, value=ftl_text)
    @settings(max_examples=100)
    def test_remove_comments_eliminates_all_comments(
        self, msg_id: str, value: str
    ) -> None:
        """PROPERTY: Comment removal transformer removes all comments."""
        ftl_source = f"# Comment\n{msg_id} = {value}\n# Another comment"
        resource = parse(ftl_source)

        # Count comments before
        visitor_before = TypeCollectorVisitor()
        visitor_before.visit(resource)
        comments_before = visitor_before.types.count("Comment")

        # Transform
        transformer = RemoveCommentsTransformer()
        transformed = transformer.transform(resource)

        # Count comments after
        visitor_after = TypeCollectorVisitor()
        visitor_after.visit(transformed)
        comments_after = visitor_after.types.count("Comment")

        # All comments must be removed
        assert comments_before > 0
        assert comments_after == 0

    @given(
        msg_id=ftl_identifiers,
        value=ftl_text,
        comment_text=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_remove_comments_preserves_messages(
        self, msg_id: str, value: str, comment_text: str
    ) -> None:
        """PROPERTY: Comment removal preserves non-comment nodes."""
        # Create FTL with comment
        safe_comment = comment_text.replace("\n", " ").replace("\r", " ")
        ftl_source = f"# {safe_comment}\n{msg_id} = {value}"
        resource = parse(ftl_source)

        transformer = RemoveCommentsTransformer()
        transformed = transformer.transform(resource)
        assert isinstance(transformed, Resource), f"Expected Resource, got {type(transformed)}"

        # Messages must be preserved
        original_messages = [e for e in resource.entries if isinstance(e, Message)]
        transformed_messages = [
            e for e in transformed.entries if isinstance(e, Message)
        ]

        assert len(original_messages) == len(transformed_messages)
        if original_messages:
            assert original_messages[0].id.name == transformed_messages[0].id.name


# ============================================================================
# PROPERTY TESTS - TRANSFORMER VARIABLE RENAMING
# ============================================================================


class TestTransformerRenaming:
    """Property tests for variable renaming transformations."""

    @given(
        msg_id=ftl_identifiers,
        old_var=ftl_identifiers,
        new_var=ftl_identifiers,
    )
    @settings(max_examples=100)
    def test_rename_variables_updates_all_references(
        self, msg_id: str, old_var: str, new_var: str
    ) -> None:
        """PROPERTY: Variable renaming updates all occurrences."""
        ftl_source = f"{msg_id} = Value: {{ ${old_var} }}"
        resource = parse(ftl_source)

        mapping = {old_var: new_var}
        transformer = RenameVariablesTransformer(mapping)
        transformed = transformer.transform(resource)
        assert isinstance(transformed, Resource), f"Expected Resource, got {type(transformed)}"

        # Check that variable was renamed
        msg = transformed.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # Find placeable
        placeables = [e for e in msg.value.elements if isinstance(e, Placeable)]
        assert len(placeables) > 0

        var_ref = placeables[0].expression
        assert isinstance(var_ref, VariableReference)
        assert var_ref.id.name == new_var

    @given(
        msg_id=ftl_identifiers,
        var1=ftl_identifiers,
        var2=ftl_identifiers,
        new_name=ftl_identifiers,
    )
    @settings(max_examples=50)
    def test_rename_preserves_other_variables(
        self, msg_id: str, var1: str, var2: str, new_name: str
    ) -> None:
        """PROPERTY: Renaming one variable preserves others."""
        # Ensure var1 and var2 are different
        assume(var1 != var2)

        ftl_source = f"{msg_id} = {{ ${var1} }} and {{ ${var2} }}"
        resource = parse(ftl_source)

        # Only rename var1
        mapping = {var1: new_name}
        transformer = RenameVariablesTransformer(mapping)
        transformed = transformer.transform(resource)
        assert isinstance(transformed, Resource), f"Expected Resource, got {type(transformed)}"

        msg = transformed.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        placeables = [e for e in msg.value.elements if isinstance(e, Placeable)]
        assert len(placeables) == 2

        # First should be renamed
        var_ref1 = placeables[0].expression
        assert isinstance(var_ref1, VariableReference)
        assert var_ref1.id.name == new_name

        # Second should be unchanged
        var_ref2 = placeables[1].expression
        assert isinstance(var_ref2, VariableReference)
        assert var_ref2.id.name == var2


# ============================================================================
# PROPERTY TESTS - TRANSFORMER IMMUTABILITY
# ============================================================================


class TestTransformerImmutability:
    """Property tests for AST immutability during transformation."""

    @given(msg_id=ftl_identifiers, value=ftl_text)
    @settings(max_examples=100)
    def test_transform_does_not_mutate_original(
        self, msg_id: str, value: str
    ) -> None:
        """PROPERTY: Transformation does not mutate original AST."""
        ftl_source = f"# Comment\n{msg_id} = {value}"
        resource = parse(ftl_source)

        # Store original state
        original_entry_count = len(resource.entries)
        original_first_entry = resource.entries[0]

        # Transform
        transformer = RemoveCommentsTransformer()
        transformed = transformer.transform(resource)

        # Original must be unchanged
        assert len(resource.entries) == original_entry_count
        assert resource.entries[0] is original_first_entry

        # Transformed should be different
        assert transformed is not resource

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        new_name=ftl_identifiers,
    )
    @settings(max_examples=50)
    def test_variable_rename_preserves_original(
        self, msg_id: str, var_name: str, new_name: str
    ) -> None:
        """PROPERTY: Variable renaming creates new nodes, preserves original."""
        ftl_source = f"{msg_id} = {{ ${var_name} }}"
        resource = parse(ftl_source)

        original_msg = resource.entries[0]
        assert isinstance(original_msg, Message)
        assert original_msg.value is not None
        original_placeable = original_msg.value.elements[0]
        assert isinstance(original_placeable, Placeable)
        original_var = original_placeable.expression
        assert isinstance(original_var, VariableReference)
        original_var_name = original_var.id.name

        # Transform
        mapping = {var_name: new_name}
        transformer = RenameVariablesTransformer(mapping)
        transformed = transformer.transform(resource)
        assert isinstance(transformed, Resource), f"Expected Resource, got {type(transformed)}"

        # Original variable name must be unchanged
        assert original_var_name == var_name
        assert original_var.id.name == var_name

        # Transformed should have new name
        transformed_msg = transformed.entries[0]
        assert isinstance(transformed_msg, Message)
        assert transformed_msg.value is not None
        transformed_placeable = transformed_msg.value.elements[0]
        assert isinstance(transformed_placeable, Placeable)
        transformed_var = transformed_placeable.expression
        assert isinstance(transformed_var, VariableReference)
        assert transformed_var.id.name == new_name


# ============================================================================
# PROPERTY TESTS - VISITOR DISPATCH
# ============================================================================


class TestVisitorDispatch:
    """Property tests for visitor method dispatch."""

    @given(msg_id=ftl_identifiers, value=ftl_text)
    @settings(max_examples=50)
    def test_dispatch_calls_correct_method(self, msg_id: str, value: str) -> None:
        """PROPERTY: Visitor dispatch calls visit_NodeType for each node."""

        class MethodTracker(ASTVisitor):
            """Track which visit methods are called."""

            def __init__(self) -> None:
                """Initialize tracker."""
                super().__init__()
                self.methods_called: set[str] = set()

            def visit(self, node: Any) -> Any:
                """Track method name."""
                method_name = f"visit_{type(node).__name__}"
                self.methods_called.add(method_name)
                return super().visit(node)

        ftl_source = f"{msg_id} = {value}"
        resource = parse(ftl_source)

        tracker = MethodTracker()
        tracker.visit(resource)

        # Must have called visit_Resource, visit_Message, etc.
        assert "visit_Resource" in tracker.methods_called
        assert "visit_Message" in tracker.methods_called
        assert "visit_Identifier" in tracker.methods_called
        assert "visit_Pattern" in tracker.methods_called

    @given(
        msg_id=ftl_identifiers,
        func_name=st.sampled_from(["NUMBER", "DATETIME"]),
        arg_value=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=50)
    def test_dispatch_visits_function_arguments(
        self, msg_id: str, func_name: str, arg_value: int
    ) -> None:
        """PROPERTY: Visitor dispatch reaches function call arguments."""
        ftl_source = f"{msg_id} = {{ {func_name}({arg_value}) }}"
        resource = parse(ftl_source)

        visitor = TypeCollectorVisitor()
        visitor.visit(resource)

        assert "FunctionReference" in visitor.types
        assert "CallArguments" in visitor.types
        assert "NumberLiteral" in visitor.types


# ============================================================================
# PROPERTY TESTS - COMPLEX TRANSFORMATIONS
# ============================================================================


class TestComplexTransformations:
    """Property tests for complex multi-level transformations."""

    @given(
        msg_id=ftl_identifiers,
        term_id=ftl_identifiers,
        var_name=ftl_identifiers,
        new_var=ftl_identifiers,
    )
    @settings(max_examples=50)
    def test_nested_structure_transformation(
        self, msg_id: str, term_id: str, var_name: str, new_var: str
    ) -> None:
        """PROPERTY: Transformation works on deeply nested structures."""
        ftl_source = (
            f"-{term_id} = Term {{ ${var_name} }}\n"
            f"{msg_id} = Message {{ -{term_id} }} and {{ ${var_name} }}"
        )
        resource = parse(ftl_source)

        mapping = {var_name: new_var}
        transformer = RenameVariablesTransformer(mapping)
        transformed = transformer.transform(resource)
        assert isinstance(transformed, Resource), f"Expected Resource, got {type(transformed)}"

        # Both term value and message should have renamed variable
        term = transformed.entries[0]
        msg = transformed.entries[1]

        assert isinstance(term, Term)
        assert isinstance(msg, Message)

        # Check term value
        assert term.value is not None
        term_placeables = [e for e in term.value.elements if isinstance(e, Placeable)]
        if term_placeables:
            var_in_term = term_placeables[0].expression
            assert isinstance(var_in_term, VariableReference)
            assert var_in_term.id.name == new_var

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        key1=ftl_identifiers,
        key2=ftl_identifiers,
        new_var=ftl_identifiers,
    )
    @settings(max_examples=50)
    def test_select_expression_variant_transformation(
        self, msg_id: str, var_name: str, key1: str, key2: str, new_var: str
    ) -> None:
        """PROPERTY: Transformation reaches variables in select variants."""
        ftl_source = (
            f"{msg_id} = {{ ${var_name} ->\n"
            f"        [{key1}] First {{ ${var_name} }}\n"
            f"       *[{key2}] Second {{ ${var_name} }}\n"
            "    }"
        )
        resource = parse(ftl_source)

        mapping = {var_name: new_var}
        transformer = RenameVariablesTransformer(mapping)
        transformed = transformer.transform(resource)
        assert isinstance(transformed, Resource), f"Expected Resource, got {type(transformed)}"

        msg = transformed.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # Find select expression
        select_placeables = [
            e
            for e in msg.value.elements
            if isinstance(e, Placeable)
            and isinstance(e.expression, SelectExpression)
        ]
        assert len(select_placeables) > 0

        select_expr = select_placeables[0].expression
        assert isinstance(select_expr, SelectExpression)

        # Selector should be renamed
        assert isinstance(select_expr.selector, VariableReference)
        assert select_expr.selector.id.name == new_var

        # Variables in variant values should also be renamed
        for variant in select_expr.variants:
            variant_placeables = [
                e for e in variant.value.elements if isinstance(e, Placeable)
            ]
            for placeable in variant_placeables:
                if isinstance(placeable.expression, VariableReference):
                    assert placeable.expression.id.name == new_var
