---
afad: "3.3"
version: "0.153.0"
domain: FUZZING
updated: "2026-03-13"
route:
  keywords: [fuzzing, coverage, atheris, libfuzzer, fuzz, seeds, corpus]
  questions: ["what do the fuzzers cover?", "what modules are fuzzed?", "what is not fuzzed?"]
---

# Fuzzer Coverage Inventory

**Purpose**: Stock-taking of what the Atheris/libFuzzer fuzzing infrastructure covers, enabling gap analysis and planning.

## Fuzzer Summary

| Fuzzer | Target Module(s) | Patterns | Seeds | Concern |
|:-------|:-----------------|:---------|:------|:--------|
| `fuzz_bridge.py` | `runtime.function_bridge`, `runtime.value_types` | 16 | 33 (.bin) | FunctionRegistry machinery, FluentNumber contracts, `make_fluent_number()` |
| `fuzz_graph.py` | `analysis.graph` | 12 | 24 (.bin) | Dependency graph cycle detection, canonicalization |
| `fuzz_builtins.py` | `runtime.functions` | 13 | 24 (.bin) | Babel formatting boundary (NUMBER, DATETIME, CURRENCY) |
| `fuzz_cache.py` | `runtime.bundle`, `runtime.cache`, `integrity` | 14 | 38 (.ftl) + 15 (.bin) | Cache concurrency, integrity, and public audit-trail access |
| `fuzz_currency.py` | `runtime.functions` | 8 | 65 (.txt) + 23 (.bin) | ROUND_HALF_UP oracle, custom `pattern=` precision alignment, locale matrix (CURRENCY) |
| `fuzz_parse_currency.py` | `parsing.currency`, `parsing.guards` | 9 | 5 (.txt) + 20 (.bin) | Locale-aware currency parsing, symbol disambiguation, cache stability |
| `fuzz_fiscal.py` | `parsing.fiscal` | 10 | 38 (.bin) | Fiscal calendar arithmetic, contracts |
| `fuzz_integrity.py` | `validation`, `syntax.validator`, `integrity`, `diagnostics.errors` | 29 | 68 (.ftl) + 35 (.bin) | Semantic validation, strict mode, cross-resource, FrozenFluentError Error Layer |
| `fuzz_iso.py` | `introspection.iso` | 10 | 36 (.bin) | ISO 3166/4217 introspection; `get_currency_decimal_digits` oracle |
| `fuzz_lock.py` | `runtime`, `runtime.rwlock` | 16 | 39 (.bin) | RWLock concurrency primitives and public runtime export |
| `fuzz_numbers.py` | `runtime.functions` | 8 | 70 (.txt) + 18 (.bin) | ROUND_HALF_UP oracle, custom `pattern=` path, boundary values, min>max clamping (NUMBER) |
| `fuzz_parse_decimal.py` | `parsing.numbers`, `parsing.guards`, `core.locale_utils` | 9 | 9 (.txt) + 1 (.bin) | Locale-aware decimal parsing, FluentNumber parsing, locale normalization/cache behavior, boundary locale validation, pseudo-locale fallback |
| `fuzz_plural.py` | `runtime.plural_rules` | 10 | 37 (.bin) | CLDR plural category selection |
| `fuzz_oom.py` | `syntax.parser` | 16 | 42 (.ftl) + 8 (.bin) | Parser object explosion (DoS) |
| `fuzz_roundtrip.py` | `syntax.parser`, `syntax.serializer` | 13 | 31 (.bin) + 4 (.ftl) | Parser-serializer convergence |
| `fuzz_runtime.py` | `runtime.bundle`, `runtime.cache`, `integrity`, `diagnostics.errors` | 6+8 | 100 (.bin) | Full runtime stack, strict mode, FluentBundle AST lookup facade, canonical locale boundary |
| `fuzz_serializer.py` | `syntax.serializer`, `syntax.parser`, `syntax.visitor` | 13 | 26 (.bin) | AST-construction serializer roundtrip, visitor/transformer validation |
| `fuzz_scope.py` | `runtime.resolver`, `runtime.bundle` | 13 | 29 (.bin) | Variable scoping, term isolation, depth guards, expansion budget |
| `fuzz_structured.py` | `syntax.parser`, `syntax.serializer` | 10 | 16 (.ftl) + 6 (.bin) | Grammar-aware AST construction |
| `fuzz_cursor.py` | `syntax.cursor`, `syntax.position` | 8 | 5 (.txt) + 35 (.bin) | Cursor state machine, ParseError formatting, position helper parity |
| `fuzz_localization.py` | `localization.orchestrator`, `localization.loading` | 22 | 13 (.bin) | FluentLocalization orchestration, canonical locale boundary, boot validation, single-message schema validation, AST lookup, cache audit trails, loader init, LoadSummary, fallback chains |
| `fuzz_dates.py` | `parsing.dates` | 14 | 59 (.bin) | CLDR→strptime token mapping, parse_date/parse_datetime locale-aware parsing; 4-digit year oracle (lv-LV/de-DE) |
| `fuzz_locale_context.py` | `runtime.locale_context`, `core.locale_utils` | 14 | 25 (.bin) | LocaleContext direct formatting, canonical locale_code contract, ROUND_HALF_UP oracle, cross-locale determinism |
| `fuzz_introspection.py` | `introspection.message` | 13 | 25 (.bin) | IntrospectionVisitor, ReferenceExtractor, programmatic AST construction; `validate_message_variables` schema oracle |
| `fuzz_diagnostics_formatter.py` | `diagnostics.formatter`, `diagnostics.validation` | 12 | 23 (.bin) | Control-char escaping, RUST/SIMPLE/JSON output, sanitize/redact modes |

## Module Coverage Matrix

