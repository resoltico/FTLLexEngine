"""Canonical owner for Babel-backed facade exports.

Facade modules derive their optional ``__all__`` entries, lazy attribute
resolution, and parser-only diagnostics from the definitions in this module.
Zero-dependency symbols should be imported directly by their facades instead of
being routed through this helper.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import NoReturn

__all__ = [
    "OptionalFacadeExport",
    "babel_optional_attr_set",
    "babel_optional_attr_tuple",
    "load_babel_optional_export",
    "raise_missing_babel_symbol",
]


@dataclass(frozen=True, slots=True)
class OptionalFacadeExport:
    """One Babel-backed export owned by a public facade."""

    public_name: str
    source_module: str
    source_name: str


_OPTIONAL_EXPORTS_BY_FACADE: dict[str, tuple[OptionalFacadeExport, ...]] = {
    "ftllexengine": (
        OptionalFacadeExport(
            public_name="AsyncFluentBundle",
            source_module="ftllexengine.runtime.async_bundle",
            source_name="AsyncFluentBundle",
        ),
        OptionalFacadeExport(
            public_name="FluentBundle",
            source_module="ftllexengine.runtime.bundle",
            source_name="FluentBundle",
        ),
        OptionalFacadeExport(
            public_name="FluentLocalization",
            source_module="ftllexengine.localization.orchestrator",
            source_name="FluentLocalization",
        ),
        OptionalFacadeExport(
            public_name="LocalizationBootConfig",
            source_module="ftllexengine.localization.boot",
            source_name="LocalizationBootConfig",
        ),
        OptionalFacadeExport(
            public_name="LocalizationCacheStats",
            source_module="ftllexengine.localization.orchestrator",
            source_name="LocalizationCacheStats",
        ),
    ),
    "ftllexengine.localization": (
        OptionalFacadeExport(
            public_name="FluentLocalization",
            source_module="ftllexengine.localization.orchestrator",
            source_name="FluentLocalization",
        ),
        OptionalFacadeExport(
            public_name="LocalizationBootConfig",
            source_module="ftllexengine.localization.boot",
            source_name="LocalizationBootConfig",
        ),
        OptionalFacadeExport(
            public_name="LocalizationCacheStats",
            source_module="ftllexengine.localization.orchestrator",
            source_name="LocalizationCacheStats",
        ),
    ),
    "ftllexengine.runtime": (
        OptionalFacadeExport(
            public_name="AsyncFluentBundle",
            source_module="ftllexengine.runtime.async_bundle",
            source_name="AsyncFluentBundle",
        ),
        OptionalFacadeExport(
            public_name="create_default_registry",
            source_module="ftllexengine.runtime.functions",
            source_name="create_default_registry",
        ),
        OptionalFacadeExport(
            public_name="currency_format",
            source_module="ftllexengine.runtime.functions",
            source_name="currency_format",
        ),
        OptionalFacadeExport(
            public_name="datetime_format",
            source_module="ftllexengine.runtime.functions",
            source_name="datetime_format",
        ),
        OptionalFacadeExport(
            public_name="FluentBundle",
            source_module="ftllexengine.runtime.bundle",
            source_name="FluentBundle",
        ),
        OptionalFacadeExport(
            public_name="get_shared_registry",
            source_module="ftllexengine.runtime.functions",
            source_name="get_shared_registry",
        ),
        OptionalFacadeExport(
            public_name="number_format",
            source_module="ftllexengine.runtime.functions",
            source_name="number_format",
        ),
        OptionalFacadeExport(
            public_name="select_plural_category",
            source_module="ftllexengine.runtime.plural_rules",
            source_name="select_plural_category",
        ),
    ),
}


def _optional_exports_for(module_name: str) -> tuple[OptionalFacadeExport, ...]:
    """Return the canonical optional-export definitions for one facade."""
    exports = _OPTIONAL_EXPORTS_BY_FACADE.get(module_name)
    if exports is None:
        msg = f"No optional export contract registered for facade {module_name!r}"
        raise KeyError(msg)
    return exports


def babel_optional_attr_tuple(module_name: str) -> tuple[str, ...]:
    """Return Babel-backed public names for one facade in canonical order."""
    return tuple(export.public_name for export in _optional_exports_for(module_name))


def babel_optional_attr_set(module_name: str) -> frozenset[str]:
    """Return Babel-backed public names for one facade as a set."""
    return frozenset(babel_optional_attr_tuple(module_name))


def load_babel_optional_export(module_name: str, name: str) -> object:
    """Resolve one Babel-backed export from the canonical facade contract."""
    for export in _optional_exports_for(module_name):
        if export.public_name == name:
            module = import_module(export.source_module)
            return getattr(module, export.source_name)
    msg = f"module {module_name!r} has no optional Babel export {name!r}"
    raise AttributeError(msg)


def raise_missing_babel_symbol(
    *,
    module_name: str,
    name: str,
    optional_attrs: frozenset[str],
    parser_only_hint: str | None = None,
) -> NoReturn:
    """Raise a helpful AttributeError for a Babel-backed optional symbol.

    Module attribute access uses ``AttributeError`` so Python feature probes
    such as ``hasattr()`` and ``getattr(..., default)`` treat the symbol as
    absent in parser-only installs.
    """
    if name in optional_attrs:
        message = (
            f"{name} requires the full runtime install (Babel + CLDR locale data). "
            "Install with: pip install ftllexengine[babel]"
        )
        if parser_only_hint is not None:
            message = f"{message}\n\n{parser_only_hint}"
        raise AttributeError(message)

    message = f"module {module_name!r} has no attribute {name!r}"
    raise AttributeError(message)
