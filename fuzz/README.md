---
afad: "3.2"
version: "0.97.0"
domain: fuzzing
updated: "2026-01-31"
route:
  keywords: [fuzzing, coverage, atheris, libfuzzer, fuzz, seeds, corpus]
  questions: ["what do the fuzzers cover?", "what modules are fuzzed?", "what is not fuzzed?"]
---

# Fuzzer Coverage Inventory

**Purpose**: Stock-taking of what the Atheris/libFuzzer fuzzing infrastructure covers, enabling gap analysis and planning.

## Fuzzer Summary

| Fuzzer | Target Module(s) | Patterns | Seeds | Concern |
|:-------|:-----------------|:---------|:------|:--------|
| `fuzz_bridge.py` | `runtime.function_bridge` | 14 | 18 (.bin) | FunctionRegistry machinery, FluentNumber contracts |
| `fuzz_graph.py` | `analysis.graph` | 12 | 12 (.bin) | Dependency graph cycle detection, canonicalization |
| `fuzz_builtins.py` | `runtime.functions`, `runtime.function_bridge` | 13 | 20 (.bin) | Built-in functions and FunctionRegistry |
| `fuzz_cache.py` | `runtime.bundle`, `runtime.cache`, `integrity` | 13 | 43 (.ftl) + 5 (.bin) | Cache concurrency and integrity |
| `fuzz_currency.py` | `parsing.currency` | 16 | 65 (.txt) | Currency symbol extraction |
| `fuzz_fiscal.py` | `parsing.fiscal` | 7 | 15 (.bin) | Fiscal calendar arithmetic |
| `fuzz_integrity.py` | `validation`, `runtime.bundle`, `integrity` | 23 | 68 (.ftl) + 2 (.bin) | Semantic validation, cross-resource |
| `fuzz_iso.py` | `introspection.iso` | 9 | 17 (.bin) | ISO 3166/4217 introspection |
| `fuzz_lock.py` | `runtime.rwlock` | 13 | 24 (.bin) | RWLock concurrency primitives |
| `fuzz_numbers.py` | `parsing.numbers` | 19 | 70 (.txt) | Locale-aware numeric parsing |
| `fuzz_plural.py` | `runtime.plural_rules` | 10 | 20 (.bin) | CLDR plural category selection |
| `fuzz_oom.py` | `syntax.parser` | 16 | 42 (.ftl) + 1 (.bin) | Parser object explosion (DoS) |
| `fuzz_roundtrip.py` | `syntax.parser`, `syntax.serializer` | 13 | 18 (.bin) | Parser-serializer convergence |
| `fuzz_runtime.py` | `runtime.bundle`, `runtime.cache`, `integrity`, `diagnostics.errors` | 6+8 | 73 (.bin) | Full runtime stack, strict mode |
| `fuzz_scope.py` | `runtime.resolver`, `runtime.bundle` | 12 | 12 (.bin) | Variable scoping, term isolation, depth guards |
| `fuzz_structured.py` | `syntax.parser`, `syntax.serializer` | 10 | 12 (.ftl) | Grammar-aware AST construction |

## Module Coverage Matrix

| Source Module | Fuzzers Covering It |
|:--------------|:--------------------|
| `analysis.graph` | graph |
| `diagnostics.errors` | runtime, oom, numbers, currency, cache, integrity, builtins |
| `integrity` | runtime, cache, integrity |
| `introspection.iso` | iso |
| `parsing.currency` | currency |
| `parsing.fiscal` | fiscal |
| `parsing.numbers` | numbers |
| `runtime.function_bridge` | bridge, builtins |
| `runtime.functions` | builtins |
| `runtime.bundle` | runtime, cache, integrity, scope |
| `runtime.resolver` | scope |
| `runtime.cache` | runtime, cache |
| `runtime.plural_rules` | plural |
| `runtime.rwlock` | lock |
| `syntax.parser` | oom, roundtrip, structured |
| `syntax.serializer` | roundtrip, structured |
| `validation` | integrity |

