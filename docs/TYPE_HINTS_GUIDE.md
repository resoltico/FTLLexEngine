<!--
RETRIEVAL_HINTS:
  keywords: [type hints, typing, mypy, type safety, pep 695, typeis, type guards, annotations]
  answers: [how to use type hints, mypy configuration, type safe code, python typing]
  related: [DOC_02_Types.md, QUICK_REFERENCE.md]
-->
# Type Hints Guide - FTLLexEngine

**Comprehensive guide to using Python 3.13+ type hints with FTLLexEngine**

FTLLexEngine is built with modern Python 3.13+ features and provides full `mypy --strict` type safety. This guide shows how to leverage type hints for better code quality and IDE support.

---

## Quick Start

### Basic Type-Safe Function

```python
from ftllexengine import FluentBundle
from ftllexengine.localization import MessageId

def format_message(bundle: FluentBundle, msg_id: MessageId) -> str:
    """Format message with proper type annotations."""
    result, errors = bundle.format_pattern(msg_id)
    if errors:
        # errors is tuple[FluentError, ...] - fully typed (v0.11.0: immutable)
        for error in errors:
            print(f"Error: {error}")
    return result

# Usage
bundle = FluentBundle("en")
bundle.add_resource("hello = Hello, World!")
output = format_message(bundle, "hello")
```

---

## Python 3.13+ Features in FTLLexEngine

### 1. PEP 695: Type Parameter Syntax (`type` keyword)

FTLLexEngine uses the new `type` keyword for type aliases:

```python
# FTLLexEngine source code (Python 3.13+)
type MessageId = str
type LocaleCode = str
type ResourceId = str
type FTLSource = str
```

**Your Code**:
```python
from ftllexengine.localization import MessageId, LocaleCode, FTLSource

# More descriptive than plain 'str'
def load_translations(locale: LocaleCode, source: FTLSource) -> None:
    bundle = FluentBundle(locale)
    bundle.add_resource(source)
```

**Benefits**:
- Better IDE autocomplete
- Self-documenting code
- Type checker understands intent
- Easier refactoring

---

### 2. PEP 727: TypeIs for Type Guards

FTLLexEngine uses `TypeIs` for runtime type narrowing:

```python
from typing import TypeIs
from ftllexengine import Message, Term, parse_ftl

# Using built-in type guards (v0.9.0: static methods)
ftl_source = "hello = World"
resource = parse_ftl(ftl_source)

for entry in resource.entries:
    if Message.guard(entry):
        # TypeIs narrows type to Message
        print(entry.id.name)  # Type checker knows entry is Message
        print(entry.value)    # Safe access to message-specific attributes

    if Term.guard(entry):
        # TypeIs narrows type to Term
        print(entry.id.name)  # entry is Term here
```

---

### 3. Pattern Matching with Type Safety

Python 3.10+ pattern matching + FTLLexEngine types:

```python
from ftllexengine import parse_ftl, Message, Term, Comment, Junk

resource = parse_ftl(ftl_source)

for entry in resource.entries:
    match entry:
        case Message(id=id_node, value=pattern):
            print(f"Message: {id_node.name}")
            # Pattern matching provides type narrowing
            if pattern:
                print(f"  Value: {pattern}")

        case Term(id=id_node):
            print(f"Term: {id_node.name}")

        case Comment():
            print("Comment found")

        case Junk(content=content):
            print(f"Parse error: {content[:50]}")
```

---

## Type Aliases Reference

### Core Type Aliases

```python
from ftllexengine.localization import MessageId, LocaleCode, ResourceId, FTLSource

# MessageId - Message identifiers
msg_id: MessageId = "welcome"

# LocaleCode - Locale codes
locale: LocaleCode = "en_US"

# ResourceId - Resource file identifiers
resource_id: ResourceId = "main.ftl"

# FTLSource - FTL source strings
ftl_source: FTLSource = "hello = Hello!"
```

**Type Hierarchy**:
```python
# At runtime, all are str
MessageId == str    # True
LocaleCode == str   # True
ResourceId == str   # True
FTLSource == str    # True

# But type checkers treat them distinctly for better errors
def format(msg_id: MessageId) -> str: ...
format("en_US")  # Static type checker error: expected MessageId, got LocaleCode
                 # (At runtime both are str, so this executes fine)
```

---

## Practical Examples

### Example 1: Message Formatter Service

