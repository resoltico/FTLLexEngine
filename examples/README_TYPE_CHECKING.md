---
afad: "3.3"
version: "0.127.0"
domain: examples
updated: "2026-02-22"
route:
  keywords: [type checking, mypy, strict, threading, examples, stubs]
  questions: ["how to type check examples?", "how to use mypy with examples?", "how to type threading.local?"]
---

# Type Checking Configuration for Examples

This directory includes enhanced type checking configuration for example code.

## Overview

The examples/ directory uses **mypy --strict** mode to demonstrate best practices for type-safe FTL localization code. This includes:

1. **Local mypy configuration** (`mypy.ini`) - Examples-specific type checking settings
2. **Custom type stubs** (`stubs/threading.pyi`) - Enhanced typing for threading.local()

## Usage

### Type-check Examples from Project Root

```bash
# Check all examples with strict typing
python -m mypy examples/ --strict

# Output: Success: no issues found in 11 source files
```

### Type-check Examples from examples/ Directory

```bash
cd examples
python -m mypy .

# Uses examples/mypy.ini configuration automatically
```

## Configuration Files

### examples/mypy.ini

Examples-specific mypy configuration that:
- Enables **strict mode** (demonstrates best practices)
- Uses Python 3.13 features (type aliases, pattern matching)
- Points to local type stubs in `stubs/` directory

**Philosophy**: Examples should demonstrate production-quality type safety.

### examples/stubs/threading.pyi

Custom type stub for `threading` module that provides:
- Enhanced typing for `threading.local()` with dynamic attributes
- Type annotations for `Thread`, `Lock`, `current_thread()`

**Why?**: The standard library's `threading.local()` uses dynamic attributes (set at runtime), which confuses type checkers. Our stub file helps mypy understand the thread-local bundle pattern used in [thread_safety.py](thread_safety.py).

## Thread-Local Typing Example

**Problem**: Standard typing can't track dynamic attributes on threading.local()

```python
thread_local = threading.local()
thread_local.bundle = FluentBundle(...)  # mypy: error - no attribute 'bundle'
return thread_local.bundle  # mypy: error - Returning Any
```

**Solution**: Our `stubs/threading.pyi` provides `__setattr__` and `__getattribute__` stubs

```python
# With our stub file:
thread_local = threading.local()
bundle: FluentBundle = FluentBundle("en", use_isolating=False)
thread_local.bundle = bundle  # mypy understands
return thread_local.bundle  # type: ignore[no-any-return]  # Still needed for return type
```

## Production Recommendation

For production code, prefer **strongly-typed wrappers** instead of dynamic attributes:

```python
from dataclasses import dataclass
import threading

@dataclass
class ThreadLocalState:
    """Strongly-typed thread-local state."""
    bundle: FluentBundle

thread_local: threading.local = threading.local()

def get_bundle() -> FluentBundle:
    """Get bundle for current thread (type-safe)."""
    if not hasattr(thread_local, "state"):
        thread_local.state = ThreadLocalState(
            bundle=FluentBundle("en", use_isolating=False)
        )
    state: ThreadLocalState = thread_local.state
    return state.bundle  # No type: ignore needed!
```

## Why Not Contribute to typeshed?

The `threading.local()` typing challenge is a known limitation in Python's type system:

1. **Dynamic attributes by design** - threading.local() intentionally uses `__setattr__`/`__getattribute__` for thread-isolation
2. **Generic solutions are complex** - Would require Generic[TypedDict] or Protocol, which adds complexity
3. **Production pattern exists** - Strongly-typed wrappers (dataclass pattern above) are the recommended approach

Our local stub is a **pragmatic solution for examples**, showing users how to work with threading.local() while maintaining type safety.

## File Structure

```
examples/
├── mypy.ini                     # Examples-specific mypy config
├── stubs/                       # Local type stubs
│   └── threading.pyi            # threading.local() enhancements
├── README_TYPE_CHECKING.md      # This file
└── *.py                         # Example scripts (all pass mypy --strict)
```

## Verification

All examples pass strict type checking:

```bash
$ python -m mypy examples/ --strict
Success: no issues found in 11 source files
```

All examples execute successfully:

```bash
$ python examples/thread_safety.py
[OK] All thread safety examples complete!
```

## Related Documentation

- [TYPE_HINTS_GUIDE.md](../docs/TYPE_HINTS_GUIDE.md) - Type hints guide for FTLLexEngine
- [thread_safety.py](thread_safety.py) - Thread safety patterns with type hints

---

**Last Updated**: 2026-02-22
**Python Version**: 3.13+
**Mypy Version**: Compatible with latest stable mypy
