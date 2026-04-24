"""Helper functions for FunctionRegistry registration and dispatch."""

from __future__ import annotations

from inspect import Parameter, signature
from typing import TYPE_CHECKING

from ftllexengine.diagnostics import ErrorCategory, ErrorTemplate, FrozenFluentError

from .function_decorator import _FTL_REQUIRES_LOCALE_ATTR
from .value_types import FunctionSignature

__all__ = ["build_function_signature", "call_registered_function", "to_camel_case"]

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from ftllexengine.core.value_types import FluentValue


def to_camel_case(snake_case: str) -> str:
    """Convert Python snake_case to FTL camelCase."""
    components = snake_case.split("_")
    return components[0] + "".join(comp.capitalize() for comp in components[1:])


def build_function_signature(
    func: Callable[..., FluentValue],
    *,
    ftl_name: str | None = None,
    param_map: dict[str, str] | None = None,
) -> FunctionSignature:
    """Build immutable registration metadata for one callable."""
    if ftl_name is None:
        ftl_name = getattr(func, "__name__", "unknown").upper()

    try:
        sig = signature(func)
    except ValueError as e:
        msg = (
            f"Cannot register '{ftl_name}': callable has no inspectable signature. "
            f"Use param_mapping parameter to provide explicit mappings. Error: {e}"
        )
        raise TypeError(msg) from e

    if getattr(func, _FTL_REQUIRES_LOCALE_ATTR, False):
        positional_capable = [
            p
            for p in sig.parameters.values()
            if p.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
            and p.name != "self"
        ]
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
        if param_name in ("self", "/", "*"):
            continue

        stripped_name = param_name.lstrip("_")
        camel_case = to_camel_case(stripped_name)

        if camel_case in auto_map and auto_map[camel_case] != param_name:
            msg = (
                f"Parameter name collision in function '{ftl_name}': "
                f"'{auto_map[camel_case]}' and '{param_name}' both map to FTL "
                f"parameter '{camel_case}'"
            )
            raise ValueError(msg)

        auto_map[camel_case] = param_name

    final_map = {**auto_map, **(param_map or {})}
    immutable_mapping = tuple(sorted(final_map.items()))

    return FunctionSignature(
        python_name=getattr(func, "__name__", "unknown"),
        ftl_name=ftl_name,
        param_mapping=immutable_mapping,
        callable=func,
    )


def call_registered_function(
    func_sig: FunctionSignature,
    *,
    ftl_name: str,
    positional: Sequence[FluentValue],
    named: Mapping[str, FluentValue],
) -> FluentValue:
    """Call a registered function signature with FTL-style named arguments."""
    python_kwargs = {}
    for ftl_param, value in named.items():
        python_param = func_sig.param_dict.get(ftl_param, ftl_param)
        python_kwargs[python_param] = value

    try:
        return func_sig.callable(*positional, **python_kwargs)
    except (TypeError, ValueError) as e:
        diag = ErrorTemplate.function_failed(ftl_name, str(e))
        raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag) from e
