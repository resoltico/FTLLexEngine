---
afad: "3.5"
version: "0.163.0"
domain: VALIDATION
updated: "2026-04-23"
route:
  keywords: [validation, validate_resource, ValidationResult, require_clean, boot validation, message schemas]
  questions: ["how do I validate FTL before loading it?", "how do I fail fast at startup?", "how do I validate message variables?"]
---

# Validation Guide

**Purpose**: Validate FTL source, loaded resources, and message-variable contracts before serving traffic.
**Prerequisites**: `validate_resource()` works in parser-only installs; the loaded-resource and boot-validation sections assume the full runtime install.

## Resource Validation

Use `validate_resource()` to check FTL source before adding it to a bundle.

```python
from ftllexengine import validate_resource

result = validate_resource("welcome = Hello, { $name }!")
assert result.is_valid is True
assert result.error_count == 0
assert result.warning_count == 0
```

`ValidationResult` separates:

- `errors`: structural or syntax validation failures.
- `warnings`: semantic problems such as unresolved references.
- `annotations`: parser-level annotations recovered from junk input.

## Loaded-Resource Validation

`FluentLocalization.require_clean()` converts load summary problems into an `IntegrityCheckFailedError`. This is the fail-fast path for production startup and therefore requires the full runtime install.

## Message Variable Contracts

Use `validate_message_variables()` when you already have an AST node, or `FluentLocalization.validate_message_schemas()` when you want to enforce contracts across a loaded localization set.

## Recommended Startup Pattern

For audited startup, prefer `LocalizationBootConfig.boot()` or `boot_simple()` over assembling the boot sequence by hand. That path loads resources, checks load cleanliness, enforces required message presence, and validates declared message schemas in one place. `LocalizationBootConfig` instances are one-shot coordinators, so create a fresh instance for each boot attempt.
