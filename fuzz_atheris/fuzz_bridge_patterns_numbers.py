from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import atheris
from fuzz_bridge_support import (
    _CAMEL_EXPECTED,
    _SNAKE_CASE_NAMES,
    BridgeFuzzError,
    _call_make_fluent_number,
    _domain,
    _group_ascii_thousands,
)

from ftllexengine.core.value_types import make_fluent_number
from ftllexengine.runtime.function_bridge import FluentNumber, FunctionRegistry
from ftllexengine.runtime.functions import create_default_registry


def _pattern_fluent_number_contracts(fdp: atheris.FuzzedDataProvider) -> None:
    """FluentNumber object contracts: str, repr, precision, frozen."""
    _domain.fluent_number_checks += 1
    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # Basic construction and str
            fn = FluentNumber(value=Decimal("1234.56"), formatted="1,234.56", precision=2)
            if str(fn) != "1,234.56":
                msg = f"FluentNumber str() = '{fn}', expected '1,234.56'"
                raise BridgeFuzzError(msg)

        case 1:
            # repr includes value info
            fn = FluentNumber(value=Decimal("99.9"), formatted="99.9", precision=1)
            r = repr(fn)
            if "99.9" not in r:
                msg = f"FluentNumber repr missing value: {r}"
                raise BridgeFuzzError(msg)

        case 2:
            # Precision can be None
            fn = FluentNumber(value=42, formatted="42", precision=None)
            if fn.precision is not None:
                msg = "FluentNumber precision should be None"
                raise BridgeFuzzError(msg)
            if str(fn) != "42":
                msg = f"FluentNumber str() with None precision = '{fn}'"
                raise BridgeFuzzError(msg)

        case _:
            # Frozen: attribute assignment should fail
            fn = FluentNumber(value=1, formatted="1", precision=0)
            try:
                fn.value = 999  # type: ignore[misc]
                msg = "FluentNumber is not frozen: attribute assignment succeeded"
                raise BridgeFuzzError(msg)
            except AttributeError:
                pass  # Expected: frozen dataclass