| Source Module | Fuzzers Covering It |
|:--------------|:--------------------|
| `analysis.graph` | graph |
| `core.locale_utils` | parse_decimal, runtime, localization, locale_context |
| `diagnostics.errors` | runtime, oom, numbers, currency, cache, integrity, builtins |
| `diagnostics.formatter` | diagnostics_formatter |
| `diagnostics.validation` | diagnostics_formatter, integrity |
| `integrity` | runtime, cache, integrity |
| `introspection.iso` | iso |
| `introspection.message` | introspection |
| `localization.loading` | localization |
| `localization.orchestrator` | localization |
| `parsing.currency` | parse_currency |
| `parsing.dates` | dates |
| `parsing.fiscal` | fiscal |
| `parsing.guards` | parse_currency, parse_decimal |
| `parsing.numbers` | parse_decimal |
| `runtime` | lock |
| `runtime.function_bridge` | bridge |
| `runtime.functions` | builtins, runtime, currency, numbers |
| `runtime.bundle` | runtime, cache, integrity, scope, localization |
| `runtime.locale_context` | locale_context, builtins |
| `runtime.resolver` | scope |
| `runtime.cache` | runtime, cache |
| `runtime.plural_rules` | plural |
| `runtime.rwlock` | lock |
| `runtime.value_types` | bridge |
| `syntax.cursor` | cursor |
| `syntax.parser` | oom, roundtrip, serializer, structured |
| `syntax.position` | cursor |
| `syntax.serializer` | roundtrip, serializer, structured |
| `syntax.visitor` | serializer |
| `validation` | integrity |

## `fuzz_bridge`

Target: `runtime.function_bridge`, `runtime.value_types` -- FunctionRegistry lifecycle, `_to_camel_case`, parameter mapping, FluentNumber contracts, `make_fluent_number()`, `fluent_function` decorator, freeze/copy isolation, dict-like interface, metadata API, signature validation error paths.

Concern boundary: This fuzzer stress-tests the bridge machinery that connects FTL function calls to Python implementations. Distinct from fuzz_builtins which tests built-in functions (NUMBER, DATETIME, CURRENCY) through the bridge; this fuzzer tests the bridge itself: registration, dispatch, parameter conversion, lifecycle, direct FluentNumber construction, and introspection. Tests registration error paths (inject_locale arity validation, underscore collision detection, auto-naming), metadata API (get_expected_positional_args, get_builtin_metadata, has_function), `make_fluent_number()` visible-precision inference, and adversarial Python objects through FluentBundle resolution.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `BridgeMetrics` dataclass (register calls/failures, call dispatch tests/errors, FluentNumber checks, `make_fluent_number()` checks, camel case tests, freeze/copy tests, locale injection tests, signature validation tests, metadata API tests, evil object tests). Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

16 patterns across 4 categories:

**REGISTRATION (4)** - Function registration and validation:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `register_basic` | 10 | len(registry) matches registration count |
| `register_signatures` | 12 | Positional-only, *args, **kwargs, many params, lambda, overwrite |
| `param_mapping_custom` | 8 | Custom param_map overrides auto-generated mapping |
| `signature_validation` | 6 | inject_locale arity TypeError, underscore collision ValueError, auto-naming |

**CONTRACTS (4)** - Object immutability and type contracts:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `fluent_number_contracts` | 12 | str, __contains__, __len__, repr, frozen, precision=None |
| `make_fluent_number_api` | 10 | default Decimal precision, grouped/localized formatting inference, bool rejection |
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

Concern boundary: This fuzzer stress-tests the Babel formatting boundary by calling NUMBER, DATETIME, and CURRENCY functions directly through the Python API. This is distinct from fuzz_runtime which invokes these functions through FTL syntax and the resolver stack. Direct API testing isolates the Babel layer from resolver/cache behavior and enables: fuzz-generated Babel pattern strings (pattern= parameter), FluentNumber precision (CLDR v operand) correctness verification, currency-specific decimal digit enforcement (JPY=0, BHD=3), ROUND_HALF_UP rounding oracle verification (NUMBER and CURRENCY), type coercion across int/float/Decimal/FluentNumber inputs, cross-locale formatting consistency, and edge value handling (NaN, Inf, -0.0, extreme magnitudes). FunctionRegistry lifecycle, parameter mapping, and locale injection protocol are covered by fuzz_bridge.py.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `BuiltinsMetrics` dataclass (per-function call counts, precision checks/violations, cross-locale tests, type coercion tests, custom pattern tests, edge value tracking, rounding oracle checks/violations, min_gt_max coverage). Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

Run this fuzzer in isolation: `./scripts/fuzz_atheris.sh builtins` (uses `.venv-atheris`, independent of the project venv). Linting of this directory is covered by `./scripts/lint.sh` (auto-discovers all directories with `.py` files).

### Patterns

13 patterns across 4 categories:

**NUMBER (4)** - Decimal/FluentNumber formatting:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `number_basic` | 12 | Result is FluentNumber, fraction/grouping variation; independent min/max draws |
| `number_precision` | 15 | CLDR v operand non-negative; ROUND_HALF_UP oracle (all ASCII-digit locales); independent min/max draws (covers min > max clamp path) |
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
| `currency_precision` | 10 | Currency-specific decimals (JPY=0, BHD=3); ROUND_HALF_UP oracle (all ASCII-digit locales) |
| `currency_cross_locale` | 8 | Same currency formatted across locales |

**CROSS-CUTTING (3)** - Multi-function and consistency:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `custom_pattern` | 8 | Custom Babel patterns for all 3 functions |
| `cross_locale_consistency` | 8 | Same value, 3+ locales, deterministic results; independent min/max draws |
| `error_paths` | 5 | Negative/huge fraction digits, empty/invalid currency |

### Allowed Exceptions

`ValueError`, `TypeError`, `OverflowError`, `InvalidOperation`, `OSError`, `ArithmeticError` -- invalid inputs and Babel formatting limitations.

### Rounding Oracle Design

`number_precision` and `currency_precision` include a ROUND_HALF_UP oracle that verifies the pre-quantization applied in `locale_context.py`. ROUND_HALF_UP pre-quantization runs before Babel (not inside it) and applies to every locale; the oracle covers all locales where digit extraction is possible.

