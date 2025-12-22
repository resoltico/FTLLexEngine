"""Visitor pattern for AST traversal.

Enables tools to traverse and transform Fluent AST without modifying node classes.

NOTE: This module follows Python stdlib ast.NodeVisitor naming convention.
Methods are named visit_NodeName (PascalCase) rather than visit_node_name (snake_case).
This is an intentional architectural decision to maintain consistency with Python's
AST visitor pattern. See: https://docs.python.org/3/library/ast.html#ast.NodeVisitor

Python 3.13+.
"""

from collections.abc import Callable
from dataclasses import fields, replace
from typing import ClassVar

from .ast import (
    ASTNode,
    Attribute,
    CallArguments,
    FunctionReference,
    Message,
    MessageReference,
    NamedArgument,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    Term,
    TermReference,
    VariableReference,
    Variant,
)


class ASTVisitor:
    """Base visitor for traversing Fluent AST.

    Follows stdlib ast.NodeVisitor convention: generic_visit() automatically
    traverses all child nodes. Override visit_NodeType methods to add custom
    behavior.

    Uses class-level dispatch table for performance:
    - Dispatch table built once per class definition via __init_subclass__
    - Avoids per-instance cache warmup overhead
    - Falls back to instance-level cache for dynamically added methods

    Use this to create:
    - Validators
    - Transformers
    - Code generators
    - Linters
    - Serializers

    Example:
        >>> class CountMessagesVisitor(ASTVisitor):
        ...     def __init__(self):
        ...         super().__init__()
        ...         self.count = 0
        ...
        ...     def visit_Message(self, node: Message) -> ASTNode:
        ...         self.count += 1
        ...         return self.generic_visit(node)  # Traverse children
        ...
        >>> visitor = CountMessagesVisitor()
        >>> visitor.visit(resource)
        >>> print(visitor.count)
    """

    __slots__ = ("_instance_dispatch_cache",)

    # Class-level dispatch table (method names only, not bound methods)
    # Built once per class definition via __init_subclass__
    _class_visit_methods: ClassVar[dict[str, str]] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Build class-level dispatch table when subclass is defined."""
        super().__init_subclass__(**kwargs)
        # Find all visit_* methods defined on this class
        cls._class_visit_methods = {}
        for name in dir(cls):
            if name.startswith("visit_") and name != "visit":
                # Extract node type name from method name (e.g., "visit_Message" -> "Message")
                node_type_name = name[6:]  # Skip "visit_"
                cls._class_visit_methods[node_type_name] = name

    def __init__(self) -> None:
        """Initialize visitor with empty instance-level dispatch cache."""
        # Instance cache for bound method references (faster than getattr each time)
        self._instance_dispatch_cache: dict[type[ASTNode], Callable[[ASTNode], ASTNode]] = {}

    def visit(self, node: ASTNode) -> ASTNode:
        """Visit a node (dispatcher with class-level + instance-level caching).

        Uses two-tier caching:
        1. Class-level: method names discovered at class definition time
        2. Instance-level: bound method references cached on first use

        Args:
            node: AST node to visit

        Returns:
            Result of visiting the node
        """
        node_type = type(node)

        # Check instance cache first (has bound method references)
        if node_type in self._instance_dispatch_cache:
            return self._instance_dispatch_cache[node_type](node)

        # Check class-level dispatch table for method name
        node_type_name = node_type.__name__
        if node_type_name in self._class_visit_methods:
            method_name = self._class_visit_methods[node_type_name]
            method = getattr(self, method_name)
        else:
            # Fall back to generic_visit
            method = self.generic_visit

        # Cache the bound method for next time
        self._instance_dispatch_cache[node_type] = method
        return method(node)  # type: ignore[no-any-return]  # getattr returns Any

    def generic_visit(self, node: ASTNode) -> ASTNode:
        """Default visitor (traverses children).

        Follows stdlib ast.NodeVisitor convention: automatically traverses
        all child nodes. Override visit_* methods to customize behavior.

        Args:
            node: AST node to visit

        Returns:
            The node itself (identity)
        """
        # Introspect dataclass fields to find and visit children
        for field in fields(node):
            value = getattr(node, field.name)

            # Skip None values and non-node fields (str, int, bool, etc.)
            if value is None or isinstance(value, (str, int, float, bool)):
                continue

            # Handle tuple of nodes (entries, elements, attributes, variants, etc.)
            if isinstance(value, tuple):
                for item in value:
                    # Only visit if item looks like an ASTNode (has dataclass fields)
                    if hasattr(item, "__dataclass_fields__"):
                        self.visit(item)
            # Handle single child node
            elif hasattr(value, "__dataclass_fields__"):
                self.visit(value)

        return node

    # Note: All visit_* methods now delegate to generic_visit() which handles
    # traversal automatically. Override these methods to add custom behavior
    # before/after visiting children.
    #
    # Example custom visitor:
    #     def visit_Message(self, node: Message) -> ASTNode:
    #         print(f"Visiting message: {node.id.name}")
    #         return self.generic_visit(node)  # Traverse children


class ASTTransformer(ASTVisitor):
    """AST transformer for in-place modifications using Python 3.13+ features.

    Extends ASTVisitor to enable transforming AST nodes in-place. Each visit method
    can return:
    - The modified node (replaces original)
    - None (removes node from parent)
    - A list of nodes (replaces single node with multiple)

    Uses Python 3.13's pattern matching for elegant node type handling.

    Example - Remove all comments:
        >>> class RemoveCommentsTransformer(ASTTransformer):
        ...     def visit_Comment(self, node: Comment) -> None:
        ...         return None  # Remove comments
        ...
        >>> transformer = RemoveCommentsTransformer()
        >>> cleaned_resource = transformer.transform(resource)

    Example - Rename all variables:
        >>> class RenameVariablesTransformer(ASTTransformer):
        ...     def __init__(self, mapping: dict[str, str]):
        ...         super().__init__()
        ...         self.mapping = mapping
        ...
        ...     def visit_VariableReference(self, node: VariableReference) -> VariableReference:
        ...         if node.id.name in self.mapping:
        ...             return VariableReference(
        ...                 id=Identifier(name=self.mapping[node.id.name])
        ...             )
        ...         return node
        ...
        >>> transformer = RenameVariablesTransformer({"old": "new"})
        >>> modified_resource = transformer.transform(resource)

    Example - Expand messages (1 → multiple):
        >>> class ExpandPluralsTransformer(ASTTransformer):
        ...     def visit_Message(self, node: Message) -> list[Message]:
        ...         # Generate multiple messages from select expressions
        ...         return [node, expanded_variant_1, expanded_variant_2]
        ...
        >>> transformer = ExpandPluralsTransformer()
        >>> expanded_resource = transformer.transform(resource)
    """

    def transform(self, node: ASTNode) -> ASTNode | None | list[ASTNode]:
        """Transform an AST node or tree.

        This is the main entry point for transformations.

        Args:
            node: AST node to transform

        Returns:
            Transformed node (may be different type, None, or list)
        """
        return self.visit(node)

    def generic_visit(self, node: ASTNode) -> ASTNode:
        """Transform node children (default behavior).

        Recursively transforms all child nodes. Uses dataclasses.replace()
        to create new immutable nodes (AST nodes are frozen).

        Args:
            node: AST node to transform

        Returns:
            New node with transformed children
        """
        # Use pattern matching for type-safe child transformation
        match node:
            case Resource(entries=entries):
                return replace(node, entries=self._transform_list(entries))
            case Message(id=id_node, value=value, attributes=attrs, comment=comment):
                return replace(
                    node,
                    id=self.visit(id_node),
                    value=self.visit(value) if value else None,
                    attributes=self._transform_list(attrs),
                    comment=self.visit(comment) if comment else None,
                )
            case Term(id=id_node, value=value, attributes=attrs, comment=comment):
                return replace(
                    node,
                    id=self.visit(id_node),
                    value=self.visit(value),
                    attributes=self._transform_list(attrs),
                    comment=self.visit(comment) if comment else None,
                )
            case Pattern(elements=elements):
                return replace(node, elements=self._transform_list(elements))
            case Placeable(expression=expr):
                return replace(node, expression=self.visit(expr))
            case SelectExpression(selector=selector, variants=variants):
                return replace(
                    node,
                    selector=self.visit(selector),
                    variants=self._transform_list(variants),
                )
            case Variant(key=key, value=value):
                return replace(node, key=self.visit(key), value=self.visit(value))
            case FunctionReference(id=id_node, arguments=args):
                # FunctionReference.arguments is not optional - always present
                return replace(
                    node,
                    id=self.visit(id_node),
                    arguments=self.visit(args),
                )
            case MessageReference(id=id_node, attribute=attr):
                return replace(
                    node,
                    id=self.visit(id_node),
                    attribute=self.visit(attr) if attr else None,
                )
            case TermReference(id=id_node, attribute=attr, arguments=args):
                return replace(
                    node,
                    id=self.visit(id_node),
                    attribute=self.visit(attr) if attr else None,
                    arguments=self.visit(args) if args else None,
                )
            case VariableReference(id=id_node):
                return replace(node, id=self.visit(id_node))
            case CallArguments(positional=pos, named=named):
                return replace(
                    node,
                    positional=self._transform_list(pos),
                    named=self._transform_list(named),
                )
            case NamedArgument(name=name, value=value):
                return replace(node, name=self.visit(name), value=self.visit(value))
            case Attribute(id=id_node, value=value):
                return replace(node, id=self.visit(id_node), value=self.visit(value))
            case _:
                # Leaf nodes (Identifier, TextElement, StringLiteral, NumberLiteral, Comment, Junk)
                # Return as-is (immutable)
                return node

    def _transform_list(self, nodes: tuple[ASTNode, ...]) -> tuple[ASTNode, ...]:
        """Transform a tuple of nodes.

        Handles node removal (None) and expansion (lists) using Python 3.13 features.
        AST nodes use tuples (immutable) instead of lists.

        Args:
            nodes: Tuple of AST nodes

        Returns:
            Transformed tuple (flattened, with None removed)
        """
        result: list[ASTNode] = []
        for node in nodes:
            transformed = self.visit(node)

            # Pattern match on transformation result
            match transformed:
                case None:
                    # Remove node (don't add to result)
                    continue
                case list():
                    # Expand node (add all items)
                    result.extend(transformed)
                case _:
                    # Replace node (add single item)
                    result.append(transformed)

        return tuple(result)