def _check_make_fluent_number_default_decimal(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Default Decimal formatting preserves trailing-zero precision."""
    int_part = fdp.ConsumeIntInRange(-9999, 9999)
    frac_core = str(fdp.ConsumeIntInRange(1, 999)).zfill(3)
    trailing_zeros = "0" * fdp.ConsumeIntInRange(1, 4)
    value = Decimal(f"{int_part}.{frac_core}{trailing_zeros}")
    fn = _call_make_fluent_number(value)
    expected_precision = len(frac_core) + len(trailing_zeros)
    if fn.formatted != str(value) or fn.precision != expected_precision:
        msg = (
            "make_fluent_number(default Decimal) did not preserve "
            f"string/precision: {fn!r} vs value={value!r}, "
            f"expected_precision={expected_precision}"
        )
        raise BridgeFuzzError(msg)

def _check_make_fluent_number_default_int(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Default integer formatting exposes zero visible decimals."""
    value = fdp.ConsumeIntInRange(-1_000_000, 1_000_000)
    fn = _call_make_fluent_number(value)
    if fn.formatted != str(value) or fn.precision != 0:
        msg = (
            "make_fluent_number(int) did not preserve zero visible precision: "
            f"{fn!r} for value={value}"
        )
        raise BridgeFuzzError(msg)

def _check_make_fluent_number_fractional_int(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Explicit fractional formatting controls visible precision for ints."""
    value = fdp.ConsumeIntInRange(-999, 999)
    frac_digits = "0" * fdp.ConsumeIntInRange(1, 4)
    formatted = f"{value}.{frac_digits}"
    fn = _call_make_fluent_number(value, formatted=formatted)
    if fn.formatted != formatted or fn.precision != len(frac_digits):
        msg = (
            "make_fluent_number(explicit fractional int) miscomputed precision: "
            f"{fn!r} for formatted={formatted!r}"
        )
        raise BridgeFuzzError(msg)

def _check_make_fluent_number_grouped_int(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Grouping separators do not create decimal precision."""
    value = fdp.ConsumeIntInRange(1_000, 999_999)
    formatted = _group_ascii_thousands(value)
    fn = _call_make_fluent_number(value, formatted=formatted)
    if fn.formatted != formatted or fn.precision != 0:
        msg = (
            "make_fluent_number(grouped int) treated grouping as decimals: "
            f"{fn!r} for formatted={formatted!r}"
        )
        raise BridgeFuzzError(msg)

def _check_make_fluent_number_localized_decimal(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Localized formatted strings drive visible precision inference."""
    whole = fdp.ConsumeIntInRange(1, 9999)
    precision = fdp.ConsumeIntInRange(1, 4)
    fraction = str(fdp.ConsumeIntInRange(0, (10**precision) - 1)).zfill(precision)
    value = Decimal(f"{whole}.{fraction}")
    grouped = _group_ascii_thousands(whole).replace(",", " ")
    formatted = f"{grouped},{fraction} EUR"
    fn = _call_make_fluent_number(value, formatted=formatted)
    if fn.formatted != formatted or fn.precision != precision:
        msg = (
            "make_fluent_number(localized decimal) miscomputed visible precision: "
            f"{fn!r} for formatted={formatted!r}"
        )
        raise BridgeFuzzError(msg)

def _check_make_fluent_number_disambiguation(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Formatted decimals for integer values are not mistaken for grouping."""
    precision = fdp.ConsumeIntInRange(1, 4)
    separator = fdp.PickValueInList([",", "."])
    zeros = "0" * precision
    value = fdp.PickValueInList([1, -1])
    formatted = f"{value}{separator}{zeros}"
    fn = _call_make_fluent_number(value, formatted=formatted)
    if fn.formatted != formatted or fn.precision != precision:
        msg = (
            "make_fluent_number(disambiguation) lost decimal precision: "
            f"{fn!r} for formatted={formatted!r}"
        )
        raise BridgeFuzzError(msg)

def _check_make_fluent_number_bool_rejection(
    _fdp: atheris.FuzzedDataProvider,
) -> None:
    """Bool inputs are rejected like direct FluentNumber construction."""
    try:
        make_fluent_number(True)
    except TypeError:
        return
    msg = "make_fluent_number(bool) should raise TypeError"
    raise BridgeFuzzError(msg)

def _pattern_make_fluent_number_api(fdp: atheris.FuzzedDataProvider) -> None:
    """make_fluent_number derives visible precision from domain values."""
    _domain.make_fluent_number_checks += 1
    handlers = (
        _check_make_fluent_number_default_decimal,
        _check_make_fluent_number_default_int,
        _check_make_fluent_number_fractional_int,
        _check_make_fluent_number_grouped_int,
        _check_make_fluent_number_localized_decimal,
        _check_make_fluent_number_disambiguation,
        _check_make_fluent_number_bool_rejection,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)

def _pattern_signature_immutability(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify FunctionSignature immutability and param_mapping tuple type."""
    reg = create_default_registry()
    func_name = fdp.PickValueInList(["NUMBER", "DATETIME", "CURRENCY"])
    info = reg.get_function_info(func_name)

    if info is None:
        msg = f"{func_name} FunctionSignature is None"
        raise BridgeFuzzError(msg)

    # param_mapping should be tuple of tuples (immutable)
    if not isinstance(info.param_mapping, tuple):
        msg = f"param_mapping is {type(info.param_mapping)}, expected tuple"
        raise BridgeFuzzError(msg)

    for pair in info.param_mapping:
        if not isinstance(pair, tuple) or len(pair) != 2:
            msg = f"param_mapping entry is not (str, str): {pair}"
            raise BridgeFuzzError(msg)

    # FunctionSignature should be frozen
    try:
        info.ftl_name = "HACKED"  # type: ignore[misc]
        msg = "FunctionSignature is not frozen"
        raise BridgeFuzzError(msg)
    except AttributeError:
        pass  # Expected

    # Callable should be present
    if not callable(info.callable):
        msg = "FunctionSignature callable is not callable"
        raise BridgeFuzzError(msg)

    # ftl_name should match what we queried
    if info.ftl_name != func_name:
        msg = f"FunctionSignature.ftl_name = '{info.ftl_name}', expected '{func_name}'"
        raise BridgeFuzzError(msg)

    # Fuzzed: try getting info for nonexistent function
    if fdp.ConsumeBool():
        fuzzed = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))
        bad_info = reg.get_function_info(fuzzed)
        if bad_info is not None and fuzzed not in ("NUMBER", "DATETIME", "CURRENCY"):
            msg = f"get_function_info returned non-None for unknown '{fuzzed}'"
            raise BridgeFuzzError(msg)

def _pattern_camel_case_conversion(fdp: atheris.FuzzedDataProvider) -> None:
    """Test _to_camel_case with known and fuzzed inputs."""
    _domain.camel_case_tests += 1
    variant = fdp.ConsumeIntInRange(0, 2)

    if variant == 0:
        # Known conversions with invariant checks
        for snake, expected_camel in _CAMEL_EXPECTED.items():
            result = FunctionRegistry._to_camel_case(snake)
            if result != expected_camel:
                msg = f"_to_camel_case('{snake}') = '{result}', expected '{expected_camel}'"
                raise BridgeFuzzError(msg)

    elif variant == 1:
        # Fuzzed snake_case names from curated list
        name = fdp.PickValueInList(list(_SNAKE_CASE_NAMES))
        result = FunctionRegistry._to_camel_case(name)
        if not isinstance(result, str):
            msg = f"_to_camel_case returned non-string: {type(result)}"
            raise BridgeFuzzError(msg)

    else:
        # Fully fuzzed input
        raw = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 50))
        result = FunctionRegistry._to_camel_case(raw)
        if not isinstance(result, str):
            msg = "_to_camel_case returned non-string for fuzzed input"
            raise BridgeFuzzError(msg)
