PROTOCOL: AGENT_FIRST_DOCUMENTATION
VERSION: 2.0
TARGET: AI Agents as Authors
SCOPE: All Project Documentation

================================================================================
PART I: SYSTEM DEFINITION
================================================================================

1. WHAT THIS PROTOCOL IS

A documentation system designed for AI agents to:
- CREATE documentation that other AI agents can efficiently consume
- MAINTAIN documentation in sync with code changes
- ROUTE queries to the correct documentation context

This is NOT a style guide. It is a machine-readable specification.

2. SYSTEM INVARIANTS

The following properties must hold at all times:

  INV-1: Every exported symbol has exactly one documentation entry.
  INV-2: Every documentation file has valid frontmatter.
  INV-3: Signatures in documentation match signatures in code.
  INV-4: No prose in reference documentation; fragments only.

When invariants break, the system is in an inconsistent state. Agents must
restore consistency before adding new content.

3. FEEDBACK MECHANISMS

Agents detect invariant violations through:

  SIGNAL-A: Orphan Detection
    - Symbol in code but not in docs → Add documentation entry
    - Symbol in docs but not in code → Remove documentation entry

  SIGNAL-B: Signature Drift
    - Parse code signature (AST or regex)
    - Compare to documented signature
    - Mismatch → Update documented signature, flag Contract for review

  SIGNAL-C: Staleness Indicators
    - project_version in frontmatter differs from actual version
    - last_updated older than significant code changes

================================================================================
PART II: FILE ARCHITECTURE
================================================================================

4. FILE TYPES