**Digit extraction** (`_extract_oracle_digits`): Uses `babel.numbers.get_decimal_symbol(locale)` and `get_group_symbol(locale)` to normalize the formatted string for any locale. Normalization removes group separators first (critical for de-DE where group separator is `.`), replaces the decimal separator with ASCII `.`, then strips all remaining non-digit characters (currency codes, whitespace, signs). Locales with non-ASCII digits (ar-EG Arabic-Indic, hi-IN Devanagari) are detected via `c.isdigit() and not c.isascii()` and skipped. Unknown locales (Babel raises `UnknownLocaleError`) are skipped via `except ValueError`.

**Oracle check**: For each non-NaN/non-Inf Decimal result where `_extract_oracle_digits` returns a value: `expected = abs(val).quantize(10^-precision, rounding=ROUND_HALF_UP)` is compared against the extracted digits. NaN and Infinity skip the oracle via `InvalidOperation` from `quantize()`.

**Input domain**: `min_frac` and `max_frac` are drawn independently (not `max_frac = ConsumeIntInRange(min_frac, N)`). This ensures the `min > max` clamping path in `format_number()` is exercised — a path that previously could trigger incorrect digit counts.

---

## `fuzz_cache`

Target: `runtime.cache` (via `FluentBundle` public API) -- cache parameter combinations, multi-threaded access (2-8 threads), LRU eviction stress, concurrent resource modification, write-once cache behavior, cache key complexity, and public audit-log visibility.

