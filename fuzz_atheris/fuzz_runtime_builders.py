# mypy: disable-error-code=name-defined
from fuzz_runtime_support import (
    _CURRENCY_OPTS,
    _DATETIME_OPTS,
    _IDENTIFIERS,
    _NUMBER_OPTS,
    _SELECTOR_KEYS,
    _TERM_IDENTIFIERS,
    _TERM_QUERY_IDS,
    _UNICODE_TEXTS,
    _VAR_NAMES,
    UTC,
    Any,
    ComplexArgs,
    FluentBundle,
    RuntimeIntegrityError,
    _domain,
    atheris,
    contextlib,
    datetime,
    validate_message_variables,
)


def _build_expression(  # noqa: PLR0911, PLR0912 - dispatch
    fdp: atheris.FuzzedDataProvider,
    depth: int = 0,
) -> str:
    """Build a random FTL expression from fuzzed bytes.

    Maps byte values to grammar productions so mutations are meaningful.
    High branch count mirrors FTL grammar production rules (10 expression types).
    """
    if depth > 3 or fdp.remaining_bytes() < 2:
        return str(fdp.PickValueInList(list(_VAR_NAMES)))

    expr_type = fdp.ConsumeIntInRange(0, 9)
    match expr_type:
        case 0:
            # Variable reference
            return str(fdp.PickValueInList(list(_VAR_NAMES)))
        case 1:
            # String literal
            return f'"{fdp.PickValueInList(list(_UNICODE_TEXTS))}"'
        case 2:
            # Number literal
            num = fdp.ConsumeIntInRange(-9999, 9999)
            if fdp.ConsumeBool():
                return str(num)
            frac = fdp.ConsumeIntInRange(0, 99)
            return f"{num}.{frac:02d}"
        case 3:
            # Message reference
            ref_id = fdp.PickValueInList(list(_IDENTIFIERS))
            if fdp.ConsumeBool():
                return f"{{ {ref_id}.title }}"
            return f"{{ {ref_id} }}"
        case 4:
            # Term reference
            term_id = fdp.PickValueInList(list(_TERM_IDENTIFIERS))
            if fdp.ConsumeBool():
                return f"{{ {term_id} }}"
            return f"{{ {term_id}.attr }}"
        case 5:
            # NUMBER() call
            var = fdp.PickValueInList(list(_VAR_NAMES))
            opts = ""
            if fdp.ConsumeBool() and fdp.remaining_bytes() > 1:
                opts = ", " + fdp.PickValueInList(list(_NUMBER_OPTS))
            return f"{{ NUMBER({var}{opts}) }}"
        case 6:
            # DATETIME() call
            var = fdp.PickValueInList(list(_VAR_NAMES))
            opts = ""
            if fdp.ConsumeBool() and fdp.remaining_bytes() > 1:
                opts = ", " + fdp.PickValueInList(list(_DATETIME_OPTS))
            return f"{{ DATETIME({var}{opts}) }}"
        case 7:
            # CURRENCY() call
            var = fdp.PickValueInList(list(_VAR_NAMES))
            opts = ", " + fdp.PickValueInList(list(_CURRENCY_OPTS))
            if fdp.ConsumeBool() and fdp.remaining_bytes() > 1:
                opts += ", " + fdp.PickValueInList(list(_CURRENCY_OPTS))
            return f"{{ CURRENCY({var}{opts}) }}"
        case 8:
            # Nested placeable
            inner = _build_expression(fdp, depth + 1)
            return f"{{ {inner} }}"
        case 9:
            # Custom function
            var = fdp.PickValueInList(list(_VAR_NAMES))
            return f'{{ FUZZ_FUNC({var}, key: "val") }}'

    return str(fdp.PickValueInList(list(_VAR_NAMES)))


def _build_select_expression(fdp: atheris.FuzzedDataProvider) -> str:
    """Build a select expression with plural/string keys."""
    var = fdp.PickValueInList(list(_VAR_NAMES))

    # Selector: raw var, NUMBER(), or CURRENCY()
    selector_type = fdp.ConsumeIntInRange(0, 2)
    match selector_type:
        case 0:
            selector = var
        case 1:
            opts = ""
            if fdp.ConsumeBool() and fdp.remaining_bytes() > 1:
                opts = ", " + fdp.PickValueInList(list(_NUMBER_OPTS))
            selector = f"NUMBER({var}{opts})"
        case _:
            opts = ", " + fdp.PickValueInList(list(_CURRENCY_OPTS))
            selector = f"CURRENCY({var}{opts})"

    # Build variants
    num_variants = fdp.ConsumeIntInRange(1, 5)
    variants: list[str] = []
    default_idx = fdp.ConsumeIntInRange(0, num_variants - 1)

    for i in range(num_variants):
        # Key: plural category or number literal
        if fdp.ConsumeBool():
            key = fdp.PickValueInList(list(_SELECTOR_KEYS))
        else:
            key = str(fdp.ConsumeIntInRange(0, 100))

        value = _build_expression(fdp, depth=1) if fdp.ConsumeBool() else "value"
        prefix = "*" if i == default_idx else ""
        variants.append(f"    [{prefix}{key}] {value}")

    body = "\n".join(variants)
    return f"{{ {selector} ->\n{body}\n}}"


