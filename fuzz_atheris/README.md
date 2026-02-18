---
afad: "3.2"
version: "0.112.0"
domain: fuzzing
updated: "2026-02-18"
route:
  keywords: [fuzzing, coverage, atheris, libfuzzer, fuzz, seeds, corpus]
  questions: ["what do the fuzzers cover?", "what modules are fuzzed?", "what is not fuzzed?"]
---

# Fuzzer Coverage Inventory

**Purpose**: Stock-taking of what the Atheris/libFuzzer fuzzing infrastructure covers, enabling gap analysis and planning.

## Fuzzer Summary

| Fuzzer | Target Module(s) | Patterns | Seeds | Concern |
|:-------|:-----------------|:---------|:------|:--------|
| `fuzz_bridge.py` | `runtime.function_bridge` | 15 | 18 (.bin) | FunctionRegistry machinery, FluentNumber contracts |
| `fuzz_graph.py` | `analysis.graph` | 12 | 12 (.bin) | Dependency graph cycle detection, canonicalization |
| `fuzz_builtins.py` | `runtime.functions` | 13 | 20 (.bin) | Babel formatting boundary (NUMBER, DATETIME, CURRENCY) |
| `fuzz_cache.py` | `runtime.bundle`, `runtime.cache`, `integrity` | 14 | 43 (.ftl) + 5 (.bin) | Cache concurrency and integrity |
| `fuzz_currency.py` | `parsing.currency` | 16 | 65 (.txt) | Currency symbol extraction |
| `fuzz_fiscal.py` | `parsing.fiscal` | 10 | 18 (.bin) | Fiscal calendar arithmetic, contracts |
| `fuzz_integrity.py` | `validation`, `syntax.validator`, `integrity` | 25 | 68 (.ftl) + 13 (.bin) | Semantic validation, strict mode, cross-resource |
| `fuzz_iso.py` | `introspection.iso` | 9 | 17 (.bin) | ISO 3166/4217 introspection |
| `fuzz_lock.py` | `runtime.rwlock` | 17 | 32 (.bin) | RWLock concurrency primitives |
| `fuzz_numbers.py` | `parsing.numbers` | 19 | 70 (.txt) | Locale-aware numeric parsing |
| `fuzz_plural.py` | `runtime.plural_rules` | 10 | 20 (.bin) | CLDR plural category selection |
| `fuzz_oom.py` | `syntax.parser` | 16 | 42 (.ftl) + 1 (.bin) | Parser object explosion (DoS) |
| `fuzz_roundtrip.py` | `syntax.parser`, `syntax.serializer` | 13 | 18 (.bin) + 4 (.ftl) | Parser-serializer convergence |
| `fuzz_runtime.py` | `runtime.bundle`, `runtime.cache`, `integrity`, `diagnostics.errors` | 6+8 | 73 (.bin) | Full runtime stack, strict mode |
| `fuzz_serializer.py` | `syntax.serializer`, `syntax.parser` | 10 | 12 (.bin) | AST-construction serializer roundtrip |
| `fuzz_scope.py` | `runtime.resolver`, `runtime.bundle` | 12 | 12 (.bin) | Variable scoping, term isolation, depth guards |
| `fuzz_structured.py` | `syntax.parser`, `syntax.serializer` | 10 | 16 (.ftl) | Grammar-aware AST construction |

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
| `runtime.function_bridge` | bridge |
| `runtime.functions` | builtins, runtime |
| `runtime.bundle` | runtime, cache, integrity, scope |
| `runtime.resolver` | scope |
| `runtime.cache` | runtime, cache |
| `runtime.plural_rules` | plural |
| `runtime.rwlock` | lock |
| `syntax.parser` | oom, roundtrip, serializer, structured |
| `syntax.serializer` | roundtrip, serializer, structured |
| `validation` | integrity |

## `fuzz_bridge`

Target: `runtime.function_bridge` -- FunctionRegistry lifecycle, `_to_camel_case`, parameter mapping, FluentNumber contracts, `fluent_function` decorator, freeze/copy isolation, dict-like interface, metadata API, signature validation error paths.