```python
from __future__ import annotations

from ftllexengine import (
    FluentBundle,
    FluentError,
    MessageId,
    LocaleCode,
    FTLSource,
)
import logging

logger = logging.getLogger(__name__)


class MessageFormatter:
    """Type-safe message formatting service."""

    def __init__(self, locale: LocaleCode) -> None:
        """Initialize formatter for locale.

        Args:
            locale: Locale code (e.g., "en_US", "lv_LV")
        """
        self._bundle: FluentBundle = FluentBundle(locale)
        self._locale: LocaleCode = locale

    def load_translations(self, ftl_source: FTLSource) -> None:
        """Load FTL translations into bundle.

        Args:
            ftl_source: FTL source string
        """
        self._bundle.add_resource(ftl_source)

    def format(
        self,
        msg_id: MessageId,
        args: dict[str, object] | None = None,
    ) -> str:
        """Format message with error logging.

        Args:
            msg_id: Message identifier
            args: Variable substitutions

        Returns:
            Formatted message string
        """
        result, errors = self._bundle.format_pattern(msg_id, args)

        if errors:
            self._log_errors(msg_id, errors)

        return result

    def _log_errors(
        self,
        msg_id: MessageId,
        errors: tuple[FluentError, ...],
    ) -> None:
        """Log translation errors.

        Args:
            msg_id: Message that had errors
            errors: Tuple of errors encountered (immutable as of v0.11.0)
        """
        for error in errors:
            logger.warning(
                "Translation error in message %r: %s",
                msg_id,
                error,
                extra={"locale": self._locale},
            )

    @property
    def locale(self) -> LocaleCode:
        """Get current locale."""
        return self._locale


# Usage
formatter = MessageFormatter("en_US")
formatter.load_translations("""
welcome = Hello, { $name }!
""")

message = formatter.format("welcome", {"name": "Alice"})
print(message)  # "Hello, Alice!"
```

---

### Example 2: Multi-Locale Manager with Type Safety

```python
from __future__ import annotations

from collections.abc import Generator
from typing import Protocol

from ftllexengine import (
    FluentBundle,
    FluentLocalization,
    LocaleCode,
    MessageId,
    ResourceId,
    FTLSource,
)


class TranslationLoader(Protocol):
    """Protocol for translation loading systems."""

    def load(self, locale: LocaleCode, resource_id: ResourceId) -> FTLSource:
        """Load FTL resource for locale.

        Args:
            locale: Locale code
            resource_id: Resource identifier

        Returns:
            FTL source content
        """
        ...


class LocalizationManager:
    """Type-safe multi-locale manager."""

    def __init__(
        self,
        locales: list[LocaleCode],
        loader: TranslationLoader,
    ) -> None:
        """Initialize manager.

        Args:
            locales: Locale codes in fallback order
            loader: Translation loading system
        """
        self._locales: tuple[LocaleCode, ...] = tuple(locales)
        self._loader: TranslationLoader = loader
        self._l10n: FluentLocalization | None = None

    def initialize(self, resource_ids: list[ResourceId]) -> None:
        """Load all resources.

        Args:
            resource_ids: List of resource file identifiers
        """
        self._l10n = FluentLocalization(
            self._locales,
            resource_ids,
            self._loader,
        )

    def translate(
        self,
        msg_id: MessageId,
        args: dict[str, object] | None = None,
    ) -> str:
        """Translate message with fallback.

        Args:
            msg_id: Message identifier
            args: Variable substitutions

        Returns:
            Translated message

        Raises:
            RuntimeError: If not initialized
        """
        if self._l10n is None:
            raise RuntimeError("Manager not initialized")

        result, errors = self._l10n.format_value(msg_id, args)

        if errors:
            # Handle errors (log, report, etc.)
            pass

        return result

    def has_translation(self, msg_id: MessageId) -> bool:
        """Check if message exists in any locale.

        Args:
            msg_id: Message identifier

        Returns:
            True if message exists
        """
        if self._l10n is None:
            return False

        return self._l10n.has_message(msg_id)

    def get_bundles(self) -> Generator[FluentBundle, None, None]:
        """Get all bundles in fallback order.

        Yields:
            FluentBundle instances

        Raises:
            RuntimeError: If not initialized
        """
        if self._l10n is None:
            raise RuntimeError("Manager not initialized")

        yield from self._l10n.get_bundles()
```

---

### Example 3: Custom Function with Full Type Safety