Concern boundary: This fuzzer stress-tests the cache subsystem by systematically varying ALL cache constructor parameters (size, entry weight, error limits, write-once, audit mode) under concurrent multi-threaded access. This is distinct from the runtime fuzzer which tests the full resolver stack with fixed cache configs and only 2 threads. Unique coverage includes: cache parameter combinations (5 params = large state space), high thread concurrency (2-8 threads vs runtime's 2), cache eviction/LRU stress, concurrent resource modification during formatting, write-once cache behavior, cache key complexity via `_make_hashable`, and `FluentBundle.get_cache_audit_log()` consistency against `get_cache_stats()`.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `CacheMetrics` dataclass (cache operations, write conflicts, oversize skips, error bloat, corruption events, audit-log checks, thread timeouts). Cache stats and audit logs are collected per-iteration via `bundle.get_cache_stats()` and `bundle.get_cache_audit_log()`, with invariant checks on tuple shape, `WriteLogEntry` typing, stats/log count agreement, non-decreasing audit timestamps, and operation-specific sequence/checksum structure. Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

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

Target: `runtime.functions.currency_format` -- ROUND_HALF_UP oracle testing, custom `pattern=` precision alignment, locale matrix, display mode preservation, and `FluentNumber` wrapper contracts.

Concern boundary: This fuzzer stress-tests the runtime CURRENCY function formatting path. Distinct from `fuzz_builtins` (which covers NUMBER/DATETIME/CURRENCY via the FTL `FluentBundle` evaluation pipeline); this fuzzer calls `currency_format` directly to probe oracle correctness, custom pattern precision alignment, and boundary-value rounding at precision 0, 2, and 3. Found production bug FIX-CURRENCY-PATTERN-PREC-001 on its first run (~1009 iterations): `format_currency` with a custom pattern and a currency whose CLDR precision differs from the pattern's declared decimal count produced incorrect rounding because `currency_digits=True` caused Babel to override the pattern's decimal count after pre-quantization.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `CurrencyMetrics` dataclass. Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

8 patterns across 4 categories:

**PRECISION (3)** - Per-currency decimal precision and custom pattern precision:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `0decimal_oracle` | 12 | JPY, KRW (0 decimals): ROUND_HALF_UP at integer boundary |
| `3decimal_oracle` | 13 | BHD, KWD, OMR (3 decimals): x.0005 midpoints |
| `pattern_oracle` | 16 | Custom `pattern=` with CLDR-differing currency: precision must match pattern, not CLDR |

**ORACLE (3)** - ROUND_HALF_UP correctness across value ranges:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `boundary_values` | 15 | 2-decimal currencies (USD, EUR, GBP, AUD, CAD, CHF): x.005 midpoints |
| `large_oracle` | 11 | Large positive amounts (>1e6): non-empty, ROUND_HALF_UP preserved |
| `negative_oracle` | 11 | Negative amounts: ROUND_HALF_UP preserved; abs() applied before oracle comparison |

**LOCALE (1)** - Cross-locale consistency:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `locale_matrix` | 11 | Same value across 10 locales: all non-empty, no exception |

**DISPLAY (1)** - Currency display mode contracts:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `display_preservation` | 11 | symbol/code/name: result contains currency identifier; not empty |

### Allowed Exceptions

`ValueError`, `TypeError` -- invalid currency codes and type validation.

---

## `fuzz_parse_currency`

Target: `parsing.currency.parse_currency`, `parsing.currency.resolve_ambiguous_symbol`, `parsing.currency._get_currency_pattern` -- locale-aware currency parsing, ambiguous symbol disambiguation, longest-match symbol regex behavior, and cache stability.

Concern boundary: This fuzzer owns the text-to-`(Decimal, ISO code)` parse surface that the runtime-formatting fuzzers do not reach. It covers ISO-code parsing, symbol-only parsing, `default_currency=` and `infer_from_locale=` disambiguation, public soft-error contracts, direct ambiguous-symbol helper behavior, and cache-clearing stability. It also targets the longest-match regex path for multi-character symbols such as `R$` and `S/`, which is distinct from runtime formatting.

Shared infrastructure imported from `fuzz_common`; domain-specific metrics tracked in `ParseCurrencyMetrics` dataclass. Pattern selection uses deterministic round-robin. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `iso_code_values` | 14 | `USD 1,234.56`-style inputs parse to exact `(Decimal, code)` pairs |
| `default_currency_ambiguous` | 12 | Ambiguous symbols resolve to explicit `default_currency` |
| `infer_from_locale` | 12 | Ambiguous symbols resolve from locale inference when enabled |
| `ambiguous_symbol_resolution` | 10 | `resolve_ambiguous_symbol()` matches locale defaults for `$`, `£`, `¥` |
| `longest_symbol_match` | 10 | Multi-character symbols beat shorter prefixes in regex matching |
| `invalid_currency_inputs` | 12 | Invalid codes/ambiguous inputs return soft errors, not silent success |
| `cache_clear_cycle` | 10 | `clear_currency_caches()` does not change parse semantics |
| `type_guard_contract` | 10 | `is_valid_currency()` accepts valid tuples and rejects malformed values |
| `raw_unicode_stability` | 12 | Arbitrary Unicode inputs preserve the public result-or-errors contract |

### Allowed Exceptions

`ValueError`, `TypeError`, `OSError`, `UnicodeEncodeError`, `FrozenFluentError` -- invalid locale/input handling and soft-error plumbing.

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

Target: `validation.validate_resource` (standalone 6-pass validation), `syntax.validator.SemanticValidator` (E0001-E0013), `integrity` (DataIntegrityError hierarchy), `FluentBundle` strict mode (SyntaxIntegrityError, FormattingIntegrityError), `diagnostics.errors.FrozenFluentError` (integrity, immutability, sealed type, hash stability).

Concern boundary: Validation gauntlet -- semantic integrity checks, cross-resource validation with `known_messages`/`known_terms`/`known_msg_deps`, chain depth limits (>MAX_DEPTH), strict mode DataIntegrityError triggering, and FrozenFluentError Error Layer properties. Distinct from fuzz_graph (direct cycle detection API) and fuzz_runtime (resolver stack, not validation).

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `IntegrityMetrics` dataclass (validation codes, strict mode exceptions, cross-resource conflicts, chain depth violations, FrozenFluentError coverage counters). Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

29 patterns across 5 categories:

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

**FROZEN_ERROR (4)** - FrozenFluentError Error Layer:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `frozen_error_integrity` | 8 | verify_integrity() True for uncorrupted errors across all ErrorCategory values |
| `frozen_error_immutability` | 8 | setattr and delattr raise ImmutabilityViolationError after construction |
| `frozen_error_sealed` | 6 | type() subclassing raises TypeError (fuzzed subclass name) |
| `frozen_error_hash_stability` | 6 | hash() and content_hash stable across repeated calls |

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
| `decimal_digits_convenience` | 8 | `get_currency_decimal_digits` == `get_currency().decimal_digits`; valid range {0,2,3,4} |

### Allowed Exceptions

`BabelImportError`, `ValueError`, `KeyError`, `LookupError` -- Babel not installed or invalid locale/CLDR data.

---

## `fuzz_lock`

Target: `runtime.RWLock`, `runtime.rwlock.RWLock` -- public facade export identity, reader/writer exclusion, reentrant reads, write-reentry rejection, write-to-read downgrade rejection, read-to-write upgrade rejection, timeout, deadlock detection, negative timeout rejection, release-without-acquire rejection, zero-timeout non-blocking paths.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `LockMetrics` dataclass (deadlocks detected, public export checks, timeouts, thread creation count, max concurrent threads). Weight skew detection compares actual vs intended pattern distribution. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default. Corpus retention rate and eviction tracking enabled.

### Patterns

Ordered cheapest-first. Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias that caused severe weight skew under FDP-based selection. Seed files provide FDP parameter bytes only (pattern is determined by iteration counter).

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `public_export_surface` | 4 | `ftllexengine.runtime.RWLock` aliases direct implementation and appears in runtime `__all__` |
| `reentrant_reads` | 5 | Same thread acquires read lock N times |
| `write_reentry_rejection` | 4 | Write-to-write reentry raises RuntimeError |
| `downgrade_rejection` | 4 | Write-to-read downgrade raises RuntimeError |
| `negative_timeout` | 4 | Negative timeout raises ValueError, lock still usable |
| `release_without_acquire` | 4 | Release without acquire raises RuntimeError, lock still usable |
| `upgrade_rejection` | 8 | Read-to-write upgrade raises RuntimeError |
| `zero_timeout_nonblocking` | 5 | timeout=0.0 fails immediately when lock held, sub-1ms |
| `rapid_lock_cycling` | 8 | Shared counter correct after rapid cycles |
| `cross_thread_handoff` | 6 | Rapid write handoff between threads, no lost entries |
| `concurrent_readers` | 12 | Multiple readers hold lock simultaneously |
| `timeout_acquisition` | 8 | TimeoutError raised, lock usable after timeout |
| `reader_writer_exclusion` | 15 | No concurrent reader+writer, no multi-writer |
| `writer_preference` | 10 | Waiting writer blocks new readers (fuzz-controlled timing) |
| `reader_starvation` | 6 | Continuous readers cannot starve waiting writer |
| `mixed_contention` | 7 | All prohibition checks and permitted ops interleaved across threads |

### Allowed Exceptions

`RuntimeError`, `TimeoutError`, `ValueError` -- expected from upgrade rejection, lock protocol violations, negative timeout rejection, and timeout-based acquisition.

---

## `fuzz_numbers`

Target: `runtime.functions.number_format` -- ROUND_HALF_UP oracle testing, custom `pattern=` path, grouping separator correctness, boundary values, min>max clamping, and `FluentNumber` wrapper contracts.

Concern boundary: This fuzzer stress-tests the runtime NUMBER function formatting path. Distinct from `fuzz_builtins` (which covers NUMBER/DATETIME via the FTL `FluentBundle` evaluation pipeline with structural invariants); this fuzzer calls `number_format` directly to probe oracle correctness and covers the custom `pattern=` fast-path that `fuzz_builtins` does not reach. Key gap: `fuzz_builtins` verifies non-empty output and ROUND_HALF_UP at specific boundary values; this fuzzer covers ROUND_HALF_UP across 35 boundary pairs at precisions 0-3, grouping separator interaction with rounding, and the `minimumFractionDigits > maximumFractionDigits` clamping path.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `NumbersMetrics` dataclass. Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

8 patterns across 3 categories:

**ORACLE (4)** - ROUND_HALF_UP correctness at precision boundaries:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `boundary_values` | 15 | 35 `(precision, x.y5)` midpoints: all must round away from zero |
| `grouping_oracle` | 16 | ROUND_HALF_UP with `use_grouping=True` across en-US/de-DE/fr-FR (gap in builtins) |
| `negative_oracle` | 12 | ROUND_HALF_UP preserved for negative values: abs() applied before oracle comparison |
| `pattern_oracle` | 13 | Custom `pattern=` path: `parse_pattern(p).frac_prec[1]` precision, ROUND_HALF_UP oracle |

**BOUNDARY (2)** - Edge-case value handling:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `large_integers` | 11 | Values >1e9: non-empty, grouping separators present for en-US |
| `min_gt_max` | 11 | `minimumFractionDigits > maximumFractionDigits`: result non-empty, no exception |

**CONTRACTS (2)** - Determinism and value preservation:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `determinism` | 11 | Same `(value, locale, kwargs)` always produces identical output |
| `value_preservation` | 11 | Formatted numeric content matches `Decimal` input through grouping/sign stripping |

### Allowed Exceptions

`ValueError`, `TypeError` -- invalid parameters and type validation.

---

## `fuzz_parse_decimal`

Target: `parsing.numbers.parse_decimal`, `parsing.numbers.parse_fluent_number`, `parsing.guards.is_valid_decimal`, `core.locale_utils` helpers -- locale-aware decimal parsing, FluentNumber parsing, locale normalization equivalence, locale boundary validation, Babel locale cache behavior, and system locale resolution.

Concern boundary: This fuzzer owns the text-to-`Decimal` and text-to-`FluentNumber` parse surface that the runtime NUMBER-formatting fuzzers do not touch. It covers canonical locale-formatted inputs, the public `parse_decimal()` + `make_fluent_number()` composition contract exposed as `parse_fluent_number()`, locale spelling normalization (`en-US` vs `en_US` vs mixed case), `require_locale_code()` trim/type/structure/canonicalization rules, public soft-error contracts, Babel locale cache reuse/clearing, and `get_system_locale()` precedence through environment variables and `locale.getlocale()`, including encoded `C.UTF-8` / `POSIX.UTF-8` pseudo-locale fallback.

Shared infrastructure imported from `fuzz_common`; domain-specific metrics tracked in `ParseDecimalMetrics` dataclass (`parse_calls`, `parse_successes`, `soft_errors`, `fluent_number_checks`, locale variant/boundary/cache/system checks). Pattern selection uses deterministic round-robin. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `canonical_values` | 14 | Known locale-formatted decimals parse to exact `Decimal` values |
| `parse_fluent_number_api` | 12 | `parse_fluent_number()` matches public `parse_decimal()` + `make_fluent_number()` composition |
| `locale_variants` | 12 | Equivalent locale spellings produce identical parse results |
| `invalid_soft_error` | 12 | Invalid decimal text returns soft errors, not silent success |
| `require_locale_code_api` | 10 | `require_locale_code()` trims/canonicalizes valid input and rejects blank, invalid, non-string, and overlong values |
| `type_guard_contract` | 10 | `is_valid_decimal()` accepts valid finite decimals and rejects bad values |
| `babel_locale_cache` | 10 | Locale normalization/cache clear cycles preserve locale-object equivalence |
| `system_locale_resolution` | 10 | `get_system_locale()` respects precedence and skips encoded C/POSIX pseudo-locales |
| `raw_unicode_stability` | 12 | Arbitrary Unicode inputs preserve the public result-or-errors contract |

### Allowed Exceptions

`ValueError`, `TypeError`, `OSError`, `RuntimeError`, `UnicodeEncodeError`, `FrozenFluentError` -- invalid locale/input handling and soft-error plumbing.

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

Target: `syntax.serializer.serialize`, `syntax.parser.FluentParserV1`, `syntax.visitor.ASTVisitor`, `syntax.visitor.ASTTransformer` -- AST-construction serializer roundtrip idempotence plus visitor/transformer dispatch and validation.

Concern boundary: This fuzzer programmatically constructs AST nodes (bypassing the parser) and feeds them to the serializer. This is the ONLY Atheris fuzzer that can produce AST states the parser would never emit -- e.g. TextElement values with leading whitespace, syntax characters in pattern-initial positions, or structurally valid but semantically unusual combinations. The same AST-construction model now also drives direct `ASTVisitor` and `ASTTransformer` coverage: custom dispatch methods, list-expanding transforms, and invalid scalar-field replacements that must raise `TypeError`.

Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, `gen_ftl_identifier`, `gen_ftl_value`, `write_finding_artifact`, `print_fuzzer_banner`, metrics, reporting); domain-specific metrics tracked in `SerializerMetrics` dataclass (ast_construction_failures, convergence_failures, junk_on_reparse, validation_errors, visitor_runs, transformer_runs). Pattern selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Custom mutator applies whitespace injection and syntax character insertion mutations before byte-level mutation. Finding artifacts written to `.fuzz_atheris_corpus/serializer/findings/`. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