Concern boundary: This fuzzer stress-tests the bridge machinery that connects FTL function calls to Python implementations. Distinct from fuzz_builtins which tests built-in functions (NUMBER, DATETIME, CURRENCY) through the bridge; this fuzzer tests the bridge itself: registration, dispatch, parameter conversion, lifecycle, and introspection. Tests registration error paths (inject_locale arity validation, underscore collision detection, auto-naming), metadata API (get_expected_positional_args, get_builtin_metadata, has_function), and adversarial Python objects through FluentBundle resolution.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `BridgeMetrics` dataclass (register calls/failures, call dispatch tests/errors, FluentNumber checks, camel case tests, freeze/copy tests, locale injection tests, signature validation tests, metadata API tests, evil object tests). Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

15 patterns across 4 categories:

**REGISTRATION (4)** - Function registration and validation:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `register_basic` | 10 | len(registry) matches registration count |
| `register_signatures` | 12 | Positional-only, *args, **kwargs, many params, lambda, overwrite |
| `param_mapping_custom` | 8 | Custom param_map overrides auto-generated mapping |
| `signature_validation` | 6 | inject_locale arity TypeError, underscore collision ValueError, auto-naming |

**CONTRACTS (3)** - Object immutability and type contracts:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `fluent_number_contracts` | 12 | str, __contains__, __len__, repr, frozen, precision=None |
| `signature_immutability` | 5 | FunctionSignature frozen, param_mapping tuple, ftl_name, fuzzed lookup |
| `camel_case_conversion` | 10 | Known snake->camelCase pairs, fuzzed input returns str |

**DISPATCH (4)** - Call dispatch and error handling:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `call_dispatch` | 12 | call() returns result or raises for unknown function |
| `locale_injection` | 10 | should_inject_locale flag, FluentBundle locale protocol |
| `error_wrapping` | 7 | TypeError/ValueError wrapped as FrozenFluentError |
| `evil_objects` | 5 | Evil __str__, __hash__, recursive list/dict, huge str, None through FluentBundle |

**INTROSPECTION (4)** - Registry introspection and lifecycle:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `dict_interface` | 8 | __contains__, __iter__, list_functions, get_python_name, get_callable, __repr__ |
| `freeze_copy_lifecycle` | 8 | Freeze prevents registration, copy is independent+unfrozen, idempotent |
| `fluent_function_decorator` | 8 | Bare, parenthesized, inject_locale=True attribute, registry integration |
| `metadata_api` | 6 | get_expected_positional_args, get_builtin_metadata, has_function vs __contains__ |

### Allowed Exceptions

`ValueError`, `TypeError`, `OverflowError`, `ArithmeticError`, `FrozenFluentError`, `RecursionError`, `RuntimeError` -- invalid inputs, frozen registry mutations, and adversarial object interactions.

---

## `fuzz_builtins`

Target: `runtime.functions` (NUMBER, DATETIME, CURRENCY) -- direct Babel formatting API boundary testing.

Concern boundary: This fuzzer stress-tests the Babel formatting boundary by calling NUMBER, DATETIME, and CURRENCY functions directly through the Python API. This is distinct from fuzz_runtime which invokes these functions through FTL syntax and the resolver stack. Direct API testing isolates the Babel layer from resolver/cache behavior and enables: fuzz-generated Babel pattern strings (pattern= parameter), FluentNumber precision (CLDR v operand) correctness verification, currency-specific decimal digit enforcement (JPY=0, BHD=3), type coercion across int/float/Decimal/FluentNumber inputs, cross-locale formatting consistency, and edge value handling (NaN, Inf, -0.0, extreme magnitudes). FunctionRegistry lifecycle, parameter mapping, and locale injection protocol are covered by fuzz_bridge.py.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `BuiltinsMetrics` dataclass (per-function call counts, precision checks/violations, cross-locale tests, type coercion tests, determinism tests, custom pattern tests, edge value tracking). Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

13 patterns across 4 categories:

**NUMBER (4)** - Decimal/FluentNumber formatting:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `number_basic` | 12 | Result is FluentNumber, fraction/grouping variation |
| `number_precision` | 15 | CLDR v operand non-negative, min_frac consistency |
| `number_edges` | 8 | NaN, Inf, -0.0, huge, tiny stability |
| `number_type_variety` | 8 | int/float/Decimal/FluentNumber all produce FluentNumber |