## `fuzz_bridge`

Target: `runtime.function_bridge` -- FunctionRegistry lifecycle, `_to_camel_case`, parameter mapping, FluentNumber contracts, `fluent_function` decorator, freeze/copy isolation, dict-like interface.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `fluent_number_contracts` | 12 | str, __contains__, __len__, repr, frozen, precision=None |
| `camel_case_conversion` | 10 | Known snake->camelCase pairs, fuzzed input returns str |
| `signature_immutability` | 5 | FunctionSignature frozen, param_mapping tuple, ftl_name, fuzzed lookup |
| `register_basic` | 10 | len(registry) matches registration count |
| `register_signatures` | 12 | Positional-only, *args, **kwargs, many params, lambda, overwrite |
| `param_mapping_custom` | 8 | Custom param_map overrides auto-generated mapping |
| `call_dispatch` | 12 | call() returns result or raises for unknown function |
| `dict_interface` | 8 | __contains__, __iter__, list_functions, get_python_name, get_callable |
| `freeze_copy_lifecycle` | 8 | Freeze prevents registration, copy is independent+unfrozen, idempotent |
| `fluent_function_decorator` | 8 | Bare, parenthesized, inject_locale=True attribute, registry integration |
| `error_wrapping` | 7 | TypeError/ValueError wrapped as FrozenFluentError |
| `locale_injection` | 10 | should_inject_locale flag, FluentBundle locale protocol |
| `evil_objects` | 5 | Evil __str__, __hash__, recursive list, huge str, None |
| `raw_bytes` | 3 | Malformed input stability |

### Allowed Exceptions

`ValueError`, `TypeError`, `OverflowError`, `ArithmeticError`, `FrozenFluentError`, `RecursionError`, `RuntimeError` -- invalid inputs, frozen registry mutations, and adversarial object interactions.

---

## `fuzz_builtins`

Target: `runtime.functions` (NUMBER, DATETIME, CURRENCY), `runtime.function_bridge` (FunctionRegistry, FluentNumber, parameter mapping, locale injection, freeze/copy).

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `number_basic` | 12 | Result is FluentNumber, fraction/grouping variation |
| `number_precision` | 15 | CLDR v operand non-negative, min_frac consistency |
| `number_edges` | 8 | NaN, Inf, -0.0, huge, tiny stability |
| `datetime_styles` | 10 | Non-empty string result, all style combos |
| `datetime_edges` | 8 | Epoch, Y2K, max timestamp, timezone offsets |
| `currency_codes` | 12 | FluentNumber result, valid/fuzzed ISO codes |
| `currency_precision` | 10 | Currency-specific decimals (JPY=0, BHD=3) |
| `custom_pattern` | 8 | Custom Babel patterns for all 3 functions |
| `registry_lifecycle` | 8 | Freeze, copy isolation, introspection, builtins present |
| `parameter_mapping` | 7 | camelCase FTL args -> snake_case via registry.call() |
| `locale_injection` | 5 | All builtins require locale, fuzzed locale fallback |
| `error_paths` | 5 | Negative/huge fraction digits, empty/invalid currency |
| `raw_bytes` | 3 | Malformed input stability |

### Allowed Exceptions

`ValueError`, `TypeError`, `OverflowError`, `InvalidOperation`, `OSError`, `ArithmeticError`, `FrozenFluentError` -- invalid inputs and Babel formatting limitations.

---

## `fuzz_cache`

