---
afad: "3.1"
version: "0.97.0"
domain: "architecture"
updated: "2026-01-28"
route: "/docs/data-integrity"
---

# Data Integrity Architecture

This document describes the architectural design for data integrity in FTLLexEngine.

## Design Principle: Fail-Fast Data Safety

For financial applications, silent data corruption is catastrophic. The system is designed to **fail loudly and immediately** rather than propagate incorrect data.

| Failure Mode | Non-Financial App | Financial App |
|:-------------|:------------------|:--------------|
| Missing translation | Show fallback | Unacceptable |
| Cache corruption | Return stale data | Unacceptable |
| Error mutation | Log and continue | Unacceptable |

**Rationale:** A bank displaying "$1,000" when the actual value is "$10,000" due to a silent fallback is worse than displaying an error. Financial applications must know immediately when something is wrong.

## Architecture Overview

```
+------------------------------------------------------------------+
|                        FluentBundle                               |
|  +------------------------------------------------------------+  |
|  |                     Strict Mode Layer                       |  |
|  |  Responsibility: Fail-fast on ANY formatting error         |  |
|  |  Raises: FormattingIntegrityError                          |  |
|  +------------------------------------------------------------+  |
|                               |                                   |
|  +------------------------------------------------------------+  |
|  |                     Error Layer                             |  |
|  |  Responsibility: Immutable, verifiable error objects       |  |
|  |  Type: FrozenFluentError (sealed, content-addressed)       |  |
|  +------------------------------------------------------------+  |
|                               |                                   |
|  +------------------------------------------------------------+  |
|  |                     Cache Layer                             |  |
|  |  Responsibility: Checksum-verified format result caching   |  |
|  |  Type: IntegrityCache (BLAKE2b-128, write-once option)     |  |
|  +------------------------------------------------------------+  |
|                               |                                   |
|  +------------------------------------------------------------+  |
|  |                  Integrity Exception Layer                  |  |
|  |  Responsibility: System failure signaling (not Fluent)     |  |
|  |  Types: DataIntegrityError hierarchy                       |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
```

## Component Responsibilities

### Strict Mode Layer

**Responsibility:** Provide fail-fast behavior at bundle level.

**Design Decision:** Strict mode is opt-in (`strict=False` default), not the only mode.

**Why not fail-fast by default?**

The Fluent specification itself defines fallback behavior. When formatting fails, you get a result (with placeholder like `{$amount}`) AND errors returned as data. This is intentional:

| Consideration | Rationale |
|:--------------|:----------|
| Fluent philosophy | "Errors as data" - caller decides severity, not the library |
| Development workflow | Seeing `{$missing}` in UI identifies issues without crashing the app |
| Graceful degradation | Some apps prefer "something shows" over "nothing shows" |
| Domain-specific severity | Missing greeting is annoying; missing balance is catastrophic |

**Why offer strict mode at all?**

Some applications cannot tolerate silent fallbacks. A missing variable returning `{$amount}` could display wrong data to users. These apps need a guarantee: if `format_pattern()` returns, the result is correct.

**Activation:**
- `FluentBundle(..., strict=True)` - explicit opt-in
- Combine with `enable_cache=True` for caching

**Invariant:** When `strict=True`, NO formatting operation returns a fallback value. Every error path raises `FormattingIntegrityError`.

### Error Layer (FrozenFluentError)

**Responsibility:** Provide immutable, verifiable error objects.

**Design Decisions:**

| Decision | Rationale |
|:---------|:----------|
| Sealed class (`@final`) | Prevents subclass invariant violations |
| Content-addressed (BLAKE2b-128) | Enables corruption detection |
| Slots-only | Memory efficiency, prevents dynamic attributes |
| Composition over inheritance | `ErrorCategory` enum replaces class hierarchy |

**Content Hash Composition:**

The BLAKE2b-128 content hash includes ALL error fields for complete audit trail integrity:

1. **Core fields:** `message`, `category.value`
2. **Diagnostic (if present):**
   - Core: `code.name`, `message`
   - Location: `span` (start, end, line, column as 4-byte big-endian)
   - Context: `hint`, `help_url`, `function_name`, `argument_name`, `expected_type`, `received_type`, `ftl_location`
   - Metadata: `severity`, `resolution_path` (each element)
3. **Context (if present):** `input_value`, `locale_code`, `parse_type`, `fallback_value`

**Length-Prefixing:** All string fields are length-prefixed (4-byte big-endian UTF-8 byte length) before hashing. This prevents collision attacks where concatenating different field sequences produces identical byte streams (e.g., `("ab", "c")` vs `("a", "bc")`).

**Sentinel Bytes:** None values are distinguished from empty values using sentinel bytes, preventing collision between `span=None` and `span=SourceSpan(0, 0, 0, 0)`.

**Invariants:**
- All attributes frozen after `__init__` completes
- `verify_integrity()` always returns True for uncorrupted errors
- Hash is stable for object lifetime

**Security Properties:**
- Constant-time hash comparison (`hmac.compare_digest`) prevents timing attacks
- Surrogate handling (`errors="surrogatepass"`) prevents Unicode exploits
- Complete field coverage prevents metadata tampering

### Cache Layer (IntegrityCache)

**Responsibility:** Provide checksum-verified caching of format results.

**Design Decisions:**

| Decision | Rationale |
|:---------|:----------|
| BLAKE2b-128 checksums | Fast cryptographic hash, 16-byte overhead per entry |
| Write-once option | Prevents data races from overwriting cached results |
| Strict/non-strict modes | Fail-fast vs. silent eviction for different use cases |
| Audit logging | Compliance and debugging for financial systems |
| Sequence numbers | Monotonic ordering for audit trail integrity |
| Idempotent write detection | Content-hash comparison for thundering herd tolerance |

**Checksum Composition:**

The BLAKE2b-128 checksum includes ALL entry fields for complete audit trail integrity:

1. **Content:** `formatted` (UTF-8 encoded, length-prefixed message output)
2. **Errors:** Each error's `content_hash` (or length-prefixed message string if unavailable)
3. **Metadata:**
   - `created_at`: 8-byte IEEE 754 double (monotonic timestamp)
   - `sequence`: 8-byte signed big-endian integer (audit trail ordering)

**Length-Prefixing:** All variable-length fields (formatted string, error messages) are length-prefixed (4-byte big-endian UTF-8 byte length) before hashing, preventing collision attacks from field concatenation.

This means different entries with identical content will have different checksums if their metadata differs. This is correct behavior: the checksum protects the complete entry, not just its content.

**Idempotent Write Detection:**

In write-once mode, concurrent writes of the same message pose a challenge: multiple threads may resolve the same message simultaneously (thundering herd). Without idempotent detection, all but the first thread would trigger `WriteConflictError`, even though all produced identical results.

The cache computes a **content-only hash** (excluding metadata like `created_at` and `sequence`) to detect idempotent writes:

1. Second write arrives for an existing key
2. Cache computes content hash of new entry: `BLAKE2b-128(formatted, errors)`
3. Compares with existing entry's content hash (constant-time via `hmac.compare_digest`)
4. If identical: increment `idempotent_writes` counter, return silently (benign race)
5. If different: TRUE conflict - raise `WriteConflictError` (strict) or log (non-strict)

This allows write-once mode to work correctly under load without false-positive conflicts.

**Type-Tagging for Cache Keys:**

Cache keys must distinguish between values that hash identically but have different types. The `_make_hashable()` function applies type-tagging to prevent collisions:

| Type | Tag Format | Purpose |
|:-----|:-----------|:--------|
| `bool` | `("__bool__", value)` | Distinguish `True` from `1` |
| `int` | `("__int__", value)` | Distinguish `1` from `1.0` |
| `float` | `("__float__", value)` | Distinguish `1.0` from `1` |
| `Decimal` | `("__decimal__", str(value))` | Preserve scale for CLDR plural rules (`Decimal("1.0")` vs `Decimal("1.00")`) |
| `FluentNumber` | `("__fluentnumber__", type, value, formatted, precision)` | Preserve underlying type and formatting info |
| `list` | `("__list__", tuple(...))` | Distinguish from tuple in formatted output |
| `tuple` | `("__tuple__", tuple(...))` | Distinguish from list |

