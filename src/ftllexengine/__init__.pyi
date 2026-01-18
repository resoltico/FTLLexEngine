"""Type stubs for ftllexengine package.

This stub file declares types for lazy-loaded attributes and re-exported symbols.
Mypy cannot infer types from __getattr__, so explicit declarations are required.
"""

from .diagnostics import (
    FluentError as FluentError,
)
from .diagnostics import (
    FluentReferenceError as FluentReferenceError,
)
from .diagnostics import (
    FluentResolutionError as FluentResolutionError,
)
from .localization import FluentLocalization as FluentLocalization
from .runtime import FluentBundle as FluentBundle
from .runtime.function_bridge import FluentValue as FluentValue
from .runtime.function_bridge import fluent_function as fluent_function
from .syntax import parse as parse_ftl
from .syntax import serialize as serialize_ftl

# Version and specification information
__version__: str
__fluent_spec_version__: str
__spec_url__: str
__recommended_encoding__: str

# Explicit __all__ for mypy to recognize re-exports
__all__: list[str] = [
    "FluentBundle",
    "FluentError",
    "FluentLocalization",
    "FluentReferenceError",
    "FluentResolutionError",
    "FluentValue",
    "__fluent_spec_version__",
    "__recommended_encoding__",
    "__spec_url__",
    "__version__",
    "fluent_function",
    "parse_ftl",
    "serialize_ftl",
]
