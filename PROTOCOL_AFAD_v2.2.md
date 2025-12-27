PROTOCOL: AGENT_FIRST_DOCUMENTATION
VERSION: 2.2
STATUS: Third Pass - Deep Refinement

================================================================================
FOUNDATIONS
================================================================================

§1 PURPOSE

This protocol governs AI agents creating documentation for AI agents to consume.
Humans are secondary readers. Machines are primary readers.

The protocol answers three questions:
1. WHAT to document (exported symbols, not internal implementation)
2. WHERE to put it (reference files vs guides)
3. HOW to structure it (schemas that enable extraction)

§2 CORE MENTAL MODEL

Documentation is a **knowledge graph** serialized as Markdown files.

```
GRAPH STRUCTURE
─────────────────────────────────────────────────
Nodes     = Components (functions, classes, types)
Edges     = Relationships (imports, calls, extends)
Clusters  = Domains (files grouping related nodes)
Index     = Entry point connecting all clusters
```

This model explains:
- Why files should contain cohesive concepts (cluster coherence)
- Why cross-references matter (edge connectivity)
- Why orphaned docs are failures (unreachable nodes)
- Why the index is critical (graph entry point)

§3 DOCSTRINGS VS EXTERNAL DOCS

This protocol governs **external documentation only**.

```
DOCUMENTATION BOUNDARY
─────────────────────────────────────────────────
DOCSTRINGS (in code)        EXTERNAL DOCS (docs/)
─────────────────────────────────────────────────
One-line summary            Full signature
Implementation notes        Parameter semantics
Private method docs         Thread safety
"Why" comments              Constraint relationships
IDE tooltip content         RAG retrieval targets
─────────────────────────────────────────────────
```

Rule: Docstrings are for developers reading code.
      External docs are for agents/tools querying APIs.

Do not duplicate content. External docs reference code; code does not
embed external doc content.

§4 PRIORITY HIERARCHY

When rules conflict, higher priority wins.

```
P0  ACCURACY     Signatures match code exactly
P1  COMPLETENESS Every export has documentation
P2  STRUCTURE    Entries follow schema patterns
P3  STYLE        Fragments, Y/N notation, formatting
```

Example: Complex signature that can't fit standard table (P2 conflict)?
Preserve accuracy (P0) with Notes section explaining deviation.

================================================================================
INVARIANTS
================================================================================

§5 SYSTEM PROPERTIES

Four properties must always hold:

```
INV-1  COMPLETENESS
       ∀ symbol ∈ exports: ∃ exactly one doc entry
       Detection: Parse __init__.py → diff vs documented symbols

INV-2  ACCURACY
       ∀ entry: signature_doc == signature_code
       Detection: AST extraction → normalized string compare

INV-3  FRESHNESS
       frontmatter.version == pyproject.toml.version
       Detection: Compare version strings

INV-4  REACHABILITY
       ∀ doc file: ∃ path from DOC_00_Index.md
       Detection: Graph traversal from index
```

When any invariant is false, the system is broken.
Agents must restore invariants before adding new content.

§6 VIOLATION SIGNALS

How agents detect invariant violations:

```
SIGNAL              MEANING                      ACTION
───────────────────────────────────────────────────────────────
ORPHAN-CODE         Export without doc entry     Create entry
ORPHAN-DOC          Doc entry without export     Remove entry
DRIFT-SIGNATURE     Signatures don't match       Update Signature
DRIFT-VERSION       Version mismatch             Update frontmatter
ISLAND-FILE         File unreachable from index  Add to index
```

================================================================================
FILE STRUCTURE
================================================================================

§7 TWO-TIER ARCHITECTURE

```
docs/
├── DOC_00_Index.md      ┐
├── DOC_01_Core.md       │ REFERENCE TIER
├── DOC_02_Types.md      │ Schema-driven, no prose
├── DOC_03_<Domain>.md   │ Agent-optimized
├── DOC_05_Errors.md     ┘
│
├── QUICK_REFERENCE.md   ┐
├── *_GUIDE.md           │ AUXILIARY TIER
├── TERMINOLOGY.md       │ Narrative allowed
└── MIGRATION.md         ┘ Human-accommodating
```

REFERENCE files: Strict schema. No prose. No examples.
AUXILIARY files: Flexible structure. Examples permitted.

