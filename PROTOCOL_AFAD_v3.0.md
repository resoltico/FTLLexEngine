PROTOCOL: AGENT_FIRST_DOCUMENTATION
VERSION: 3.0
STATUS: Fourth Pass - Retrieval-Oriented Refinement

═══════════════════════════════════════════════════════════════════════════════
§1 RETRIEVAL-ORIENTED ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════════

This protocol optimizes documentation for retrieval-augmented generation (RAG).

CORE INSIGHT: Documentation is not read linearly. It is chunked, embedded, and
retrieved. Every design decision must answer: "Does this improve retrieval?"

Three retrieval properties govern all decisions:

    PROPERTY         MEANING                        OPTIMIZATION
    ─────────────────────────────────────────────────────────────
    CHUNKABILITY     Can be split at natural        256-512 tokens per entry
                     semantic boundaries            Single concept per entry

    EMBEDDABILITY    Semantic meaning captured      Keywords at entry start
                     in first 100 tokens            Avoid pronouns/references

    ROUTABILITY      Query → correct file/entry     Distinctive terminology
                     without full-text search       Frontmatter hints

RETRIEVAL COST MODEL:

    Cost = tokens_retrieved × calls × complexity

    Goal: Minimize tokens while maximizing answer accuracy.
    Trade-off: More entries = more precise retrieval but more calls.
    Sweet spot: 1-3 retrieved entries answer 80% of queries.

═══════════════════════════════════════════════════════════════════════════════
§2 ATOMIC DOCUMENTATION DESIGN
═══════════════════════════════════════════════════════════════════════════════

Documentation follows atomic design principles:

    LEVEL       DEFINITION                    EXAMPLE
    ─────────────────────────────────────────────────────────────
    ATOM        Single entry (one symbol)     `FluentBundle.format_pattern`
    MOLECULE    Related entries (one class)   All FluentBundle methods
    ORGANISM    Full file (one domain)        DOC_01_Core.md
    ECOSYSTEM   All files (full project)      docs/

ATOM RULES (§3-§8 schemas are atoms):
- One concept only
- Self-contained (no "see above")
- 200-400 tokens ideal (max 600)
- First sentence: what it IS (not what it does)
- Last section: version/deprecation

MOLECULE RULES:
- Group by class or logical cluster
- Shared intro paragraph allowed
- Cross-reference within molecule OK

ORGANISM RULES:
- One domain per file
- Critical entries at file start (first 30%)
- Routine entries in middle
- Edge cases at file end (last 20%)

This addresses "lost in the middle" phenomenon: LLMs process start and end of
context more reliably than middle.

═══════════════════════════════════════════════════════════════════════════════
§3 INVARIANTS
═══════════════════════════════════════════════════════════════════════════════

Four properties that must always hold:

    INV-1 COMPLETENESS   Every export has exactly one doc entry
    INV-2 ACCURACY       signature_doc == signature_code
    INV-3 FRESHNESS      frontmatter.version == project.version
    INV-4 ATOMICITY      Every entry ≤600 tokens

Detection signals:

    SIGNAL          CONDITION                    ACTION
    ─────────────────────────────────────────────────────────────
    ORPHAN-CODE     Export without entry         Create atom
    ORPHAN-DOC      Entry without export         Delete atom
    DRIFT           Signatures differ            Update + flag
    BLOAT           Entry >600 tokens            Split into atoms

═══════════════════════════════════════════════════════════════════════════════
§4 FILE ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════════

Two tiers, derived from filename pattern:

    PATTERN         TIER          CONTENT MODEL
    ─────────────────────────────────────────────────────────────
    DOC_*.md        reference     Schema-driven, no prose
    *.md            auxiliary     Narrative permitted

NOTE: v2.2 had explicit `tier` field in frontmatter. Removed in v3.0.
Tier is derivable from filename; explicit field was redundant.

Standard domains:

    FILE                DOMAIN      COVERAGE
    ─────────────────────────────────────────────────────────────
    DOC_00_Index.md     INDEX       Exports, routing, navigation
    DOC_01_Core.md      CORE        80% of queries (high-frequency API)
    DOC_02_Types.md     TYPES       Data structures, type aliases
    DOC_03_*.md         PRIMARY     Main domain (Parsing, IO)
    DOC_04_*.md         SECONDARY   Supporting domain (Runtime)
    DOC_05_Errors.md    ERRORS      Exception hierarchy

