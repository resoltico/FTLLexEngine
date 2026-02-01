"""Visitor pattern for AST traversal.

Enables tools to traverse and transform Fluent AST without modifying node classes.

NOTE: This module follows Python stdlib ast.NodeVisitor naming convention.
Methods are named visit_NodeName (PascalCase) rather than visit_node_name (snake_case).
This is an intentional architectural decision to maintain consistency with Python's
AST visitor pattern. See: https://docs.python.org/3/library/ast.html#ast.NodeVisitor

Type Parameters:
- ASTVisitor[T] is generic over return type T
- ASTVisitor (no type param) defaults to T=ASTNode
- ASTTransformer uses extended return type: ASTNode | None | list[ASTNode]

Python 3.13+.
"""

from dataclasses import Field, fields, replace
from typing import ClassVar

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.depth_guard import DepthGuard

from .ast import (
    ASTNode,
    Attribute,
    CallArguments,
    Comment,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)

__all__ = ["ASTTransformer", "ASTVisitor"]

# Type aliases for visitor return types
type VisitorResult = ASTNode
type TransformerResult = ASTNode | None | list[ASTNode]


class ASTVisitor[T = ASTNode]:
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

    __slots__ = ("_depth_guard",)

    # Class-level dispatch table (method names only, not bound methods)
    # Built once per class definition via __init_subclass__
    #
    # Dispatch avoids instance-level bound-method caching to prevent reference
    # cycles (self -> cache dict -> bound method -> self). Instead, visit()
    # resolves methods via getattr on each call. The overhead is negligible
    # compared to AST traversal and avoids accumulating unreachable objects
    # that require gc cycle collection.
    _class_visit_methods: ClassVar[dict[str, str]] = {}

    # Class-level cache for dataclass fields per node type
    # Avoids repeated introspection in generic_visit (PERF-VISITOR-002)
    _fields_cache: ClassVar[dict[type[ASTNode], tuple[Field[object], ...]]] = {}

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

    def __init__(self, *, max_depth: int | None = None) -> None:
        """Initialize visitor with depth guard and dispatch cache.

        Subclasses MUST call super().__init__() to ensure depth protection
        is properly initialized. Failure to do so will raise AttributeError
        on first visit() call.

        Args:
            max_depth: Maximum traversal depth (default: MAX_DEPTH from constants).
                      Controls depth protection against deeply nested ASTs.
        """
        # Depth guard prevents stack overflow from adversarial/malformed ASTs.
        # Uses same MAX_DEPTH (100) as parser, resolver, serializer for consistency.
        effective_max_depth = max_depth if max_depth is not None else MAX_DEPTH
        self._depth_guard = DepthGuard(max_depth=effective_max_depth)

    def visit(self, node: ASTNode) -> T:
        """Visit a node (dispatcher with depth protection).

        Depth Protection:
            Every visit() call increments the depth counter. This ensures
            depth protection works regardless of whether custom visit_*
            methods call generic_visit() or visit() on children. The guard
            is in the dispatcher, not the traverser, so no bypass is possible.

        Dispatch:
            Uses the class-level method name table built by __init_subclass__
            to resolve visit_* methods via getattr on each call. This avoids
            caching bound methods on the instance, which would create reference
            cycles (self -> cache dict -> bound method -> self).

        Args:
            node: AST node to visit

        Returns:
            Result of visiting the node

        Raises:
            FrozenFluentError: If traversal depth exceeds max_depth (category=RESOLUTION)
        """
        # Depth guard in visit() ensures protection for ALL traversals,
        # including custom visit_* methods that call self.visit() on children
        # without going through generic_visit(). This closes the bypass vector.
        with self._depth_guard:
            # Check class-level dispatch table for method name
            node_type_name = type(node).__name__
            method_name = self._class_visit_methods.get(node_type_name)
            if method_name is not None:
                return getattr(self, method_name)(node)  # type: ignore[no-any-return]
            return self.generic_visit(node)

    def _get_node_fields(self, node_type: type[ASTNode]) -> tuple[Field[object], ...]:
        """Get cached dataclass fields for a node type.

        Uses class-level cache to avoid repeated introspection.
        Thread-safe: dict operations are atomic in CPython.

        Args:
            node_type: The AST node type to get fields for

        Returns:
            Tuple of dataclass Field objects
        """
        if node_type not in ASTVisitor._fields_cache:
            ASTVisitor._fields_cache[node_type] = fields(node_type)
        return ASTVisitor._fields_cache[node_type]

    def generic_visit(self, node: ASTNode) -> T:
        """Default visitor that traverses all child nodes.

        Follows stdlib ast.NodeVisitor convention: automatically traverses
        all child nodes. Override visit_* methods to customize behavior.

        Note:
            Depth protection is handled by visit(), not here. This ensures
            protection works regardless of how subclasses implement traversal.

        Args:
            node: AST node to visit

        Returns:
            The node itself (identity)
        """
        # Depth guard is in visit() - every self.visit() call is protected
        # Use cached fields to avoid repeated introspection (PERF-VISITOR-002)
        for field in self._get_node_fields(type(node)):
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

        return node  # type: ignore[return-value]  # T defaults to ASTNode

    # Note: All visit_* methods now delegate to generic_visit() which handles
    # traversal automatically. Override these methods to add custom behavior
    # before/after visiting children.
    #
    # Example custom visitor:
    #     def visit_Message(self, node: Message) -> ASTNode:
    #         print(f"Visiting message: {node.id.name}")
    #         return self.generic_visit(node)  # Traverse children