Target: `runtime.cache.IntegrityCache` -- cache invalidation, key collision, write-once, multi-threaded access (2-8 threads).

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `variable_messages` | 10 | Cache key varies with args |
| `attribute_messages` | 8 | Attribute in cache key |
| `select_expressions` | 8 | Complex pattern caching |
| `message_references` | 8 | Resolver stress under cache |
| `term_references` | 8 | Namespace variation in keys |
| `long_values` | 6 | Memory weight enforcement |
| `many_variables` | 6 | Key complexity scaling |
| `circular_refs` | 6 | Error caching on cycles |
| `minimal_resource` | 6 | Empty/trivial resource caching |
| `hotspot` | 6 | Repeated access cache hits |
| `raw_bytes` | 12 | Malformed input stability |
| `capacity_stress` | 6 | Eviction under capacity pressure |
| `deep_args` | 10 | Deeply nested/unhashable args stress `_make_hashable` |

### Allowed Exceptions

`CacheCorruptionError`, `WriteConflictError`, `DataIntegrityError`, `FrozenFluentError` -- cache integrity violations are expected findings; `FrozenFluentError` from depth guards.

---

## `fuzz_graph`

Target: `analysis.graph` -- `canonicalize_cycle`, `make_cycle_key`, `detect_cycles`, `build_dependency_graph`. Validates cycle detection correctness, canonicalization invariants, and dependency graph construction with namespace prefixing.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `canonicalize_idempotence` | 12 | Double canonicalization is identity, closing element preserved |
| `canonicalize_direction` | 10 | A->B->C and A->C->B produce distinct canonical forms |
| `make_cycle_key_consistency` | 8 | Key matches joined canonical form, rotation-invariant (unique nodes) |
| `canonicalize_edge_cases` | 6 | Empty, single, two-element sequences handled correctly |
| `detect_self_loops` | 10 | Self-referencing node detected as cycle of length 2 |
| `detect_simple_cycles` | 12 | Known N-node ring detected, all nodes present |
| `detect_dag_no_cycles` | 10 | Acyclic graphs return empty cycle list |
| `detect_disconnected` | 8 | Independent components each detect their own cycles |
| `detect_dense_mesh` | 8 | Complete graph cycle detection stability |
| `detect_deep_chain` | 8 | Long chain (up to 200 nodes) with back-edge cycle detection |
| `build_dependency_graph` | 10 | Namespace prefixing, key/value structure, msg_deps unprefixed |
| `adversarial_graph` | 5 | Unicode node IDs, empty strings, whitespace-only identifiers |

### Allowed Exceptions

`ValueError`, `TypeError`, `RecursionError` -- invalid inputs and graph construction edge cases.

---

## `fuzz_currency`

Target: `parsing.currency.parse_currency` -- tiered loading, ambiguous symbol resolution, numeric extraction across locales.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `unambiguous_unicode` | 8 | Fast tier resolves unique symbols |
| `ambiguous_dollar` | 8 | Locale disambiguates `$` |
| `ambiguous_pound` | 7 | Locale disambiguates `£` |
| `ambiguous_yen_yuan` | 7 | Locale disambiguates `¥` |
| `ambiguous_kr` | 7 | Locale disambiguates `kr` |
| `comma_decimal` | 7 | European decimal parsing |
| `period_grouping` | 7 | European grouping parsing |
| `negative_format` | 8 | Prefix/suffix/paren negatives |
| `explicit_iso_code` | 7 | ISO code bypass symbol lookup |
| `invalid_iso_code` | 7 | Error on invalid codes |
| `whitespace_variation` | 7 | Unicode whitespace handling |
| `edge_case` | 5 | Empty, BOM, zero-width, Arabic-Indic |
| `raw_bytes` | 10 | Malformed input stability |
| `fullwidth_digits` | 5 | Fullwidth numeral handling |
| `code_symbol_combo` | 5 | ISO code + symbol mixed input |
| `special_number` | 5 | Differential: FTL vs Python builtins |

### Allowed Exceptions

`FrozenFluentError` -- depth guard safety mechanism.

---

## `fuzz_fiscal`