**DATETIME (3)** - Date/time formatting:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `datetime_styles` | 10 | Non-empty string result, all style combos |
| `datetime_edges` | 8 | Epoch, Y2K, max timestamp, timezone offsets |
| `datetime_timezone_stress` | 6 | Fixed-offset timezones (-12h to +14h), UTC, naive |

**CURRENCY (3)** - Currency formatting:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `currency_codes` | 12 | FluentNumber result, valid/fuzzed ISO codes |
| `currency_precision` | 10 | Currency-specific decimals (JPY=0, BHD=3) |
| `currency_cross_locale` | 8 | Same currency formatted across locales |

**CROSS-CUTTING (3)** - Multi-function and consistency:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `custom_pattern` | 8 | Custom Babel patterns for all 3 functions |
| `cross_locale_consistency` | 8 | Same value, 3+ locales, deterministic results |
| `error_paths` | 5 | Negative/huge fraction digits, empty/invalid currency |

### Allowed Exceptions

`ValueError`, `TypeError`, `OverflowError`, `InvalidOperation`, `OSError`, `ArithmeticError` -- invalid inputs and Babel formatting limitations.

---

## `fuzz_cache`

Target: `runtime.cache` (via `FluentBundle` public API) -- cache parameter combinations, multi-threaded access (2-8 threads), LRU eviction stress, concurrent resource modification, write-once cache behavior, cache key complexity.

