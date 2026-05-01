from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import atheris
from fuzz_bridge_support import (
    BridgeFuzzError,
    _domain,
)

from ftllexengine.runtime.function_bridge import FunctionRegistry, fluent_function


def _pattern_register_basic(fdp: atheris.FuzzedDataProvider) -> None:
    """Basic function registration: name generation, simple callables."""
    _domain.register_calls += 1
    reg = FunctionRegistry()
    num_funcs = fdp.ConsumeIntInRange(1, 5)

    for i in range(num_funcs):

        def make_fn(idx: int) -> Any:
            def fn(_value: Any) -> str:
                return f"result_{idx}"

            fn.__name__ = f"test_func_{idx}"
            return fn

        func = make_fn(i)
        ftl_name = f"FUNC{i}" if fdp.ConsumeBool() else None
        reg.register(func, ftl_name=ftl_name)

    # Invariant: len matches registration count
    if len(reg) != num_funcs:
        msg = f"Registry len {len(reg)} != expected {num_funcs}"
        raise BridgeFuzzError(msg)

def _pattern_register_signatures(fdp: atheris.FuzzedDataProvider) -> None:
    """Registration with various Python function signatures."""
    _domain.register_calls += 1
    reg = FunctionRegistry()
    variant = fdp.ConsumeIntInRange(0, 6)

    match variant:
        case 0:
            # Positional-only params
            def pos_only(value: Any, /) -> str:
                return str(value)

            reg.register(pos_only, ftl_name="POS_ONLY")

        case 1:
            # Keyword-only params
            def kw_only(value: Any, *, style: str = "default") -> str:
                return f"{value}_{style}"

            reg.register(kw_only, ftl_name="KW_ONLY")
            result = reg.call("KW_ONLY", [42], {"style": "custom"})
            if "42" not in str(result):
                msg = f"KW_ONLY result missing value: {result}"
                raise BridgeFuzzError(msg)

        case 2:
            # *args function
            def varargs(*args: Any) -> str:
                return "_".join(str(a) for a in args)

            reg.register(varargs, ftl_name="VARARGS")
            n = fdp.ConsumeIntInRange(0, 5)
            positional = [fdp.ConsumeIntInRange(0, 100) for _ in range(n)]
            reg.call("VARARGS", positional, {})

        case 3:
            # **kwargs function
            def kwargs_fn(value: Any, **kwargs: Any) -> str:
                return f"{value}_{len(kwargs)}"

            reg.register(kwargs_fn, ftl_name="KWARGS_FN")
            named = {f"key{i}": i for i in range(fdp.ConsumeIntInRange(0, 5))}
            reg.call("KWARGS_FN", ["hello"], named)

        case 4:
            # Function with many parameters (auto-mapping stress)
            def many_params(
                value: Any,
                *,
                minimum_fraction_digits: int = 0,
                maximum_fraction_digits: int = 3,
                use_grouping: bool = True,
                currency_display: str = "symbol",
            ) -> str:
                return str(value)

            reg.register(many_params, ftl_name="MANY")
            info = reg.get_function_info("MANY")
            if info is None:
                msg = "get_function_info returned None for registered function"
                raise BridgeFuzzError(msg)
            # Verify param_mapping includes all snake_case -> camelCase
            mapping_dict = dict(info.param_mapping)
            if "minimumFractionDigits" not in mapping_dict:
                msg = f"Missing camelCase mapping: {mapping_dict}"
                raise BridgeFuzzError(msg)

        case 5:
            # Duplicate registration (should overwrite)
            def fn_v1(_value: Any) -> str:
                return "v1"

            def fn_v2(_value: Any) -> str:
                return "v2"

            fn_v2.__name__ = "fn_v1"
            reg.register(fn_v1, ftl_name="DUP")
            reg.register(fn_v2, ftl_name="DUP")
            result = reg.call("DUP", ["x"], {})
            if str(result) != "v2":
                msg = f"Duplicate registration did not overwrite: got {result}"
                raise BridgeFuzzError(msg)

        case _:
            # Lambda registration
            reg.register(str, ftl_name="LAMBDA")
            reg.call("LAMBDA", [42], {})

def _pattern_param_mapping_custom(fdp: atheris.FuzzedDataProvider) -> None:
    """Custom param_map overrides auto-generated mappings."""
    _domain.register_calls += 1
    reg = FunctionRegistry()

    def target_fn(value: Any, *, minimum_fraction_digits: int = 0) -> str:
        return str(value)

    variant = fdp.ConsumeIntInRange(0, 2)

    if variant == 0:
        # Custom mapping overrides auto-generated
        custom_map = {"customName": "minimum_fraction_digits"}
        reg.register(target_fn, ftl_name="CUSTOM_MAP", param_map=custom_map)
        result = reg.call("CUSTOM_MAP", [42], {"customName": 2})
        if "42" not in str(result):
            msg = f"Custom param_map call failed: {result}"
            raise BridgeFuzzError(msg)

    elif variant == 1:
        # Empty custom map (auto-generation only)
        reg.register(target_fn, ftl_name="EMPTY_MAP", param_map={})
        info = reg.get_function_info("EMPTY_MAP")
        if info is None or len(info.param_mapping) == 0:
            msg = "Empty param_map should still have auto-generated mappings"
            raise BridgeFuzzError(msg)

    else:
        # Fuzzed param_map keys
        fuzzed_key = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 30))
        custom_map = {fuzzed_key: "minimum_fraction_digits"}
        reg.register(target_fn, ftl_name="FUZZ_MAP", param_map=custom_map)
        with contextlib.suppress(Exception):
            reg.call("FUZZ_MAP", [1], {fuzzed_key: 2})

def _pattern_signature_validation(fdp: atheris.FuzzedDataProvider) -> None:
    """Test registration error paths: locale arity, collision, auto-naming."""
    _domain.signature_validation_tests += 1
    reg = FunctionRegistry()
    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # inject_locale with insufficient positional params -> TypeError
            @fluent_function(inject_locale=True)
            def bad_fn(value: Any) -> str:
                return str(value)

            try:
                reg.register(bad_fn, ftl_name="BAD_LOCALE")
                msg = "inject_locale with 1 positional param did not raise TypeError"
                raise BridgeFuzzError(msg)
            except TypeError:
                _domain.register_failures += 1

        case 1:
            # Underscore collision detection -> ValueError
            def colliding(
                value: Any,
                *,
                _data: int = 0,
                data: int = 0,
            ) -> str:
                return str(value)

            try:
                reg.register(colliding, ftl_name="COLLIDE")
                msg = "Underscore collision did not raise ValueError"
                raise BridgeFuzzError(msg)
            except ValueError:
                _domain.register_failures += 1

        case 2:
            # Auto-naming from __name__ (ftl_name=None)
            def my_custom_function(value: Any) -> str:
                return str(value)

            reg.register(my_custom_function)
            if "MY_CUSTOM_FUNCTION" not in reg:
                msg = "Auto-naming failed: MY_CUSTOM_FUNCTION not in registry"
                raise BridgeFuzzError(msg)

        case _:
            # inject_locale=True with *args function (should succeed)
            @fluent_function(inject_locale=True)
            def varargs_locale(*args: Any) -> str:
                return str(args)

            reg.register(varargs_locale, ftl_name="VARARGS_LOCALE")
            if not reg.should_inject_locale("VARARGS_LOCALE"):
                msg = "varargs function with inject_locale not detected"
                raise BridgeFuzzError(msg)