**CLDR Plural Rule Preservation:** Decimal type-tagging uses `str(value)` instead of the numeric value. This preserves scale information critical for CLDR plural rules: `Decimal("1.0")` and `Decimal("1.00")` must cache separately because some locales have scale-dependent plural forms.

**Recursive Verification:**

The `IntegrityCacheEntry.verify()` method performs recursive integrity verification:

1. Recomputes entry checksum from current field values
2. For each `FrozenFluentError` in the errors tuple, calls `verify_integrity()`
3. Returns `True` only if ALL checks pass (entry checksum AND all error content hashes)

This defense-in-depth approach detects corruption at any level of the data hierarchy.

**Invariants:**
- Every `get()` verifies checksum before returning
- Corrupted entries are never returned (either raise or evict)
- Sequence numbers never decrease, even after `clear()`
- Metadata tampering is detected by checksum verification

**Trade-offs:**
- Checksum verification adds ~0.1 microseconds per `get()` - acceptable for financial correctness
- Write-once mode prevents legitimate cache updates - use only when data race prevention is critical
- Different timestamps produce different checksums - not suitable for content-only comparison
- Idempotent detection adds hash comparison on cache hit - negligible for concurrent workloads

### Integrity Exception Layer

**Responsibility:** Signal system failures distinct from Fluent errors.

**Design Decision:** Separate hierarchy from `FrozenFluentError` because:
1. Different error domains (system failure vs. translation issue)
2. Different handling requirements (escalate vs. fallback)
3. Prevents confusion when catching exceptions

**Hierarchy:**
```
DataIntegrityError (base - immutable after construction)
├── CacheCorruptionError       - Checksum mismatch detected
├── FormattingIntegrityError   - Strict mode formatting failure
├── ImmutabilityViolationError - Mutation attempt on frozen object
├── IntegrityCheckFailedError  - Generic verification failure
└── WriteConflictError         - Write-once cache violation
```

**Invariant:** All integrity exceptions carry `IntegrityContext` for post-mortem analysis.

## Security Model

### Attack Vectors Mitigated

| Attack | Mitigation |
|:-------|:-----------|
| Error mutation after logging | `__setattr__` raises after freeze |
| Subclass overrides | `@final` + `__init_subclass__` raises |
| Dynamic attribute injection | `__slots__` only, no `__dict__` |
| Hash tampering | Constant-time comparison |
| Cache poisoning | Checksum verification on every read |
| Data race overwrites | Write-once semantics option |
| Metadata tampering | Complete field coverage in checksums/hashes |
| Diagnostic field tampering | All 11 Diagnostic fields included in error hash |
| Timestamp/sequence forgery | Metadata included in cache checksum |
| Field concatenation collision | Length-prefixing prevents `("ab","c")` = `("a","bc")` |
| Type confusion in cache keys | Type-tagging distinguishes `1` from `1.0` from `True` |
| Decimal scale loss | `str(Decimal)` preserves scale for CLDR plural rules |
| Nested error corruption | Recursive verification checks entry AND all contained errors |

### Trust Boundaries

1. **External input** (FTL source, format arguments): Validated at parser/bundle boundary
2. **Cached data**: Verified on every read via checksum
3. **Error objects**: Immutable after construction

## Performance Characteristics

| Operation | Overhead | Acceptable Because |
|:----------|:---------|:-------------------|
| Error hash computation | ~0.1 microseconds | One-time at construction |
| Cache checksum verification | ~0.1 microseconds | Correctness over speed for financial |
| Slots vs dict | ~200 bytes saved per error | Net memory reduction |

## References

- [FrozenFluentError API](DOC_05_Errors.md)
- [ErrorCategory Enum](DOC_02_Types.md)
- [FluentBundle strict mode](DOC_01_Core.md)
- [Thread Safety](THREAD_SAFETY.md)
- [BLAKE2 Specification](https://www.blake2.net/)