All documentation lives in docs/. Two types:

  REFERENCE (docs/DOC_*.md)
    Purpose: API signatures, contracts, constraints.
    Content: Schema-driven. No prose. No examples.
    Naming: DOC_<NN>_<Context>.md

  AUXILIARY (docs/*_GUIDE.md, docs/*.md without DOC_ prefix)
    Purpose: Tutorials, policies, glossaries.
    Content: Narrative with embedded code.
    Naming: <TOPIC>_GUIDE.md, QUICK_REFERENCE.md, TERMINOLOGY.md

5. FRONTMATTER SCHEMA (All Files)

Every file begins with YAML frontmatter:

```yaml
---
spec: AFAD-2
version: <project semver>
type: reference | guide | policy | glossary | index
context: <CONTEXT_ID>  # For reference files only
updated: <ISO-8601>
author: <agent_id | human_id>
route:
  keywords: [<terms that should find this file>]
  answers: [<questions this file answers>]
  related: [<linked files>]
---
```

Field rules:
- spec: Always "AFAD-2"
- type: Determines which schemas apply
- context: Required for type=reference; omit for auxiliary
- route: Required for index, errors, core; optional elsewhere

6. REFERENCE FILE CONTEXTS

Standard contexts (project may extend):

  00_Index    Navigation hub, export lists, routing table
  01_Core     High-frequency public API
  02_Types    Data structures, AST, type aliases
  03_<Domain> Primary domain (Parsing, IO, Services)
  04_<Domain> Secondary domain (Runtime, Middleware)
  05_Errors   Exception hierarchy, diagnostics
  06_Testing  Test infrastructure (optional)

Agents should create new contexts when:
- A domain has >30 symbols
- Symbols form a cohesive group
- Existing contexts would exceed 1000 lines

================================================================================
PART III: COMPONENT SCHEMAS
================================================================================

7. SCHEMA SELECTION

To document a component, follow this decision tree:

```
Is it a class/function/method?
  ├─ Yes → Use CALLABLE SCHEMA (Section 8)
  └─ No ─┬─ Is it a property/attribute?
         │    └─ Yes → Use PROPERTY SCHEMA (Section 9)
         ├─ Is it an enum?
         │    └─ Yes → Use ENUM SCHEMA (Section 10)
         ├─ Is it a type alias?
         │    └─ Yes → Use TYPE SCHEMA (Section 11)
         ├─ Is it a constant?
         │    └─ Yes → Use CONSTANT SCHEMA (Section 12)
         └─ Is it an exception?
              └─ Yes → Use EXCEPTION SCHEMA (Section 13)
```

8. CALLABLE SCHEMA

For functions, methods, classmethods, staticmethods, constructors.

```markdown
## `name`

### Signature
```<language>
[decorator if @classmethod/@staticmethod/@property]
def name(params) -> ReturnType:
```

### Contract
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `name` | `Type` | Y/N | <10-word fragment> |

### Constraints
- Return: <what it returns>
- Raises: <exceptions> | Never
- State: <mutation behavior> | Read-only | None
- Thread: Safe | Unsafe | <nuanced description>
- Version: Added vX.Y.Z | Changed vX.Y.Z <what changed>

---
```

Contract rules:
- Req column: "Y" or "N" only
- Description: Fragment, not sentence. No articles. Max 10 words.
- Omit rows for *args, **kwargs unless semantically significant

Constraints rules:
- Omit inapplicable lines (no "N/A")
- Always include Return and Raises
- Include Thread if method mutates state
- Include Version for features added after v1.0.0

9. PROPERTY SCHEMA

For @property decorated methods and dataclass fields.

```markdown
## `ClassName.property_name`

### Signature
```<language>
@property
def property_name(self) -> Type:
```

### Constraints
- Return: <description>
- State: Read-only
- Thread: Safe

---
```

No Contract table for properties.

10. ENUM SCHEMA

```markdown
## `EnumName`

### Signature
```<language>
class EnumName(Enum):  # or StrEnum, IntEnum
    MEMBER_A = value_a
    MEMBER_B = value_b
```

### Members
| Member | Value | Description |
|:-------|:------|:------------|
| `MEMBER_A` | `value_a` | <fragment> |

### Constraints
- Purpose: <why this enum exists>

---
```

For IntEnums with semantic ranges, add a Ranges section before Members.

11. TYPE SCHEMA

```markdown
## Type Aliases

### Signature
```<language>
type AliasName = UnionType | OtherType
```

### Constraints
- Cannot use with isinstance(). Use pattern matching.

---
```

Group related type aliases in one entry.

12. CONSTANT SCHEMA

```markdown
## `CONSTANT_NAME`

### Definition
```<language>
CONSTANT_NAME: Type = value
```

### Constraints
- Purpose: <why this constant exists>
- Location: <module.path>

---
```

13. EXCEPTION SCHEMA

Document exceptions in two parts:

A. Hierarchy tree (once per file):
```markdown
## Exception Hierarchy

```
BaseException
  ├─ ChildA
  │   └─ GrandchildA
  └─ ChildB
```
```

B. Individual entries for exceptions with parameters:
```markdown
## `ExceptionName`

### Signature
```<language>
class ExceptionName(ParentException):
    attribute: Type
```

### Contract
| Field | Type | Description |
|:------|:-----|:------------|
| `attribute` | `Type` | <fragment> |

### Constraints
- Purpose: <specialized error case>

---
```

For empty exceptions (inherit-only), use simplified form:
```markdown
## `ExceptionName`

### Signature
```<language>
class ExceptionName(ParentException): ...
```

### Constraints
- Purpose: <specialized error case>
- Inherits: All behavior from ParentException

---
```

================================================================================
PART IV: AUXILIARY DOCUMENTATION
================================================================================

14. AUXILIARY FILE TYPES

| Type | File Pattern | Purpose |
|------|--------------|---------|
| index | DOC_00_Index.md | Navigation, exports, routing |
| guide | *_GUIDE.md | Tutorials, how-to |
| policy | CONTRIBUTING.md | Standards, workflows |
| glossary | TERMINOLOGY.md | Term definitions |
| reference | docs/QUICK_REFERENCE.md | Cheat sheet |
| changelog | CHANGELOG.md | Version history |
| readme | README.md | Entry point, installation |

15. GUIDE STRUCTURE

```markdown
---
spec: AFAD-2
version: X.Y.Z
type: guide
updated: YYYY-MM-DD
author: agent_id
route:
  keywords: [topic keywords]
  answers: [questions answered]
  related: [linked files]
---

# <Topic> Guide

**Purpose**: <one sentence>
**Prerequisites**: <required knowledge>

## Overview

<2-3 paragraphs of context>

## Step 1: <Action Verb>

<instruction>

```<language>
# working code
```

## Step 2: <Action Verb>

...

## Summary

- Key point 1
- Key point 2

## See Also

- [Related Doc](path)
```

16. README EXCEPTION

README.md is a "storefront" - it sells the project. Exceptions granted:
- Code examples ARE allowed
- Comparison tables ARE encouraged
- Marketing language IS acceptable
- Max ~300 lines

README must include: Installation, Quick Start, Documentation links.
README must NOT include: Full API reference, troubleshooting, exhaustive examples.

17. QUICK_REFERENCE STRUCTURE

Task-oriented, copy-paste friendly:

```markdown
---
spec: AFAD-2
version: X.Y.Z
type: reference
updated: YYYY-MM-DD
---

# Quick Reference

## Task Category

### Task Name
```<language>
# working code
```

### Another Task
```<language>
# working code
```
```

No explanations longer than 2 sentences per task.

================================================================================
PART V: MAINTENANCE LOOPS
================================================================================

18. SYNCHRONIZATION PROTOCOL

When code changes, documentation must follow. Execute this loop:

```
1. INVENTORY
   - Parse entry point exports
   - Build symbol → context mapping

2. COMPARE
   - For each symbol: locate doc entry
   - Extract signature from markdown
   - Compare against code signature

3. RECONCILE
   - Missing symbol → Create entry (Section 7-13)
   - Signature mismatch → Update Signature block
   - Removed symbol → Delete entry

4. FINALIZE
   - Update frontmatter: version, updated
   - Validate invariants (Section 2)
   - Commit if valid
```

19. AUTONOMOUS AUTHORITY

AI agents have standing authority to:

  DELETE documentation when:
    - All documented symbols were removed from code
    - File duplicates another file entirely

  MERGE files when:
    - Two contexts have >50% overlap
    - One file has <5 entries

  SPLIT files when:
    - File exceeds 1000 lines
    - Two distinct sub-contexts emerge

  CREATE files when:
    - New domain emerges (>10 related symbols)
    - Existing contexts would become unwieldy

Agents MUST log actions in commit messages.

================================================================================
PART VI: ESCAPE HATCHES
================================================================================

20. HANDLING EXCEPTIONS TO SCHEMA

Not everything fits schemas. Use these mechanisms:

A. NOTES SECTION
Add a ## Notes section at the end of any entry for:
- Quirks that don't fit Constraints
- Historical context
- Implementation warnings

```markdown
### Constraints
- Return: Result object
- State: Read-only

### Notes
- Pre-v2.0: This returned None on failure.
- Performance: O(n²) for inputs >1000 items.

---
```

B. DESIGN DECISIONS
For architectural choices that affect multiple components:

```markdown
## Design Decisions

### <Decision Name>
**Context**: <what problem or choice was faced>
**Decision**: <what was chosen>
**Rationale**: <why this choice>
**Alternatives**: <what was rejected and why>
```

C. CROSS-CUTTING CONCERNS
For content spanning multiple contexts:

```markdown
## See Also

- [DOC_XX.md](DOC_XX.md): <relationship>
- [source.py](../src/source.py): Implementation
```

================================================================================
PART VII: VALIDATION
================================================================================

21. PRE-COMMIT CHECKS

Before any documentation commit:

  [ ] Frontmatter present and valid?
  [ ] Every entry has Signature and Constraints?
  [ ] Contract tables use "Y/N" (not "Yes/No")?
  [ ] Descriptions are fragments (<10 words)?
  [ ] No orphaned symbols (both directions)?
  [ ] Version field matches project version?

22. STRUCTURAL VALIDATION

Automated checks (CI integration):

| Check | Rule | Exit Code |
|-------|------|-----------|
| Frontmatter | Valid YAML, required fields present | 1 |
| Schema | Entry sections in correct order | 2 |
| Signatures | Match code (AST comparison) | 3 |
| Orphans | No undocumented exports, no stale entries | 4 |
| Prose | No sentences in Contract descriptions | 5 |

Exit 0 = all pass.

================================================================================
END OF PROTOCOL
================================================================================

VERSION HISTORY

2.0 (2025-12-27)
- Unified AFAD and AFAD-AUX into single protocol
- Replaced enumerated schemas with decision tree
- Unified frontmatter format (YAML for all)
- Added escape hatches (Notes, Design Decisions, Cross-cutting)
- Reduced from ~1700 lines to ~400 lines (76% reduction)
- Replaced goal-oriented language with system invariants
- Added feedback mechanisms for detecting inconsistency

1.1 (2025-12-26)
- Added retrieval hints, version annotations, extended schemas

1.0 (2025-12-01)
- Initial release
