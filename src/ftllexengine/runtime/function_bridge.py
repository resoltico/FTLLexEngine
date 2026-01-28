"""Function call bridge between Python and FTL calling conventions.

Provides a bidirectional mapping layer:
    - Python: snake_case parameters (PEP 8)
    - FTL: camelCase parameters (JavaScript/ICU heritage)

This allows Python functions to use Pythonic APIs while maintaining
compatibility with FTL syntax in .ftl files.

Architecture:
    - FunctionRegistry: Manages function registration and calling
    - Auto-generates parameter mappings from function signatures
    - Converts FTL camelCase args → Python snake_case args at call time

Example:
    # Python function (snake_case):
    def number_format(value, *, minimum_fraction_digits=0):
        ...

    # FTL file (camelCase):
    price = { $amount NUMBER(minimumFractionDigits: 2) }

    # Bridge automatically converts: minimumFractionDigits → minimum_fraction_digits

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from inspect import Parameter, signature
from typing import TYPE_CHECKING, Protocol, overload

from ftllexengine.diagnostics import ErrorCategory, ErrorTemplate, FrozenFluentError

if TYPE_CHECKING:
    from ftllexengine.runtime.function_metadata import FunctionMetadata

__all__ = [
    "FluentFunction",
    "FluentNumber",
    "FluentValue",
    "FunctionRegistry",
    "FunctionSignature",
    "fluent_function",
]

@dataclass(frozen=True, slots=True)
class FluentNumber:
    """Wrapper for formatted numbers preserving numeric identity and precision.

    When NUMBER() formats a value, the result needs to:
    1. Display the formatted string in output (e.g., "1,234.56")
    2. Still match plural categories in select expressions (e.g., [one], [other])
    3. Preserve precision metadata for CLDR plural rules (v operand)

    FluentNumber carries all three pieces of information, allowing the resolver to:
    - Use __str__ for final output (formatted string)
    - Use .value and .precision for plural category matching

    Attributes:
        value: Original numeric value for matching
        formatted: Locale-formatted string for display
        precision: Visible fraction digit count (CLDR v operand), computed from
            the formatted string. This is the ACTUAL count of digits after the
            decimal separator, not the minimum_fraction_digits parameter.
            None if not specified (raw variable interpolation).

    Example:
        >>> fn = FluentNumber(value=1, formatted="1.00", precision=2)
        >>> str(fn)  # Used in output
        '1.00'
        >>> fn.value  # Used for plural matching
        1
        >>> fn.precision  # CLDR v operand: 2 visible fraction digits
        2

    Precision Semantics:
        The precision field reflects what is VISIBLE in the formatted output:
        - FluentNumber(1.5, "1.5", precision=1) - one visible fraction digit
        - FluentNumber(1, "1.00", precision=2) - two visible fraction digits
        - FluentNumber(1, "1", precision=0) - no visible fraction digits
    """

    value: int | float | Decimal
    formatted: str
    precision: int | None = None

    def __str__(self) -> str:
        """Return formatted string for output."""
        return self.formatted

    def __contains__(self, item: str) -> bool:
        """Support membership testing on formatted string."""
        return item in self.formatted

    def __len__(self) -> int:
        """Return length of formatted string."""
        return len(self.formatted)

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return f"FluentNumber(value={self.value!r}, formatted={self.formatted!r})"


# Type alias for Fluent-compatible function values.
# This is the CANONICAL definition - imported by resolver.py and localization.py.
# Defined here (not in resolver.py) to avoid circular imports.
# Note: Includes both datetime.date and datetime.datetime for flexibility.
# FluentNumber added for NUMBER() identity preservation in select expressions.
#
# Collections Support:
#   Sequence[FluentValue] and Mapping[str, FluentValue] are supported for custom
#   functions that need to pass structured data. The cache (_make_hashable) and
#   resolver handle these types correctly. Collections are recursively typed.
type FluentValue = (
    str
    | int
    | float
    | bool
    | Decimal
    | datetime
    | date
    | FluentNumber
    | None
    | Sequence["FluentValue"]
    | Mapping[str, "FluentValue"]
)

# Attribute name for marking functions that require locale injection.
# Used by FunctionRegistry.should_inject_locale() and @fluent_function decorator.
_FTL_REQUIRES_LOCALE_ATTR: str = "_ftl_requires_locale"


class FluentFunction(Protocol):
    """Protocol for Fluent-compatible functions.

    Functions must accept:
    - value: The primary value to format (positional)
    - locale_code: The locale code (positional)
    - **kwargs: Named arguments (keyword-only)

    And return a FluentValue (typically str, but may return numeric types for
    functions that produce values for further processing like NUMBER).
    """

    def __call__(
        self,
        value: FluentValue,
        locale_code: str,
        /,
        **kwargs: FluentValue,
    ) -> FluentValue:
        ...  # pragma: no cover  # Protocol stub - not executable


@overload
def fluent_function[F: Callable[..., FluentValue]](
    func: F,
    *,
    inject_locale: bool = False,
) -> F: ...


@overload
def fluent_function[F: Callable[..., FluentValue]](
    func: None = None,
    *,
    inject_locale: bool = False,
) -> Callable[[F], F]: ...


def fluent_function[F: Callable[..., FluentValue]](
    func: F | None = None,
    *,
    inject_locale: bool = False,
) -> F | Callable[[F], F]:
    """Decorator for marking custom functions with Fluent metadata.

    Use this decorator to configure how your custom function integrates
    with the Fluent resolution system.

    Args:
        func: The function to decorate (auto-filled when used without parentheses)
        inject_locale: If True, the bundle's locale code will be appended as
            the final positional argument when the function is called from FTL.
            Use this for locale-aware formatting functions.

    Returns:
        Decorated function with Fluent metadata attributes set.

    Locale Injection Protocol:
        When inject_locale=True, the bundle's locale code is APPENDED after all
        positional arguments provided by FTL. For single-argument functions (the
        common case for formatting), this effectively makes locale the second
        positional argument.

        Expected function signature pattern:
            def my_func(value: T, locale_code: str, *, keyword_args...) -> R

        FTL call pattern:
            { MY_FUNC($value, kwarg: "x") }  ->  my_func(value, locale_code, kwarg="x")

        Built-in functions (NUMBER, DATETIME, CURRENCY) follow this pattern and
        the resolver validates arity before injection. For custom functions, ensure
        your signature matches the expected pattern.

    Example - Simple function (no locale):
        >>> @fluent_function
        ... def my_upper(value: str) -> str:
        ...     return value.upper()
        >>> bundle.add_function("MYUPPER", my_upper)
        >>> # FTL: { MY_UPPER($name) }

    Example - Locale-aware function:
        >>> @fluent_function(inject_locale=True)
        ... def my_format(value: int, locale_code: str) -> str:
        ...     # Format number according to locale
        ...     return format_for_locale(value, locale_code)
        >>> bundle.add_function("MYFORMAT", my_format)
        >>> # FTL: { MY_FORMAT($count) }
        >>> # Bundle appends locale: my_format(count_value, "en_US")
    """

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> FluentValue:
            return fn(*args, **kwargs)

        # Set locale injection marker if requested
        if inject_locale:
            setattr(wrapper, _FTL_REQUIRES_LOCALE_ATTR, True)

        return wrapper  # type: ignore[return-value]  # wrapper preserves F signature

    # Handle both @fluent_function and @fluent_function() usage
    if func is not None:
        return decorator(func)
    return decorator


@dataclass(frozen=True, slots=True)
class FunctionSignature:
    """Function metadata with calling convention mappings.

    Attributes:
        python_name: Function name in Python (snake_case)
        ftl_name: Function name in FTL files (UPPERCASE)
        param_mapping: Immutable mapping of FTL camelCase → Python snake_case params.
            Stored as sorted tuple of (ftl_param, python_param) pairs for full
            immutability. Use dict(param_mapping) for O(1) lookup when needed.
        callable: The actual Python function

    Immutability:
        All fields are immutable. param_mapping uses tuple instead of dict to
        ensure FunctionSignature objects can be safely shared across registries
        without risk of mutation via retained references.
    """

    python_name: str
    ftl_name: str
    param_mapping: tuple[tuple[str, str], ...]
    callable: Callable[..., FluentValue]


class FunctionRegistry:
    """Manages Python ↔ FTL function calling convention bridge.

    Provides automatic parameter name conversion:
        - FTL uses camelCase (minimumFractionDigits)
        - Python uses snake_case (minimum_fraction_digits)

    The registry handles the conversion transparently.

    Supports dict-like introspection:
        - list_functions(): List all registered function names
        - get_function_info(name): Get function metadata
        - __iter__: Iterate over function names
        - __len__: Count registered functions
        - __contains__: Check if function exists (supports 'in' operator)

    Freezing:
        Registries can be frozen via freeze() to prevent further modifications.
        Once frozen, register() will raise TypeError. This is used by
        get_shared_registry() to protect the shared singleton from accidental
        modification.

    Memory Optimization:
        Uses __slots__ for memory efficiency (avoids per-instance __dict__).

    Example:
        >>> registry = FunctionRegistry()
        >>> registry.register(my_func, ftl_name="CUSTOM")
        >>> "CUSTOM" in registry
        True
        >>> len(registry)
        1
        >>> for name in registry:
        ...     print(name)
        CUSTOM
    """

    __slots__ = ("_frozen", "_functions")

    def __init__(self) -> None:
        """Initialize empty function registry."""
        self._functions: dict[str, FunctionSignature] = {}
        self._frozen: bool = False

    def register(
        self,
        func: Callable[..., FluentValue],
        *,
        ftl_name: str | None = None,
        param_map: dict[str, str] | None = None,
    ) -> None:
        """Register Python function for FTL use.

        Args:
            func: Python function to register
            ftl_name: Function name in FTL (default: func.__name__.upper())
            param_map: Custom parameter mappings (overrides auto-generation)

        Raises:
            TypeError: If registry is frozen (via freeze() method).
            TypeError: If func has inject_locale=True but signature is incompatible.
                      Functions marked with inject_locale=True must have at least
                      2 positional parameters to receive (value, locale_code).

        Example:
            >>> def number_format(value, *, minimum_fraction_digits=0):
            ...     return str(value)
            >>> registry = FunctionRegistry()
            >>> registry.register(number_format, ftl_name="NUMBER")
            >>> # FTL: { $x NUMBER(minimumFractionDigits: 2) }
            >>> # Python: number_format(x, minimum_fraction_digits=2)
        """
        if self._frozen:
            msg = (
                "Cannot modify frozen registry. "
                "Use create_default_registry() to get a mutable copy."
            )
            raise TypeError(msg)

        # Default FTL name: UPPERCASE version of function name
        if ftl_name is None:
            ftl_name = getattr(func, "__name__", "unknown").upper()

        # Auto-generate parameter mappings from function signature
        try:
            sig = signature(func)
        except ValueError as e:
            # Some callables (certain C functions, mock objects) don't have signatures
            msg = (
                f"Cannot register '{ftl_name}': callable has no inspectable signature. "
                f"Use param_mapping parameter to provide explicit mappings. Error: {e}"
            )
            raise TypeError(msg) from e

        # Validate signature compatibility with locale injection if required
        if getattr(func, _FTL_REQUIRES_LOCALE_ATTR, False):
            # Count positional-or-keyword parameters that can accept positional arguments
            # POSITIONAL_ONLY and POSITIONAL_OR_KEYWORD both accept positional args
            positional_capable = [
                p for p in sig.parameters.values()
                if p.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
                and p.name != "self"
            ]
            # Check if function has VAR_POSITIONAL (*args) which can accept any number of
            # positional arguments. A function with *args can receive (value, locale_code).
            has_var_positional = any(
                p.kind == Parameter.VAR_POSITIONAL for p in sig.parameters.values()
            )
            if not has_var_positional and len(positional_capable) < 2:
                msg = (
                    f"Function '{ftl_name}' marked with inject_locale=True requires "
                    f"at least 2 positional parameters (value, locale_code), but has "
                    f"{len(positional_capable)}. Signature: {sig}"
                )
                raise TypeError(msg)

        auto_map: dict[str, str] = {}

        for param_name in sig.parameters:
            # Skip 'self' and positional-only markers
            if param_name in ("self", "/", "*"):
                continue

            # Strip leading underscores for FTL name (Python convention for unused/private)
            # but keep original param_name for the mapping value
            stripped_name = param_name.lstrip("_")

            # Convert Python snake_case → FTL camelCase
            camel_case = self._to_camel_case(stripped_name)

            # Detect underscore collision: e.g., both `_value` and `value` map to `value`
            if camel_case in auto_map and auto_map[camel_case] != param_name:
                msg = (
                    f"Parameter name collision in function '{ftl_name}': "
                    f"'{auto_map[camel_case]}' and '{param_name}' both map to FTL "
                    f"parameter '{camel_case}'"
                )
                raise ValueError(msg)

            auto_map[camel_case] = param_name

        # Merge custom mappings with auto-generated ones
        # Custom mappings override auto-generated ones
        final_map = {**auto_map, **(param_map or {})}

        # Convert to immutable sorted tuple for safe sharing across registries
        # Sorting ensures deterministic ordering for testing and debugging
        immutable_mapping = tuple(sorted(final_map.items()))

        # Store function signature
        self._functions[ftl_name] = FunctionSignature(
            python_name=getattr(func, "__name__", "unknown"),
            ftl_name=ftl_name,
            param_mapping=immutable_mapping,
            callable=func,
        )

    def call(
        self,
        ftl_name: str,
        positional: Sequence[FluentValue],
        named: Mapping[str, FluentValue],
    ) -> FluentValue:
        """Call Python function with FTL arguments.

        Converts FTL camelCase parameters to Python snake_case parameters.

        Args:
            ftl_name: Function name from FTL (e.g., "NUMBER")
            positional: Positional arguments
            named: Named arguments from FTL (camelCase)

        Returns:
            Function result as FluentValue (str, int, float, Decimal, datetime, etc.).
            The resolver will format non-string values to strings for final output.

        Raises:
            FrozenFluentError: If function not found (category=REFERENCE)
            FrozenFluentError: If function execution fails (category=RESOLUTION)
        """
        # Check if function exists
        if ftl_name not in self._functions:
            diag = ErrorTemplate.function_not_found(ftl_name)
            raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)

        func_sig = self._functions[ftl_name]

        # Convert FTL camelCase args → Python snake_case args
        # Reconstruct dict from immutable tuple for O(1) lookup
        param_dict = dict(func_sig.param_mapping)
        python_kwargs = {}
        for ftl_param, value in named.items():
            # Look up Python parameter name
            python_param = param_dict.get(ftl_param, ftl_param)
            python_kwargs[python_param] = value

        # Call Python function
        # Only catch TypeError and ValueError which typically indicate argument issues:
        # - TypeError: Wrong number/types of arguments passed to function
        # - ValueError: Function explicitly rejected an argument value
        #
        # Do NOT catch KeyError, AttributeError, ArithmeticError, etc. These indicate
        # bugs in the custom function implementation and should propagate to expose
        # the real issue. Swallowing them masks debugging information.
        #
        # Type safety note: positional is Sequence[FluentValue] but custom functions
        # may expect specific types. Type checking is enforced at runtime via
        # TypeError, not at compile time. This is intentional for dynamic dispatch.
        try:
            return func_sig.callable(*positional, **python_kwargs)
        except (TypeError, ValueError) as e:
            diag = ErrorTemplate.function_failed(ftl_name, str(e))
            raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag) from e

    def has_function(self, ftl_name: str) -> bool:
        """Check if function is registered.

        Args:
            ftl_name: Function name from FTL

        Returns:
            True if function is registered
        """
        return ftl_name in self._functions

    def freeze(self) -> None:
        """Freeze registry to prevent further modifications.

        Once frozen, calling register() will raise TypeError.
        This is used by get_shared_registry() to protect the shared
        singleton from accidental modification.

        Freezing is irreversible. To get a mutable registry with the
        same functions, use copy() which creates an unfrozen copy.
        """
        self._frozen = True

    @property
    def frozen(self) -> bool:
        """Check if registry is frozen (read-only).

        Returns:
            True if registry is frozen and cannot be modified.
        """
        return self._frozen

    def get_python_name(self, ftl_name: str) -> str | None:
        """Get Python function name for FTL function.

        Args:
            ftl_name: Function name from FTL

        Returns:
            Python function name, or None if not found
        """
        sig = self._functions.get(ftl_name)
        return sig.python_name if sig else None

    def list_functions(self) -> list[str]:
        """List all registered function names (FTL names).

        Returns:
            List of FTL function names (e.g., ["NUMBER", "DATETIME", "CURRENCY"])

        Example:
            >>> registry = FunctionRegistry()
            >>> registry.register(lambda x: str(x), ftl_name="CUSTOM")
            >>> registry.list_functions()
            ['CUSTOM']
        """
        return list(self._functions.keys())

    def get_function_info(self, ftl_name: str) -> FunctionSignature | None:
        """Get function metadata by FTL name.

        Args:
            ftl_name: Function name from FTL (e.g., "NUMBER")

        Returns:
            FunctionSignature with metadata, or None if not found

        Example:
            >>> registry = FunctionRegistry()
            >>> def my_func(value, *, min_digits=0): return str(value)
            >>> registry.register(my_func, ftl_name="MYFUNC")
            >>> info = registry.get_function_info("MYFUNC")
            >>> info.python_name
            'my_func'
            >>> info.ftl_name
            'MYFUNC'
        """
        return self._functions.get(ftl_name)

    def get_callable(self, ftl_name: str) -> Callable[..., FluentValue] | None:
        """Get the underlying callable for a registered function.

        Public API for accessing function callables without exposing internal
        storage. Use this instead of accessing _functions directly.

        Args:
            ftl_name: Function name from FTL (e.g., "NUMBER")

        Returns:
            The registered callable, or None if function not found

        Example:
            >>> registry = FunctionRegistry()
            >>> def my_func(value): return str(value)
            >>> registry.register(my_func, ftl_name="MYFUNC")
            >>> callable_func = registry.get_callable("MYFUNC")
            >>> callable_func is my_func
            True
        """
        sig = self._functions.get(ftl_name)
        return sig.callable if sig else None

    def __iter__(self) -> Iterator[str]:
        """Iterate over FTL function names.

        Returns:
            Iterator over FTL function names

        Example:
            >>> registry = FunctionRegistry()
            >>> registry.register(lambda x: str(x), ftl_name="FUNC1")
            >>> registry.register(lambda x: str(x), ftl_name="FUNC2")
            >>> for name in registry:
            ...     print(name)
            FUNC1
            FUNC2
        """
        return iter(self._functions)

    def __len__(self) -> int:
        """Count of registered functions.

        Returns:
            Number of registered functions

        Example:
            >>> registry = FunctionRegistry()
            >>> len(registry)
            0
            >>> registry.register(lambda x: str(x), ftl_name="FUNC")
            >>> len(registry)
            1
        """
        return len(self._functions)

    def __contains__(self, ftl_name: str) -> bool:
        """Check if function is registered using 'in' operator.

        Args:
            ftl_name: Function name from FTL

        Returns:
            True if function is registered

        Example:
            >>> registry = FunctionRegistry()
            >>> registry.register(lambda x: str(x), ftl_name="CUSTOM")
            >>> "CUSTOM" in registry
            True
            >>> "MISSING" in registry
            False
        """
        return ftl_name in self._functions

    def __repr__(self) -> str:
        """Return string representation for debugging.


        Returns:
            String representation showing registered functions

        Example:
            >>> registry = FunctionRegistry()
            >>> repr(registry)
            'FunctionRegistry(functions=0)'
        """
        return f"FunctionRegistry(functions={len(self._functions)})"

    def copy(self) -> FunctionRegistry:
        """Create an unfrozen copy of this registry.

        Returns:
            New FunctionRegistry instance with the same functions.
            The copy is always unfrozen, even if the original was frozen.

        Note:
            FunctionSignature objects are shared between the original and
            copy, but this is safe because FunctionSignature is fully
            immutable (frozen dataclass with immutable tuple for param_mapping).
            Modifications to the registry (adding/removing functions) in
            either copy won't affect the other.

        Example:
            >>> frozen_registry = get_shared_registry()  # Frozen
            >>> my_registry = frozen_registry.copy()  # Unfrozen copy
            >>> my_registry.register(my_custom_func)  # Works!
        """
        new_registry = FunctionRegistry()
        new_registry._functions = self._functions.copy()
        # Note: _frozen is already False from __init__, copy is always unfrozen
        return new_registry

    def should_inject_locale(self, ftl_name: str) -> bool:
        """Check if locale should be injected for this function call.

        This is the canonical way to check locale injection requirements.
        It checks the callable's _ftl_requires_locale attribute, which is
        set by the @fluent_function decorator or _mark_locale_required().

        Args:
            ftl_name: FTL function name (e.g., "NUMBER", "CURRENCY")

        Returns:
            True if locale should be injected, False otherwise.

        Logic:
            1. Check if function exists in registry
            2. Get the callable and check its _ftl_requires_locale attribute
            3. Only inject if the callable has the marker set to True

        Example:
            >>> registry = FunctionRegistry()
            >>> @fluent_function(inject_locale=True)
            ... def my_format(value, locale_code): return str(value)
            >>> registry.register(my_format, ftl_name="MYFORMAT")
            >>> registry.should_inject_locale("MYFORMAT")
            True
        """
        if ftl_name not in self._functions:
            return False

        callable_func = self._functions[ftl_name].callable
        return getattr(callable_func, _FTL_REQUIRES_LOCALE_ATTR, False) is True

    def get_expected_positional_args(self, ftl_name: str) -> int | None:
        """Get expected positional argument count for a built-in function.

        Used for arity validation before locale injection to prevent
        TypeError from incorrect argument positioning.

        For custom functions (not in BUILTIN_FUNCTIONS), returns None
        and the registry allows any number of positional arguments.

        Args:
            ftl_name: FTL function name (e.g., "NUMBER", "CURRENCY")

        Returns:
            Expected positional arg count (from FTL, before locale injection),
            or None if not a built-in function with known arity.

        Example:
            >>> registry = create_default_registry()
            >>> registry.get_expected_positional_args("NUMBER")
            1
            >>> registry.get_expected_positional_args("CUSTOM")
            None
        """
        # Lazy import to avoid circular dependency at module load time
        from ftllexengine.runtime.function_metadata import BUILTIN_FUNCTIONS  # noqa: PLC0415

        metadata = BUILTIN_FUNCTIONS.get(ftl_name)
        return metadata.expected_positional_args if metadata else None

    def get_builtin_metadata(self, ftl_name: str) -> FunctionMetadata | None:
        """Get metadata for a built-in function.

        Args:
            ftl_name: FTL function name (e.g., "NUMBER", "DATETIME")

        Returns:
            FunctionMetadata for built-in functions, None for custom functions.

        Example:
            >>> registry = create_default_registry()
            >>> meta = registry.get_builtin_metadata("NUMBER")
            >>> meta.requires_locale
            True
        """
        # Lazy import to avoid circular dependency at module load time
        from ftllexengine.runtime.function_metadata import BUILTIN_FUNCTIONS  # noqa: PLC0415

        return BUILTIN_FUNCTIONS.get(ftl_name)

    @staticmethod
    def _to_camel_case(snake_case: str) -> str:
        """Convert Python snake_case to FTL camelCase.

        Args:
            snake_case: Python parameter name (e.g., "minimum_fraction_digits")

        Returns:
            FTL parameter name (e.g., "minimumFractionDigits")

        Examples:
            >>> FunctionRegistry._to_camel_case("minimum_fraction_digits")
            'minimumFractionDigits'
            >>> FunctionRegistry._to_camel_case("use_grouping")
            'useGrouping'
            >>> FunctionRegistry._to_camel_case("value")
            'value'
        """
        # Split on underscores
        components = snake_case.split("_")

        # First component stays lowercase, rest are capitalized
        return components[0] + "".join(comp.capitalize() for comp in components[1:])