13 patterns across 5 categories:

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

**VISITOR (3)** - Direct `syntax.visitor` coverage:

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `visitor_dispatch` | 8 | Custom `visit_*` handlers and generic traversal both execute |
| `transformer_roundtrip` | 8 | List-expanding `ASTTransformer` output remains serializable and convergent |
| `transformer_validation` | 6 | Invalid scalar replacements for required fields raise `TypeError` |

### Allowed Exceptions

`ValueError`, `TypeError`, `RecursionError`, `MemoryError`, `UnicodeDecodeError`, `UnicodeEncodeError` -- AST construction edge cases, serializer limits, visitor validation, and encoding boundaries.

---

## `fuzz_cursor`

Target: `syntax.cursor.Cursor`, `syntax.cursor.LineOffsetCache`, `syntax.cursor.ParseError`, `syntax.cursor.ParseResult`, `syntax.position` helpers -- cursor state-machine behavior, contextual parse-error rendering, and line/column parity across normalized source.

Concern boundary: Existing parser fuzzers only touch `Cursor` indirectly through parser control flow. This fuzzer hits the subsystem directly: constructor guards, `peek()`/`advance()`/`expect()` semantics, whitespace skipping, line navigation, parity between cursor-computed positions and standalone helper functions, `ParseError.format_with_context()` rendering, and `ParseResult` contract behavior on arbitrary raw and CRLF-normalized sources.