Target: `parsing.fiscal` -- `FiscalCalendar`, `FiscalDelta`, `FiscalPeriod` arithmetic and invariants.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `calendar_invariants` | 25 | Quarter 1-4, month 1-12, date in fiscal year |
| `quarter_boundaries` | 15 | Quarter start/end contiguous |
| `delta_arithmetic` | 20 | Commutativity, identity, associativity |
| `delta_algebra` | 15 | Double negation, scalar multiplication |
| `period_immutability` | 10 | Hashable, frozen, equality |
| `convenience_functions` | 10 | Match FiscalCalendar methods |
| `boundary_stress` | 5 | Extreme years, leap years |

### Allowed Exceptions

`ValueError`, `OverflowError`, `TypeError` -- invalid dates and arithmetic overflow.

---

## `fuzz_integrity`

Target: `validation.validate_resource` + `FluentBundle` -- semantic validation, cross-resource integrity.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `simple_message` | 8 | Valid FTL accepted |
| `message_attr` | 8 | Attribute validation |
| `message_ref` | 7 | Intra-resource reference |
| `term_def` | 7 | Term definition valid |
| `term_usage` | 8 | Term reference resolution |
| `select_expr` | 7 | Select validation |
| `multiple_entries` | 7 | Multi-entry resource |
| `comment_message` | 7 | Comment + message combo |
| `complex_pattern` | 7 | Variable in pattern |
| `circular_2way` | 6 | Circular reference detection |
| `undefined_ref` | 6 | Undefined reference flagged |
| `duplicate_id` | 6 | Duplicate ID detection |
| `attr_only` | 6 | Attribute-only message |
| `deep_chain` | 6 | Deep reference chain |
| `cross_resource_ref` | 6 | Cross-resource reference |
| `term_attr` | 6 | Term with attributes |
| `function_ref` | 6 | Function call in pattern |
| `id_conflict` | 6 | Multi-resource ID conflict |
| `unclosed_brace` | 5 | Malformed FTL recovery |
| `invalid_id` | 5 | Invalid identifier rejection |
| `malformed_pattern` | 5 | Empty placeable handling |
| `null_bytes` | 5 | Null byte tolerance |
| `raw_bytes` | 10 | Malformed input stability |

### Allowed Exceptions

`DataIntegrityError`, `FrozenFluentError` -- integrity violations are expected findings.

---

## `fuzz_iso`

Target: `introspection.iso` -- ISO 3166-1 territory and ISO 4217 currency lookups, type guards, cache.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `territory_lookup` | 15 | alpha2 matches input, name non-empty, hashable |
| `currency_lookup` | 15 | code matches input, decimal_digits in {0,2,3,4} |
| `type_guards` | 15 | Guard consistent with lookup result |
| `cache_consistency` | 12 | Repeated lookup returns same object |
| `list_functions` | 10 | Returns frozenset, elements typed, cardinality |
| `territory_currencies` | 10 | Returns tuple of 3-char uppercase codes |
| `cache_clear_stress` | 8 | Post-clear value equality preserved |
| `cross_reference` | 8 | Territory currencies resolve via get_currency |
| `invalid_input_stress` | 7 | Empty, long, null, unicode, mixed case |

### Allowed Exceptions

`BabelImportError`, `ValueError`, `KeyError`, `LookupError` -- Babel not installed or invalid locale/CLDR data.

---

## `fuzz_lock`

Target: `runtime.rwlock.RWLock`, `with_read_lock`, `with_write_lock` -- reader/writer exclusion, reentrancy, downgrading, timeout, deadlock detection.

### Patterns

