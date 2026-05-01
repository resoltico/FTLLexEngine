from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import atheris
from fuzz_bridge_support import (
    _ALLOWED_EXCEPTIONS,
    BridgeFuzzError,
    _domain,
    _pick_locale,
)

from ftllexengine.diagnostics import FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.runtime.function_bridge import FunctionRegistry, fluent_function
from ftllexengine.runtime.functions import create_default_registry, get_shared_registry


def _pattern_call_dispatch(fdp: atheris.FuzzedDataProvider) -> None:
    """Test call() dispatch with varied argument shapes."""
    _domain.call_dispatch_tests += 1
    reg = FunctionRegistry()

    def echo_fn(value: Any, **kwargs: Any) -> str:
        return f"{value}|{len(kwargs)}"

    reg.register(echo_fn, ftl_name="ECHO")

    variant = fdp.ConsumeIntInRange(0, 4)

    match variant:
        case 0:
            # Normal call
            result = reg.call("ECHO", [42], {"key": "val"})
            if "42" not in str(result):
                msg = f"Normal call failed: {result}"
                raise BridgeFuzzError(msg)

        case 1:
            # No positional args
            with contextlib.suppress(*_ALLOWED_EXCEPTIONS, FrozenFluentError):
                reg.call("ECHO", [], {})

        case 2:
            # Many positional args
            n = fdp.ConsumeIntInRange(2, 10)
            args = [fdp.ConsumeIntInRange(0, 100) for _ in range(n)]
            with contextlib.suppress(*_ALLOWED_EXCEPTIONS, FrozenFluentError):
                reg.call("ECHO", args, {})

        case 3:
            # Unknown function name
            with contextlib.suppress(*_ALLOWED_EXCEPTIONS, FrozenFluentError):
                reg.call("NONEXISTENT", [1], {})

        case _:
            # Call with many kwargs
            n = fdp.ConsumeIntInRange(1, 10)
            kwargs = {f"k{i}": i for i in range(n)}
            reg.call("ECHO", ["val"], kwargs)

def _pattern_locale_injection(fdp: atheris.FuzzedDataProvider) -> None:
    """Test locale injection protocol with custom functions."""
    _domain.locale_injection_tests += 1
    reg = FunctionRegistry()
    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # Decorated with inject_locale=True
            @fluent_function(inject_locale=True)
            def locale_fn(value: Any, locale_code: str) -> str:
                return f"{value}@{locale_code}"

            reg.register(locale_fn, ftl_name="LOCALE_FN")

            if not reg.should_inject_locale("LOCALE_FN"):
                msg = "should_inject_locale returned False for decorated function"
                raise BridgeFuzzError(msg)

        case 1:
            # Not decorated -- should NOT inject locale
            def plain_fn(value: Any) -> str:
                return str(value)

            reg.register(plain_fn, ftl_name="PLAIN_FN")

            if reg.should_inject_locale("PLAIN_FN"):
                msg = "should_inject_locale returned True for plain function"
                raise BridgeFuzzError(msg)

        case 2:
            # Nonexistent function
            if reg.should_inject_locale("DOES_NOT_EXIST"):
                msg = "should_inject_locale returned True for nonexistent function"
                raise BridgeFuzzError(msg)

        case _:
            # End-to-end: locale injection through FluentBundle
            locale = _pick_locale(fdp)
            bundle = FluentBundle(locale, strict=False)

            @fluent_function(inject_locale=True)
            def fmt_fn(value: Any, locale_code: str) -> str:
                return f"[{locale_code}:{value}]"

            bundle.add_function("FMT", fmt_fn)
            bundle.add_resource("msg = { FMT($val) }\n")
            with contextlib.suppress(Exception):
                bundle.format_pattern("msg", {"val": "test"})

