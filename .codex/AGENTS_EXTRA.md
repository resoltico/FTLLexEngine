# FTLLexEngine Project Directives

# 1. ARCHITECTURAL PRIME DIRECTIVE

## 1.1 Library Identity

FTLLexEngine is the Python runtime for the **Fluent Template Language specification**, with **CLDR-backed locale-aware formatting** and **fail-fast boot validation with structured integrity evidence**. Every public symbol must arise from one of these three purposes. The library is not a general utilities collection, not a financial domain toolkit, not a concurrency framework — it is the i18n layer that production systems build directly on top of, and nothing else.

The primary use case is production systems where every locale resource must load cleanly, every message schema must match exactly, and every failure must produce named, traceable evidence — regulated deployments, audited backends, compliance-constrained services. This purpose drives every API design decision.

**Three Design Axioms:**

**Axiom 1 — Downstream Burden Elimination.**
Before adding any symbol to a public facade, ask: *what downstream composition does this replace?* Every public surface must eliminate a pattern that serious callers would otherwise implement themselves. `require_locale_code()` replaced per-caller trim/blank/length/normalize chains. `LocalizationBootConfig` replaced per-caller boot sequence assembly. `make_fluent_number()` replaced per-caller visible-precision inference. Primitives that serve only internal composition belong in submodules, not on `ftllexengine`, `ftllexengine.runtime`, or `ftllexengine.localization`.

**Axiom 2 — Fail-Fast at Boot, Structured Evidence at Runtime.**
Validate everything before accepting traffic. The canonical boot chain — `LocalizationBootConfig.boot()`, or `FluentLocalization` + `require_clean()` + `validate_message_schemas()` — raises `IntegrityCheckFailedError` if any resource fails to load cleanly or any schema mismatches. At runtime, formatting and parsing errors are returned as immutable structured evidence (`FrozenFluentError`, `LoadSummary`), while cache evidence flows through `CacheDebugLogEntry` and `CacheIntegrityEvent`. Silent degradation is prohibited; all failures are explicit.

**Axiom 3 — Explicit Failures, Immutable Evidence.**
Every failure produces a named, typed, immutable error object with structured context. `strict=True` is the default on `FluentBundle` and `FluentLocalization` — exceptions, not silent empty strings, are the correct response to integrity failures. `strict=False` is an explicit opt-in for soft-error return semantics where `format_pattern` returns a `(result, errors)` tuple. Cache evidence structures (`CacheDebugLogEntry`, `CacheIntegrityEvent`, `IntegrityContext`) carry dual timestamps (`timestamp_monotonic` for ordering, `wall_time_unix` for cross-system correlation) because compliance traces must be reproducible across restarts.

**API design review — apply before any new public surface:**

1. What downstream composition does this replace? (Axiom 1)
2. Does construction fail fast? Does runtime return immutable structured evidence? (Axiom 2)
3. Does it belong on a facade `__init__`, or is it an internal primitive? (§1.5)
4. Does it introduce any upward layer dependency? (§1.5)
5. Does it fall within one of the owned domains in §1.6 — FTL spec, CLDR locale formatting, compliance boot/audit, ISO 4217, or ISO 3166? Apply the full rejection test (§1.6) before answering yes.

## 1.2 Runtime Environment

General Python 3.13 posture (PEP 695 generics, `match/case` dispatch, free-threaded/JIT considerations, removed-module list, packaging discipline) is in `AGENTS_PYTHON313.md`. The project-specific additions are below.

* **Baseline:** Python 3.13 (current=3.14, next=3.15). Avoid 3.14+ syntax until the baseline is raised.
* **Dependencies:** Babel is the **sole permitted external dependency** and is **optional**. CLDR locale data is a curated international standard dataset that cannot be derived algorithmically; Babel is the canonical Python interface. All other functionality must be Standard Library only.
* **Two install modes:**
    * **Parser-only** (`pip install ftllexengine`): no external dependencies. Provides `parse_ftl`, `serialize_ftl`, AST manipulation, and validation.
    * **Full runtime** (`pip install ftllexengine[babel]`): includes Babel for `FluentBundle`, `FluentLocalization`, and `ftllexengine.parsing` modules.

## 1.3 Structural Mechanics

