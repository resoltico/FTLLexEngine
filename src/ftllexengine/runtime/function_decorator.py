"""Decorator helpers for Fluent-callable functions."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import overload

from ftllexengine.core.value_types import FluentValue

_FTL_REQUIRES_LOCALE_ATTR: str = "_ftl_requires_locale"

__all__ = ["_FTL_REQUIRES_LOCALE_ATTR", "fluent_function"]


@overload
def fluent_function[F: Callable[..., FluentValue]](  # pragma: no cover
    func: F,
    *,
    inject_locale: bool = False,
) -> F: ...


@overload
def fluent_function[F: Callable[..., FluentValue]](  # pragma: no cover
    func: None = None,
    *,
    inject_locale: bool = False,
) -> Callable[[F], F]: ...


def fluent_function[F: Callable[..., FluentValue]](
    func: F | None = None,
    *,
    inject_locale: bool = False,
) -> F | Callable[[F], F]:
    """Decorator for marking custom functions with Fluent metadata."""

    def decorator(fn: F) -> F:
        if inject_locale:
            @wraps(fn)
            def wrapper(*args: object, **kwargs: object) -> FluentValue:
                return fn(*args, **kwargs)

            setattr(wrapper, _FTL_REQUIRES_LOCALE_ATTR, True)
            return wrapper  # type: ignore[return-value]

        return fn

    if func is not None:
        return decorator(func)
    return decorator