§8 FRONTMATTER

All files require YAML frontmatter:

```yaml
---
afad: "2.2"                      # Protocol version
version: "X.Y.Z"                 # Project version
tier: reference | auxiliary      # Which tier
domain: CORE | TYPES | ...       # Semantic cluster
updated: "YYYY-MM-DDTHH:MM:SSZ"  # Last modified
author: <agent_id>               # Last author

# RAG routing hints
route:
  keywords: [terms, for, search]
  questions: ["natural language queries this answers"]
---
```

Note: v2.1 had `upstream`/`downstream` fields. Removed in v2.2.
Cross-references are edges but should be derived from content, not
manually maintained in frontmatter (prone to drift).

§9 DOMAIN ORGANIZATION

Standard domains:

```
DOMAIN    FILE                CONTENTS
───────────────────────────────────────────────────────────────
INDEX     DOC_00_Index.md     Exports, routing table, navigation
CORE      DOC_01_Core.md      Primary public API (80% of queries)
TYPES     DOC_02_Types.md     Data structures, AST, type aliases
<DOMAIN>  DOC_03_<Name>.md    Primary domain (Parsing, IO, etc.)
<DOMAIN>  DOC_04_<Name>.md    Secondary domain (Runtime, etc.)
ERRORS    DOC_05_Errors.md    Exception hierarchy, diagnostics
TESTING   DOC_06_Testing.md   Test infrastructure (optional)
```

Heuristics for restructuring:

```
CREATE new domain:  >25 symbols that cluster conceptually
MERGE domains:      <10 entries OR >50% cross-reference density
SPLIT domain:       >80 entries OR two distinct sub-clusters
```

================================================================================
SCHEMAS
================================================================================

§10 SCHEMA SELECTION

```
                    ┌─────────────────────┐
                    │  What type of       │
                    │  component?         │
                    └──────────┬──────────┘
                               │
    ┌──────────┬───────────┬───┴───┬───────────┬──────────┐
    ▼          ▼           ▼       ▼           ▼          ▼
 Callable   Property    Enum    Type       Constant  Exception
    │          │          │     Alias         │          │
    ▼          ▼          ▼       ▼           ▼          ▼
  §11        §12        §13     §14         §15        §16
```

All schemas share:
- `## \`name\`` heading (backticks, exact symbol name)
- `### Signature` block (full typed signature)
- `### Constraints` block (semantics, behavior)
- `---` separator after entry

§11 CALLABLE SCHEMA

For functions, methods, classmethods, staticmethods.

```
## `function_name`

### Signature
```python
def function_name(
    required: Type,
    /,
    optional: Type = default,
    *,
    keyword_only: Type = default,
) -> ReturnType:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `required` | `Type` | Y | What this represents (≤10 words) |
| `optional` | `Type` | N | What this represents |

### Constraints
- Return: What is returned; edge cases
- Raises: `Exception` when condition | Never
- State: Mutates X | Read-only | Pure
- Thread: Safe | Unsafe | Safe for reads

### Notes  ← OPTIONAL
- Historical: Pre-v2.0 behavior was X
- Performance: O(n²) for large inputs
- Deprecated: Use Y instead (v3.0+)

---
```

**RENAMED**: "Contract" → "Parameters" (clearer terminology)

Column semantics:
- Name: Exact parameter name in backticks
- Type: Full type annotation in backticks
- Req: "Y" or "N" only (never "Yes"/"No")
- Semantics: Fragment (no articles, no "The X parameter")

§12 PROPERTY SCHEMA

```
## `Class.property_name`

### Signature
```python
@property
def property_name(self) -> Type:
```

### Constraints
- Return: What the property represents
- State: Read-only | Computed | Cached

---
```

No Parameters table (properties take no arguments).

§13 ENUM SCHEMA

```
## `EnumName`

### Signature
```python
class EnumName(Enum):
    MEMBER_A = "value_a"
    MEMBER_B = "value_b"
```

### Members
| Member | Value | Semantics |
|:-------|:------|:----------|
| `MEMBER_A` | `"value_a"` | What this member represents |

### Constraints
- Purpose: Why this enum exists
- String: Members are strings (StrEnum) | Members are ints (IntEnum)

