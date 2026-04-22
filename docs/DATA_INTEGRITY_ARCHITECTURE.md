---
afad: "3.5"
version: "0.163.0"
domain: ARCHITECTURE
updated: "2026-04-22"
route:
  keywords: [data integrity, strict mode, FrozenFluentError, IntegrityCheckFailedError, cache audit, boot validation]
  questions: ["how does strict mode relate to integrity?", "what audit evidence does the runtime expose?", "what is boot validation for?"]
---

# Data Integrity Architecture

**Purpose**: Summarize the fail-fast and immutable-evidence patterns used by FTLLexEngine.
**Prerequisites**: Familiarity with `FluentBundle`, `FluentLocalization`, and `LocalizationBootConfig`.

## Overview

The library pushes validation as early as possible and represents runtime failures as immutable, structured evidence:

- `FrozenFluentError` captures formatting and parsing failures without mutable side channels.
- `FormattingIntegrityError`, `SyntaxIntegrityError`, and `IntegrityCheckFailedError` surface strict-mode failures explicitly.
- `LoadSummary`, `ResourceLoadResult`, and boot schema results provide startup evidence for localization initialization.
- `CacheConfig(enable_audit=True)` exposes immutable audit-log entries for cache operations.

## Strict Mode

- `FluentBundle` and `FluentLocalization` default to `strict=True`.
- Resource junk and formatting failures raise instead of silently degrading.
- `strict=False` is an explicit opt-in for fallback-return behavior.

## Boot Validation

`LocalizationBootConfig.boot()` is the canonical fail-fast startup path when resources must be clean before the application accepts traffic. It combines resource loading, `require_clean()`, required-message enforcement, and message-schema validation. The config object is intentionally one-shot: create a new instance instead of reusing one after `boot()` or `boot_simple()`.