class ASTTransformer(ASTVisitor[TransformerResult]):
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

    def transform(self, node: ASTNode) -> TransformerResult:
        """Transform an AST node or tree.

        This is the main entry point for transformations.

        Args:
            node: AST node to transform

        Returns:
            Transformed node (may be different type, None, or list)
        """
        return self.visit(node)

    def _validate_scalar_result(
        self, result: TransformerResult, field_name: str
    ) -> ASTNode:
        """Validate that required scalar field assignment returns a single node.

        AST nodes have two types of fields:
        - Scalar fields (e.g., Message.id, Pattern.value): Expect single node
        - Collection fields (e.g., Resource.entries, Pattern.elements): Expect tuple of nodes

        This method enforces that visit() for REQUIRED scalar fields returns a
        single ASTNode, not None or list[ASTNode]. Returning None/list for required
        scalar fields creates invalid AST structures that violate dataclass constraints.

        For OPTIONAL fields (e.g., Message.comment), use _validate_optional_scalar_result
        instead, which permits None returns.

        Args:
            result: Result from visit() call
            field_name: Name of the field being assigned (for error messages)

        Returns:
            The validated single ASTNode

        Raises:
            TypeError: If result is None or list[ASTNode] (invalid for required scalar fields)
        """
        match result:
            case None:
                msg = (
                    f"Cannot assign None to required scalar field '{field_name}'. "
                    f"Required scalar fields must have a single ASTNode. "
                    f"To remove a node, delete its parent or transform its parent to None."
                )
                raise TypeError(msg)
            case list():
                msg = (
                    f"Cannot assign list to scalar field '{field_name}'. "
                    f"Scalar fields require a single ASTNode. "
                    f"Got {len(result)} nodes: {[type(n).__name__ for n in result]}. "
                    f"To expand nodes, return a list from the parent's visit method."
                )
                raise TypeError(msg)
            case _:
                # Single ASTNode - valid
                return result

    def _validate_optional_scalar_result(
        self, result: TransformerResult, field_name: str
    ) -> ASTNode | None:
        """Validate optional scalar field assignment, allowing None.

        For optional fields like Message.comment and Message.value, transformers
        may return None to remove the field value. This method permits None while
        still rejecting list returns (scalar fields cannot expand to lists).

        Args:
            result: Result from visit() call
            field_name: Name of the field being assigned (for error messages)

        Returns:
            The validated ASTNode or None

        Raises:
            TypeError: If result is list[ASTNode] (invalid for scalar fields)
        """
        match result:
            case None:
                # None is valid for optional fields (removal)
                return None
            case list():
                msg = (
                    f"Cannot assign list to optional scalar field '{field_name}'. "
                    f"Scalar fields require a single ASTNode or None. "
                    f"Got {len(result)} nodes: {[type(n).__name__ for n in result]}. "
                    f"To expand nodes, return a list from the parent's visit method."
                )
                raise TypeError(msg)
            case _:
                # Single ASTNode - valid
                return result

    def generic_visit(self, node: ASTNode) -> TransformerResult:
        """Transform node children using pattern matching.

        Recursively transforms all child nodes. Uses dataclasses.replace()
        to create new immutable nodes (AST nodes are frozen).

        Note:
            Depth protection is handled by visit(), not here. This ensures
            protection works regardless of how subclasses implement traversal.

        Args:
            node: AST node to transform

        Returns:
            New node with transformed children
        """
        # Depth guard is in visit() - every self.visit() call is protected
        # Use pattern matching for type-safe child transformation
        match node:
            case Resource(entries=entries):
                return replace(
                    node,
                    entries=self._transform_list(
                        entries,
                        "Resource.entries",
                        (Message, Term, Comment, Junk),
                    ),
                )
            case Message(id=id_node, value=value, attributes=attrs, comment=comment):
                # Message.value and Message.comment are optional - allow None returns
                validated_value = (
                    self._validate_optional_scalar_result(
                        self.visit(value), "Message.value"
                    )
                    if value
                    else None
                )
                validated_comment = (
                    self._validate_optional_scalar_result(
                        self.visit(comment), "Message.comment"
                    )
                    if comment
                    else None
                )
                return replace(
                    node,
                    id=self._validate_scalar_result(self.visit(id_node), "Message.id"),
                    value=validated_value,
                    attributes=self._transform_list(
                        attrs, "Message.attributes", (Attribute,)
                    ),
                    comment=validated_comment,
                )
            case Term(id=id_node, value=value, attributes=attrs, comment=comment):
                # Term.comment is optional - allow None returns
                validated_comment = (
                    self._validate_optional_scalar_result(
                        self.visit(comment), "Term.comment"
                    )
                    if comment
                    else None
                )
                return replace(
                    node,
                    id=self._validate_scalar_result(self.visit(id_node), "Term.id"),
                    value=self._validate_scalar_result(self.visit(value), "Term.value"),
                    attributes=self._transform_list(
                        attrs, "Term.attributes", (Attribute,)
                    ),
                    comment=validated_comment,
                )
            case Pattern(elements=elements):
                return replace(
                    node,
                    elements=self._transform_list(
                        elements, "Pattern.elements", (TextElement, Placeable)
                    ),
                )
            case Placeable(expression=expr):
                validated_expr = self._validate_scalar_result(
                    self.visit(expr), "Placeable.expression"
                )
                return replace(node, expression=validated_expr)
            case SelectExpression(selector=selector, variants=variants):
                validated_selector = self._validate_scalar_result(
                    self.visit(selector), "SelectExpression.selector"
                )
                return replace(
                    node,
                    selector=validated_selector,
                    variants=self._transform_list(
                        variants, "SelectExpression.variants", (Variant,)
                    ),
                )
            case Variant(key=key, value=value):
                return replace(
                    node,
                    key=self._validate_scalar_result(self.visit(key), "Variant.key"),
                    value=self._validate_scalar_result(self.visit(value), "Variant.value"),
                )
            case FunctionReference(id=id_node, arguments=args):
                # FunctionReference.arguments is not optional - always present
                func_validated_args = self._validate_scalar_result(
                    self.visit(args), "FunctionReference.arguments"
                )
                return replace(
                    node,
                    id=self._validate_scalar_result(self.visit(id_node), "FunctionReference.id"),
                    arguments=func_validated_args,
                )
            case MessageReference(id=id_node, attribute=attr):
                # MessageReference.attribute is optional - allow None returns
                msg_validated_attr = (
                    self._validate_optional_scalar_result(
                        self.visit(attr), "MessageReference.attribute"
                    )
                    if attr
                    else None
                )
                return replace(
                    node,
                    id=self._validate_scalar_result(self.visit(id_node), "MessageReference.id"),
                    attribute=msg_validated_attr,
                )
            case TermReference(id=id_node, attribute=attr, arguments=args):
                # TermReference.attribute and TermReference.arguments are optional
                # Type narrowing needed because validator returns ASTNode | None
                # but fields expect Identifier | None and CallArguments | None
                term_validated_attr: Identifier | None = (
                    self._validate_optional_scalar_result(
                        self.visit(attr), "TermReference.attribute"
                    )  # type: ignore[assignment]
                    if attr
                    else None
                )
                term_validated_args: CallArguments | None = (
                    self._validate_optional_scalar_result(
                        self.visit(args), "TermReference.arguments"
                    )  # type: ignore[assignment]
                    if args
                    else None
                )
                return replace(
                    node,
                    id=self._validate_scalar_result(self.visit(id_node), "TermReference.id"),
                    attribute=term_validated_attr,
                    arguments=term_validated_args,
                )
            case VariableReference(id=id_node):
                validated_id = self._validate_scalar_result(
                    self.visit(id_node), "VariableReference.id"
                )
                return replace(node, id=validated_id)
            case CallArguments(positional=pos, named=named):
                return replace(
                    node,
                    positional=self._transform_list(
                        pos,
                        "CallArguments.positional",
                        (
                            StringLiteral, NumberLiteral, VariableReference,
                            MessageReference, TermReference, FunctionReference,
                            Placeable,
                        ),
                    ),
                    named=self._transform_list(
                        named, "CallArguments.named", (NamedArgument,)
                    ),
                )
            case NamedArgument(name=name, value=value):
                return replace(
                    node,
                    name=self._validate_scalar_result(self.visit(name), "NamedArgument.name"),
                    value=self._validate_scalar_result(self.visit(value), "NamedArgument.value"),
                )
            case Attribute(id=id_node, value=value):
                return replace(
                    node,
                    id=self._validate_scalar_result(self.visit(id_node), "Attribute.id"),
                    value=self._validate_scalar_result(self.visit(value), "Attribute.value"),
                )
            case _:
                # Leaf nodes: Identifier, TextElement, StringLiteral,
                # NumberLiteral, Comment, Junk. Return as-is (immutable).
                return node

    def _transform_list(
        self,
        nodes: tuple[ASTNode, ...],
        field_name: str,
        expected_types: tuple[type[ASTNode], ...],
    ) -> tuple[ASTNode, ...]:
        """Transform a tuple of nodes with runtime type validation.

        Handles node removal (None) and expansion (lists). Validates that
        each resulting node is an instance of one of the expected types,
        preventing silent AST corruption from buggy transformers.

        Args:
            nodes: Tuple of AST nodes to transform.
            field_name: Dotted field name for error messages (e.g., "Pattern.elements").
            expected_types: Tuple of allowed node types for this field.

        Returns:
            Transformed tuple (flattened, with None removed, type-validated).

        Raises:
            TypeError: If any transformed node is not an instance of expected_types.
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
                    # Expand node (add all items after validation)
                    for item in transformed:
                        self._validate_element_type(item, field_name, expected_types)
                    result.extend(transformed)
                case _:
                    # Replace node (add single item after validation)
                    self._validate_element_type(transformed, field_name, expected_types)
                    result.append(transformed)

        return tuple(result)

    @staticmethod
    def _validate_element_type(
        node: ASTNode,
        field_name: str,
        expected_types: tuple[type[ASTNode], ...],
    ) -> None:
        """Validate that a transformed node matches the expected field type.

        Args:
            node: Transformed AST node.
            field_name: Dotted field name for error messages.
            expected_types: Tuple of allowed node types.

        Raises:
            TypeError: If node is not an instance of any expected type.
        """
        if not isinstance(node, expected_types):
            expected_names = " | ".join(t.__name__ for t in expected_types)
            msg = (
                f"Transformer produced {type(node).__name__} for "
                f"'{field_name}', expected {expected_names}. "
                f"Transformers must return nodes matching the field's "
                f"type constraint to maintain AST structural integrity."
            )
            raise TypeError(msg)
