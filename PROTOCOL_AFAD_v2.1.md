PROTOCOL: AGENT_FIRST_DOCUMENTATION
VERSION: 2.1
STATUS: Refined Second Pass

================================================================================
LAYER 0: PHILOSOPHY
================================================================================

1. THE MENTAL MODEL

Documentation is a **knowledge graph**, not a collection of files.

  NODES: Components (functions, classes, types, constants)
  EDGES: Relationships (calls, inherits, uses, relates-to)
  CLUSTERS: Contexts (domains of related concepts)

When an agent reads or writes documentation, it is traversing and modifying
this graph. Files are merely the serialization format.

Why this matters:
- A node without edges is orphaned (retrieval failure)
- A node with too many inbound edges is a hub (potential file split)
- A cluster with weak internal cohesion should be reorganized
- Query routing = finding the shortest path from question to answer

2. THE DUAL AUDIENCE PROBLEM

Documentation has asymmetric readers and writers:

  WRITERS: AI agents (100% of authors)
  READERS: AI agents (~80%) + Humans (~20%)

This creates tension:
- Agents prefer structured, parseable formats (YAML, tables)
- Humans prefer narrative, examples, progressive disclosure
- Agents are token-sensitive; humans are not

Resolution:
- REFERENCE docs optimize for agents (structured, minimal)
- AUXILIARY docs accommodate humans (narrative, examples allowed)
- Both use the same frontmatter (unified retrieval)

3. THE RETRIEVAL OPTIMIZATION PRINCIPLE

For RAG systems, chunk semantics matter more than chunk size.

  BAD:  One file with 50 unrelated functions (embedding = noise)
  GOOD: One file per cohesive concept cluster (embedding = signal)

  BAD:  Long prose descriptions (token waste, embedding dilution)
  GOOD: Keyword-dense fragments (high signal density)