Restructuring heuristics (with justification):

    ACTION    TRIGGER                JUSTIFICATION
    ─────────────────────────────────────────────────────────────
    CREATE    >20 related exports    File exceeds retrieval sweet spot
    MERGE     <8 entries             File too small for dedicated embedding
    SPLIT     >60 entries            File exceeds context window efficiency

    Calibration: Adjust thresholds ±30% based on entry token density.
    Dense entries (400+ tokens) → lower thresholds.
    Sparse entries (<200 tokens) → higher thresholds.

═══════════════════════════════════════════════════════════════════════════════
§5 FRONTMATTER
═══════════════════════════════════════════════════════════════════════════════

Minimal required fields:

```yaml
---
afad: "3.0"
version: "X.Y.Z"
domain: CORE | TYPES | ERRORS | ...
updated: "YYYY-MM-DD"
route:
  keywords: [terms, that, find, this]
  questions: ["natural language query"]
---
```

Field semantics:

    FIELD       PURPOSE                     RETRIEVAL IMPACT
    ─────────────────────────────────────────────────────────────
    afad        Schema version              Agent selects parser
    version     Project version             Freshness check
    domain      Semantic cluster            File routing
    updated     Last modification           Staleness signal
    route       Retrieval hints             Query → file routing

REMOVED from v2.2:
- `tier`: Derived from filename (DOC_*.md = reference)
- `author`: Not used in retrieval; track in git
- Timestamps with timezone: ISO-8601 date sufficient

ROUTE OPTIMIZATION:
- `keywords`: 5-10 terms that should find this file
- `questions`: 2-5 natural language queries this answers
- Keywords should be distinctive (not generic like "function", "class")

═══════════════════════════════════════════════════════════════════════════════
§6 SCHEMA SELECTION
═══════════════════════════════════════════════════════════════════════════════

    Component type?
    │
    ├─ Callable (function/method/class) ──→ §7
    ├─ Property (@property) ──────────────→ §8
    ├─ Enum ──────────────────────────────→ §9
    ├─ Type alias ────────────────────────→ §10
    ├─ Constant ──────────────────────────→ §11
    └─ Exception ─────────────────────────→ §12

All schemas share:
- `## \`name\`` heading (backticks required)
- `### Signature` code block
- `### Constraints` semantic list
- `---` separator

═══════════════════════════════════════════════════════════════════════════════
§7 CALLABLE SCHEMA
═══════════════════════════════════════════════════════════════════════════════

For functions, methods, classmethods, staticmethods.

Template:

```
## `function_name`

Function/method that <does X>. ← EMBEDDABILITY: First line = what it IS

### Signature
```python
def function_name(required: Type, /, optional: Type = default) -> Return:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `required` | `Type` | Y | Fragment ≤10 words |

### Constraints
- Return: What; edge cases
- Raises: `Exception` when X | Never
- State: Mutates X | Read-only | Pure
- Thread: Safe | Unsafe

### Notes ← OPTIONAL: quirks, deprecation
- Version: Added v2.0 | Deprecated v3.0

---
```

COLUMN RULES:
- Name: Exact, in backticks
- Type: Full annotation, in backticks
- Req: "Y" or "N" only
- Semantics: Fragment, no articles, ≤10 words

ENTRY SIZING:
- Target: 250-350 tokens
- If >500 tokens: Consider splitting (separate class entry from methods)
- Omit *args/**kwargs unless semantically significant

═══════════════════════════════════════════════════════════════════════════════
§8 PROPERTY SCHEMA
═══════════════════════════════════════════════════════════════════════════════

```
## `Class.property_name`

Property representing <what>. ← First line states what it IS

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
Target: 80-150 tokens.

═══════════════════════════════════════════════════════════════════════════════
§9 ENUM SCHEMA
═══════════════════════════════════════════════════════════════════════════════

```
## `EnumName`

Enumeration of <what category>. ← First line states category

### Signature
```python
class EnumName(Enum):
    MEMBER_A = "value"
    MEMBER_B = "value"
```

### Members
| Member | Value | Semantics |
|:-------|:------|:----------|
| `MEMBER_A` | `"value"` | What this represents |

### Constraints
- Purpose: Why this enum exists
- Type: StrEnum | IntEnum | Enum

---
```

For IntEnums with code ranges, add `### Ranges` before Members.