---
```

For IntEnums with semantic code ranges, add before Members:

```
### Ranges
| Range | Category | Purpose |
|:------|:---------|:--------|
| 1000-1999 | Syntax | Parsing errors |
```

§14 TYPE ALIAS SCHEMA

```
## `AliasName`

### Definition
```python
type AliasName = TypeA | TypeB | TypeC
```

### Constraints
- Purpose: What this type represents
- Narrowing: Pattern matching or .guard() (isinstance fails)

---
```

Group related aliases in single entry when they form a family.

§15 CONSTANT SCHEMA

```
## `CONSTANT_NAME`

### Definition
```python
CONSTANT_NAME: Type = value
```

### Constraints
- Purpose: Why this constant exists
- Location: `module.path` (if not in main exports)

---
```

§16 EXCEPTION SCHEMA

Document hierarchy once per file:

```
## Exception Hierarchy

```
BaseError
├── SyntaxError
│   └── ParseError
└── RuntimeError
    └── ResolutionError
```

---
```

Then individual entries:

```
## `SpecificError`

### Signature
```python
class SpecificError(ParentError):
    field: Type
```

### Parameters
| Field | Type | Semantics |
|:------|:-----|:----------|
| `field` | `Type` | What this carries |

### Constraints
- Purpose: What error scenario
- Recovery: Suggested fix

---
```

For inherit-only exceptions:

```
## `SpecificError`

### Signature
```python
class SpecificError(ParentError): ...
```

### Constraints
- Purpose: Specialized error case
- Inherits: Full behavior from ParentError

---
```

================================================================================
ANTI-PATTERNS
================================================================================

§17 WHAT NOT TO DO

```
ANTI-PATTERN                  WHY IT'S WRONG                FIX
─────────────────────────────────────────────────────────────────────────────
Prose in Parameters           Wastes tokens, hard to parse  Use fragments
  "The message_id parameter
   specifies the identifier"  →  "Message identifier"

Duplicating docstrings        Double maintenance burden     Reference only
  Copy-pasting docstring
   into external docs         →  External = structured view

Examples in reference docs    Bloats retrieval chunks       examples/ directory
  Usage examples in DOC_*     →  Link to examples/

Sentence descriptions         Embedding noise               Keyword fragments
  "Returns a boolean that
   indicates whether..."      →  "True if exists"

Manual cross-references       Will drift                    Derive from content
  Maintaining link lists      →  Let tools compute edges

Version in prose              Hard to parse                 Constraints field
  "Added in version 2.0"      →  Version: Added v2.0

Exhaustive parameter lists    Overloads reference          Focus on semantics
  Repeating type info from
   signature in prose         →  Types in Signature only
─────────────────────────────────────────────────────────────────────────────
```

§18 COMMON MISTAKES BY DOMAIN

```
DOMAIN     COMMON MISTAKE                    CORRECT APPROACH
─────────────────────────────────────────────────────────────────────────────
CORE       Documenting private methods       Only document exports
TYPES      Missing type narrowing info       Include Narrowing constraint
ERRORS     Flat exception list               Hierarchy tree + individual
TESTING    Documenting test cases            Document infrastructure only
INDEX      Stale routing table               Update on every file change
─────────────────────────────────────────────────────────────────────────────
```

================================================================================
LIFECYCLE
================================================================================

§19 DEPRECATION PROTOCOL

When deprecating a component:

```
PHASE 1: ANNOUNCE (version N)
──────────────────────────────────────
### Notes
- Deprecated: Use `NewThing` instead. Will be removed in vN+2.

PHASE 2: WARNING (version N+1)
──────────────────────────────────────
### Constraints
- Deprecated: v{N}. Removal: v{N+2}. Migration: See MIGRATION.md#thing