Shared infrastructure imported from `fuzz_common`; domain-specific metrics tracked in `CursorMetrics` dataclass. Pattern selection uses deterministic round-robin. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `constructor_guards` | 12 | Negative/out-of-range positions reject; EOF cursor behavior is correct |
| `peek_advance_expect` | 14 | `peek`, `advance`, `slice_*`, and `expect` match manual semantics |
| `whitespace_skips` | 12 | `skip_spaces`/`skip_whitespace` agree with reference implementations |
| `line_navigation` | 10 | Line-start/line-end helpers preserve valid cursor positions |
| `line_col_parity` | 12 | Cursor-computed line/column matches cached position helper results |
| `parse_error_formatting` | 10 | Context rendering stays non-empty and positionally coherent |
| `position_helpers` | 12 | `line_offset`, `column_offset`, `get_line_content`, `format_position` stay consistent |
| `parse_result_contract` | 8 | `ParseResult` success/error states preserve documented invariants |

### Allowed Exceptions

`ValueError`, `EOFError`, `UnicodeEncodeError` -- invalid positions, EOF access, and encoding edge cases.

---

## `fuzz_runtime`

Target: `runtime.bundle.FluentBundle` -- full resolver stack, strict mode, caching, concurrency, security, AST lookup facade, and canonical constructor locale boundary contracts.

Scenario selection uses deterministic round-robin through a pre-built weighted schedule (`select_pattern_round_robin`), immune to coverage-guided mutation bias. Security sub-pattern selection within `_perform_security_fuzzing` remains FDP-based (second-level, already guaranteed execution). FDP bytes are used exclusively for scenario parameters, not scenario selection. String and RegEx instrumentation hooks enabled for deeper coverage of message ID lookups, selector matching, and pattern-based parsing. Shared infrastructure imported from `fuzz_common` (`BaseFuzzerState`, metrics, reporting); domain-specific metrics tracked in `RuntimeMetrics` dataclass, including `FluentBundle.get_message()` / `get_term()` AST lookup checks, constructor locale boundary checks, and direct `validate_message_variables()` compatibility. Weight skew detection compares actual vs intended scenario distribution. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

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
| `security_locale_boundary` | 8 | Canonicalize valid locales to lowercase underscore; reject blank, non-string, invalid, and overlong constructor locales |
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
| `expansion_size_limit` | 5 | `_total_chars` budget fires, EXPANSION_BUDGET_EXCEEDED returned |

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

## `fuzz_localization`

Target: `localization.orchestrator.FluentLocalization`, `localization.loading.PathResourceLoader` -- multi-locale orchestration, canonical locale boundary and boot validation APIs, eager loader-backed initialization, fallback chains, `LoadSummary`, and post-construction mutation APIs.

Concern boundary: This fuzzer stress-tests the FluentLocalization lifecycle orthogonal to FluentBundle. Distinct from fuzz_runtime (single bundle) and fuzz_integrity (validation). It covers constructor locale canonicalization/deduplication and unified rejection errors, multi-locale fallback traversal, `add_resource()` mutation between calls, `has_message()`/`get_message_ids()` API contracts, `get_message()`/`get_term()` AST lookup precedence, `require_clean()`, `validate_message_variables()`, and `validate_message_schemas()` boot-validation APIs, per-locale `get_cache_audit_log()` access, custom function registration and invocation, `on_fallback` callback delivery, introspection delegation, and the loader-backed initialization path: eager resource loading, canonical `{locale}` directory substitution, `PathResourceLoader` path validation, per-locale success/not-found/error accounting, junk-bearing loads, and `source_path` propagation into `LoadSummary`.

Shared infrastructure imported from `fuzz_common`; domain-specific metrics tracked in `LocalizationMetrics` dataclass (including AST lookup, schema-validation, cache-audit, constructor locale-boundary, and loader/boot-validation counters). Pattern selection uses deterministic round-robin. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `single_locale_add_resource` | 10 | add_resource accepts valid FTL; format returns the stored value |
| `multi_locale_fallback` | 10 | Primary miss triggers fallback; callback sees resolved locale |
| `chain_of_3_fallback` | 8 | 3-locale chain traverses correctly |
| `format_value_missing` | 7 | Missing message returns fallback text plus errors |
| `format_with_variables` | 9 | Variables propagate through fallback chain |
| `add_resource_mutation` | 7 | add_resource between format calls updates visible state |
| `has_message_api` | 7 | has_message/has_attribute contracts hold across locales |
| `ast_lookup_api` | 7 | get_message/get_term honor fallback precedence and namespace boundaries |
| `get_message_ids_api` | 6 | get_message_ids returns all IDs without duplicates |
| `validate_resource_api` | 7 | validate_resource delegates and returns structured results |
| `validate_message_variables_api` | 6 | single-message schema validation matches AST lookup and raises integrity context on missing/mismatched schemas |
| `validate_message_schemas_api` | 6 | exact schema order, fallback resolution, and missing/extra variable failures |
| `add_function_custom` | 6 | Custom UPPER function registration/invocation works |
| `introspect_api` | 7 | get_message_variables/introspect_message stay consistent |
| `cache_audit_api` | 6 | get_cache_audit_log matches initialized locales and stats |
| `locale_boundary_api` | 5 | Constructor canonicalizes/deduplicates valid locales and rejects blank/non-string/invalid/overlong input |
| `on_fallback_callback` | 6 | on_fallback receives requested/resolved locale data |
| `loader_init_success` | 5 | Eager loader initialization records all-success summary data |
| `loader_not_found_fallback` | 5 | Primary miss increments not_found while fallback still resolves |
| `loader_junk_summary` | 4 | Junk-bearing resources are surfaced through LoadSummary |
| `loader_path_error` | 4 | Invalid `resource_id` becomes a loader error, not a crash |
| `require_clean_api` | 5 | clean initialization returns summary; missing/junk/error states raise integrity context |