Ordered cheapest-first. Pattern selection uses `ConsumeBytes(2)` with modulo to distribute uniformly across the weight space, avoiding the tail-entry overflow bias inherent in `ConsumeIntInRange` cumulative scans. Seed files use 2-byte big-endian suffixes targeting each pattern's weight range.

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `reentrant_reads` | 5 | Same thread acquires read lock N times |
| `reentrant_writes` | 5 | Same thread acquires write lock N times |
| `upgrade_rejection` | 8 | Read-to-write upgrade raises RuntimeError |
| `decorator_correctness` | 6 | with_read_lock/with_write_lock return values |
| `write_to_read_downgrade` | 10 | Writer acquires reads, persist after write release |
| `rapid_lock_cycling` | 8 | Shared counter correct after rapid cycles |
| `cross_thread_handoff` | 6 | Rapid write handoff between threads, no lost entries |
| `concurrent_readers` | 12 | Multiple readers hold lock simultaneously |
| `timeout_acquisition` | 8 | TimeoutError raised, lock usable after timeout |
| `reader_writer_exclusion` | 15 | No concurrent reader+writer, no multi-writer |
| `writer_preference` | 10 | Waiting writer blocks new readers (fuzz-controlled timing) |
| `reader_starvation` | 6 | Continuous readers cannot starve waiting writer |
| `mixed_contention` | 7 | All operations interleaved across threads |

### Allowed Exceptions

`RuntimeError`, `TimeoutError` -- expected from upgrade rejection, lock protocol violations, and timeout-based acquisition.

---

## `fuzz_numbers`

Target: `parsing.numbers.parse_number`, `parse_decimal` -- locale-aware numeric parsing with CLDR separators.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `basic_integer` | 8 | Parse succeeds for plain integers |
| `decimal_period` | 8 | Period decimal parsing |
| `us_thousands` | 7 | Comma grouping (en-US) |
| `space_thousands` | 7 | Space grouping (fr-FR, lv-LV) |
| `de_format` | 7 | German format (period group, comma decimal) |
| `ch_format` | 7 | Swiss format (apostrophe group) |
| `scientific` | 7 | Scientific notation |
| `signed_number` | 7 | Explicit sign prefix |
| `small_decimal` | 7 | Sub-unit decimals (0.000123) |
| `large_integer` | 7 | Large integers |
| `zero_variant` | 6 | Zero representations (0, -0, +0) |
| `special_float` | 6 | NaN, Infinity, -Infinity |
| `extreme_large` | 6 | Extreme magnitude (1e308) |
| `unicode_digits` | 6 | Arabic-Indic, Thai, Khmer digits |
| `malformed` | 6 | Malformed number strings |
| `null_bytes` | 5 | Null byte tolerance |
| `very_long` | 5 | Very long input strings |
| `invalid_string` | 5 | Non-numeric strings |
| `raw_bytes` | 10 | Malformed input stability |

### Allowed Exceptions

`FrozenFluentError` -- depth guard safety mechanism.

---

## `fuzz_plural`

Target: `runtime.plural_rules.select_plural_category` -- CLDR plural category selection across locales, number types, and precision-aware v-operand handling.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `category_validity` | 15 | Result in {zero, one, two, few, many, other} |
| `precision_sensitivity` | 15 | Precision changes v operand, both results valid |
| `locale_coverage` | 12 | High-leverage locales with boundary numbers |
| `locale_fallback` | 8 | Invalid/unknown locales fall back gracefully |
| `determinism` | 12 | Same inputs always return same category |
| `number_type_variety` | 10 | int, float, Decimal all produce valid categories |
| `boundary_numbers` | 12 | CLDR boundary values (0, 1, 2, 5, 11, 21, 100) |
| `cache_consistency` | 8 | LRU-cached locale returns consistent results |
| `extreme_inputs` | 5 | Huge, negative, NaN, Inf, high precision |
| `raw_bytes` | 3 | Malformed input stability |

### Allowed Exceptions

`ValueError`, `TypeError`, `OverflowError`, `InvalidOperation` -- invalid numbers and arithmetic edge cases.

---

## `fuzz_oom`