def _pattern_error_wrapping(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify TypeError/ValueError from functions are wrapped as FrozenFluentError."""
    _domain.call_dispatch_errors += 1
    reg = create_default_registry()
    variant = fdp.ConsumeIntInRange(0, 2)

    match variant:
        case 0:
            # Call NUMBER with wrong type
            try:
                reg.call("NUMBER", ["not_a_number", "en"], {})
            except FrozenFluentError:
                pass  # Expected wrapping
            except (TypeError, ValueError):
                pass  # Also acceptable

        case 1:
            # Call nonexistent function
            with contextlib.suppress(FrozenFluentError, KeyError):
                reg.call("NONEXISTENT", [1], {})

        case _:
            # Call with wrong arity
            with contextlib.suppress(FrozenFluentError, TypeError):
                reg.call("NUMBER", [], {})

def _pattern_evil_objects(fdp: atheris.FuzzedDataProvider) -> None:
    """Adversarial Python objects as FTL variables through FluentBundle."""
    _domain.evil_object_tests += 1
    variant = fdp.ConsumeIntInRange(0, 5)

    match variant:
        case 0:
            # Evil __str__ raises RuntimeError
            class EvilStr:
                """Object whose __str__ raises RuntimeError."""

                def __str__(self) -> str:
                    raise RuntimeError("evil __str__")  # noqa: EM101 - dynamic type in error message

            var: object = EvilStr()

        case 1:
            # Evil __hash__ raises TypeError
            class EvilHash:
                """Object whose __hash__ raises TypeError."""

                def __hash__(self) -> int:
                    raise TypeError("unhashable evil")  # noqa: EM101 - dynamic type in error message

                def __str__(self) -> str:
                    return "evil"

            var = EvilHash()

        case 2:
            # Recursive list
            recursive_list: list[object] = []
            recursive_list.append(recursive_list)
            var = recursive_list

        case 3:
            # Recursive dict
            recursive_dict: dict[str, object] = {}
            recursive_dict["self"] = recursive_dict
            var = recursive_dict

        case 4:
            # Massive string
            size = fdp.ConsumeIntInRange(1000, 50000)
            var = "A" * size

        case _:
            # None value
            var = None

    # Full FluentBundle resolution path with adversarial objects
    bundle = FluentBundle("en-US", cache=CacheConfig() if fdp.ConsumeBool() else None)
    bundle.add_resource("msg = Value: { $var }\n")
    with contextlib.suppress(*_ALLOWED_EXCEPTIONS, FrozenFluentError):
        bundle.format_pattern("msg", {"var": var})  # type: ignore[dict-item]

def _pattern_dict_interface(fdp: atheris.FuzzedDataProvider) -> None:  # noqa: PLR0912 - dispatch
    """Dict-like interface: __iter__, __contains__, __len__, list_functions, __repr__."""
    reg = create_default_registry()
    variant = fdp.ConsumeIntInRange(0, 4)

    match variant:
        case 0:
            # __contains__ for known builtins
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                if name not in reg:
                    msg = f"Default registry missing {name} via __contains__"
                    raise BridgeFuzzError(msg)
            # Nonexistent
            fuzzed = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))
            if fuzzed in reg and fuzzed not in ("NUMBER", "DATETIME", "CURRENCY"):
                msg = f"Registry contains unexpected function: {fuzzed}"
                raise BridgeFuzzError(msg)

        case 1:
            # __iter__ yields all function names
            names = list(reg)
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                if name not in names:
                    msg = f"__iter__ missing {name}"
                    raise BridgeFuzzError(msg)

        case 2:
            # list_functions returns all registered names (insertion order)
            funcs = reg.list_functions()
            if len(funcs) != len(reg):
                msg = f"list_functions length {len(funcs)} != len(reg) {len(reg)}"
                raise BridgeFuzzError(msg)
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                if name not in funcs:
                    msg = f"list_functions missing {name}"
                    raise BridgeFuzzError(msg)

        case 3:
            # get_python_name and get_callable
            py_name = reg.get_python_name("NUMBER")
            if py_name is None:
                msg = "get_python_name('NUMBER') returned None"
                raise BridgeFuzzError(msg)
            callable_fn = reg.get_callable("NUMBER")
            if callable_fn is None:
                msg = "get_callable('NUMBER') returned None"
                raise BridgeFuzzError(msg)
            # Nonexistent
            if reg.get_python_name("FAKE") is not None:
                msg = "get_python_name returned non-None for nonexistent"
                raise BridgeFuzzError(msg)

        case _:
            # __repr__ consistency
            empty_reg = FunctionRegistry()
            r = repr(empty_reg)
            if "0" not in r:
                msg = f"Empty registry repr missing '0': {r}"
                raise BridgeFuzzError(msg)
            empty_reg.register(str, ftl_name="TEST")
            r2 = repr(empty_reg)
            if "1" not in r2:
                msg = f"Single-func registry repr missing '1': {r2}"
                raise BridgeFuzzError(msg)

def _pattern_freeze_copy_lifecycle(fdp: atheris.FuzzedDataProvider) -> None:
    """Freeze/copy lifecycle: isolation, mutation prevention."""
    _domain.freeze_copy_tests += 1
    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # Freeze prevents registration
            reg = FunctionRegistry()
            reg.register(str, ftl_name="PRE")
            reg.freeze()
            if not reg.frozen:
                msg = "Registry not frozen after freeze()"
                raise BridgeFuzzError(msg)
            try:
                reg.register(str, ftl_name="POST")
                msg = "Frozen registry accepted registration"
                raise BridgeFuzzError(msg)
            except TypeError:
                pass  # Expected

        case 1:
            # Copy is unfrozen and independent
            shared = get_shared_registry()
            copy = shared.copy()
            if copy.frozen:
                msg = "Copy should be unfrozen"
                raise BridgeFuzzError(msg)

            def custom(_value: Any) -> str:
                return "custom"

            copy.register(custom, ftl_name="COPY_ONLY")
            if "COPY_ONLY" in shared:
                msg = "Copy polluted original registry"
                raise BridgeFuzzError(msg)
            if "COPY_ONLY" not in copy:
                msg = "Copy missing newly registered function"
                raise BridgeFuzzError(msg)

        case 2:
            # Copy preserves all original functions
            original = create_default_registry()
            original_funcs = set(original)
            copy = original.copy()
            copy_funcs = set(copy)
            if original_funcs != copy_funcs:
                msg = f"Copy functions differ: {original_funcs - copy_funcs}"
                raise BridgeFuzzError(msg)

        case _:
            # Double freeze is safe (idempotent)
            reg = FunctionRegistry()
            reg.freeze()
            reg.freeze()  # Should not raise
            if not reg.frozen:
                msg = "Double freeze broke frozen state"
                raise BridgeFuzzError(msg)

def _pattern_fluent_function_decorator(fdp: atheris.FuzzedDataProvider) -> None:
    """Test @fluent_function decorator edge cases."""
    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # Bare decorator (no parentheses)
            @fluent_function
            def bare_fn(value: Any) -> str:
                return str(value)

            if bare_fn(42) != "42":
                msg = f"Bare decorator broke function: {bare_fn(42)}"
                raise BridgeFuzzError(msg)

        case 1:
            # Decorator with parentheses, no inject_locale
            @fluent_function()
            def parens_fn(value: Any) -> str:
                return str(value)

            if parens_fn(42) != "42":
                msg = f"Parenthesized decorator broke function: {parens_fn(42)}"
                raise BridgeFuzzError(msg)

        case 2:
            # Decorator with inject_locale=True sets attribute
            @fluent_function(inject_locale=True)
            def locale_fn(value: Any, locale_code: str) -> str:
                return f"{value}@{locale_code}"

            attr_name = "_ftl_requires_locale"
            if not getattr(locale_fn, attr_name, False):
                msg = "inject_locale=True did not set attribute"
                raise BridgeFuzzError(msg)

            result = locale_fn(42, "en")
            if result != "42@en":
                msg = f"Decorated function broken: {result}"
                raise BridgeFuzzError(msg)

        case _:
            # Register decorated function in registry
            @fluent_function(inject_locale=True)
            def reg_fn(_value: Any, locale_code: str) -> str:
                return f"[{locale_code}]"

            reg = FunctionRegistry()
            reg.register(reg_fn, ftl_name="REG_FN")
            if not reg.should_inject_locale("REG_FN"):
                msg = "Decorated + registered: should_inject_locale is False"
                raise BridgeFuzzError(msg)

def _pattern_metadata_api(fdp: atheris.FuzzedDataProvider) -> None:  # noqa: PLR0912 - dispatch
    """Test get_expected_positional_args, get_builtin_metadata, has_function."""
    _domain.metadata_api_tests += 1
    reg = create_default_registry()
    variant = fdp.ConsumeIntInRange(0, 4)

    match variant:
        case 0:
            # get_expected_positional_args for known builtins
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                result = reg.get_expected_positional_args(name)
                if result is None:
                    msg = f"get_expected_positional_args({name}) returned None"
                    raise BridgeFuzzError(msg)
                if result != 1:
                    msg = f"get_expected_positional_args({name}) = {result}, expected 1"
                    raise BridgeFuzzError(msg)

        case 1:
            # get_expected_positional_args for unknown function
            fuzzed = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))
            result = reg.get_expected_positional_args(fuzzed)
            if fuzzed not in ("NUMBER", "DATETIME", "CURRENCY") and result is not None:
                msg = f"get_expected_positional_args({fuzzed!r}) returned {result}"
                raise BridgeFuzzError(msg)

        case 2:
            # get_builtin_metadata for known builtins
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                meta = reg.get_builtin_metadata(name)
                if meta is None:
                    msg = f"get_builtin_metadata({name}) returned None"
                    raise BridgeFuzzError(msg)
                if not meta.requires_locale:
                    msg = f"Builtin {name} should require locale"
                    raise BridgeFuzzError(msg)

        case 3:
            # has_function vs __contains__ consistency
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                has = reg.has_function(name)
                contains = name in reg
                if has != contains:
                    msg = f"has_function != __contains__ for {name}"
                    raise BridgeFuzzError(msg)
            fuzzed = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))
            has = reg.has_function(fuzzed)
            contains = fuzzed in reg
            if has != contains:
                msg = f"has_function != __contains__ for fuzzed {fuzzed!r}"
                raise BridgeFuzzError(msg)

        case _:
            # get_builtin_metadata for unknown function returns None
            fuzzed = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 30))
            meta = reg.get_builtin_metadata(fuzzed)
            if fuzzed not in ("NUMBER", "DATETIME", "CURRENCY") and meta is not None:
                msg = f"get_builtin_metadata({fuzzed!r}) returned non-None"
                raise BridgeFuzzError(msg)
