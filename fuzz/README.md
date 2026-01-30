---
afad: "3.2"
version: "0.97.0"
domain: fuzzing
updated: "2026-01-29"
route:
  keywords: [fuzzing, coverage, atheris, libfuzzer, fuzz, seeds, corpus]
  questions: ["what do the fuzzers cover?", "what modules are fuzzed?", "what is not fuzzed?"]
---

# Fuzzer Coverage Inventory

**Purpose**: Stock-taking of what the Atheris/libFuzzer fuzzing infrastructure covers, enabling gap analysis and planning.

## Fuzzer Summary

| Fuzzer | Target Module(s) | Patterns | Seeds | Concern |
|:-------|:-----------------|:---------|:------|:--------|
| `fuzz_cache.py` | `runtime.bundle`, `runtime.cache`, `integrity` | 12 | 43 (.ftl) + 5 (.bin) | Cache concurrency and integrity |
| `fuzz_currency.py` | `parsing.currency` | 16 | 65 (.txt) | Currency symbol extraction |
| `fuzz_fiscal.py` | `parsing.fiscal` | 7 | 15 (.bin) | Fiscal calendar arithmetic |
| `fuzz_integrity.py` | `validation`, `runtime.bundle`, `integrity` | 23 | 68 (.ftl) + 2 (.bin) | Semantic validation, cross-resource |
| `fuzz_iso.py` | `introspection.iso` | 9 | 17 (.bin) | ISO 3166/4217 introspection |
| `fuzz_lock.py` | `runtime.rwlock` | 10 | 18 (.bin) | RWLock concurrency primitives |
| `fuzz_numbers.py` | `parsing.numbers` | 19 | 70 (.txt) | Locale-aware numeric parsing |
| `fuzz_oom.py` | `syntax.parser` | 16 | 42 (.ftl) + 1 (.bin) | Parser object explosion (DoS) |
| `fuzz_runtime.py` | `runtime.bundle`, `runtime.cache`, `integrity`, `diagnostics.errors` | 6+5 | 61 (.bin) | Full runtime stack, strict mode |
| `fuzz_structured.py` | `syntax.parser`, `syntax.serializer` | 10 | 12 (.ftl) | Grammar-aware AST construction |

## Module Coverage Matrix

| Source Module | Fuzzers Covering It |
|:--------------|:--------------------|
| `diagnostics.errors` | runtime, oom, numbers, currency, cache, integrity |
| `integrity` | runtime, cache, integrity |
| `introspection.iso` | iso |
| `parsing.currency` | currency |
| `parsing.fiscal` | fiscal |
| `parsing.numbers` | numbers |
| `runtime.bundle` | runtime, cache, integrity |
| `runtime.cache` | runtime, cache |
| `runtime.rwlock` | lock |
| `syntax.parser` | oom, structured |
| `syntax.serializer` | structured |
| `validation` | integrity |

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

### Allowed Exceptions

`CacheCorruptionError`, `WriteConflictError`, `DataIntegrityError`, `FrozenFluentError` -- cache integrity violations are expected findings; `FrozenFluentError` from depth guards.

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

Target: `runtime.rwlock.RWLock`, `with_read_lock`, `with_write_lock` -- reader/writer exclusion, reentrancy, downgrading, deadlock detection.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `reader_writer_exclusion` | 15 | No concurrent reader+writer, no multi-writer |
| `concurrent_readers` | 12 | Multiple readers hold lock simultaneously |
| `writer_preference` | 10 | Waiting writer blocks new readers |
| `reentrant_reads` | 12 | Same thread acquires read lock N times |
| `reentrant_writes` | 10 | Same thread acquires write lock N times |
| `write_to_read_downgrade` | 12 | Writer acquires reads, persist after write release |
| `upgrade_rejection` | 8 | Read-to-write upgrade raises RuntimeError |
| `rapid_lock_cycling` | 8 | Shared counter correct after rapid cycles |
| `decorator_correctness` | 6 | with_read_lock/with_write_lock return values |
| `mixed_contention` | 7 | All operations interleaved across threads |

### Allowed Exceptions

`RuntimeError` -- expected from upgrade rejection and lock protocol violations.

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

## `fuzz_runtime`

Target: `runtime.bundle.FluentBundle` -- full resolver stack, strict mode, caching, concurrency, security.

### Patterns

| Pattern | Weight | Invariants Checked |
|:--------|-------:|:-------------------|
| `core_runtime` | 40 | Frozen error checksum, cache stability, determinism |
| `strict_mode` | 20 | Zero errors in strict format_pattern |
| `caching` | 15 | Cache hit determinism, corruption detection |
| `security` | 10 | *(5 sub-patterns below)* |
| `concurrent` | 10 | No deadlocks, 2-thread barrier test |
| `differential` | 5 | Same FTL, different configs, no crash divergence |

Security sub-patterns:

| Sub-pattern | Weight | Attack Vector |
|:------------|-------:|:--------------|
| `security_recursion` | 30 | Deep placeables, cyclic refs, self-ref terms |
| `security_memory` | 25 | Large values, many variants/attributes |
| `security_cache_poison` | 20 | inf/nan/None/list as args |
| `security_function_inject` | 15 | Custom function registration |
| `security_locale_explosion` | 10 | Very long / control char locales |

### Allowed Exceptions

`CacheCorruptionError`, `FormattingIntegrityError`, `WriteConflictError`, `FrozenFluentError`, `RecursionError`, `MemoryError` -- integrity violations are findings; depth guards and resource limits are safety mechanisms.

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
