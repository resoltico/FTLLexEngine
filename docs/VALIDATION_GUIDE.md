---
afad: "3.1"
version: "0.97.0"
domain: validation
updated: "2026-01-28"
route:
  keywords: [validation, validate_resource, SemanticValidator, duplicate, cycle detection, FTL validation]
  questions: ["how to validate FTL?", "what validation checks exist?", "where is duplicate detection?", "how to detect cycles?"]
---

# Validation Guide

**Purpose**: Understand FTLLexEngine's validation architecture and responsibility distribution.
**Prerequisites**: Basic FTL syntax knowledge.

## Overview

FTLLexEngine implements a **two-tier validation architecture**:

1. **Resource-level validation** (`validate_resource()`): Checks spanning multiple entries
2. **AST node-level validation** (`SemanticValidator`): Checks within individual AST nodes

This separation follows single-responsibility principle: each validator handles checks appropriate to its scope.

---

## Validation Responsibility Matrix

| Check | Module | Function/Class | Scope |
|:------|:-------|:---------------|:------|
| Syntax errors (Junk) | `validation.resource` | `_extract_syntax_errors()` | Resource |
| Duplicate message IDs | `validation.resource` | `_collect_entries()` | Resource |
| Duplicate term IDs | `validation.resource` | `_collect_entries()` | Resource |
| Duplicate attribute IDs | `validation.resource` | `_collect_entries()` | Entry |
| Messages without value/attrs | `validation.resource` | `_collect_entries()` | Entry |
| Shadow warnings | `validation.resource` | `_collect_entries()` | Resource |
| Undefined message refs | `validation.resource` | `_check_undefined_references()` | Resource |
| Undefined term refs | `validation.resource` | `_check_undefined_references()` | Resource |
| Circular references | `validation.resource` | `_detect_circular_references()` | Resource |
| Long reference chains | `validation.resource` | `_detect_long_chains()` | Resource |
| Term missing value | `syntax.validator` | `SemanticValidator` | Node |
| Select without default | `syntax.validator` | `SemanticValidator` | Node |
| Select without variants | `syntax.validator` | `SemanticValidator` | Node |
| Duplicate variant keys | `syntax.validator` | `SemanticValidator` | Node |
| Duplicate named arguments | `syntax.validator` | `SemanticValidator` | Node |
| Term positional args warning | `syntax.validator` | `SemanticValidator` | Node |

---

## Quick Start

```python
from ftllexengine import parse_ftl
from ftllexengine.validation import validate_resource

# Parse FTL content
source = """
hello = Hello, { $name }!
-brand = FTLLexEngine
welcome = Welcome to { -brand }
"""

resource = parse_ftl(source)

# Validate
result = validate_resource(resource)

if result.is_valid:
    print("Validation passed")
else:
    for error in result.errors:
        print(f"Error: {error.code} - {error.message}")
    for warning in result.warnings:
        print(f"Warning: {warning.code} - {warning.message}")
```

---

## Resource-Level Validation

`validate_resource()` orchestrates six validation passes:

### Pass 1: Syntax Error Extraction

Converts `Junk` entries (unparseable content) to structured errors.

```python
# FTL with syntax error
source = "hello = Hello { missing-close"
resource = parse_ftl(source)
result = validate_resource(resource)
# Error: VALIDATION_PARSE_ERROR
```

### Pass 2: Entry Collection and Duplicates

Checks for duplicate IDs within namespaces and duplicate attributes within entries.

```python
# Duplicate message ID
source = """
hello = First
hello = Second
"""
# Warning: VALIDATION_DUPLICATE_ID - "Duplicate message ID 'hello'"
```

**Namespace Separation**: Per Fluent spec, messages and terms have separate namespaces:
```python
# NOT a duplicate - different namespaces
source = """
brand = Brand message
-brand = Brand term
"""
# No warning: 'brand' and '-brand' coexist
```

### Pass 3: Undefined Reference Detection

Identifies references to non-existent messages or terms.

```python
source = """
hello = { greeting }
-missing = { -nonexistent }
"""
# Warning: VALIDATION_UNDEFINED_MESSAGE - "Message 'hello' references undefined message 'greeting'"
# Warning: VALIDATION_UNDEFINED_TERM - "Term '-missing' references undefined term '-nonexistent'"
```

### Pass 4: Circular Reference Detection

Detects cycles in the message/term dependency graph.

```python
source = """
a = { b }
b = { c }
c = { a }
"""
# Warning: VALIDATION_CIRCULAR_REF - "Circular reference detected: a -> b -> c -> a"
```

