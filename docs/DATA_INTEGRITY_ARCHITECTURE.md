---
afad: "4.0"
version: "0.164.0"
domain: ARCHITECTURE
updated: "2026-04-24"
route:
  keywords: [data integrity, strict mode, FrozenFluentError, IntegrityCheckFailedError, cache audit, boot validation]
  questions: ["how does strict mode relate to integrity?", "what audit evidence does the runtime expose?", "what is boot validation for?"]
---

# Data Integrity Architecture

**Purpose**: Summarize the fail-fast and immutable-evidence patterns used by FTLLexEngine.
**Prerequisites**: Familiarity with `FluentBundle`, `FluentLocalization`, and `LocalizationBootConfig` from the full runtime install.

## Overview

The library pushes validation as early as possible and represents runtime failures as immutable, structured evidence:

- `FrozenFluentError` captures formatting and parsing failures without mutable side channels.
- `FormattingIntegrityError`, `SyntaxIntegrityError`, and `IntegrityCheckFailedError` surface strict-mode failures explicitly.
- `LoadSummary`, `ResourceLoadResult`, and boot schema results provide startup evidence for localization initialization.
- `CacheConfig(enable_audit=True)` exposes immutable audit-log entries for cache operations.

## Strict Mode

- `FluentBundle` and `FluentLocalization` default to `strict=True`.
- Resource junk and formatting failures raise instead of silently degrading.
- `strict=False` is an explicit opt-in for `(result, errors)` tuple returns on formatting APIs that would otherwise raise.

## Boot Validation

`LocalizationBootConfig.boot()` is the canonical fail-fast startup path when resources must be clean before the application accepts traffic. It combines resource loading, `require_clean()`, required-message enforcement, and message-schema validation. The config object is intentionally one-shot: create a new instance instead of reusing one after `boot()` or `boot_simple()`.

## Internal Seams

The public contract stays centered on the facade types, but the implementation is intentionally partitioned so integrity behavior can evolve without collapsing back into single large modules:

- `runtime.bundle` remains the public home of `FluentBundle`, while lifecycle and mutation responsibilities are delegated into focused internal runtime modules.
- `runtime.cache` remains the public cache surface, while audit-log behavior, stats helpers, and cache-key shaping live in dedicated internal cache modules.
- `runtime.function_bridge` remains the public registry surface, while decorator metadata attachment and registry introspection helpers are separated internally.
- `diagnostics.templates` remains the public diagnostic-template namespace, while reference, runtime, and parsing template families are maintained in smaller focused modules.

This split does not change user imports. It preserves clearer ownership boundaries for audit evidence, strict-mode failures, and runtime mutation paths.