Target: `syntax.parser.FluentParserV1` -- small inputs producing massive ASTs ("Billion Laughs" style DoS).

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `placeable_nest` | 8 | Nested placeable depth limit |
| `attribute_explosion` | 8 | Many attributes per message |
| `select_nest` | 7 | Nested select expressions |
| `variant_explosion` | 7 | Many variants per select |
| `reference_chain` | 8 | Long message reference chains |
| `term_nest` | 7 | Nested term references |
| `mixed_placeable_select` | 7 | Combined placeable/select nesting |
| `attribute_select_combo` | 7 | Attributes with selects inside |
| `raw_bytes` | 10 | Malformed input stability |
| `comment_flood` | 6 | Many comments before message |
| `message_flood` | 6 | Many small messages |
| `multiline_value` | 6 | Long multiline continuations |
| `variant_expression_explosion` | 6 | Variants with placeables in arms |
| `cyclic_chain` | 6 | Self-referencing message cycles |
| `term_message_cross_ref` | 6 | Terms and messages cross-referencing |
| `attr_deep_placeable` | 5 | Attributes with deep nesting |

### Allowed Exceptions

`FrozenFluentError` -- depth guard and max nesting enforcement.

---

## `fuzz_roundtrip`

Target: `syntax.parser.FluentParserV1`, `syntax.serializer.serialize` -- parser-serializer convergence property S(P(S(P(x)))) == S(P(x)) across all grammar productions.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `simple_message` | 10 | Basic id = value roundtrips |
| `variable_placeable` | 12 | { $var } placeables survive roundtrip |
| `term_reference` | 8 | -term definitions and { -term } references |
| `message_reference` | 8 | { other-msg } cross-references |
| `select_expression` | 15 | Plural/string selector with variants |
| `attributes` | 10 | .attr = value on messages |
| `comments` | 5 | #, ##, ### comment types |
| `function_call` | 8 | NUMBER, DATETIME, CURRENCY with args |
| `multiline_pattern` | 7 | Continuation line values |
| `mixed_resource` | 12 | Multiple entry types combined |
| `deep_nesting` | 5 | String literals, nested variable refs |
| `raw_unicode` | 5 | Random Unicode junk-free convergence |
| `convergence_stress` | 5 | Multi-pass S2 == S3 stabilization |

### Allowed Exceptions

`ValueError`, `RecursionError`, `MemoryError`, `UnicodeDecodeError`, `UnicodeEncodeError` -- parser/serializer resource limits and encoding edge cases.

---

## `fuzz_runtime`

Target: `runtime.bundle.FluentBundle` -- full resolver stack, strict mode, caching, concurrency, security.

Scenario and security sub-pattern selection uses deterministic weighted round-robin driven by the iteration counter, not fuzzed bytes. This prevents libFuzzer's coverage-guided mutations from skewing the scenario distribution (observed: concurrent at 52% instead of intended 10% when routing was byte-driven). All fuzzed bytes now go to FTL content and configuration generation. String and RegEx instrumentation hooks enabled for deeper coverage of message ID lookups, selector matching, and pattern-based parsing.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `core_runtime` | 40 | Frozen error checksum, cache stability, determinism |
| `strict_mode` | 20 | Zero errors in strict format_pattern |
| `caching` | 15 | Cache hit determinism, corruption detection |
| `security` | 10 | *(8 sub-patterns below)* |
| `concurrent` | 10 | No deadlocks, 2-thread barrier test |
| `differential` | 5 | Same FTL, different configs, no crash divergence |

Security sub-patterns:

| Sub-pattern | Weight | Attack Vector |
|:------------|-------:|:--------------|
| `security_recursion` | 25 | Deep placeables, cyclic refs, self-ref terms |
| `security_memory` | 20 | Large values, many variants/attributes |
| `security_cache_poison` | 15 | inf/nan/None/list as args |
| `security_function_inject` | 12 | Custom function registration + recursive cross-context calls |
| `security_locale_explosion` | 8 | Very long / control char locales |
| `security_expansion_budget` | 8 | Billion Laughs exponential message expansion (max_expansion_size) |
| `security_dag_expansion` | 7 | DAG shared-reference args stress _make_hashable node budget |
| `security_dict_functions` | 5 | Dict-as-functions constructor rejection (TypeError guard) |