PHASE 3: REMOVAL (version N+2)
──────────────────────────────────────
- Remove documentation entry
- Add to CHANGELOG.md under "Removed"
- Update MIGRATION.md with final migration path
```

Timeline: Minimum 2 minor versions between deprecation and removal.

§20 DOCUMENTATION VERSIONING

When protocol changes:

```
CHANGE TYPE              ACTION                        EXAMPLE
─────────────────────────────────────────────────────────────────────────────
New optional field       Add to schema, document       Notes section
New required field       Major version bump            afad: "3.0"
Schema restructure       Major version bump            Parameters renamed
Field removal            Major version bump            upstream/downstream
─────────────────────────────────────────────────────────────────────────────
```

The `afad` field in frontmatter enables schema evolution.
Agents should check `afad` version and apply appropriate schema.

================================================================================
MAINTENANCE
================================================================================

§21 SYNCHRONIZATION LOOP

```
TRIGGER: Code change (export added, signature changed, export removed)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. INVENTORY                                                             │
│    Parse entry point → extract exports with signatures                   │
│    Build: symbol → (signature, domain) mapping                           │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. COMPARE                                                               │
│    For each symbol: locate doc entry, extract signature                  │
│    Categorize: MATCH | DRIFT | ORPHAN-CODE | ORPHAN-DOC                  │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. RECONCILE                                                             │
│    MATCH      → no action                                                │
│    DRIFT      → update Signature, review Parameters                      │
│    ORPHAN-CODE → create entry (§10 schema selection)                     │
│    ORPHAN-DOC  → remove entry                                            │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. FINALIZE                                                              │
│    Update frontmatter (version, updated, author)                         │
│    Verify invariants (§5)                                                │
│    Commit if all pass                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

§22 AUTONOMOUS AUTHORITY

Agents may restructure without explicit permission:

```
ACTION      TRIGGER                           REQUIREMENT
─────────────────────────────────────────────────────────────────────────────
DELETE      All entries removed               Log in commit message
MERGE       <8 entries OR >50% overlap        Log in commit message
SPLIT       >80 entries OR distinct clusters  Log in commit message
CREATE      >15 new related symbols           Log in commit message
RENAME      Domain name is misleading         Log in commit message
─────────────────────────────────────────────────────────────────────────────
```

After restructuring:
1. Update index routing table
2. Verify all invariants
3. Log rationale in commit

================================================================================
VALIDATION
================================================================================

§23 VALIDATION LEVELS

```
LEVEL  CHECK                           SEVERITY   BLOCKING
─────────────────────────────────────────────────────────────────────────────
L0     Frontmatter valid YAML          Critical   Yes
L0     Required frontmatter fields     Critical   Yes
L1     Every entry has Signature       Error      Yes
L1     Every entry has Constraints     Error      Yes
L2     Signatures match code           Error      Yes
L2     No orphaned symbols             Error      Yes
L3     Parameters uses Y/N             Warning    No
L3     Semantics are fragments         Warning    No
L4     Route metadata present          Info       No
─────────────────────────────────────────────────────────────────────────────
```

L0-L2: Must pass before commit.
L3-L4: Should be addressed; don't block.

§24 RECOVERY

```
FAILURE    RECOVERY
─────────────────────────────────────────────────────────────────────────────
L0         Fix YAML syntax; add missing frontmatter fields
L1         Add missing Signature/Constraints; use minimal content if unknown
L2         Run sync loop (§21); address all ORPHAN and DRIFT
L3/L4      Address in subsequent pass; don't block on warnings
─────────────────────────────────────────────────────────────────────────────
```

§25 TESTING DOCUMENTATION

Beyond signature matching, verify:

```
CHECK                         METHOD
─────────────────────────────────────────────────────────────────────────────
Code examples run             Execute code blocks in QUICK_REFERENCE, guides
Links resolve                 Crawl all [text](link) patterns
Imports valid                 Extract imports from examples, verify symbols
No deprecated usage           Cross-ref examples with CHANGELOG Removed
Frontmatter current           Compare version to pyproject.toml
─────────────────────────────────────────────────────────────────────────────
```

================================================================================
SCALE ADAPTATION
================================================================================

§26 MINIMUM VIABLE DOCUMENTATION

For small projects (<20 exports), minimum required:

```
docs/
├── DOC_00_Index.md      # Exports list, simple routing
└── DOC_01_Core.md       # All components in one file
```

May omit:
- Separate Types/Errors/Testing files
- Complex routing tables
- Detailed route metadata

§27 SCALE CALIBRATION

```
PROJECT SIZE     RECOMMENDED STRUCTURE
─────────────────────────────────────────────────────────────────────────────
Small (<20)      DOC_00 + DOC_01 only; domains collapsed
Medium (20-100)  Standard structure (DOC_00 through DOC_05)
Large (>100)     Additional domain splits; consider sub-indices
Monorepo         Per-package docs/ with shared TERMINOLOGY.md
─────────────────────────────────────────────────────────────────────────────
```