Concern boundary: This fuzzer stress-tests the cache subsystem by systematically varying ALL cache constructor parameters (size, entry weight, error limits, write-once, audit mode) under concurrent multi-threaded access. This is distinct from the runtime fuzzer which tests the full resolver stack with fixed cache configs and only 2 threads. Unique coverage includes: cache parameter combinations (5 params = large state space), high thread concurrency (2-8 threads vs runtime's 2), cache eviction/LRU stress, concurrent resource modification during formatting, write-once cache behavior, and cache key complexity via `_make_hashable`.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `CacheMetrics` dataclass (cache operations, write conflicts, oversize skips, error bloat, corruption events, thread timeouts). Cache stats (hits, misses, oversize skips, error bloat, corruption) collected per-iteration via `bundle.get_cache_stats()` public API and accumulated into domain metrics. Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

14 patterns across 3 categories:

**CACHE_KEYS (7)** - Cache key variation and complexity:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `variable_messages` | 10 | Cache key varies with args |
| `attribute_messages` | 8 | Attribute-qualified cache keys |
| `select_expressions` | 8 | Complex pattern caching |
| `message_references` | 6 | Cross-message resolution cache |
| `term_references` | 6 | Namespace variation in keys |
| `many_variables` | 6 | Key complexity scaling (5-10 placeables) |
| `deep_args` | 8 | Nested dicts/lists, unhashable types stress `_make_hashable` |

**STRESS_PATTERNS (4)** - Capacity and resource stress:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `long_values` | 5 | Memory weight enforcement |
| `circular_refs` | 5 | Error caching on cycles |
| `minimal_resource` | 4 | Empty/trivial resource edge cases |
| `hotspot` | 8 | Repeated access cache hit efficiency |

**CONCURRENCY (3)** - Multi-threaded scenarios:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `capacity_stress` | 10 | LRU eviction under capacity pressure |
| `concurrent_modify` | 8 | Race conditions: resource modification during formatting |
| `frozen_cache` | 8 | Write-once cache behavior (immutable entries) |

### Allowed Exceptions

`CacheCorruptionError`, `WriteConflictError`, `DataIntegrityError`, `FrozenFluentError`, `ValueError`, `TypeError`, `KeyError`, `RecursionError`, `MemoryError` -- cache integrity violations are expected findings; other exceptions from invalid inputs and depth guards.

---

## `fuzz_graph`

Target: `analysis.graph` -- `_canonicalize_cycle`, `make_cycle_key`, `detect_cycles`, `entry_dependency_set`. Validates cycle detection correctness, canonicalization invariants, and namespace-prefixed dependency set construction.

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
| `entry_dependency_set` | 10 | Namespace prefixing, frozenset return, count preservation |
| `adversarial_graph` | 5 | Unicode node IDs, empty strings, whitespace-only identifiers |

### Allowed Exceptions

`ValueError`, `TypeError`, `RecursionError` -- invalid inputs and graph construction edge cases.

---

## `fuzz_currency`

Target: `parsing.currency.parse_currency` -- longest-match-first symbol detection, ambiguous symbol resolution, numeric extraction across locales.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `unambiguous_unicode` | 8 | Unique symbols resolve unambiguously |
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

Target: `parsing.fiscal` -- `FiscalCalendar`, `FiscalDelta`, `FiscalPeriod`, `MonthEndPolicy`, and 5 convenience functions (`fiscal_quarter`, `fiscal_year`, `fiscal_month`, `fiscal_year_start`, `fiscal_year_end`). Tests date arithmetic correctness, boundary conditions, month-end policy handling, algebraic properties, type validation error paths, and immutability contracts.

Concern boundary: Sole owner of the `parsing.fiscal` module. No other fuzzer imports or exercises any fiscal API. Tests FiscalCalendar cross-consistency (fiscal_year/quarter/month/period agreement, quarter contiguity, year span 365/366), FiscalDelta algebraic properties (commutativity, double negation, __sub__ == __add__ + __neg__, __mul__/__rmul__ symmetry, total_months), cross-policy ValueError enforcement, MonthEndPolicy CLAMP/STRICT invariants, FiscalPeriod frozen dataclass contracts (hash, eq, ordering, repr, validation), and convenience function oracle testing against FiscalCalendar methods.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `FiscalMetrics` dataclass (per-pattern check counts). Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

10 patterns across 4 categories:

**CALENDAR (3)** - FiscalCalendar invariants and identity:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `calendar_invariants` | 15 | Quarter 1-4, month 1-12, date in fiscal year, period agreement |
| `quarter_boundaries` | 10 | Quarter start/end contiguous, span 365/366 days |
| `calendar_identity` | 5 | Hash, equality, repr, frozen, type validation, range validation |

**ARITHMETIC (4)** - FiscalDelta operations and policies:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `delta_add_subtract` | 12 | add_to returns date, subtract_from == negate().add_to(), CLAMP month-end, STRICT ValueError |
| `delta_algebra` | 12 | Commutativity, double negation, __neg__ == negate(), total_months, __mul__/__rmul__, __sub__ |
| `policy_cross` | 8 | with_policy preserves components, cross-policy add/sub ValueError, all policies valid |
| `delta_validation` | 5 | Non-int fields TypeError, non-MonthEndPolicy TypeError, valid construction |

**CONTRACTS (2)** - Immutability and oracle testing:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `period_contracts` | 8 | Hash, equality, ordering (__lt__/__gt__/__le__/__ge__), frozen, repr, validation |
| `convenience_oracle` | 8 | All 5 convenience functions match FiscalCalendar methods |

**STRESS (1)** - Boundary conditions:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `boundary_stress` | 5 | Extreme dates (year 1-9999), large deltas, result type assertion |

### Allowed Exceptions

`ValueError`, `OverflowError`, `TypeError` -- invalid dates, arithmetic overflow, and type validation.

---

## `fuzz_integrity`

Target: `validation.validate_resource` (standalone 6-pass validation), `syntax.validator.SemanticValidator` (E0001-E0013), `integrity` (DataIntegrityError hierarchy), `FluentBundle` strict mode (SyntaxIntegrityError, FormattingIntegrityError).

Concern boundary: Validation gauntlet -- semantic integrity checks, cross-resource validation with `known_messages`/`known_terms`/`known_msg_deps`, chain depth limits (>MAX_DEPTH), strict mode DataIntegrityError triggering. Distinct from fuzz_graph (direct cycle detection API) and fuzz_runtime (resolver stack, not validation).

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `IntegrityMetrics` dataclass (validation codes, strict mode exceptions, cross-resource conflicts, chain depth violations). Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

25 patterns across 4 categories:

**VALIDATION (10)** - Standalone `validate_resource()`:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `valid_simple` | 8 | Valid FTL accepted without errors |
| `valid_complex` | 6 | Multi-entry with refs, terms, selects |
| `syntax_errors` | 8 | Junk extraction, parse error codes |
| `undefined_refs` | 10 | UNDEFINED_REFERENCE warning |
| `circular_2way` | 8 | 2-node cycle detection |
| `circular_3way` | 6 | 3-node cycle detection |
| `circular_self` | 6 | Self-reference detection |
| `duplicate_ids` | 8 | DUPLICATE_ID warning |
| `chain_depth_limit` | 10 | CHAIN_DEPTH_EXCEEDED for >MAX_DEPTH |
| `mixed_issues` | 6 | Multiple validation issues |

**SEMANTIC (6)** - SemanticValidator (E0001-E0013):

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `semantic_no_default` | 8 | SELECT_NO_DEFAULT detection |
| `semantic_duplicate_variant` | 6 | VARIANT_DUPLICATE detection |
| `semantic_duplicate_named_arg` | 6 | NAMED_ARG_DUPLICATE detection |
| `semantic_term_positional` | 6 | TERM_POSITIONAL_ARGS warning |
| `semantic_no_variants` | 6 | Malformed select -> Junk |
| `semantic_combined` | 5 | Multiple semantic issues |

**STRICT_MODE (5)** - DataIntegrityError triggering:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `strict_syntax_junk` | 10 | SyntaxIntegrityError on Junk |
| `strict_format_missing` | 8 | FormattingIntegrityError on missing msg |
| `strict_format_cycle` | 6 | Cycle in format triggers error |
| `strict_add_invalid` | 8 | Multiple Junk -> SyntaxIntegrityError |
| `strict_combined` | 5 | Various strict mode failures |

**CROSS_RESOURCE (4)** - Multi-resource scenarios:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `cross_shadow` | 8 | SHADOW_WARNING with known_messages |
| `cross_cycle` | 10 | Cross-resource cycle via known_msg_deps |
| `cross_undefined` | 8 | Reference resolved by known_messages |
| `cross_chain_depth` | 6 | Chain depth spanning resources |

### Allowed Exceptions

`DataIntegrityError` (and subclasses), `FrozenFluentError`, `ValueError`, `TypeError`, `KeyError`, `RecursionError`, `MemoryError` -- expected for strict mode and adversarial inputs.

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

Target: `runtime.rwlock.RWLock`, `with_read_lock`, `with_write_lock` -- reader/writer exclusion, reentrancy, downgrading, timeout, deadlock detection, negative timeout rejection, release-without-acquire rejection, zero-timeout non-blocking paths.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `LockMetrics` dataclass (deadlocks detected, timeouts, thread creation count, max concurrent threads). Weight skew detection compares actual vs intended pattern distribution. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default. Corpus retention rate and eviction tracking enabled.

### Patterns

Ordered cheapest-first. Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias that caused severe weight skew under FDP-based selection. Seed files provide FDP parameter bytes only (pattern is determined by iteration counter).

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `reentrant_reads` | 5 | Same thread acquires read lock N times |
| `reentrant_writes` | 5 | Same thread acquires write lock N times |
| `negative_timeout` | 4 | Negative timeout raises ValueError, lock still usable |
| `release_without_acquire` | 4 | Release without acquire raises RuntimeError, lock still usable |
| `upgrade_rejection` | 8 | Read-to-write upgrade raises RuntimeError |
| `decorator_correctness` | 6 | with_read_lock/with_write_lock return values |
| `zero_timeout_nonblocking` | 5 | timeout=0.0 fails immediately when lock held, sub-1ms |
| `write_to_read_downgrade` | 10 | Writer acquires reads, persist after write release |
| `rapid_lock_cycling` | 8 | Shared counter correct after rapid cycles |
| `cross_thread_handoff` | 6 | Rapid write handoff between threads, no lost entries |
| `concurrent_readers` | 12 | Multiple readers hold lock simultaneously |
| `timeout_acquisition` | 8 | TimeoutError raised, lock usable after timeout |
| `downgrade_then_contention` | 8 | Converted reads block writers, properly releasable |
| `reader_writer_exclusion` | 15 | No concurrent reader+writer, no multi-writer |
| `writer_preference` | 10 | Waiting writer blocks new readers (fuzz-controlled timing) |
| `reader_starvation` | 6 | Continuous readers cannot starve waiting writer |
| `mixed_contention` | 7 | All operations interleaved across threads |

### Allowed Exceptions

`RuntimeError`, `TimeoutError`, `ValueError` -- expected from upgrade rejection, lock protocol violations, negative timeout rejection, and timeout-based acquisition.

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

Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. FDP bytes are used exclusively for pattern parameters, not pattern selection. String and RegEx instrumentation hooks enabled for deeper coverage of identifier lookups and pattern-based parsing. Custom mutator parses valid FTL, applies AST-level mutations (swap variants, duplicate attributes, mutate variant keys, nest placeables, shuffle entries) using `dataclasses.replace()` on frozen AST nodes, serializes, then applies byte-level mutation on top. Multi-pass convergence checks (S2 == S3 == S4) verify serialization stabilizes within 3 passes. AST structural comparison (ignoring spans) catches bugs where serialization normalizes structural differences that string comparison misses. Junk ratio tracked and warned when >50%. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

When a convergence failure is detected, the fuzzer writes finding artifacts (source.ftl, s1.ftl, s2.ftl, meta.json) to `.fuzz_atheris_corpus/roundtrip/findings/`. These artifacts enable post-mortem debugging without Atheris and can be replayed via `python fuzz_atheris/fuzz_atheris_replay_finding.py`.

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
| `convergence_stress` | 5 | Multi-pass S2 == S3 == S4 stabilization |

### Allowed Exceptions

`ValueError`, `RecursionError`, `MemoryError`, `UnicodeDecodeError`, `UnicodeEncodeError` -- parser/serializer resource limits and encoding edge cases.

---

## `fuzz_serializer`

Target: `syntax.serializer.serialize`, `syntax.parser.FluentParserV1` -- AST-construction serializer roundtrip idempotence via programmatically built AST nodes.

Concern boundary: This fuzzer programmatically constructs AST nodes (bypassing the parser) and feeds them to the serializer. This is the ONLY Atheris fuzzer that can produce AST states the parser would never emit -- e.g. TextElement values with leading whitespace, syntax characters in pattern-initial positions, or structurally valid but semantically unusual combinations. Addresses the blind spot where text-based fuzzers (fuzz_roundtrip, fuzz_structured) start from the parser, which normalizes inputs before the serializer sees them. Created in response to BUG-SERIALIZER-LEADING-WS-001.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, `gen_ftl_identifier`, `gen_ftl_value`, `write_finding_artifact`, `print_fuzzer_banner`, metrics, reporting); domain-specific metrics tracked in `SerializerMetrics` dataclass (ast_construction_failures, convergence_failures, junk_on_reparse, validation_errors). Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Custom mutator applies whitespace injection and syntax character insertion mutations before byte-level mutation. Finding artifacts written to `.fuzz_atheris_corpus/serializer/findings/`. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