═══════════════════════════════════════════════════════════════════════════════
§10 TYPE ALIAS SCHEMA
═══════════════════════════════════════════════════════════════════════════════

```
## `AliasName`

Type alias for <what category>. ← First line states what it represents

### Definition
```python
type AliasName = TypeA | TypeB
```

### Constraints
- Purpose: Why this alias exists
- Narrowing: Pattern match or .guard() (isinstance fails)

---
```

Group related aliases when they form a semantic family.
Target: 60-120 tokens per alias.

═══════════════════════════════════════════════════════════════════════════════
§11 CONSTANT SCHEMA
═══════════════════════════════════════════════════════════════════════════════

```
## `CONSTANT_NAME`

Constant defining <what>. ← First line states what it defines

### Definition
```python
CONSTANT_NAME: Type = value
```

### Constraints
- Purpose: Why this constant exists

---
```

Target: 40-80 tokens.

═══════════════════════════════════════════════════════════════════════════════
§12 EXCEPTION SCHEMA
═══════════════════════════════════════════════════════════════════════════════

Hierarchy tree (once per file):

```
## Exception Hierarchy

```
BaseError
├─ SyntaxError
│   └─ ParseError
└─ RuntimeError
```

---
```

Individual entries:

```
## `SpecificError`

Exception raised when <condition>. ← First line states trigger

### Signature
```python
class SpecificError(ParentError):
    field: Type
```

### Parameters ← Only if exception has fields
| Field | Type | Semantics |
|:------|:-----|:----------|
| `field` | `Type` | What this carries |

### Constraints
- Purpose: What error scenario
- Recovery: Suggested fix

---
```

For inherit-only exceptions, omit Parameters and use minimal form.

═══════════════════════════════════════════════════════════════════════════════
§13 QUERY PATTERNS
═══════════════════════════════════════════════════════════════════════════════

How agents should query this documentation:

    QUERY TYPE              PATTERN                      EXPECTED HIT
    ─────────────────────────────────────────────────────────────────────
    "What does X do?"       route.keywords + Signature   Single atom
    "How do I achieve Y?"   route.questions + Guide      Guide section
    "What type is X?"       Parameters table row         Cell value
    "What errors can X      Constraints → Raises         Exception atom
     raise?"
    "What changed in vN?"   Notes → Version              Atom + CHANGELOG

LAZY LOADING PROTOCOL:

Agents should NOT load all documentation upfront. Instead:

    1. Query index (DOC_00) for file routing
    2. Query specific file for entry routing
    3. Load specific entry
    4. If entry references other symbol, query that symbol

This mimics human cognition: look up what you need, not memorize everything.

HIERARCHICAL AGENT PATTERN:

For complex queries:
    1. Main agent identifies domain
    2. Sub-agent explores domain file with generous context
    3. Sub-agent returns concise answer
    4. Main agent continues with clean context

═══════════════════════════════════════════════════════════════════════════════
§14 ANTI-PATTERNS
═══════════════════════════════════════════════════════════════════════════════

    ANTI-PATTERN              WHY WRONG                   FIX
    ─────────────────────────────────────────────────────────────────────
    Prose in Parameters       Wastes tokens               Fragments only
    Duplicating docstrings    Double maintenance          Reference only
    Examples in reference     Bloats chunks               examples/ dir
    Sentence descriptions     Embedding noise             Keyword fragments
    "See above" references    Breaks atomicity            Self-contained
    >600 token entries        Retrieval degradation       Split atoms
    Generic keywords          Poor routing                Distinctive terms

═══════════════════════════════════════════════════════════════════════════════
§15 LIFECYCLE
═══════════════════════════════════════════════════════════════════════════════

DEPRECATION (3-phase, 2+ minor versions):

    PHASE          LOCATION                     CONTENT
    ─────────────────────────────────────────────────────────────────────
    ANNOUNCE       ### Notes                    Deprecated: Use X. Removal: vN+2
    (version N)

    WARNING        ### Constraints              Deprecated: vN. Migration: §link
    (version N+1)

    REMOVAL        Delete entry                 CHANGELOG: Removed section
    (version N+2)

DOCUMENTATION VERSIONING:

    CHANGE TYPE         AFAD VERSION    EXAMPLE
    ─────────────────────────────────────────────────────────────────────
    New optional field   Minor bump      afad: "3.1" adds Notes
    New required field   Major bump      afad: "4.0" adds required X
    Schema restructure   Major bump      afad: "4.0" renames Parameters
    Field removal        Major bump      afad: "4.0" removes tier

