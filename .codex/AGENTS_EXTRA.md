# Critical

1. Always load and use the .codex/AGENTS_EXTRA.md, if it exists, when working on the project. AGENTS_EXTRA.md contains specialized project-tailored information.
2. Before starting actual work on documentation, but not earlier than that, load the .codex/PROTOCOL_AFAD.md, and use it for all your work on the documentation.

---

# 1. ARCHITECTURAL PRIME DIRECTIVE

## 1.1 Library Identity

FTLLexEngine is the Python runtime for the **Fluent Template Language specification**, with
**CLDR-backed locale-aware formatting** and **fail-fast boot validation with structured audit evidence**. Every
public symbol must arise from one of these three purposes. The library is not a general
utilities collection, not a financial domain toolkit, not a concurrency framework — it is
the i18n layer that production systems build directly on top of, and nothing else.

The primary use case is production systems where every locale resource must load cleanly,
every message schema must match exactly, and every failure must produce named, traceable
evidence — regulated deployments, audited backends, compliance-constrained services. This
purpose drives every API design decision.

**Three Design Axioms:**

**Axiom 1 — Downstream Burden Elimination:**
Before adding any symbol to a public facade, ask: *what downstream composition does this
replace?* Every public surface must eliminate a pattern that serious callers would otherwise
implement themselves. `require_locale_code()` replaced per-caller trim/blank/length/normalize
chains. `LocalizationBootConfig` replaced per-caller boot sequence assembly. `make_fluent_number()`
replaced per-caller visible-precision inference. Primitives that serve only internal composition
belong in submodules, not in `ftllexengine`, `ftllexengine.runtime`, or
`ftllexengine.localization`.

**Axiom 2 — Fail-Fast at Boot, Structured Evidence at Runtime:**
Validate everything before accepting traffic. The canonical boot chain —
`LocalizationBootConfig.boot()`, or `FluentLocalization` + `require_clean()` +
`validate_message_schemas()` — raises `IntegrityCheckFailedError` if any resource fails to
load cleanly or any schema mismatches. At runtime, errors are returned as immutable structured
evidence (`FrozenFluentError`, `WriteLogEntry`, `LoadSummary`) so callers can build auditable,
loggable, compliant systems on top. Silent degradation is prohibited; all failures are explicit.

**Axiom 3 — Explicit Failures, Immutable Evidence:**
Every failure produces a named, typed, immutable error object with structured context.
`strict=True` is the default on `FluentBundle` and `FluentLocalization` — exceptions, not
silent empty strings, are the correct response to integrity failures. `strict=False` is an
explicit opt-in for soft-error return semantics where `format_pattern` returns a
`(result, errors)` tuple. Audit structures (`WriteLogEntry`, `IntegrityContext`) carry dual
timestamps (`timestamp` for monotonic ordering, `wall_time_unix` for cross-system correlation)
because compliance traces must be reproducible across restarts.

**API Design Review — apply before any new public surface:**
1. What downstream composition does this replace? (Axiom 1)
2. Does construction fail fast? Does runtime return immutable structured evidence? (Axiom 2)
3. Does it belong in a facade `__init__`, or is it an internal primitive? (see §1.5)
4. Does it introduce any upward layer dependency? (see §1.5)
5. Does it fall within one of the owned domains in §1.6 — FTL spec, CLDR locale
   formatting, compliance boot/audit, ISO 4217, or ISO 3166? Apply the full rejection
   test (§1.6) before answering yes.

## 1.2 Runtime Environment Constraints (Python 3.13+)
**Constraint:** The solution space targets **Python 3.13** as the baseline, targeting forward
compatibility with the current and next CPython release by avoiding constructs documented as
deprecated or removed.
* **Version Support Policy:** Support the baseline release and forward. Current values (update
  when a new CPython stable release occurs): baseline=3.13, current=3.14, next=3.15.
* **Forward Compatibility:** Use only stable language features. Avoid deprecated constructs and
  CPython-specific internals that may change between releases.
* **Syntax Enforcement System:**
    * **Type Topology:** Leverage **PEP 695** generics and `type` aliases as the foundational
      data modeling layer (e.g., `class Buffer[T]: ...`). Type hints are not documentation;
      they are structural contracts.
    * **Control Flow:** Utilize `match/case` structural pattern matching as the primary dispatch
      mechanism, reducing the cyclomatic complexity inherent in `if/elif` chains.
* **Dependency Isolation:** The **Python Standard Library** is the sole permitted toolkit, with
  the below stated explicit permitted exception. External dependencies are treated as system
  contaminants and are prohibited unless creating the solution within the Standard Library
  bounds is not achievable.
    * **Permitted Exception:** `Babel` is the sole external dependency (optional), providing
      Unicode CLDR locale data (plural rules, currency symbols, number formatting). CLDR data
      is a curated international standard dataset that cannot be derived algorithmically. Babel
      is the canonical Python interface to CLDR.
    * **Babel Optionality:** Babel is an **optional** dependency. The package supports two
      installation modes:
        * **Parser-only** (`pip install ftllexengine`): No external dependencies. Provides
          syntax parsing (`parse_ftl`, `serialize_ftl`), AST manipulation, and validation.
        * **Full runtime** (`pip install ftllexengine[babel]`): Includes Babel for locale-aware
          formatting via `FluentBundle`, `FluentLocalization`, and `ftllexengine.parsing`
          modules.
* **Obsolescence Filter:** The system strictly rejects features scheduled for removal.
    * Legacy import mechanics (`imp`, `sys.path`) and pre-PEP 695 typing (e.g., `typing.List`)
      are structurally invalid inputs.

## 1.3 Structural Mechanics
* **Immutability Protocol:** State mutation creates hidden coupling and non-determinism. The
  system defaults to **Immutable Data Structures** (`frozen=True` dataclasses, `tuples`) to
  enforce referential transparency. Mutation is permitted in exactly two bounded cases:
    1. **Performance-critical accumulation buffers:** isolated parse-buffer components where
       temporary accumulation is the direct implementation mechanism (e.g., parser's internal
       character/token accumulation).
    2. **Scoped context managers:** classes implementing the `__enter__`/`__exit__` protocol
       where tracked mutable state (e.g., a depth counter) has deterministic enter/exit
       lifetime and no external visibility (e.g., `DepthGuard`).
* **Explicit Control Topology:** Implicit behavior and "magic" methods increase cognitive load
  and reduce auditability. The system demands explicit control flow and dependency injection
  over global state or `threading.local` thread-local storage. **ContextVars
  (`contextvars.ContextVar`) are permitted** for task-scoped state in high-frequency primitive
  operations — they provide automatic async task isolation and do not share state between
  concurrent parse operations. Any `ContextVar` usage MUST be documented as an architectural
  decision per §3.6 and included in the Known Waiver Registry (§3.7).
* **Constants Placement Policy:** The `constants.py` module is for **cross-package
  configuration constants** (depth limits, cache sizes, input bounds). Module-local private
  constants (leading underscore) that are semantic to a single module's functionality belong IN
  that module, not in `constants.py`. Examples: Unicode escape lengths in parser primitives,
  indentation strings in serializer, cache tuning parameters in cache implementation. This
  follows the principle of locality — implementation details stay with their implementation.

## 1.4 Specification Authority (Fluent)
**Constraint:** The Fluent specification is the authoritative reference for runtime behavior.