10 patterns across 4 categories:

**WHITESPACE (2)** - Leading/trailing whitespace in TextElement values:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `leading_whitespace` | 18 | Leading spaces in message and attribute values roundtrip correctly |
| `trailing_whitespace` | 8 | Trailing spaces in values roundtrip correctly |

**SYNTAX (2)** - FTL syntax characters in values:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `syntax_chars_value` | 15 | Braces, dots, hash, asterisk, brackets in values |
| `string_literal_placeable` | 10 | StringLiteral placeables with edge-case content |

**STRUCTURE (4)** - Structural edge cases:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `simple_message` | 8 | Baseline AST-constructed message roundtrip |
| `attribute_edge_cases` | 12 | Attributes with whitespace/syntax-char values |
| `term_edge_cases` | 8 | Terms with whitespace in values and attributes |
| `select_expression` | 8 | AST-constructed select expressions with leading-space variant values |

**COMPOSITION (2)** - Complex element combinations:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `mixed_elements` | 8 | Interleaved TextElement/Placeable with leading spaces |
| `multiline_value` | 5 | Multi-line values with indentation edge cases |

### Allowed Exceptions

`ValueError`, `TypeError`, `RecursionError`, `MemoryError`, `UnicodeDecodeError`, `UnicodeEncodeError` -- AST construction edge cases, serializer limits, and encoding boundaries.