```python
from __future__ import annotations

from ftllexengine import FluentBundle
from ftllexengine.runtime.functions import create_default_registry
from typing import Literal

# Python 3.13+ with precise types
def format_currency(
    amount: float | int,
    *,
    currency_code: Literal["USD", "EUR", "GBP", "JPY"] = "USD",
    show_symbol: bool = True,
) -> str:
    """Format currency with type-safe currency codes.

    Args:
        amount: Monetary amount
        currency_code: ISO currency code (limited set)
        show_symbol: Include currency symbol

    Returns:
        Formatted currency string
    """
    symbols: dict[str, str] = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
    }

    symbol = symbols[currency_code] if show_symbol else currency_code
    return f"{symbol}{amount:,.2f}"


# Create isolated registry and register function
registry = create_default_registry()
registry.register(
    format_currency,
    ftl_name="CURRENCY",
    param_map={
        "currencyCode": "currency_code",
        "showSymbol": "show_symbol",
    },
)

# Type-safe usage with custom registry
bundle: FluentBundle = FluentBundle("en", functions=registry)
bundle.add_resource("""
price = { CURRENCY($amount, currencyCode: "EUR") }
""")

result, _ = bundle.format_pattern("price", {"amount": 99.95})
```

---

### Example 4: AST Visitor with Type Guards

```python
from __future__ import annotations

from ftllexengine import (
    ASTVisitor,
    Message,
    Term,
    VariableReference,
    FunctionReference,
    parse_ftl,
)


class VariableCollector(ASTVisitor):
    """Collect all variables from FTL source with type safety."""

    def __init__(self) -> None:
        """Initialize collector."""
        super().__init__()
        self.variables: set[str] = set()
        self.current_message: str | None = None

    def visit_Message(self, node: Message) -> None:
        """Visit message node.

        Args:
            node: Message AST node
        """
        self.current_message = node.id.name
        super().visit_Message(node)
        self.current_message = None

    def visit_VariableReference(self, node: VariableReference) -> None:
        """Collect variable reference.

        Args:
            node: VariableReference AST node
        """
        self.variables.add(node.id.name)
        super().visit_VariableReference(node)


# Usage with type checking
ftl_source = """
welcome = Hello, { $name }!
farewell = Goodbye, { $firstName } { $lastName }!
"""

resource = parse_ftl(ftl_source)
collector = VariableCollector()
collector.visit(resource)

# Type checker knows variables is set[str]
all_vars: set[str] = collector.variables
print(f"Found variables: {sorted(all_vars)}")
# → Found variables: ['firstName', 'lastName', 'name']
```

---

## Type-Safe Error Handling

### Pattern 1: Exhaustive Error Handling

```python
from ftllexengine import (
    FluentError,
    FluentReferenceError,
    FluentResolutionError,
    FluentCyclicReferenceError,
)


def handle_errors(errors: tuple[FluentError, ...]) -> None:
    """Handle translation errors with exhaustive matching.

    Args:
        errors: Tuple of errors from formatting (immutable as of v0.11.0)
    """
    for error in errors:
        match error:
            case FluentReferenceError():
                # Missing message, variable, or term
                print(f"Reference error: {error}")

            case FluentResolutionError():
                # Runtime error during function execution
                print(f"Resolution error: {error}")

            case FluentCyclicReferenceError():
                # Circular dependency detected
                print(f"Circular reference: {error}")

            case FluentError():
                # Catch-all for future error types
                print(f"Unknown error: {error}")
```

---

### Pattern 2: Type-Safe Error Categorization

```python
from __future__ import annotations

from dataclasses import dataclass
from ftllexengine import FluentError, FluentReferenceError


@dataclass(frozen=True, slots=True)
class ErrorReport:
    """Type-safe error categorization."""

    critical: tuple[FluentError, ...]
    warnings: tuple[FluentError, ...]

    @classmethod
    def from_errors(cls, errors: tuple[FluentError, ...]) -> ErrorReport:
        """Categorize errors by severity.

        Args:
            errors: Tuple of translation errors (immutable as of v0.11.0)

        Returns:
            Categorized error report
        """
        critical_list: list[FluentError] = []
        warnings_list: list[FluentError] = []

        for error in errors:
            if isinstance(error, FluentReferenceError):
                critical_list.append(error)
            else:
                warnings_list.append(error)

        return cls(critical=tuple(critical_list), warnings=tuple(warnings_list))

    @property
    def has_critical(self) -> bool:
        """Check if critical errors exist."""
        return len(self.critical) > 0

    @property
    def error_count(self) -> int:
        """Total error count."""
        return len(self.critical) + len(self.warnings)
```

---

## Advanced Type Patterns

### Generic Wrapper for Bundles