def _build_message(fdp: atheris.FuzzedDataProvider, msg_id: str) -> str:  # noqa: PLR0912 - dispatch
    """Build a complete FTL message entry."""
    if fdp.remaining_bytes() < 2:
        return f"{msg_id} = fallback\n"

    msg_type = fdp.ConsumeIntInRange(0, 5)
    match msg_type:
        case 0:
            # Simple value with expressions
            parts: list[str] = []
            num_parts = fdp.ConsumeIntInRange(1, 3)
            for _ in range(num_parts):
                if fdp.ConsumeBool():
                    parts.append(_build_expression(fdp))
                else:
                    parts.append(fdp.PickValueInList(list(_UNICODE_TEXTS)))
            value = " ".join(parts)
            msg = f"{msg_id} = {value}\n"
        case 1:
            # Select expression
            sel = _build_select_expression(fdp)
            msg = f"{msg_id} =\n    {sel}\n"
        case 2:
            # Message with attributes
            value = _build_expression(fdp)
            attrs: list[str] = []
            num_attrs = fdp.ConsumeIntInRange(1, 3)
            for j in range(num_attrs):
                attr_val = _build_expression(fdp, depth=1)
                attrs.append(f"    .attr{j} = {attr_val}")
            attr_block = "\n".join(attrs)
            msg = f"{msg_id} = {value}\n{attr_block}\n"
        case 3:
            # Cyclic reference
            target = fdp.PickValueInList(list(_IDENTIFIERS))
            msg = f"{msg_id} = {{ {target} }}\n"
        case 4:
            # Reference chain
            target = fdp.PickValueInList(list(_IDENTIFIERS))
            if fdp.ConsumeBool():
                msg = f"{msg_id} = prefix {{ {target} }} suffix\n"
            else:
                msg = f"{msg_id} = {{ {target}.title }}\n"
        case _:
            # Deep nesting
            nesting = fdp.ConsumeIntInRange(1, 8)
            expr = fdp.PickValueInList(list(_VAR_NAMES))
            for _ in range(nesting):
                expr = f"{{ {expr} }}"
            msg = f"{msg_id} = {expr}\n"

    # Optionally add attributes even to non-attribute messages
    if fdp.ConsumeBool() and fdp.remaining_bytes() > 2:
        msg = msg.rstrip("\n") + f"\n    .title = {_build_expression(fdp)}\n"

    return msg


def _build_term(fdp: atheris.FuzzedDataProvider) -> str:
    """Build a term definition."""
    term_id = fdp.PickValueInList(list(_TERM_IDENTIFIERS))

    if fdp.ConsumeBool():
        # Term with select
        sel = _build_select_expression(fdp)
        term = f"{term_id} =\n    {sel}\n"
    else:
        value = _build_expression(fdp)
        term = f"{term_id} = {value}\n"

    # Optional attributes
    if fdp.ConsumeBool() and fdp.remaining_bytes() > 1:
        attr_val = _build_expression(fdp, depth=1)
        term = term.rstrip("\n") + f"\n    .attr = {attr_val}\n"

    return term


def _build_ftl_resource(fdp: atheris.FuzzedDataProvider) -> str:
    """Build a complete FTL resource from fuzzed bytes.

    Grammar-aware: each byte decision maps to a structural choice in the FTL
    grammar, so libFuzzer coverage feedback drives exploration of new resolver
    code paths rather than random noise.
    """
    parts: list[str] = []

    # Always include some terms for term references to resolve
    num_terms = fdp.ConsumeIntInRange(0, 3)
    for _ in range(num_terms):
        if fdp.remaining_bytes() < 2:
            break
        parts.append(_build_term(fdp))

    # Build messages - use deterministic IDs so TARGET_MESSAGE_IDS can find them
    ids_to_build = list(_IDENTIFIERS)
    num_messages = fdp.ConsumeIntInRange(2, min(8, len(ids_to_build)))
    for i in range(num_messages):
        if fdp.remaining_bytes() < 2:
            break
        parts.append(_build_message(fdp, ids_to_build[i]))

    return "\n".join(parts)