---

## `fuzz_runtime`

Target: `runtime.bundle.FluentBundle` -- full resolver stack, strict mode, caching, concurrency, security.

Scenario selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Security sub-pattern selection within `_perform_security_fuzzing` remains FDP-based (second-level, already guaranteed execution). FDP bytes are used exclusively for scenario parameters, not scenario selection. String and RegEx instrumentation hooks enabled for deeper coverage of message ID lookups, selector matching, and pattern-based parsing. Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `RuntimeMetrics` dataclass. Weight skew detection compares actual vs intended scenario distribution. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

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

Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. FDP bytes are used exclusively for pattern parameters, not pattern selection. String and RegEx instrumentation hooks enabled for deeper coverage of identifier lookups and pattern-based parsing. Custom mutator parses valid FTL, applies AST-level mutations (swap variants, duplicate attributes, mutate variant keys, nest placeables, shuffle entries), serializes, then applies byte-level mutation on top. Module-level `FluentSerializer` instance reused across iterations (avoids per-call allocation). Junk ratio tracked and warned when >50%. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

When a convergence failure is detected, the fuzzer writes finding artifacts (source.ftl, s1.ftl, s2.ftl, meta.json) to `.fuzz_atheris_corpus/structured/findings/`. These artifacts enable post-mortem debugging without Atheris and can be replayed via `python fuzz_atheris/fuzz_atheris_replay_finding.py`.

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