### Memory Management

Two reference cycle sources were fixed in ftllexengine 0.101.0 (MEM-REFCYCLE-001): (1) `ASTVisitor._instance_dispatch_cache` stored bound methods referencing `self`, and (2) `FrozenFluentError.__traceback__` retained resolver frames. Both are now eliminated at source. The fuzzer still runs `gc.collect()` every 256 iterations as a defensive measure against Atheris instrumentation overhead, and defaults to `-rss_limit_mb=4096` as a safety net.

### Allowed Exceptions

`CacheCorruptionError`, `FormattingIntegrityError`, `WriteConflictError`, `FrozenFluentError`, `RecursionError`, `MemoryError` -- integrity violations are findings; depth guards and resource limits are safety mechanisms.

---

## `fuzz_scope`

Target: `runtime.resolver` (via `FluentBundle`) -- variable scoping, term argument isolation, message reference scope inheritance, ResolutionContext push/pop, GlobalDepthGuard cross-context depth tracking, select expression scope, bidi isolation marks.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `term_arg_isolation` | 12 | Terms see ONLY explicit args, not caller's scope |
| `variable_shadowing` | 12 | External $var preserved around term call |
| `message_ref_scope` | 10 | Referenced messages share caller's args |
| `select_scope` | 10 | Selector and variant bodies share message scope |
| `attribute_scope` | 8 | Attribute patterns share message scope |
| `bidi_isolation` | 8 | FSI/PDI wrap values, don't alter content |
| `function_arg_scope` | 8 | Function args evaluated in calling scope |
| `nested_term_scope` | 8 | Nested terms maintain independent scopes |
| `scope_chain` | 8 | Message ref chains share args (depth 2-4) |
| `cross_message_isolation` | 6 | Independent messages don't pollute each other |
| `depth_guard_boundary` | 5 | Self-ref, mutual recursion, deep chains hit limits |
| `adversarial_scope` | 5 | Scope leaks, missing vars, empty values, fuzzed IDs |

### Allowed Exceptions

`ValueError`, `TypeError`, `OverflowError`, `FrozenFluentError`, `RecursionError`, `RuntimeError` -- invalid inputs, depth guard enforcement, and resolution errors.

---

## `fuzz_structured`

Target: `syntax.parser.FluentParserV1`, `syntax.serializer.FluentSerializer` -- grammar-aware AST construction and roundtrip verification.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `simple_messages` | 10 | Parse produces entries |
| `variable_messages` | 12 | Variable placeables parse correctly |
| `term_definitions` | 8 | Term definitions accepted |
| `attribute_messages` | 10 | Attribute parsing |
| `select_expressions` | 15 | Select with plural/string keys |
| `comment_entries` | 5 | Comment parsing |
| `multi_entry` | 15 | Multi-message resource handling |
| `corrupted_input` | 10 | Malformed input stability |
| `deep_nesting` | 8 | Deep placeable/reference nesting |
| `roundtrip_verify` | 7 | S(P(S(P(x)))) == S(P(x)) convergence |

### Allowed Exceptions

`RecursionError`, `MemoryError`, `UnicodeDecodeError`, `UnicodeEncodeError` -- resource limits and encoding edge cases.

---

## Observability Standard

All fuzzers share:

- `FuzzerState` dataclass with bounded deques
- psutil RSS memory tracking with leak detection (quartile comparison)
- Performance percentiles: min/mean/median/p95/p99/max
- Per-pattern wall-time accumulation
- Crash-proof JSON report via `atexit` (stderr + `.fuzz_corpus/<target>/`)
- argparse CLI (`--checkpoint-interval`, `--seed-corpus-size`)
- Top-10 slowest operations (max-heap)
- FIFO seed corpus management with configurable max size
