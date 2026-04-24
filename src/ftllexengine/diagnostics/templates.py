"""Error message templates.

Centralized error message templates for testable, consistent error messages.
Python 3.13+. Zero external dependencies.
"""

from .template_parsing import _ParsingErrorTemplateMixin
from .template_reference import _ReferenceErrorTemplateMixin
from .template_runtime import _RuntimeErrorTemplateMixin

__all__ = ["ErrorTemplate"]


class ErrorTemplate(
    _ReferenceErrorTemplateMixin,
    _RuntimeErrorTemplateMixin,
    _ParsingErrorTemplateMixin,
):
    """Centralized error message templates.

    All error messages are created here. NO f-strings in exception constructors!
    This solves EM101/EM102 violations while providing:
        - Testable error messages
        - Consistent formatting
        - Easy i18n in the future
        - Documentation of all error cases
    """
