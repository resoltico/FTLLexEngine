"""Runtime error template composition.

Premise:
    Runtime diagnostics cover two distinct concerns: function-boundary
    failures and resolver/runtime-state failures.

Reason:
    Keeping the small composition owner here lets the focused mixin modules
    stay below the architecture line budget while the public import surface
    remains unchanged.
"""

from __future__ import annotations

from .template_runtime_functions import _RuntimeFunctionErrorTemplateMixin
from .template_runtime_state import _RuntimeStateErrorTemplateMixin


class _RuntimeErrorTemplateMixin(
    _RuntimeFunctionErrorTemplateMixin,
    _RuntimeStateErrorTemplateMixin,
):
    """Compose the runtime diagnostic template families into one mixin."""