### Allowed Exceptions

`ValueError`, `TypeError`, `UnicodeEncodeError`, `FrozenFluentError`, `DataIntegrityError`, `FormattingIntegrityError`, `SyntaxIntegrityError` -- invalid locale/resource input, loader validation, strict mode enforcement, and resolution errors.

---

## `fuzz_dates`

Target: `parsing.dates.parse_date`, `parsing.dates.parse_datetime` -- CLDR→strptime token mapping, locale-aware date/datetime parsing across 24 test locales (Latin-DMY, Latin-MDY, Latin-YMD, CJK, RTL).

Concern boundary: This fuzzer stress-tests the bidirectional date parsing pipeline. Covers the `_babel_to_strptime` token mapping, all 14 pattern variants (short/medium/long/full plus 4-digit year oracle), adversarial inputs (null bytes, ANSI escapes, surrogates, 10000-char strings, invalid month/day values), and cross-locale format string generation. Key invariants: if result is None, errors must be non-empty; if result is not None, it must be a `date`/`datetime` instance; `parse_datetime` result must be instance of `datetime` (not bare `date`). The `four_digit_year_acceptance` pattern uses ISO 8601 as a ground-truth oracle: `parse_date("dd.MM.yyyy", locale)` for locales whose CLDR short pattern uses `yy` must return the same date as `parse_date("yyyy-MM-dd", locale)`.

Shared infrastructure imported from `fuzz_common`; domain-specific metrics tracked in `DatesMetrics` dataclass. Pattern selection uses deterministic round-robin. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=4096` default.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `parse_date_generated` | 14 | Generated date strings parse successfully per locale |
| `parse_datetime_generated` | 12 | Generated datetime strings parse per locale |
| `locale_variation` | 12 | Same date parsed in multiple locales |
| `style_variation` | 12 | short/medium/long/full styles all produce parseable strings |
| `cross_locale_agreement` | 10 | Parsing is consistent across 3 random locales |
| `adversarial_input` | 10 | Null bytes, surrogates, ANSI escapes handled without crash |
| `format_then_parse` | 12 | format → parse roundtrip (DATETIME output is parseable) |
| `invalid_date_values` | 10 | month=13, day=99 produce errors, not silent wrong dates |
| `empty_string` | 8 | Empty string → errors, not crash |
| `whitespace_input` | 8 | Whitespace-only → errors, not crash |
| `partial_date_strings` | 6 | Partial (year-only, month-only) inputs handled |
| `unicode_month_names` | 8 | Non-ASCII month names in CJK/RTL locales |
| `leap_year_boundary` | 8 | Feb 29 on leap/non-leap years |
| `four_digit_year_acceptance` | 8 | lv-LV/de-DE/pl-PL/fi-FI/ru-RU: dd.MM.yyyy == ISO oracle; must not return None |

### Allowed Exceptions

`ValueError`, `TypeError`, `UnicodeDecodeError`, `UnicodeEncodeError`, `FrozenFluentError` -- invalid locale, encoding edge cases, and bidirectional parse errors.

---

## `fuzz_locale_context`

Target: `runtime.locale_context.LocaleContext`, `core.locale_utils.normalize_locale` -- direct formatting API: `format_number()`, `format_currency()`, `format_datetime()`, canonical locale boundary handling, ROUND_HALF_UP rounding oracle, cross-locale determinism.

Concern boundary: This fuzzer stress-tests the LocaleContext formatting layer, distinct from fuzz_builtins (which goes through FluentBundle/FTL) and fuzz_runtime (full runtime stack). Directly exercises the locale-aware formatting primitives that caused the v0.145.0 ROUND_HALF_UP regression and now verifies that every successful `LocaleContext.create()` path stores a canonical lowercase underscore `locale_code`. Key invariant (oracle-based): `format_number(val, max_frac=N)` must round half-up (not half-even), verified by `Decimal.quantize(10^-N, ROUND_HALF_UP)`. Control chars stripped from currency symbols prevent log injection through formatted output.

Shared infrastructure imported from `fuzz_common`; domain-specific metrics tracked in `LocaleContextMetrics` dataclass. Pattern selection uses deterministic round-robin. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=2048` default (no Babel concurrency needed).

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `format_number_int` | 8 | Integers format to non-empty output with canonical locale_code |
| `format_number_decimal` | 8 | Decimal values format to non-empty output |
| `format_number_precision` | 8 | ROUND_HALF_UP oracle at explicit min/max precision |
| `format_number_custom_pattern` | 6 | Custom number patterns produce non-empty output |
| `format_number_grouping` | 6 | Grouping on/off remains stable |
| `format_currency_standard` | 8 | Standard currency formatting is non-empty and oracle-safe |
| `format_currency_precision_override` | 6 | Currency display variants remain non-empty |
| `format_currency_custom_pattern` | 5 | Custom currency patterns produce non-empty output |
| `format_datetime_date_obj` | 7 | `date` promotion to midnight datetime formats correctly |
| `format_datetime_datetime_obj` | 7 | `datetime` formatting is non-empty |
| `format_datetime_style_combo` | 7 | Date/time style combinations remain non-empty |
| `format_datetime_pattern` | 6 | Custom datetime patterns produce non-empty output |
| `locale_create_adversarial` | 8 | Successful creates store canonical locale_code; invalid boundaries reject cleanly |
| `cross_locale_determinism` | 5 | Same value+locale → identical output on repeated calls |