```python
from __future__ import annotations

from typing import Generic, TypeVar
from ftllexengine import FluentBundle
from ftllexengine.localization import MessageId

T = TypeVar("T")


class TypedBundle(Generic[T]):
    """Type-safe wrapper for FluentBundle with custom context.

    This pattern allows attaching typed metadata to bundles.
    """

    def __init__(self, bundle: FluentBundle, context: T) -> None:
        """Initialize typed bundle.

        Args:
            bundle: FluentBundle instance
            context: Custom context data
        """
        self._bundle: FluentBundle = bundle
        self._context: T = context

    @property
    def bundle(self) -> FluentBundle:
        """Get underlying bundle."""
        return self._bundle

    @property
    def context(self) -> T:
        """Get typed context."""
        return self._context

    def format(self, msg_id: MessageId, args: dict[str, object] | None = None) -> str:
        """Format message.

        Args:
            msg_id: Message identifier
            args: Variable substitutions

        Returns:
            Formatted string
        """
        result, _ = self._bundle.format_pattern(msg_id, args)
        return result


# Usage with typed context
@dataclass
class UserContext:
    """User-specific localization context."""

    user_id: int
    timezone: str
    date_format: str


user_ctx = UserContext(user_id=123, timezone="America/New_York", date_format="MM/DD/YYYY")
bundle = FluentBundle("en_US")

typed_bundle: TypedBundle[UserContext] = TypedBundle(bundle, user_ctx)

# Type checker knows context is UserContext
print(typed_bundle.context.timezone)  # Type-safe access
```

---

## mypy Configuration

For maximum type safety with FTLLexEngine:

```ini
# mypy.ini or pyproject.toml [tool.mypy]
[mypy]
python_version = 3.13
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_any_generics = true

# FTLLexEngine is fully typed
[mypy-ftllexengine]
ignore_missing_imports = false
```

---

## Type Checking Best Practices

### DO: Use Type Aliases

```python
from ftllexengine.localization import MessageId, LocaleCode

# ✅ Good - descriptive types
def format_message(msg_id: MessageId, locale: LocaleCode) -> str:
    ...

# ❌ Less clear - generic str
def format_message(msg_id: str, locale: str) -> str:
    ...
```

---

### DO: Annotate Return Types

```python
from ftllexengine import FluentBundle

# ✅ Good - explicit return type
def create_bundle(locale: str) -> FluentBundle:
    return FluentBundle(locale)

# ❌ Less safe - inferred return type
def create_bundle(locale: str):
    return FluentBundle(locale)
```

---

### DO: Use Type Guards for AST

```python
from ftllexengine import parse_ftl, Message

resource = parse_ftl(ftl_source)

for entry in resource.entries:
    # ✅ Good - type guard provides narrowing (v0.9.0: static method)
    if Message.guard(entry):
        # entry is Message here
        print(entry.value)

    # ✅ Also correct - isinstance() works fine
    if isinstance(entry, Message):
        # Type checker narrows to Message here too
        print(entry.value)
    # Note: Message.guard() is preferred for FTLLexEngine style consistency
```

---

### DO: Use dict[K, V] Syntax (Python 3.9+)

```python
# ✅ Good - modern syntax (Python 3.9+)
def format(msg_id: str, args: dict[str, object]) -> str:
    ...

# ❌ Old - deprecated typing.Dict
from typing import Dict
def format(msg_id: str, args: Dict[str, object]) -> str:
    ...
```

---

## Troubleshooting Type Errors

### Error: "Argument has incompatible type"

```python
# ❌ Type error
locale_codes: list[LocaleCode] = ["en", "fr"]
bundle = FluentBundle(locale_codes)  # Error: expected str, got list

# ✅ Fixed - extract single locale
bundle = FluentBundle(locale_codes[0])
```

---

### Error: "Item 'None' of 'Optional[...]' has no attribute"

```python
from ftllexengine import parse_ftl, Message

resource = parse_ftl(ftl_source)
msg = resource.entries[0]

# ❌ Type error - entry might not be Message
print(msg.value)  # Error: entry could be Term, Comment, Junk

# ✅ Fixed - use type guard (v0.9.0: static method)
if Message.guard(msg):
    print(msg.value)  # Safe - type narrowed to Message
```

---

## Summary

**FTLLexEngine provides**:
- Full `mypy --strict` compatibility
- Python 3.13+ modern type features
- Type aliases for clarity
- Type guards for runtime narrowing
- Complete type annotations

**Best practices**:
- Use provided type aliases (`MessageId`, `LocaleCode`, etc.)
- Annotate function return types
- Use type guards for AST manipulation
- Enable `mypy --strict` in your project
- Leverage Python 3.13+ features

---

**Type Hints Guide Last Updated**: December 23, 2025
**FTLLexEngine Version**: 0.38.0
**Python Version**: 3.13+

**See Also**:
- [DOC_00_Index.md](DOC_00_Index.md) - Complete API reference
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Quick examples
- [examples/](../examples/) - Working code samples