**Specification Sources:**
* Primary: [Project Fluent Guide](https://projectfluent.org/fluent/guide/)
* Syntax: [Fluent Syntax 1.0](https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf)
* Validation: [valid.md](https://github.com/projectfluent/fluent/blob/master/spec/valid.md)
* Reference implementation: [Mozilla python-fluent](https://github.com/projectfluent/python-fluent)

**Specification Primacy:**

When AI agents or developers assume behavior that differs from the specification, the
specification wins. Common misunderstandings:

| Assumption | Specification Reality |
|:-----------|:---------------------|
| `{ $count }` should format locale-aware | Variables are formatted as-is via `str()` |
| `NUMBER($count)` is optional for numbers | `NUMBER()` is REQUIRED for locale-aware formatting |
| Implicit date formatting exists | `DATETIME()` is REQUIRED for locale-aware dates |
| Messages and terms share a namespace | Separate namespaces: `foo` and `-foo` can coexist |
| `NUMBER(style: "currency")` for currency | Use `CURRENCY()` function, not NUMBER with style |
| `NUMBER(style: "percent")` for percent | No percent style; use `NUMBER()` with manual `%` |

**Example: Locale-Aware Number Formatting**

```python
# Input: count = 1000, locale = "de_DE"

# Fluent message: { $count }
# Output: "1000" (NOT "1.000")
# Reason: Per spec, variables are interpolated as-is

# Fluent message: { NUMBER($count) }
# Output: "1.000" (locale-aware)
# Reason: NUMBER() explicitly requests locale formatting
```

This is SPEC-COMPLIANT behavior, not a bug. The Fluent specification intentionally separates:
* Raw interpolation: `{ $var }` — developer controls formatting
* Locale-aware formatting: `{ NUMBER($var) }`, `{ DATETIME($var) }` — locale determines format

**JavaScript Intl API Conflation (Common Agent Error):**

Agents familiar with JavaScript's `Intl.NumberFormat` API frequently assume FTLLexEngine uses
the same patterns. This is incorrect.

| JavaScript Intl Pattern | FTLLexEngine Equivalent |
|:------------------------|:-----------------------|
| `Intl.NumberFormat(locale, {style: 'currency', currency: 'EUR'})` | `CURRENCY($val, currency: "EUR")` |
| `Intl.NumberFormat(locale, {style: 'percent'})` | Not supported; use `NUMBER()` + literal `%` |
| `Intl.NumberFormat(locale, {style: 'decimal'})` | `NUMBER($val)` (default behavior) |
| `Intl.DateTimeFormat(locale, {year: 'numeric', month: 'long'})` | `DATETIME($val, dateStyle: "long")` |

**Root Cause:** JavaScript's `Intl` API uses a single constructor with `style` parameter to
switch modes. Fluent/FTLLexEngine uses **separate functions** for each formatting type. The FTL
parser accepts any named arguments (it's syntax-agnostic), so `NUMBER($x, style: "currency")`
parses successfully but the `style` argument is ignored at runtime.

**Agent Responsibility:** Before flagging runtime behavior as incorrect:
1. Verify behavior against Fluent specification
2. Check Mozilla python-fluent reference implementation
3. If behavior matches spec: NOT a bug, even if counterintuitive
4. If behavior differs from spec: VALID issue; proceed with filing
5. Never assume JavaScript API patterns apply; verify function signatures against
   DOC_04_Runtime.md

## 1.5 Layer Architecture and Facade Contract

### 1.5.1 Layer Graph (Architectural Law)

The package layer hierarchy is a hard structural invariant, not a style convention:

```
core ← syntax ← parsing ← runtime ← localization
         ↑                    ↑
    introspection          analysis
         ↑
    diagnostics ← validation
```

| Layer | Contents | May import from |
|:------|:---------|:----------------|
| `core` | Depth guards, Babel compat, locale utils, value types | stdlib only |
| `diagnostics` | Error types, validation results, formatter | `core` |
| `validation` | Resource validation | `core`, `syntax`, `diagnostics` |
| `syntax` | AST, parser, serializer, validator | `core`, `diagnostics` |
| `introspection` | Message introspection, ISO lookup (Babel) | `core`, `syntax` |
| `analysis` | Cycle detection, dependency graph | `core`, `syntax` |
| `parsing` | Locale-aware parsers (Babel required) | `core`, `syntax` |
| `runtime` | FluentBundle, resolver, cache, functions | `core`, `syntax`, `introspection`, `analysis`, `diagnostics` |
| `localization` | FluentLocalization, boot, loaders | `runtime` and all below |

**Upward dependencies are structural violations, not style issues.** A module in layer N may
not import from layer M > N. Violations must be fixed by moving the symbol to the correct
layer, not by using a runtime local import to paper over the problem.

**Detection pattern:** When layer N needs a symbol from layer M > N, ask: "Does this symbol
conceptually belong in layer ≤ N?" If yes, move the symbol. The 0.154.0 `FluentNumber`
relocation (`runtime.value_types` → `core.value_types`) is the canonical example — it was a
violation because `parsing` needed `FluentNumber` to implement `parse_fluent_number()`, but
`parsing` cannot import from `runtime`.

### 1.5.2 Public Facade Contract

The three public facades are permanent API contracts. A symbol on a facade cannot be removed
or renamed without a CHANGELOG.md `### Breaking Changes` entry.

| Facade | Import path | Scope |
|:-------|:------------|:------|
| Root | `ftllexengine` | All end-user entry points |
| Runtime | `ftllexengine.runtime` | FluentBundle, AsyncFluentBundle, FluentNumber, FunctionRegistry |
| Localization | `ftllexengine.localization` | FluentLocalization, LocalizationBootConfig, loader types |

**Submodule paths** (`ftllexengine.runtime.bundle`, `ftllexengine.core.value_types`) are
internal navigation paths, not contracted surfaces. They may be reorganized without breaking
the public contract provided facade re-exports are maintained.

**Export hygiene:** Every symbol in a facade `__init__.py` must have an explicit `__all__`
entry. Implicit reachability via attribute traversal does not constitute a public contract.

**Prohibited facade additions:** Symbols that exist only to expose implementation details
(internal cache structures, private lock primitives, parser internals) must not be promoted
to a facade even if callers request it. The facade is a curated surface, not a namespace dump.

## 1.6 Public Surface Scope Constraint

**Constraint:** FTLLexEngine is the Python runtime for the Fluent Template Language
specification, with CLDR-backed locale-aware formatting and fail-fast boot validation
with structured audit evidence. Its public surface is bounded by three owned domains plus two narrowly-named
standards datasets. Symbols outside these domains do not belong on any public facade,
regardless of technical merit or caller convenience.

**The Owned Domains (exhaustive — not a representative sample):**

| Domain | Bounded by | Examples of in-scope symbols |
|:-------|:-----------|:-----------------------------|
| **FTL specification** | The Fluent 1.0 EBNF and valid.md | parse_ftl, serialize_ftl, validate_resource, AST nodes, FTL built-in functions |
| **CLDR-backed locale formatting** | Babel + Unicode CLDR | FluentBundle, FluentNumber, LocaleCode, normalize_locale, CLDR lookups |
| **Compliance-grade boot and audit** | The FTL/locale pipeline only | LocalizationBootConfig, IntegrityContext, LoadSummary, integrity exceptions arising from FTL resource loading |
| **ISO 4217 currency data** | The ISO 4217 standard as exposed by Babel/CLDR | CurrencyCode, is_valid_currency_code, get_currency_decimal_digits |
| **ISO 3166 territory data** | The ISO 3166-1 alpha-2 standard as exposed by Babel/CLDR | TerritoryCode, is_valid_territory_code, require_territory_code |

The last two domains are named standards with fixed scope — not a generic "international
standards" category. A new standard (ISO 8601, IETF BCP-47 extensions, ITU-T E.164) is
NOT automatically in-scope because a standard exists; it must be added to this table with
explicit justification, because the table is exhaustive.

**Mechanical Rejection Test — apply before any new public symbol:**

1. Does this symbol address a failure mode or composition burden that arises specifically
   from the FTL spec, CLDR locale formatting, or the boot/audit pipeline — and not from
   general programming?
2. Would this symbol need to exist in a library that exclusively implements FTL parsing,
   CLDR-backed locale formatting, and fail-fast boot validation — with no knowledge
   of the caller's domain (financial, medical, logistics, etc.)?
3. Is this symbol's definition or behaviour meaningfully coupled to FTL, CLDR, or the
   boot pipeline — or could it exist without modification in an unrelated Python library?

All three questions must be answered YES. A symbol that fails any one is OUT OF SCOPE for
the public facade. It may exist internally if the implementation requires it, but must not
appear in `__all__` of any facade module.

**Bootstrapping trap:** Defining a new type (e.g., `PhoneNumber`) does not automatically
make a corresponding validator (`require_phone_number`) in-scope. Question 2 applies to
the type itself: would a pure FTL/CLDR/boot library need `PhoneNumber`? If not, neither
the type nor its validator belongs on a public facade.

**Explicitly Out-of-Scope Categories:**

* **Generic type validators** (`require_int`, `require_non_negative_int`,
  `require_non_empty_str`, `coerce_tuple`, etc.): Every Python program needs integer and
  string validation. A stripped FTL/CLDR/boot library would not. Validators are in-scope
  only when the validated type is intrinsic to FTL, CLDR, or boot (e.g.,
  `require_fluent_number` — `FluentNumber` cannot exist outside this library;
  `require_locale_code` — locale canonicalization is required by the CLDR formatting
  pipeline).

* **Fiscal calendar** (`FiscalCalendar`, `FiscalDelta`, `FiscalPeriod`, `MonthEndPolicy`,
  `fiscal_year`, `fiscal_quarter`, `fiscal_month`, `fiscal_year_start`, `fiscal_year_end`,
  `require_fiscal_calendar`, `require_fiscal_period`): Pure date arithmetic with no CLDR
  interaction, no Babel dependency, and no FTL parser involvement. Not an ISO standard.
  Fails the mechanical rejection test on all three questions — no FTL/CLDR/boot coupling;
  would not exist in a stripped FTL/CLDR/boot library; could exist unmodified in any
  financial or accounting library.

* **Accounting/ledger domain** (`LedgerInvariantError`, invariant codes such as
  `BALANCE`, `DUPLICATE_ACCOUNT`, `PERIOD_OVERLAP`): Financial ledger semantics are the
  caller's domain. A stripped FTL/CLDR/boot library has no concept of a ledger. These
  symbols would exist unchanged in a CRM or ERP library that never touches FTL.

* **Storage and persistence domain** (`PersistenceIntegrityError`): Resource *loading*
  into the FTL pipeline is in-scope (`ResourceLoader`, `PathResourceLoader` — these are
  the boundary at which FTL resources enter the library). Storage layer failures below
  that boundary are the caller's concern; a stripped FTL/CLDR/boot library would have
  no concept of persistence integrity independent of FTL resource loading.

* **General concurrency primitives** (`RWLock`, `InterpreterPool`): Concurrency is an
  implementation detail of the runtime layer, not a contract offered to callers. Internal
  modules use `RWLock` for bundle thread-safety; callers have no need to instantiate it.
  `InterpreterPool` is a general PEP 734 pool with no FTL-specific semantics.

* **Internal resolver machinery** (`FluentResolver`, `ResolutionContext`): These are
  implementation details of message resolution. The extension API is `FunctionRegistry` +
  `fluent_function`. Callers do not instantiate resolvers.

**Scope Creep Detection:**

Scope creep occurs when the library adds a symbol because a caller *could use it* rather
than because *the FTL/CLDR/boot pipeline specifically requires it*. The test is not
"does this help callers?" — everything helpful passes that test. The test is: would a
library stripped to only FTL parsing + CLDR formatting + boot validation still need this
symbol? If not, it does not belong. "Could use" adds surface; "the pipeline requires"
eliminates downstream burden. Only the latter justifies promotion.

# 2. CODE & OUTPUT CONSTRAINTS

## 2.1 Professional Output Standard (No-Emoji Policy)
**Constraint:** Enforce strict adherence to professional ASCII standards.
* **PROHIBITED:** Emojis or decorative characters in source code, comments, docstrings, or
  commit messages.
* **PERMITTED:** Emojis are *only* permissible within **Test Data strings** to validate
  Unicode/FTL specification handling (e.g., `parse_ftl("greeting = 👋")` as FTL message
  content inside a test fixture).

## 2.2 Status & Logging Indicators
Use only standardized ASCII indicators for logging and CLI output.

| Status | Indicator | Rationale |
| :--- | :--- | :--- |
| **Success** | `[OK]`, `[PASS]` | Unambiguous status reporting. |
| **Failure** | `[FAIL]`, `[ERROR]` | High-priority failure flag. |
| **Warning** | `[WARN]` | Deprecation or non-critical state alert. |

## 2.3 Documentation Standard
* **Docstrings:** All public modules, classes, and functions must have concise docstrings.
* **Style:** Use Google-style docstrings. This is the style established in the existing
  codebase; consistency with existing code takes precedence.
* **Typing:** Do not duplicate type information in docstrings; rely on type hints.

## 2.4 Self-Containment Principle
**Constraint:** Source code, tests, and documentation must NEVER reference CLAUDE.md.

* **PROHIBITED:** Comments/docstrings referencing "CLAUDE.md", "Section X.Y", or
  "per CLAUDE.md"
* **REQUIRED:** All architectural justifications must be self-contained and self-explanatory
* **RATIONALE:** CLAUDE.md is an AI agent directive, not developer documentation. Human
  developers must understand design decisions without consulting AI protocols.

**Examples:**
```python
# PROHIBITED
# Violates CLAUDE.md §1.3 explicit control flow principle

# REQUIRED
# Uses task-local ContextVar for performance: primitives called 100+ times per parse.
# Explicit context parameter would require 10+ signature changes and 200+ call site updates.
```

**Scope:** Applies to all `.py` files, CHANGELOG.md, and user-facing documentation. Internal
protocol files (`.claude/*.md`, `.codex/*.md`, `.gemini/*.md`) are exempt.

# 3. QUALITY HIERARCHY & WAIVERS

Maintain distinct quality configurations for static analysis. You must respect the specific
configuration files associated with each directory scope.

## 3.1 Core Production Code (`src/`): STRICT
* **Quality Target:** All linters exit 0: Ruff (zero errors), Mypy (`strict = true`). See §5.7
  for enforcement order.
* **Ruff Configuration:** `select = ["ALL"]` with focused `ignore` list in `pyproject.toml`
  (D, ANN, COM812, ISC001, and framework-specific families). New rules apply automatically;
  explicit `ignore` or per-file-ignores required for any suppression.
* **Mypy Configuration:** `strict = true`. No unchecked types; full type annotation coverage
  required.
* **Waiver Philosophy:** Only permit **Architectural Waivers** (see §3.6). Never permit waivers
  for logic bugs, security issues, performance flaws, or dead code.

## 3.2 Verification Test Code (`tests/`): PRAGMATIC
* **Quality Target:** All linters exit 0: Ruff (zero errors), Mypy (pragmatic). See §5.7 for
  enforcement order.
* **Configuration Scope:**
    * **Linter:** `pyproject.toml` (Ruff per-directory overrides).
    * **Type Checker:** `tests/mypy.ini`.
* **Key Allowed Waivers:**
    * `N802` (Naming): Permitted for FTL specification mimicry (e.g., `UPPERCASE_functions`).
    * `SLF001` (Private Access): Permitted for integration tests verifying internal object
      state.
    * `E402`, `PLC0415` (Import Position): Permitted for Hypothesis strategy isolation.

## 3.3 Example Code (`examples/`): DEMONSTRATIVE
* **Configuration Scope:**
    * **Type Checker:** `examples/mypy.ini`.
* **Waiver Philosophy:** Inline configuration is preferred here to serve as documentation for
  users on how to handle linting in their own implementations.

## 3.4 Operational Fuzzing Code (`fuzz_atheris/`): OPERATIONAL
* **Quality Target:** Ruff (zero errors), Mypy (operational — `fuzz_atheris/mypy.ini`). See
  §5.7 for enforcement order.
* **Configuration Scope:**
    * **Linter:** `pyproject.toml` (fuzz_atheris per-directory overrides).
    * **Type Checker:** `fuzz_atheris/mypy.ini`.
* **Key Allowed Waivers:**
    * `PLR0912`, `PLR0915` (Dispatch Complexity): Pattern handler functions in fuzz modules
      MUST use dispatch-to-sub-handlers (see §4.3) rather than monolithic if/elif chains.
      Sub-handler functions are individually simple; the dispatcher itself is a one-liner index
      into a tuple of callables. This is the canonical pattern — do not suppress PLR0912 on
      a monolithic function; refactor first.
    * `S101` (assert): Permitted for invariant checks inside fuzz patterns.
* **Fuzz Pattern Architecture:** Each fuzz pattern function (`_pattern_*`) dispatches to a
  tuple of sub-handler functions (`_check_*`). Each sub-handler tests one behavioral scenario.
  This mirrors the dispatch-to-sub-handlers pattern in §4.3 and keeps individual functions
  within McCabe complexity limits.

## 3.5 No Deferrals Policy
**Constraint:** Technical debt is prohibited. Every issue identified must be resolved
immediately.

**Prohibited Deferrals:**
* "Fix in next version" — If an issue is found, fix it now.
* "TODO: refactor later" — Refactor immediately or not at all.
* "Known issue" — Unknown issues become known; known issues become fixed.
* Backwards-compatibility shims — Make clean breaks; remove deprecated code entirely.
* Migration paths — Users adapt to the current API; old APIs are deleted, not deprecated.
* Suppression as fix — Never suppress lint/static analysis warnings when the underlying code
  can be corrected. Suppression (`# noqa`, `# type: ignore`, `per-file-ignores`) is only
  valid for permanent architectural patterns (see §3.6), not for avoiding proper remediation.

**Rationale:** Deferred fixes accumulate interest. A "small" workaround today becomes an
architectural constraint tomorrow. The cost of immediate remediation is always lower than the
cost of accumulated technical debt.

## 3.6 Waiver Implementation Protocol
Waivers are for **permanent architectural necessities**, never for deferring fixes.

1.  **Fix First:** Attempt remediation before waivering. Waivers are a last resort.
2.  **Permanence Requirement:** A waiver must address a permanent constraint (e.g., Visitor
    pattern naming), not a temporary inconvenience.
3.  **Scope:** Use `per-file-ignores` in the relevant configuration file for patterns that
    apply uniformly to an entire file or directory. Use inline `# noqa` directives for
    isolated single-line exceptions within otherwise conformant files.
4.  **Documentation:** Every waiver must be accompanied by a concise, high-value comment
    justifying the *permanent architectural necessity*.

**Prohibited Waiver Justifications:**
* "Will fix later" — No. Fix now or not at all.
* "Not enough time" — Time is not an accepted constraint; correctness is.
* "Too complex to refactor" — Complexity is a symptom of design issues; address the root
  cause.

## 3.7 Design Principle Hierarchy (Waiver Recognition)
**Constraint:** Documented architectural waivers OVERRIDE general principles stated in this
document.

The codebase contains intentional deviations from stated principles where trade-off analysis
justifies the design. AI agents must distinguish between:

| Category | Definition | Action |
|:---------|:-----------|:-------|
| **Principle** | Default mode of operation stated in CLAUDE.md | Apply unless waiver documented |
| **Waiver** | Documented exception with trade-off rationale | Respect; do NOT flag as violation |
| **Violation** | Undocumented deviation without justification | Flag for remediation |

**Waiver Recognition Signals:**

A design decision is a DOCUMENTED WAIVER if ANY of these signals are present:
* Module docstring explains trade-off (e.g., "Task-Local State (Architectural Decision)")
* Inline comment includes keywords: "intentional", "trade-off", "architectural", "design
  decision"
* Suppression comment provides rationale (e.g., `# noqa: PLC0415 - circular import`)
* Comment explicitly states "permanent" or "accepted"

**Example: Task-Local ContextVar vs. Explicit Control (§1.3)**

§1.3 states: "The system demands explicit control flow... over global state or
`threading.local`."

`primitives.py` uses `contextvars.ContextVar` task-local state (NOT `threading.local`) with
documented justification. ContextVars are async-safe and task-isolated; they do not violate
§1.3's prohibition. The waiver covers the *implicit state* aspect of the principle:
```
# Task-Local State (Architectural Decision):
# - Primitive functions called 100+ times per parse operation
# - Explicit context threading would require ~10 signature changes
# - ContextVar.get()/set() is O(1) with automatic async task isolation
# This is a permanent architectural pattern...
```

This is a WAIVER, not a VIOLATION. The documentation:
1. Acknowledges the principle being relaxed (implicit state)
2. Provides quantitative justification (100+ calls, 10 signatures)
3. Explicitly marks it as "permanent architectural pattern"

**Violation Detection:**

An issue is a TRUE VIOLATION only if:
1. Behavior contradicts a stated principle (e.g., uses `threading.local` or module-global
   mutable state)
2. No documentation within the module docstring OR within the enclosing function/class scope
   justifies the deviation
3. No suppression comment provides rationale

**Agent Responsibility:**

Before flagging ANY apparent principle violation:
1. Read the module docstring for architectural decisions
2. Search within the enclosing function or class scope for waiver documentation
3. Consult the Known Waiver Registry below
4. If documented with rationale: NOT a violation; respect the waiver
5. If undocumented: VALID violation; proceed with issue

**Known Waiver Registry:**

All architectural waivers in `src/`. Each entry is a documented, permanent decision — not a
deferral.

| Module | Suppressed Rule(s) | Principle Relaxed | Permanent Justification |
|:-------|:------------------|:------------------|:------------------------|
| `syntax/parser/primitives.py` | §1.3 explicit control | §1.3 explicit control topology | `ContextVar` task-local state; 100+ calls/parse; threading via ContextVar gives automatic async isolation with O(1) overhead |
| `core/depth_guard.py` | §1.3 immutability | §1.3 immutability protocol | Mutable `current_depth` counter required by context-manager `__enter__`/`__exit__` protocol; state is strictly scoped to each `with` block |
| `core/babel_compat.py` | PLW0603, F401, PLC0415 | §1.3 explicit control (global singleton) | `_babel_available` is a module-level sentinel; computed once at first call; `global` statement is the only stdlib mechanism for a mutable module-level singleton without a class |
| `syntax/parser/core.py`, `rules.py` | PLR0911, PLR0912, PLR0915 | §4.3 dispatch complexity | EBNF grammar rule dispatch: one function = one grammar rule; branching is structural, not accidental |
| `syntax/serializer.py` | PLR0912 | §4.3 dispatch complexity | Classification-dispatch model (§4.6): `_serialize_pattern`, `_emit_classified_line`, `_serialize_expression` branches are exhaustive over closed grammar types |
| `syntax/visitor.py` | ERA001, PLR0911, PLR0912 | §4.3 dispatch complexity | Visitor dispatch + docstring examples (`ERA001`); branching from closed AST node set |
| `runtime/resolver.py` | PLR0911, type:ignore[unreachable] | §4.3 dispatch complexity | `_resolve_expression`, `_get_fallback_for_placeable`: closed `Expression` union type, one return path per variant; `type:ignore[unreachable]` on `_get_fallback_for_placeable` `case _:` — union is statically exhaustive but wildcard is retained as safety net: error-recovery contract must always return a string, never raise |
| `runtime/cache.py` | PLR0911, PLR0912 | §4.3 dispatch complexity | `_make_hashable`: type dispatch over heterogeneous Python values; each branch handles a distinct Python type |
| `introspection/message.py` | N802, RUF022 | §4.1 visitor naming | `visit_NodeName` methods follow stdlib `ast.NodeVisitor` convention; `__all__` organized by category for public/internal clarity |
| `runtime/bundle.py` | PLR0912, E501 | §4.3 dispatch complexity | Resource registration and validation coordination; long lines in structured logging messages |
| `parsing/currency.py` | PLR0911, PLR0912 | §4.3 dispatch complexity | Ambiguous currency symbol disambiguation requires exhaustive symbol/territory resolution |
| `parsing/dates.py` | DTZ007 | Naive datetime | Library does not impose timezone; caller provides timezone-aware values or explicitly opts into naive datetime |
| `runtime/locale_context.py` | DTZ001 | Naive datetime | `format_datetime` promotes a plain `date` to midnight `datetime` with no tzinfo; the date carried no timezone, so none is inferred — this is the correct semantics for a calendar date with no intrinsic time |
| `syntax/parser/whitespace.py` | SIM102 | Style | Nested `if` guards cursor state and EOF simultaneously; merging the conditions hides the state machine intent |
| `syntax/validator.py` | EM102 | Style | `TypeError` f-string messages: violation type includes dynamic type; static string would omit it |
| Babel-optional modules (`parsing/`, `runtime/`, `introspection/`, `core/`) | PLC0415 | §4.2 runtime imports | Babel is optional; imports inside functions are the only way to make them lazy (avoids `ImportError` at module load for parser-only installs) |
| `diagnostics/formatter.py`, `diagnostics/validation.py` | PLC0415 | §4.2 runtime imports | Mutual runtime circular: `ValidationError`/`ValidationWarning` require runtime `isinstance` checks in formatter; `DiagnosticFormatter` is instantiated at runtime in validation factory. Neither is type-only — both execute code at call time. §4.2 pattern 2 is the correct resolution. |
| `diagnostics/codes.py` | PLC0415 | §4.2 runtime imports | `Diagnostic.format()` instantiates `DiagnosticFormatter` at runtime; circular between codes and formatter resolved per §4.2 pattern 2. |
| `validation/resource.py` | PLC0415 | §4.2 runtime imports | Resource validation triggers re-parse for annotation extraction; runtime circular between validation and syntax/parser layers. |
| `runtime/resolution_context.py` | §1.3 immutability | §1.3 immutability protocol | `ResolutionContext` uses mutable `_stack`, `_seen`, `_total_chars`, and `_expression_guard` for cycle detection and expansion tracking; §1.3 explicitly permits mutable accumulation buffers in performance-critical operations; isolation is guaranteed by creating a fresh instance per resolution call — no state leaks between concurrent resolutions |
| `runtime/function_bridge.py` | PLC0415 | §4.2 runtime imports | Function metadata loaded lazily on first call; runtime circular between bridge and function_metadata modules. |
| `runtime/bundle.py` (PLC0415) | PLC0415 | §4.2 runtime imports | Bundle loads `analysis.graph.entry_dependency_set` and `introspection.extract_references` at runtime; circular between runtime layer and analysis/introspection layers. |
| `core/__init__.py` | PLC0415, module `__getattr__` | §1.3 immutability | Lazy-loads `DepthGuard`/`depth_clamp` via module `__getattr__` to break circular import: `depth_guard` → `diagnostics` → `syntax.__init__` → `serializer` → `core.depth_guard`. Eager import during `ftllexengine` package init would deadlock the import chain. `globals()` mutation in `__getattr__` is a permanent, accepted stdlib pattern for module-level lazy singletons. |
| `parsing/guards.py` | TC003 | §4.2 TYPE_CHECKING | `date`, `datetime`, `Decimal` cannot be moved under TYPE_CHECKING: `typing.get_type_hints()` evaluates TypeIs annotation strings at runtime and requires these names in module globals; moving them causes `NameError` in callers using `get_type_hints()` |
| `syntax/ast.py` | TC001 | §4.2 TYPE_CHECKING | `CommentType` is a public re-exported symbol; consumers do `from ftllexengine.syntax.ast import CommentType` at runtime; moving under TYPE_CHECKING would break this import |
| `localization/boot.py` | §1.3 immutability (`object.__setattr__`) | §1.3 immutability protocol | `_booted` guard requires a single post-init mutation (False→True) on a frozen dataclass. `object.__setattr__` bypasses the generated `__setattr__` — the same mechanism Python's own frozen dataclass `__init__` uses. Config fields remain permanently immutable; only the one-shot guard transitions, once, permanently. No alternative exists without abandoning `frozen=True` or changing the public API. |


# 4. DESIGN PATTERNS & LINT INTEGRATION

## 4.1 Visitor Pattern Implementation
* **Pattern:** Follow the standard library's `ast.NodeVisitor` convention for AST traversal.
* **Waiver:** Suppress `N802` (function name snake_case) for dispatch methods like
  `visit_Message` to match the node class names.

## 4.2 Runtime Imports (Circular Dependency Avoidance)
**Two distinct patterns, applied in priority order:**

1. **`TYPE_CHECKING` guard (preferred for type-only imports):** When a circular dependency
   exists only because a type annotation references the other module, wrap the import under
   `TYPE_CHECKING`. No `PLC0415` suppression is required (the import is still top-level); the
   import is elided at runtime.
   ```python
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from ftllexengine.introspection import MessageIntrospection
   ```
2. **Function-local import (runtime circular dependency):** Use only when the circular
   dependency cannot be resolved via `TYPE_CHECKING` because the import is needed at runtime
   (not just for type annotations). Requires `PLC0415` suppression with rationale.
   ```python
   def _resolve(self) -> ...:
       from ftllexengine.runtime.cache import IntegrityCache  # noqa: PLC0415 - runtime circular
       ...
   ```
* **Constraint:** `TYPE_CHECKING` is always preferred. New `PLC0415` suppressions require
  explicit justification proving `TYPE_CHECKING` is insufficient.

## 4.3 Handling Complex Dispatch Logic
* **Pattern:** Grammar-derived or specification-driven dispatch logic has inherently high
  branching complexity. This applies to both the parser and the serializer.
* **Waiver:** Suppress `PLR0912` (too many branches) and `PLR0915` (too many statements) for:
    * The main parser loop (`syntax/parser/core.py`) — EBNF grammar rule dispatch
    * Serializer classification-dispatch methods (`syntax/serializer.py`:
      `_serialize_pattern`, `_emit_classified_line`) — documented in §4.6

**Fuzz pattern handlers:** `_pattern_*` functions in `fuzz_atheris/` that cover many
behavioral scenarios MUST use dispatch-to-sub-handlers rather than a single if/elif chain.
The top-level handler selects a sub-handler via an integer index into a tuple; each
sub-handler is a standalone function covering one scenario. This keeps each function under
complexity limits and makes scenario coverage explicit. Do NOT suppress PLR0912 on a monolithic
function — refactor it.

## 4.4 Type Narrowing (Union Types)
**Critical Implementation:** Never access attributes of a Union type without prior runtime
validation.
* **Action:** Always use explicit `isinstance()` checks or `match/case` blocks to narrow the
  type before accessing specific attributes.

```python
# Type-Safe Narrowing Example
from ftllexengine.syntax.ast import Message, Term, Pattern

def get_entry_id(entry: Message | Term) -> str:
    """Extract identifier from Message or Term using pattern matching."""
    match entry:
        case Message(id=identifier):
            return identifier.name
        case Term(id=identifier):
            return identifier.name
        case _:
            raise TypeError(f"Unexpected entry type: {type(entry)}")
```

## 4.5 Facade Layer (FluentBundle, FluentLocalization, LocalizationBootConfig)

The facade layer is where the platform axioms from §1.1 are realized. All three facade classes
coordinate subsystems; none implement the logic they coordinate. The dependency graph is
**unidirectional** — delegate modules MUST NOT import any facade class.

### 4.5.1 FluentBundle — Single-Locale Formatting Unit

`FluentBundle` is the core formatting unit. It owns a single locale and a set of parsed FTL
resources.

| Responsibility | Delegate Module | FluentBundle Role |
|:---------------|:----------------|:------------------|
| Parsing | `syntax.parser.FluentParserV1` | Calls `parse()`, registers results |
| Resolution | `runtime.resolver.FluentResolver` | Instantiates, calls `resolve_message()` |
| Validation | `validation.validate_resource()` | Single-line delegation |
| Introspection | `introspection.extract_variables()`, `introspect_message()` | Single-line delegation |
| Caching | `runtime.cache.IntegrityCache` | Holds reference, calls `get()`/`put()` |

**Metric Clarification:** FluentBundle has a high docstring-to-code ratio because it is the
primary public API facade. This is expected given the mandate in §2.3. High docstring ratio
is not debt.

### 4.5.2 FluentLocalization — Multi-Locale Coordinator

`FluentLocalization` coordinates a set of locale-scoped `FluentBundle` instances and
implements the fallback chain. It does not hold bundles eagerly — bundle creation is lazy on
first `format_pattern` call for a given locale.

| Responsibility | Delegate | FluentLocalization Role |
|:---------------|:---------|:------------------------|
| Resource loading | `ResourceLoader` protocol | Calls `loader.load(locale, resource_id)` |
| Bundle management | `FluentBundle` | Creates on demand, holds in `_bundles` dict |
| Fallback resolution | Locale chain | Iterates locale list until format succeeds |
| Boot validation | `require_clean()`, `validate_message_schemas()` | Provides pre-traffic validation API |
| Audit log | `FluentBundle.get_cache_audit_log()` | Aggregates per-locale logs into dict |

### 4.5.3 LocalizationBootConfig — Strict-Mode Boot Orchestrator

`LocalizationBootConfig` is a one-shot boot coordinator, not a persistent object. It composes
`FluentLocalization`, `require_clean()`, and `validate_message_schemas()` into a single
audited boot sequence and discards itself after `boot()` returns the live `FluentLocalization`.

* `boot()` → `(FluentLocalization, LoadSummary, tuple[MessageVariableValidationResult, ...])`:
  PRIMARY API; executes full boot sequence and returns structured evidence for audit trails;
  raises `IntegrityCheckFailedError` on any load failure, required-message absence, or schema
  mismatch.
* `boot_simple()` → `FluentLocalization`: simplified form; raises on failure but discards
  audit evidence; use when structured evidence is not required.
* The `LocalizationBootConfig` instance has no role after `boot()` completes. It is not
  thread-safe to share across calls.

**PROHIBITED Refactorings (all three facades):**
* Extracting facade methods into mixins (creates hidden C3 linearization complexity)
* Creating "Service" wrappers around single-line delegation methods (adds indirection, zero
  benefit)
* Lifting delegate module internals to the facade (violates the unidirectional dependency
  graph)

## 4.6 Serializer Architecture (FluentSerializer)
**Pattern:** The serializer is a deterministic AST-to-FTL compiler. Its architecture separates
three concern layers and enforces a classify-then-dispatch model for continuation line emission.

### 4.6.1 Architectural Layers

| Layer | Responsibility | Methods |
|:------|:---------------|:--------|
| **Validation** | AST structural correctness (separate pass, runs first) | `_validate_resource`, `_validate_expression`, `_validate_pattern`, `_validate_call_arguments`, `_validate_identifier`, `_validate_select_expression` |
| **Node Serialization** | AST node dispatch via `match/case` | `_serialize_entry`, `_serialize_message`, `_serialize_term`, `_serialize_attribute`, `_serialize_comment`, `_serialize_junk`, `_serialize_expression`, `_serialize_call_arguments`, `_serialize_select_expression` |
| **Pattern Emission** | Continuation line classification, whitespace preservation, character escaping | `_serialize_pattern`, `_classify_line`, `_escape_text` |

**Constraint:** Validation runs BEFORE serialization. Serialization code assumes validated
input. These layers MUST NOT be merged.

### 4.6.2 Continuation Line Model

The FTL parser interprets continuation lines structurally: leading whitespace is syntactic
indent, blank lines are stripped, and characters `.`, `*`, `[` as the first non-whitespace
trigger attribute/variant parsing. The serializer MUST ensure that content whitespace and
content syntax characters are not misinterpreted as structural.

**Invariant:** Every continuation line emitted by the serializer must be unambiguous under FTL
parsing rules. Ambiguity is resolved by wrapping problematic content in `StringLiteral`
placeables (`{ "..." }`), which the parser treats as expression content, not structural syntax.

**Classification-Before-Dispatch:**

Each continuation line is classified ONCE by a pure function, then handled through a single
`match/case` dispatch:

```python
class _LineKind(Enum):
    EMPTY = auto()           # No content (just structural indent)
    WHITESPACE_ONLY = auto() # All spaces; parser would strip as blank line
    SYNTAX_LEADING = auto()  # First non-ws char is . or * or [; parser
                             # would interpret as attribute/variant
    NORMAL = auto()          # Unambiguous text content
```

| Kind | Ambiguity | Resolution |
|:-----|:----------|:-----------|
| `EMPTY` | None | Emit structural indent only |
| `WHITESPACE_ONLY` | Parser strips blank continuation lines | Wrap entire line in `StringLiteral` placeable |
| `SYNTAX_LEADING` | Parser treats first non-ws char as structural | Emit leading spaces as text, wrap syntax char in `StringLiteral` placeable |
| `NORMAL` | None (may contain braces that need escaping) | Emit with brace escaping via `_escape_text` |

**PROHIBITED:**
* Handling whitespace ambiguity classes outside the classification-dispatch model (no scattered
  `if` branches in multiple methods)
* Adding line-level concerns to `_escape_text` (it handles character-level brace escaping only)
* Modifying AST nodes to carry serializer-specific layout hints (AST represents language
  structure, not rendering)
* Event/Layout/Emitter pipeline abstractions (overengineered for the Fluent 1.0 grammar,
  which is a finalized specification with a fixed, closed node set)

### 4.6.3 Separate-Line Mode

When a pattern contains cross-element whitespace dependencies (a `TextElement` starting with
spaces follows a newline-ending element), the serializer outputs the pattern on a separate
line from `=` to establish `initial_common_indent` before any semantic whitespace. This is a
**pattern-level** decision, orthogonal to the per-line classification in §4.6.2.

**Interaction:** `WHITESPACE_ONLY` and `SYNTAX_LEADING` lines are handled by per-line
wrapping, NOT by separate-line mode. Only `NORMAL` lines with leading whitespace after a
cross-element newline trigger separate-line mode.

### 4.6.4 Character-Level Escaping (`_escape_text`)

The `_escape_text` function handles ONLY brace escaping: `{` and `}` at any position are
wrapped as `StringLiteral` placeables (per Fluent spec, braces in `TextElement` content must
be expressed as `{ "{" }` and `{ "}" }`).

All other ambiguity concerns are resolved BEFORE `_escape_text` is called:
* Syntax characters (`.`, `*`, `[`) at continuation line starts: handled by
  `_emit_classified_line` (`SYNTAX_LEADING` branch)
* Whitespace-only lines: handled by `_emit_classified_line` (`WHITESPACE_ONLY` branch)
* Newline detection and continuation line boundaries: text is pre-split by
  `_serialize_pattern`

### 4.6.5 Exhaustiveness

All `match/case` dispatches on closed union types (`Entry`, `Expression`, `_LineKind`) MUST be
exhaustive. Use `assert_never()` from `typing` for enum dispatches and explicit
`case _: raise TypeError(...)` for AST union dispatches where the union may grow.

## 4.7 Ruff Configuration and Operational Rules

**Configuration:** `select = ["ALL"]` in `[tool.ruff.lint]`. New rules apply automatically;
explicit `ignore` or per-file-ignores required for any suppression. No curated allow-list —
the ignore list must justify every exception.

### 4.7.1 Global `ignore` vs Per-File-Ignores

| Mechanism | Use when |
|:----------|:---------|
| Global `ignore` | Rule NEVER applies anywhere in the codebase (wrong framework, redundant with mypy strict, formatter territory) |
| Per-file-ignores | Rule is valid for most files but a specific file has a documented architectural reason for an exception |
| Per-directory blanket | Entire directory has a distinct quality standard (`tests/`, `examples/`, `fuzz_atheris/`, `scripts/`) |

**Prohibited:** Suppressing a rule globally because one file needs it. One file's exception
belongs in per-file-ignores, not the global ignore list.

### 4.7.2 TC001/TC003 (TYPE_CHECKING Imports) — Non-Negotiable Exceptions

Two categories of imports **must never** be moved under `TYPE_CHECKING`, even when TC fires:

1. **TypeIs annotation types**: `typing.get_type_hints()` evaluates annotation strings at
   runtime in the module's `globals()`. If `date`, `datetime`, `Decimal` (or any type used in
   `-> TypeIs[X]`) are under `TYPE_CHECKING`, `get_type_hints()` raises `NameError` at runtime
   in callers.
   - Affected: `parsing/guards.py` (`date`, `datetime`, `Decimal`)
   - Fix: keep as direct import; add
     `# noqa: TC003 - TypeIs return annotation requires X at runtime for get_type_hints() resolution`

2. **Public re-exported symbols**: If callers do
   `from ftllexengine.syntax.ast import CommentType` at runtime, moving `CommentType` under
   `TYPE_CHECKING` in `ast.py` makes the import fail.
   - Affected: `syntax/ast.py` (`CommentType`)
   - Fix: keep as direct import; add
     `# noqa: TC001 - CommentType is re-exported as a public runtime symbol`

Both are in the Known Waiver Registry (§3.7).

### 4.7.3 FBT001/FBT002 (Boolean Traps) — Fix Pattern

Ruff FBT flags boolean-typed positional parameters. **Preferred fix:** make the argument
keyword-only by adding `*` before it.

```python
# BEFORE (FBT001 fires)
def get_patterns(locale: str, allow_expansion: bool = True) -> list[str]: ...

# AFTER (FBT resolved)
def get_patterns(locale: str, *, allow_expansion: bool = True) -> list[str]: ...
```

After making an arg keyword-only, check all call sites — mypy reports "too many positional
arguments" for any missed site.

**Acceptable waiver** (for truly internal private functions): add to per-file-ignores with
rationale. Do not add FBT to the global ignore.

### 4.7.4 C901 (McCabe Complexity) — Waiver Pattern

Grammar rules, AST visitor dispatch, and closed-union dispatch legitimately exceed the McCabe
threshold. Add C901 alongside PLR0912 in per-file-ignores:

```toml
"src/ftllexengine/syntax/parser/rules.py" = ["PLR0911", "PLR0912", "PLR0915", "C901"]
```

Rationale comment template: `"Grammar/AST dispatch: one function = one grammar rule;
cyclomatic complexity is structural, not accidental."`


# 5. VERIFICATION METHODOLOGY

## 5.1 Test File Naming Schema

Test file naming is a hard structural constraint, not a style preference. It determines
discoverability: an agent searching for tests covering `runtime/bundle.py` must be able to
predict the filename without scanning all 200+ test files.

**Canonical schema:** `test_{package}_{module}[_{qualifier}].py`

| Segment | Derived from | Examples |
|:--------|:-------------|:---------|
| `{package}` | `src/ftllexengine/` subpackage name | `runtime`, `syntax`, `parsing`, `diagnostics` |
| `{module}` | Module filename without `.py` | `bundle`, `resolver`, `serializer` |
| `{qualifier}` | Optional single axis (see permitted list) | `_property`, `_integration` |

For nested subpackages, join segments with underscore:
`src/ftllexengine/syntax/parser/core.py` → `test_syntax_parser_core.py`

For top-level modules (`src/ftllexengine/enums.py`), omit the package segment:
`test_enums.py`

**Permitted qualifiers (exhaustive list):**

| Qualifier | Meaning | Runs in CI? |
|:----------|:--------|:------------|
| *(none)* | Primary unit/contract tests | Yes |
| `_property` | Hypothesis `@given` tests | Yes |
| `_integration` | Multi-component tests crossing module boundaries | Yes |
| `_roundtrip` | Serialization/parse identity verification | Yes |
| `_state_machine` | `RuleBasedStateMachine` tests (in `tests/fuzz/` only) | No |

No other qualifiers are permitted. If a file cannot be classified by one of these axes,
it belongs in an existing file or signals that file should be split.

**Fuzz-marker test location:** All tests carrying `@pytest.mark.fuzz` MUST reside in
`tests/fuzz/`. The `tests/` root contains only tests that run in CI without the fuzz marker.
A `_property` file in `tests/` root is NOT a fuzz file even if it uses `@given`; the marker
and directory are what determine fuzz status (see §5.8).

**Deprecated suffixes — prohibited for new files:**

| Deprecated suffix | Canonical replacement |
|:------------------|:----------------------|
| `_hypothesis` | `_property` |
| `_fuzzing` | Move file to `tests/fuzz/` |
| `_properties` | `_property` |
| `_comprehensive` | *(none; split into focused files by axis)* |
| `_advanced` | *(none; not a behavioral axis)* |
| `_edge_cases` | *(none; fold edge cases into primary or property file)* |

**Files name systems under test, not motivations for writing them:**

```
PROHIBITED: test_system_quality_audit_fixes.py       (internal task reference)
PROHIBITED: test_diagnostics_and_runtime_behaviors.py  ("and" = two subjects)
PROHIBITED: test_cross_module_branch_coverage.py     (coverage technique, not subject)
PROHIBITED: test_bundle_advanced_hypothesis.py       (two deprecated qualifiers)

REQUIRED:   test_runtime_bundle_property.py
REQUIRED:   test_diagnostics_formatter_integration.py
REQUIRED:   test_runtime_resolver_property.py
```

"And" in a filename is a mandatory split signal: the file covers two subjects and must
become two files. A file name that cannot map back to a single source module path is invalid.

## 5.2 Hypothesis-First Protocol
Property-Based Testing (Hypothesis) is the **primary** mechanism for verification, not an
afterthought. Unit tests with fixed inputs are appropriate only for CLDR-mandated exact output
values and `@example`-promoted Hypothesis failures (regression cases). All other verification
uses Hypothesis.

**HypoFuzz Symbiosis:** All Hypothesis tests are designed for coverage-guided fuzzing via
HypoFuzz. Tests and strategies MUST emit semantic coverage signals via `hypothesis.event()` to
guide the fuzzer toward interesting code paths.

## 5.3 Test Construction Strategy
Do not simply "fuzz" the code. You must construct tests based on deep code analysis:

### 5.3.1 Identify Properties
Before writing code, identify the mathematical properties of the component:
* *Roundtrip:* `decode(encode(x)) == x`
* *Idempotence:* `parse(parse(x).to_string()) == parse(x)`
* *Oracle:* Compare behavior against ShadowBundle or reference implementation
* *Metamorphic:* Predictable relationships (e.g., `len(filter(xs)) <= len(xs)`)

### 5.3.2 Emit Semantic Coverage Events (MANDATORY)
**Constraint:** Every `@given` test — regardless of file or marker — MUST use `hypothesis.event()`
to signal semantically interesting behaviors invisible to code coverage. HypoFuzz treats events
as virtual branches, actively seeking inputs that produce new events. Preflight enforces this
across ALL `@given` tests, not just fuzz-marked modules.

```python
from hypothesis import event, given
from tests.strategies.ftl import ftl_placeables

@given(placeable=ftl_placeables())
def test_placeable_serialization(placeable: Placeable) -> None:
    # REQUIRED: Emit event for expression type diversity
    event(f"expr_type={type(placeable.expression).__name__}")

    result = serialize(placeable)
    parsed = parse(result)

    # REQUIRED: Emit event for error paths
    if parsed.errors:
        event(f"error={type(parsed.errors[0]).__name__}")

    assert parsed.ast == placeable
```

**Event Taxonomy (Use Consistently):**

| Category | Format | Examples |
|:---------|:-------|:---------|
| Strategy choice | `strategy={variant}` | `strategy=placeable_variable`, `strategy=chaos_prefix_brace` |
| Domain classification | `{domain}={variant}` | `currency_decimals=2`, `territory_region=europe` |
| Boundary/depth | `boundary={name}`, `depth={n}` | `boundary=at_max_depth`, `depth=99` |
| Unicode category | `unicode={category}` | `unicode=emoji`, `unicode=cjk` |
| Property outcome | `outcome={result}` | `outcome=roundtrip_success`, `outcome=immutability_enforced` |
| Test parameter | `{param}={value}` | `thread_count=20`, `cache_size=50`, `reentry_depth=3` |
| State machine | `rule={name}`, `invariant={name}` | `rule=add_simple_message`, `invariant=cache_stats_consistent` |

**Strategy Events vs Test Events:**

* **Strategy events** are emitted by strategy functions in `tests/strategies/`. They are
  tracked by `EXPECTED_EVENTS` in `tests/strategy_metrics.py` and drive strategy-level coverage
  metrics. Format: `strategy={family}_{variant}` or `{domain}={variant}`.
* **Test events** are emitted by individual `@given` test functions and `@rule`/`@invariant`
  methods. They guide HypoFuzz per-test but are NOT tracked by `EXPECTED_EVENTS`. Format:
  `{param}={value}`, `outcome={result}`, `rule={name}`.

When adding a new strategy, update `EXPECTED_EVENTS`. When adding test events, no metrics
update is needed.

### 5.3.3 Strategy Construction (Soundness Over Exhaustion)
* Use `st.from_type()` and `st.builds()` to construct valid domain objects
* **Avoid:** High-rejection-rate filters on loose primitives (e.g.,
  `st.text().filter(is_valid_ftl)`). Low-rejection filters on constrained strategies are
  acceptable when they improve readability.
* **REQUIRED:** Strategies MUST emit events when selecting between semantically distinct
  variants

```python
@composite
def ftl_placeables(draw: st.DrawFn, max_depth: int = 2) -> Placeable:
    """Generate Placeable AST nodes.

    Events emitted:
    - strategy=placeable_{choice}: Type of expression generated
    """
    choice = draw(st.sampled_from(["variable", "function_ref", "term_ref"]))

    # REQUIRED: Emit strategy choice for fuzzer guidance
    event(f"strategy=placeable_{choice}")

    # ... generation logic ...
```

### 5.3.4 Contextual Awareness
Investigate how code is called. Define strategies that mirror real usage patterns (e.g.,
chunked buffer inputs vs. whole-string inputs).

### 5.3.5 Event Verification
**Constraint:** Verify event infrastructure coverage.

```bash
./scripts/fuzz_hypofuzz.sh --preflight
```

**Enforcement Levels:**
1. **File-level:** Every `@pytest.mark.fuzz` module MUST contain `event()` calls.
2. **Per-test (AST-based):** Every `@given` test function across ALL test files (both
   `tests/` root and `tests/fuzz/`) MUST emit at least one semantic event. The preflight tool
   parses all test files via Python AST to verify this — the check is not scoped to fuzz-marked
   modules. Any `@given` test without `event()` fails preflight with exit code 1.
3. **Strategy file coverage:** Every strategy implementation file in `tests/strategies/` MUST
   emit `event()` calls. `__init__.py` is exempt as a pure re-export aggregator (enforced by
   `_STRATEGY_REEXPORT_FILES` in the preflight script). A strategy file with 0 events gives
   HypoFuzz zero semantic guidance — treated as an error, not a warning.
4. **Zero gaps:** Preflight must report zero gaps at all three levels. Any gap causes exit
   code 1.

**Violation:** If preflight shows fuzz modules, individual tests, or strategy files without
events, fuzzing sessions will have reduced semantic guidance. HypoFuzz captures events
internally for coverage decisions — components without events provide no semantic signals.

**Scope Limitation:** Preflight validates `@given` tests only. `RuleBasedStateMachine` rules
and invariants use `@rule`/`@invariant` decorators (not `@given`), so their event coverage
is not checked by preflight. State machine event coverage is verified manually.

### 5.3.6 Runtime Strategy Metrics

The runtime metrics system (`tests/strategy_metrics.py`) complements preflight's static
analysis with dynamic event collection during test execution.

**Three Core Constants:**

| Constant | Purpose |
|:---------|:--------|
| `EXPECTED_EVENTS` | Set of fully-expanded event strings expected from all strategies |
| `STRATEGY_CATEGORIES` | Maps event prefixes to human-readable strategy family names |
| `INTENDED_WEIGHTS` | Expected per-variant distribution within each strategy family |

**Metrics Collected:** Total events, per-strategy counts, weight skew (threshold: 0.15),
coverage gaps, performance percentiles.

**Preflight vs Runtime Distinction:**

| Aspect | Preflight (`--preflight`) | Runtime (`--deep --metrics`) |
|:-------|:--------------------------|:-----------------------------|
| Method | Static AST analysis | Dynamic event collection |
| Question | "Does `event()` exist in code?" | "Which events fired? At what frequencies?" |
| Catches | Missing instrumentation | Dead code paths, weight skew |
| Speed | Instant (no test execution) | Requires full test run |

**Activation:**

```bash
./scripts/fuzz_hypofuzz.sh --deep --metrics
```

Environment variables: `STRATEGY_METRICS=1`, `STRATEGY_METRICS_LIVE=1`,
`STRATEGY_METRICS_DETAILED=1`. Results saved to `.hypothesis/strategy_metrics.json`.

**Maintenance:** When adding a new event-emitting strategy in `tests/strategies/`, update all
three constants in `tests/strategy_metrics.py`. Test-level events (emitted by `@given` tests,
not strategies) do not require metrics updates.

## 5.4 The Feedback Loop (Regression Proofing)
* **Discovery:** When Hypothesis finds a failure, it caches the minimal failing example in
  `.hypothesis/examples/`
* **Action:** Investigate the root cause. Distinguish between a genuine bug and an incorrect
  test assumption
* **Promotion:** For every non-trivial bug found, **promote the failing example** into the
  test suite using the `@example(...)` decorator

```python
@example(ftl="edge-case = { $var")  # Promoted from Hypothesis finding
@given(ftl=ftl_simple_messages())
def test_roundtrip(ftl: str) -> None:
    ...
```

**Crash Recording Infrastructure:** When a Hypothesis test fails, the `conftest.py` crash
recording hook (`pytest_runtest_makereport`) automatically:
1. Generates a standalone `repro_crash_<hash>.py` reproduction script in
   `.hypothesis/crashes/`
2. Saves JSON metadata (test ID, example args, error type, timestamp) alongside the script
3. Creates portable crash files that persist independently of `.hypothesis/examples/` and
   survive database cleanup

Use `./scripts/fuzz_hypofuzz.sh --repro` or run crash scripts directly for reproduction.

## 5.5 Database Persistence
The Hypothesis example database (`.hypothesis/examples/`) persists across fuzzing sessions. It
stores failing examples and covering examples (inputs that trigger distinct code paths during
`Phase.reuse`).

**Cross-Session Value:**
* **Phase.reuse:** Replays stored examples FIRST, catching regressions immediately
* **Example accumulation:** Each `--deep` session discovers new covering examples and failures
* **Shrink memory:** Minimal failing examples preserved across runs

**Constraint:** Do NOT delete `.hypothesis/` between fuzzing sessions unless intentionally
resetting the database. A 30-minute session today + 30-minute session tomorrow = 60 minutes
of cumulative learning.

## 5.6 Hypothesis Profiles
Profiles are defined in `tests/conftest.py`. Use the appropriate profile for context:

| Profile | max_examples | deadline | Use Case |
|:--------|:-------------|:---------|:---------|
| `dev` | 500 | 200ms | Local development |
| `ci` | 50 | 200ms | Fast CI feedback (reproducible) |
| `verbose` | 100 | 200ms | Debugging with progress output |
| `hypofuzz` | 10000 | None | Coverage-guided `--deep` runs |
| `stateful_fuzz` | 500 | None | State machine fuzzing |

**Profile Details:**
* All profiles include `Phase.target` for targeted property exploration via `target()`.
* `ci` uses `derandomize=True` for reproducible builds and `print_blob=True` for failure
  reproduction.
* `hypofuzz` suppresses `HealthCheck.too_slow` and `HealthCheck.data_too_large` for intensive
  runs.
* `fuzz_hypofuzz.sh --deep` automatically sets `HYPOTHESIS_PROFILE=hypofuzz`.

## 5.7 Workflow Execution Order
The execution of scripts defines the quality gate. **All three steps must pass in order.**

1.  **Lint:** `./scripts/lint.sh` (Ruff → Mypy). Must exit code 0.
2.  **Test:** `./scripts/test.sh` (Pytest + Hypothesis + Coverage). Must meet the 95%
    threshold. Must exit code 0.
3.  **Preflight:** `./scripts/fuzz_hypofuzz.sh --preflight` (AST-based event audit). Must exit
    code 0. Run whenever `tests/` or `tests/strategies/` files are modified. Runs in seconds
    (no test execution); zero cost to always run.

### Script Output Design (Agent-Native, Log-on-Fail)
Both `lint.sh` and `test.sh` are AI-agent-optimized with a **log-on-fail** design. Run them
directly without any output truncation:

```bash
./scripts/lint.sh
./scripts/test.sh
```

**NEVER pipe through `tail`, `head`, or any output limiter. NEVER append redirection operators
(`2>&1`, `>`, `>>`).**  The output is already appropriately sized:
* **On success:** emits only structured summary lines (`[PASS]`, JSON block). Already minimal
  — no truncation needed.
* **On failure:** captures the full diagnostic log, then dumps it all at once. This dump IS
  the analysis. Truncating it destroys the error context needed for diagnosis.

Limiting output (e.g., `| tail -100`) means on failure you see only the summary footer,
missing the actual error details. Redirecting stderr (e.g., `2>&1`) loses the distinction
between stdout and the Bash tool's inherent stderr capture. The scripts are designed so the
agent never needs to re-run them to get more detail.

## 5.8 Fuzz Test Skip Designation (Standardized)
**Constraint:** Intensive property tests excluded from normal runs use `@pytest.mark.fuzz` and
a standardized skip reason.

### Decision Criteria: When to Apply `@pytest.mark.fuzz`

The fuzz marker controls whether a test **runs at all** during `test.sh`. It is independent of
`event()` calls (which are mandatory in ALL `@given` tests per §5.3.2) and independent of
Hypothesis profiles (which control example counts when a test does run).

| Test Category | Runs in CI? | Fuzz Marker? | Example Count |
|:--------------|:------------|:-------------|:--------------|
| Regular `@given` with `event()` | Yes | No | `ci`=50, `dev`=500 |
| Intensive fuzz-only | No (skipped) | `@pytest.mark.fuzz` | Only under `--deep` (10000) |

**Apply `@pytest.mark.fuzz` ONLY when** the test meets one or more of these criteria:
* **State machines** (`RuleBasedStateMachine`) that explore exponential state spaces
* **Generators producing expensive objects** (deeply nested ASTs, large resources) where even
  50 examples would exceed CI time budgets
* **Tests with `deadline=None`** that intentionally allow slow individual examples
* **Tests requiring `suppress_health_check`** for `too_slow` or `data_too_large`

**Hard placement rule:** Any test that uses `deadline=None` or
`suppress_health_check=[HealthCheck.too_slow]` MUST carry `@pytest.mark.fuzz` and reside in
`tests/fuzz/`. These settings signal that the test is intentionally slow — running 50 such
tests in CI would blow time budgets. Examples: boot-sequence tests that construct real loaders,
state machines. Do NOT place `deadline=None`
tests in `tests/` root even if they have bounded strategies.

**Never hardcode `max_examples` in `tests/fuzz/`:** Fuzz tests MUST NOT set `max_examples=N`
in their `@settings` decorator. The `hypofuzz` profile controls exploration depth (10,000 for
`--deep --metrics`, continuous for HypoFuzz). Hardcoding `max_examples` overrides the profile
and artificially caps exploration — a `@settings(max_examples=20)` test runs only 20 examples
even under the `hypofuzz` profile's 10,000 budget. The only meaningful settings for fuzz tests
are `deadline=None`, `suppress_health_check`, and `stateful_step_count` (state machines only).

**Do NOT apply `@pytest.mark.fuzz`** to standard `@given` tests with bounded strategies and
no deadline suppression. These run fast at 50 examples and benefit from CI regression
coverage. The Hypothesis profile system (`ci`/`dev`/`hypofuzz`) automatically scales example
counts — the same test runs with 50 examples in CI and 10000 under `--deep` without any
marker.

### Marker Mechanics

* **Marker:** `@pytest.mark.fuzz` at class or module level (`pytestmark = pytest.mark.fuzz`).
* **Skip Reason Prefix:** All fuzz skips use the reason prefix `"FUZZ:"`. The canonical reason
  string is:
  ```
  FUZZ: run with ./scripts/fuzz_hypofuzz.sh --deep or pytest -m fuzz
  ```
* **Prefix Requirement:** The `"FUZZ:"` prefix is a structural contract consumed by
  `conftest.py` and `test.sh` for skip categorization. Do not alter the prefix.
* **Skip Breakdown Reporting:** `test.sh` emits `skipped_fuzz` and `skipped_other` in the
  JSON summary. If `skipped_other > 0`, a `[WARN]` is emitted indicating non-fuzz tests were
  skipped and require investigation.
* **Prohibited Variations:** `"SKIPPEDfuzz"`, `"SKIPPED fuzz"`, `"Fuzzing test"`, or any
  other ad-hoc skip reason for fuzz tests. All fuzz skip reasons MUST use the `"FUZZ:"` prefix.

### HypoFuzz Targeting Rationale

`--deep` targets `tests/fuzz/` exclusively — NOT `tests/`. This is a deliberate concentration
strategy:

| Target | Effect |
|:-------|:-------|
| `tests/fuzz/` (correct) | 4 workers concentrated on ~35 high-value, slow, open-ended targets |
| `tests/` (wrong) | 4 workers diluted across 1500+ tests, most of which are fast and bounded |

Pointing HypoFuzz at `tests/` wastes worker capacity on tests that already run fine under CI's
50-example budget. The fuzz directory exists precisely to give HypoFuzz a concentrated set of
targets where unlimited exploration has the highest marginal value: state machines, pool
concurrency, boot sequences, subinterpreters. When adding new fuzz targets, always place them
in `tests/fuzz/`; `tests/` tests are CI regression suites, not fuzzing targets.

## 5.9 Advanced: Targeted Fuzzing with target()
All profiles include `Phase.target`, so `target()` is active in every test run. Use it to
guide Hypothesis toward inputs that maximize specific metrics:

```python
from hypothesis import given, settings, target

@settings(deadline=None)
@given(source=ftl_chaos_source())
def test_parser_recovery(source: str) -> None:
    result = parse(source)
    # Guide fuzzer toward inputs with more junk nodes (parser stress)
    target(len([e for e in result.body if isinstance(e, Junk)]), label="junk_count")
```

The `target()` function accepts a numeric value and an optional label. Hypothesis actively
seeks inputs that maximize the targeted metric, making it effective for hunting specific bug
classes (deep nesting, large error counts, parser recovery stress).

# 6. DOCUMENTATION PROTOCOL (MANDATORY)

## 6.1 Governing Protocol
**Constraint:** All markdown file operations MUST comply with PROTOCOL_AFAD.md (v4.0).

| File Pattern | Tier | Protocol Section |
|:-------------|:-----|:-----------------|
| `docs/DOC_*.md` | Reference | AFAD reference-doc rules |
| `README.md` (repository root) | Storefront special case | `AGENTS.md` root README exception |
| `*.md` (all other repo markdown) | Auxiliary / special | AFAD auxiliary-doc rules or native document convention |

**Protocol Location:** `.codex/PROTOCOL_AFAD.md`

## 6.2 Protocol Enforcement
**Before ANY markdown file operation**, the AI agent MUST:

1. **LOAD** `.codex/PROTOCOL_AFAD.md`.
2. **IDENTIFY** the file tier (Reference = `DOC_*.md`, Auxiliary = other).
3. **COMPLY** with all schema requirements, formatting rules, and validation checks.
4. **REJECT** any user request that would violate the protocol.

## 6.3 Reference Documentation (AFAD v4.0)
Applies to: `docs/DOC_00_Index.md`, `docs/DOC_01_*.md`, `docs/DOC_02_*.md`, etc.

**Requirements:**
* YAML frontmatter with `afad: "4.0"`, `version`, `domain`, `updated`, `route`
* Component Entry Schema: Signature, Parameters table, Constraints
* First line states what symbol IS (embeddability)
* Minimal one-shot examples permitted (≤5 lines)
* Full type annotations on all signatures
* Entry ≤600 tokens (atomicity)

## 6.4 Auxiliary Documentation (AFAD v4.0)
Applies to: any repo `*.md` file that does NOT match `docs/DOC_*.md`, except the repository
root `README.md` storefront special case. Examples: `CHANGELOG.md`, `docs/*_GUIDE.md`,
`docs/THREAD_SAFETY.md`, `examples/README.md`.

**Requirements:**
* YAML frontmatter with `afad: "4.0"`, `version`, `domain`, `updated`, `route` where the file convention permits it
* Purpose/Prerequisites/Overview structure for guides
* Economy of words (no filler phrases)
* All code blocks specify language and are runnable
* QUICK_REFERENCE: task-oriented, copy-paste, zero prose
* Root `README.md` stays human-first and does not require AFAD frontmatter

## 6.5 Prohibited Actions
The AI agent MUST NOT:

* Create or modify markdown files without loading the protocol
* Violate schema requirements (missing Signature, missing Constraints)
* Add prose to Parameters tables (fragments only, ≤10 words)
* Add full API signatures to auxiliary docs (belongs in `DOC_*.md`)
* Duplicate content across files (consolidation required)
* Use filler phrases ("It is important to note...", "As mentioned earlier...")
* Create entries >600 tokens (split into atoms)

## 6.6 Protocol Loading Requirement
**This is a BLOCKING requirement.** If instructed to create or modify any `*.md` file:

```
LOAD .codex/PROTOCOL_AFAD.md
APPLY tier-appropriate AFAD 4.0 rules (reference-doc or auxiliary-doc path as applicable)
VALIDATE per AFAD 4.0 validation rules (L0-L2 blocking, L3 advisory)
```

Failure to load and comply with the governing protocol is a system failure.

# 7. VERSION DOCUMENTATION POLICY

## 7.1 Single Source of Truth
**CHANGELOG.md is the authoritative record of version history.**
Version change documentation MUST NOT be duplicated in source code comments, docstrings, or
test documentation.

## 7.2 Prohibited Patterns in Source Code
**PROHIBITED** in `src/`, `tests/`, and `examples/`:
* `# v0.X.0: Feature added` — Version provenance comments
* `(TICKET-001 fix)` — Ticket reference annotations
* `As of v0.X.0` or `Since v0.X.0` — Behavioral version notes in docstrings
* `Updated in v0.X.0` — Change markers in comments

**PERMITTED** locations for version information:
* `__version__` in `__init__.py`
* `version` field in `pyproject.toml`
* `version:` in YAML frontmatter
* `- Version: Added in v0.X.0.` in `docs/DOC_*.md` reference documentation only

**NOTE on MIGRATION.md**: This document is for **fluent.runtime → FTLLexEngine** migration
(external library), NOT for FTLLexEngine version-to-version upgrades. Version upgrade guidance
belongs in CHANGELOG.md.

## 7.3 Test Documentation Standard
Test docstrings describe **WHAT** is tested, not **WHEN** it changed:
```python
# PROHIBITED
"""v0.39.0: Pound symbol is now ambiguous (GBP, EGP, GIP)."""

# REQUIRED
"""Pound symbol requires locale-aware resolution (ambiguous: GBP, EGP, GIP)."""
```

## 7.4 Reference Documentation Exception
Per §6.3 above, inline version metadata is permitted ONLY in `docs/DOC_*.md` files as part of
the Constraints section:
```markdown
- Version: Added in v0.31.0.
```
This is the single permitted location for inline version notes outside CHANGELOG.md.

## 7.5 Rationale
* **Maintenance Burden:** Version references scattered across 200+ locations require manual
  updates each release.
* **Duplication:** Same change documented in CHANGELOG.md and inline creates drift risk.
* **Staleness:** Old version numbers remain as historical noise.
* **Mixed Concerns:** Behavioral documentation entangled with change history obscures intent.

## 7.6 Enforcement
* New code MUST NOT introduce version provenance comments.
* Existing version references are grandfathered but SHOULD be removed when the code section is
  modified for other reasons.

# 8. INCIDENTAL OBSERVATION PROTOCOL

## 8.1 Passive Discovery Mandate
**Constraint:** While performing any task that involves reading source code, the AI agent
naturally forms assessments about code quality, defects, efficiency, and modernization
opportunities. These observations MUST be captured rather than discarded.

**Rationale:** The agent processes significant context during routine operations (file reads,
debugging, implementation). Optimization opportunities and defects noticed during this work
have value but are typically lost because no explicit directive exists to record them.

## 8.2 Observation Scope
Record observations that are optimization opportunities and defects to
`.codex/OBSERVATIONS_INCIDENTAL.txt`:

| Category | Examples |
|:---------|:---------|
| Performance | O(N) loop replaceable with O(1) lookup, unnecessary allocations |
| Modernization | Pre-PEP 695 patterns, deprecated stdlib usage |
| Simplification | Dead code paths, over-engineered abstractions |
| Memory | Cacheable computations, object pooling opportunities |
| Defects | Bugs, spec violations, security issues, API gaps |

## 8.3 Recording Protocol
**Location:** `.codex/OBSERVATIONS_INCIDENTAL.txt`

**When to Record:** Upon noticing an optimization opportunity or a defect during ANY file read
operation, append an entry. Do not interrupt the current task workflow — record concisely and
continue.

**Entry Format:**
```
------------------------------------------------------------------------
OBSERVED: <timestamp>
FILE: <path>:<line_range>
CATEGORY: PERF | MODERN | SIMPLIFY | MEMORY | DEFECT
OBSERVATION: <1-2 sentence description of what could be improved or fixed>
CURRENT: <brief code snippet or pattern description>
SUGGESTED: <brief description of improvement or fix approach>
EFFORT: TRIVIAL | MINOR | MODERATE
------------------------------------------------------------------------
```

**Field Definitions:**
* `EFFORT: TRIVIAL` — Single-line or mechanical change
* `EFFORT: MINOR` — Localized change, <20 lines affected
* `EFFORT: MODERATE` — Cross-function or requires careful testing

## 8.4 Non-Interruption Principle
Recording an observation MUST NOT:
* Interrupt the user's current task
* Trigger immediate remediation (unless user requests)
* Generate chat output announcing the observation
* Slow down the primary workflow

The file serves as a backlog for future optimization and defect sprints, not an action queue.

## 8.5 Deduplication
Before recording, check if an equivalent observation already exists. If so, do not add a
duplicate entry. Observations that have been promoted to `ISSUES-VALID.txt` should be removed
from `OBSERVATIONS_INCIDENTAL.txt`.
