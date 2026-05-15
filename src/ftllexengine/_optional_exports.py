"""Canonical owner for Babel-backed facade exports.

Facade modules derive their optional ``__all__`` entries, lazy attribute
resolution, and parser-only diagnostics from the definitions in this module.
Zero-dependency symbols should be imported directly by their facades instead of
being routed through this helper.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

from ftllexengine.core.babel_compat import BabelImportError

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
    stub_kind: str = "class"


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
            source_module="ftllexengine.localization.cache_stats",
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
            source_module="ftllexengine.localization.cache_stats",
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
            stub_kind="callable",
        ),
        OptionalFacadeExport(
            public_name="currency_format",
            source_module="ftllexengine.runtime.functions",
            source_name="currency_format",
            stub_kind="callable",
        ),
        OptionalFacadeExport(
            public_name="datetime_format",
            source_module="ftllexengine.runtime.functions",
            source_name="datetime_format",
            stub_kind="callable",
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
            stub_kind="callable",
        ),
        OptionalFacadeExport(
            public_name="number_format",
            source_module="ftllexengine.runtime.functions",
            source_name="number_format",
            stub_kind="callable",
        ),
        OptionalFacadeExport(
            public_name="select_plural_category",
            source_module="ftllexengine.runtime.plural_rules",
            source_name="select_plural_category",
            stub_kind="callable",
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
    export = _optional_export(module_name, name)
    module = import_module(export.source_module)
    return getattr(module, export.source_name)


def _optional_export(module_name: str, name: str) -> OptionalFacadeExport:
    """Return the export contract for one optional public name."""
    for export in _optional_exports_for(module_name):
        if export.public_name == name:
            return export
    msg = f"module {module_name!r} has no optional Babel export {name!r}"
    raise AttributeError(msg)


def _missing_babel_message(name: str, parser_only_hint: str | None) -> str:
    """Build the user-facing missing-Babel message for one symbol."""
    error = BabelImportError(name)
    message = str(error)
    if parser_only_hint is not None:
        return f"{message}\n\n{parser_only_hint}"
    return message


def _build_missing_babel_function(name: str, parser_only_hint: str | None) -> object:
    """Create a callable placeholder that fails with BabelImportError when used."""
    message = _missing_babel_message(name, parser_only_hint)

    def _missing(*_args: object, **_kwargs: object) -> object:
        error = BabelImportError(name)
        error.args = (message,)
        raise error

    _missing.__name__ = name
    _missing.__qualname__ = name
    _missing.__doc__ = message
    return _missing


def _build_missing_babel_class(name: str, parser_only_hint: str | None) -> object:
    """Create a class placeholder that fails with BabelImportError when instantiated."""
    message = _missing_babel_message(name, parser_only_hint)

    def _raise_on_new(_cls: type[object], *_args: object, **_kwargs: object) -> object:
        error = BabelImportError(name)
        error.args = (message,)
        raise error

    return type(
        name,
        (),
        {
            "__doc__": message,
            "__new__": staticmethod(_raise_on_new),
        },
    )


def raise_missing_babel_symbol(
    *,
    module_name: str,
    name: str,
    optional_attrs: frozenset[str],
    parser_only_hint: str | None = None,
) -> object:
    """Return a helpful placeholder for one Babel-backed optional symbol.

    Module attribute access uses ``AttributeError`` so Python feature probes
    such as ``hasattr()`` and ``getattr(..., default)`` treat unknown names as
    absent. Optional runtime names resolve to explicit placeholders so import
    statements can surface a useful Babel installation error when the symbol is
    actually used.
    """
    if name in optional_attrs:
        export = _optional_export(module_name, name)
        if export.stub_kind == "callable":
            return _build_missing_babel_function(name, parser_only_hint)
        return _build_missing_babel_class(name, parser_only_hint)

    message = f"module {module_name!r} has no attribute {name!r}"
    raise AttributeError(message)