* **Immutability protocol.** State mutation creates hidden coupling and non-determinism. The system defaults to **immutable data structures** (`frozen=True` dataclasses, tuples) to enforce referential transparency. Mutation is permitted in exactly two bounded cases:
    1. **Performance-critical accumulation buffers:** isolated parse-buffer components where temporary accumulation is the direct implementation mechanism (e.g., parser's internal character/token accumulation).
    2. **Scoped context managers:** classes implementing `__enter__`/`__exit__` where tracked mutable state has deterministic enter/exit lifetime and no external visibility (e.g., `DepthGuard`).

* **Explicit control topology.** Implicit behavior and "magic" methods increase cognitive load and reduce auditability. Prefer explicit control flow and dependency injection over global state or `threading.local`. **`contextvars.ContextVar` is permitted** for task-scoped state in high-frequency primitive operations — it provides automatic async task isolation and does not share state between concurrent parse operations. Any `ContextVar` usage MUST be documented as an architectural decision per §3.6 and included in the Known Waiver Registry (§3.7).

* **Constants placement.** `constants.py` is for **cross-package configuration constants** (depth limits, cache sizes, input bounds). Module-local private constants (leading underscore) that are semantic to a single module belong IN that module, not in `constants.py`. Examples: Unicode escape lengths in parser primitives, indentation strings in serializer, cache tuning parameters in cache implementation. Implementation details stay with their implementation.

## 1.4 Specification Authority (Fluent)

The Fluent specification is the authoritative reference for runtime behavior. When agents or developers assume behavior that differs from the specification, the specification wins.

**Specification sources:**

* Primary: [Project Fluent Guide](https://projectfluent.org/fluent/guide/)
* Syntax: [Fluent Syntax 1.0](https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf)
* Validation: [valid.md](https://github.com/projectfluent/fluent/blob/master/spec/valid.md)
* Reference implementation: [Mozilla python-fluent](https://github.com/projectfluent/python-fluent)

**Common misunderstandings:**

| Assumption | Specification reality |
|:-----------|:----------------------|
| `{ $count }` should format locale-aware | Variables interpolate as-is via `str()` |
| `NUMBER($count)` is optional for numbers | `NUMBER()` is REQUIRED for locale-aware formatting |
| Implicit date formatting exists | `DATETIME()` is REQUIRED for locale-aware dates |
| Messages and terms share a namespace | Separate namespaces: `foo` and `-foo` can coexist |
| `NUMBER(style: "currency")` for currency | Use `CURRENCY()` function |
| `NUMBER(style: "percent")` for percent | No percent style; use `NUMBER()` + literal `%` |

The FTL parser is syntax-agnostic and accepts any named arguments; the grammar does not reject `NUMBER($x, style: "currency")`. The argument is silently ignored at runtime. Spec compliance is checked at runtime, not parse time.

**JavaScript Intl conflation.** Agents trained on `Intl.NumberFormat` patterns frequently assume FTLLexEngine uses the same single-constructor + `style` parameter idiom. It does not — Fluent uses **separate functions** per formatting type.

| JavaScript Intl pattern | FTLLexEngine equivalent |
|:------------------------|:------------------------|
| `Intl.NumberFormat(locale, {style: 'currency', currency: 'EUR'})` | `CURRENCY($val, currency: "EUR")` |
| `Intl.NumberFormat(locale, {style: 'percent'})` | Not supported; `NUMBER()` + literal `%` |
| `Intl.NumberFormat(locale, {style: 'decimal'})` | `NUMBER($val)` (default behavior) |
| `Intl.DateTimeFormat(locale, {year: 'numeric', month: 'long'})` | `DATETIME($val, dateStyle: "long")` |

**Before flagging runtime behavior as incorrect:**

1. Verify against the Fluent specification.
2. Check Mozilla python-fluent reference implementation.
3. Spec match → not a bug, even if counterintuitive.
4. Spec divergence → valid issue; proceed with filing.
5. Never assume JavaScript API patterns apply; verify function signatures against `docs/DOC_04_Runtime.md`.

## 1.5 Layer Architecture and Facade Contract

### 1.5.1 Layer graph (architectural law)

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

**Upward dependencies are structural violations, not style issues.** A module in layer N must not import from layer M > N. Violations must be fixed by **moving the symbol to the correct layer**, not by hiding the import in a function body.

**Detection pattern:** when layer N needs a symbol from layer M > N, ask: "Does this symbol conceptually belong in layer ≤ N?" If yes, move it. The 0.154.0 `FluentNumber` relocation (`runtime.value_types` → `core.value_types`) is the canonical example — it was a violation because `parsing` needed `FluentNumber` to implement `parse_fluent_number()`, but `parsing` cannot import from `runtime`.

### 1.5.2 Public facade contract

The three public facades are permanent API contracts. A symbol on a facade cannot be removed or renamed without a `CHANGELOG.md` `### Breaking Changes` entry.

| Facade | Import path | Scope |
|:-------|:------------|:------|
| Root | `ftllexengine` | All end-user entry points |
| Runtime | `ftllexengine.runtime` | FluentBundle, AsyncFluentBundle, FluentNumber, FunctionRegistry |
| Localization | `ftllexengine.localization` | FluentLocalization, LocalizationBootConfig, loader types |

**Submodule paths** (`ftllexengine.runtime.bundle`, `ftllexengine.core.value_types`) are internal navigation paths, not contracted surfaces. They may be reorganized without breaking the public contract provided facade re-exports are maintained.

**Export hygiene:** every symbol in a facade `__init__.py` must have an explicit `__all__` entry. Implicit reachability via attribute traversal does not constitute a public contract.

**Prohibited facade additions:** symbols that exist only to expose implementation details (internal cache structures, private lock primitives, parser internals) must not be promoted to a facade even if callers request it. The facade is a curated surface, not a namespace dump.

## 1.6 Public Surface Scope Constraint

FTLLexEngine's public surface is bounded by **three owned domains plus two narrowly-named standards datasets**. Symbols outside these domains do not belong on any public facade, regardless of technical merit or caller convenience.

**Owned domains (exhaustive — not a representative sample):**

| Domain | Bounded by | Examples of in-scope symbols |
|:-------|:-----------|:-----------------------------|
| **FTL specification** | Fluent 1.0 EBNF and valid.md | `parse_ftl`, `serialize_ftl`, `validate_resource`, AST nodes, FTL built-in functions |
| **CLDR-backed locale formatting** | Babel + Unicode CLDR | `FluentBundle`, `FluentNumber`, `LocaleCode`, `normalize_locale`, CLDR lookups |
| **Compliance-grade boot and audit** | The FTL/locale pipeline only | `LocalizationBootConfig`, `IntegrityContext`, `LoadSummary`, integrity exceptions arising from FTL resource loading |
| **ISO 4217 currency data** | The ISO 4217 standard as exposed by Babel/CLDR | `CurrencyCode`, `is_valid_currency_code`, `get_currency_decimal_digits` |
| **ISO 3166 territory data** | The ISO 3166-1 alpha-2 standard as exposed by Babel/CLDR | `TerritoryCode`, `is_valid_territory_code`, `require_territory_code` |

The last two domains are **named standards with fixed scope** — not a generic "international standards" category. ISO 8601, IETF BCP-47 extensions, and ITU-T E.164 are NOT automatically in scope; they would require explicit promotion of the table above.

**Mechanical rejection test — all three must be YES:**

1. Does this symbol address a failure mode or composition burden that arises specifically from the FTL spec, CLDR locale formatting, or the boot/audit pipeline — and not from general programming?
2. Would this symbol need to exist in a library that exclusively implements FTL parsing, CLDR-backed locale formatting, and fail-fast boot validation — with no knowledge of the caller's domain (financial, medical, logistics, etc.)?
3. Is this symbol's definition or behavior meaningfully coupled to FTL, CLDR, or the boot pipeline — or could it exist without modification in an unrelated Python library?

A symbol that fails any one is OUT OF SCOPE for the public facade. It may exist internally if the implementation requires it, but must not appear in `__all__` of any facade module.

**Bootstrapping trap:** defining a new type (e.g., `PhoneNumber`) does not automatically make a corresponding validator (`require_phone_number`) in-scope. Question 2 applies to the type itself: would a pure FTL/CLDR/boot library need `PhoneNumber`? If not, neither the type nor its validator belongs on a public facade.

**Explicitly out-of-scope categories:**

* **Generic type validators** (`require_int`, `require_non_negative_int`, `require_non_empty_str`, `coerce_tuple`): every Python program needs integer and string validation. A stripped FTL/CLDR/boot library would not. Validators are in-scope only when the validated type is intrinsic to FTL, CLDR, or boot (e.g., `require_fluent_number` — `FluentNumber` cannot exist outside this library; `require_locale_code` — locale canonicalization is required by the CLDR pipeline).
* **Fiscal calendar** (`FiscalCalendar`, `FiscalDelta`, `FiscalPeriod`, `MonthEndPolicy`, `fiscal_year`, `fiscal_quarter`, etc.): pure date arithmetic with no CLDR/Babel/FTL coupling. Not an ISO standard. Would exist unmodified in any financial or accounting library.
* **Accounting/ledger domain** (`LedgerInvariantError`, invariant codes such as `BALANCE`, `DUPLICATE_ACCOUNT`, `PERIOD_OVERLAP`): financial ledger semantics are the caller's domain.
* **Storage and persistence domain** (`PersistenceIntegrityError`): resource *loading* into the FTL pipeline is in-scope (`ResourceLoader`, `PathResourceLoader`); storage layer failures below that boundary are the caller's concern.
* **General concurrency primitives** (`RWLock`, `InterpreterPool`): concurrency is an implementation detail of the runtime layer, not a contract. `InterpreterPool` is a general PEP 734 pool with no FTL semantics.
* **Internal resolver machinery** (`FluentResolver`, `ResolutionContext`): the extension API is `FunctionRegistry` + `fluent_function`. Callers do not instantiate resolvers.

**Scope creep detection.** The test is not "does this help callers?" — everything helpful passes that test. The test is: would a library stripped to only FTL parsing + CLDR formatting + boot validation still need this symbol? If not, it does not belong. "Could use" adds surface; "the pipeline requires" eliminates downstream burden. Only the latter justifies promotion.

---

# 2. CODE & OUTPUT CONSTRAINTS

`AGENTS.md` §7.10 already prohibits emojis in code, comments, and documentation. The additions below are project-specific.

## 2.1 Status & Logging Indicators

Use only standardized ASCII indicators for logging and CLI output.

| Status | Indicator | Rationale |
|:-------|:----------|:----------|
| **Success** | `[OK]`, `[PASS]` | Unambiguous status reporting |
| **Failure** | `[FAIL]`, `[ERROR]` | High-priority failure flag |
| **Warning** | `[WARN]` | Deprecation or non-critical state alert |

**Test data exception (the only one):** emojis are permitted *only* inside test fixture data when validating Unicode/FTL specification handling (e.g., `parse_ftl("greeting = 👋")`). They are never permitted in source code, comments, docstrings, commit messages, or non-fixture test code.

## 2.2 Documentation Style

* **Docstrings:** all public modules, classes, and functions must have concise docstrings.
* **Style:** Google-style docstrings (matches existing code; consistency over preference).
* **Typing:** do not duplicate type information in docstrings; type hints are the contract.

## 2.3 Self-Containment Principle

Source code, tests, and user-facing documentation must remain **self-contained**. They must NEVER reference AI-agent-only directives or the `.codex/` protocol stack. Human developers must understand design decisions without consulting agent protocols.

* **Prohibited:** comments, docstrings, error messages, or user-facing docs that reference `AGENTS.md`, `CLAUDE.md`, files in `.codex/` / `.claude/` / `.gemini/`, "Section X.Y" of an internal protocol, or "per the agent contract."
* **Required:** architectural justifications must stand alone — readable by a human developer who has never seen the protocol stack.

```python
# PROHIBITED
# Violates AGENTS_EXTRA.md §1.3 explicit control topology.

# REQUIRED
# Task-local ContextVar for performance: primitive functions are called 100+ times per
# parse, and explicit context threading would require ~10 signature changes and 200+
# call site updates.
```

**Scope:** all files in `src/`, `tests/`, `examples/`, `CHANGELOG.md`, and user-facing markdown. The protocol stack itself (`AGENTS.md`, `.codex/`, `.claude/`, `.gemini/`) is exempt — it can and must reference itself.

---

# 3. QUALITY HIERARCHY & WAIVERS

Distinct quality configurations apply by directory scope. Respect the configuration files associated with each.

## 3.1 Core Production Code (`src/`): STRICT

* **Quality target:** all linters exit 0. Ruff (zero errors), Mypy (`strict = true`). See §5.7 for execution order.
* **Ruff:** `select = ["ALL"]` with focused `ignore` list in `pyproject.toml` (D, ANN, COM812, ISC001, framework families). New rules apply automatically; explicit `ignore` or per-file-ignores required for any suppression.
* **Mypy:** `strict = true`. No unchecked types; full annotation coverage required.
* **Waivers:** only architectural waivers (§3.6). Never permit waivers for logic bugs, security issues, performance flaws, or dead code.

## 3.2 Verification Test Code (`tests/`): PRAGMATIC

* **Quality target:** Ruff zero errors, Mypy pragmatic.
* **Configuration:** `pyproject.toml` (Ruff per-directory overrides), `tests/mypy.ini` (Mypy).
* **Allowed waivers:**
    * `N802` — FTL specification mimicry (e.g., `UPPERCASE_functions`).
    * `SLF001` — integration tests verifying internal object state.
    * `E402`, `PLC0415` — Hypothesis strategy isolation.

## 3.3 Example Code (`examples/`): DEMONSTRATIVE

* **Configuration:** `examples/mypy.ini`.
* Inline configuration is preferred — examples document linting practice for users.

## 3.4 Operational Fuzzing Code (`fuzz_atheris/`): OPERATIONAL

* **Quality target:** Ruff zero errors, Mypy operational (`fuzz_atheris/mypy.ini`).
* **Configuration:** `pyproject.toml` overrides + `fuzz_atheris/mypy.ini`.
* **Allowed waivers:**
    * `PLR0912`, `PLR0915` — pattern handler functions in fuzz modules MUST use dispatch-to-sub-handlers (§4.3) rather than monolithic if/elif chains. Sub-handler functions are individually simple; the dispatcher itself is a one-liner index into a tuple of callables. Do not suppress PLR0912 on a monolithic function — refactor it.
    * `S101` — `assert` is permitted for invariant checks inside fuzz patterns.
* **Pattern architecture:** each `_pattern_*` function dispatches to a tuple of `_check_*` sub-handlers; each sub-handler tests one behavioral scenario. Mirrors §4.3.

## 3.5 Clean Breaks, No Debt

This project takes a stricter stance than `AGENTS.md` §7.4 baseline: **no migration paths, no transitional shims, no deprecation cycles.** Old APIs are deleted, not deprecated. Users adapt to the current API. `CHANGELOG.md` is the single authoritative version ledger.

**Prohibited:**

* `# TODO: refactor later`, `# FIXME`, "fix in next version", "known issue" — fix now or not at all.
* Backwards-compatibility shims, transitional APIs, parallel-maintained old APIs — make clean breaks; remove deprecated code entirely.
* Suppression as fix — `# noqa`, `# type: ignore`, `per-file-ignores` are reserved for permanent architectural patterns documented in §3.7. They are never a way to defer remediation.
* Version provenance in `src/`, `tests/`, `examples/` — no `# v0.X.0: feature added`, no "As of v0.X.0", no "Since v0.X.0", no "Updated in v0.X.0", no `(TICKET-001 fix)` annotations. Test docstrings describe **WHAT** is tested, not **WHEN** it changed:

```python
# PROHIBITED
"""v0.39.0: Pound symbol is now ambiguous (GBP, EGP, GIP)."""

# REQUIRED
"""Pound symbol requires locale-aware resolution (ambiguous: GBP, EGP, GIP)."""
```

**Permitted version locations (exhaustive):**

* `__version__` in `__init__.py`
* `version` field in `pyproject.toml`
* `version:` in YAML frontmatter
* `- Version: Added in v0.X.0.` in `docs/DOC_*.md` Constraints sections only

**Rationale.** Deferred fixes accumulate interest: a "small" workaround today becomes an architectural constraint tomorrow. Version references scattered across 200+ locations require manual updates each release; duplication creates drift; old version numbers remain as historical noise. The cost of immediate remediation is always lower than the cost of accumulated debt.

## 3.6 Waiver Implementation Protocol

Waivers are for **permanent architectural necessities**, never for deferring fixes.

1. **Fix first.** Attempt remediation before waivering. Waivers are a last resort.
2. **Permanence.** A waiver must address a permanent constraint (e.g., Visitor pattern naming), not a temporary inconvenience.
3. **Scope.** Use `per-file-ignores` for patterns that apply uniformly to a file or directory; use inline `# noqa` for isolated single-line exceptions in otherwise conformant files.
4. **Documentation.** Every waiver must carry a concise, high-value comment justifying the *permanent architectural necessity*.

**Prohibited justifications:** "will fix later", "not enough time", "too complex to refactor". Time is not an accepted constraint; correctness is.

## 3.7 Design Principle Hierarchy (Waiver Recognition)

Documented architectural waivers OVERRIDE general principles stated in this document or in `AGENTS_PYTHON313.md`. Distinguish carefully:

| Category | Definition | Action |
|:---------|:-----------|:-------|
| **Principle** | Default mode of operation stated in this file or the `.codex/` stack | Apply unless waiver documented |
| **Waiver** | Documented exception with trade-off rationale | Respect; do NOT flag as violation |
| **Violation** | Undocumented deviation without justification | Flag for remediation |

**Waiver recognition signals** — a design decision is a documented waiver if any of these are present:

* Module docstring explains the trade-off.
* Inline comment includes "intentional", "trade-off", "architectural", "design decision".
* Suppression comment provides rationale (e.g., `# noqa: PLC0415 - circular import`).
* Comment explicitly states "permanent" or "accepted".

**Example: task-local ContextVar vs explicit control (§1.3).**

§1.3 states: "prefer explicit control flow... over global state or `threading.local`." `primitives.py` uses `contextvars.ContextVar` task-local state (NOT `threading.local`) with documented justification:

```
# Task-Local State (Architectural Decision):
# - Primitive functions called 100+ times per parse operation
# - Explicit context threading would require ~10 signature changes
# - ContextVar.get()/set() is O(1) with automatic async task isolation
# This is a permanent architectural pattern...
```

This is a WAIVER, not a violation. The documentation (1) acknowledges the relaxed principle, (2) provides quantitative justification, (3) explicitly marks it permanent.

**Violation detection.** An issue is a true violation only if:

1. Behavior contradicts a stated principle (e.g., uses `threading.local` or module-global mutable state).
2. No documentation in the module docstring or enclosing function/class scope justifies the deviation.
3. No suppression comment provides rationale.

**Before flagging any apparent principle violation:** read the module docstring, search the enclosing scope for waiver documentation, consult the registry below. If documented: not a violation. If undocumented: file the issue.

### Known Waiver Registry

All architectural waivers in `src/`. Each entry is a documented, permanent decision — not a deferral.

| Module | Suppressed rule(s) | Principle relaxed | Permanent justification |
|:-------|:-------------------|:------------------|:------------------------|
| `syntax/parser/primitives.py` | §1.3 explicit control | §1.3 explicit control topology | `ContextVar` task-local state; 100+ calls/parse; threading via ContextVar gives automatic async isolation with O(1) overhead |
| `core/depth_guard.py` | §1.3 immutability | §1.3 immutability protocol | Mutable `current_depth` counter required by context-manager `__enter__`/`__exit__`; state strictly scoped to each `with` block |
| `core/babel_compat.py` | PLW0603, F401, PLC0415 | §1.3 explicit control (global singleton) | `_babel_available` is a module-level sentinel computed once at first call; `global` is the only stdlib mechanism for a mutable module-level singleton without a class |
| `syntax/parser/core.py`, `rules.py` | PLR0911, PLR0912, PLR0915 | §4.3 dispatch complexity | EBNF grammar rule dispatch: one function = one grammar rule; branching is structural, not accidental |
| `syntax/serializer.py` | PLR0912 | §4.3 dispatch complexity | Classification-dispatch model (§4.6): `_serialize_pattern`, `_emit_classified_line`, `_serialize_expression` branches are exhaustive over closed grammar types |
| `syntax/visitor.py` | ERA001, PLR0911, PLR0912 | §4.3 dispatch complexity | Visitor dispatch + docstring examples (`ERA001`); branching from closed AST node set |
| `runtime/resolver.py` | PLR0911, type:ignore[unreachable] | §4.3 dispatch complexity | `_resolve_expression`, `_get_fallback_for_placeable`: closed `Expression` union, one return per variant; `type:ignore[unreachable]` on `_get_fallback_for_placeable` `case _:` — union is statically exhaustive but wildcard is retained as safety net for the error-recovery contract (must always return a string, never raise) |
| `runtime/cache.py` | PLR0911, PLR0912 | §4.3 dispatch complexity | `_make_hashable`: type dispatch over heterogeneous Python values; each branch handles a distinct Python type |
| `introspection/message.py` | N802, RUF022 | §4.1 visitor naming | `visit_NodeName` follows stdlib `ast.NodeVisitor` convention; `__all__` organized by category for public/internal clarity |
| `runtime/bundle.py` | PLR0912, E501 | §4.3 dispatch complexity | Resource registration and validation coordination; long lines in structured logging messages |
| `parsing/currency.py` | PLR0911, PLR0912 | §4.3 dispatch complexity | Ambiguous currency symbol disambiguation requires exhaustive symbol/territory resolution |
| `parsing/dates.py` | DTZ007 | Naive datetime | Library does not impose timezone; caller provides timezone-aware values or explicitly opts into naive datetime |
| `runtime/locale_context.py` | DTZ001 | Naive datetime | `format_datetime` promotes a plain `date` to midnight `datetime` with no tzinfo; the date carried no timezone, so none is inferred — correct semantics for a calendar date with no intrinsic time |
| `syntax/parser/whitespace.py` | SIM102 | Style | Nested `if` guards cursor state and EOF simultaneously; merging the conditions hides the state-machine intent |
| `syntax/validator.py` | EM102 | Style | `TypeError` f-string messages: violation type includes dynamic type; static string would omit it |
| Babel-optional modules (`parsing/`, `runtime/`, `introspection/`, `core/`) | PLC0415 | §4.2 runtime imports | Babel is optional; imports inside functions are the only way to make them lazy (avoids `ImportError` at module load for parser-only installs) |
| `diagnostics/formatter.py`, `diagnostics/validation.py` | PLC0415 | §4.2 runtime imports | Mutual runtime circular: `ValidationError`/`ValidationWarning` require runtime `isinstance` in formatter; `DiagnosticFormatter` is instantiated at runtime in validation factory. Neither is type-only |
| `diagnostics/codes.py` | PLC0415 | §4.2 runtime imports | `Diagnostic.format()` instantiates `DiagnosticFormatter` at runtime; circular between codes and formatter |
| `validation/resource.py` | PLC0415 | §4.2 runtime imports | Resource validation triggers re-parse for annotation extraction; runtime circular between validation and syntax/parser layers |
| `runtime/resolution_context.py` | §1.3 immutability | §1.3 immutability protocol | `ResolutionContext` uses mutable `_stack`, `_seen`, `_total_chars`, `_expression_guard` for cycle detection and expansion tracking; §1.3 permits mutable accumulation buffers in performance-critical operations; isolation is guaranteed by creating a fresh instance per resolution call |
| `runtime/function_bridge.py` | PLC0415 | §4.2 runtime imports | Function metadata loaded lazily on first call; runtime circular between bridge and function_metadata modules |
| `runtime/bundle.py` (PLC0415) | PLC0415 | §4.2 runtime imports | Bundle loads `analysis.graph.entry_dependency_set` and `introspection.extract_references` at runtime; circular between runtime and analysis/introspection layers |
| `core/__init__.py` | PLC0415, module `__getattr__` | §1.3 immutability | Lazy-loads `DepthGuard`/`depth_clamp` via module `__getattr__` to break circular import: `depth_guard` → `diagnostics` → `syntax.__init__` → `serializer` → `core.depth_guard`. Eager import during `ftllexengine` package init would deadlock the import chain. `globals()` mutation in `__getattr__` is a permanent, accepted stdlib pattern for module-level lazy singletons |
| `parsing/guards.py` | TC003 | §4.2 TYPE_CHECKING | `date`, `datetime`, `Decimal` cannot be moved under TYPE_CHECKING: `typing.get_type_hints()` evaluates TypeIs annotation strings at runtime and requires these names in module globals; moving them causes `NameError` in callers using `get_type_hints()` |
| `syntax/ast.py` | TC001 | §4.2 TYPE_CHECKING | `CommentType` is a public re-exported symbol; consumers do `from ftllexengine.syntax.ast import CommentType` at runtime; moving under TYPE_CHECKING would break this import |
| `localization/boot.py` | §1.3 immutability (`object.__setattr__`) | §1.3 immutability protocol | `_booted` guard requires a single post-init mutation (False→True) on a frozen dataclass. `object.__setattr__` bypasses the generated `__setattr__` — the same mechanism Python's frozen dataclass `__init__` uses. Config fields remain permanently immutable; only the one-shot guard transitions, once, permanently |

---

# 4. DESIGN PATTERNS & LINT INTEGRATION

## 4.1 Visitor Pattern

* Follow the standard library's `ast.NodeVisitor` convention for AST traversal.
* Suppress `N802` (function name snake_case) for dispatch methods like `visit_Message` to match node class names.

## 4.2 Runtime Imports (Circular Dependency Avoidance)

Two distinct patterns, applied in priority order:

1. **`TYPE_CHECKING` guard (preferred for type-only imports).** When a circular dependency exists only because a type annotation references the other module, wrap the import under `TYPE_CHECKING`. No `PLC0415` suppression is required (the import is still top-level); the import is elided at runtime.
   ```python
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from ftllexengine.introspection import MessageIntrospection
   ```
2. **Function-local import (runtime circular dependency).** Use only when the import is needed at runtime (not just for annotations). Requires `PLC0415` suppression with rationale.
   ```python
   def _resolve(self) -> ...:
       from ftllexengine.runtime.cache import IntegrityCache  # noqa: PLC0415 - runtime circular
       ...
   ```

`TYPE_CHECKING` is always preferred. New `PLC0415` suppressions require explicit justification proving `TYPE_CHECKING` is insufficient.

## 4.3 Complex Dispatch Logic

Grammar-derived or specification-driven dispatch logic has inherently high branching complexity. Suppress `PLR0912` (too many branches) and `PLR0915` (too many statements) for:

* the main parser loop (`syntax/parser/core.py`) — EBNF grammar rule dispatch.
* serializer classification-dispatch methods (`syntax/serializer.py`: `_serialize_pattern`, `_emit_classified_line`) — documented in §4.6.

**Fuzz pattern handlers.** `_pattern_*` functions in `fuzz_atheris/` that cover many behavioral scenarios MUST use dispatch-to-sub-handlers rather than a single if/elif chain. The top-level handler selects a sub-handler via an integer index into a tuple; each sub-handler is a standalone function covering one scenario. Do NOT suppress PLR0912 on a monolithic function — refactor it.

## 4.4 Type Narrowing (Union Types)

Never access attributes of a Union type without prior runtime validation. Use explicit `isinstance()` checks or `match/case` to narrow before accessing specific attributes.

```python
from ftllexengine.syntax.ast import Message, Term

def get_entry_id(entry: Message | Term) -> str:
    match entry:
        case Message(id=identifier):
            return identifier.name
        case Term(id=identifier):
            return identifier.name
        case _:
            raise TypeError(f"Unexpected entry type: {type(entry)}")
```

## 4.5 Facade Layer

The facade layer realizes the platform axioms from §1.1. All three facade classes coordinate subsystems; none implement the logic they coordinate. The dependency graph is **unidirectional** — delegate modules MUST NOT import any facade class.

### 4.5.1 FluentBundle — single-locale formatting unit

`FluentBundle` owns a single locale and a set of parsed FTL resources.

| Responsibility | Delegate | FluentBundle role |
|:---------------|:---------|:------------------|
| Parsing | `syntax.parser.FluentParserV1` | Calls `parse()`, registers results |
| Resolution | `runtime.resolver.FluentResolver` | Instantiates, calls `resolve_message()` |
| Validation | `validation.validate_resource()` | Single-line delegation |
| Introspection | `introspection.extract_variables()`, `introspect_message()` | Single-line delegation |
| Caching | `runtime.cache.IntegrityCache` | Holds reference, calls `get()`/`put()` |

FluentBundle's high docstring-to-code ratio is expected — it is the primary public API facade. High docstring ratio is not debt.

### 4.5.2 FluentLocalization — multi-locale coordinator

`FluentLocalization` coordinates locale-scoped `FluentBundle` instances and implements the fallback chain. Bundle creation is **lazy** — first `format_pattern` call for a given locale.

| Responsibility | Delegate | FluentLocalization role |
|:---------------|:---------|:------------------------|
| Resource loading | `ResourceLoader` protocol | Calls `loader.load(locale, resource_id)` |
| Bundle management | `FluentBundle` | Creates on demand, holds in `_bundles` dict |
| Fallback resolution | Locale chain | Iterates locale list until format succeeds |
| Boot validation | `require_clean()`, `validate_message_schemas()` | Provides pre-traffic validation API |
| Cache debug log | `FluentBundle.get_cache_debug_log()` | Aggregates per-locale debug logs into dict |

### 4.5.3 LocalizationBootConfig — strict-mode boot orchestrator

`LocalizationBootConfig` is a one-shot boot coordinator, not a persistent object. It composes `FluentLocalization`, `require_clean()`, and `validate_message_schemas()` into a single audited boot sequence and discards itself after `boot()` returns the live `FluentLocalization`.

* `boot()` → `(FluentLocalization, LoadSummary, tuple[MessageVariableValidationResult, ...])`: PRIMARY API; executes full boot sequence and returns structured evidence; raises `IntegrityCheckFailedError` on any load failure, required-message absence, or schema mismatch.
* `boot_simple()` → `FluentLocalization`: simplified form; raises on failure but discards audit evidence; use when structured evidence is not required.
* The `LocalizationBootConfig` instance has no role after `boot()` completes. It is not thread-safe to share across calls.

**Prohibited refactorings (all three facades):**

* Extracting facade methods into mixins — creates hidden C3 linearization complexity.
* Creating "Service" wrappers around single-line delegation methods — adds indirection, zero benefit.
* Lifting delegate module internals to the facade — violates the unidirectional dependency graph.

## 4.6 Serializer Architecture (FluentSerializer)

The serializer is a deterministic AST-to-FTL compiler. Three concern layers, classify-then-dispatch model for continuation lines.

### 4.6.1 Architectural layers

| Layer | Responsibility | Methods |
|:------|:---------------|:--------|
| **Validation** | AST structural correctness (separate pass, runs first) | `_validate_resource`, `_validate_expression`, `_validate_pattern`, `_validate_call_arguments`, `_validate_identifier`, `_validate_select_expression` |
| **Node serialization** | AST node dispatch via `match/case` | `_serialize_entry`, `_serialize_message`, `_serialize_term`, `_serialize_attribute`, `_serialize_comment`, `_serialize_junk`, `_serialize_expression`, `_serialize_call_arguments`, `_serialize_select_expression` |
| **Pattern emission** | Continuation line classification, whitespace preservation, character escaping | `_serialize_pattern`, `_classify_line`, `_escape_text` |

Validation runs BEFORE serialization. Serialization assumes validated input. These layers MUST NOT be merged.

### 4.6.2 Continuation line model

The FTL parser interprets continuation lines structurally: leading whitespace is syntactic indent, blank lines are stripped, and characters `.`, `*`, `[` as the first non-whitespace trigger attribute/variant parsing. The serializer MUST ensure that content whitespace and content syntax characters are not misinterpreted as structural.

**Invariant:** every continuation line emitted by the serializer must be unambiguous under FTL parsing rules. Ambiguity is resolved by wrapping problematic content in `StringLiteral` placeables (`{ "..." }`), which the parser treats as expression content.

**Classification-before-dispatch.** Each continuation line is classified ONCE by a pure function, then handled through a single `match/case` dispatch:

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

**Prohibited:**

* Handling whitespace ambiguity classes outside the classification-dispatch model (no scattered `if` branches in multiple methods).
* Adding line-level concerns to `_escape_text` (it handles character-level brace escaping only).
* Modifying AST nodes to carry serializer-specific layout hints.
* Event/Layout/Emitter pipeline abstractions (overengineered for a finalized closed-grammar specification).

### 4.6.3 Separate-line mode

When a pattern contains cross-element whitespace dependencies (a `TextElement` starting with spaces follows a newline-ending element), the serializer outputs the pattern on a separate line from `=` to establish `initial_common_indent` before any semantic whitespace. This is a **pattern-level** decision, orthogonal to the per-line classification in §4.6.2.

`WHITESPACE_ONLY` and `SYNTAX_LEADING` lines are handled by per-line wrapping, NOT by separate-line mode. Only `NORMAL` lines with leading whitespace after a cross-element newline trigger separate-line mode.

### 4.6.4 Character-level escaping (`_escape_text`)

`_escape_text` handles ONLY brace escaping: `{` and `}` at any position are wrapped as `StringLiteral` placeables (per Fluent spec, braces in `TextElement` content must be expressed as `{ "{" }` and `{ "}" }`). All other ambiguity concerns are resolved BEFORE `_escape_text`:

* Syntax characters at line starts: `_emit_classified_line` (`SYNTAX_LEADING` branch).
* Whitespace-only lines: `_emit_classified_line` (`WHITESPACE_ONLY` branch).
* Newline detection and continuation boundaries: text is pre-split by `_serialize_pattern`.

### 4.6.5 Exhaustiveness

All `match/case` dispatches on closed union types (`Entry`, `Expression`, `_LineKind`) MUST be exhaustive. Use `assert_never()` from `typing` for enum dispatches and explicit `case _: raise TypeError(...)` for AST union dispatches where the union may grow.

## 4.7 Ruff Configuration

`select = ["ALL"]` in `[tool.ruff.lint]`. New rules apply automatically; explicit `ignore` or per-file-ignores required for any suppression.

### 4.7.1 Global `ignore` vs per-file-ignores

| Mechanism | Use when |
|:----------|:---------|
| Global `ignore` | Rule NEVER applies anywhere in the codebase (wrong framework, redundant with mypy strict, formatter territory) |
| Per-file-ignores | Rule is valid for most files but a specific file has a documented architectural reason for an exception |
| Per-directory blanket | Entire directory has a distinct quality standard (`tests/`, `examples/`, `fuzz_atheris/`, `scripts/`) |

Suppressing a rule globally because one file needs it is prohibited. One file's exception belongs in per-file-ignores.

### 4.7.2 TC001/TC003 (TYPE_CHECKING) — non-negotiable exceptions

Two import categories must NEVER be moved under `TYPE_CHECKING`, even when TC fires:

1. **TypeIs annotation types.** `typing.get_type_hints()` evaluates annotation strings at runtime in the module's `globals()`. If `date`, `datetime`, `Decimal` (or any type used in `-> TypeIs[X]`) are under `TYPE_CHECKING`, `get_type_hints()` raises `NameError` at runtime in callers.
   - Affected: `parsing/guards.py`.
   - Fix: keep as direct import; add `# noqa: TC003 - TypeIs return annotation requires X at runtime for get_type_hints() resolution`.
2. **Public re-exported symbols.** If callers do `from ftllexengine.syntax.ast import CommentType` at runtime, moving `CommentType` under `TYPE_CHECKING` breaks the import.
   - Affected: `syntax/ast.py`.
   - Fix: keep as direct import; add `# noqa: TC001 - re-exported as a public runtime symbol`.

Both are in the Known Waiver Registry (§3.7).

### 4.7.3 FBT001/FBT002 (boolean traps) — fix pattern

Ruff FBT flags boolean-typed positional parameters. **Preferred fix:** make the argument keyword-only with `*`.

```python
# BEFORE (FBT fires)
def get_patterns(locale: str, allow_expansion: bool = True) -> list[str]: ...

# AFTER
def get_patterns(locale: str, *, allow_expansion: bool = True) -> list[str]: ...
```

After making an arg keyword-only, check all call sites — mypy reports "too many positional arguments" for any missed site. For truly internal private functions, per-file-ignores with rationale is acceptable. Do not add FBT to the global ignore.

### 4.7.4 C901 (McCabe complexity) — waiver pattern

Grammar rules, AST visitor dispatch, and closed-union dispatch legitimately exceed McCabe. Add C901 alongside PLR0912 in per-file-ignores:

```toml
"src/ftllexengine/syntax/parser/rules.py" = ["PLR0911", "PLR0912", "PLR0915", "C901"]
```

Rationale template: *"Grammar/AST dispatch: one function = one grammar rule; cyclomatic complexity is structural, not accidental."*

---

# 5. VERIFICATION METHODOLOGY

## 5.1 Test File Naming Schema

Test file naming is a hard structural constraint, not a style preference. It determines discoverability: an agent searching for tests covering `runtime/bundle.py` must be able to predict the filename without scanning all 200+ test files.

**Canonical schema:** `test_{package}_{module}[_{qualifier}].py`

| Segment | Derived from | Examples |
|:--------|:-------------|:---------|
| `{package}` | `src/ftllexengine/` subpackage name | `runtime`, `syntax`, `parsing`, `diagnostics` |
| `{module}` | Module filename without `.py` | `bundle`, `resolver`, `serializer` |
| `{qualifier}` | Optional single axis (see permitted list) | `_property`, `_integration` |

For nested subpackages, join with underscore: `src/ftllexengine/syntax/parser/core.py` → `test_syntax_parser_core.py`.

For top-level modules (`src/ftllexengine/enums.py`), omit the package segment: `test_enums.py`.

**Permitted qualifiers (exhaustive):**

| Qualifier | Meaning | Runs in CI? |
|:----------|:--------|:------------|
| *(none)* | Primary unit/contract tests | Yes |
| `_property` | Hypothesis `@given` tests | Yes |
| `_integration` | Multi-component tests crossing module boundaries | Yes |
| `_roundtrip` | Serialization/parse identity verification | Yes |
| `_state_machine` | `RuleBasedStateMachine` tests (in `tests/fuzz/` only) | No |

No other qualifiers are permitted. If a file cannot be classified by one of these axes, it belongs in an existing file or signals that file should be split.

**Fuzz-marker location.** All tests carrying `@pytest.mark.fuzz` MUST reside in `tests/fuzz/`. The `tests/` root contains only tests that run in CI without the fuzz marker. A `_property` file in `tests/` root is NOT a fuzz file even if it uses `@given`; the marker and directory are what determine fuzz status (see §5.8).

**Deprecated suffixes — prohibited:**

| Deprecated | Canonical replacement |
|:-----------|:----------------------|
| `_hypothesis`, `_properties` | `_property` |
| `_fuzzing` | Move file to `tests/fuzz/` |
| `_comprehensive` | Split into focused files by axis |
| `_advanced`, `_edge_cases` | Not behavioral axes; fold into primary or property file |

**Files name systems under test, not motivations:**

```
PROHIBITED: test_system_quality_audit_fixes.py       (internal task reference)
PROHIBITED: test_diagnostics_and_runtime_behaviors.py  ("and" = two subjects)
PROHIBITED: test_cross_module_branch_coverage.py     (coverage technique, not subject)
PROHIBITED: test_bundle_advanced_hypothesis.py       (two deprecated qualifiers)

REQUIRED:   test_runtime_bundle_property.py
REQUIRED:   test_diagnostics_formatter_integration.py
REQUIRED:   test_runtime_resolver_property.py
```

"And" in a filename is a mandatory split signal: the file covers two subjects and must become two files. A filename that cannot map back to a single source module path is invalid.

## 5.2 Hypothesis-First Protocol

Property-based testing (Hypothesis) is the **primary** verification mechanism. Unit tests with fixed inputs are appropriate only for CLDR-mandated exact output values and `@example`-promoted Hypothesis failures (regression cases). All other verification uses Hypothesis.

**HypoFuzz symbiosis:** all Hypothesis tests are designed for coverage-guided fuzzing via HypoFuzz. Tests and strategies MUST emit semantic coverage signals via `hypothesis.event()` to guide the fuzzer toward interesting code paths.

## 5.3 Test Construction Strategy

Construct tests based on deep code analysis, not blind fuzzing.

### 5.3.1 Identify properties

Before writing code, identify mathematical properties of the component:

* **Roundtrip:** `decode(encode(x)) == x`
* **Idempotence:** `parse(parse(x).to_string()) == parse(x)`
* **Oracle:** compare behavior against ShadowBundle or reference implementation.
* **Metamorphic:** predictable relationships (e.g., `len(filter(xs)) <= len(xs)`).

### 5.3.2 Emit semantic coverage events (mandatory)

Every `@given` test — regardless of file or marker — MUST use `hypothesis.event()` to signal semantically interesting behaviors invisible to code coverage. HypoFuzz treats events as virtual branches and actively seeks inputs that produce new events. Preflight enforces this across all `@given` tests, not just fuzz-marked modules.

```python
from hypothesis import event, given
from tests.strategies.ftl import ftl_placeables

@given(placeable=ftl_placeables())
def test_placeable_serialization(placeable: Placeable) -> None:
    event(f"expr_type={type(placeable.expression).__name__}")

    result = serialize(placeable)
    parsed = parse(result)

    if parsed.errors:
        event(f"error={type(parsed.errors[0]).__name__}")

    assert parsed.ast == placeable
```

**Event taxonomy (use consistently):**

| Category | Format | Examples |
|:---------|:-------|:---------|
| Strategy choice | `strategy={variant}` | `strategy=placeable_variable`, `strategy=chaos_prefix_brace` |
| Domain classification | `{domain}={variant}` | `currency_decimals=2`, `territory_region=europe` |
| Boundary/depth | `boundary={name}`, `depth={n}` | `boundary=at_max_depth`, `depth=99` |
| Unicode category | `unicode={category}` | `unicode=emoji`, `unicode=cjk` |
| Property outcome | `outcome={result}` | `outcome=roundtrip_success`, `outcome=immutability_enforced` |
| Test parameter | `{param}={value}` | `thread_count=20`, `cache_size=50`, `reentry_depth=3` |
| State machine | `rule={name}`, `invariant={name}` | `rule=add_simple_message`, `invariant=cache_stats_consistent` |

**Strategy events vs test events:**

* **Strategy events** are emitted by strategy functions in `tests/strategies/`. They are tracked by `EXPECTED_EVENTS` in `tests/strategy_metrics.py` and drive strategy-level coverage metrics. Format: `strategy={family}_{variant}` or `{domain}={variant}`.
* **Test events** are emitted by individual `@given` test functions and `@rule`/`@invariant` methods. They guide HypoFuzz per-test but are NOT tracked by `EXPECTED_EVENTS`. Format: `{param}={value}`, `outcome={result}`, `rule={name}`.

When adding a new strategy, update `EXPECTED_EVENTS`. When adding test events, no metrics update is needed.

### 5.3.3 Strategy construction (soundness over exhaustion)

* Use `st.from_type()` and `st.builds()` to construct valid domain objects.
* Avoid: high-rejection-rate filters on loose primitives (e.g., `st.text().filter(is_valid_ftl)`). Low-rejection filters on constrained strategies are acceptable when they improve readability.
* Strategies MUST emit events when selecting between semantically distinct variants.

```python
@composite
def ftl_placeables(draw: st.DrawFn, max_depth: int = 2) -> Placeable:
    """Generate Placeable AST nodes.

    Events emitted:
    - strategy=placeable_{choice}: Type of expression generated
    """
    choice = draw(st.sampled_from(["variable", "function_ref", "term_ref"]))
    event(f"strategy=placeable_{choice}")
    # ... generation logic ...
```

### 5.3.4 Contextual awareness

Investigate how code is called. Define strategies that mirror real usage patterns (e.g., chunked buffer inputs vs. whole-string inputs).

### 5.3.5 Event verification

Verify event infrastructure coverage:

```bash
./scripts/fuzz_hypofuzz.sh --preflight
```

**Enforcement levels:**

1. **File-level:** every `@pytest.mark.fuzz` module MUST contain `event()` calls.
2. **Per-test (AST-based):** every `@given` test function across ALL test files (both `tests/` root and `tests/fuzz/`) MUST emit at least one semantic event. The preflight tool parses all test files via Python AST.
3. **Strategy file coverage:** every strategy file in `tests/strategies/` MUST emit `event()` calls. `__init__.py` is exempt as a pure re-export aggregator (enforced by `_STRATEGY_REEXPORT_FILES` in the preflight script). A strategy file with 0 events gives HypoFuzz zero semantic guidance — treated as an error, not a warning.
4. **Zero gaps:** preflight must report zero gaps at all three levels. Any gap → exit code 1.

**Scope limitation:** preflight validates `@given` tests only. `RuleBasedStateMachine` rules and invariants use `@rule`/`@invariant` (not `@given`), so their event coverage is verified manually.

### 5.3.6 Runtime strategy metrics

The runtime metrics system (`tests/strategy_metrics.py`) complements preflight's static analysis with dynamic event collection during test execution.

| Constant | Purpose |
|:---------|:--------|
| `EXPECTED_EVENTS` | Set of fully-expanded event strings expected from all strategies |
| `STRATEGY_CATEGORIES` | Maps event prefixes to human-readable strategy family names |
| `INTENDED_WEIGHTS` | Expected per-variant distribution within each strategy family |

**Metrics collected:** total events, per-strategy counts, weight skew (threshold: 0.15), coverage gaps, performance percentiles.

| Aspect | Preflight (`--preflight`) | Runtime (`--deep --metrics`) |
|:-------|:--------------------------|:-----------------------------|
| Method | Static AST analysis | Dynamic event collection |
| Question | "Does `event()` exist in code?" | "Which events fired? At what frequencies?" |
| Catches | Missing instrumentation | Dead code paths, weight skew |
| Speed | Instant | Requires full test run |

**Activation:**

```bash
./scripts/fuzz_hypofuzz.sh --deep --metrics
```

Environment: `STRATEGY_METRICS=1`, `STRATEGY_METRICS_LIVE=1`, `STRATEGY_METRICS_DETAILED=1`. Results saved to `.hypothesis/strategy_metrics.json`.

**Maintenance:** when adding a new event-emitting strategy in `tests/strategies/`, update all three constants in `tests/strategy_metrics.py`. Test-level events do not require metrics updates.

## 5.4 Feedback Loop (Regression Proofing)

* **Discovery:** when Hypothesis finds a failure, it caches the minimal failing example in `.hypothesis/examples/`.
* **Action:** investigate root cause. Distinguish a genuine bug from an incorrect test assumption.
* **Promotion:** for every non-trivial bug found, **promote the failing example** into the test suite using `@example(...)`.

```python
@example(ftl="edge-case = { $var")  # Promoted from Hypothesis finding
@given(ftl=ftl_simple_messages())
def test_roundtrip(ftl: str) -> None:
    ...
```

**Crash recording infrastructure.** When a Hypothesis test fails, the `conftest.py` crash-recording hook (`pytest_runtest_makereport`) automatically:

1. Generates a standalone `repro_crash_<hash>.py` reproduction script in `.hypothesis/crashes/`.
2. Saves JSON metadata (test ID, example args, error type, timestamp) alongside the script.
3. Creates portable crash files that persist independently of `.hypothesis/examples/` and survive database cleanup.

Use `./scripts/fuzz_hypofuzz.sh --repro` or run crash scripts directly for reproduction.

## 5.5 Database Persistence

The Hypothesis example database (`.hypothesis/examples/`) persists across fuzzing sessions. It stores failing examples and covering examples (inputs that trigger distinct code paths during `Phase.reuse`).

* **Phase.reuse:** replays stored examples FIRST, catching regressions immediately.
* **Example accumulation:** each `--deep` session discovers new covering examples and failures.
* **Shrink memory:** minimal failing examples preserved across runs.

Do NOT delete `.hypothesis/` between fuzzing sessions unless intentionally resetting the database. A 30-minute session today + 30-minute session tomorrow = 60 minutes of cumulative learning.

## 5.6 Hypothesis Profiles

Profiles are defined in `tests/conftest.py`.

| Profile | max_examples | deadline | Use case |
|:--------|:-------------|:---------|:---------|
| `dev` | 500 | 200ms | Local development |
| `ci` | 50 | 200ms | Fast CI feedback (reproducible) |
| `verbose` | 100 | 200ms | Debugging with progress output |
| `hypofuzz` | 10000 | None | Coverage-guided `--deep` runs |
| `stateful_fuzz` | 500 | None | State machine fuzzing |

* All profiles include `Phase.target` for targeted property exploration via `target()`.
* `ci` uses `derandomize=True` for reproducible builds and `print_blob=True` for failure reproduction.
* `hypofuzz` suppresses `HealthCheck.too_slow` and `HealthCheck.data_too_large` for intensive runs.
* `fuzz_hypofuzz.sh --deep` automatically sets `HYPOTHESIS_PROFILE=hypofuzz`.

## 5.7 Workflow Execution Order

The repository has one canonical full verification entry point: `./check.sh`.
Use it at the end of non-trivial work and whenever the change touches docs,
examples, scripts, packaging metadata, or release surfaces.

For focused iteration inside the code/test loop, use these narrower commands:

1. **Lint:** `./scripts/lint.sh`. Runs Ruff, mypy, the bare-`noqa` audit, and the explicit repository static validators. Must exit 0.
2. **Test:** `./scripts/test.sh`. Runs pytest + Hypothesis + coverage. The coverage threshold is read from `pyproject.toml`; do not duplicate percentages elsewhere. Must exit 0.
3. **Preflight:** `./scripts/fuzz_hypofuzz.sh --preflight`. AST-based event audit. Run whenever `tests/` or `tests/strategies/` files are modified. Runs in seconds (no test execution); zero cost to always run.

### Script output design (agent-native, log-on-fail)

`lint.sh` and `test.sh` are AI-agent-optimized with a **log-on-fail** design. Run them directly without output truncation:

```bash
./scripts/lint.sh
./scripts/test.sh
```

**NEVER pipe through `tail`, `head`, or any output limiter. NEVER append redirection operators (`2>&1`, `>`, `>>`).** Output is already appropriately sized:

* On success: emits only structured summary lines (`[PASS]`, JSON block). Already minimal — no truncation needed.
* On failure: captures the full diagnostic log, then dumps it all at once. This dump IS the analysis. Truncating it destroys the error context needed for diagnosis.

Limiting output (e.g., `| tail -100`) means on failure you see only the summary footer, missing the actual error details. Redirecting stderr (e.g., `2>&1`) loses the distinction between stdout and the Bash tool's inherent stderr capture. The scripts are designed so the agent never needs to re-run them to get more detail.

## 5.8 Fuzz Test Skip Designation

Intensive property tests excluded from normal runs use `@pytest.mark.fuzz` and a standardized skip reason.

### When to apply `@pytest.mark.fuzz`

The marker controls whether a test **runs at all** during `test.sh`. It is independent of `event()` calls (mandatory in ALL `@given` tests per §5.3.2) and independent of Hypothesis profiles (which control example counts when a test does run).

| Test category | Runs in CI? | Fuzz marker? | Example count |
|:--------------|:------------|:-------------|:--------------|
| Regular `@given` with `event()` | Yes | No | `ci`=50, `dev`=500 |
| Intensive fuzz-only | No (skipped) | `@pytest.mark.fuzz` | Only under `--deep` (10000) |

**Apply `@pytest.mark.fuzz` ONLY when** the test meets one or more of:

* **State machines** (`RuleBasedStateMachine`) that explore exponential state spaces.
* **Generators producing expensive objects** (deeply nested ASTs, large resources) where 50 examples would exceed CI time budgets.
* **Tests with `deadline=None`** that intentionally allow slow individual examples.
* **Tests requiring `suppress_health_check`** for `too_slow` or `data_too_large`.

**Hard placement rule:** any test that uses `deadline=None` or `suppress_health_check=[HealthCheck.too_slow]` MUST carry `@pytest.mark.fuzz` and reside in `tests/fuzz/`. These settings signal that the test is intentionally slow — running 50 such tests in CI would blow time budgets. Examples: boot-sequence tests that construct real loaders, state machines. Do NOT place `deadline=None` tests in `tests/` root even if they have bounded strategies.

**Never hardcode `max_examples` in `tests/fuzz/`.** Fuzz tests MUST NOT set `max_examples=N` in their `@settings` decorator. The `hypofuzz` profile controls exploration depth (10,000 for `--deep --metrics`, continuous for HypoFuzz). Hardcoding `max_examples` overrides the profile and artificially caps exploration — a `@settings(max_examples=20)` test runs only 20 examples even under the `hypofuzz` profile's 10,000 budget. The only meaningful settings for fuzz tests are `deadline=None`, `suppress_health_check`, and `stateful_step_count` (state machines only).

**Do NOT apply `@pytest.mark.fuzz`** to standard `@given` tests with bounded strategies and no deadline suppression. These run fast at 50 examples and benefit from CI regression coverage.

### Marker mechanics

* **Marker:** `@pytest.mark.fuzz` at class or module level (`pytestmark = pytest.mark.fuzz`).
* **Skip reason prefix:** all fuzz skips use the prefix `"FUZZ:"`. Canonical reason:
  ```
  FUZZ: run with ./scripts/fuzz_hypofuzz.sh --deep or pytest -m fuzz
  ```
* **Prefix requirement:** the `"FUZZ:"` prefix is a structural contract consumed by `conftest.py` and `test.sh` for skip categorization. Do not alter the prefix.
* **Skip breakdown reporting:** `test.sh` emits `skipped_fuzz` and `skipped_other` in the JSON summary. If `skipped_other > 0`, a `[WARN]` is emitted indicating non-fuzz tests were skipped and require investigation.
* **Prohibited variations:** `"SKIPPEDfuzz"`, `"SKIPPED fuzz"`, `"Fuzzing test"`, or any other ad-hoc skip reason. All fuzz skip reasons MUST use the `"FUZZ:"` prefix.

### HypoFuzz targeting rationale

`--deep` targets `tests/fuzz/` exclusively — NOT `tests/`. This is a deliberate concentration strategy:

| Target | Effect |
|:-------|:-------|
| `tests/fuzz/` (correct) | 4 workers concentrated on ~35 high-value, slow, open-ended targets |
| `tests/` (wrong) | 4 workers diluted across 1500+ tests, most of which are fast and bounded |

Pointing HypoFuzz at `tests/` wastes worker capacity on tests that already run fine under CI's 50-example budget. The fuzz directory exists precisely to give HypoFuzz a concentrated set of targets where unlimited exploration has the highest marginal value: state machines, pool concurrency, boot sequences, subinterpreters. When adding new fuzz targets, always place them in `tests/fuzz/`.

## 5.9 Targeted Fuzzing with `target()`

All profiles include `Phase.target`, so `target()` is active in every test run. Use it to guide Hypothesis toward inputs that maximize specific metrics:

```python
from hypothesis import given, settings, target

@settings(deadline=None)
@given(source=ftl_chaos_source())
def test_parser_recovery(source: str) -> None:
    result = parse(source)
    target(len([e for e in result.body if isinstance(e, Junk)]), label="junk_count")
```

`target()` accepts a numeric value and an optional label. Hypothesis actively seeks inputs that maximize the targeted metric — effective for hunting specific bug classes (deep nesting, large error counts, parser recovery stress).

---

# 6. INCIDENTAL OBSERVATIONS

This protocol is the project's concrete realization of `AGENTS.md` §7.3.

While reading source code for any task, the agent forms assessments about quality, defects, efficiency, and modernization opportunities. Capture them rather than discard them.

**Recording location:** `.codex/OBSERVATIONS_INCIDENTAL.txt` (created lazily on first use).

**What to record:** optimization opportunities (PERF, MEMORY, MODERN, SIMPLIFY) and defects (DEFECT — bugs, spec violations, security issues, API gaps).

**When to record:** upon noticing a real issue during any file read. Do not interrupt the current task workflow — record concisely and continue.

**Entry format:**

```
------------------------------------------------------------------------
OBSERVED: <timestamp>
FILE: <path>:<line_range>
CATEGORY: PERF | MODERN | SIMPLIFY | MEMORY | DEFECT
OBSERVATION: <1-2 sentence description>
CURRENT: <brief code snippet or pattern>
SUGGESTED: <brief description of fix>
EFFORT: TRIVIAL | MINOR | MODERATE
------------------------------------------------------------------------
```

* `TRIVIAL` — single-line or mechanical change.
* `MINOR` — localized change, <20 lines affected.
* `MODERATE` — cross-function or requires careful testing.

**Non-interruption.** Recording must NOT interrupt the user's task, trigger immediate remediation (unless requested), generate chat output announcing the observation, or slow the primary workflow. The file is a backlog for future sprints, not an action queue.

**Deduplication.** Check for an equivalent existing entry before recording. Observations promoted to `ISSUES-VALID.txt` should be removed from `OBSERVATIONS_INCIDENTAL.txt`.