Practical implication:
- Each DOC file should represent a **single semantic domain**
- Each component entry should be **self-contained** (no external dependencies to understand it)
- Cross-references are edges, not content (don't duplicate; link)

4. PRIORITY HIERARCHY

Not all rules are equal. When constraints conflict, higher priority wins.

  P0 (CRITICAL): Signature accuracy, orphan prevention
  P1 (IMPORTANT): Schema compliance, fragment style
  P2 (STYLISTIC): Formatting consistency, ordering

Example: If a signature is complex and doesn't fit the standard Contract table
format (P1), you may deviate from the schema to ensure accuracy (P0).

================================================================================
LAYER 1: CORE INVARIANTS
================================================================================

5. SYSTEM PROPERTIES

These properties must hold. If violated, the system is broken.

  INV-1  COMPLETENESS
         Every exported symbol has exactly one documentation entry.
         Detection: Parse exports → diff against documented symbols.

  INV-2  ACCURACY
         Every documented signature matches the code signature.
         Detection: AST extraction → string comparison (normalized).

  INV-3  FRESHNESS
         Documentation version matches code version.
         Detection: Compare frontmatter.version to pyproject.toml/package.json.

  INV-4  NAVIGABILITY
         Every documentation file is reachable from the index.
         Detection: Crawl from DOC_00_Index → ensure full coverage.

Invariants are binary (true/false). Agents must restore truth before proceeding.

6. FEEDBACK SIGNALS

Agents detect invariant violations through these mechanisms:

  ORPHAN-CODE: Symbol exported but not documented.
    → Action: Create entry using appropriate schema.

  ORPHAN-DOC: Symbol documented but not exported.
    → Action: Remove entry (or verify internal-use documentation is intentional).

  DRIFT-SIGNATURE: Code signature differs from documented signature.
    → Action: Update Signature block. Flag Contract for review.

  DRIFT-VERSION: Frontmatter version < code version.
    → Action: Update frontmatter. Audit for undocumented changes.

  ISLAND-FILE: Documentation file not linked from index.
    → Action: Add to index routing table. Verify intentional isolation.

================================================================================
LAYER 2: FILE ARCHITECTURE
================================================================================

7. THE TWO-TIER SYSTEM

All documentation lives in docs/. Two tiers:

  ┌─────────────────────────────────────────────────────────────────────┐
  │  REFERENCE TIER (DOC_*.md)                                          │
  │  ─────────────────────────────────────────────────────────────────  │
  │  Purpose:   API contracts (signatures, parameters, constraints)     │
  │  Style:     Declarative, schema-driven, no prose                    │
  │  Audience:  Primarily AI agents; secondarily IDEs and tools         │
  │  Chunking:  Each entry is a self-contained retrieval unit           │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │  AUXILIARY TIER (*_GUIDE.md, *.md without DOC_ prefix)              │
  │  ─────────────────────────────────────────────────────────────────  │
  │  Purpose:   Tutorials, policies, glossaries, cheat sheets           │
  │  Style:     Narrative with embedded code                            │
  │  Audience:  Primarily humans; secondarily AI for contextual queries │
  │  Chunking:  Section-based (h2 headers define chunks)                │
  └─────────────────────────────────────────────────────────────────────┘

8. FRONTMATTER (All Files)

Unified YAML frontmatter enables consistent retrieval:

```yaml
---
afad: "2.1"                          # Protocol version (always "2.1")
version: "X.Y.Z"                     # Project version this documents
tier: reference | auxiliary          # Which tier (determines schema expectations)
domain: <DOMAIN_ID>                  # Semantic domain (CORE, TYPES, PARSING, etc.)
updated: "YYYY-MM-DDTHH:MM:SSZ"      # ISO-8601 UTC timestamp
author: <agent_id>                   # Last modifier

# Routing metadata (enables knowledge graph edges)
route:
  keywords: [<search terms>]         # Words that should retrieve this file
  questions: [<natural language>]    # Questions this file answers
  upstream: [<files that link here>] # Inbound edges (for graph analysis)
  downstream: [<files this links to>]# Outbound edges
---
```

Field semantics:
- `afad`: Protocol version. Enables schema evolution.
- `tier`: Determines which Layer 3 schemas apply.
- `domain`: Semantic clustering. Used for context-aware retrieval.
- `route.upstream/downstream`: Explicit graph edges for navigation.

9. REFERENCE FILE DOMAINS

Standard domains (extend as needed):

  Domain       │ Typical Contents                        │ File
  ─────────────┼─────────────────────────────────────────┼──────────────────
  INDEX        │ Navigation, exports, routing table      │ DOC_00_Index.md
  CORE         │ Primary public API (high-frequency)     │ DOC_01_Core.md
  TYPES        │ Data structures, AST nodes, aliases     │ DOC_02_Types.md
  <PRIMARY>    │ Main domain (Parsing, IO, Services)     │ DOC_03_<Name>.md
  <SECONDARY>  │ Secondary domain (Runtime, Advanced)    │ DOC_04_<Name>.md
  ERRORS       │ Exception hierarchy, diagnostics        │ DOC_05_Errors.md
  TESTING      │ Test infrastructure (optional)          │ DOC_06_Testing.md

Domain creation heuristics:
- Create new domain when: >25 related symbols OR distinct conceptual cluster
- Merge domains when: <10 entries OR high cross-reference density
- Split domain when: >80 entries OR low internal cohesion

10. AUXILIARY FILE PATTERNS

  Pattern              │ Purpose                    │ Location
  ─────────────────────┼────────────────────────────┼──────────────
  README.md            │ Project storefront         │ Root
  CHANGELOG.md         │ Version history            │ Root
  CONTRIBUTING.md      │ Contributor policy         │ Root
  *_GUIDE.md           │ Tutorial/how-to            │ docs/
  QUICK_REFERENCE.md   │ Cheat sheet                │ docs/
  TERMINOLOGY.md       │ Glossary                   │ docs/
  MIGRATION.md         │ Upgrade paths              │ docs/

================================================================================
LAYER 3: COMPONENT SCHEMAS
================================================================================

11. SCHEMA PHILOSOPHY

Schemas are **templates with semantics**, not rigid structures.

Core principle: Every schema has:
- REQUIRED sections (omission is a violation)
- OPTIONAL sections (include when applicable)
- EXTENSION points (for domain-specific additions)

The agent's job is to select the right schema and apply judgment
for optional/extension content.

12. SCHEMA SELECTOR

```
START
  │
  ├─ Is it callable (function, method, constructor)?
  │     └─ Yes → CALLABLE SCHEMA (§13)
  │
  ├─ Is it a property (@property, dataclass field)?
  │     └─ Yes → PROPERTY SCHEMA (§14)
  │
  ├─ Is it an enumeration (Enum, StrEnum, IntEnum)?
  │     └─ Yes → ENUM SCHEMA (§15)
  │
  ├─ Is it a type alias (PEP 695 `type X = ...`)?
  │     └─ Yes → TYPE SCHEMA (§16)
  │
  ├─ Is it a constant (module-level `UPPER_CASE`)?
  │     └─ Yes → CONSTANT SCHEMA (§17)
  │
  ├─ Is it an exception class?
  │     └─ Yes → EXCEPTION SCHEMA (§18)
  │
  └─ Does it not fit any category?
        └─ Yes → GENERIC SCHEMA (§19) with Notes explaining structure
```

13. CALLABLE SCHEMA

```markdown
## `component_name`

### Signature
```python
def component_name(
    positional: Type,
    /,
    standard: Type = default,
    *,
    keyword_only: Type = default,
) -> ReturnType:
```

### Contract
| Parameter | Type | Req | Semantics |
|:----------|:-----|:----|:----------|
| `positional` | `Type` | Y | <what it represents, max 10 words> |

### Constraints
- Return: <what is returned, including edge cases>
- Raises: <ExceptionType> when <condition> | Never
- State: <mutation behavior> | Read-only | Pure
- Thread: Safe | Unsafe | <nuanced: "Safe for reads, unsafe for writes">

### [Optional] Notes
- <Historical context, performance characteristics, non-obvious behavior>

---
```

REQUIRED: Signature, Contract (unless no parameters), Constraints
OPTIONAL: Notes (when behavior has caveats)

Contract column semantics:
- Parameter: Exact name with backticks
- Type: Full type annotation with backticks
- Req: "Y" (required) or "N" (optional) — never "Yes"/"No"
- Semantics: Fragment describing what this parameter represents (not "The X parameter")

Constraint field vocabulary:
- Return: Always present. Describe the return value.
- Raises: Always present. Use "Never" if guaranteed not to raise.
- State: Include if method modifies anything.
- Thread: Include if concurrent access is relevant.
- Version: Include for features added after 1.0 ("Added v2.3.0", "Changed v2.5.0")
- Complexity: Include for algorithms ("O(n log n) time, O(n) space")
- Security: Include for input validation, depth guards, sanitization

14. PROPERTY SCHEMA

```markdown
## `ClassName.property_name`

### Signature
```python
@property
def property_name(self) -> Type:
```

### Constraints
- Return: <what the property returns>
- State: Read-only | Computed | Cached

---
```

REQUIRED: Signature, Constraints
OPTIONAL: Notes

No Contract table (properties have no parameters).

15. ENUM SCHEMA

```markdown
## `EnumName`

### Signature
```python
class EnumName(Enum):  # or StrEnum, IntEnum
    MEMBER_A = value_a
    MEMBER_B = value_b
```

### Members
| Member | Value | Semantics |
|:-------|:------|:----------|
| `MEMBER_A` | `value_a` | <what this member represents> |

### Constraints
- Purpose: <why this enum exists>
- String: Members are/are not strings (for StrEnum)

---
```

For IntEnums with semantic ranges (like error codes):

```markdown
### Ranges
| Range | Category | Purpose |
|:------|:---------|:--------|
| 1000-1999 | Syntax | FTL parsing errors |
| 2000-2999 | Resolution | Runtime resolution errors |
```

16. TYPE SCHEMA

```markdown
## `TypeAliasName`

### Definition
```python
type TypeAliasName = ComponentA | ComponentB | ComponentC
```

### Constraints
- Purpose: <what this type represents>
- Narrowing: Use pattern matching or `.guard()` methods (isinstance fails)

---
```

Group related aliases when they form a family.

17. CONSTANT SCHEMA

```markdown
## `CONSTANT_NAME`

### Definition
```python
CONSTANT_NAME: Type = value
```

### Constraints
- Purpose: <why this constant exists>
- Location: `module.path` (if not in main exports)

---
```

18. EXCEPTION SCHEMA

Document the hierarchy once, then individual exceptions:

```markdown
## Exception Hierarchy

```
BaseError
├── SyntaxError
│   └── ParseError
├── RuntimeError
│   ├── ReferenceError
│   └── ResolutionError
└── ValidationError
```

---

## `SpecificException`

### Signature
```python
class SpecificException(ParentException):
    attribute: Type
```

### Contract
| Attribute | Type | Semantics |
|:----------|:-----|:----------|
| `attribute` | `Type` | <what this carries> |

### Constraints
- Purpose: <specific error scenario this represents>
- Recovery: <suggested recovery action, if any>

---
```

For empty exceptions (inherit-only behavior):

```markdown
## `EmptyException`

### Signature
```python
class EmptyException(ParentException): ...
```

### Constraints
- Purpose: <specialized error scenario>
- Inherits: Full behavior from ParentException

---
```

19. GENERIC SCHEMA

For components that don't fit standard schemas:

```markdown
## `component_name`

### Definition
```python
<whatever the component is>
```

### Notes
- Structure: <explain what this is and why it doesn't fit standard schemas>
- Usage: <how to use it>

---
```

Always include Notes explaining why the generic schema was necessary.

================================================================================
LAYER 4: AUXILIARY DOCUMENTATION
================================================================================

20. AUXILIARY SCHEMA FLEXIBILITY

Auxiliary docs have more structural freedom than reference docs.
However, they must still have:
- Valid frontmatter (Layer 2, §8)
- Clear purpose statement
- Working code examples (verified against current API)

21. GUIDE TEMPLATE

```markdown
---
afad: "2.1"
version: "X.Y.Z"
tier: auxiliary
domain: <topic>
updated: "YYYY-MM-DDTHH:MM:SSZ"
author: agent_id
route:
  keywords: [topic, related, terms]
  questions: ["how do I X?", "what is Y?"]
  downstream: [DOC_01_Core.md, examples/example.py]
---

# <Topic> Guide

**Purpose**: <one sentence describing what reader will learn>
**Prerequisites**: <required knowledge to benefit from this guide>

## Overview

<2-3 paragraphs of context. Why does this topic matter?>

## <Action Step 1>

<Instruction paragraph>

```python
# Working code example
result = function(args)
```

<Explanation of what happened>

## <Action Step 2>

...

## Summary

- Key takeaway 1
- Key takeaway 2
- Key takeaway 3

## See Also

- [Related Guide](RELATED_GUIDE.md): <relationship>
- [API Reference](DOC_01_Core.md#component): Detailed API
```

22. README EXCEPTION

README.md is a **storefront**. It sells the project.

Permitted (exceptional):
- Code examples demonstrating value proposition
- Comparison tables (before/after, us vs alternatives)
- Marketing language ("fast", "simple", "powerful")
- Badges, hero images, table of contents

Required:
- Installation instructions
- Quick Start with working code
- Links to deeper documentation

Prohibited:
- Full API reference (link to docs/)
- Exhaustive examples (link to examples/)
- Troubleshooting (link to guides)

Target: Reader decides to try the project within 60 seconds.

23. QUICK_REFERENCE PATTERN

Task-oriented, zero prose, copy-paste friendly:

```markdown
## Task Category

### Specific Task
```python
result = function(args)
```

### Another Task
```python
other = different(params)
```
```

Maximum 2 sentences of context per category.
Each snippet must be independently runnable.

================================================================================
LAYER 5: ADAPTATION MECHANISMS
================================================================================

24. SCALE CALIBRATION

Protocol applies differently at different scales:

  SMALL PROJECT (<20 exports)
    - May collapse domains (CORE+TYPES in one file)
    - Routing table may be simple list
    - Testing context often unnecessary

  MEDIUM PROJECT (20-100 exports)
    - Standard domain separation
    - Full routing table
    - Testing context if test infrastructure is complex

  LARGE PROJECT (>100 exports)
    - May need additional domain splits
    - Consider sub-indices for domain clusters
    - Multiple testing files if warranted

Agents should adapt, not rigidly apply.

25. ESCAPE HATCHES

When reality doesn't fit schemas:

A. NOTES SECTION
   Add `### Notes` to any entry for:
   - Historical context ("Pre-v2.0 returned None")
   - Performance warnings ("O(n²) for large inputs")
   - Non-obvious behavior ("Caches results internally")
   - Deprecation notices ("Deprecated in v3.0, use X instead")

B. DESIGN DECISIONS SECTION
   For architectural choices affecting multiple components:

   ```markdown
   ## Design Decisions

   ### <Decision Name>
   **Context**: <what problem required a decision>
   **Decision**: <what was chosen>
   **Rationale**: <why, including rejected alternatives>
   ```

C. DOMAIN-SPECIFIC EXTENSIONS
   Domains may define additional sections. Examples:
   - TESTING domain: Marker tables, profile configurations
   - ERRORS domain: Diagnostic code ranges
   - PARSING domain: Grammar rule references

   Document domain extensions in the domain's introduction.

26. GRACEFUL DEGRADATION

When agents cannot fully comply:

  PRIORITY ORDER (attempt in sequence):
  1. Full schema compliance
  2. Correct signature with simplified Contract
  3. Signature-only with Notes explaining limitations
  4. Placeholder entry with TODO marker

  Never leave undocumented exports. Partial documentation > none.

================================================================================
LAYER 6: MAINTENANCE PROTOCOL
================================================================================

27. SYNCHRONIZATION LOOP

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  TRIGGER: Code change detected (new export, signature change, removal)      │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. INVENTORY                                                               │
│     - Parse entry point (__init__.py, index.ts, mod.rs)                     │
│     - Extract all public exports with signatures                            │
│     - Build: symbol → (signature, domain) mapping                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  2. COMPARE                                                                 │
│     - For each export: find corresponding DOC entry                         │
│     - Extract documented signature from markdown                            │
│     - Diff: code_signature vs doc_signature                                 │
│     - Categorize: MATCH | DRIFT | ORPHAN-CODE | ORPHAN-DOC                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  3. RECONCILE                                                               │
│     - MATCH: No action needed                                               │
│     - DRIFT: Update Signature block, review Contract                        │
│     - ORPHAN-CODE: Create entry using schema selector (§12)                 │
│     - ORPHAN-DOC: Remove entry (or verify intentional)                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  4. FINALIZE                                                                │
│     - Update frontmatter: version, updated, author                          │
│     - Verify invariants (§5): COMPLETENESS, ACCURACY, FRESHNESS, NAVIGABILITY│
│     - If all pass: commit                                                   │
│     - If any fail: diagnose and retry from step 3                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

28. AUTONOMOUS AUTHORITY

AI agents have standing authority to restructure documentation:

  ACTION       │ WHEN                                    │ REQUIRED
  ─────────────┼─────────────────────────────────────────┼─────────────────────
  DELETE file  │ All entries removed OR file is duplicate│ Log in commit
  MERGE files  │ >50% cross-reference OR <8 entries      │ Log in commit
  SPLIT file   │ >80 entries OR two distinct clusters    │ Log in commit
  CREATE file  │ New domain emerges (>15 related symbols)│ Log in commit
  RENAME file  │ Domain name no longer reflects content  │ Log in commit

Agents must:
- Log actions with rationale in commit message
- Update index routing table after restructuring
- Verify invariants after restructuring

29. AUXILIARY MAINTENANCE

For auxiliary docs, agents should verify:
- Code examples run against current API (no deprecated calls)
- Links resolve (no broken references)
- Version references are current
- Frontmatter version matches project version

Trigger: After any API-breaking change, audit all auxiliary docs.

================================================================================
LAYER 7: VALIDATION
================================================================================

30. VALIDATION LEVELS

  LEVEL    │ CHECK                              │ SEVERITY  │ BLOCKING
  ─────────┼────────────────────────────────────┼───────────┼──────────
  L0       │ Frontmatter valid YAML             │ Critical  │ Yes
  L0       │ Frontmatter has required fields    │ Critical  │ Yes
  L1       │ Every entry has Signature section  │ Error     │ Yes
  L1       │ Every entry has Constraints section│ Error     │ Yes
  L2       │ Signatures match code              │ Error     │ Yes
  L2       │ No orphaned symbols (either dir)   │ Error     │ Yes
  L3       │ Contract uses "Y/N" not "Yes/No"   │ Warning   │ No
  L3       │ Descriptions are fragments         │ Warning   │ No
  L4       │ Routing metadata present           │ Info      │ No
  L4       │ Cross-references resolve           │ Info      │ No

Blocking validations must pass before commit.
Non-blocking validations should be addressed but don't prevent commits.

31. RECOVERY PROTOCOL

When validation fails:

  L0 FAILURE (frontmatter):
    → Fix frontmatter syntax
    → Ensure all required fields present
    → Re-validate

  L1 FAILURE (missing sections):
    → Add missing Signature and/or Constraints sections
    → Use minimal content if details unknown (flag for review)

  L2 FAILURE (drift/orphans):
    → Run synchronization loop (§27)
    → Address all ORPHAN-CODE and ORPHAN-DOC
    → Update all DRIFT entries

  L3/L4 WARNINGS:
    → Address in subsequent pass
    → Do not block progress on warnings

================================================================================
LAYER 8: WORKED EXAMPLES (FROM FTLLEXENGINE)
================================================================================

32. REFERENCE ENTRY EXAMPLE

From DOC_01_Core.md:

```markdown
## `FluentBundle.format_pattern`

### Signature
```python
def format_pattern(
    self,
    message_id: str,
    /,
    args: Mapping[str, FluentValue] | None = None,
    *,
    attribute: str | None = None,
) -> tuple[str, tuple[FluentError, ...]]:
```

### Contract
| Parameter | Type | Req | Semantics |
|:----------|:-----|:----|:----------|
| `message_id` | `str` | Y | Message identifier to format (positional-only) |
| `args` | `Mapping[str, FluentValue] \| None` | N | Variable values for placeholders |
| `attribute` | `str \| None` | N | Specific attribute to format |

### Constraints
- Return: Tuple of (formatted_string, errors). Never fails.
- Raises: Never. All errors collected in tuple.
- State: Read-only (may update internal cache).
- Thread: Safe for concurrent reads.

---
```

33. EXCEPTION HIERARCHY EXAMPLE

From DOC_05_Errors.md:

```markdown
## Exception Hierarchy

```
FluentError
├── FluentSyntaxError
├── FluentReferenceError
│   └── FluentCyclicReferenceError
├── FluentResolutionError
│   └── DepthLimitExceededError
└── FluentParseError
```

---

## `FluentReferenceError`

### Signature
```python
class FluentReferenceError(FluentError): ...
```

### Constraints
- Purpose: Unknown message or term reference during resolution.
- Recovery: Check message ID spelling; verify resource was loaded.
- Inherits: Full behavior from FluentError.

---
```

34. FRONTMATTER EXAMPLE

From DOC_00_Index.md:

```yaml
---
afad: "2.1"
version: "0.35.0"
tier: reference
domain: INDEX
updated: "2025-12-27T12:00:00Z"
author: "claude-opus-4-5"
route:
  keywords: [api reference, exports, imports, documentation, ftllexengine]
  questions: ["what classes are available?", "how do I import?", "where is X documented?"]
  downstream: [DOC_01_Core.md, DOC_02_Types.md, DOC_03_Parsing.md, DOC_04_Runtime.md, DOC_05_Errors.md]
---
```

================================================================================
END OF PROTOCOL
================================================================================

DESIGN NOTES

This protocol is structured in layers:
- Layer 0: Philosophy (the "why")
- Layer 1: Invariants (what must always be true)
- Layer 2: File architecture (how files are organized)
- Layer 3: Component schemas (how entries are structured)
- Layer 4: Auxiliary documentation (narrative docs)
- Layer 5: Adaptation (flexibility mechanisms)
- Layer 6: Maintenance (keeping docs in sync)
- Layer 7: Validation (verifying correctness)
- Layer 8: Examples (concrete illustrations)

Layers build on each other. An agent can read Layer 0-1 for philosophy,
add Layer 2-3 for reference docs, add Layer 4 for auxiliary docs.

VERSION HISTORY

2.1 (2025-12-27) - Second pass refinement
  - Added Layer 0 (Philosophy) with mental model, dual audience, retrieval optimization
  - Added priority hierarchy (P0 Critical → P2 Stylistic)
  - Restructured into explicit layers (0-8)
  - Added scale calibration for different project sizes
  - Added graceful degradation protocol
  - Enhanced frontmatter with upstream/downstream edges
  - Added worked examples from FTLLexEngine codebase
  - Added recovery protocol for validation failures
  - Improved schema selector decision tree

2.0 (2025-12-27) - First unified protocol
  - Unified AFAD and AFAD-AUX into single protocol
  - Replaced enumerated schemas with decision tree
  - Added escape hatches

1.x (2025-12) - Original split protocols
  - AFAD-v1.1: Reference documentation
  - AFAD-AUX-v1.1: Auxiliary documentation

SOURCES

- [Stack Overflow: Chunking in RAG](https://stackoverflow.blog/2024/12/27/breaking-up-is-hard-to-do-chunking-in-rag-applications/)
- [Model Context Protocol Architecture](https://modelcontextprotocol.io/specification/2025-03-26/architecture)
- [Knowledge Graphs in Technical Documentation](https://clickhelp.com/clickhelp-technical-writing-blog/how-knowledge-graphs-can-improve-documentation-creation/)
- [Unstructured: Chunking Best Practices](https://unstructured.io/blog/chunking-for-rag-best-practices)
- [W3C: Extensibility, Evolvability, Interoperability](https://www.w3.org/Protocols/Design/Interevol.html)