**Cross-Type Cycles**: The validator builds a unified graph to detect cycles spanning both messages and terms:
```python
source = """
msg = { -term }
-term = { msg }
"""
# Warning: Detects message -> term -> message cycle
```

**Cross-Resource Cycles**: When validating via `FluentBundle.validate_resource()`, the validator also detects cycles involving entries already loaded in the bundle:
```python
bundle = FluentBundle("en")
bundle.add_resource("msg_a = { msg_b }")  # msg_a depends on msg_b

# Now validate a resource that completes the cycle
result = bundle.validate_resource("msg_b = { msg_a }")
# Warning: Circular reference detected - msg_a and msg_b form a cycle
```

This cross-resource detection works because the bundle tracks dependencies for all loaded entries.

### Pass 5: Long Chain Detection

Warns about reference chains approaching `MAX_DEPTH` limit.

```python
# Chain of 90 messages (warning threshold at MAX_DEPTH - 10)
# Warning: VALIDATION_LONG_CHAIN
```

### Pass 6: Semantic Validation

Delegates to `SemanticValidator` for AST node-level checks.

---

## AST Node-Level Validation (SemanticValidator)

`SemanticValidator` checks semantic correctness within individual AST nodes.

### Term Must Have Value

```python
source = "-empty"  # Term without value
# Error: VALIDATION_TERM_NO_VALUE
```

### Select Expression Requirements

```python
# Missing default variant
source = """
count = { $n ->
    [one] One
    [other] Other
}
"""
# Error: VALIDATION_SELECT_NO_DEFAULT - must have exactly one *[default]

# Missing variants
source = "count = { $n -> }"
# Error: VALIDATION_SELECT_NO_VARIANTS

# Duplicate variant keys
source = """
count = { $n ->
    [one] First one
    [one] Second one
   *[other] Other
}
"""
# Error: VALIDATION_VARIANT_DUPLICATE
```

### Duplicate Named Arguments

```python
source = "msg = { NUMBER($n, style: 'decimal', style: 'percent') }"
# Error: VALIDATION_NAMED_ARG_DUPLICATE
```

### Term Positional Arguments Warning

Per Fluent specification, terms only accept named arguments. Positional arguments are silently ignored at runtime. The validator warns about this to catch likely user errors:

```python
source = """
-brand = Acme Corp
msg = { -brand($value) }
"""
# Warning: VALIDATION_TERM_POSITIONAL_ARGS - "Term '-brand' called with positional arguments; positional arguments are ignored for term references"
```

---

## Architecture Rationale

**Why Two Tiers?**

| Concern | Level | Example |
|:--------|:------|:--------|
| Cross-entry relationships | Resource | Circular references between messages |
| Entry-spanning checks | Resource | Duplicate attribute IDs across attributes |
| Node-internal rules | AST Node | Select expression must have default |
| Call argument rules | AST Node | Named argument uniqueness |

Attempting to consolidate all checks into one validator would create a "god class" with mixed concerns. The current design:

1. `validate_resource()` owns the resource-level view
2. `SemanticValidator` owns the node-level view
3. Each is testable independently
4. Each has clear responsibility boundaries

---

## Integration with FluentBundle

`FluentBundle.add_resource()` automatically validates during resource loading:

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US")
errors = bundle.add_resource("hello = Hello")

if errors:
    for error in errors:
        print(f"Load error: {error}")
```

For standalone validation without a bundle (CI/CD pipelines, linters):

```python
from ftllexengine import parse_ftl
from ftllexengine.validation import validate_resource

result = validate_resource(parse_ftl(ftl_content))
```

---

## Validation Result Structure

```python
@dataclass
class ValidationResult:
    errors: list[ValidationError]    # Blocking issues
    warnings: list[ValidationWarning] # Non-blocking issues
    annotations: list[Annotation]    # Parser annotations

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0
```

**Error vs Warning**:
- **Errors**: Prevent correct resolution (syntax errors, missing term values)
- **Warnings**: May indicate issues but don't prevent resolution (duplicates, undefined refs)

---

## Summary

| Validator | Location | Checks |
|:----------|:---------|:-------|
| `validate_resource()` | `validation/resource.py` | Duplicates, cycles, undefined refs, chains |
| `SemanticValidator` | `syntax/validator.py` | Term values, select rules, argument uniqueness |

**Key Insight**: If you're looking for a specific check, consult the responsibility matrix. Checks spanning multiple entries are in `validate_resource()`; checks within a single AST node are in `SemanticValidator`.