### Allowed Exceptions

`ValueError`, `TypeError`, `OverflowError`, `UnicodeEncodeError`, `FrozenFluentError` -- invalid locale, Babel formatting errors, and out-of-range values.

---

## `fuzz_introspection`

Target: `introspection.message.IntrospectionVisitor`, `introspection.message.ReferenceExtractor`, `introspection.message.MessageIntrospection` -- `extract_variables()`, `extract_references()`, `extract_references_by_attribute()`, `introspect_message()`, `clear_introspection_cache()`, `FluentBundle` introspection facade.

Concern boundary: This fuzzer uses programmatic AST construction (bypasses the FTL parser) to reach introspection code paths that parser-generated ASTs would never produce. Tests the `MAX_DEPTH` guard via `SelectExpression` chain at depths ± `MAX_DEPTH`, frozenset deduplication (same variable referenced N times → 1 entry), `requires_variable(x)` ↔ `get_variable_names()` consistency, cache correctness under repeated calls, and weakref/lock safety under the `threading.Lock`-protected result cache.

Shared infrastructure imported from `fuzz_common`; domain-specific metrics tracked in `IntrospectionMetrics` dataclass. Pattern selection uses deterministic round-robin. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=2048` default.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `extract_variables_simple` | 14 | Variables returned as frozenset; deduplication correct |
| `extract_references_simple` | 12 | Message/term refs returned correctly |
| `attribute_variables` | 10 | Attribute-level variables extracted |
| `deduplication_invariant` | 12 | N references to same var → 1 frozenset entry |
| `requires_variable_consistency` | 10 | requires_variable ↔ get_variable_names match |
| `deep_nesting_guard` | 10 | MAX_DEPTH chain triggers guard, no unhandled crash |
| `select_expression_vars` | 8 | Variables in select variants extracted |
| `term_reference_vars` | 8 | Term args as variable references |
| `cache_correctness` | 10 | Repeated calls return identical frozensets |
| `clear_cache` | 8 | clear_introspection_cache() resets state correctly |
| `bundle_facade` | 8 | FluentBundle.introspect_message() delegation |
| `adversarial_ast` | 5 | Programmatic AST edge cases (empty pattern, no elements) |
| `validate_variables_schema` | 8 | exact/superset/subset invariants; frozen result; missing/extra sets correct |

### Allowed Exceptions

`ValueError`, `TypeError`, `RecursionError`, `FrozenFluentError` -- invalid AST nodes, depth guard enforcement, and resolution errors.

---

## `fuzz_diagnostics_formatter`

Target: `diagnostics.formatter.DiagnosticFormatter`, `diagnostics.validation.ValidationError`, `diagnostics.validation.ValidationWarning`, `diagnostics.validation.ValidationResult` -- RUST/SIMPLE/JSON output formats, control-character escaping (log injection prevention), sanitize/redact modes, `format_validation_result()`, `format_error()`, `format_warning()`, `format_all()`.

Concern boundary: This fuzzer stress-tests the diagnostic formatting pipeline as a security boundary. The primary invariant is that no raw ASCII control character (0x00-0x1F, 0x7F) survives into RUST or SIMPLE formatted output when injected into any diagnostic field (message, hint, function_name, argument_name, expected_type, received_type, ftl_location, resolution_path). Secondary invariants: JSON output always parses as valid JSON; sanitize mode bounds output length; redact mode replaces content with `[content redacted]` sentinel; `format_all()` contains each individual formatted diagnostic; `color=True` produces ANSI escape sequences.

Shared infrastructure imported from `fuzz_common`; domain-specific metrics tracked in `FormatterMetrics` dataclass. Pattern selection uses deterministic round-robin. Periodic `gc.collect()` every 256 iterations and `-rss_limit_mb=2048` default.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `control_char_escaping` | 14 | No raw C0/DEL in RUST/SIMPLE output after injection |
| `format_rust_all_fields` | 12 | RUST non-empty; span line present; resolution_path separator |
| `format_json_valid` | 12 | JSON parseable; mandatory keys present; code matches |
| `format_simple` | 10 | Single-line for clean messages; code name in output |
| `sanitize_truncation` | 10 | Sanitize mode truncates; ellipsis marker present |
| `sanitize_redact` | 8 | Redact mode hides content; sentinel present |
| `format_error_location` | 10 | line/column present when set; absent when not set |
| `format_warning_context` | 8 | Context present in output; redact removes it |
| `format_validation_result_mixed` | 8 | passed/failed summary; include_warnings respected |
| `format_all_multiple` | 8 | Each individual diagnostic present in combined output |
| `color_ansi_mode` | 5 | color=True longer than color=False; ESC byte present |
| `adversarial_fields` | 5 | Control chars in rich fields all escaped |

### Allowed Exceptions

`ValueError`, `TypeError` -- invalid input types to format_error/format_warning.

---

## Observability Standard

All fuzzers import shared infrastructure from `fuzz_common.py` (`BaseFuzzerState`, metrics, reporting) and compose domain-specific metrics via separate dataclasses:

- `BaseFuzzerState` dataclass with bounded deques (shared via `fuzz_common`)
- Domain metrics: `RoundtripMetrics`, `SerializerMetrics`, `StructuredMetrics`, `RuntimeMetrics`, `LockMetrics`, `IntegrityMetrics`, `CacheMetrics`, `BuiltinsMetrics`, `BridgeMetrics`, `FiscalMetrics`, `ISOMetrics`, `CurrencyMetrics`, `NumbersMetrics`, `OOMMetrics`, `PluralMetrics`, `ScopeMetrics`, `LocalizationMetrics`, `DatesMetrics`, `LocaleContextMetrics`, `IntrospectionMetrics`, `FormatterMetrics` (per-fuzzer)
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