§28 GRACEFUL DEGRADATION

When full compliance isn't achievable:

```
PRIORITY   APPROACH
─────────────────────────────────────────────────────────────────────────────
1st        Full schema compliance
2nd        Signature + simplified Parameters (fewer columns)
3rd        Signature + Notes explaining limitations
4th        Placeholder with TODO marker

NEVER      Leave exported symbol undocumented
─────────────────────────────────────────────────────────────────────────────
```

================================================================================
AUXILIARY DOCUMENTATION
================================================================================

§29 GUIDE STRUCTURE

```markdown
---
afad: "2.2"
version: "X.Y.Z"
tier: auxiliary
domain: <topic>
updated: "YYYY-MM-DDTHH:MM:SSZ"
author: agent_id
route:
  keywords: [topic keywords]
  questions: ["how do I X?"]
---

# <Topic> Guide

**Purpose**: What reader will learn
**Prerequisites**: Required knowledge

## Overview

Brief context (2-3 paragraphs)

## <Action Step 1>

Instruction

```python
# Working code
```

## Summary

- Key point 1
- Key point 2

## See Also

- [Related](link): relationship
```

§30 README EXCEPTION

README.md is a storefront. Sells the project.

**Permitted** (exceptions to normal rules):
- Code examples showing value proposition
- Marketing language
- Comparison tables
- Badges

**Required**:
- Installation
- Quick Start (working code)
- Documentation links

**Prohibited**:
- Full API reference
- Exhaustive examples
- Troubleshooting details

Goal: Reader tries project within 60 seconds.

§31 QUICK_REFERENCE

Task-oriented, copy-paste, zero prose:

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

Maximum 2 sentences per category.
Every snippet must run independently.

================================================================================
WORKED EXAMPLE
================================================================================

§32 COMPLETE ENTRY EXAMPLE

From DOC_01_Core.md (FTLLexEngine):

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

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `message_id` | `str` | Y | Message identifier (positional-only) |
| `args` | `Mapping[str, FluentValue] \| None` | N | Variable values |
| `attribute` | `str \| None` | N | Specific attribute to format |

### Constraints
- Return: (formatted_string, errors) tuple. Never fails.
- Raises: Never. Errors collected in tuple.
- State: Read-only (may update cache).
- Thread: Safe for concurrent reads.

---
```

================================================================================
END OF PROTOCOL
================================================================================

VERSION HISTORY

2.2 (2025-12-27) - Third pass refinement
  - Renamed "Contract" → "Parameters" (clearer terminology)
  - Removed upstream/downstream from frontmatter (drift-prone)
  - Added §17-18 Anti-Patterns section
  - Added §19-20 Lifecycle Management (deprecation, versioning)
  - Added §3 Docstrings vs External Docs boundary
  - Added §25 Testing Documentation verification
  - Added §26 Minimum Viable Documentation
  - Flattened structure (removed layer numbering)
  - More economical expression throughout

2.1 (2025-12-27) - Second pass refinement
  - Added philosophy layer (mental model, dual audience)
  - Added priority hierarchy
  - Added scale calibration, graceful degradation
  - Added worked examples

2.0 (2025-12-27) - First unified protocol
  - Unified AFAD and AFAD-AUX
  - Decision tree for schema selection

1.x (2025-12) - Original split protocols

SOURCES

- [Stack Overflow: Chunking in RAG](https://stackoverflow.blog/2024/12/27/breaking-up-is-hard-to-do-chunking-in-rag-applications/)
- [Real Python: Documenting Python Code](https://realpython.com/documenting-python-code/)
- [Hitchhiker's Guide: Documentation](https://docs.python-guide.org/writing/documentation/)
- [Apidog: API Versioning & Deprecation](https://apidog.com/blog/api-versioning-deprecation-strategy/)
- [SendGrid: 4 Common Documentation Antipatterns](https://sendgrid.com/blog/4-common-antipatterns-avoid-documentation/)
- [MCP Architecture](https://modelcontextprotocol.io/specification/2025-03-26/architecture)