═══════════════════════════════════════════════════════════════════════════════
§16 MAINTENANCE
═══════════════════════════════════════════════════════════════════════════════

SYNC LOOP (on code change):

    1. INVENTORY: Parse exports → build symbol:signature map
    2. COMPARE: For each symbol, categorize: MATCH | DRIFT | ORPHAN
    3. RECONCILE:
       - MATCH → no action
       - DRIFT → update Signature, flag Parameters for review
       - ORPHAN-CODE → create atom
       - ORPHAN-DOC → delete atom
    4. FINALIZE: Update frontmatter, verify invariants, commit

AUTONOMOUS AUTHORITY:

Agents may restructure without permission:

    ACTION    TRIGGER           REQUIREMENT
    ─────────────────────────────────────────────────────────────────────
    DELETE    All atoms removed  Log in commit
    MERGE     <8 entries         Log in commit
    SPLIT     >60 entries        Log in commit
    CREATE    >15 new symbols    Log in commit

═══════════════════════════════════════════════════════════════════════════════
§17 VALIDATION
═══════════════════════════════════════════════════════════════════════════════

    LEVEL   CHECK                        BLOCKING
    ─────────────────────────────────────────────────────────────────────
    L0      Frontmatter valid YAML       Yes
    L0      Required fields present      Yes
    L1      Every entry has Signature    Yes
    L1      Every entry has Constraints  Yes
    L2      Signatures match code        Yes
    L2      No orphan symbols            Yes
    L2      Entries ≤600 tokens          Yes  ← NEW in v3.0
    L3      Parameters uses Y/N          No
    L3      Fragments ≤10 words          No

RECOVERY:

    FAILURE    RECOVERY
    ─────────────────────────────────────────────────────────────────────
    L0         Fix YAML, add fields
    L1         Add Signature/Constraints with minimal content
    L2         Run sync loop; split bloated entries
    L3         Fix in subsequent pass

═══════════════════════════════════════════════════════════════════════════════
§18 SCALE
═══════════════════════════════════════════════════════════════════════════════

    PROJECT SIZE    STRUCTURE                 NOTES
    ─────────────────────────────────────────────────────────────────────
    Small (<20)     DOC_00 + DOC_01 only      Domains collapsed
    Medium (20-80)  Standard (DOC_00-05)      One domain per file
    Large (>80)     + domain splits           Sub-indices considered
    Monorepo        Per-package docs/         Shared TERMINOLOGY.md

GRACEFUL DEGRADATION:

    PRIORITY   APPROACH
    ─────────────────────────────────────────────────────────────────────
    1st        Full schema
    2nd        Signature + simplified Parameters
    3rd        Signature + Notes
    4th        Placeholder with TODO

    NEVER      Leave export undocumented

═══════════════════════════════════════════════════════════════════════════════
§19 MULTI-LANGUAGE
═══════════════════════════════════════════════════════════════════════════════

This protocol is Python-centric but extensible:

    CONCEPT           PYTHON                JAVASCRIPT/TS        RUST
    ─────────────────────────────────────────────────────────────────────
    Exports           __all__/__init__      export statements     pub items
    Signature block   def name():           function name() {}    fn name()
    Type annotations  param: Type           param: type           param: Type
    Properties        @property             get accessor          impl block
    Exceptions        class XError          class XError          enum Error

When documenting polyglot projects:
- Use language-specific signature syntax in code blocks
- Maintain consistent schema structure across languages
- Note language in frontmatter: `language: typescript`

═══════════════════════════════════════════════════════════════════════════════
§20 AUXILIARY DOCUMENTATION
═══════════════════════════════════════════════════════════════════════════════

GUIDE STRUCTURE:

```markdown
---
afad: "3.0"
version: "X.Y.Z"
domain: <topic>
updated: "YYYY-MM-DD"
route:
  keywords: [topic keywords]
  questions: ["how do I X?"]
---

# <Topic> Guide

**Purpose**: What reader learns
**Prerequisites**: Required knowledge

## Overview

2-3 paragraphs of context.

## <Action Step>

Instruction.

```python
# Working code
```

## Summary

- Key point 1
- Key point 2
```

README EXCEPTION:

README.md is a storefront. Permitted: examples, marketing, badges.
Required: Installation, Quick Start, doc links.
Prohibited: Full API, exhaustive examples.

QUICK_REFERENCE:

Task-oriented, copy-paste, zero prose.
Every snippet runs independently.
Max 2 sentences per category.

═══════════════════════════════════════════════════════════════════════════════
§21 CONFLICT RESOLUTION
═══════════════════════════════════════════════════════════════════════════════

Priority hierarchy: P0 Accuracy > P1 Completeness > P2 Structure > P3 Style

COMMON CONFLICTS:

    CONFLICT                           RESOLUTION
    ─────────────────────────────────────────────────────────────────────
    Complex signature doesn't fit      Keep accurate signature (P0)
    standard table                     Add Notes explaining structure (P2)

    Entry exceeds 600 tokens           Split into atoms (P2 Atomicity)
    but splitting loses cohesion       unless accuracy suffers (P0 wins)

    Undocumented export but            Create placeholder (P1 Completeness)
    semantics unknown                  with TODO and minimal Constraints

    Style violation but                Fix style (P3) in subsequent pass
    content is accurate                Don't block on style

═══════════════════════════════════════════════════════════════════════════════
§22 WORKED EXAMPLE
═══════════════════════════════════════════════════════════════════════════════

From DOC_01_Core.md:

```markdown
## `FluentBundle.format_pattern`

Method that formats a Fluent message with optional arguments.

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
| `message_id` | `str` | Y | Message identifier |
| `args` | `Mapping[str, FluentValue] \| None` | N | Variable values |
| `attribute` | `str \| None` | N | Specific attribute to format |

### Constraints
- Return: (formatted_string, errors) tuple; never fails
- Raises: Never; errors collected in tuple
- State: Read-only (may update internal cache)
- Thread: Safe for concurrent reads

---
```

Token count: ~180 (within 200-400 target)
First line: States what method IS
Self-contained: No "see above" references

═══════════════════════════════════════════════════════════════════════════════
END OF PROTOCOL
═══════════════════════════════════════════════════════════════════════════════

VERSION HISTORY

3.0 (2025-12-27) - Fourth pass: Retrieval-oriented refinement
  - Added §1 Retrieval-Oriented Architecture (ROA) with cost model
  - Added §2 Atomic Documentation Design (atoms/molecules/organisms)
  - Added §13 Query Patterns with lazy loading protocol
  - Added §19 Multi-Language extension framework
  - Added §21 Conflict Resolution with concrete examples
  - Added token budget constraints (≤600 tokens per entry)
  - Added "lost in the middle" awareness (critical content at edges)
  - Removed redundant `tier` field (derived from filename)
  - Removed `author` field (track in git, not docs)
  - Justified heuristic thresholds with calibration guidance
  - Optimized entry sizing for RAG (256-512 token target)
  - Added embeddability rule: first line states what symbol IS

2.2 (2025-12-27) - Third pass
  - Renamed Contract → Parameters
  - Added anti-patterns, lifecycle management
  - Flattened structure

2.1 (2025-12-27) - Second pass
  - Added philosophy layer, priority hierarchy

2.0 (2025-12-27) - First unified protocol

SOURCES

- [Firecrawl: Chunking Strategies for RAG 2025](https://www.firecrawl.dev/blog/best-chunking-strategies-rag-2025)
- [LangCopilot: Document Chunking 70% Accuracy Boost](https://langcopilot.com/posts/2025-10-11-document-chunking-for-rag-practical-guide)
- [Weaviate: Chunking Strategies](https://weaviate.io/blog/chunking-strategies-for-rag)
- [GetMaxim: Context Window Management](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/)
- [Pinecone: Why Use Retrieval Instead of Larger Context](https://www.pinecone.io/blog/why-use-retrieval-instead-of-larger-context/)
- [Swimm: LLM Context Windows](https://swimm.io/learn/large-language-models/llm-context-windows-basics-examples-and-prompting-best-practices)
- [Microservices.io: API Composition Pattern](https://microservices.io/patterns/data/api-composition.html)
- [Microservice API Patterns](https://microservice-api-patterns.org/)
- [Daily.dev: API Versioning Best Practices](https://daily.dev/blog/api-versioning-strategies-best-practices-guide)
- [Postman: API Versioning](https://www.postman.com/api-platform/api-versioning/)