def _generate_complex_args(fdp: atheris.FuzzedDataProvider) -> ComplexArgs:
    """Generate fuzzed arguments matching grammar variable names.

    Uses the same variable names as _build_expression so that constructed
    FTL messages can resolve their variable references.
    """
    # Always provide the core variables so resolution paths are exercised
    arg_keys = ("var", "name", "count", "amount", "date", "var_0", "var_1", "var_2", "var_3")

    args: ComplexArgs = {}
    for key in arg_keys:
        if fdp.remaining_bytes() < 2:
            # Provide defaults for remaining keys
            args[key] = 42
            continue

        val_type = fdp.ConsumeIntInRange(0, 9)
        match val_type:
            case 0:
                args[key] = fdp.ConsumeUnicodeNoSurrogates(20)
            case 1:
                args[key] = fdp.ConsumeFloat()
            case 2:
                args[key] = fdp.ConsumeInt(4)
            case 3:
                args[key] = datetime.now(tz=UTC)
            case 4:
                args[key] = [fdp.ConsumeUnicodeNoSurrogates(5) for _ in range(3)]
            case 5:
                args[key] = {"nested": fdp.ConsumeInt(2)}
            case 6:
                args[key] = fdp.ConsumeBool()
            case 7:
                # Numeric edge cases for NUMBER/CURRENCY selectors
                args[key] = fdp.PickValueInList([0, 1, 2, 3, 5, 10, 100, 1000000])
            case 8:
                # Float edge cases
                args[key] = fdp.PickValueInList(
                    [0.0, -0.0, 1.5, float("inf"), float("-inf"), float("nan")]
                )
            case 9:
                # Decimal-like for precision testing
                args[key] = fdp.ConsumeIntInRange(-99999, 99999) / 100

    return args


def _fuzzed_function(args: list[Any], kwargs: dict[str, Any]) -> str:
    """Mock custom function for FunctionRegistry testing."""
    return f"PROCESSED_{len(args)}_{len(kwargs)}"


def _add_random_resources(fdp: atheris.FuzzedDataProvider, bundle: FluentBundle) -> None:
    """Add grammar-aware FTL resources to bundle.

    Constructs structurally valid FTL from fuzzed bytes so that libFuzzer
    mutations map to meaningful grammar variations rather than random noise.
    """
    ftl = _build_ftl_resource(fdp)

    with contextlib.suppress(Exception):
        bundle.add_resource(ftl)

    # Optionally add a second resource (tests message dedup / last-wins behavior)
    if fdp.ConsumeBool() and fdp.remaining_bytes() > 4:
        ftl2 = _build_ftl_resource(fdp)
        with contextlib.suppress(Exception):
            bundle.add_resource(ftl2)


def _validate_bundle_message_lookup(
    bundle: FluentBundle,
    message_id: str,
) -> None:
    """Validate FluentBundle.get_message() for one message identifier."""
    message = bundle.get_message(message_id)
    if message is None:
        return

    if message.id.name != message_id:
        msg = f"get_message({message_id!r}) returned node named {message.id.name!r}"
        raise RuntimeIntegrityError(msg)
    if bundle.get_term(message_id) is not None:
        msg = f"get_term({message_id!r}) crossed the message/term namespace boundary"
        raise RuntimeIntegrityError(msg)

    declared_variables = bundle.get_message_variables(message_id)
    validation = validate_message_variables(message, declared_variables)
    if not validation.is_valid:
        msg = f"validate_message_variables() rejected bundle message {message_id!r}"
        raise RuntimeIntegrityError(msg)
    if validation.declared_variables != declared_variables:
        msg = (
            "validate_message_variables() changed declared variables for "
            f"{message_id!r}: {validation.declared_variables!r} vs {declared_variables!r}"
        )
        raise RuntimeIntegrityError(msg)


def _validate_bundle_term_lookup(
    bundle: FluentBundle,
    term_id: str,
) -> None:
    """Validate FluentBundle.get_term() for one term identifier."""
    term = bundle.get_term(term_id)
    if term is None:
        return

    if term.id.name != term_id:
        msg = f"get_term({term_id!r}) returned node named {term.id.name!r}"
        raise RuntimeIntegrityError(msg)
    if bundle.get_term(f"-{term_id}") is not None:
        msg = f"get_term('-{term_id}') bypassed the no-leading-dash contract"
        raise RuntimeIntegrityError(msg)
    if bundle.get_message(term_id) is not None:
        msg = f"get_message({term_id!r}) crossed the term/message namespace boundary"
        raise RuntimeIntegrityError(msg)

    declared_variables = bundle.introspect_term(term_id).get_variable_names()
    validation = validate_message_variables(term, declared_variables)
    if not validation.is_valid:
        msg = f"validate_message_variables() rejected bundle term {term_id!r}"
        raise RuntimeIntegrityError(msg)
    if validation.declared_variables != declared_variables:
        msg = (
            "validate_message_variables() changed declared term variables for "
            f"{term_id!r}: {validation.declared_variables!r} vs {declared_variables!r}"
        )
        raise RuntimeIntegrityError(msg)


def _verify_ast_lookup_accessors(bundle: FluentBundle) -> None:
    """Validate FluentBundle AST lookup accessors on the public facade."""
    _domain.ast_lookup_checks += 1

    missing_id = "__missing_bundle_lookup__"
    if bundle.get_message(missing_id) is not None:
        msg = f"get_message({missing_id!r}) returned a node for a missing message"
        raise RuntimeIntegrityError(msg)
    if bundle.get_term(missing_id) is not None:
        msg = f"get_term({missing_id!r}) returned a node for a missing term"
        raise RuntimeIntegrityError(msg)

    for message_id in _IDENTIFIERS:
        _validate_bundle_message_lookup(bundle, message_id)

    for term_id in _TERM_QUERY_IDS:
        _validate_bundle_term_lookup(bundle, term_id)