All fuzzers import shared infrastructure from `fuzz_common.py` (`BaseFuzzerState`, metrics, reporting) and compose domain-specific metrics via separate dataclasses:

- `BaseFuzzerState` dataclass with bounded deques (shared via `fuzz_common`)
- Domain metrics: `RoundtripMetrics`, `SerializerMetrics`, `StructuredMetrics`, `RuntimeMetrics`, `LockMetrics`, `IntegrityMetrics`, `CacheMetrics`, `BuiltinsMetrics`, `BridgeMetrics`, `FiscalMetrics`, `ISOMetrics`, `CurrencyMetrics`, `NumbersMetrics`, `OOMMetrics`, `PluralMetrics`, `ScopeMetrics` (per-fuzzer)
- psutil RSS memory tracking with leak detection (quartile comparison)
- Performance percentiles: min/mean/median/p95/p99/max
- Per-pattern wall-time accumulation
- Weight skew detection: actual vs intended distribution per pattern, warns when >3x deviation
- Corpus retention rate: `corpus_evictions` / `corpus_entries_added` tracks FIFO churn
- Crash-proof JSON report via `atexit` (stderr + `.fuzz_atheris_corpus/<target>/`)
- argparse CLI (`--checkpoint-interval`, `--seed-corpus-size`)
- Top-10 slowest operations (max-heap)
- FIFO seed corpus management (`dict[str, bytes]`) with configurable max size and eviction tracking
- Deterministic round-robin weighted pattern routing (immune to coverage-guided mutation bias)
- Pattern-stratified corpus retention (per-pattern FIFO buckets preserve diversity)
- `atheris.enabled_hooks` for `str` and `RegEx` comparison feedback
- Periodic `gc.collect()` every 256 iterations
- `-rss_limit_mb=4096` default safety net
- Custom mutator (roundtrip, serializer, structured): AST-level mutations + byte-level mutation for structurally valid inputs
- Finding artifact system (roundtrip, serializer, structured): source/s1/s2/meta.json written to `.fuzz_atheris_corpus/<target>/findings/`
- `fuzz_atheris_replay_finding.py`: standalone reproduction of finding artifacts without Atheris instrumentation
- Adaptive time budgets: patterns exceeding 10x their mean cost are tracked (`time_budget_skips`)
- Performance outlier tracking: inputs exceeding 2x P99 latency are recorded with timestamps
- Per-pattern mean cost tracking: exponential moving average for cost-aware scheduling
- Graceful Ctrl+C handling: custom mutators catch `KeyboardInterrupt` and set status to "stopped"
- FTL-safe text generation (structured): 90% safe ASCII, 8% Unicode, 2% inline-safe special chars
- Consolidated `record_iteration_metrics`: single function for all fuzzers (time budgets, outlier tracking, corpus retention)
- Common FTL generation: `gen_ftl_identifier` and `gen_ftl_value` for deterministic FDP-based identifier/value generation
- Common finding artifacts: `write_finding_artifact` with parametric `extra_meta` for per-fuzzer metadata
- Common banner: `print_fuzzer_banner` for consistent startup output across all fuzzers
