"""Parsing error template composition."""

from __future__ import annotations

from .template_parsing_currency import _ParsingCurrencyErrorTemplateMixin
from .template_parsing_input import _ParsingInputErrorTemplateMixin


class _ParsingErrorTemplateMixin(
    _ParsingCurrencyErrorTemplateMixin,
    _ParsingInputErrorTemplateMixin,
):
    """Compose parsing diagnostic template families into one mixin."""
