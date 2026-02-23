<!--
RETRIEVAL_HINTS:
  keywords: [changelog, release notes, version history, breaking changes, migration, what's new]
  answers: [what changed in version, breaking changes, release history, version changes]
-->
# Changelog

Notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.129.0] - 2026-02-23

### Changed (BREAKING)

- **`NumberLiteral.__post_init__` enforces raw/value invariant** (ARCH-NUMBERLITERAL-INVARIANT-001):
  - `NumberLiteral` carries `value: int | Decimal` (used by the resolver for plural-category
    matching) and `raw: str` (used by the serializer for output); no validation ensured these
    two fields were consistent; `NumberLiteral(value=Decimal("1.5"), raw="9.9")` silently
    passed construction, then serialized as `"9.9"` while matching plural rules for `1.5`
    — silent data corruption that could cause mismatched output in financial documents;
    additionally, `isinstance(True, int)` is `True` so `NumberLiteral(value=True, raw="1")`
    was silently accepted and stored a boolean as a numeric literal
  - Added `__post_init__` to `NumberLiteral` that: (1) rejects `bool` for `value` before
    the `isinstance(value, int)` check; (2) validates `raw` is parseable as an `int` (when
    `value` is `int`) or `Decimal` (when `value` is `Decimal`) — raises `ValueError` with
    message "not a valid number literal" on failure; (3) rejects non-finite `Decimal` raw
    strings such as `"Infinity"` or `"NaN"` — raises `ValueError` "not a finite number";
    (4) validates `parsed_raw == value` — raises `ValueError` "parses to X but value is Y"
    on divergence
  - Consequence: two defensive exception handlers that caught `InvalidOperation` for
    malformed `NumberLiteral.raw` in `_find_exact_variant` (resolver) and `_variant_key_to_string`
    (validator) are now unreachable dead code and have been removed; their removal eliminates
    silent masking of programmer errors in those code paths
  - Location: `syntax/ast.py`, `runtime/resolver.py`, `syntax/validator.py`,
    `tests/test_syntax_ast.py`, `tests/test_runtime_resolver_depth_cycles.py`,
    `tests/test_runtime_resolver_error_fallback.py`, `tests/test_runtime_resolver_selection.py`,
    `tests/test_syntax_validator.py`, `tests/test_syntax_parser_validator_branches.py`

- **`FiscalCalendar` date methods enforce `fiscal_year` 1–9999** (DEFECT-FISCALCALENDAR-YEAR-BOUNDS-001):
  - Follow-on to DEFECT-FISCALPERIOD-YEAR-BOUNDS-001 (v0.128.0); that fix added bounds
    validation to `FiscalPeriod.__post_init__`, but the four public date-returning methods
    `fiscal_year_start_date(fiscal_year)`, `fiscal_year_end_date(fiscal_year)`,
    `quarter_start_date(fiscal_year, quarter)`, and `quarter_end_date(fiscal_year, quarter)`
    take a bare `int` parameter with no bounds check; `cal.fiscal_year_start_date(0)` evaluates
    to `date(0 - 1, start_month, 1)` → `date(-1, ...)` → Python `ValueError: year -1 is out
    of range` with no attribution to the caller's invalid argument; callers going through these
    methods directly (not via `FiscalPeriod`) received a cryptic error with no indication that
    the `fiscal_year` argument was the problem
  - Added `if not 1 <= fiscal_year <= 9999: raise ValueError(f"fiscal_year must be 1-9999,
    got {fiscal_year}")` at the top of each of the four public date-returning methods;
    `_add_months()` now also validates `target_year` post-arithmetic and raises
    `ValueError(f"Result year {target_year} is out of the supported range 1-9999")` before
    delegating to `date()`, preventing the cryptic Python-internal `ValueError` from escaping
    when month arithmetic pushes results out of the supported date range
  - Location: `core/fiscal.py`, `tests/test_core_fiscal.py`

- **`FiscalDelta` rejects `bool` for numeric fields** (DEFECT-FISCALDELTA-BOOL-REJECTION-001):
  - `FiscalDelta.__post_init__` validated each of `years`, `quarters`, `months`, and `days`
    with `isinstance(value, int)` — but `isinstance(True, int)` is `True` (bool is a subclass
    of int in Python); `FiscalDelta(years=True)` silently created `FiscalDelta(years=1)`;
    the same issue existed in `__mul__`: `isinstance(factor, int)` passed for `True`, so
    `delta * True` multiplied by 1 rather than returning `NotImplemented`; boolean-as-integer
    is never valid fiscal arithmetic input
  - Added `isinstance(value, bool)` guard BEFORE the `isinstance(value, int)` check for
    all four numeric fields in `__post_init__`; raises `TypeError("years must be int, not bool")`
    (and similarly for other fields); added matching guard in `__mul__`: `isinstance(factor, bool)`
    now returns `NotImplemented` before the `isinstance(factor, int)` check
  - Location: `core/fiscal.py`, `tests/test_core_fiscal.py`

### Changed

- **`FiscalDelta.__add__`/`__sub__` policy mismatch messages remove spurious quotes**
  (CLARITY-FISCALDELTA-POLICY-MSG-001):
  - Error messages used `f"{self.month_end_policy.value!r}"` where `.value` is already a
    `str`; `!r` added unnecessary surrounding quotes, producing
    `"month_end_policy: 'preserve' vs 'clamp'"` in financial logs instead of the cleaner
    `"preserve vs clamp"`
  - Removed `!r` from both `.value` interpolations in `__add__` and `__sub__` error messages
  - Location: `core/fiscal.py`

- **`FluentBundle` POSIX locale rejection message includes BCP 47 guidance**
  (CLARITY-BUNDLE-POSIX-LOCALE-MSG-001):
  - `_LOCALE_PATTERN` in `bundle.py` rejects POSIX locale format `en_US.UTF-8` but the
    rejection message gave no actionable guidance; a developer with `LANG=en_US.UTF-8` had
    to debug the regex to discover that the `.UTF-8` charset suffix was the issue
  - Error message now reads: `"Invalid locale code format: '{locale}'. Locale must be ASCII
    alphanumeric with optional underscore or hyphen separators. Use BCP 47 format (e.g.,
    'en-US', 'de-DE', 'zh-Hans-CN'). Strip charset suffixes such as '.UTF-8' from POSIX
    locale strings."`
  - Location: `runtime/bundle.py`

- **`introspection/message.py` WeakKeyDictionary waiver documents GIL dependency**
  (ARCH-INTROSPECTION-GIL-DOC-001):
  - The accepted WeakKeyDictionary race (worst case: redundant computation, not data
    corruption) relies on CPython's GIL making dict read/write operations atomic at the
    bytecode level; this assumption was not documented; under Python 3.13+ free-threaded
    mode (`--disable-gil`, PEP 703), GIL atomicity is absent and concurrent
    `WeakKeyDictionary` writes can corrupt the dict's internal state; the waiver acceptance
    was correct for CPython with GIL but incomplete as written
  - Added explicit GIL dependency documentation to the waiver comment block: states that
    the race acceptance is valid under the CPython GIL, that free-threaded mode (PEP 703)
    removes this guarantee, and that a `threading.Lock` is required if free-threaded support is ever needed
  - Location: `introspection/message.py`

- **Test files renamed to match §5.1 naming schema** (NAMING-FISCAL-TEST-RENAME-001):
  - `tests/test_parsing_fiscal.py` and `tests/test_parsing_fiscal_property.py` were named
    for the `parsing/` package where `fiscal.py` previously resided; `fiscal.py` moved to
    `core/` in v0.128.0 (ARCH-FISCAL-MOVE-CORE-001) but the test file names were not
    updated; per §5.1, test file names must map to the source module's current package:
    `core/fiscal.py` → `test_core_fiscal*.py`
  - Renamed via `git mv`: `test_parsing_fiscal.py` → `test_core_fiscal.py`;
    `test_parsing_fiscal_property.py` → `test_core_fiscal_property.py`
  - Location: `tests/test_core_fiscal.py`, `tests/test_core_fiscal_property.py`

## [0.128.0] - 2026-02-23

### Changed (BREAKING)

- **`fiscal.py` moved from `parsing/` to `core/`** (ARCH-FISCAL-MOVE-CORE-001):
  - `FiscalCalendar`, `FiscalDelta`, `FiscalPeriod`, `MonthEndPolicy`, and the five
    convenience functions have zero Babel dependency; keeping them in `parsing/` forced
    parser-only installs to fail with `ModuleNotFoundError: No module named 'babel'`
    when importing `from ftllexengine.parsing import FiscalCalendar`, because
    `parsing/__init__.py` imports `.currency` and `.dates` at module level before
    reaching the fiscal re-export; the docstring correctly stated "No external
    dependencies" but the import behaviour contradicted this claim
  - Moved `src/ftllexengine/parsing/fiscal.py` → `src/ftllexengine/core/fiscal.py`;
    `core/__init__.py` now exports all fiscal types; `parsing/__init__.py` re-exports
    from `ftllexengine.core.fiscal` so `from ftllexengine.parsing import FiscalCalendar`
    still works for Babel installs; all fiscal types are now directly importable from the
    top-level `ftllexengine` namespace without Babel; `tests/test_parsing_fiscal.py`
    updated four `from ftllexengine.parsing.fiscal import _add_months` calls to
    `from ftllexengine.core.fiscal import _add_months`
  - Location: `core/fiscal.py` (new), `core/__init__.py`, `parsing/__init__.py`,
    `ftllexengine/__init__.py`, `tests/test_parsing_fiscal.py`

- **`FluentNumber.value` type narrowed from `int | float | Decimal` to `int | Decimal`**
  (DEFECT-FLUENTNUMBER-FLOAT-PRECISION-001):
  - Storing `float` in `FluentNumber.value` contradicted the library's stated guarantee
    of "Decimal precision — No float math, no rounding surprises" (README); `float` has
    approximately 15 significant decimal digits, while `int` and `Decimal` are exact;
    `FluentNumber` is the internal storage type used for plural category matching and cache
    key construction, both of which require exact numeric representation
  - `FluentNumber.value` type annotation changed to `int | Decimal`; `number_format()`
    and `currency_format()` now convert `float` input via `Decimal(str(value))` before
    constructing `FluentNumber`, preserving the caller's intended decimal representation;
    `FluentValue` (the public input type) retains `float` since callers legitimately pass
    native Python floats to `format_pattern()`
  - Location: `runtime/value_types.py`, `runtime/functions.py`

- **`FiscalPeriod` rejects `fiscal_year` outside 1–9999** (DEFECT-FISCALPERIOD-YEAR-BOUNDS-001):
  - `FiscalPeriod.__post_init__` validated `quarter` (1–4) and `month` (1–12) but not
    `fiscal_year`; invalid values such as 0, −1, or 99999 were silently accepted at
    construction time and produced a cryptic `ValueError: year 0 is out of range` from
    Python's `datetime.date` only when `fiscal_year_start_date()` or similar methods
    were later called; fail-fast at construction time is the correct behaviour for a
    financial-grade library
  - Added `if not 1 <= self.fiscal_year <= 9999: raise ValueError(...)` as the first
    check in `FiscalPeriod.__post_init__`; bounds match Python's `datetime.date` year
    range; four tests added to `tests/test_parsing_fiscal.py`
  - Location: `core/fiscal.py`, `tests/test_parsing_fiscal.py`

### Changed

- **Fiscal convenience functions use module-level singleton for calendar-year case**
  (PERF-FISCAL-CALENDAR-ALLOC-001):
  - Every call to `fiscal_quarter(d)`, `fiscal_year(d)`, `fiscal_month(d)`,
    `fiscal_year_start(y)`, or `fiscal_year_end(y)` with the default `start_month=1`
    allocated a new `FiscalCalendar(start_month=1)` instance; `FiscalCalendar` is an
    immutable frozen dataclass so the per-call allocation is unnecessary
  - Added `_CALENDAR_YEAR: Final[FiscalCalendar] = FiscalCalendar(start_month=1)` as a
    module-level constant; all five convenience functions now use `_CALENDAR_YEAR` when
    `start_month == 1` and allocate a new instance only for non-calendar fiscal years
  - Location: `core/fiscal.py`

- **Fiscal types promoted to top-level `ftllexengine` namespace** (API-FISCAL-TOPLEVEL-001):
  - `FiscalCalendar`, `FiscalDelta`, `FiscalPeriod`, `MonthEndPolicy`, `fiscal_quarter`,
    `fiscal_year`, `fiscal_month`, `fiscal_year_start`, and `fiscal_year_end` were only
    accessible via `ftllexengine.parsing` (Babel-gated) or direct submodule import;
    financial users expect top-level access and the types have no Babel dependency
  - All nine symbols now importable as `from ftllexengine import FiscalCalendar, ...`
    with no Babel requirement; added to `__all__` in `ftllexengine/__init__.py`
  - Location: `ftllexengine/__init__.py`

- **`bridge_fnum_type` and `bridge_fnum_precision` strategy events added to metrics**
  (GAP-STRATEGY-METRICS-BRIDGE-FNUM-001):
  - The `fluent_numbers()` strategy in `tests/strategies/ftl.py` emitted
    `bridge_fnum_type={type}` and `bridge_fnum_precision={n}` events that were absent
    from `EXPECTED_EVENTS`, `STRATEGY_CATEGORIES`, and `INTENDED_WEIGHTS` in
    `tests/strategy_metrics.py`; the coverage gap detection system could not flag missing
    coverage for this strategy family; additionally the float branch was removed from the
    strategy after `FluentNumber.value` no longer accepts float
  - Added `bridge_fnum_type=int`, `bridge_fnum_type=decimal`, and four
    `bridge_fnum_precision=*` variants to all three tracking constants; removed float
    branch from `fluent_numbers()` in `tests/strategies/ftl.py`
  - Location: `tests/strategy_metrics.py`, `tests/strategies/ftl.py`

## [0.127.0] - 2026-02-23

### Changed (BREAKING)

- **`DEFAULT_MAX_ENTRY_SIZE` renamed to `DEFAULT_MAX_ENTRY_WEIGHT`** (CLARITY-CONSTANTS-ENTRY-SIZE-RENAME-001):
  - `DEFAULT_MAX_ENTRY_SIZE` named an entry weight ceiling yet used "size" while the corresponding `CacheConfig.max_entry_weight` field and its docstring consistently used "weight"; the cross-module terminology mismatch required readers to mentally reconcile two terms for the same concept, and the import error on upgrade is immediate and unambiguous
  - Renamed to `DEFAULT_MAX_ENTRY_WEIGHT` throughout `constants.py`, `runtime/cache_config.py`, and `runtime/cache.py`
  - Location: `constants.py`, `runtime/cache_config.py`, `runtime/cache.py`

- **`ValidationResult.error_count` now counts syntax errors only** (CLARITY-VALIDATION-ERROR-COUNT-001):
  - `error_count` returned `len(self.errors) + len(self.annotations)`, conflating two distinct diagnostic categories under a name that implies only hard syntax errors; callers that depended on `error_count == 0` as a clean-resource signal were silently misled — a resource with annotations only would still report `error_count > 0`; a new `annotation_count` property is added to give each category its own unambiguous name
  - `error_count` now returns `len(self.errors)` only; `annotation_count` property added returning `len(self.annotations)`; the formatter validation summary now reports both counts separately: `"N issue(s) (E error(s), A annotation(s)), W warning(s)"`
  - Location: `diagnostics/validation.py`, `diagnostics/formatter.py`

- **`ErrorTemplate.expression_depth_exceeded` renamed to `depth_exceeded`** (CLARITY-TEMPLATES-DEPTH-RENAME-001):
  - `expression_depth_exceeded` was called from three structurally unrelated contexts — expression nesting (`depth_guard.py`), message resolution depth (`resolution_context.py`), and any future validation traversal depth — but the `expression_` prefix falsely implied the method applied exclusively to expression nesting, misleading readers who encountered the call in non-expression contexts and suggesting separate methods might be needed for other depth types
  - Renamed to `depth_exceeded`; all three call sites updated
  - Location: `diagnostics/templates.py`, `core/depth_guard.py`, `runtime/resolution_context.py`

### Changed

- **`get_babel_locale` cache key inconsistency eliminated** (DEFECT-LOCALE-UTILS-CACHE-KEY-001):
  - `get_babel_locale` was the `@lru_cache`-decorated function; the locale code was normalized inside the function body after being used as the cache key, so `"en-US"`, `"en_US"`, and `"EN-US"` each created a separate cache entry despite being semantically equivalent; the module-level locale cache grew without bound under locale format variation, and `cache_clear()` / `cache_info()` exposed the wrong function's LRU statistics
  - Split into private `_get_babel_locale_normalized(normalized_code: str)` carrying the `@lru_cache` decorator (cache key is always the post-normalized form) and public `get_babel_locale(locale_code: str)` (normalizes via `normalize_locale()` then delegates); `clear_locale_cache()` now clears `_get_babel_locale_normalized`'s cache; semantically equivalent locale codes share exactly one cache entry
  - Location: `core/locale_utils.py`

- **`MAX_SOURCE_SIZE` corrected to exactly 10,000,000 bytes** (DEFECT-CONSTANTS-SOURCE-SIZE-001):
  - `MAX_SOURCE_SIZE` was computed as `10 * 1024 * 1024 = 10,485,760`; all module docstrings and comments described the limit as "10 million bytes"; the 4.86% surplus allowed inputs up to 485,760 bytes larger than the documented limit, a correctness defect for financial applications that rely on the stated byte budget for capacity planning and DoS risk modelling
  - Changed to the integer literal `10_000_000`; documented limit and enforced limit are now identical
  - Location: `constants.py`

- **`PYTHON_EXCEPTION_ATTRS` deduplicated to a single module-level constant** (SIMPLIFY-INTEGRITY-ATTRS-DEDUP-001):
  - The same `frozenset` of Python exception machinery attribute names (`__traceback__`, `__context__`, `__cause__`, `__suppress_context__`, `__notes__`) was defined independently as a class attribute `_PYTHON_EXCEPTION_ATTRS` inside both `DataIntegrityError` (`integrity.py`) and `FrozenFluentError` (`diagnostics/errors.py`); a future addition to Python's exception machinery would require two synchronised edits with no static enforcement; the duplication also required a circular-import workaround: `errors.py` imported `ImmutabilityViolationError` inside `__setattr__` and `__delattr__` bodies with `# noqa: PLC0415` to avoid a module-level circular import, inflating the call-time cost of every mutation attempt on `FrozenFluentError`
  - Extracted to module-level constant `PYTHON_EXCEPTION_ATTRS: frozenset[str]` in `integrity.py` and added to `__all__`; `diagnostics/errors.py` imports both `PYTHON_EXCEPTION_ATTRS` and `ImmutabilityViolationError` at the top level; class-level `_PYTHON_EXCEPTION_ATTRS` definitions removed from both classes; all function-local deferred imports eliminated
  - Location: `integrity.py`, `diagnostics/errors.py`

- **`FluentParserV1._junk_limit_exceeded()` extracted to eliminate triplicated DoS guard** (SIMPLIFY-PARSER-JUNK-DOS-GUARD-001):
  - The three parse branches in `FluentParserV1.parse()` — message, term, and junk recovery — each contained an identical six-line block checking `self._max_parse_errors > 0 and junk_count >= self._max_parse_errors`, emitting a `WARNING` log, and breaking the loop; triplicated logic is a maintenance hazard for a security-critical path: a future change to the threshold condition, log message, or log level would require three synchronised edits
  - Extracted to private method `_junk_limit_exceeded(self, junk_count: int) -> bool`; all three call sites replaced with `if self._junk_limit_exceeded(junk_count): break`
  - Location: `syntax/parser/core.py`

### Fixed

- **`graph.py` `# pragma: no branch` lacked explanation** (CLARITY-GRAPH-PRAGMA-COMMENT-001):
  - The coverage pragma at `detect_cycles()` suppressing the False branch of `if canonical not in seen_canonical` was unaccompanied by any rationale; readers could not determine whether the unseen branch was architecturally impossible, a test coverage gap, or dead code awaiting removal
  - Added a four-line comment block immediately above the pragma explaining the DFS invariant: each `(node → neighbor)` edge in `rec_stack` is visited at most once per DFS start node, making the `canonical already seen` False branch unreachable within a single DFS pass; `seen_canonical` is never pre-populated by the caller
  - Location: `analysis/graph.py`

- **`FunctionRegistry.__repr__` docstring had an extraneous blank line** (CLARITY-FUNCTION-BRIDGE-REPR-DOCSTRING-001):
  - The one-line summary and the `Returns:` section were separated by two blank lines; Google-style docstrings require exactly one blank line between the summary and the first named section
  - Removed the extra blank line
  - Location: `runtime/function_bridge.py`

## [0.126.0] - 2026-02-22

### Fixed

- **`LocaleContext._cache_lock` used `RLock` with no re-entry path** (SIMPLIFY-LOCALECONTEXT-RLOCK-001):
  - `_cache_lock` was declared as `threading.RLock()` (reentrant lock); no code path in `create()`, `clear_cache()`, `cache_size()`, or `cache_info()` acquires the lock and then re-acquires it from the same thread; `RLock` pays two atomic operations per acquire/release versus `Lock`'s one, making every cache read a needless double-overhead operation
  - Replaced with `threading.Lock()`; all four docstrings that referenced "RLock" updated to "Lock" for accuracy
  - Location: `runtime/locale_context.py`

- **`LocaleContext.create_or_raise()` bypassed the LRU cache entirely** (DEFECT-LOCALECONTEXT-CREATE-OR-RAISE-CACHE-001):
  - `create_or_raise()` constructed a fresh `LocaleContext` and returned it without consulting or populating the class-level LRU cache; a subsequent `create(same_locale)` call experienced a cache miss and re-parsed via Babel; in the reverse order, `create()` cached the instance but `create_or_raise()` ignored it and created a second, unshared instance; repeated `create_or_raise()` calls for the same valid locale multiplied Babel `Locale.parse()` invocations without bound
  - Fixed: `create_or_raise()` now validates the locale strictly via `Babel.Locale.parse()` (raising `ValueError` on failure as before), then delegates to `create()` for all cache management; on the first call, `parse()` executes twice (once for validation, once inside `create()` on cache miss); on all subsequent calls, `create()` returns the cached instance without re-parsing, making repeated calls effectively O(1); cache coherence between `create()` and `create_or_raise()` is now guaranteed
  - Location: `runtime/locale_context.py`

- **`integrity.py` had three blank lines before `WriteConflictError`** (CLARITY-INTEGRITY-BLANK-LINE-001):
  - PEP 8 and the rest of the module use exactly two blank lines between top-level class definitions; `IntegrityCheckFailedError` was followed by three blank lines before `WriteConflictError`, a visual inconsistency with no semantic content
  - Reduced to the standard two blank lines
  - Location: `integrity.py`

- **`parse_pattern` failures in `number_format` and `currency_format` silently swallowed at `DEBUG` level** (DEFECT-FUNCTIONS-PARSE-PATTERN-LOG-LEVEL-001):
  - When Babel's `parse_pattern()` raises on a custom format pattern string after `format_number`/`format_currency` has already succeeded, the exception was caught and logged at `DEBUG` level; the consequence is a silent loss of precision capping for the CLDR `v` operand (visible fraction digit count), meaning `number_format(1.2, pattern="0.0'5'")` can produce an inflated plural precision; for financial applications that use ICU single-quote pattern literals, this miscategorisation silently causes the wrong plural form to be selected
  - Changed log level from `DEBUG` to `WARNING` in both `number_format` and `currency_format`; message text updated to name the exact consequence ("CLDR v operand may be inflated") so operators can identify the affected pattern and respond appropriately
  - Location: `runtime/functions.py`

## [0.125.0] - 2026-02-22

### Changed

- **`_COMMENT_TYPE_BY_HASH_COUNT` module-level tuple constant replaces per-call dict in `parse_comment()`** (PERF-PARSER-RULES-COMMENT-TYPE-001):
  - `parse_comment()` constructed a temporary `{1: CommentType.COMMENT, 2: CommentType.GROUP, 3: CommentType.RESOURCE}` dict on every invocation to map hash count to `CommentType`; the dict was discarded after the single `.get()` call
  - Replaced with module-level `_COMMENT_TYPE_BY_HASH_COUNT: tuple[CommentType, CommentType, CommentType]` constant; index access `_COMMENT_TYPE_BY_HASH_COUNT[hash_count - 1]` is O(1) with zero allocation on each call; the tuple is constructed once at module import time
  - Location: `syntax/parser/rules.py`

### Fixed

- **`ParseError.format_with_context()` docstring example used `list` instead of `tuple`** (CLARITY-CURSOR-PARSEERROR-DOCSTRING-001):
  - The `expected` field in `ParseError` is typed `tuple[str, ...]`; the docstring example showed `expected=[']', '}']` (list literal), misrepresenting the actual type at every reader's first point of contact with the API
  - Corrected to `expected=(']', '}')` (tuple literal) to accurately reflect the declared type
  - Location: `syntax/cursor.py`

## [0.124.0] - 2026-02-22

### Changed (BREAKING)

- **`FluentLocalization` context manager is now a no-op** (ARCH-LOCALIZATION-CONTEXT-MANAGER-NOOP-001):
  - `__enter__` previously acquired a write lock to reset `_modified_in_context = False`; `__exit__` conditionally cleared all bundle caches when the localization was modified during the context; this was architecturally redundant and harmful for the same reasons as `FluentBundle` (v0.123.0): `add_resource()`, `add_function()`, and `clear_cache()` already clear the relevant cache immediately on mutation; the deferred `__exit__` clear invalidated valid cache entries populated by concurrent readers after the mutation; Thread A's context exit could evict Thread B's valid in-flight cache fills across all locale bundles
  - `__enter__` now returns `self` unconditionally; `__exit__` is now a no-op; `_modified_in_context` slot removed; no write lock is acquired on context entry or exit
  - Code relying on `with l10n:` to auto-clear bundle caches on block exit must now call `l10n.clear_cache()` explicitly; read-only `with l10n:` usage is unaffected (it was already correct)
  - `FluentBundle` and `FluentLocalization` context managers now have identical semantics: both are no-ops used for structured scoping only
  - Location: `localization/orchestrator.py`

## [0.123.0] - 2026-02-22

### Changed (BREAKING)

- **`FluentBundle` context manager is now a no-op** (ARCH-BUNDLE-CONTEXT-MANAGER-NOOP-001):
  - `__enter__` previously acquired a write lock to reset `_modified_in_context = False`; `__exit__` conditionally cleared the format cache when the bundle was modified during the context; this was architecturally redundant and harmful: `add_resource()` and `add_function()` already call `self._cache.clear()` immediately on modification, and the deferred `__exit__` clear invalidated valid cache entries populated after the modification; in concurrent usage, Thread A's context exit could evict Thread B's valid in-flight cache fills
  - `__enter__` now returns `self` unconditionally; `__exit__` is now a no-op; `_modified_in_context` slot removed; no write lock is acquired on context entry or exit
  - Code relying on `with bundle:` to auto-clear the cache on block exit must now call `bundle.clear_cache()` explicitly; read-only `with bundle:` usage is unaffected (it was already correct)
  - Location: `runtime/bundle.py`

### Changed

- **`_get_resolver()` and `_invalidate_resolver()` one-liner methods inlined** (SIMPLIFY-BUNDLE-RESOLVER-WRAPPERS-001):
  - Both were zero-value indirection: `_get_resolver()` returned `self._resolver`; `_invalidate_resolver()` assigned `self._resolver = self._create_resolver()`; each was called from exactly one site
  - Methods deleted; call sites replaced with direct attribute access/assignment
  - Location: `runtime/bundle.py`

- **`_PendingRegistration` converted to `@dataclass(slots=True)`** (MODERN-BUNDLE-PENDING-REG-001):
  - Was implemented as a plain class with manual `__slots__` and `__init__`; inconsistent with the rest of the codebase which uses `@dataclass` throughout
  - Replaced with `@dataclass(slots=True)` using `field(default_factory=...)` for all mutable default fields; semantics are identical
  - Location: `runtime/bundle.py`

- **`__slots__ = ()` added to three empty `DataIntegrityError` subclasses** (MEMORY-INTEGRITY-SLOTS-001):
  - `CacheCorruptionError`, `ImmutabilityViolationError`, and `IntegrityCheckFailedError` added no new attributes but omitted `__slots__ = ()`; Python created a `__dict__` for instances of each subclass, wasting memory and breaking the slot discipline established by `DataIntegrityError`
  - `__slots__ = ()` added to all three
  - Location: `integrity.py`

- **`_FALLBACK_MAX_DEPTH` named constant added for fallback depth limit** (CLARITY-RESOLVER-FALLBACK-DEPTH-001):
  - `_get_fallback_for_placeable` used a bare `10` as its default `depth` argument with no explanation; the magic number was opaque at definition and call sites
  - Extracted to module-level constant `_FALLBACK_MAX_DEPTH: int = 10` with a docstring explaining the rationale
  - Location: `runtime/resolver.py`

### Fixed

- **`args = args or {}` replaced with explicit `None` check in resolver** (DEFECT-RESOLVER-ARGS-FALSY-001):
  - `resolve_message` used `args = args or {}` which treated any falsy `Mapping` (e.g., a custom `Mapping` subclass with `__bool__` returning `False`) as `None` and replaced it with `{}`, silently discarding all variable bindings
  - Fixed to `args = {} if args is None else args`; only the `None` sentinel is replaced
  - Location: `runtime/resolver.py`

- **Stale `clear_all_caches()` docstring** (CLARITY-CLEAR-ALL-CACHES-DOCS-001):
  - Docstring referenced `FormatCache` (the class's former name, replaced by `IntegrityCache`) and advised users to "recreate the FluentBundle instance" to clear bundle caches (incorrect — `bundle.clear_cache()` is the correct API)
  - Corrected both: `FormatCache` → `IntegrityCache`; advice updated to `bundle.clear_cache()`
  - Location: `__init__.py`

- **`FluentBundle.__init__` `functions` parameter docstring was misleading** (CLARITY-BUNDLE-FUNCTIONS-PARAM-001):
  - Docstring said "Share function registrations between bundles"; the registry is immediately `.copy()`ed on construction, so no sharing occurs after `__init__` returns
  - Corrected: documents that the registry is copied on construction and later mutations to the original have no effect
  - Location: `runtime/bundle.py`

## [0.122.0] - 2026-02-22

### Fixed

- **LRU cache eviction corrupted capacity when updating an existing key** (DEFECT-CACHE-LRU-EVICTION-001):
  - `IntegrityCache.put()` called `self._cache.popitem(last=False)` unconditionally when the cache was full, then updated the existing key if it was already present; when `key` already existed in a full cache, one LRU-end entry was evicted AND the existing key was updated, silently shrinking the effective capacity by one slot per thundering-herd write to the same key
  - Fixed: compute `is_update = key in self._cache` before the eviction guard; skip `popitem` when `is_update is True`; subsequent `move_to_end(key)` promotes the updated entry to MRU position without altering capacity
  - Location: `runtime/cache.py`

- **Expansion budget overflow generated duplicate errors for nested resolutions** (DEFECT-RESOLVER-BUDGET-DUPLICATE-001):
  - `_resolve_pattern` reported an `EXPANSION_BUDGET_EXCEEDED` error from two separate sites: the pre-loop check (fired on every iteration where `context.total_chars > context.max_expansion_size`) and the `Placeable` post-track check; when the overflow originated in a nested `_resolve_pattern` call (via term reference, message reference, or select-expression variant), the nested call already appended the error to the shared `errors` list, causing the outer call to append a second identical error
  - Fixed in two changes: (1) pre-loop check moved before the element loop as an early `return` — it fires only when `_resolve_pattern` is entered with an already-exceeded context (e.g., externally provided `ResolutionContext`), never after a nested call; (2) `Placeable` post-track check now records `pre_track = context.total_chars` before `track_expansion` and suppresses the `errors.append` when `pre_track > context.max_expansion_size` (the overflow and its error were already reported inside the nested call)
  - Location: `runtime/resolver.py`

- **`IntegrityCache` docstrings referenced `RLock` after lock downgrade in v0.121.0** (CLARITY-CACHE-LOCK-DOCS-001):
  - v0.121.0 (PERF-CACHE-LOCK-001) changed `IntegrityCache._lock` from `threading.RLock()` to `threading.Lock()` but did not update the module docstring phrase "Thread-safe using threading.RLock (reentrant lock)" or the class docstring phrase "All operations are protected by RLock"
  - Corrected both sites to "threading.Lock" and "protected by Lock"
  - Location: `runtime/cache.py`

### Changed

- **`babel_compat` getters simplified: dead `try/except ImportError` removed** (SIMPLIFY-BABEL-DEAD-EXCEPT-001):
  - Seven getter functions (`get_cldr_version`, `get_babel_numbers`, `get_babel_dates`, `get_global_data_func`, `get_number_format_error_class`, `get_parse_decimal_func`, `get_locale_identifiers_func`) each wrapped their `from babel import ...` statement in a `try/except ImportError` block after calling `require_babel()`; `require_babel()` raises `BabelImportError` when Babel is unavailable, making the except clauses unreachable in any healthy environment; all seven had `# pragma: no cover` confirming they were never reached in CI
  - Dead `try/except` blocks removed; each getter now calls `require_babel(feature)` and imports directly; `# pragma: no cover` annotations removed alongside; tests that previously reached the catch path through `sys.modules` manipulation (relying on a stale `_babel_available = True` sentinel) updated to use direct sentinel reset (`_bc._babel_available = False`) consistent with the pattern used by all other tests in that class
  - Location: `core/babel_compat.py`, `tests/test_introspection_iso.py`

## [0.121.0] - 2026-02-22

### Changed (BREAKING)

- **`with_read_lock` and `with_write_lock` decorators removed** (DEAD-RWLOCK-DECORATORS-001):
  - Both decorators were unreachable dead code: absent from `__all__ = ["RWLock"]`, not imported by any module in the codebase, not covered by any test
  - Deleted from `runtime/rwlock.py`; `Callable` and `wraps` imports removed alongside; the file now exports only `RWLock`
  - Callers must use the context-manager API directly: `with lock.read():` / `with lock.write():`, which provide identical semantics without decorator indirection
  - Location: `runtime/rwlock.py`

- **`ErrorCategory` base changed from `Enum` to `StrEnum`** (CLARITY-ERRORCATEGORY-STRENUM-001):
  - `ErrorCategory(Enum)` produced `str(ErrorCategory.REFERENCE) == "ErrorCategory.REFERENCE"`; `.value` access was required for serialization and log aggregation, and the `str()` output was not the plain value string
  - Changed to `ErrorCategory(StrEnum)`: `str(ErrorCategory.REFERENCE) == "reference"`; direct equality `ErrorCategory.REFERENCE == "reference"` is now `True` (StrEnum inherits from `str`); `.value` and `.name` attributes are unchanged
  - Code comparing `str(category)` against `"ErrorCategory.X"` strings must update to compare against the plain value strings (`"reference"`, `"resolution"`, `"cyclic"`, `"parse"`, `"formatting"`)
  - Location: `diagnostics/codes.py`

### Fixed

- **TextElement expansion budget exhaustion abandoned entire `parts` accumulator** (DEFECT-RESOLVER-TEXTELEMENT-BUDGET-001):
  - `_resolve_pattern` handled `Placeable` budget exhaustion by catching `FrozenFluentError`, appending the error, and breaking — preserving previously accumulated `parts`; `TextElement` budget exhaustion propagated the exception upward via `track_expansion`, abandoning the entire `parts` accumulator and silently discarding all previously resolved elements
  - Fixed: `TextElement` branch now checks `context.total_chars > context.max_expansion_size` after calling `track_expansion`, appends `EXPANSION_BUDGET_EXCEEDED` error, and breaks — symmetric behavior with the `Placeable` path; partial output is preserved regardless of which element type triggers the limit
  - Location: `runtime/resolver.py`

- **`ResolutionContext._seen` was injectable via dataclass `__init__`** (SECURITY-RESOLUTION-CONTEXT-SEEN-001):
  - `_seen: set[str] = field(default_factory=set)` was a public `__init__` parameter; any caller could construct `ResolutionContext(_seen={"target-message"})` to pre-populate the cycle-detection set, making `context.contains("target-message")` return `True` immediately and silently bypassing cycle detection for an arbitrary message ID without any error
  - Fixed: changed to `field(init=False, default_factory=set)`; excluded from `__init__`; pre-population is structurally impossible
  - Location: `runtime/resolution_context.py`

- **Data race on `_modified_in_context` in `FluentBundle` and `FluentLocalization`** (RACE-MODIFIED-IN-CONTEXT-001):
  - `_modified_in_context` was reset to `False` in `__enter__` and read + reset in `__exit__` without holding `_rwlock`; concurrent `add_function` and `add_resource` calls write `_modified_in_context = True` under a write lock; in Python 3.13 free-threaded mode `__exit__` could observe a stale `False` and skip cache invalidation despite concurrent mutations having occurred
  - Fixed: `__enter__` resets `_modified_in_context` under `_rwlock.write()` (bundle) or `_lock.write()` (orchestrator); `__exit__` reads and resets the flag atomically under the same write lock, then performs cache invalidation outside the lock (cache operations are independently thread-safe)
  - Location: `runtime/bundle.py`, `localization/orchestrator.py`

- **`_clear_tracebacks` destroyed forensic audit trail on every resolver return** (FORENSIC-CLEAR-TRACEBACKS-001):
  - `_clear_tracebacks` set `err.__traceback__ = None` on every `FrozenFluentError` before `resolve_message` returned; stack traces were unconditionally destroyed at the resolver boundary, making post-mortem incident analysis impossible unless the caller logged the exception before the error tuple was discarded; this contradicted the forensic intent of `FrozenFluentError`'s BLAKE2b content hashing design
  - Fixed: `_clear_tracebacks` deleted; all six `return (result, _clear_tracebacks(errors))` call sites changed to `return (result, tuple(errors))`; tracebacks are preserved for the full lifetime of the error objects
  - Location: `runtime/resolver.py`

### Changed

- **`ResolutionContext.track_expansion` no longer raises on budget exceeded** (ARCH-TRACK-EXPANSION-SOC-001):
  - `track_expansion` both mutated `_total_chars` and generated `FrozenFluentError` via `ErrorTemplate`, coupling state tracking to error policy in an infrastructure object; the resolver already had a pre-loop budget check that generated the same diagnostic via different code, making budget exhaustion handling inconsistent across `TextElement` and `Placeable` paths
  - `track_expansion(char_count)` now only mutates `_total_chars` and never raises; callers check `context.total_chars > context.max_expansion_size` after each call and generate `FrozenFluentError` directly; error construction is unified in `_resolve_pattern` for both element paths
  - Location: `runtime/resolution_context.py`, `runtime/resolver.py`

- **`IntegrityCache._lock` changed from `RLock` to `Lock`** (PERF-CACHE-LOCK-001):
  - `IntegrityCache._lock` was `threading.RLock()`; no call path in `IntegrityCache` acquires the lock re-entrantly — every public method acquires at entry and `_audit` is documented to run while the lock is already held without re-acquiring; `RLock` tracked the owning thread ID and acquire count on every acquisition, adding measurable overhead in the hot path of `format_pattern()`
  - Changed to `threading.Lock()`; lock semantics unchanged for all current call paths; any future inadvertent re-entry would raise `RuntimeError` immediately rather than silently succeeding
  - Location: `runtime/cache.py`

- **`GlobalDepthGuard` thread-spawning limitation documented** (CLARITY-DEPTH-GUARD-THREAD-LIMIT-001):
  - The class docstring documented protection against same-thread re-entry via `ContextVar` but did not document the known limitation: custom functions that spawn new threads bypass the guard entirely — each new thread receives `ContextVar` default (depth 0) and can initiate a full-depth resolution chain independent of the spawning thread's guard state
  - Added explicit "Thread Spawning Limitation" section to the docstring; no code changes; the limitation is an accepted consequence of `ContextVar` semantics
  - Location: `runtime/resolution_context.py`

- **`resolve_message` except clause comment corrected** (CLARITY-RESOLVER-EXCEPT-COMMENT-001):
  - The `except FrozenFluentError` block carried the comment "Global depth exceeded — collect error and return fallback"; the block catches all `FrozenFluentError` instances regardless of `DiagnosticCode` — including `EXPANSION_BUDGET_EXCEEDED` and `EXPRESSION_DEPTH_EXCEEDED` from the expression depth guard — not only global depth violations; the misleading comment could cause developers to incorrectly narrow the guard's scope during maintenance
  - Replaced with: "Resolution limit exceeded (global depth, expression depth, or expansion budget). Collect error and return fallback — prevents partial output from reaching the caller."
  - Location: `runtime/resolver.py`

## [0.120.0] - 2026-02-21

### Changed (BREAKING)

- **`FluentResolver` slots privatized** (ARCH-RESOLVER-SLOTS-PRIVATE-001):
  - Five public `__slots__` attributes were directly writable from external code: `locale`, `messages`, `terms`, `function_registry`, `use_isolating`; public slots on an internal implementation class permitted callers to mutate resolver state from outside its invariants
  - Renamed to `_locale`, `_messages`, `_terms`, `_function_registry`, `_use_isolating`; all accesses within the class updated accordingly
  - `FluentResolver` is an internal class; public resolver interaction is via `FluentBundle.format_pattern()`; direct `FluentResolver` usage requiring private-slot access should use `# noqa: SLF001` with a rationale comment
  - Location: `runtime/resolver.py`

- **`FluentBundle.cache_config` return type changed to `CacheConfig | None`** (ARCH-BUNDLE-CACHE-CONFIG-NULLABLE-001):
  - `cache_config` previously returned `CacheConfig` in all cases: when `cache=None` was passed to the constructor, it silently initialized `_cache_config = CacheConfig()` and returned that phantom instance, making a disabled cache look enabled
  - Now `_cache_config` is stored as `CacheConfig | None`; `cache_config` returns `None` when caching is disabled and the configured `CacheConfig` when enabled; callers accessing `bundle.cache_config.size` etc. must first guard with `assert bundle.cache_config is not None` or `if bundle.cache_config is not None:`
  - Location: `runtime/bundle.py`

- **`FluentBundle.cache_size` property removed** (ARCH-BUNDLE-CACHE-SIZE-REMOVE-001):
  - `cache_size` returned `cache_config.size` without guarding for `None`; with `cache_config` now nullable, `cache_size` would silently return 0 or raise `AttributeError` on disabled-cache bundles; the delegation added no value over `bundle.cache_config.size`
  - Callers must replace `bundle.cache_size` with `bundle.cache_config.size` (guarded: `if bundle.cache_config is not None: ... bundle.cache_config.size`)
  - Location: `runtime/bundle.py`

### Fixed

- **Data race in `FluentBundle.__repr__`** (DEFECT-BUNDLE-REPR-RACE-001):
  - `__repr__` accessed `len(self._messages)` and `len(self._terms)` without holding `_rwlock`; concurrent `add_resource()` calls (which mutate both dicts under a write lock) could yield a torn read
  - Fixed: `__repr__` acquires `_rwlock.read()` before reading both counts
  - Location: `runtime/bundle.py`

- **Data race in `FluentLocalization.__repr__`** (DEFECT-LOCALIZATION-REPR-RACE-001):
  - `__repr__` accessed `len(self._bundles)` without holding `_lock`; concurrent bundle initialization mutates `_bundles` under a write lock
  - Fixed: `__repr__` acquires `_lock.read()` to read the bundle count; `len(self._locales)` is safe (immutable tuple)
  - Location: `localization/orchestrator.py`

- **Phantom `CacheConfig` when cache disabled** (DEFECT-BUNDLE-PHANTOM-CACHE-CONFIG-001):
  - When `FluentBundle` was constructed with `cache=None`, `__init__` set `self._cache_config = CacheConfig()` — an unconditional default instantiation; `cache_config` returned a `CacheConfig` instance even when caching was disabled, and `cache_size` returned `DEFAULT_CACHE_SIZE` (1000) rather than indicating no cache
  - Fixed: `_cache_config` is stored as `cache` directly (may be `None`); see `cache_config` and `cache_size` breaking changes above
  - Location: `runtime/bundle.py`

- **Validation performed after cache lookup in `_format_pattern_impl`** (DEFECT-BUNDLE-VALIDATION-ORDER-001):
  - `_format_pattern_impl` checked the cache before validating `message_id`, `args`, and `attribute`; an invalid `message_id` (empty string, non-string) or invalid `args` type could interact with the cache before being rejected
  - Fixed: all three validation checks (`message_id`, `args`, `attribute`) precede the cache lookup; invalid inputs are rejected immediately without touching the cache
  - Location: `runtime/bundle.py`

- **PII-exposing debug log in `_format_pattern_impl`** (DEFECT-BUNDLE-PII-LOG-001):
  - `logger.debug("Resolved message '%s': %s", message_id, result[:50])` emitted the first 50 characters of every resolved message; for financial applications this can expose account numbers, balances, or transaction details in application logs
  - Fixed: message replaced with `logger.debug("Resolved message '%s' successfully", message_id)`; the resolved text is never logged
  - Location: `runtime/bundle.py`

- **`IntegrityCacheEntry.verify()` duck-typed `@final` class** (DEFECT-CACHE-VERIFY-DUCK-TYPE-001):
  - `verify()` checked `getattr(error, "verify_integrity", None)` and `callable(verify_method)` before calling the method; `FrozenFluentError` is `@final` and unconditionally exposes `verify_integrity()`, making the defensive duck-type check both dead code and a performance overhead per-error
  - Fixed: direct call `error.verify_integrity()` without the attribute guard; loop consolidated to `return all(error.verify_integrity() for error in self.errors)`
  - Location: `runtime/cache.py`

- **`ISO_4217_DECIMAL_DIGITS` was a mutable module-level constant** (DEFECT-CONSTANTS-MUTABLE-DICT-001):
  - `ISO_4217_DECIMAL_DIGITS: dict[str, int]` was a plain `dict`; any code importing and modifying it (by accident or otherwise) would corrupt the shared constant for all subsequent callers in the same process
  - Fixed: wrapped in `MappingProxyType`; the type annotation is `MappingProxyType[str, int]`; mutation attempts raise `TypeError` at runtime
  - Location: `constants.py`

### Changed

- **`IntegrityCache.size` delegates to `__len__`** (REFACTOR-CACHE-SIZE-DELEGATE-001):
  - `size` acquired `self._lock` and returned `len(self._cache)` — identical to `__len__`; two methods held the same lock sequentially for the same operation
  - `__len__` now acquires the lock and returns the count; `size` calls `len(self)`, delegating to `__len__` without a second lock acquisition
  - Location: `runtime/cache.py`

- **`FluentLocalization._primary_locale` precomputed at initialization** (PERF-LOCALIZATION-PRIMARY-LOCALE-001):
  - `format_pattern()` computed `primary_locale = self._locales[0] if self._locales else None` on every call; `_locales` is an immutable tuple validated non-empty at construction
  - `_primary_locale: LocaleCode` is now set once in `__init__` immediately after locale validation; `format_pattern()` reads the precomputed value directly
  - Location: `localization/orchestrator.py`

- **`scripts/verify_iso4217.py` type annotations aligned with actual types** (REFACTOR-VERIFY-ISO4217-TYPES-001):
  - `_check_unrecognized`, `_check_discrepancies`, and `_check_coverage_gaps` were annotated `iso_digits: dict[str, int]` and `babel_currencies: set[str]`; the first parameter receives `MappingProxyType[str, int]` (now the actual type of the constant) and the second receives `frozenset[str]` (return type of Babel's `list_currencies()`)
  - Parameters changed to `Mapping[str, int]` and `frozenset[str]`; call site wraps `list_currencies()` result in `frozenset()`; redundant `print("[EXIT-CODE] ...")` lines removed (exit code is set by `sys.exit()`)
  - Location: `scripts/verify_iso4217.py`

## [0.119.0] - 2026-02-21

### Fixed

- **Data race in `FluentBundle` resolver initialization** (DEFECT-BUNDLE-RESOLVER-RACE-001):
  - `_resolver` was initialized lazily under a read lock: the first `format_pattern` call wrote `self._resolver` while only holding a read lock, creating a write-under-read-lock data race in Python 3.13 free-threaded mode (PYTHON_GIL=0)
  - Fixed: resolver created eagerly in `__init__` via `_create_resolver()`; `_get_resolver()` is now a pure read that never writes; `_invalidate_resolver()` recreates the resolver under a write lock (called only by `add_function`, not by `add_resource`, since the resolver holds dict references and observes mutations directly)
  - Type annotation updated from `FluentResolver | None` to `FluentResolver`; the `if self._resolver is None` branch in `_get_resolver()` is removed
  - Location: `runtime/bundle.py`

- **`FormattingIntegrityError` component wrong when raised through `FluentLocalization`** (DEFECT-LOCALIZATION-INTEGRITY-COMPONENT-001):
  - `FluentLocalization.format_pattern()` delegates to `FluentBundle.format_pattern()`, which raises `FormattingIntegrityError` with `context.component="bundle"`; callers monitoring the component field saw `"bundle"` even when the call originated from the localization layer
  - Fixed: `format_pattern()` catches `FormattingIntegrityError`, rebuilds `IntegrityContext` with `component="localization"`, and re-raises; all other fields (operation, key, expected, actual, timestamp) are preserved from the original context
  - Location: `localization/orchestrator.py`

- **`ResolutionContext.pop()` silently discarded state corruption** (DEFECT-RESOLUTION-CONTEXT-POP-001):
  - `pop()` used `self._seen.discard(key)` — `discard` is a no-op when the key is absent; if `_seen` and `stack` fell out of sync, the corruption was silently absorbed
  - Fixed: replaced with `self._seen.remove(key)` — raises `KeyError` if the key is absent, making state corruption immediately visible
  - Location: `runtime/resolution_context.py`

- **`IntegrityCacheEntry._feed_errors()` contained dead duck-typed fallback** (DEFECT-CACHE-FEED-ERRORS-FALLBACK-001):
  - `_feed_errors()` used `getattr(error, "content_hash", None)` with an `isinstance(content_hash, bytes)` guard and a `str(error).encode()` fallback; `FrozenFluentError` is `@final` and always exposes `content_hash: bytes`, making the fallback unreachable for any valid input
  - Fixed: fallback removed; `error.content_hash` accessed directly; any non-`FrozenFluentError` input immediately raises `AttributeError` rather than being silently accepted
  - Location: `runtime/cache.py`

### Changed

- **`IntegrityCache.clear()` no longer resets cumulative observability metrics** (DEFECT-CACHE-CLEAR-METRICS-001):
  - `clear()` previously reset `hits`, `misses`, `unhashable_skips`, `oversize_skips`, `error_bloat_skips`, `corruption_detected`, `idempotent_writes`, and `sequence` to 0, destroying production observability data each time the cache was invalidated (e.g., after `add_resource`)
  - Fixed: `clear()` removes cached entries only; all counters accumulate across the lifetime of the `IntegrityCache` instance
  - Callers that read statistics immediately after a `clear()` call and expect zero values must capture a pre-clear snapshot and subtract
  - Location: `runtime/cache.py`

- **`FluentLocalization.get_cache_stats()` now aggregates all `IntegrityCache` fields** (DEFECT-LOCALIZATION-CACHE-STATS-001):
  - `get_cache_stats()` previously returned only 7 keys (`size`, `maxsize`, `hits`, `misses`, `hit_rate`, `unhashable_skips`, `bundle_count`), silently dropping 11 fields from `IntegrityCache.get_stats()`
  - Now returns all 18 keys: the original 7 plus `oversize_skips`, `error_bloat_skips`, `corruption_detected`, `idempotent_writes`, `sequence`, `write_once`, `strict`, `audit_enabled`, `audit_entries`, `max_entry_weight`, `max_errors_per_entry`; boolean fields are from the first bundle (all bundles share one `CacheConfig`); numeric fields are summed across all bundles
  - Callers comparing `set(get_cache_stats().keys())` against a hardcoded expected set must add the 11 new fields
  - Location: `localization/orchestrator.py`

- **`FluentLocalization.format_value()` delegates to `format_pattern()`** (DEFECT-LOCALIZATION-FORMAT-VALUE-001):
  - `format_value()` was an ~80-line near-duplicate of `format_pattern()` with identical locale-fallback chain, strict-mode handling, and error propagation logic
  - Replaced with a single-line delegate: `return self.format_pattern(message_id, args)`; all behavior preserved since `format_pattern` defaults to `attribute=None`
  - Location: `localization/orchestrator.py`

## [0.118.0] - 2026-02-21

### Changed (BREAKING)

- **`FluentBundle.format_value()` removed** (ARCH-BUNDLE-FORMAT-VALUE-REMOVE-001):
  - `format_value(message_id, args)` was an alias for `format_pattern(message_id, args, attribute=None)`; the `attribute=None` default is already the default for `format_pattern`, making the alias redundant
  - The name created false symmetry with `FluentLocalization.format_value()`, which performs locale-fallback chain walking — `FluentBundle.format_value()` did not; callers seeing `.format_value()` on both types could not infer the different operational semantics
  - Callers must replace `bundle.format_value(msg_id, args)` with `bundle.format_pattern(msg_id, args)`
  - `FluentLocalization.format_value()` is unchanged
  - Location: `runtime/bundle.py`

- **`FluentBundle` pass-through cache properties removed** (ARCH-BUNDLE-CACHE-PROPS-REMOVE-001):
  - Five read-only properties delegated entirely to `self._cache_config.*` without transformation: `cache_write_once`, `cache_enable_audit`, `cache_max_audit_entries`, `cache_max_entry_weight`, `cache_max_errors_per_entry`
  - `bundle.cache_config` is already a public property returning the `CacheConfig` instance; the five properties added API surface with zero new information
  - Callers must replace `bundle.cache_write_once` → `bundle.cache_config.write_once`, `bundle.cache_enable_audit` → `bundle.cache_config.enable_audit`, `bundle.cache_max_audit_entries` → `bundle.cache_config.max_audit_entries`, `bundle.cache_max_entry_weight` → `bundle.cache_config.max_entry_weight`, `bundle.cache_max_errors_per_entry` → `bundle.cache_config.max_errors_per_entry`
  - Location: `runtime/bundle.py`

- **`FluentNumber.__contains__` and `__len__` removed** (ARCH-FLUENT-NUMBER-PROTOCOL-REMOVE-001):
  - Both methods made `FluentNumber` behave as a string container — `len(fn)` returned `len(fn.formatted)`, `x in fn` returned `x in fn.formatted`; this is semantically incorrect for a numeric type
  - Neither method was called anywhere in production code; they had zero uses
  - Callers must access `fn.formatted` directly for string-container operations on the formatted representation
  - Location: `runtime/value_types.py`

### Fixed

- **`GlobalDepthGuard.__enter__` constructed `ErrorTemplate.expression_depth_exceeded()` twice** (DEFECT-DEPTH-GUARD-DOUBLE-CONSTRUCT-001):
  - On a depth limit violation, `ErrorTemplate.expression_depth_exceeded(self._max_depth)` was called once to obtain the string message (`str(...)`) and again to obtain the diagnostic for `FrozenFluentError(diagnostic=...)`, allocating two identical objects where one suffices
  - Fixed: the result is computed once into a local variable `diag` and used for both the string message and the diagnostic argument
  - Location: `runtime/resolution_context.py`

### Changed

- **`IntegrityCache` content hash stored at construction time** (PERF-INTEGRITY-CACHE-CONTENT-HASH-001):
  - `IntegrityCacheEntry.content_hash` was a `@property` that recomputed the BLAKE2b-128 hash on every access; the cache `put()` idempotency check called the property once per store attempt, invoking a full BLAKE2b round-trip each time
  - `content_hash` is now an `init=False` field computed once in `__post_init__` via `object.__setattr__` (same pattern as `FunctionSignature.param_dict`); subsequent accesses read the cached bytes with no computation
  - `verify()` now checks the stored `content_hash` against a recomputed value before the full checksum check, providing defense-in-depth against in-memory corruption of the content hash field itself
  - Location: `runtime/cache.py`

- **`IntegrityCacheEntry` error-hashing logic deduplicated** (REFACTOR-CACHE-FEED-ERRORS-DRY-001):
  - The identical 10-line error-hashing block (length prefix, per-error type tag, content-hash or string encoding) appeared verbatim in both `_compute_checksum` and `_compute_content_hash`, creating a maintenance hazard where any BLAKE2b encoding change required two synchronized edits
  - Extracted to a `@staticmethod _feed_errors(h, errors)` shared by both methods; public signatures of `_compute_checksum` and `_compute_content_hash` unchanged
  - Location: `runtime/cache.py`

- **`__init__.py` lazy-load cache uses `globals()` pattern** (REFACTOR-INIT-LAZY-CACHE-001):
  - Babel-independent lazy attributes (`CacheConfig`, `FluentValue`, `fluent_function`) were stored in a module-level `_lazy_cache: dict[str, object]` dict, requiring a dict lookup on every `__getattr__` call after the first access
  - Replaced with the standard `globals()[name] = obj` pattern; after the first access the attribute is stored in `module.__dict__` and subsequent lookups bypass `__getattr__` entirely via Python's normal attribute lookup protocol
  - Location: `ftllexengine/__init__.py`

## [0.117.0] - 2026-02-21

### Changed (BREAKING)

- **`DiagnosticFormatter.format_error` and `format_warning` raise `TypeError` on type violations** (ARCH-DIAG-ASSERT-TO-TYPEERROR-001):
  - `ARCH-DIAG-DUCK-TYPING-001` (v0.116.0) enforced the type contract with `assert isinstance(...)`, which raises `AssertionError` in standard mode and is silently suppressed when Python runs with `-O`
  - Both guards replaced with explicit `if not isinstance(...): raise TypeError(...)` — enforces the contract unconditionally regardless of optimization level
  - Callers catching `AssertionError` for type enforcement failures in these methods must migrate to `TypeError`
  - Location: `diagnostics/formatter.py`

### Changed

- **`babel_compat.py` consolidated as the sole Babel import gateway** (ARCH-BABEL-GATEWAY-001):
  - Scattered `from babel.X import Y` imports across `runtime/`, `introspection/`, `parsing/`, and `core/` modules bypassed the `_babel_available` availability sentinel and invoked Babel APIs directly; any module importing Babel this way ignored `require_babel()` guards
  - All direct Babel imports replaced with gateway functions in `core/babel_compat.py`; six new gateway functions added to `__all__`: `get_babel_dates`, `get_babel_numbers`, `get_global_data_func`, `get_locale_identifiers_func`, `get_number_format_error_class`, `get_parse_decimal_func`
  - Location: `core/babel_compat.py`

- **`require_babel()` added at entry points of `select_plural_category`, `LocaleContext.create`, `LocaleContext.create_or_raise`** (ARCH-BABEL-REQUIRE-ENTRY-001):
  - After gateway consolidation, the first Babel operation in each function was a gateway call that raised `BabelImportError` with the internal gateway identifier (e.g., `"UnknownLocaleError"`) rather than the public function name
  - Explicit `require_babel(feature_name)` added as the first statement in each function; error messages now consistently name the user-facing entry point
  - Location: `runtime/plural_rules.py`, `runtime/locale_context.py`

## [0.116.0] - 2026-02-20

### Changed (BREAKING)

- **`ValidationError.code` and `ValidationWarning.code` changed from `str` to `DiagnosticCode`** (ARCH-DIAG-CODE-TYPE-001):
  - Both fields were typed as bare `str`, requiring callers to manage raw string codes with no type safety; `Diagnostic.code` was already `DiagnosticCode`, making the two validation types incoherent with the rest of the diagnostics domain
  - Both fields are now `DiagnosticCode`; all construction sites in `validation/resource.py` updated; the new `_annotation_to_diagnostic_code()` helper promotes `Annotation.code: str` → `DiagnosticCode` using `DiagnosticCode[code]` with `PARSE_JUNK` as the fallback for unknown annotation codes
  - Callers comparing `error.code` or `warning.code` against string literals must update to `DiagnosticCode` enum members or use `.name` for string comparison
  - Location: `diagnostics/validation.py`, `validation/resource.py`

- **`DiagnosticCode.INVALID_CHARACTER` (3002) and `DiagnosticCode.EXPECTED_TOKEN` (3003) removed** (ARCH-DIAG-DEAD-CODES-001):
  - Both enum values were never referenced in production code; character-level and token-level errors are carried as raw strings in `Annotation.code` (the parser AST type), not as `DiagnosticCode` values; the enum members were unreachable dead code
  - `_annotation_to_diagnostic_code()` maps any `Annotation.code` string not matching a `DiagnosticCode` name (including `"INVALID_CHARACTER"` and `"EXPECTED_TOKEN"`) to `DiagnosticCode.PARSE_JUNK`, the canonical parse error code
  - Callers holding references to `DiagnosticCode.INVALID_CHARACTER` or `DiagnosticCode.EXPECTED_TOKEN` must migrate to `DiagnosticCode.PARSE_JUNK`
  - Location: `diagnostics/codes.py`

- **`DiagnosticFormatter.format_error` and `format_warning` are now strictly typed** (ARCH-DIAG-DUCK-TYPING-001):
  - Both methods previously accepted `object` with `getattr` fallbacks, allowing duck-typed callers to pass arbitrary objects; this pattern bypassed the domain type system and concealed misuse
  - Both methods now accept `ValidationError` and `ValidationWarning` respectively; an `isinstance` guard enforces the type at the entry point, raising `AssertionError` on violation
  - Duck-typed callers passing arbitrary objects with matching attribute names must migrate to proper `ValidationError` or `ValidationWarning` instances
  - Location: `diagnostics/formatter.py`

- **`_escape_control_chars` promoted from `DiagnosticFormatter` class method to module-level function** (ARCH-DIAG-ESCAPE-PROMOTE-001):
  - The function contains no formatter state and is called from multiple formatter methods; keeping it as a class method was an incorrect structural classification
  - It is now a module-level function in `diagnostics/formatter.py` and exported for test use; `DiagnosticFormatter._escape_control_chars(text)` no longer exists
  - Callers using `DiagnosticFormatter._escape_control_chars(text)` must update to `from ftllexengine.diagnostics.formatter import _escape_control_chars`
  - Location: `diagnostics/formatter.py`

- **`ValidationWarning.format()` gains `sanitize` and `redact_content` parameters** (FEAT-DIAG-WARNING-SANITIZE-001):
  - `ValidationError.format(sanitize=False, redact_content=False)` already supported sanitization; `ValidationWarning.format()` had no equivalent, leaving warning context strings always rendered raw
  - `ValidationWarning.format()` now accepts the same signature: `format(sanitize: bool = False, redact_content: bool = False)`; both methods delegate to `DiagnosticFormatter` for consistent output
  - Default values preserve existing behavior; callers not passing the new arguments are unaffected
  - Location: `diagnostics/validation.py`

- **`MessageIntrospection._variable_names` and `_function_names` removed from constructor** (ARCH-INTROSPECT-DERIVED-FIELDS-001):
  - Both fields are internal caches derived from `variables` and `functions`; declaring them with `init=True` (the default) allowed external callers to construct `MessageIntrospection` with inconsistent derived state, where `_variable_names` could differ from `frozenset(v.name for v in variables)`
  - Both fields changed to `field(init=False, repr=False, compare=False, hash=False)`; `__post_init__` computes them from the authoritative public fields using `object.__setattr__` (required for frozen dataclass mutation); consistency is now enforced by construction
  - Callers explicitly passing `_variable_names` or `_function_names` as keyword arguments must remove those arguments; callers using `introspect_message()` to obtain instances are unaffected
  - Location: `introspection/message.py`

### Changed

- **`IntrospectionVisitor._visit_expression` converted to `match/case`** (REFACTOR-INTROSPECT-VISIT-MATCH-001):
  - The method dispatched on expression types using six `if/elif isinstance()` branches with TypeIs guards, while every other dispatch site in the codebase uses structural pattern matching
  - Converted to a single exhaustive `match/case` block; semantics unchanged; cyclomatic complexity reduced from 7 to 1
  - Location: `introspection/message.py`

- **`IntrospectionVisitor._extract_function_call` context save/restore restructured** (REFACTOR-INTROSPECT-FUNC-LOOP-001):
  - Context was saved and restored inside both the `positional` and `named` argument loops, performing O(n) redundant save/restore operations per function call
  - Context is now saved once before both loops and restored once after via `try/finally`; semantics unchanged; per-iteration allocation overhead eliminated
  - Location: `introspection/message.py`

- **`_get_babel_currencies()` result cached across all locale lookups** (PERF-INTROSPECT-ISO-CURRENCIES-CACHE-001):
  - The function returns English CLDR currency name data (invariant across all locales) but carried no cache; every call to `_list_currencies_impl` for a new locale triggered a full Babel round-trip to obtain the same English currency map
  - `@lru_cache(maxsize=1)` applied; `_get_babel_currencies.cache_clear()` added to `clear_iso_cache()` to maintain cache coherence
  - Location: `introspection/iso.py`

- **Repeated `UnknownLocaleError` detection extracted to `_is_unknown_locale_error` helper** (REFACTOR-INTROSPECT-ISO-UNKNOWN-LOCALE-001):
  - The same 8-line `except Exception` block (lazy-import of `UnknownLocaleError`, `isinstance` check, fallback or re-raise) was duplicated verbatim in `_get_babel_territories`, `_get_babel_currency_name`, and `_get_babel_currency_symbol`
  - Extracted to a module-level `_is_unknown_locale_error(exc: Exception) -> bool` helper; all three sites reduced to a single-line conditional; one maintenance point if Babel's exception hierarchy changes
  - Location: `introspection/iso.py`

### Fixed

- **`_escape_control_chars` escaped only 4 of 33 C0 control characters** (SEC-DIAG-ESCAPE-COVERAGE-001):
  - The original implementation replaced only `\x1b` (ESC), `\r`, `\n`, `\t`; the remaining 29 C0 characters (0x00–0x08, 0x0b–0x0c, 0x0e–0x1a, 0x1c–0x1f) and DEL (0x7f) passed through unescaped into diagnostic output and log streams
  - Any of those characters embedded in message identifiers or user-supplied values could inject fake diagnostic lines into structured log output (log injection)
  - Fixed: a `str.maketrans` / `str.translate` table covering the full C0 range (0x00–0x1f) and 0x7f performs the mapping in a single O(n) pass; `\n`, `\r`, `\t`, and `\x1b` retain their conventional escape notation for readability
  - Location: `diagnostics/formatter.py`

- **`import json` in `DiagnosticFormatter._format_json` was suppressed without justification** (ARCH-DIAG-JSON-IMPORT-001):
  - The function-level `import json` carried `# noqa: PLC0415` (import outside top-level) without a documented circular-dependency justification; `json` is a stdlib module with no dependency on `diagnostics/`
  - Fixed: `import json` moved to module-level; the suppression removed
  - Location: `diagnostics/formatter.py`

- **`FluentLocalization._get_or_create_bundle` held write lock for all bundle accesses** (BUG-LOCALIZATION-BUNDLE-WRITELOCK-001):
  - Every public `FluentLocalization` method (`format_value`, `format_pattern`, `has_message`, etc.) routes through `_get_or_create_bundle`, which acquired the exclusive write lock for all accesses — including plain dict lookups on already-initialized bundles
  - After bundle initialization, all concurrent format operations serialized through the write lock, rendering the readers-writer lock ineffective and silently negating the concurrency guarantees documented in the public API
  - Fixed: `_get_or_create_bundle` now uses double-checked locking — read lock for the common already-initialized case (allows concurrent format operations); write lock acquired only when creating a new bundle, with a double-check after write-lock acquisition. Callers already holding the write lock (`add_resource`, `add_function`) use RWLock downgrading semantics (`_acquire_read` short-circuits via `_writer_held_reads`)
  - Location: `localization/orchestrator.py`

- **`FluentLocalization._resources_loaded` was dead state** (BUG-LOCALIZATION-RESOURCES-LOADED-DEAD-001):
  - `_resources_loaded: set[LocaleCode]` was declared in `__slots__`, initialized as an empty set in `__init__`, and populated in `_load_single_resource` via `.add(locale)`, but was never read by any method in the class
  - The unreachable set consumed memory proportional to the number of locales and provided zero observable behavior
  - Fixed: `_resources_loaded` removed from `__slots__`, `__init__`, and `_load_single_resource`
  - Location: `localization/orchestrator.py`

- **`FallbackInfo.message_id` typed as bare `str` instead of `MessageId`** (BUG-LOCALIZATION-FALLBACKINFO-MESSAGE-ID-TYPE-001):
  - The `message_id` field on `FallbackInfo` was annotated `str` while all other identifier fields across the localization domain use the `MessageId` semantic type alias; the inconsistency silently broke domain-level type contracts
  - Fixed: `message_id` field type changed to `MessageId`; `MessageId` added to the import from `ftllexengine.localization.types`
  - Location: `localization/loading.py`

- **`LoadSummary.get_all_junk` accumulated results in a mutable intermediate list** (BUG-LOCALIZATION-GETALLJUNK-MUTABLE-INTERMEDIATE-001):
  - The method built a mutable `list[Junk]` via `.extend()` then converted to `tuple` at return, introducing unnecessary heap allocation and contradicting the immutability principle governing the localization domain
  - Fixed: replaced with a generator expression passed directly to `tuple()`, eliminating the intermediate mutable container
  - Location: `localization/loading.py`

- **`IntrospectionVisitor` context state corrupted on `DepthGuard` exception** (BUG-INTROSPECT-CONTEXT-SAFETY-001):
  - Three context save/restore sites in `_visit_expression` (SelectExpression branch) and `_extract_function_call` (both argument loops) restored `self._context` only on the normal path; if `DepthGuard` raised `FrozenFluentError` mid-visit, `self._context` was left at the mutated value, corrupting subsequent visits on the same visitor instance
  - All three sites wrapped in `try/finally`; `self._context` is restored regardless of whether `DepthGuard` raises; `_visit_variant` hardened with `try/finally` for consistent defensive posture
  - Location: `introspection/message.py`

## [0.115.0] - 2026-02-19

### Changed (BREAKING)

- **`core/` package introduced; `locale_utils.py` promoted to `core/locale_utils.py`** (REFACTOR-CORE-LOCALE-001):
  - `ftllexengine.locale_utils` module removed; all functionality now lives in `ftllexengine.core.locale_utils`
  - Callers importing `get_system_locale`, `normalize_locale`, `get_babel_locale`, `clear_locale_cache` must update import paths to `ftllexengine.core.locale_utils`
  - `ftllexengine.core` package created as the home for cross-cutting utilities shared by both `syntax/` and `runtime/` domains
  - Location: `core/__init__.py`, `core/locale_utils.py` (new); `locale_utils.py` (removed)

- **`localization.py` split into `localization/` package** (REFACTOR-LOCALIZATION-SPLIT-001):
  - `ftllexengine.localization` is now a package (`localization/__init__.py`) instead of a single module; all public exports are re-exported from `__init__.py` — no import-path changes required for consumers
  - Internal structure: `localization/types.py` (PEP 695 type aliases), `localization/loading.py` (`ResourceLoader` protocol, `PathResourceLoader`, `LoadSummary`, `ResourceLoadResult`, `FallbackInfo`), `localization/orchestrator.py` (`FluentLocalization` class)
  - `LoadSummary` converted from manual frozen-object pattern (`object.__setattr__` + custom `__setattr__`/`__delattr__`) to `@dataclass(frozen=True, slots=True)` — raises `FrozenInstanceError` (subclass of `AttributeError`) on mutation attempts instead of the previous custom error
  - `ResourceLoader` protocol gains a `describe_path(locale, resource_id) -> str` method with a default implementation (`return f"{locale}/{resource_id}"`); `PathResourceLoader` overrides it to return the actual filesystem path; callers implementing `ResourceLoader` as a structural subtype must add `describe_path` to their class
  - `_check_mapping_arg` extracted as a `@staticmethod` on `FluentLocalization`; previously duplicated verbatim in both `format_value` and `format_pattern`
  - Location: `localization/__init__.py`, `localization/types.py`, `localization/loading.py`, `localization/orchestrator.py` (new); `localization.py` (removed)

- **`LoadStatus` moved to `ftllexengine.enums`** (REFACTOR-LOADSTATUS-ENUMS-001):
  - `LoadStatus` was defined in `localization.py`; now defined in `enums.py` and re-exported from `localization/__init__.py`
  - Callers importing `LoadStatus` from `ftllexengine.localization` are unaffected; callers importing from `ftllexengine.enums` gain access without a localization import
  - Location: `enums.py` (definition), `localization/__init__.py` (re-export)

- **Parser-only constants removed from `constants.py`** (REFACTOR-CONSTANTS-LOCALITY-001):
  - `MAX_PARSE_ERRORS` renamed to `_MAX_PARSE_ERRORS` and moved to `syntax/parser/core.py` — implementation detail private to the parser
  - `MAX_LOOKAHEAD_CHARS` renamed to `_MAX_LOOKAHEAD_CHARS` and moved to `syntax/parser/rules.py` — implementation detail private to the rule engine
  - `_MAX_IDENTIFIER_LENGTH` renamed to `MAX_IDENTIFIER_LENGTH` (public constant, cross-package security bound); `_MAX_NUMBER_LENGTH` and `_MAX_STRING_LITERAL_LENGTH` remain in `syntax/parser/primitives.py` as private parser-local constants
  - Callers importing `MAX_PARSE_ERRORS` or `MAX_LOOKAHEAD_CHARS` from `ftllexengine.constants` must update their imports; `MAX_IDENTIFIER_LENGTH` is now the public spelling (no leading underscore)
  - Location: `constants.py`, `syntax/parser/core.py`, `syntax/parser/rules.py`, `syntax/parser/primitives.py`

### Fixed

- **`get_system_locale()` default fallback not normalized** (BUG-LOCALE-NORMALIZE-FALLBACK-001):
  - The hardcoded fallback `"en_US"` bypassed `normalize_locale()`, returning a mixed-case string inconsistent with normalized locale codes (all lowercase)
  - Fixed: fallback is now `normalize_locale("en_US")` = `"en_us"`
  - Location: `core/locale_utils.py`

- **`clear_all_caches()` called `locale_utils.clear_locale_cache()` unconditionally** (BUG-CLEAR-CACHES-BABEL-GUARD-001):
  - `clear_all_caches()` in `__init__.py` called into `locale_utils` (now `core.locale_utils`) via the Babel-independent path; the call was missing from the post-move import chain and would fail in parser-only installations
  - Fixed: `clear_all_caches()` imports and calls `core.locale_utils.clear_locale_cache()` under the correct Babel-independent guard
  - Location: `src/ftllexengine/__init__.py`

- **`clear_all_caches()` docstring exposed private API `bundle._cache.clear()`** (BUG-INIT-PRIVATE-API-DOC-001):
  - Public docstring instructed callers to invoke `bundle._cache.clear()` (private attribute) for bundle-specific cache eviction, leaking an implementation detail through the public interface
  - Fixed: docstring updated to recommend recreating the `FluentBundle` instance instead
  - Location: `src/ftllexengine/__init__.py`

## [0.114.0] - 2026-02-19

### Changed (BREAKING)

- **`syntax/` domain hardened** (REFACTOR-SYNTAX-HARDEN-001):
  - `syntax/ast.py`: trailing blank lines removed from `Attribute`, `Comment`, and `Variant` class docstrings; docstrings now conform to single-line closing-quote form
  - `syntax/cursor.py`: unused `field` import removed from `dataclasses` import; `ParseError.expected` field default changed from `field(default_factory=tuple)` to `= ()` — `tuple()` is not a mutable default, `field(default_factory=...)` was unnecessary overhead
  - `syntax/parser/core.py`: `__all__` and `logger` module-level declarations moved above `_has_blank_line_between` to satisfy Pylint C0103/C0301 ordering; declarations now precede all module-level code they document
  - `syntax/parser/rules.py`: `ParseContext.__post_init__` replaced `object.__setattr__(self, ...)` with direct attribute assignment `self._depth_exceeded_flag = [False]`; `ParseContext` is not frozen, so `object.__setattr__` bypass was redundant
  - `syntax/position.py`: `__all__` expanded from `["column_offset", "line_offset"]` to include `format_position`, `get_error_context`, and `get_line_content`; the three omitted public functions were exported from the package but absent from `__all__`, creating an inconsistency between the module's declared surface and its actual exports
  - `syntax/serializer.py`: `_validate_select_expression` function removed — `SelectExpression.__post_init__` enforces the default-variant invariant at construction time, making the serializer's redundant post-construction re-check dead code; `SerializationValidationError` docstring updated to reflect the actual error cases (duplicate named args, invalid argument value types, invalid identifiers); the `isinstance(element, Placeable)` guard in `_serialize_pattern` replaced with bare `else` — after the `isinstance(element, TextElement)` branch, the only remaining type is `Placeable` (union is closed), so the redundant type check was removed; `_validate_resource` docstring updated to reflect current behavior (identifiers, call arguments, expression depth — not default-variant counting)
  - `syntax/serializer.py`: removed import of `count_default_variants` from `validation_helpers` (no longer needed after `_validate_select_expression` removal)
  - Location: `syntax/ast.py`, `syntax/cursor.py`, `syntax/parser/core.py`, `syntax/parser/rules.py`, `syntax/position.py`, `syntax/serializer.py`

### Changed

- **`syntax/validator.py` defensive checks documented as intentional architectural pattern** (REFACTOR-VALIDATOR-DEFENSE-IN-DEPTH-001):
  - `_validate_select_expression` previously validated `not select.variants` and `count_default_variants(select) != 1` without explaining why these checks exist alongside `SelectExpression.__post_init__` which enforces the same invariants at construction time
  - Docstring updated to explicitly document these as defense-in-depth checks: ASTs can be constructed via `object.__new__` + `object.__setattr__` to bypass `__post_init__` (e.g., deserialization, test fixtures, adversarial input); the validator is the last line of defense before invalid FTL is emitted
  - Inline comments updated: each check now states "Defense-in-depth: __post_init__ enforces X at construction. Guards against object.__new__ bypass."
  - This is a permanent architectural pattern — the diagnostic codes `VALIDATION_SELECT_NO_VARIANTS` and `VALIDATION_SELECT_NO_DEFAULT` remain reachable via the bypass scenario and their presence is correct
  - `test_select_without_variants_validator_defensive_check` and `test_select_with_zero_defaults_validator_defensive_check` docstrings updated to remove line-number references and state the defense-in-depth intent explicitly
  - Location: `syntax/validator.py`, `tests/test_validator.py`

- **`__init__.py` lazy-load dispatch converted to `match/case` with exhaustive guards** (REFACTOR-INIT-DISPATCH-001):
  - `_load_babel_independent` and the Babel-required block in `__getattr__` both used sequential `if name ==` chains; converted to `match/case` per the primary dispatch mechanism mandate
  - Added exhaustive `case _: raise AssertionError(f"__getattr__: unhandled Babel-... attribute {name!r}")` arms to both dispatch blocks; previously, adding a name to `_BABEL_REQUIRED_ATTRS` or `_BABEL_INDEPENDENT_ATTRS` without a corresponding handler caused a silent fallthrough to `raise AttributeError`, producing a misleading "module has no attribute" error instead of exposing the internal invariant violation
  - `AssertionError` is semantically correct here: the condition indicates a programming error in the library (frozenset and case arms are out of sync), not a legitimate caller attribute error
  - Public API behavior is unchanged; `AttributeError` is still raised for genuinely unknown attributes at line 171
  - `test_babel_required_fallthrough_to_attribute_error` renamed to `test_babel_required_unhandled_attr_raises_assertion_error` and updated to assert `AssertionError` with match `"unhandled Babel-required attribute"`; the test exercises the `case _:` arm by temporarily injecting a fake attribute into `_BABEL_REQUIRED_ATTRS`
  - Location: `src/ftllexengine/__init__.py`, `tests/test_init_error_paths.py`

## [0.113.0] - 2026-02-19

### Changed (BREAKING)

- **`diagnostics/` domain hardened** (REFACTOR-DIAGNOSTICS-HARDEN-001):
  - `DiagnosticCode` enum values reordered to strict numeric sequence within each range (1000–1099, 2000–2999, 3000–3999, 4000–4999, 5000–5199): `MAX_DEPTH_EXCEEDED` (2010) was previously positioned out of order between `CYCLIC_REFERENCE` (2001) and `NO_VARIANTS` (2002); now placed after `PATTERN_INVALID` (2009), matching its integer value
  - Numeric values themselves are unchanged — this is a source-order fix only, not a value change; all integer codes remain API-stable
  - Dead code removed from `diagnostics/errors.py`:`if TYPE_CHECKING: pass` block (lines 23-24) was imported and immediately discarded with no effect; removed entirely
  - Unreachable branch annotated in `diagnostics/formatter.py`: `assert_never(self.output_format)` exhaustiveness guard marked `# pragma: no cover`; unreachable by construction (all `OutputFormat` members handled above)
  - Unreachable branch annotated in `diagnostics/errors.py`: Pre-freeze `object.__setattr__` path in `__setattr__` marked `# pragma: no cover`; unreachable on CPython because `__init__` uses `object.__setattr__` directly and `Exception.__init__` bypasses Python-level `__setattr__` on CPython

- **`introspection/` domain hardened** (REFACTOR-INTROSPECTION-HARDEN-001):
  - `extract_references_by_attribute` was exported from `introspection/__init__.py` but missing from `message.__all__`; inconsistency resolved by adding to `__all__`
  - `_visit_pattern_element` match/case lacked exhaustiveness guard; `assert_never` added for the closed `TextElement | Placeable` union, turning silent misses into immediate `AssertionError`
  - `if message.value:` truthiness check in `introspect_message` replaced with `if message.value is not None:`; `Pattern` is a dataclass with no `__bool__` override and is always truthy, making the False branch permanently dead when the condition was a truthiness test
  - Dead `if func.arguments:` guard removed from `_extract_function_call`; `arguments: CallArguments` is typed non-nullable and `CallArguments` has no `__bool__` override so the guard was always True; argument loops are empty no-ops when `positional=()` and `named=()`, making the guard redundant
  - `introspection/iso.py`: removed useless `if TYPE_CHECKING: pass` block and accompanying unused `TYPE_CHECKING` import
  - `introspection/iso.py`: three self-referential `raise exc from exc` chains corrected to `raise exc from None` (suppresses implicit `ImportError` context that polluted the exception chain)
  - Location: `introspection/message.py`, `introspection/iso.py`

- **`syntax/validator.py` hardened with exhaustiveness guards** (REFACTOR-VALIDATOR-HARDEN-001):
  - `_validate_entry`, `_validate_pattern_element`, `_validate_inline_expression` lacked `case _:` exhaustiveness guards; unknown AST node types silently bypassed validation; `raise TypeError(...)` guards added to all three dispatch methods
  - Location: `syntax/validator.py`

### Fixed

- **`_validate_select_expression` crashes on nested `SelectExpression` selectors** (BUG-VALIDATOR-SELECTOR-DISPATCH-001):
  - Selector was validated via `_validate_inline_expression` directly; `SelectExpression` is not an `InlineExpression`, so directly-constructed ASTs with a `SelectExpression` as the outer selector raised `TypeError` at the exhaustiveness guard
  - Changed to `_validate_expression` (general dispatcher), routing both `SelectExpression` and `InlineExpression` selectors correctly
  - Location: `syntax/validator.py`

## [0.112.0] - 2026-02-18

### Changed (BREAKING)

- **`analysis/` domain hardened** (REFACTOR-ANALYSIS-HARDEN-001):
  - `build_dependency_graph` removed -- dead production code; `validation/resource.py` maintains its own private `_build_dependency_graph` which is the sole consumer of graph construction logic
  - `canonicalize_cycle` made private (`_canonicalize_cycle`) -- internal deduplication detail, not a public analysis primitive
  - `entry_dependency_set` return type changed from `set[str]` to `frozenset[str]` -- enforces immutability at API boundary; cascading type change through `FluentBundle._msg_deps`/`_term_deps` and `validate_resource` known deps parameters (`Mapping[str, frozenset[str]]`)
  - `detect_cycles` cycle deduplication changed from string keys to canonical tuple keys -- eliminates redundant string construction and arrow-join overhead during detection
  - `_NodeState` enum replaced with bool constants (`_ENTERING`/`_EXITING`) -- two-member enums with no associated data are overengineered; bool comparison is a single CPU instruction
  - Defensive `pragma: no cover` / `pragma: no branch` guards removed from unreachable code paths -- masking dead code behind coverage pragmas violates auditability
  - Public API surface: `detect_cycles`, `entry_dependency_set`, `make_cycle_key`
  - Location: `analysis/graph.py`, `analysis/__init__.py`, `runtime/bundle.py`, `validation/resource.py`

- **`runtime/` domain hardened** (REFACTOR-RUNTIME-HARDEN-001):
  - `IntegrityCacheEntry.to_tuple()` renamed to `as_result()`
  - `ResolutionContext._total_chars` encapsulated behind `total_chars` read-only property; resolver uses public API instead of private attribute access
  - `fluent_function` decorator no longer wraps callables when `inject_locale=False` -- returns the original function unchanged, eliminating unnecessary indirection
  - `LocaleContext._factory_token` excluded from dataclass `repr`, `compare`, and `hash` via `field()` metadata -- sentinel no longer leaks into equality semantics
  - `FluentResolver` cached on `FluentBundle` instance instead of per-call allocation; invalidated on `add_function()`, transparent to `add_resource()` (resolver references mutable dicts directly)
  - Location: `runtime/cache.py`, `runtime/resolution_context.py`, `runtime/function_bridge.py`, `runtime/locale_context.py`, `runtime/bundle.py`, `runtime/resolver.py`

### Fixed

- **`format_number` crashes on `Decimal` infinity/NaN** (BUG-DECIMAL-SPECIAL-001):
  - `math.isinf()` and `math.isnan()` raise `TypeError` when called with `Decimal` arguments; special-value detection now uses type-aware predicates (`Decimal.is_finite()` for Decimal, `math.isinf()`/`math.isnan()` for float)
  - Applications passing `Decimal('Infinity')` or `Decimal('NaN')` through locale formatting no longer crash
  - Location: `runtime/locale_context.py`

- **Silent exception swallowing in `NUMBER`/`CURRENCY` pattern parsing** (BUG-SILENT-EXCEPT-001):
  - Bare `except Exception: pass` in `number_format` and `currency_format` replaced with `logger.debug()` calls, providing observability for parse failures that silently disable precision capping
  - Location: `runtime/functions.py`

## [0.111.0] - 2026-02-18

### Changed (BREAKING)

- **`core/` domain hardened** (REFACTOR-CORE-HARDEN-001):
  - `DepthGuard` API reduced to two safe patterns: context manager (`with guard:`) and explicit `check()`. Removed `increment()`, `decrement()`, `reset()`, `is_exceeded()`, and `depth` property -- these bypassed safety invariants (increment without limit check, silent floor on decrement, mid-operation state reset)
  - `babel_compat` dead production API removed: `BabelNumbersProtocol`, `BabelDatesProtocol`, `get_babel_numbers()`, `get_babel_dates()`, `get_unknown_locale_error()` -- zero production consumers; protocols typed modules as class instances
  - `core/errors.py` re-export shim deleted -- zero consumers; all code imports directly from `ftllexengine.diagnostics`
  - `core/__init__.py` exports reduced to `DepthGuard` and `depth_clamp` only
  - `babel_compat._check_babel_available` changed from `lru_cache` to module-level sentinel -- callers that used `.cache_clear()` must now reset `_babel_available = None` directly
  - Location: `core/depth_guard.py`, `core/babel_compat.py`, `core/__init__.py`

### Fixed

- **`DepthGuard.__post_init__` used `object.__setattr__` on non-frozen dataclass** (BUG-DEPTHGUARD-SETATTR-001):
  - Cargo-culted from frozen dataclass pattern; replaced with plain attribute assignment
  - Location: `core/depth_guard.py`

## [0.110.0] - 2026-02-17

### Changed

- **Parsing domain internal refactoring** (REFACTOR-PARSING-001):
  - `_build_currency_maps_from_cldr` decomposed into three focused helpers: `_collect_all_currencies`, `_build_symbol_mappings`, `_build_locale_currency_map`
  - `parse_currency` split into phase-based orchestration with `_detect_currency_symbol` (longest-match-first regex) and `_parse_currency_amount` (amount extraction and decimal parsing)
  - Common CLDR pattern extraction in `dates.py` consolidated into `_extract_cldr_patterns`, eliminating duplication between `_get_date_patterns` and `_get_datetime_patterns`
  - Lazy Babel imports across `numbers.py`, `currency.py`, and `dates.py` replaced with centralized `require_babel()` from `core.babel_compat`, eliminating duplicated `try/except ImportError` blocks
  - `_get_localized_era_strings` switched from `try/except ImportError` to `is_babel_available()` guard for graceful degradation
  - `assert currency_code is not None` replaced with explicit `if currency_code is None:` guard returning structured error tuple
  - No public API changes; all function signatures and return types preserved

- **Currency symbol detection collapsed to single-pattern architecture** (REFACTOR-CURRENCY-SINGLE-PATTERN-001):
  - Removed `_get_currency_pattern_fast()` two-tier detection; `_detect_currency_symbol` now uses a single longest-match-first regex built from the complete merged symbol set (fast tier + CLDR)
  - Multi-char CLDR symbols (`Rs`, `kr.`, `$AU`) are no longer shadowed by single-char fast-tier prefixes (`R`, `kr`, `$`)
  - `_get_currency_pattern_full()` renamed to `_get_currency_pattern()`; `clear_currency_caches()` clears 3 caches instead of 4
  - Fast-tier data constants retained for merge-priority logic and Babel-absent fallback
  - No public API changes

### Fixed

- **CLDR symbol shadowing in currency detection** (BUG-CURRENCY-SHADOW-001):
  - Multi-char CLDR-only symbols (`Rs`, `kr.`, `$AU`) were shadowed by single-char fast-tier regex matches (`R`, `kr`, `$`), causing silent wrong results in financial parsing (e.g., `kr. 500` in da_DK parsed as `(0.500, SEK)` instead of `(500, DKK)` -- a 1000x magnitude error)
  - 39 CLDR symbols were shadowed; locale-to-currency fallback was unreachable for these symbols
  - Root cause: tiered detection tried fast-tier regex first; on match, skipped the full CLDR regex that would have found the correct longer symbol
  - Fix: single pattern architecture with longest-match-first ordering guarantees multi-char symbols match before their single-char prefixes

## [0.109.0] - 2026-02-17

### Changed (BREAKING)

- **Cache integrity strict decoupled from bundle strict** (REFACTOR-INTEGRITY-STRICT-001):
  - `CacheConfig` gains `integrity_strict: bool = True` field controlling cache corruption and write-conflict behavior
  - `IntegrityCache.strict` now sourced from `CacheConfig.integrity_strict` instead of `FluentBundle.strict`
  - `FluentBundle.strict` controls formatting error behavior only (fail-fast vs fallback)
  - `CacheConfig.integrity_strict` controls cache corruption response only (raise vs silent evict)
  - `CacheConfig.__post_init__` validates all numeric fields are positive at construction time
  - Location: `runtime/cache_config.py`, `runtime/bundle.py`, `runtime/cache.py`

- **`FluentLocalization` upgraded from `RLock` to `RWLock`** (REFACTOR-L10N-RWLOCK-001):
  - `FluentLocalization` internal lock changed from `threading.RLock` to `RWLock`
  - Read operations (`format_value`, `format_pattern`, `has_message`, `get_cache_stats`) acquire read lock (concurrent)
  - Write operations (`add_resource`, `add_function`, `clear_cache`) acquire write lock (exclusive)
  - Location: `localization.py`

- **Context manager semantics unified** (REFACTOR-CONTEXT-MANAGER-001):
  - `FluentLocalization.__enter__`/`__exit__` now uses cache invalidation tracking (matching `FluentBundle`)
  - Previous behavior: acquired/released internal lock on enter/exit
  - New behavior: tracks modification state; clears cache on exit only if modified during context
  - Both `FluentBundle` and `FluentLocalization` context managers now have identical semantics
  - Location: `localization.py`

### Fixed

- **`FluentLocalization` strict mode contract breach** (BUG-L10N-STRICT-001):
  - `_handle_message_not_found` returned fallback tuple regardless of `strict=True`
  - `FluentLocalization(strict=True)` now raises `FormattingIntegrityError` on missing messages, matching `FluentBundle` behavior
  - Added `strict` property and `_raise_strict_error` method to `FluentLocalization`
  - Location: `localization.py`

- **`IntegrityCache._make_hashable` Mapping ABC path bypassed node budget** (BUG-HASHABLE-NODE-BUDGET-001):
  - `Mapping` ABC types (e.g., `ChainMap`) recursed via `IntegrityCache._make_hashable(v, depth - 1)` instead of `_recurse(v)`, bypassing the `_counter` node budget protection
  - Malicious deeply-nested `Mapping` values could cause unbounded recursion
  - Fix: Mapping ABC path now uses `_recurse(v)` consistent with other collection paths
  - Location: `runtime/cache.py`

- **`FrozenFluentError` freeze ordering** (BUG-FROZEN-ERROR-INIT-001):
  - `super().__init__(message)` was called after `object.__setattr__(self, "_frozen", True)`, preventing `Exception.__init__` from setting `self.args`
  - On CPython this worked due to implementation details, but could fail on PyPy or free-threaded builds
  - Fix: `super().__init__(message)` now called before `_frozen = True`
  - Location: `diagnostics/errors.py`

- **`WriteConflictError.new_seq` reported stale sequence** (BUG-WRITE-CONFLICT-SEQ-001):
  - `WriteConflictError` reported `new_seq=self._sequence` (current) instead of `new_seq=self._sequence + 1` (would-be next)
  - Fix: reports the sequence number the conflicting write would have received
  - Location: `runtime/cache.py`

## [0.108.0] - 2026-02-15

### Changed (BREAKING)

- **Cache configuration extracted to `CacheConfig` dataclass** (REFACTOR-CACHE-CONFIG-001):
  - `FluentBundle.__init__` replaces 7 individual cache keyword arguments (`enable_cache`, `cache_size`, `cache_write_once`, `cache_enable_audit`, `cache_max_audit_entries`, `cache_max_entry_weight`, `cache_max_errors_per_entry`) with a single `cache: CacheConfig | None = None` parameter
  - `FluentBundle.for_system_locale()` factory method updated with the same signature change
  - `FluentLocalization.__init__` replaces `enable_cache` and `cache_size` with `cache: CacheConfig | None = None`
  - `FluentLocalization.cache_size` property removed; replaced by `cache_config` property returning `CacheConfig | None`
  - `CacheConfig` is a frozen dataclass with `size`, `write_once`, `enable_audit`, `max_audit_entries`, `max_entry_weight`, `max_errors_per_entry` fields
  - `cache=None` (default) disables caching; `cache=CacheConfig()` enables caching with defaults
  - Exported from top-level package: `from ftllexengine import CacheConfig`
  - Location: `runtime/cache_config.py` (new), `runtime/bundle.py`, `localization.py`

- **`LoadSummary` converted to computed-property architecture** (REFACTOR-LOAD-SUMMARY-001):
  - `LoadSummary` changed from frozen dataclass with `object.__setattr__` workaround to `__slots__`-based immutable class
  - `total_attempted`, `successful`, `not_found`, `errors`, `junk_count` changed from stored fields to computed `@property` methods derived from the `results` tuple
  - `LoadSummary.error_count` property removed; use `LoadSummary.errors` instead (identical semantics, `error_count` was a trivial alias)
  - Eliminates pre-computed field drift risk; all statistics always consistent with `results`
  - Location: `localization.py`

### Changed

- **`FunctionSignature.param_dict` cached as frozen mapping** (PERF-FUNCTION-SIGNATURE-001):
  - `FunctionSignature` now pre-computes `param_dict: MappingProxyType[str, str]` in `__post_init__` from the `params` tuple
  - Eliminates repeated `dict()` construction on every function call during resolution
  - Read-only `MappingProxyType` wrapper preserves the immutability invariant
  - Location: `runtime/value_types.py`

- **`entry_dependency_set()` extracted as public helper** (REFACTOR-DEPENDENCY-SET-001):
  - `entry_dependency_set(entry)` computes the set of message/term identifiers referenced by a `Message` or `Term`
  - Extracted from inline logic in `_build_dependency_graph()` in `validation/resource.py`
  - Location: `analysis/graph.py`

- **`_collect_pending_entries()` extracted from `_register_resource`** (REFACTOR-COLLECT-PENDING-001):
  - Registration logic for collecting messages, terms, and junk from parsed resources extracted into standalone helper
  - Reduces `_register_resource` complexity and improves testability
  - Location: `runtime/bundle.py`

### Fixed

- **DiagnosticFormatter ANSI escape injection via user-controlled fields** (BUG-FORMATTER-ANSI-INJECTION-001):
  - `_escape_control_chars()` did not escape `\x1b` (ESC), allowing user input in `ftl_location` or `help_url` fields to inject ANSI escape sequences into formatter output
  - `help_url` field was not passed through `_escape_control_chars()` at all in `_format_rust()`
  - Fix: `\x1b` now escaped as `\\x1b`; `help_url` field now escaped in Rust format output
  - Location: `diagnostics/formatter.py`

- **`PathResourceLoader._validate_resource_id` inconsistent error message** (BUG-VALIDATE-RESOURCE-MSG-001):
  - Leading path separator rejection (backslash on non-Windows) used `"must not start with path separator"` instead of the `"not allowed in resource_id"` pattern used by the other three validation paths (absolute path, traversal, whitespace)
  - Inconsistency caused programmatic `match=` assertions to miss this code path
  - Fix: error message now uses `"Leading path separator not allowed in resource_id"` for consistency
  - Location: `localization.py`

## [0.107.0] - 2026-02-14

### Changed (BREAKING)

- **Value types extracted to `runtime.value_types` module** (REFACTOR-VALUE-TYPES-001):
  - `FluentNumber`, `FluentValue`, `FluentFunction`, `FunctionSignature` moved from `runtime.function_bridge` to `runtime.value_types`
  - `function_bridge` re-exports all symbols for compatibility; direct imports from `function_bridge` continue to work
  - Canonical import path: `from ftllexengine.runtime.value_types import FluentNumber, FluentValue`
  - Rationale: separates core value type definitions from registry/bridge machinery
  - Location: `runtime/value_types.py` (new), `runtime/function_bridge.py`

- **Resolution context extracted to `runtime.resolution_context` module** (REFACTOR-RESOLUTION-CONTEXT-001):
  - `GlobalDepthGuard`, `ResolutionContext` moved from `runtime.resolver` to `runtime.resolution_context`
  - `resolver` re-exports both symbols for compatibility
  - Canonical import path: `from ftllexengine.runtime.resolution_context import ResolutionContext`
  - Rationale: `ResolutionContext` and `GlobalDepthGuard` are independent of `FluentResolver` and used by external code
  - Location: `runtime/resolution_context.py` (new), `runtime/resolver.py`

- **Validation resource.py deduplication** (REFACTOR-VALIDATION-DEDUP-001):
  - `_collect_entries()` Message/Term handling consolidated into shared `_check_entry()` helper
  - `_build_dependency_graph()` reference resolution consolidated into `_resolve_reference()`, node building into `_add_entry_nodes()`, known entry handling into `_add_known_entries()`
  - No public API changes; internal refactor only
  - Location: `validation/resource.py`

### Added

- **FluentLocalization API surface parity with FluentBundle**:
  - `has_attribute(message_id, attribute)`: check attribute existence across fallback chain
  - `get_message_ids()`: union of message IDs from all bundles, priority-ordered
  - `get_message_variables(message_id)`: delegate to first bundle with the message
  - `get_all_message_variables()`: merge variables from all bundles (first-wins)
  - `introspect_term(term_id)`: delegate to first bundle with the term
  - `__enter__` / `__exit__`: context manager support (acquires/releases RLock)
  - Location: `localization.py`

### Changed

- **DiagnosticFormatter exhaustive match/case with `assert_never()`** (MODERNIZE-FORMATTER-EXHAUSTIVE-001):
  - `format()` match/case on `OutputFormat` StrEnum now includes `case _: assert_never(self.output_format)` default branch
  - Catches future enum additions at type-check time; eliminates coverage.py phantom partial branch (91->exit)
  - Severity string formatting extracted to `_severity_str()` helper to keep `_format_rust()` within branch limit
  - Location: `diagnostics/formatter.py`

- **`Diagnostic.format_error()` delegates to `DiagnosticFormatter`** (SIMPLIFY-FORMATTER-DELEGATION-001):
  - `Diagnostic.format_error()` in `codes.py` now delegates to `DiagnosticFormatter().format(self)` instead of maintaining a parallel Rust-style formatting implementation
  - Eliminates divergence risk between two near-identical formatting paths
  - `_format_rust()` and `_format_json()` now include `resolution_path` in output (was only in the old `format_error()` implementation)
  - `format_error()` output now includes control-character escaping via `_escape_control_chars()` (security hardening)
  - Location: `diagnostics/codes.py`, `diagnostics/formatter.py`

- **`isinstance` fast paths in `format_error()` / `format_warning()`** (PERF-FORMATTER-FASTPATH-001):
  - Primary callers always pass `ValidationError` / `ValidationWarning` with known attributes; `isinstance` check enables direct attribute access on the fast path
  - Duck-typing `getattr()` fallback preserved for third-party objects
  - Location: `diagnostics/formatter.py`

- **Serializer: removed dead guard on `FunctionReference.arguments`** (SIMPLIFY-SERIALIZER-DEAD-GUARD-001):
  - `_validate_expression` wrapped `_validate_call_arguments` in `if expr.arguments:` for the `FunctionReference` case
  - `FunctionReference.arguments` is typed `CallArguments` (required field); dataclass instances are always truthy, so the guard was dead code
  - `TermReference.arguments` retains its guard (`CallArguments | None`, genuinely optional)
  - Location: `syntax/serializer.py`

- **Serializer: exhaustive `assert_never()` on variant key match/case** (SIMPLIFY-SERIALIZER-EXHAUSTIVE-VARIANT-KEY-001):
  - `_serialize_select_expression` match on `variant.key` dispatched `Identifier` and `NumberLiteral` without a default branch
  - Added `case _ as unreachable: assert_never(unreachable)` consistent with other match dispatches in the same file (lines 519, 771, 833)
  - Documents the type-system invariant (`VariantKey = Identifier | NumberLiteral`)
  - Location: `syntax/serializer.py`

### Fixed

- **`get_error_context` missing marker at EOF after trailing newline** (BUG-POSITION-EOF-MARKER-001):
  - When `pos` pointed at EOF after a trailing newline (e.g., `pos == len(source)` where `source[-1] == '\n'`), `line_offset` resolved to `len(lines)` (past all `splitlines()` content) and the marker was never emitted
  - Function contract requires unconditional marker presence for non-empty source; callers had to guard with `assume(line_num < len(lines))` to avoid assertion failures
  - Fix: emit marker on an empty line when `line_num >= len(lines)`, consistent with the existing loop logic for in-range lines
  - Location: `syntax/position.py` `get_error_context()`

## [0.106.0] - 2026-02-11

### Fixed

- **Serializer separate-line mode decision unstable across roundtrips** (BUG-SERIALIZER-MODE-INSTABILITY-001):
  - Different bug category from 0.104.0/0.105.0 emission bugs: this is a **decision-layer** convergence failure, not an emission-layer wrapping gap
  - `_pattern_needs_separate_line` cross-element check triggered separate-line mode for ANY `TextElement` starting with a space after a newline-ending element, including `WHITESPACE_ONLY` and `SYNTAX_LEADING` content that per-line wrapping already handles
  - The serializer wrapped the ambiguous content in a `StringLiteral` placeable (correct), but this transformed the `TextElement` into a `Placeable` node in the re-parsed AST; the cross-element check does not inspect `Placeable` nodes, so separate-line mode did not trigger on re-serialization, producing different output: `S(P(x)) != S(P(S(P(x))))`
  - Example: source `aaaaa =\n    h\n           \n` (whitespace-only continuation line) parsed and serialized to S1 in separate-line mode; S1 parsed to an AST with a `Placeable` instead of `TextElement`, serialized to S2 in inline mode; S1 != S2
  - Root cause: the intra-element check (added in 0.105.0 refactor) correctly used `_classify_line` and only triggered for `NORMAL` lines; the cross-element check (predating the refactor) did not classify, triggering unconditionally; the two checks were inconsistent
  - Fix: cross-element check now classifies the first line of the `TextElement` via `_classify_line` and only triggers separate-line mode for `NORMAL` content, matching the intra-element check; `WHITESPACE_ONLY` and `SYNTAX_LEADING` content goes through per-line wrapping in `_emit_classified_line` without mode change
  - Invariant enforced: separate-line mode activates only for `NORMAL` lines with leading whitespace (the one case where per-line wrapping cannot help, because the parser absorbs content whitespace as structural indent); all other line kinds are handled by `_emit_classified_line` without requiring a mode change
  - Location: `syntax/serializer.py` `_pattern_needs_separate_line()`

## [0.105.0] - 2026-02-10

### Changed

- **Serializer pattern emission refactored to classification-based dispatch** (REFACTOR-SERIALIZER-PATTERN-001):
  - Replaced three interleaved methods (`_serialize_pattern`, `_serialize_text_element`, `_pattern_needs_separate_line`) with a unified continuation line classification model
  - New `_LineKind` enum (`EMPTY`, `WHITESPACE_ONLY`, `SYNTAX_LEADING`, `NORMAL`) classifies each continuation line exactly once; a single `match/case` dispatch point selects the correct wrapping strategy
  - `_classify_line()` pure function and `_escape_text()` (brace-only escaping) extracted as module-level functions, enabling independent testing and reuse
  - `_emit_classified_line()` static method serves as the single dispatch point for all continuation line ambiguity classes
  - All `match/case` dispatches now use `assert_never()` exhaustiveness guards (`_serialize_entry`, `_serialize_expression`, `_emit_classified_line`) to catch missing cases at type-check time when new AST variants are added
  - `_serialize_expression` uses full structural destructuring in patterns (`StringLiteral(value=value)`, `TermReference(id=Identifier(name=name), ...)`) instead of body-level attribute access
  - No public API changes; `serialize()` and `FluentSerializer.serialize()` semantics preserved
  - Location: `syntax/serializer.py`

### Fixed

- **Serializer roundtrip idempotence failure on `SYNTAX_LEADING` continuation lines with content whitespace** (BUG-SERIALIZER-WS-SYNTAX-002):
  - Same bug class as BUG-SERIALIZER-WS-SYNTAX-001 (fixed in 0.104.0): syntactically ambiguous whitespace in serializer output; residual case missed by the original fix and inherited by the 0.105.0 classification refactor
  - When a continuation line had content spaces preceding a syntax character (`.`, `*`, `[`), e.g., `"dS7aQ\n      .h?Q"`, the `SYNTAX_LEADING` emission branch wrapped the syntax character in a `StringLiteral` placeable (`{ "." }`) but emitted the preceding content spaces as raw text
  - The FTL parser computes common indent as the minimum indent across all continuation lines; structural indent (4 spaces) plus raw content spaces (e.g., 6 spaces = 10 total) became the common indent, and all 10 spaces were stripped during common-indent removal, losing the 6 content spaces
  - Re-serializing the parsed AST produced only the 4-space structural indent before the placeable, breaking idempotence: `S(AST) != S(P(S(AST)))`
  - Fix: `_emit_classified_line` `SYNTAX_LEADING` branch now wraps leading content spaces in a `StringLiteral` placeable (`{ "      " }{ "." }...`), matching the treatment already used by `WHITESPACE_ONLY` and leading-whitespace-after-`=`; the parser sees the spaces as expression content (opaque to indent stripping), preserving them through roundtrip
  - Invariant enforced: all content whitespace preceding the first non-whitespace character on a continuation line must be placeable-wrapped; raw spaces are indistinguishable from structural indent
  - Location: `syntax/serializer.py` `_emit_classified_line()`

- **`Diagnostic.__str__` returns raw dataclass repr instead of human-readable message** (BUG-DIAGNOSTIC-STR-001):
  - `Diagnostic` (frozen dataclass) had no `__str__` method; `str(diagnostic)` returned the full `repr()` with all fields including `None` values, e.g., `Diagnostic(code=<DiagnosticCode.VARIABLE_NOT_PROVIDED: 1005>, message="...", span=None, ...)`
  - All `FrozenFluentError` construction sites use `str(diag)` as the `message` parameter, so `error.message` and `str(error)` both returned the raw repr
  - Users calling `str(error)` in logging, error display, or exception handlers saw opaque dataclass output instead of the human-readable message
  - Fix: Added `__str__` to `Diagnostic` returning `self.message`; `repr()` unchanged for debugging
  - Location: `diagnostics/codes.py` `Diagnostic.__str__()`

## [0.104.0] - 2026-02-09

### Fixed

- **Serializer roundtrip idempotence failure on patterns with leading whitespace** (BUG-SERIALIZER-LEADING-WS-001):
  - When a pattern's first `TextElement` started with spaces (e.g., programmatically constructed `TextElement(value=' 0')`), the serializer emitted the spaces inline after `= `, producing `    .a =  0`
  - On re-parse, the FTL parser consumed all post-`=` whitespace as syntax, yielding value `0` (space lost); re-serializing then produced `    .a = 0`, breaking idempotence: `serialize(parse(serialize(ast))) != serialize(ast)`
  - Fix: `_serialize_pattern` now detects leading spaces in the first `TextElement` and wraps them in a `StringLiteral` placeable (`{ " " }`), consistent with how braces (`{`, `}`) and line-start syntax characters (`[`, `*`, `.`) are already wrapped when syntactically ambiguous
  - Location: `syntax/serializer.py` `_serialize_pattern()`

- **Serializer roundtrip idempotence failure on multiline patterns with whitespace-only continuation lines** (BUG-SERIALIZER-BLANK-LINE-001):
  - Same bug class as BUG-SERIALIZER-LEADING-WS-001: syntactically ambiguous whitespace in serializer output
  - When a `TextElement` contained embedded newlines with whitespace-only content between them (e.g., `"foo\n   \nbar"`), the serializer's `text.replace("\n", "\n    ")` created continuation lines where structural indent plus content whitespace produced a whitespace-only line
  - The FTL parser treats whitespace-only continuation lines as blank lines and strips all whitespace during common-indent removal, losing content; re-serializing produced different output, breaking idempotence
  - Fix: `_serialize_pattern` now splits multiline text line-by-line; whitespace-only continuation lines are wrapped in `StringLiteral` placeables (`{ "   " }`); `_pattern_needs_separate_line` refined to skip whitespace-only lines (handled by placeable wrapping, not separate-line mode)
  - Location: `syntax/serializer.py` `_serialize_pattern()`, `_pattern_needs_separate_line()`

- **Serializer roundtrip failure on continuation lines with whitespace-preceded syntax characters** (BUG-SERIALIZER-WS-SYNTAX-001):
  - Same bug class as BUG-SERIALIZER-LEADING-WS-001 and BUG-SERIALIZER-BLANK-LINE-001: syntactically ambiguous content in serializer output
  - When a `TextElement` contained a continuation line where content whitespace preceded a syntax character (`.`, `*`, `[`), e.g., `"hello\n           ."`, the serializer emitted the line as-is after structural indent: `               .`
  - The FTL parser strips all leading whitespace to find the first non-whitespace character; finding `.` (or `*`, `[`), it stops reading the pattern and attempts to parse a structural construct (attribute/variant), which fails, producing `Junk`
  - The existing fix in `_serialize_text_element` wrapped syntax characters at position 0 of a continuation line but not when preceded by content spaces on the same line
  - Fix: `_serialize_text_element` now scans past leading spaces at continuation line starts to find the first non-whitespace character; if it is a syntax character, the spaces are emitted as text and the character is wrapped in a `StringLiteral` placeable (e.g., `           { "." }`)
  - Location: `syntax/serializer.py` `_serialize_text_element()`

## [0.103.0] - 2026-02-05

### Dependencies

- **Babel**: Minimum version raised from 2.17.0 to 2.18.0
  - CLDR 47 data (improved locale data accuracy)
  - Performance improvement in number pattern matching
  - Fixed compact currency formatting for exactly 1000
  - Official Python 3.14 support

### Added

- **`get_cldr_version()` introspection function** (FEAT-CLDR-VERSION-001):
  - Returns the CLDR version string from Babel for diagnostics
  - Useful for debugging locale-specific formatting differences
  - Available from `ftllexengine.introspection` and `ftllexengine.core.babel_compat`
  - Location: `core/babel_compat.py`

### Changed

- **CLDR documentation URL updated to `latest`**:
  - `plural_rules.py` docstring URL now points to `charts/latest/` instead of versioned `charts/47/`
  - Ensures documentation remains current as CLDR versions evolve

## [0.102.0] - 2026-02-03

### Added

- **`FluentBundle.function_registry` read-only property** (API-BUNDLE-REGISTRY-001):
  - Provides public access to the `FunctionRegistry` without requiring `bundle._function_registry` (SLF001 violation)
  - Location: `runtime/bundle.py`

### Fixed

- **`IntegrityCache.get_stats()` return type annotation omitted `bool`** (FIX-CACHE-STATS-TYPE-001):
  - Return type was `dict[str, int | float]` but actual returned dict includes `bool` values for `write_once`, `strict`, and `audit_enabled` keys
  - While technically valid in Python (bool subclasses int), the annotation was misleading for static analysis and IDE tooling
  - Updated to `dict[str, int | float | bool]` in `IntegrityCache.get_stats()`, `FluentBundle.get_cache_stats()`, and `FluentLocalization.get_cache_stats()`
  - Location: `runtime/cache.py`, `runtime/bundle.py`, `localization.py`

- **Duplicate `BabelImportError` class in `introspection/iso.py`** (FIX-BABEL-IMPORT-DUP-001):
  - `iso.py` defined its own `BabelImportError` with a no-arg constructor, incompatible with the canonical version in `core/babel_compat.py` (which takes `feature: str`)
  - Replaced with import from `core.babel_compat`; all call sites now pass `"ISO introspection"` as the feature name
  - Location: `introspection/iso.py`

- **`LocaleContext` allowed direct `__init__` bypassing factory validation** (FIX-LOCALE-CTX-INIT-001):
  - `LocaleContext.__init__` was publicly callable, bypassing the `create()` factory's locale validation and cache management
  - Added sentinel-based guard via `_factory_token` field; direct construction now raises `TypeError`
  - Location: `runtime/locale_context.py`

- **Roundtrip convergence failure on select expressions with indented closing brace** (BUG-CONTINUATION-CLOSEBRACE-001):
  - `is_indented_continuation()` did not exclude `}` from the continuation character set, only `[`, `*`, `.`
  - The serializer outputs `\n }` (indented closing brace) at the end of select expressions; on re-parse, this line was misidentified as a pattern continuation, injecting a phantom newline into the AST
  - Each parse-serialize cycle added a blank continuation line (`\n    `), growing output by 5 bytes and preventing convergence: `S(P(x)) != S(P(S(P(x))))`
  - Fix: Added `}` to the exclusion set in `is_indented_continuation()`; bare `}` at a continuation line start is always a select/placeable closing brace (literal `}` in text is serialized as `{ "}" }`)
  - Location: `syntax/parser/whitespace.py` `is_indented_continuation()`
  - Impact: All select expression patterns now achieve roundtrip idempotence regardless of variant content or whitespace structure

## [0.101.0] - 2026-02-01

### Breaking Changes

- **FluentBundle rejects non-FunctionRegistry `functions` parameter** (SEC-BUNDLE-DICT-FUNCTIONS-001):
  - `FluentBundle(locale, functions=some_dict)` now raises `TypeError` at construction time
  - Previously, a `dict` was silently accepted (it has `.copy()`) but caused opaque `AttributeError` during `format_pattern()` when `should_inject_locale()` was called on the dict
  - Pass `FunctionRegistry()` or `create_default_registry()` instead

### Added

- **Expansion budget for resolver DoS prevention** (SEC-RESOLVER-EXPANSION-BUDGET-001):
  - New `max_expansion_size` parameter on `FluentBundle` and `FluentResolver` (default: 1,000,000 characters)
  - Prevents Billion Laughs attacks where small FTL input expands exponentially via nested message references (e.g., `m0={m1}{m1}, m1={m2}{m2}, ...`)
  - Tracked via `ResolutionContext._total_chars`; halts resolution with `EXPANSION_BUDGET_EXCEEDED` diagnostic when exceeded
  - New `DEFAULT_MAX_EXPANSION_SIZE` constant in `constants.py`
  - New `DiagnosticCode.EXPANSION_BUDGET_EXCEEDED` (2015)

### Fixed

- **Visible precision inflated by ICU literal digit suffixes** (BUG-PRECISION-LITERAL-SUFFIX-001):
  - `_compute_visible_precision()` now accepts `max_fraction_digits` keyword to cap the counted fraction digits
  - `number_format()` and `currency_format()` parse custom Babel patterns to extract `frac_prec[1]` and pass it as the cap
  - Prevents ICU single-quote literal digit suffixes (e.g., `0.0'5'`) from inflating the CLDR v operand used for plural category selection

- **NaN/Infinity crash in plural category selection** (BUG-PLURAL-NAN-CRASH-001):
  - `select_plural_category()` now returns `"other"` for `float('nan')`, `float('inf')`, `Decimal('NaN')`, and `Decimal('Infinity')`
  - Previously raised `ValueError: cannot convert float NaN to integer` from Babel's `plural_rule()`
  - Per Fluent spec, resolution must never fail catastrophically

- **Cache `_make_hashable` DAG expansion DoS** (SEC-CACHE-DAG-EXPANSION-001):
  - `IntegrityCache._make_hashable()` now tracks total nodes visited via a budget counter (limit: 10,000 nodes)
  - Prevents exponential expansion when hashing DAG structures with shared references (e.g., `l=[l,l]` repeated 25 times = 2^25 nodes)
  - Raises `TypeError` on budget exhaustion, caught by `_make_key` for graceful cache bypass

- **Fallback depth default reduced from MAX_DEPTH to 10**:
  - `_get_fallback_for_placeable()` default `depth` parameter changed from `MAX_DEPTH` (100) to 10
  - Fallback generation is simple string construction that never legitimately requires 100 levels of recursion

- **Reference cycles in ASTVisitor and resolver cause memory accumulation** (MEM-REFCYCLE-001):
  - `ASTVisitor._instance_dispatch_cache` stored bound methods that referenced `self`, creating `self -> dict -> bound_method -> self` cycles; removed in favor of class-level method name dispatch with `getattr` per call
  - `FluentResolver.resolve_message()` returned `FrozenFluentError` objects with `__traceback__` referencing resolver frames, creating `error -> traceback -> frame -> locals -> bundle -> errors` cycles; tracebacks now cleared at the resolver boundary via `_clear_tracebacks()`
  - Combined effect: zero gc-collectable objects per resolution cycle; eliminates multi-GB RSS growth under tight-loop usage (e.g., fuzzing 17K+ iterations)

- **Collection values in placeables cause exponential `str()` expansion** (SEC-RESOLVER-DAG-STR-001):
  - `_format_value()` now returns type-name placeholders (`[list]`, `[dict]`, etc.) for `Sequence` and `Mapping` values instead of calling `str()`
  - Previously, a DAG structure passed as a variable argument (e.g., `l=[l,l]` repeated 30 times) caused `str()` to expand 2^30 nodes, consuming multi-GB memory and tens of seconds of CPU
  - Collections are valid `FluentValue` types for passing to custom functions, but are not meaningful in placeable display context
  - `_make_hashable()` node budget already protected the cache path; this closes the resolver path

## [0.100.0] - 2026-01-31

### Added

- **RWLock Timeout Support** (FEAT-RWLOCK-TIMEOUT-001):
  - `RWLock.read()` and `RWLock.write()` accept optional `timeout: float | None` parameter
  - `None` (default) preserves existing indefinite-wait behavior (fully backward compatible)
  - `0.0` enables non-blocking try-acquire pattern
  - Positive float specifies maximum seconds to wait before raising `TimeoutError`
  - Negative values raise `ValueError` immediately
  - Reentrant and lock-downgrading acquisitions never block, so timeout is irrelevant in those paths
  - Write timeout correctly decrements `_waiting_writers` counter via `try/finally`, preventing reader starvation from abandoned write attempts
  - `with_read_lock()` and `with_write_lock()` decorators accept `timeout` parameter
  - Location: `runtime/rwlock.py`
  - Impact: Enables bounded-wait lock acquisition for production resilience (slow writes no longer block all readers indefinitely)

## [0.99.0] - 2026-01-31

### Breaking Changes

- **Plural Rounding Mode Consistency** (LOGIC-PLURAL-ROUND-001):
  - Previous: `select_plural_category()` used `ROUND_HALF_EVEN` (banker's rounding) for quantization while `format_number()` used `ROUND_HALF_UP`, causing plural category and displayed number to disagree at half-values (e.g., 2.5 formatted as "3" but plural category selected for "2")
  - Fix: Changed `select_plural_category()` to use `ROUND_HALF_UP`, matching the formatting rounding mode
  - Location: `runtime/plural_rules.py` `select_plural_category()`
  - Impact: Values exactly at the half-point (e.g., 2.5, 3.5) may now select a different plural category. The displayed number and plural form always agree

### Fixed

- **ISO Introspection Exception Handling Precision** (LOGIC-EXCEPTION-SUPPRESSION-001):
  - Previous: Babel wrapper functions in `introspection/iso.py` used fragile substring matching (`"locale" in str(exc).lower()`) to catch `UnknownLocaleError`, which could suppress unrelated exceptions whose messages happen to contain "locale" or "unknown"
  - Fix: Replaced substring matching with type-based `isinstance(exc, UnknownLocaleError)` check. Non-locale exceptions now propagate correctly regardless of message content
  - Location: `introspection/iso.py` `_get_babel_territories()`, `_get_babel_currency_name()`, `_get_babel_currency_symbol()`
  - Impact: Logic bugs and unexpected exceptions with "locale" in their message are no longer silently suppressed

- **Serializer Continuation Line Syntax Collision** (BUG-SER-LINESTART-SYNTAX-001):
  - Previous: `serialize()` placed `[`, `*`, or `.` at the start of continuation lines in multiline patterns, causing re-parse to interpret them as variant key, default variant, or attribute syntax instead of text content
  - Issue: Roundtrip convergence violation `S(P(S(P(x)))) != S(P(x))` -- serialized output re-parsed with Junk entries
  - Fix: Unified `_serialize_text_element()` method detects syntactically significant characters at continuation line boundaries and wraps them as StringLiteral placeables (`{ "[" }`, `{ "*" }`, `{ "." }`)
  - Location: `syntax/serializer.py` `FluentSerializer._serialize_text_element()`
  - Impact: All valid ASTs now produce serialized output that re-parses identically

## [0.98.0] - 2026-01-30

### Breaking Changes

- **AST Construction Validation** (VAL-AST-CONSTRUCT-UNSAFE-001):
  - `Message.__post_init__` raises `ValueError` if both `value` is `None` and `attributes` is empty
  - `Term.__post_init__` raises `ValueError` if `value` is `None`
  - `SelectExpression.__post_init__` raises `ValueError` if `variants` is empty or does not contain exactly one default variant
  - Code that constructs these AST nodes with invalid state must be updated

- **Strict Mode Cache-Before-Raise** (RUN-BUNDLE-STRICT-CACHE-BYPASS-001):
  - Strict mode now caches resolution results before raising `FormattingIntegrityError`
  - Cache hits in strict mode also re-raise if the cached result contains errors
  - Previous behavior: errors were not cached; repeated calls re-resolved each time

- **Attribute-Granular Cycle Detection** (VAL-RESOURCE-ATTR-CYCLE-FP-001):
  - Dependency graph tracks attribute-level references (`msg.tooltip` vs `msg`)
  - Cross-attribute references within the same message are no longer flagged as circular
  - `extract_references()` now returns attribute-qualified reference names (e.g., `"msg.tooltip"`)

### Fixed

- **Select Expression EOF Crash** (BUG-PARSER-SELECT-EOF-001):
  - Previous: `parse_select_expression` accessed `cursor.current` after inner `skip_blank` without EOF check
  - Issue: Unterminated select expressions (missing closing `}`) caused unhandled `EOFError` crash
  - Fix: Added `cursor.is_eof` guard after `skip_blank` inside the variant parsing loop
  - Location: `syntax/parser/rules.py` `parse_select_expression()`
  - Impact: Malformed select expressions now fail gracefully instead of crashing the parser

- **ISO 4217 Non-ASCII Bypass** (PARSE-CURR-ISO-FORMAT-BUG-001):
  - Previous: `_is_valid_iso_4217_format()` accepted non-ASCII uppercase letters (e.g., Cyrillic)
  - Fix: Added `code.isascii()` check before `code.isupper()` and `code.isalpha()`
  - Location: `parsing/currency.py`

- **Number Format DoS** (SEC-NUM-FORMAT-DOS-001):
  - Previous: `format_number()` accepted arbitrary fraction digit values, enabling unbounded string allocation
  - Fix: Added `MAX_FORMAT_DIGITS` constant (100) and bounds validation in `format_number()`
  - Location: `constants.py`, `runtime/locale_context.py`

- **Diagnostic Log Injection** (SEC-DIAG-LOG-INJECTION-001):
  - Previous: User-controlled message text rendered verbatim in text-format diagnostics
  - Fix: Added `_escape_control_chars()` to `DiagnosticFormatter` for RUST and SIMPLE output formats
  - Location: `diagnostics/formatter.py`

- **RWLock Mixed Thread Identification** (MAINT-RWLOCK-MIXED-IDENT-001):
  - Previous: `_active_writer` stored `threading.Thread`; comparisons used `threading.get_ident()` (int)
  - Fix: Unified on `threading.get_ident()` (int); `_active_writer` type changed to `int | None`
  - Location: `runtime/rwlock.py`

- **CLDR Date/Datetime Missing "full" Style** (PARSE-DATE-STYLE-GAP-001):
  - Previous: `_DATE_PARSE_STYLES` and `_DATETIME_PARSE_STYLES` omitted "full" CLDR style
  - Fix: Added "full" to both style tuples; used `hasattr` for safe pattern attribute access
  - Location: `parsing/dates.py`

- **Date Pattern Attribute Access** (PARSE-DATE-ATTR-BUG-001):
  - Previous: Direct `.pattern` access on Babel format objects could raise `AttributeError`
  - Fix: Added `hasattr(fmt, "pattern")` check with `str(fmt)` fallback
  - Location: `parsing/dates.py`

## [0.97.0] - 2026-01-28

### Fixed

- **ISO 4217 Currency Code Validation** (API-CURR-VALIDATE-001):
  - Previous: `parse_currency()` accepted invalid `default_currency` values (lowercase, wrong length, non-alphabetic) and returned them verbatim
  - Issue: API contract violation; ISO 4217 requires exactly 3 uppercase ASCII letters
  - Fix: Added `_is_valid_iso_4217_format()` helper; `_resolve_currency_code()` now validates `default_currency` parameter before accepting it
  - Location: `parsing/currency.py` `_is_valid_iso_4217_format()`, `_resolve_currency_code()`
  - Impact: Invalid `default_currency` values now return proper error tuple instead of corrupting output

- **Parser Async Error Context Safety** (SEC-PARSER-ASYNC-ERROR-UNSAFE-001):
  - Previous: `primitives.py` used `threading.local()` for parse error context
  - Issue: Thread-local storage leaks context between async tasks sharing the same thread
  - Fix: Replaced `threading.local()` with `contextvars.ContextVar`, providing automatic task-local isolation
  - Location: `syntax/parser/primitives.py` `_error_context_var`
  - Impact: Parse error context is now isolated per async task; no cross-task contamination in asyncio/ASGI

- **Resolver Term Argument Depth Bypass** (SEC-RESOLVER-DEPTH-BYPASS-001):
  - Previous: Term argument evaluation in `_resolve_term_reference` bypassed `expression_guard`
  - Issue: Malicious FTL with deeply nested term arguments could bypass depth limits
  - Fix: Wrapped term argument evaluation in `with context.expression_guard:` block
  - Location: `runtime/resolver.py` `_resolve_term_reference()`
  - Impact: Term arguments now respect expression depth limits, preventing DoS

- **Serializer Argument Depth Bypass** (SEC-SERIALIZER-DEPTH-BYPASS-001):
  - Previous: `_serialize_call_arguments` did not wrap argument serialization in `depth_guard`
  - Issue: Malicious ASTs with deeply nested function arguments could bypass depth limits
  - Fix: Added `with depth_guard:` around positional and named argument serialization
  - Location: `syntax/serializer.py` `_serialize_call_arguments()`
  - Impact: Function call arguments now respect serialization depth limits

- **CallArguments Blank Handling** (SPEC-PARSER-BLANK-HANDLING-001):
  - Previous: `parse_call_arguments` used `skip_blank_inline` (spaces only)
  - Issue: FTL spec defines `CallArguments ::= blank? "(" ...` where `blank` includes newlines
  - Fix: Changed to `skip_blank` to allow multiline function argument formatting
  - Location: `syntax/parser/rules.py` `parse_call_arguments()`
  - Impact: Multiline function arguments now parse correctly per FTL specification

- **FunctionRegistry VAR_POSITIONAL Support** (MAINT-FUNC-REGISTRY-VAR-POSITIONAL-001):
  - Previous: `inject_locale` validation rejected functions with `*args` and fewer than 2 named positional params
  - Issue: Functions using `*args` can accept `(value, locale_code)` positionally
  - Fix: Added `VAR_POSITIONAL` detection; skip minimum parameter check when `*args` present
  - Location: `runtime/function_bridge.py` `FunctionRegistry.register()`
  - Impact: Functions with `*args` signatures now work with `inject_locale=True`

- **Currency Cache Size Constant Mismatch** (MAINT-CONST-MISMATCH-001):
  - Previous: `_get_currency_impl` used `MAX_TERRITORY_CACHE_SIZE` for its LRU cache
  - Issue: Currency and territory lookups have different cardinalities; shared limit is incorrect
  - Fix: Added `MAX_CURRENCY_CACHE_SIZE` constant (300); updated `_get_currency_impl` to use it
  - Location: `constants.py`, `introspection/iso.py` `_get_currency_impl()`
  - Impact: Currency cache sized independently from territory cache

### Added

- **AST Span Fields** (ARCH-AST-SPAN-MISSING-001):
  - Added optional `span: Span | None = None` field to `Pattern`, `TextElement`, and `Placeable` AST nodes
  - These nodes were the only pattern-level AST nodes missing span support
  - Impact: Uniform span interface across all AST nodes for source mapping and diagnostics

- `MAX_CURRENCY_CACHE_SIZE` constant in `ftllexengine.constants` (value: 300)

## [0.96.0] - 2026-01-28

### Fixed

- **Visible Precision Digit Count** (PRECISION-DIGIT-COUNT-001):
  - Previous: `_compute_visible_precision` counted ALL digits in fraction part, including digits after non-digit characters (e.g., `"1.20%"` returned 3 instead of 2)
  - Issue: CLDR plural rule `v` operand requires counting only leading consecutive fraction digits
  - Fix: Changed to break-on-first-non-digit loop instead of summing all digit characters
  - Location: `runtime/functions.py` `_compute_visible_precision()`
  - Impact: Correct `v` operand for formatted numbers with trailing non-digit suffixes

- **Serializer Roundtrip Data Loss** (SERIALIZER-INDENT-LOSS-001):
  - Previous: Programmatic ASTs with embedded newlines followed by whitespace within a single TextElement lost significant whitespace during serialize-parse roundtrips
  - Issue: `_pattern_needs_separate_line` only checked first element; regex-based indent replacement skipped lines already at 4-space indent
  - Fix: Added embedded newline+whitespace detection in `_pattern_needs_separate_line`; replaced conditional regex with unconditional `str.replace("\n", "\n    ")`
  - Location: `syntax/serializer.py` `_pattern_needs_separate_line()`, `_serialize_pattern()`
  - Impact: Programmatic ASTs now roundtrip correctly through serialize-parse cycles

- **Resolver Duplicate Error Handling** (DRY-RESOLVER-CALL-001):
  - Previous: Two identical ~20-line try/except blocks for locale-injected and non-locale function calls
  - Issue: DRY violation; inconsistency risk between the two code paths
  - Fix: Extracted `_call_function_safe()` method encapsulating shared error handling
  - Location: `runtime/resolver.py` `_call_function_safe()`
  - Impact: Single error handling path for all function calls; reduced maintenance surface

- **ASTTransformer Type Safety** (TYPE-SAFETY-VISITOR-001):
  - Previous: `_transform_list` accepted any `ASTNode` subclass without field-level type validation
  - Issue: Buggy transformers could silently produce wrong-typed nodes, corrupting AST structure
  - Fix: Added `expected_types` parameter to `_transform_list` and `_validate_element_type` static method; all call sites in `generic_visit` now pass explicit expected types
  - Location: `syntax/visitor.py` `_transform_list()`, `_validate_element_type()`, `generic_visit()`
  - Impact: Runtime TypeError for transformers producing nodes that violate field type constraints

- **ISO 4217 Data Integrity Documentation** (MAINT-ISO-CURRENCY-DATA-001, MAINT-ISO-PRECISION-001):
  - Previous: Comment in `constants.py` falsely claimed Babel does not expose decimal digit data
  - Fix: Updated comment to accurately describe the relationship between hardcoded ISO 4217 data and Babel CLDR data, documenting known discrepancies (e.g., IQD: Babel=0, ISO 4217=3)
  - Location: `constants.py` `ISO_4217_DECIMAL_DIGITS` comment

### Added

- `scripts/verify_iso4217.py`: CI verification script comparing hardcoded ISO 4217 decimal digits against Babel CLDR data; reports discrepancies as warnings (ISO 4217 standard is authoritative)

## [0.95.0] - 2026-01-28

### Fixed

- **RWLock Write-to-Read Reentrancy** (ARCH-RWLOCK-DEAD-004):
  - Previous: Thread holding write lock deadlocked when acquiring read lock
  - Issue: `_acquire_read()` checked for reentrant read locks but not write-to-read transitions
  - Fix: Added write-owner bypass in `_acquire_read()` with `_writer_read_count` tracking
  - Location: `runtime/rwlock.py` `_acquire_read()`, `_release_read()`
  - Impact: Write lock holders can now acquire nested read locks without blocking

- **CURRENCY Returns FluentNumber** (API-CURR-TYPE-003):
  - Previous: `currency_format()` returned `str`, preventing use as plural selector
  - Issue: Inconsistency with `number_format()` which returns `FluentNumber`
  - Fix: `currency_format()` now returns `FluentNumber` with value, formatted string, and ISO 4217 precision
  - Location: `runtime/functions.py` `currency_format()`, `runtime/function_bridge.py` `FluentNumber`
  - Impact: `CURRENCY()` results can now be used in select/plural expressions

- **AST Span Coverage** (FTL-B-001):
  - Previous: `Identifier` and `Attribute` AST nodes had `span=None` after parsing
  - Issue: Parser constructed these nodes without capturing start/end positions
  - Fix: All `Identifier()` and `Attribute()` constructions in the parser now populate `span`
  - Location: `syntax/parser/rules.py` (14 Identifier sites, 1 Attribute site)
  - Impact: Complete source location tracking for all AST nodes

- **Function Arguments Accept Message Attributes** (FTL-D-001):
  - Previous: `NUMBER(msg.attr)` rejected by argument parser
  - Issue: `parse_argument_expression` did not handle dot-notation attribute access
  - Fix: Added message attribute parsing via `_parse_message_attribute` delegation
  - Location: `syntax/parser/rules.py` `parse_argument_expression()`
  - Impact: Full inline expression support in function call arguments

- **Plural Rule Precision** (DEBT-PLURAL-ROUND-005):
  - Previous: `Decimal.quantize()` called without explicit rounding mode
  - Issue: Relied on mutable `decimal.getcontext().rounding` which can be modified by application code
  - Fix: Added explicit `rounding=ROUND_HALF_EVEN` parameter
  - Location: `runtime/plural_rules.py` `select_plural_category()`
  - Impact: Deterministic banker's rounding regardless of ambient Decimal context

- **StringLiteral.guard()** (FTL-C-001):
  - Previous: `StringLiteral` lacked `guard()` static method present on all other AST literal types
  - Fix: Added `guard()` returning `TypeIs[StringLiteral]` for type narrowing
  - Location: `syntax/ast.py` `StringLiteral`
  - Impact: API consistency with `NumberLiteral.guard()` and other AST node guards

- **IntegrityCache Docstring** (DOCS-CACHE-WEIGHT-006):
  - Previous: Docstring described weight formula as `len(formatted_str) + (len(errors) * 200)`
  - Fix: Updated to describe content-based weight calculation via `_estimate_error_weight()`
  - Location: `runtime/cache.py` `IntegrityCache.__init__`

- **Pyproject.toml Self-Containment** (FTL-A-001):
  - Previous: Comment referenced undocumented "Task 4"
  - Fix: Replaced with self-contained architectural rationale
  - Location: `pyproject.toml` pylint too-many-lines suppression

### Added

- `FluentNumber.__contains__()` and `FluentNumber.__len__()` methods for string-like protocol support

## [0.94.0] - 2026-01-27

### Fixed

- **Cache Key Collision: dict vs ChainMap** (SEC-CACHE-COLLISION-001):
  - Previous: `dict` and `ChainMap` with identical content produced identical cache keys
  - Issue: `str(dict)` differs from `str(ChainMap)` but cache returned wrong formatted output
  - Fix: Added `"__dict__"` type-tag for dict and `"__mapping__"` type-tag for Mapping ABC
  - Location: `runtime/cache.py` `IntegrityCache._make_hashable()`
  - Impact: Distinct Mapping types now produce distinct cache keys

- **Cache Key TypeError for frozenset** (TYPE-CACHE-FROZENSET-001):
  - Previous: `frozenset` arguments caused `TypeError: Unknown type in cache key`
  - Issue: `frozenset` is not a Sequence or Mapping; fell through to error handler
  - Fix: Added explicit `case frozenset():` returning `("__frozenset__", ...)`
  - Location: `runtime/cache.py` `IntegrityCache._make_hashable()`
  - Impact: frozenset arguments now properly cached

- **Hash Composition Type Markers** (SEC-HASH-AMBIGUITY-CACHE-001):
  - Previous: Raw content_hash bytes concatenated without type marker
  - Issue: Theoretical collision between hash bytes and length-prefixed strings
  - Fix: Added `b"\x01"` marker before hash bytes, `b"\x00"` before encoded strings
  - Location: `runtime/cache.py` `IntegrityCacheEntry._compute_checksum()`, `_compute_content_hash()`
  - Impact: Unambiguous structural hashing for financial-grade integrity

- **FrozenFluentError Section Markers** (SEC-HASH-AMBIGUITY-ERROR-001):
  - Previous: Optional diagnostic/context sections had no presence markers
  - Issue: Theoretical collision between different section configurations
  - Fix: Added section markers `b"\x01DIAG"`/`b"\x00NODIAG"` and `b"\x01CTX"`/`b"\x00NOCTX"`
  - Location: `diagnostics/errors.py` `FrozenFluentError._compute_content_hash()`
  - Impact: Unambiguous structural hashing regardless of optional field presence

- **Validation Reports All Deep Chains** (VAL-REDUNDANT-REPORTS-001):
  - Previous: `_detect_long_chains` only reported the single longest chain
  - Issue: Users had to fix and re-run to discover additional deep chains
  - Fix: Now returns warnings for ALL chains exceeding max_depth, sorted by depth
  - Location: `validation/resource.py` `_detect_long_chains()`
  - Impact: Better UX for complex FTL files with multiple deep reference chains

## [0.93.0] - 2026-01-26

### Fixed

- **Cache Key Datetime Timezone Collision Prevention** (INTEG-CACHE-DT-TZ-COLLISION-001):
  - Previous: `IntegrityCache._make_hashable` returned datetime objects as-is
  - Issue: Two datetime objects with same UTC instant but different tzinfo (e.g., 12:00 UTC vs 07:00 EST) compare equal in Python and share hash, but format to different local time strings; cache returned wrong formatted output
  - Fix: datetime now returns `("__datetime__", isoformat, tz_key)` where tz_key distinguishes timezones
  - Location: `runtime/cache.py` `IntegrityCache._make_hashable()`
  - Impact: Financial applications with timezone-aware datetime formatting get correct cached results

- **Cache Key Float Negative Zero Collision Prevention** (INTEG-CACHE-FLOAT-NEG-ZERO-001):
  - Previous: `IntegrityCache._make_hashable` returned float values as `("__float__", value)`
  - Issue: `0.0 == -0.0` in Python but locale formatting may distinguish them ("-0" vs "0"); cache returned wrong formatted output
  - Fix: float now uses `("__float__", str(value))` to preserve sign representation
  - Location: `runtime/cache.py` `IntegrityCache._make_hashable()`
  - Impact: Applications with signed-zero semantics get correct cached results

- **Cache Type Validation Robustness** (INTEG-CACHE-VERIFY-HASATTR-001):
  - Previous: `_compute_checksum` and `verify` used `hasattr` without type validation
  - Issue: Duck-typed objects with wrong `content_hash` type could cause unexpected errors in integrity-critical code
  - Fix: Added `isinstance` type validation for `content_hash` (must be `bytes`) and `callable` check for `verify_integrity`
  - Location: `runtime/cache.py` `IntegrityCacheEntry._compute_checksum()`, `_compute_content_hash()`, `verify()`
  - Impact: More robust integrity verification with explicit type checking

- **Cache Sequence/Mapping ABC Support** (INTEG-CACHE-MAPPING-SEQ-TYPE-GAP-001):
  - Previous: `_make_hashable` used narrow type checks (`list`, `tuple`, `dict`) only
  - Issue: Other Sequence types (UserList) and Mapping types (ChainMap) caused cache bypass
  - Fix: Added fallback checks using `collections.abc.Sequence` and `Mapping` ABCs
  - Location: `runtime/cache.py` `IntegrityCache._make_hashable()`
  - Impact: Custom function implementations using ABC-compliant types now benefit from caching

- **FrozenFluentError Python 3.11+ Compatibility** (INTEG-FROZENFLUENTEERROR-NOTES-001):
  - Previous: `FrozenFluentError._PYTHON_EXCEPTION_ATTRS` missing `__notes__`
  - Issue: `add_note()` and exception groups (PEP 654/678) raised `ImmutabilityViolationError` on Python 3.11+
  - Fix: Added `__notes__` to allowed Python exception attributes, matching `DataIntegrityError`
  - Location: `diagnostics/errors.py` `FrozenFluentError._PYTHON_EXCEPTION_ATTRS`
  - Impact: Full compatibility with Python 3.11+ exception features

- **Function Error Fallback Consistency** (INTEG-FALLBACK-FUNCTION-ERROR-001):
  - Previous: Function failure fallback was `{ NUMBER() }` in exception handlers but `{!NUMBER}` in AST fallback
  - Issue: Inconsistent output format for the same error condition made debugging harder
  - Fix: All function error fallbacks now use `FALLBACK_FUNCTION_ERROR` constant from `constants.py`
  - Location: `runtime/resolver.py` `FluentResolver._resolve_function_call()`
  - Impact: Consistent error output format across all function failure scenarios

### Changed

- **Parser Pattern Logic Consolidation** (DEBT-DUPLICATE-PARSER-LOGIC-001):
  - Previous: `parse_simple_pattern` and `parse_pattern` had ~80 lines of duplicated continuation handling logic
  - Change: Extracted shared logic into `_process_continuation_line()` and `_append_newline_to_elements()` helpers
  - Location: `syntax/parser/rules.py`
  - Impact: Reduced maintenance burden; single point for pattern parsing fixes

- **Resolver ContextVar Waiver Formalization** (ARCH-CONTEXTVAR-IMPLICIT-STATE-001):
  - Previous: `_global_resolution_depth` ContextVar had security rationale but lacked formal waiver keywords
  - Change: Added explicit "Architectural Decision" and "Trade-off" documentation
  - Location: `runtime/resolver.py` module-level documentation
  - Impact: Waiver is now formally recognized; prevents future refactoring attempts that would break security

- **Bundle Cache Comment Accuracy** (DOCS-LAZY-CACHE-DRIFT-001):
  - Previous: Comment mentioned "lazy initialization" but cache was created eagerly
  - Change: Updated comment to accurately describe eager initialization behavior
  - Location: `runtime/bundle.py` `FluentBundle.__init__()`
  - Impact: Documentation matches implementation

## [0.92.0] - 2026-01-25

### Added

- **IntegrityCache Idempotent Write Support** (SEC-CACHE-STRICT-CONCURRENCY-DOS-001):
  - Previous: `write_once=True` rejected ALL overwrites, even identical values
  - Issue: Thundering herd scenarios caused N-1 threads to crash with `WriteConflictError` when multiple threads resolved same message simultaneously
  - New: `content_hash` property on `IntegrityCacheEntry` for content-only comparison (excludes metadata)
  - New: `idempotent_writes` counter and property on `IntegrityCache` tracking benign concurrent writes
  - New: `WRITE_ONCE_IDEMPOTENT` and `WRITE_ONCE_CONFLICT` audit log operations for distinguishing benign races from true conflicts
  - Fix: `put()` compares content hashes before rejecting; identical values treated as idempotent success
  - Location: `runtime/cache.py` `IntegrityCacheEntry.content_hash`, `IntegrityCache.put()`, `IntegrityCache.idempotent_writes`
  - Impact: High-concurrency cold-cache scenarios no longer cause false-positive errors; financial applications can safely use `write_once=True` under load

### Fixed

- **ISO Cache Size Complete Alignment** (DOCS-ISO-CACHE-SIZE-MISMATCH-001):
  - Previous: `_get_territory_impl` and `_get_currency_impl` used `MAX_LOCALE_CACHE_SIZE` (128)
  - Issue: CHANGELOG v0.89.0 claimed territory caches were fixed but implementation was incomplete; only `_get_territory_currencies_impl` was updated
  - Fix: Both `_get_territory_impl` and `_get_currency_impl` now use `MAX_TERRITORY_CACHE_SIZE` (300)
  - Location: `introspection/iso.py`
  - Impact: Full territory/currency iteration no longer causes cache thrashing; documented fix now matches implementation

- **ISO Validation Cache Pollution Prevention** (SEC-ISO-VALIDATION-POLLUTION-001):
  - Previous: `is_valid_territory_code` and `is_valid_currency_code` called lookup functions, caching `None` for invalid inputs
  - Issue: Attackers could fill LRU caches with `None` entries by validating random strings, evicting legitimate cached lookups
  - Fix: Validation now uses O(1) membership check against cached enumerated code sets (`_territory_codes_impl`, `_currency_codes_impl`)
  - Location: `introspection/iso.py` `is_valid_territory_code()`, `is_valid_currency_code()`, `clear_iso_cache()`
  - Impact: Validation no longer pollutes lookup caches; O(1) validation via pre-cached frozen sets; cache clear includes new code set caches

- **Fiscal Calendar Dead Code Removal** (DEBT-FISCAL-DEAD-CODE-001):
  - Previous: `fiscal_year_end_date` contained unreachable `else 12` branch in `end_month` calculation
  - Issue: Early return for `start_month == 1` made `start_month > 1` condition always true at subsequent line
  - Fix: Simplified to `end_month = self.start_month - 1`
  - Location: `parsing/fiscal.py` `FiscalCalendar.fiscal_year_end_date()`
  - Impact: No behavioral change; code clarity improved

## [0.91.0] - 2026-01-25

### Breaking Changes

- **ISO get_territory_currencies Returns Tuple** (ARCH-ISO-MUTABLE-RETURN-001):
  - Previous: `get_territory_currencies(territory)` returned `list[CurrencyCode]`
  - Issue: Mutable return type violates immutability protocol; callers could accidentally mutate cached data
  - **Breaking**: Return type changed to `tuple[CurrencyCode, ...]`
  - Location: `introspection/iso.py` `get_territory_currencies()`
  - Migration: Replace `currencies.append(...)` with `currencies = (*currencies, new_code)` or convert explicitly with `list(get_territory_currencies(code))`
  - Impact: API consistency with immutability protocol; cache integrity protected

### Added

- **Fiscal Convenience Functions** (API-FISCAL-CONSISTENCY-001):
  - New `fiscal_year(date, start_month=1)` - Get fiscal year for a date
  - New `fiscal_month(date, start_month=1)` - Get fiscal month (1-12) for a date
  - Wrappers around `FiscalCalendar` for common use cases
  - Location: `parsing/fiscal.py`
  - Exported from: `ftllexengine.parsing`
  - Impact: Simpler API for users who don't need full `FiscalCalendar` capabilities

- **FluentLocalization Strict Mode** (API-STRICT-MODE-MISSING-001):
  - New `strict: bool = False` parameter in `FluentLocalization.__init__()`
  - Propagates strict mode to all `FluentBundle` instances created during resolution
  - Location: `localization.py` `FluentLocalization.__init__()`, `_get_or_create_bundle()`
  - Impact: Applications can now enable strict mode at the localization layer, not just bundle layer

### Fixed

- **Era String Caching Performance** (PERF-ERA-STRIP-REDUNDANT-001):
  - Previous: `_strip_era()` created new `Babel.Locale` object on every call
  - Issue: Locale instantiation is expensive; redundant when parsing many dates with same locale
  - Fix: Added `_get_localized_era_strings(locale_code)` with `@lru_cache(maxsize=64)`
  - Helper `_extract_era_strings_from_babel_locale()` extracted for code clarity
  - Location: `parsing/dates.py`
  - Impact: Date parsing performance improved for repeated locale usage

- **Strict Mode Atomicity** (ARCH-STRICT-ATOMICITY-001):
  - Previous: `FluentBundle._register_resource()` mutated bundle state before strict mode validation
  - Issue: Failed strict validation left bundle in partially modified state; violated atomicity guarantee
  - Fix: Implemented two-phase commit pattern - collect all entries first, validate, then apply
  - Location: `runtime/bundle.py` `_register_resource()`
  - Impact: Strict mode failures are now atomic; bundle state unchanged on `SyntaxIntegrityError`

- **Error Class Defensive Tuple Conversion** (DEFENSIVE-INTEGRITY-TUPLE-001):
  - Previous: `FormattingIntegrityError` and `SyntaxIntegrityError` stored tuple parameters directly
  - Issue: If caller passed mutable sequence, stored reference could be mutated externally
  - Fix: Added `tuple()` conversion in both constructors
  - Location: `integrity.py` `FormattingIntegrityError.__init__()`, `SyntaxIntegrityError.__init__()`
  - Impact: Error objects are now truly immutable regardless of caller input type

- **Custom Function Exception Handling** (RES-FUNC-UNCAUGHT-EXCEPTION-001):
  - Previous: Uncaught exceptions from custom functions propagated up, crashing resolution
  - Issue: Fluent specification requires graceful degradation; one bad function shouldn't crash entire message
  - Fix: Wrapped custom function calls in try/except; logs warning; returns placeholder `{ FUNCNAME() }`
  - Re-raises `FrozenFluentError` (internal control flow) to preserve existing behavior
  - Location: `runtime/resolver.py` `FluentResolver._resolve_function_call()`
  - Impact: Spec-compliant graceful degradation; custom function bugs no longer crash resolution

## [0.90.0] - 2026-01-25

### Breaking Changes

- **FiscalDelta Policy Conflict Detection** (SEM-FISCAL-DELTA-POLICY-001):
  - Previous: `FiscalDelta.__add__()` and `__sub__()` silently used `self.month_end_policy`, ignoring the right operand's policy
  - Issue: Order-dependent behavior - `delta_preserve + delta_strict` gave preserve semantics, `delta_strict + delta_preserve` gave strict semantics
  - **Breaking**: Operations now raise `ValueError` when operands have different `month_end_policy` values
  - **New**: Added `with_policy(policy: MonthEndPolicy)` method for explicit policy conversion
  - Location: `parsing/fiscal.py` `FiscalDelta.__add__()`, `__sub__()`, `with_policy()`
  - Migration: Use `delta1.with_policy(MonthEndPolicy.PRESERVE) + delta2` to explicitly normalize policies before arithmetic
  - Impact: Financial applications get explicit control over month-end behavior; silent semantic conflicts eliminated

- **FluentNumber Cache Key Normalization** (BUG-CACHE-NAN-POLLUTION-001):
  - Previous: `FluentNumber` containing NaN values used raw `value.value` in cache keys
  - Issue: IEEE 754 NaN inequality (`nan != nan`) caused cache pollution - each `put()` created unretrievable entries
  - **Breaking**: Cache key structure changed for `FluentNumber` - inner value now recursively normalized
  - Fix: Inner value normalized via `_make_hashable()`, converting NaN to canonical `"__NaN__"` string
  - Location: `runtime/cache.py` `IntegrityCache._make_hashable()`
  - Impact: NaN-containing formatting results are now properly cached and retrievable

### Fixed

- **Datetime Parsing Component Order** (SEM-DATETIME-ORDER-001):
  - Previous: `_get_datetime_patterns()` always generated date-first patterns (`{date}{sep}{time}`)
  - Issue: Locales with time-first ordering (CLDR pattern `{0} {1}` where `{0}=time`) failed to parse correctly formatted datetimes
  - Fix: `_extract_datetime_separator()` now returns `(separator, is_time_first)` tuple; `_get_datetime_patterns()` respects order
  - Location: `parsing/dates.py` `_extract_datetime_separator()`, `_get_datetime_patterns()`
  - Impact: Datetime parsing now works correctly for locales with time-before-date formatting conventions

- **FluentValue and fluent_function Babel Independence** (ARCH-BABEL-FALSE-DEPENDENCY-001):
  - Previous: `FluentValue` and `fluent_function` were in `_BABEL_REQUIRED_ATTRS`, incorrectly classified as requiring Babel
  - Issue: Parser-only installations received confusing Babel-related error messages when importing pure Python utilities
  - Fix: Moved to separate `_BABEL_INDEPENDENT_ATTRS` set with dedicated lazy loading (no Babel error handling)
  - Location: `__init__.py` `_BABEL_REQUIRED_ATTRS`, `_BABEL_INDEPENDENT_ATTRS`, `__getattr__()`
  - Impact: `from ftllexengine import FluentValue, fluent_function` works without Babel; clearer error messages

- **IntegrityCache Constant Usage** (DEBT-CACHE-CONSTANTS-001):
  - Previous: `IntegrityCache.__init__()` hardcoded `maxsize=1000` instead of using `DEFAULT_CACHE_SIZE`
  - Issue: Inconsistent with `max_entry_weight` which correctly used `DEFAULT_MAX_ENTRY_SIZE` constant
  - Fix: Changed to `maxsize: int = DEFAULT_CACHE_SIZE`; added constant to imports
  - Location: `runtime/cache.py` `IntegrityCache.__init__()`
  - Impact: Cache size configuration centralized in `constants.py`; no behavioral change (same default value)

## [0.89.0] - 2026-01-24

### Breaking Changes

- **ISO Territory Currencies API Redesign** (API-ISO-MULTI-CURRENCY-001):
  - Previous: `get_territory_currency(territory)` returned `CurrencyCode | None` (single currency)
  - Issue: Multi-currency territories (e.g., Panama uses PAB and USD) had data loss; only first currency returned
  - **Breaking**: Function renamed to `get_territory_currencies(territory)` returning `list[CurrencyCode]`
  - **Breaking**: `TerritoryInfo.default_currency: CurrencyCode | None` replaced by `TerritoryInfo.currencies: tuple[CurrencyCode, ...]`
  - Location: `introspection/iso.py`
  - Migration: Replace `get_territory_currency(code)` with `get_territory_currencies(code)`, access `territory.currencies` (tuple) instead of `territory.default_currency`
  - Impact: Financial applications can now access all legal tender currencies for any territory

### Fixed

- **ISO list_currencies Locale Filtering** (LOGIC-ISO-LIST-FILTERING-001):
  - Previous: `list_currencies(locale)` filtered out currencies without localized names in target locale
  - Issue: Result set varied by locale (e.g., 'fr' returned fewer currencies than 'en'), violating ISO 4217 completeness
  - Fix: Returns complete ISO 4217 currency set regardless of locale; currencies without localized names use English name as fallback
  - Location: `introspection/iso.py` `_list_currencies_impl()`
  - Impact: Consistent currency list across all locales for financial applications

- **ISO Territory Cache Size Mismatch** (PERF-ISO-CACHE-SIZE-001):
  - Previous: `_get_territory_currency_impl` used `MAX_LOCALE_CACHE_SIZE` (128) as cache size
  - Issue: ISO 3166-1 defines ~249 territories; iterating all territories caused cache thrashing (>50% eviction rate)
  - Fix: Added `MAX_TERRITORY_CACHE_SIZE = 300` constant; territory-keyed caches now use appropriate size
  - Location: `constants.py`, `introspection/iso.py`
  - Impact: Full territory iteration no longer causes cache evictions

- **FiscalDelta Operator Polymorphism** (LOGIC-FISCAL-DELTA-TYPE-001):
  - Previous: `__add__`, `__sub__`, `__mul__` hardcoded `FiscalDelta()` constructor, breaking subclass polymorphism
  - Issue: Subclasses of `FiscalDelta` lost type identity through arithmetic operations (e.g., `CustomDelta + delta` returned `FiscalDelta`, not `CustomDelta`)
  - Fix: All operators now use `type(self)(...)` pattern, consistent with `negate()` method
  - Location: `parsing/fiscal.py` `FiscalDelta.__add__()`, `__sub__()`, `__mul__()`, `__rmul__()`
  - Impact: Subclasses properly preserve type through all arithmetic operations

- **FiscalDelta.add_to Docstring Error** (DOCS-FISCAL-ERROR-DRIFT-001):
  - Previous: Docstring claimed `OverflowError` for date range violations
  - Issue: Python's `date()` constructor raises `ValueError` for year outside 1-9999, not `OverflowError`
  - Fix: Docstring corrected to document `ValueError` for both day overflow and year range violations
  - Location: `parsing/fiscal.py` `FiscalDelta.add_to()`, `subtract_from()` docstrings
  - Impact: Callers can now correctly catch `ValueError` for all range violations

- **Parser Variant Lookahead Limit Mismatch** (PARSER-VARIANT-LOOKAHEAD-MISMATCH-001):
  - Previous: `MAX_LOOKAHEAD_CHARS` (128) was smaller than `_MAX_IDENTIFIER_LENGTH` (256)
  - Issue: Valid variant keys with 129-256 character identifiers were misparsed as literal text
  - Fix: Increased `MAX_LOOKAHEAD_CHARS` to 300 to accommodate maximum-length identifiers plus bracket/whitespace overhead
  - Location: `constants.py`
  - Impact: Variant keys with long identifiers now parse correctly per Fluent EBNF

## [0.88.0] - 2026-01-24

### Fixed

- **ISO Introspection UnknownLocaleError Leak** (ROBUST-ISO-UNKNOWN-LOCALE-001):
  - Previous: `_get_babel_currency_name()` and `_get_babel_currency_symbol()` only caught `(ValueError, LookupError, KeyError, AttributeError)`
  - Issue: Babel's `UnknownLocaleError` inherits from `Exception`, not `LookupError`; very long or garbage locale strings caused the exception to leak to callers, violating the API contract that only `BabelImportError` should propagate
  - Discovery: Atheris fuzzer with input `locale="x" * 100` triggered `UnknownLocaleError` in `get_currency()`
  - Fix: Added defensive `except Exception` clause (matching `_get_babel_territories()` pattern) that checks for locale-related errors and returns graceful fallback
  - Location: `introspection/iso.py` `_get_babel_currency_name()`, `_get_babel_currency_symbol()`
  - Impact: API contract honored; garbage locale inputs return `None` or fallback instead of raising Babel-specific exceptions

- **ISO Introspection Cache Integration** (MAINT-CACHE-MISSING-001):
  - Previous: `clear_all_caches()` did not clear ISO introspection caches (territories, currencies)
  - Issue: Memory from ISO lookups could not be reclaimed via the central cache clearing function
  - Fix: `clear_all_caches()` now imports and calls `clear_iso_cache()` from introspection module
  - Location: `__init__.py` `clear_all_caches()` function
  - Impact: Complete cache clearing for long-running applications using ISO introspection

- **ISO Introspection Bounded Caches** (SEC-DOS-UNBOUNDED-ISO-001):
  - Previous: ISO lookup functions used unbounded `@functools.cache` (equivalent to `lru_cache(maxsize=None)`)
  - Security issue: Attacker could exhaust memory by cycling through unique locale strings, as each unique input was permanently cached
  - Fix: Replaced `@cache` with `@lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)` on all cached functions
  - Refactored to normalize inputs before caching:
    - Public functions normalize inputs (code uppercasing, locale normalization)
    - Internal `_impl` functions receive pre-normalized inputs and are cached
  - Functions affected: `get_territory`, `get_currency`, `list_territories`, `list_currencies`, `get_territory_currency`
  - Location: `introspection/iso.py`
  - Impact: Memory exhaustion attack vector eliminated; cache bounded to 128 entries per function

- **ISO Introspection Locale Normalization** (API-ISO-LOCALE-NORM-001):
  - Previous: Locale parameters used directly as cache keys without normalization
  - Issue: Variant formats ('en-US', 'en_US', 'en_us') created separate cache entries, wasting memory and reducing cache hit rates
  - Fix: All locale parameters normalized via `normalize_locale()` before caching
  - Code case also normalized: 'us', 'US', 'Us' now hit same cache entry
  - Location: `introspection/iso.py` all public lookup functions
  - Impact: Cache efficiency improved; consistent behavior with other locale-aware modules

- **ISO Introspection Exception Narrowing** (ROBUST-ISO-EXCEPTIONS-001):
  - Previous: Internal Babel wrappers used broad `except Exception:` catching all errors
  - Issue: Logic bugs (NameError, TypeError) and system errors (MemoryError) were silently converted to "data not found" results, masking bugs in financial-grade contexts
  - Fix: Narrowed exception handling to `(ValueError, LookupError, KeyError, AttributeError)`
  - Babel's `UnknownLocaleError` (inherits from Exception, not LookupError) handled specially in `_get_babel_territories()`
  - Logic bugs and system errors now propagate for proper debugging
  - Location: `introspection/iso.py` `_get_babel_currency_name()`, `_get_babel_currency_symbol()`, `_get_babel_territory_currencies()`, `_get_babel_territories()`
  - Impact: Fail-fast behavior for logic bugs; improved debuggability in financial applications

- **FiscalDelta month_end_policy Validation** (SEC-INPUT-VALIDATION-002):
  - Previous: `FiscalDelta` did not validate `month_end_policy` field at construction
  - Issue: Passing invalid policy values (strings, None) caused `UnboundLocalError` deep in arithmetic operations instead of clear validation error at construction
  - Fix: Added `isinstance(self.month_end_policy, MonthEndPolicy)` check in `__post_init__()`
  - Added defensive default case in `_add_months()` match statement for defense-in-depth
  - Location: `parsing/fiscal.py` `FiscalDelta.__post_init__()`, `_add_months()`
  - Impact: Invalid inputs fail fast at construction with clear `TypeError`; arithmetic operations protected by defense-in-depth

- **Date Parsing Bounded Caches** (SEC-DOS-UNBOUNDED-DATES-001):
  - Previous: Date pattern cache functions used unbounded `@functools.cache`
  - Security issue: Attacker could exhaust memory by calling `parse_date()` or `parse_datetime()` with millions of unique fake locale strings, each creating a permanent cache entry
  - Fix: Replaced `@cache` with `@lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)` on `_get_date_patterns()` and `_get_datetime_patterns()`
  - Location: `parsing/dates.py` lines 291, 396
  - Impact: Memory exhaustion attack vector eliminated; cache bounded to 128 entries per function; LRU eviction for high-volume applications

### Changed

- **RWLock Decorators Modernized to PEP 695** (MODERN-PEP695-RWLOCK-001):
  - Previous: `with_read_lock` and `with_write_lock` decorators used legacy `TypeVar("T")` pattern
  - Modernization: Converted to PEP 695 generic function syntax `def with_read_lock[T](...)`
  - Removed module-level `T = TypeVar("T")` declaration
  - Location: `runtime/rwlock.py` lines 265, 297
  - Impact: Cleaner syntax aligned with Python 3.13+ standards; no API change

## [0.87.0] - 2026-01-23

### Added

- **ISO Introspection API** (FEATURE-ISO-INTROSPECTION-001):
  - New `ftllexengine.introspection.iso` module for ISO 3166/4217 data access
  - Type aliases: `TerritoryCode`, `CurrencyCode` (PEP 695 style)
  - Data classes: `TerritoryInfo`, `CurrencyInfo` (immutable, hashable)
  - Lookup functions:
    - `get_territory(code, locale)` - ISO 3166-1 territory by alpha-2 code
    - `get_currency(code, locale)` - ISO 4217 currency by code
    - `list_territories(locale)` - All known territories
    - `list_currencies(locale)` - All known currencies
    - `get_territory_currency(territory)` - Default currency for territory
  - Type guards: `is_valid_territory_code()`, `is_valid_currency_code()` (PEP 742 TypeIs)
  - Cache management: `clear_iso_cache()` for memory control
  - All results cached with `@functools.cache` for performance
  - Requires Babel: Functions raise `BabelImportError` if unavailable
  - Location: `introspection/iso.py`, exported from `ftllexengine.introspection`
  - Financial context: Enables runtime territory-to-currency resolution for multi-currency applications

- **Fiscal Calendar Arithmetic** (FEATURE-FISCAL-CALENDAR-001):
  - New `ftllexengine.parsing.fiscal` module for fiscal date calculations
  - `MonthEndPolicy` enum: PRESERVE, CLAMP, STRICT for month-end date handling
  - `FiscalPeriod` dataclass: Immutable fiscal period identifier (year, quarter, month)
  - `FiscalCalendar` dataclass: Configurable fiscal year boundaries with methods:
    - `fiscal_year(date)` - Get fiscal year for date
    - `fiscal_quarter(date)` - Get fiscal quarter (1-4) for date
    - `fiscal_month(date)` - Get fiscal month (1-12) for date
    - `fiscal_period(date)` - Get complete FiscalPeriod for date
    - `fiscal_year_start(year)` - First day of fiscal year
    - `fiscal_year_end(year)` - Last day of fiscal year
    - `quarter_start(year, quarter)` - First day of fiscal quarter
    - `quarter_end(year, quarter)` - Last day of fiscal quarter
    - `date_range(date)` - Fiscal year date range tuple
  - `FiscalDelta` dataclass: Period delta with arithmetic operators:
    - Fields: years, quarters, months, days, month_end_policy
    - Methods: `add_to(date)`, `subtract_from(date)`, `total_months()`, `negate()`
    - Operators: `+`, `-`, `*`, unary `-`
  - Convenience functions: `fiscal_quarter()`, `fiscal_year_start()`, `fiscal_year_end()`
  - No external dependencies (stdlib only)
  - Location: `parsing/fiscal.py`, exported from `ftllexengine.parsing`
  - Financial context: UK (Apr), Japan (Apr), Australia (Jul), US federal (Oct) fiscal years

- **ISO 4217 Decimal Digits Constants** (DATA-ISO4217-DECIMALS-001):
  - New constants in `constants.py`:
    - `ISO_4217_DECIMAL_DIGITS`: Dict mapping currency codes to decimal places
    - `ISO_4217_DEFAULT_DECIMALS`: Default decimal places (2)
  - Covers currencies with non-standard decimals:
    - 0 decimals: JPY, KRW, VND, BIF, CLP, etc.
    - 3 decimals: BHD, IQD, JOD, KWD, LYD, OMR, TND
    - 4 decimals: CLF, UYW
  - Used by `CurrencyInfo.decimal_digits` for accurate currency formatting
  - Location: `constants.py`

## [0.86.0] - 2026-01-22

### Fixed

- **NaN Cache Pollution Prevention** (SEC-CACHE-NAN-POLLUTION-001):
  - Previous: `float("nan")` and `Decimal("NaN")` values in cache arguments created unretrievable cache entries
  - Security issue: NaN violates Python equality (`nan != nan`), so keys containing NaN can never be retrieved. Each `put()` with NaN creates a NEW entry, polluting the cache until legitimate entries are evicted (DoS via cache thrashing)
  - Fix: NaN values normalized to canonical `"__NaN__"` string representation in `_make_hashable()`
    - `float("nan")` -> `("__float__", "__NaN__")`
    - `Decimal("NaN")` -> `("__decimal__", "__NaN__")`
    - `Decimal("sNaN")` -> `("__decimal__", "__NaN__")` (signaling NaN also normalized)
  - Location: `runtime/cache.py` `_make_hashable()` float and Decimal cases
  - Impact: Cache entries with NaN arguments are now retrievable; cache pollution attack vector eliminated
  - Financial context: NaN can appear in edge cases (division by zero, undefined calculations); cache must handle gracefully

- **FluentValue Type Alias Collection Support** (TYPE-DEF-INCOMPLETE-001):
  - Previous: `FluentValue` type alias excluded `Sequence` and `Mapping` types despite runtime support
  - Issue: Passing `list` or `dict` arguments to `format_pattern()` caused false positive type errors in mypy/pyright strict mode
  - Fix: Updated `FluentValue` to include recursive collection types:
    ```python
    type FluentValue = (
        str | int | float | bool | Decimal | datetime | date | FluentNumber | None |
        Sequence["FluentValue"] | Mapping[str, "FluentValue"]
    )
    ```
  - Location: `runtime/function_bridge.py` line 112
  - Impact: Static type checkers now accept collection arguments; type contract matches runtime capability
  - Note: Python 3.13+ recursive type aliases (PEP 695) enable this definition

## [0.85.0] - 2026-01-21

### Added

- **SyntaxIntegrityError Exception** (ARCH-STRICT-SCOPE-001):
  - Previous: `FluentBundle.add_resource()` returned Junk entries silently in strict mode
  - Issue: Financial applications require fail-fast behavior; silent failures during resource loading are unacceptable for monetary formatting
  - Added: `SyntaxIntegrityError` exception raised in strict mode when syntax errors (Junk entries) are detected
  - Exception attributes:
    - `junk_entries: tuple[Junk, ...]` - Junk AST nodes representing syntax errors
    - `source_path: str | None` - Optional path to source file for error context
    - `context: IntegrityContext` - Structured diagnostic context
  - Export: Available from `ftllexengine` top-level package
  - Location: `integrity.py`, `runtime/bundle.py` `_register_resource()`
  - Impact: Complete strict mode coverage for both syntax (SyntaxIntegrityError) and formatting (FormattingIntegrityError)

- **API Boundary Type Validation** (SEC-INPUT-VALIDATION-001):
  - Previous: `add_resource()` and `validate_resource()` accepted any type without validation
  - Issue: Passing `bytes` instead of `str` could cause confusing downstream errors; type safety requires explicit validation at public API boundaries
  - Added: `isinstance(source, str)` check at entry point with descriptive `TypeError`
  - Error message includes: actual type received, guidance to decode bytes (`source.decode('utf-8')`)
  - Locations:
    - `FluentBundle.add_resource()` - raises `TypeError` for non-string source
    - `FluentBundle.validate_resource()` - raises `TypeError` for non-string source
    - `validate_resource()` standalone function - raises `TypeError` for non-string source
  - Impact: Clear error messages at API boundaries; defense-in-depth type safety

## [0.84.0] - 2026-01-21

### Added

- **FluentBundle Cache Security Parameters** (API-CACHE-SECURITY-PARAMS-001):
  - Previous: IntegrityCache security parameters (write_once, enable_audit, max_audit_entries, max_entry_weight, max_errors_per_entry) were not accessible through FluentBundle constructor
  - Issue: Financial applications requiring cache audit trails or write-once semantics had no public API to enable these features
  - Added: Five new parameters to `FluentBundle.__init__()` and `FluentBundle.for_system_locale()`:
    - `cache_write_once: bool = False` - Reject updates to existing cache keys (data race prevention)
    - `cache_enable_audit: bool = False` - Maintain audit log of all cache operations
    - `cache_max_audit_entries: int = 10000` - Maximum audit log entries before oldest eviction
    - `cache_max_entry_weight: int = 10000` - Maximum memory weight for cached results
    - `cache_max_errors_per_entry: int = 50` - Maximum errors per cache entry
  - Added: Five corresponding read-only properties for introspection:
    - `cache_write_once`, `cache_enable_audit`, `cache_max_audit_entries`, `cache_max_entry_weight`, `cache_max_errors_per_entry`
  - Locations: `runtime/bundle.py` `__init__()`, `for_system_locale()`, properties
  - Impact: Full IntegrityCache feature exposure for financial-grade applications

- **FluentBundle.for_system_locale strict Parameter** (API-FOR-SYSTEM-LOCALE-STRICT-001):
  - Previous: `for_system_locale()` factory method did not accept `strict` parameter
  - Issue: Creating strict-mode bundles with system locale detection required two-step initialization
  - Added: `strict: bool = False` parameter to `for_system_locale()`
  - Location: `runtime/bundle.py` `for_system_locale()` method
  - Impact: Complete parameter parity between `__init__()` and `for_system_locale()`

## [0.83.0] - 2026-01-21

### Fixed

- **Hash Composition Length-Prefixing** (SEC-HASH-COLLISION-LENGTH-PREFIX-001):
  - Previous: String fields in hash composition were concatenated without length prefixes
  - Security issue: Different field sequences could produce identical byte streams (e.g., `("ab", "c")` and `("a", "bc")` hash identically)
  - Fix: All string fields now length-prefixed (4-byte big-endian UTF-8 byte length) before hashing
  - Locations: `diagnostics/errors.py` `_hash_string()` helper, `runtime/cache.py` `_compute_checksum()`
  - Impact: Collision attacks via field boundary manipulation now prevented

- **FrozenFluentError Exception Attribute Whitelist** (IMPL-EXCEPTION-ATTRS-001):
  - Previous: `FrozenFluentError.__setattr__()` blocked ALL attribute writes after freeze, including Python exception machinery
  - Issue: Python sets `__traceback__`, `__context__`, `__cause__`, `__suppress_context__` on exceptions after construction
  - Fix: Added `_PYTHON_EXCEPTION_ATTRS` whitelist allowing Python runtime to set exception machinery attributes
  - Location: `diagnostics/errors.py` lines 113-115, 165-167
  - Impact: FrozenFluentError now works correctly as a raisable exception in all contexts

- **Cache Key Type Confusion for Decimal** (DATA-INTEGRITY-CACHE-DECIMAL-001):
  - Previous: `Decimal` values used raw numeric representation in cache keys
  - Issue: `Decimal("1.0")` and `Decimal("1.00")` produced same cache key despite different CLDR plural rule behavior
  - Fix: Decimal now type-tagged with `str(value)` preserving scale: `("__decimal__", "1.0")` vs `("__decimal__", "1.00")`
  - Location: `runtime/cache.py` `_make_hashable()` Decimal case
  - Impact: Correct caching for locales with scale-dependent plural rules

- **Cache Key Type Confusion for FluentNumber** (DATA-INTEGRITY-CACHE-FLUENTNUMBER-001):
  - Previous: `FluentNumber` values lost underlying type information in cache keys
  - Issue: `FluentNumber(value=1, ...)` with int value and `FluentNumber(value=1.0, ...)` with float value shared cache key
  - Fix: FluentNumber now type-tagged with full info: `("__fluentnumber__", type_name, value, formatted, precision)`
  - Location: `runtime/cache.py` `_make_hashable()` FluentNumber case
  - Impact: Correct caching for FluentNumber with different underlying types or formatting

- **Cache Key Type Confusion for list/tuple** (DATA-INTEGRITY-CACHE-LIST-TUPLE-001):
  - Previous: Both `list` and `tuple` converted to plain tuple in cache keys
  - Issue: `[1, 2]` and `(1, 2)` produced same cache key despite potentially different formatted output
  - Fix: Lists tagged as `("__list__", ...)` and tuples as `("__tuple__", ...)`
  - Location: `runtime/cache.py` `_make_hashable()` list/tuple cases
  - Impact: Correct caching for list vs tuple argument values

- **Cache Entry Recursive Verification** (DATA-INTEGRITY-RECURSIVE-VERIFY-001):
  - Previous: `IntegrityCacheEntry.verify()` only checked entry checksum, not contained errors
  - Issue: Corrupted `FrozenFluentError` objects inside cache entry could pass verification
  - Fix: `verify()` now recursively calls `verify_integrity()` on all errors (defense-in-depth)
  - Location: `runtime/cache.py` `IntegrityCacheEntry.verify()` method
  - Impact: Complete integrity verification at all levels of data hierarchy

### Changed

- **Audit Log O(1) Eviction** (PERF-AUDIT-LOG-DEQUE-001):
  - Previous: Audit log used `list` with slicing for eviction: `self._audit_log = self._audit_log[-max_entries:]`
  - Performance issue: List slicing is O(n) for large logs
  - Change: Now uses `deque(maxlen=max_entries)` for O(1) automatic eviction
  - Location: `runtime/cache.py` lines 47, 467, 626
  - Impact: Improved performance for audit-enabled caches with high write volume

- **Dynamic Error Weight Calculation** (DATA-INTEGRITY-ERROR-WEIGHT-001):
  - Previous: Static 200-byte estimate per error (`_ERROR_WEIGHT_BYTES = 200`)
  - Issue: Errors with large messages or diagnostics exceeded estimate; errors with short messages wasted budget
  - Change: Dynamic weight calculation: base overhead (100 bytes) + actual string lengths
  - Location: `runtime/cache.py` `_estimate_error_weight()` function
  - Impact: More accurate memory bounding for error bloat protection

## [0.82.0] - 2026-01-21

### Fixed

- **Cache Checksum Includes Metadata** (SEC-METADATA-INTEGRITY-GAP-001):
  - Previous: `IntegrityCacheEntry._compute_checksum()` only hashed `formatted` and `errors`, excluding `created_at` and `sequence`
  - Security issue: Attacker could tamper with metadata fields without detection, compromising audit trail integrity
  - Fix: Checksum now includes ALL entry fields:
    1. `formatted`: Message output (UTF-8 encoded)
    2. `errors`: Each error's content_hash
    3. `created_at`: Monotonic timestamp (8-byte IEEE 754 double)
    4. `sequence`: Entry sequence number (8-byte signed big-endian)
  - Location: `runtime/cache.py` `_compute_checksum()` method
  - Impact: Cache entries with tampered timestamps or sequences now fail `verify()`

- **Error Content Hash Includes All Diagnostic Fields** (SEC-METADATA-INTEGRITY-GAP-002):
  - Previous: `FrozenFluentError._compute_content_hash()` only hashed `diagnostic.code` and `diagnostic.message`, excluding 10 other fields
  - Security issue: Diagnostic fields (span, hint, severity, resolution_path, etc.) could be tampered without detection
  - Fix: Content hash now includes ALL Diagnostic fields:
    - Core: `code.name`, `message`
    - Location: `span` (start, end, line, column as 4-byte big-endian)
    - Context: `hint`, `help_url`, `function_name`, `argument_name`, `expected_type`, `received_type`, `ftl_location`
    - Metadata: `severity`, `resolution_path` (each element)
    - Uses sentinel bytes for None distinction (prevents collision between None and empty/zero values)
  - Location: `diagnostics/errors.py` `_compute_content_hash()` method
  - Impact: Errors with tampered diagnostic fields now fail `verify_integrity()`

### Changed

- **Cache Checksum Semantics** (BREAKING for direct _compute_checksum users):
  - `IntegrityCacheEntry._compute_checksum(formatted, errors)` signature changed to `_compute_checksum(formatted, errors, created_at, sequence)`
  - `IntegrityCacheEntry.create()` now captures timestamp BEFORE computing checksum for consistency
  - Different entries with same content now have different checksums (timestamps differ)
  - This is correct behavior: checksums protect the entire entry, not just content

## [0.81.0] - 2026-01-20

### Fixed

- **Cache Type Collision Prevention** (DATA-INTEGRITY-CACHE-COLLISION-001):
  - Previous: Python's hash equality (`hash(1) == hash(True) == hash(1.0)`) caused cache collisions when these values produced different formatted outputs
  - Example bug: Format with `v=1` cached "1", then format with `v=True` returned cached "1" instead of correct "true"
  - Fix: `IntegrityCache._make_hashable()` now type-tags bool/int/float values to prevent hash collision
  - Location: `runtime/cache.py` lines 664-672
  - Impact: Correct cache behavior for mixed bool/int/float argument values

- **Bundle Strict Mode Cache Propagation** (ARCH-STRICT-MODE-DISCONNECT-001):
  - Previous: `FluentBundle(strict=True, enable_cache=True)` created cache with `strict=False`, ignoring bundle's strict setting
  - Consequence: Cache corruption was silently handled instead of raising `CacheCorruptionError`
  - Fix: Bundle's `strict` parameter now propagates to `IntegrityCache` constructor
  - Location: `runtime/bundle.py` line 270
  - Impact: Strict mode bundles now have fail-fast cache corruption detection

- **FormattingIntegrityError Type Safety** (TYPE-ERROR-LOOSE-TYPING-001):
  - Previous: `fluent_errors` property typed as `tuple[object, ...]` (loose typing)
  - Consequence: Consumers lost IDE autocomplete and type inference for error properties
  - Fix: Now typed as `tuple[FrozenFluentError, ...]` using TYPE_CHECKING import
  - Location: `integrity.py` lines 265, 274, 294
  - Impact: Improved type safety for strict mode error handling code

### Added

- **FluentBundle Reentrancy Documentation** (DOC-LOCKING-REENTRANCY-001):
  - Added "Reentrancy Limitation" section to `FluentBundle` class docstring
  - Documents that calling `add_resource()` or `add_function()` from custom functions during formatting raises `RuntimeError`
  - Location: `runtime/bundle.py` lines 83-90

## [0.80.0] - 2026-01-20

### Breaking

- **BREAKING**: Replaced `FormatCache` with `IntegrityCache` (DATA-INTEGRITY-002):
  - Previous: `FormatCache` class with simple LRU caching and tuple-based API
  - Now: `IntegrityCache` class with BLAKE2b-128 checksum verification
  - API change: `cache.put(...)` signature changed from `(msg_id, args, attr, locale, isolating, (result, errors))` to `(msg_id, args, attr, locale, isolating, result, errors)` (separate arguments)
  - API change: `cache.get(...)` returns `IntegrityCacheEntry | None` instead of `tuple[str, tuple[Error, ...]] | None`
  - Migration pattern:
    ```python
    # Before
    from ftllexengine.runtime.cache import FormatCache
    cache = FormatCache(maxsize=1000)
    cache.put("msg", args, None, "en", True, (result, errors))
    cached = cache.get("msg", args, None, "en", True)
    if cached:
        result, errors = cached

    # After
    from ftllexengine.runtime.cache import IntegrityCache
    cache = IntegrityCache(maxsize=1000, strict=False)
    cache.put("msg", args, None, "en", True, result, errors)
    entry = cache.get("msg", args, None, "en", True)
    if entry:
        result, errors = entry.to_tuple()
    ```
  - Impact: All direct cache API usage must be updated; FluentBundle internal usage updated automatically

- **BREAKING**: Replaced exception hierarchy with `FrozenFluentError` sealed class (DATA-INTEGRITY-001):
  - Previous: `FluentError`, `FluentReferenceError`, `FluentResolutionError`, `FluentCyclicReferenceError`, `FluentParseError`, `FormattingError` exception classes
  - Now: Single `FrozenFluentError` class with `ErrorCategory` enum for classification
  - Migration pattern:
    ```python
    # Before
    from ftllexengine import FluentReferenceError
    if isinstance(error, FluentReferenceError): ...

    # After
    from ftllexengine.diagnostics import FrozenFluentError, ErrorCategory
    if isinstance(error, FrozenFluentError) and error.category == ErrorCategory.REFERENCE: ...
    ```
  - Categories: `REFERENCE`, `RESOLUTION`, `CYCLIC`, `PARSE`, `FORMATTING`
  - Impact: All code checking error types via isinstance() must be updated

### Added

- **IntegrityCache: Financial-Grade Format Caching** (DATA-INTEGRITY-002):
  - Thread-safe LRU cache with BLAKE2b-128 checksum verification on every `get()`
  - `IntegrityCacheEntry`: Immutable cache entry with `formatted`, `errors`, `checksum`, `created_at`, `sequence`
  - `WriteLogEntry`: Immutable audit log entry for compliance and debugging
  - Write-once semantics: Optional `write_once=True` prevents overwrites (data race prevention)
  - Strict mode: `strict=True` (default) raises `CacheCorruptionError` on checksum mismatch; `strict=False` silently evicts
  - Audit logging: `enable_audit=True` records all cache operations to internal log
  - New integrity exceptions: `CacheCorruptionError`, `WriteConflictError`
  - Sequence numbers: Monotonically increasing for audit trail integrity
  - Configurable limits: `max_entry_weight`, `max_errors_per_entry`, `max_audit_entries`
  - Import: `from ftllexengine.runtime.cache import IntegrityCache, IntegrityCacheEntry`

- **Integrity Context and Exceptions** (DATA-INTEGRITY-002):
  - `IntegrityContext`: Dataclass for error context (component, operation, key, expected, actual, timestamp)
  - `CacheCorruptionError`: Raised when checksum verification fails (strict mode)
  - `WriteConflictError`: Raised when write-once semantics violated (strict mode)
  - Import: `from ftllexengine.integrity import CacheCorruptionError, WriteConflictError, IntegrityContext`

- **FrozenFluentError: Immutable, Content-Addressable Errors** (DATA-INTEGRITY-001):
  - Immutable: All attributes frozen after construction; mutation raises `ImmutabilityViolationError`
  - Sealed: Cannot be subclassed (enforced at static analysis via `@final` and at runtime)
  - Content-addressed: BLAKE2b-128 hash computed at construction for integrity verification
  - Hashable: Can be used in sets and as dict keys; hash based on content, not identity
  - Properties: `message`, `category`, `diagnostic`, `context`, `content_hash`, `fallback_value`
  - Method: `verify_integrity()` - recomputes hash with constant-time comparison

- **ErrorCategory Enum**: Replaces exception class hierarchy
  - `REFERENCE`: Unknown message, term, or variable reference
  - `RESOLUTION`: Runtime resolution failure (depth exceeded, function error)
  - `CYCLIC`: Cyclic reference detected
  - `PARSE`: Bi-directional parsing failure (number, date, currency)
  - `FORMATTING`: Locale-aware formatting failure

- **FrozenErrorContext Dataclass**: Immutable context for parse/formatting errors
  - Fields: `input_value`, `locale_code`, `parse_type`, `fallback_value`
  - Used to provide additional context for `PARSE` and `FORMATTING` category errors

- **DataIntegrityError and ImmutabilityViolationError**: New integrity exceptions
  - `DataIntegrityError`: Base class for data integrity violations
  - `ImmutabilityViolationError`: Raised when attempting to mutate frozen objects
  - Import: `from ftllexengine.integrity import DataIntegrityError, ImmutabilityViolationError`

- **FormattingIntegrityError: Strict Mode Exception** (DATA-INTEGRITY-003):
  - Raised when `strict=True` bundle encounters ANY formatting errors
  - Carries original Fluent errors: `fluent_errors` property (tuple of FrozenFluentError)
  - Carries fallback value: `fallback_value` property (what would have been returned in non-strict mode)
  - Carries message ID: `message_id` property for identifying failed message
  - Includes `IntegrityContext` for post-mortem analysis
  - Import: `from ftllexengine.integrity import FormattingIntegrityError`

- **FluentBundle strict Mode Parameter** (DATA-INTEGRITY-003):
  - New `strict: bool = False` parameter in `FluentBundle.__init__`
  - When `strict=True`: Any formatting error raises `FormattingIntegrityError` instead of returning fallback
  - Property: `bundle.strict` returns current strict mode setting
  - Use case: Financial applications that cannot accept silent fallbacks for missing translations
  - Example:
    ```python
    bundle = FluentBundle("en", strict=True)
    bundle.add_resource("msg = Hello, { $name }!")
    # Raises FormattingIntegrityError instead of returning "Hello, {$name}!"
    bundle.format_pattern("msg", {})
    ```

## [0.79.0] - 2026-01-18

### Breaking

- **BREAKING**: Renamed `FunctionCallInfo.positional_args` to `positional_arg_vars` (SEM-INTROSPECTION-DATA-LOSS-001):
  - Previous: Field named `positional_args` suggested it contained all positional arguments
  - Actual behavior: Only contains variable reference names, not literals or other expressions
  - New name: `positional_arg_vars` accurately describes contents (variable names only)
  - Migration: Replace all `.positional_args` access with `.positional_arg_vars`
  - Impact: Code using introspection API to analyze function calls
  - Location: `introspection.py` lines 123-133, 392-397

### Added

- **Term Positional Arguments Validation Warning** (VAL-TERM-POSITIONAL-ARGS-001): SemanticValidator now warns when term references include positional arguments:
  - Reason: Per Fluent spec, terms only accept named arguments; positional arguments are silently ignored at runtime
  - Warning: `VALIDATION_TERM_POSITIONAL_ARGS` - "Term '-{name}' called with positional arguments; positional arguments are ignored for term references"
  - Impact: Catches likely user errors at validation time instead of silent runtime behavior
  - Location: `syntax/validator.py` lines 310-323

- **Cross-Resource Cycle Detection** (VAL-CROSS-RESOURCE-CYCLES-001): `FluentBundle.validate_resource()` now detects cycles involving dependencies OF existing bundle entries:
  - Previous: Only detected cycles within the new resource or involving known entry names (not their dependencies)
  - Example gap: Resource 1 has `msg_a = { msg_b }`, Resource 2 has `msg_b = { msg_a }` - cycle was not detected
  - Now: Bundle tracks dependencies (`_msg_deps`, `_term_deps`) for all loaded entries
  - Impact: Validation now catches cross-resource cycles that would cause infinite loops at runtime
  - Location: `runtime/bundle.py` lines 219-222, 628-652; `validation/resource.py` lines 467-469, 518-538

### Changed

- **Dependency Graph Extended Parameters**: `validate_resource()` and `_build_dependency_graph()` accept optional `known_msg_deps` and `known_term_deps` parameters for cross-resource validation.

## [0.78.0] - 2026-01-18

### Breaking

- **BREAKING**: Removed `FluentSyntaxError` exception class (DEAD-CODE-ERROR-001):
  - Previous: `FluentSyntaxError` was exported from `ftllexengine` and `ftllexengine.diagnostics`
  - Reason: Class was never raised by any code path; Fluent parser uses Junk nodes for syntax errors per robustness principle
  - Migration: Remove all `FluentSyntaxError` imports and exception handlers; use Junk node detection instead
  - Example: `if any(isinstance(e, Junk) for e in resource.body): ...`

### Fixed

- **NUMBER() CLDR Precision Calculation** (SEM-PRECISION-MISMATCH-001): Fixed precision calculation for CLDR plural rule matching:
  - Previous: `FluentNumber.precision` was set to `minimum_fraction_digits` parameter, not actual visible digits
  - Root cause: CLDR v operand must reflect ACTUAL formatted output (e.g., "1.2" has v=1, not v=0)
  - Now: Added `_compute_visible_precision()` helper that counts digits after decimal separator in formatted string
  - Impact: Plural category selection now matches CLDR specification for all locales
  - Location: `runtime/functions.py` lines 39-72, 114-118

- **Documentation: `max_source_size` Precision** (DOC-BUNDLE-001): Clarified `max_source_size` docstrings:
  - Previous: "10M" was ambiguous (decimal megabytes vs binary mebibytes)
  - Now: "10 MiB / 10,485,760 chars" provides unambiguous specification
  - Location: `runtime/bundle.py` (3 occurrences)

### Changed

- **PathResourceLoader Validation** (USABILITY-LOCALIZATION-001): Added fail-fast validation for `{locale}` placeholder:
  - Previous: Missing placeholder caused silent failures at runtime (locale substitution returned unchanged path)
  - Now: `ValueError` raised at construction time with clear error message
  - Impact: Configuration errors detected immediately, not at first resource load
  - Location: `localization.py` `PathResourceLoader.__post_init__`

## [0.77.0] - 2026-01-17

### Fixed

- **Serializer Roundtrip Whitespace Corruption** (IMPL-SERIALIZER-ROUNDTRIP-CORRUPTION-001): Fixed data corruption during roundtrip serialization of patterns with embedded leading whitespace:
  - Previous: Patterns with TextElements where leading whitespace follows a newline (e.g., "Line 1\n  Line 2") would lose the semantic whitespace on roundtrip
  - Root cause: Serializer's per-element indentation logic didn't account for inter-element whitespace semantics; parser's common_indent calculation would strip all indentation
  - Now: Added `_pattern_needs_separate_line()` helper to detect problematic patterns; serializer emits such patterns on separate lines with continuation indent to preserve whitespace through roundtrip
  - Impact: Multi-line messages with indented continuation lines (code examples, formatted text) now preserve all whitespace correctly
  - Location: `syntax/serializer.py` lines 541-552, 557-559

- **Cache Tuple Argument Handling** (IMPL-CACHE-TUPLE-REJECTION-001): Fixed FormatCache silently bypassing cache for arguments containing tuples:
  - Previous: `_make_hashable()` lacked `case tuple():` handler, causing tuples to fall through to default case and raise TypeError, which was caught and treated as unhashable
  - Now: Added tuple handler that recursively processes elements, consistent with list handling
  - Impact: Format calls with tuple arguments now correctly cache results instead of recomputing every time
  - Location: `runtime/cache.py` lines 343-346

- **Validation CRLF Line Position Accuracy** (IMPL-VALIDATION-OFFSET-MISMATCH-001): Fixed validation error line/column positions for files with CRLF line endings:
  - Previous: LineOffsetCache used raw source positions while AST spans used normalized (LF-only) positions, causing cumulative drift in error locations for CRLF files
  - Root cause: Parser normalizes CRLF/CR to LF internally, but validation was building offset cache from raw source
  - Now: Validation normalizes source using same regex pattern as parser before building LineOffsetCache
  - Impact: Windows-originated FTL files now report correct error locations without position drift
  - Location: `validation/resource.py` lines 678-682

- **Parser Attribute Blank Line Handling** (IMPL-PARSER-ATTRIBUTE-BLANK-LINE-001): Fixed attribute parsing to support blank lines between attributes per Fluent specification:
  - Previous: Parser terminated attribute parsing on blank lines, silently dropping subsequent attributes
  - Root cause: Loop consumed single newline then checked for `.`, breaking on blank lines (second newline)
  - Now: Added inner loop to skip consecutive newlines (blank lines) before checking for attribute marker
  - Spec compliance: Fluent EBNF `Attribute ::= line_end blank? "." ...` where `blank ::= (blank_inline | line_end)+`
  - Impact: FTL files with blank lines between attributes for readability now parse correctly
  - Location: `syntax/parser/rules.py` lines 1719-1722

### Added

- Added `_pattern_needs_separate_line()` helper method to serializer for detecting patterns requiring separate-line serialization
- Added `_CONT_INDENT` constant in serializer for continuation line indentation

## [0.76.0] - 2026-01-17

### Performance

- **Cursor Hot Path Optimization** (PERF-CURSOR-*): Reduced cursor object allocation in parsing hot paths:
  - `Cursor.skip_spaces()`: Integer arithmetic loop replaces O(N) cursor allocations
  - `Cursor.skip_whitespace()`: Same optimization pattern for whitespace skipping
  - `Cursor.skip_to_line_end()`: C-level `str.find()` replaces character-by-character loop
  - `LineOffsetCache.__init__()`: `str.find()` loop replaces `enumerate()` iteration
  - Location: `syntax/cursor.py` lines 233-239, 265-271, 373-378, 468-477

- **Parser Indentation Counting** (PERF-RULES-INDENT-001): Replaced cursor-based loop with integer arithmetic in `_count_leading_spaces()`:
  - Eliminates O(N) cursor object allocations on multiline pattern parsing hot path
  - Location: `syntax/parser/rules.py` lines 622-629

- **Blank Line Detection** (PERF-CORE-BLANK-CHECK-001): Replaced substring containment check with bounded `str.find()`:
  - `source.find("\n", start, end) != -1` avoids temporary substring allocation
  - Location: `syntax/parser/core.py` line 84

- **Unicode Escape Validation** (PERF-ESCAPE-HEX-001): Replaced `all(c in _HEX_DIGITS for c in hex_digits)` with `frozenset.issuperset()`:
  - O(1) membership test per character via hash lookup
  - `_HEX_DIGITS` changed from `str` to `frozenset[str]`
  - Location: `syntax/parser/primitives.py` lines 85-86, 338-341, 367-370

- **Identifier Validation** (PERF-ID-VALIDATION-REGEX-001): Replaced `all(is_identifier_char(ch) for ch in name[1:])` with compiled regex:
  - C-level regex matching outperforms Python-level iteration
  - Added `_IDENTIFIER_CONTINUATION_PATTERN` compiled regex
  - Location: `core/identifier_validation.py` lines 40-43, 148-149

- **Serializer Brace Handling** (PERF-SERIALIZER-BRACES-001): Replaced character-by-character loop with `str.find()` scanning in `_serialize_text_with_braces()`:
  - Locates next brace via C-level search, emits text runs in bulk
  - Location: `syntax/serializer.py` lines 554-588

- **Introspection Name Caching** (PERF-INTROS-VAR-SET-001): Added pre-computed name caches to `MessageIntrospection`:
  - `_variable_names: frozenset[str]` and `_function_names: frozenset[str]` computed once at creation
  - `get_variable_names()`, `get_function_names()` now return cached values (O(1))
  - `requires_variable()` uses O(1) frozenset membership vs O(N) `any()` iteration
  - Location: `introspection.py` lines 183-219, 560-572

## [0.75.0] - 2026-01-16

### Added

- **Cache Lifecycle Management API** (CACHE-LIFECYCLE-MANAGEMENT): Added comprehensive cache clearing API for all module-level caches:
  - Added: `clear_all_caches()` top-level function to clear all library caches in one call
  - Added: `clear_locale_cache()` in `ftllexengine.locale_utils` for Babel locale cache
  - Added: `clear_date_caches()` in `ftllexengine.parsing.dates` for date/datetime pattern caches
  - Added: `clear_currency_caches()` in `ftllexengine.parsing.currency` for currency-related caches
  - Added: `clear_introspection_cache()` in `ftllexengine.introspection` (already existed, now exported)
  - Added: `LocaleContext.clear_cache()` class method (already existed, now documented)
  - Export: All clear functions exported through their respective module `__all__` lists
  - Location: `__init__.py` lines 75-108, `locale_utils.py`, `parsing/__init__.py`, `parsing/dates.py`, `parsing/currency.py`
  - Rationale: Applications need to clear caches for testing, hot-reloading configurations, or memory management

- **Aggregate Cache Statistics API** (API-BUNDLE-STATS-AGGREGATION-001): Added `FluentLocalization.get_cache_stats()` method to aggregate cache statistics across all bundles:
  - Returns: `dict[str, int | float] | None` with keys: `size`, `maxsize`, `hits`, `misses`, `hit_rate` (0.0-100.0), `unhashable_skips`, `bundle_count`
  - Returns `None` when caching is disabled (`enable_cache=False`)
  - Thread-safe: Uses existing `RLock` for concurrent access
  - Aggregation: Sums values from all initialized `FluentBundle` instances
  - Location: `src/ftllexengine/localization.py` lines 1155-1193
  - Rationale: Production monitoring requires aggregate cache metrics for multi-locale deployments without accessing private `_bundles` attribute

### Fixed

- **Test Documentation Accuracy**: Fixed incorrect test docstring that claimed `functools.cache` prevents thundering herd on cold cache. The test now correctly documents that `functools.cache` is thread-safe for cache access but does NOT prevent multiple threads from simultaneously computing on a cold cache. Test pre-warms cache to verify intended behavior.
  - Location: `tests/test_coverage_final_gaps.py::TestCurrencyCachingBehavior::test_concurrent_currency_maps_access`
- **Parser Dead Code Elimination**: Eliminated unreachable branch in `_has_blank_line_between` comment merging logic. Simplified implementation from 12 lines with newline counter to idiomatic single expression: `"\n" in source[start:end]`. The branch condition `newline_count >= 1` was always True after `newline_count += 1`, making the subsequent check dead code. Uses CPython's optimized `memchr()` for character containment. This improves code maintainability and achieves 100% branch coverage.
  - Location: `src/ftllexengine/syntax/parser/core.py` lines 80-83
  - Impact: No behavioral change; dead code removal and performance improvement

## [0.74.0] - 2026-01-15

### Fixed

- **Serializer Named Argument Validation** (LOGIC-SERIALIZER-VALIDATION-001): Fixed `serialize(validate=True)` to catch invalid named arguments in programmatically-constructed ASTs:
  - Added: Duplicate named argument name detection per CallArguments
  - Added: Named argument value type validation (must be StringLiteral or NumberLiteral per FTL EBNF)
  - Previous: Serializer accepted and produced invalid FTL like `NUMBER($x, style: "a", style: "a")` or `NUMBER($x, style: $var)`
  - Now: `SerializationValidationError` raised with descriptive message identifying the violation
  - Rationale: Parser enforces these constraints via `parse_call_arguments()`, but serializer validation did not, allowing programmatic AST construction to bypass spec compliance
  - Impact: Programmatic AST construction errors caught before producing unparseable FTL
  - Location: `syntax/serializer.py` new `_validate_call_arguments()` function (lines 141-197)

### Added

- Added `_validate_call_arguments()` internal function in serializer to centralize CallArguments validation for both FunctionReference and TermReference
- Added test suite in `tests/test_serializer_validation.py` covering:
  - Duplicate named argument detection for FunctionReference and TermReference
  - Non-literal value rejection (VariableReference, FunctionReference as values)
  - Valid arguments with StringLiteral and NumberLiteral
  - Validation bypass when `validate=False`

## [0.73.0] - 2026-01-14

### Breaking

- **BREAKING**: Changed `NumberLiteral.value` type from `int | float` to `int | Decimal` for financial-grade precision ([C-SEMANTIC-001]):
  - Decimal literals now use Python's `Decimal` type to eliminate IEEE 754 rounding surprises
  - Example: `0.1 + 0.2 == 0.3` now works correctly (previously failed due to float precision)
  - Integer literals continue using `int` for memory efficiency
  - Impact: Code accessing `NumberLiteral.value` directly will receive `Decimal` instead of `float` for decimal numbers
  - Migration: Update code expecting `float` to handle `Decimal` (most arithmetic operations work transparently)

### Changed

- Moved hardcoded locale length limit (1000) from `FluentBundle` to `constants.MAX_LOCALE_LENGTH_HARD_LIMIT` for configurability and consistency with other DoS prevention constants ([G-DEBT-001])
- Added `max_parse_errors` parameter to `FluentParserV1.__init__()` with default `MAX_PARSE_ERRORS = 100`. Parser now aborts after exceeding the limit, preventing memory exhaustion from malformed input that generates excessive Junk entries. Setting `max_parse_errors=0` disables the limit (consistent with `max_source_size=0` semantics) ([F-SEC-DoS-001])
- Enhanced `ASTTransformer.generic_visit()` with scalar field validation that distinguishes between required and optional fields. Required fields (e.g., `Message.id`, `Placeable.expression`) raise `TypeError` when visit methods return `None` or `list[ASTNode]`. Optional fields (e.g., `Message.comment`, `Message.value`, `Term.comment`, `MessageReference.attribute`, `TermReference.attribute`, `TermReference.arguments`) now correctly accept `None` returns to enable node removal via transformers ([B-ARCH-TYPE-001])

### Added

- Added `constants.MAX_LOCALE_LENGTH_HARD_LIMIT` constant (value: 1000) for DoS prevention via locale code validation
- Added `constants.MAX_PARSE_ERRORS` constant (value: 100) for DoS prevention via parse error accumulation limit
- Added `ASTTransformer._validate_scalar_result()` internal method for runtime validation of required scalar field assignments during AST transformation
- Added `ASTTransformer._validate_optional_scalar_result()` internal method for validation of optional scalar fields, permitting `None` returns for node removal
- Added test suite `tests/test_decimal_precision.py` verifying Decimal precision guarantee for financial calculations
- Added test suite `tests/test_parse_error_limit.py` verifying parse error limit DoS protection and Fluent spec-compliant Junk merging behavior
- Added test suite `tests/test_transformer_validation.py` verifying ASTTransformer scalar field validation for both required and optional fields

### Fixed

- Fixed precision loss in decimal number literals. Previously, `1.0000000000000001` would be stored as float losing precision; now stored as `Decimal("1.0000000000000001")` preserving all digits
- Fixed potential memory exhaustion from adversarial FTL input with thousands of syntax errors. Parser now aborts after 100 errors (configurable via `max_parse_errors`)
- Fixed `ASTTransformer` incorrectly rejecting `None` returns for optional scalar fields. Previously, transformers returning `None` for fields like `Message.comment` raised `TypeError`, making comment removal impossible. Now correctly distinguishes required fields (reject `None`) from optional fields (accept `None` for removal)

## [0.72.0] - 2026-01-14

### Removed
- **Dead Compatibility Code** (DEBT-DEAD-COMPAT-001): Removed unreachable try/except block for importlib.metadata import:
  - Previous: `try/except ImportError` wrapped `importlib.metadata` imports with fallback error
  - Now: Direct import without exception handling
  - Rationale: `importlib.metadata` is standard library since Python 3.8; project targets Python 3.13+
  - Impact: No behavioral change; dead code removal only
  - Location: `__init__.py` lines 117-122

### Changed
- **Babel Type Safety** (TYPE-ANY-BABEL-001): Added Protocol types for Babel modules to improve type safety:
  - Added: `BabelNumbersProtocol` defining `format_decimal()`, `format_currency()`, `format_percent()` signatures
  - Added: `BabelDatesProtocol` defining `format_datetime()`, `format_date()`, `format_time()` signatures
  - Changed: `get_babel_numbers()` return type from `Any` to `BabelNumbersProtocol`
  - Changed: `get_babel_dates()` return type from `Any` to `BabelDatesProtocol`
  - Rationale: Protocols provide type safety for Babel consumers without requiring full type stubs; mypy can now catch type errors in code calling Babel functions
  - Impact: Improved static type checking for number, date, and currency formatting functions
  - Location: `core/babel_compat.py` lines 45-117, 241-272

### Fixed
- **Identifier Validation Unification** (SEC-SERIALIZER-UNBOUNDED-001, DRY-ID-VALIDATION-001): Unified identifier validation across parser and serializer to ensure consistency:
  - Added: New module `core/identifier_validation.py` as single source of truth for FTL identifier grammar
  - Added: `is_valid_identifier(name: str) -> bool` function validating both syntax and length constraints
  - Added: `is_identifier_start(ch: str) -> bool` and `is_identifier_char(ch: str) -> bool` for streaming validation
  - Changed: Serializer now uses unified validation module instead of regex pattern
  - Changed: Parser imports identifier character functions from unified module
  - Fixed: Serializer now enforces 256-character identifier length limit (previously only checked syntax)
  - Fixed: Parser and serializer now accept/reject identical identifier sets (prevents divergence)
  - Added: Property-based test `test_identifier_validation_unification.py` verifying parser/serializer consistency
  - Rationale: Duplication created maintenance burden and consistency risk; parser enforced length limits but serializer did not; programmatic AST construction could bypass parser limits
  - Impact: Serializer now rejects identifiers exceeding 256 characters; prevents DoS via overlength identifiers in programmatic ASTs
  - Locations: New file `core/identifier_validation.py`, `syntax/serializer.py` lines 18-20, 77-95 (removed `_IDENTIFIER_PATTERN` regex), `syntax/parser/primitives.py` lines 49-51, 82-84 (removed local function definitions), new test file `tests/test_identifier_validation_unification.py`

- **Documentation Accuracy** (DOC-STALE-SERIALIZER-001): Fixed FluentSerializer docstring to show correct import path:
  - Previous: Docstring demonstrated `from ftllexengine.syntax import parse, FluentSerializer`
  - Now: Demonstrates public API `from ftllexengine.syntax import parse, serialize`
  - Added: Advanced usage example showing direct class import for users needing class instantiation
  - Rationale: `FluentSerializer` is intentionally not exported from `ftllexengine.syntax`; users should use `serialize()` function
  - Impact: Users following docstring now get working imports instead of ImportError
  - Location: `syntax/serializer.py` FluentSerializer class docstring lines 251-263

## [0.71.0] - 2026-01-13

### Removed
- **Convenience Re-exports** (FTL-MODERN-001): Removed convenience re-exports that violated canonical import locations:
  - Removed: `FluentValue` from `ftllexengine.runtime.resolver` exports
  - Removed: `get_babel_locale()` function from `ftllexengine.core.babel_compat` module
  - Migration (FluentValue): Replace `from ftllexengine.runtime.resolver import FluentValue` with `from ftllexengine.runtime.function_bridge import FluentValue`
  - Migration (get_babel_locale): Replace `from ftllexengine.core.babel_compat import get_babel_locale` with `from ftllexengine.locale_utils import get_babel_locale`
  - Rationale: Convenience re-exports create multiple import paths for the same functionality, obscuring the canonical location and making the codebase harder to navigate
  - Impact: Code importing from non-canonical locations will raise ImportError
  - Locations: `runtime/resolver.py` `__all__`, `core/babel_compat.py` removed `get_babel_locale()` function, updated `babel_compat.py` module docstring

### Changed
- **Decorator Metadata Preservation** (FTL-MODERN-004): Standardized decorators to use `functools.wraps` for proper metadata preservation:
  - Changed: `with_read_lock` and `with_write_lock` decorators in `runtime/rwlock.py`
  - Previous: Manual `__name__` and `__doc__` assignment
  - Now: Uses `@wraps(func)` decorator for comprehensive metadata preservation
  - Rationale: `functools.wraps` is the standard library mechanism for preserving function metadata, handling `__name__`, `__doc__`, `__module__`, `__qualname__`, `__annotations__`, and `__dict__`
  - Impact: Decorated methods now correctly preserve all function metadata, improving introspection and debugging
  - Location: `runtime/rwlock.py` lines 289, 321

### Fixed
- **Variant Marker Blank Handling** (FTL-GRAMMAR-003): Fixed `_is_variant_marker()` to correctly handle whitespace after opening bracket per Fluent EBNF specification:
  - Previous: Parser failed to recognize variant keys with spaces after opening bracket (e.g., `[ one]`)
  - Now: Skips `blank_inline` (spaces only) after `[` before reading variant key, per Fluent EBNF: `VariantKey ::= "[" blank? (NumberLiteral | Identifier) blank? "]"`
  - Rationale: Fluent specification explicitly allows optional whitespace after opening bracket in variant keys
  - Impact: Variant keys like `[ one]`, `[  two]` now parse correctly instead of being treated as literal text
  - Location: `syntax/parser/rules.py` `_is_variant_marker()` lines 251-256

- **Nesting Depth Diagnostic** (FTL-DIAG-001): Parser now emits specific diagnostic when nesting depth limit exceeded:
  - Previous: Generic "Parse error" with `DiagnosticCode.PARSE_JUNK` when exceeding max nesting depth
  - Now: Specific `DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED` with descriptive message including the limit value
  - Added: New diagnostic code `PARSE_NESTING_DEPTH_EXCEEDED = 3005` in `diagnostics/codes.py`
  - Implementation: `ParseContext` now tracks depth-exceeded state via mutable flag shared across all nested contexts. When `parse_placeable()` detects depth exceeded, it marks the flag. Junk creation sites in `FluentParserV1.parse()` check this flag and emit the specific diagnostic.
  - Rationale: Specific diagnostics help users identify the exact cause of parse failures, especially for DoS prevention mechanisms
  - Impact: Deeply nested FTL like `{ { { ... } } }` exceeding limit now shows "Nesting depth limit exceeded (max: 100)" instead of generic "Parse error"
  - Locations: `diagnostics/codes.py` new code `PARSE_NESTING_DEPTH_EXCEEDED = 3005`, `syntax/parser/rules.py` `ParseContext` lines 100-151, `parse_placeable()` lines 1583-1589, `syntax/parser/core.py` Junk creation lines 513-526

## [0.70.0] - 2026-01-13

### Fixed
- **Multiline Pattern Blank Line Indentation** (FTL-GRAMMAR-001): Fixed `parse_pattern` and `parse_simple_pattern` to correctly handle blank lines before the first content line in multiline patterns:
  - Previous: `is_indented_continuation()` skipped all blank lines to find indented content, but `parse_pattern()` advanced past only one newline before measuring `common_indent`. When cursor landed on a blank line, `_count_leading_spaces()` returned 0, causing all indentation to be preserved literally.
  - Now: Both `skip_multiline_pattern_start()` and continuation handling in `parse_pattern()`/`parse_simple_pattern()` skip all blank lines before measuring common indent.
  - API Change: `skip_multiline_pattern_start()` now returns `tuple[Cursor, int]` (cursor and initial indent count) instead of just `Cursor`. This allows `parse_pattern()` to receive the pre-computed `initial_common_indent`.
  - Pattern Fix: When handling continuation lines, newlines are now merged with the previous element immediately, while extra spaces (beyond common indent) are prepended to the next text element. This ensures correct element boundaries.
  - Impact: FTL patterns like `msg =\n\n    value` now correctly strip the 4-space indentation, producing `"value"` instead of `"    value"`.
  - Location: `syntax/parser/whitespace.py` `skip_multiline_pattern_start()`, `syntax/parser/rules.py` `parse_pattern()`, `parse_simple_pattern()`, `parse_message()`, `parse_attribute()`, `parse_term()`

## [0.69.0] - 2026-01-12

### Fixed
- **Parser Comment Blank Line Detection** (FTL-PARSER-001): Fixed `_has_blank_line_between` to correctly detect single blank lines between comments:
  - Previous: Required two newlines in checked region, causing adjacent comments with single blank line to incorrectly merge
  - Now: Condition changed from `newline_count >= 2` to `newline_count >= 1`
  - Rationale: `parse_comment` already consumes first comment's trailing newline, so single newline in gap region indicates blank line
  - Impact: Comments separated by one blank line now correctly produce separate AST Comment nodes per Fluent specification
  - Location: `parser/core.py` `_has_blank_line_between()` line 88

- **Number Formatting Precision Loss** (FTL-RUNTIME-001): Removed unnecessary float() conversion in `format_number` that degraded Decimal precision:
  - Previous: `value = float(Decimal(...).quantize(...))` converted back to float after quantization
  - Now: `value = Decimal(...).quantize(...)` preserves Decimal precision
  - Rationale: Babel's `format_decimal()` explicitly supports Decimal type; float conversion defeats precision-preserving quantization
  - Impact: Large decimal values (e.g., 123456789.12) now format without floating-point artifacts
  - Location: `runtime/locale_context.py` `format_number()` line 420

- **Dependency Graph Term Prefix Inconsistency** (LOGIC-GRAPH-DEPENDENCY-001): Fixed `build_dependency_graph` to prefix term references in dependency values:
  - Previous: Keys used prefixed format (`"msg:id"`, `"term:id"`) but values contained unprefixed term IDs (`{"brand"}`)
  - Now: Values also use prefixed format (`{"term:brand"}`) matching key namespace
  - Rationale: `detect_cycles()` looks up neighbor IDs as keys; unprefixed values failed to find prefixed keys
  - Impact: Term-to-term cycles (A->B->A) and cross-type cycles now correctly detected
  - Location: `analysis/graph.py` `build_dependency_graph()` lines 238, 246

- **Batch Operation Lock Granularity** (FTL-RUNTIME-002): Optimized `get_all_message_variables` to use single read lock for atomic snapshot:
  - Previous: N+1 lock acquisitions (one for `get_message_ids()`, N for `get_message_variables()`)
  - Now: Single read lock acquires atomic snapshot directly from `self._messages.items()`
  - Rationale: Reduces lock overhead for large bundles; prevents inconsistent snapshots during concurrent mutations
  - Impact: Improved performance and correctness for thread-safe batch introspection
  - Location: `runtime/bundle.py` `get_all_message_variables()` lines 1010-1014

- **Serializer Redundant Newlines** (NAME-SERIALIZER-SPACING-001): Fixed serializer to preserve compact message formatting without extra blank lines:
  - Previous: Message/Term entries ended with `"\n"` but separator logic added another `"\n"`, creating blank line
  - Now: Message->Message and Term->Term transitions skip extra separator (entries already end with newline)
  - Rationale: Roundtrip of compact FTL (no blank lines between messages) should preserve formatting
  - Impact: `"msg1 = A\nmsg2 = B"` now roundtrips without introducing blank line
  - Location: `syntax/serializer.py` `_serialize_resource()` lines 343-347
  - Note: Comment separation logic preserved (blank lines prevent attachment/merging per specification)

## [0.68.0] - 2026-01-12

### Removed
- **Backwards Compatibility Re-export** (DEBT-CACHE-REEXPORT): Removed `DEFAULT_MAX_ENTRY_SIZE` from `ftllexengine.runtime.cache` module exports:
  - Previous: `DEFAULT_MAX_ENTRY_SIZE` re-exported from `cache.py` for backwards compatibility
  - Now: Import from canonical location `ftllexengine.constants` only
  - Migration: Replace `from ftllexengine.runtime.cache import DEFAULT_MAX_ENTRY_SIZE` with `from ftllexengine.constants import DEFAULT_MAX_ENTRY_SIZE`

- **Test Strategy Aliases** (DEBT-STRATEGY-ALIASES): Removed backwards compatibility aliases from `tests/strategies.py`:
  - Removed: `ftl_messages` alias for `ftl_message_nodes`
  - Removed: `ftl_junk` alias for `ftl_junk_nodes` (dead code, never used)
  - Updated: `test_validator_hypothesis.py` and `test_serializer_roundtrip.py` to use canonical names

- **Dead Exception Handling** (FTL-DEAD-EXCEPTION-001): Removed unreachable FluentSyntaxError catch blocks:
  - Previous: `FluentBundle.add_resource()` and `validate_resource()` caught FluentSyntaxError that is never raised
  - Now: Dead catch blocks removed from `bundle.py` and `validation/resource.py`
  - Rationale: Parser returns errors in Resource.junk, never raises FluentSyntaxError during normal parsing
  - Documentation: Removed FluentSyntaxError from docstring Raises section in `parser/core.py`

### Fixed
- **Misleading Comment** (DEBT-RESOLVER-COMMENT): Clarified `FluentValue` re-export comment in `resolver.py`:
  - Previous: Comment stated "for public API compatibility" (implied backwards compatibility)
  - Now: Comment states "for module convenience" (accurate architectural description)

- **Placeable Whitespace Handling** (FTL-STRICT-WHITESPACE-001): Parser now allows any whitespace (not just inline) around placeable expressions:
  - Previous: `skip_blank_inline()` only skipped spaces/tabs before opening and after closing placeable braces
  - Now: `skip_blank()` allows spaces, tabs, and newlines around `{` and `}` in placeable expressions
  - Locations: `parse_placeable()` opening brace (line 1543), after expression (line 1557), `parse_block_text_continuation()` (line 1594)
  - Rationale: Fluent spec does not restrict whitespace in placeables to inline-only

- **Parser Dispatch Redundancy** (FTL-REDUNDANT-DISPATCH-001): Removed redundant underscore check in argument expression parsing:
  - Previous: Dispatch checked `is_identifier_start(ch) or ch == "_"` but `_` makes `is_identifier_start()` return True
  - Now: Simplified to `is_identifier_start(ch)` only
  - Location: `parse_argument_expression()` line 1488
  - Impact: No behavioral change; code cleanup only

- **Coverage-Motivated Code Removal** (FTL-COVERAGE-COMMENT-001): Removed pointless `continue` statement in resolver:
  - Previous: `case Entry(): continue` existed only for branch coverage, not semantic value
  - Now: Removed from `_validate_references()` match block
  - Rationale: Test coverage should not drive production code structure

- **Term Attribute Resolution Order** (FTL-TERM-ATTR-ORDER-001): Term attributes now use last-wins semantics matching Fluent specification:
  - Previous: `next()` iterator found first matching attribute, ignoring later definitions
  - Now: `next(reversed(...))` finds last matching attribute
  - Impact: FTL with duplicate term attributes now resolves consistently with reference implementation
  - Example: `-brand = X` with `.legal = Old` then `.legal = New` now resolves to "New"

- **Cache Key Isolation** (FTL-CACHE-KEY-ISOLATION-001): Format cache now includes `use_isolating` parameter in cache key:
  - Previous: Same message formatted with different isolation settings shared cache entry
  - Now: `use_isolating` boolean is 5th element in cache key tuple
  - Impact: Prevents incorrect cache hits when isolation setting differs between calls
  - API: `FormatCache.get()` and `.put()` now require `use_isolating` parameter

- **Plural Category Precision** (FTL-PLURAL-PRECISION-001): Precision=0 now triggers quantization for plural selection:
  - Previous: `precision > 0` check excluded precision=0, so integer formatting didn't quantize
  - Now: `precision >= 0` ensures precision=0 correctly quantizes to integer form
  - Impact: `NUMBER($n, maximumFractionDigits: 0)` now correctly rounds before plural selection
  - Location: `plural_rules.py` condition in `select_plural_category()`

- **Number Rounding Consistency** (FTL-NUMBER-ROUNDING-001): All number formatting now uses ROUND_HALF_UP:
  - Previous: Only precision=0 applied ROUND_HALF_UP quantization, other precision levels used default rounding
  - Now: ROUND_HALF_UP applied for all precision levels (0, fixed, variable)
  - Impact: Consistent half-up rounding (2.5→3, 3.5→4) matches CLDR specification
  - Location: `locale_context.py` format_number() method
  - Note: Special values (inf, -inf, NaN) bypass quantization to avoid InvalidOperation errors

- **Serializer Indentation** (FTL-SERIALIZER-DOUBLE-INDENT-001): Pattern text containing newlines no longer double-indents:
  - Previous: Pattern with `\n` got additional 4-space indent, producing 8-space indent on continuation
  - Now: Regex `r"\n(?!    )"` only adds indent after newlines not already followed by 4+ spaces
  - Impact: Roundtrip serialization preserves original indentation
  - Example: `msg = Line1\n    Line2` no longer becomes `msg = Line1\n        Line2`

- **Validator Numeric Normalization** (FTL-VALIDATOR-NUMERIC-NORMALIZATION-001): Variant key comparison no longer uses scientific notation:
  - Previous: `str(Decimal("100").normalize())` returned "1E2", causing false duplicate detection
  - Now: `format(normalized, "f")` returns "100" for consistent comparison
  - Impact: Select expression variant keys like `[100]` and `[1E2]` correctly compared
  - Location: `validator.py` `_variant_key_to_string()` method

## [0.67.0] - 2026-01-11

### Fixed
- **Thread Safety** (SEC-BUNDLE-WRITE-BLOCKING): `FluentBundle.add_resource()` now parses FTL source outside the write lock to minimize reader contention:
  - Previous: Parse operation occurred inside write lock, blocking all concurrent read operations (format_pattern, has_message)
  - Now: Parse executes outside lock (parser is stateless/thread-safe), only registration (dict updates) requires exclusive access
  - Impact: Large FTL file parsing (up to 10MB) no longer causes reader starvation in multi-threaded environments
  - Implementation: Split `_add_resource_impl` into parse (unlocked) + `_register_resource` (locked) phases

- **Locale Validation Coherence** (SEM-LOCALE-LENGTH-INCOHERENCE): Aligned locale length validation between `FluentBundle` and `LocaleContext`:
  - Previous: FluentBundle accepted up to 1000 chars, but LocaleContext silently fell back to en_US at 35 chars
  - Now: LocaleContext warns at 35 chars but attempts Babel validation - valid extended locales are accepted
  - Impact: BCP 47 locales with extensions (e.g., "zh-Hans-CN-u-ca-chinese-nu-hansfin-x-myapp", 43 chars) now work correctly
  - Rationale: Two-tier validation supports valid extended locales while warning about potential misconfiguration

- **Cache Memory Tuning** (SEC-CACHE-WEIGHT-TUNING): Error weight reduced from 1000 to 200 bytes for realistic cache memory estimation:
  - Previous: `_ERROR_WEIGHT_BYTES = 1000` made `max_errors_per_entry=50` unreachable (weight limit rejected >10 errors)
  - Now: `_ERROR_WEIGHT_BYTES = 200` allows 50 errors × 200 bytes = 10,000 bytes (matches DEFAULT_MAX_ENTRY_SIZE)
  - Impact: Templates with many missing variables now cacheable up to configured error limit
  - Rationale: Parameter interaction aligned - error count limit is now the effective constraint, not weight calculation

- **Context Manager Cache Optimization** (SEM-BUNDLE-CONTEXT-CLEAR): Context manager cache clearing now conditional on modification:
  - Previous: `FluentBundle.__exit__` cleared cache unconditionally, even for read-only operations
  - Now: Cache cleared only if bundle was modified during context (add_resource, add_function, clear_cache called)
  - Impact: Shared bundle scenarios no longer experience cache invalidation from read-only context manager usage
  - Implementation: Added `_modified_in_context` flag tracking, preserves cache for pure read operations

- **Resource ID Validation** (SEM-L10N-RESOURCE-ID-WHITESPACE): Added whitespace validation for resource IDs and locale codes:
  - Previous: Resource ID " messages.ftl" (leading space) constructed path "/root/en/ messages.ftl", causing file-not-found errors
  - Now: `PathResourceLoader._validate_resource_id` rejects leading/trailing whitespace with explicit error message
  - Also: `FluentLocalization.add_resource` validates locale parameter for whitespace
  - Impact: Fail-fast detection of copy-paste errors from config files, YAML parsing, user input

- **Date Parsing Internationalization** (SEM-DATES-GHOST-SEPARATOR, SEM-DATES-ERA-ENGLISH-ONLY): Enhanced date parsing for non-English locales:
  - **Ghost Separator Fix**: Pattern "zzzz HH:mm" now produces "%H:%M" instead of " %H:%M" (leading space removed)
    - Implementation: Changed `.rstrip()` to `.strip()` + adjacent separator cleanup when tokens map to None
    - Impact: Timezone-first and era-first patterns now parse correctly
  - **Localized Era Support**: Era stripping now uses Babel's localized era names when available
    - Previous: Only English/Latin era strings ("AD", "BC", "CE", "BCE", "Anno Domini") were stripped
    - Now: Queries Babel `Locale.eras` property for locale-specific era names (e.g., French "ap. J.-C.", Arabic "م")
    - Impact: Non-English date strings with era designations now parse correctly
    - Fallback: Uses English/Latin eras if Babel unavailable or locale has no era data

## [0.66.0] - 2026-01-10

### Breaking Changes
- **Cache Weight Semantics** (SEM-CACHE-WEIGHT-001): `FormatCache` parameter renamed to accurately reflect memory weight calculation:
  - Previous: `max_entry_size` parameter documented as character limit
  - Now: `max_entry_weight` parameter correctly named for weight formula: `len(formatted_str) + (len(errors) * 1000)`
  - Rationale: Original name misleadingly suggested pure character count, but implementation used composite weight including error collection size
  - Migration: Replace `max_entry_size` with `max_entry_weight` in FormatCache constructor calls
  - Example before: `FormatCache(maxsize=1000, max_entry_size=10000)`
  - Example after: `FormatCache(maxsize=1000, max_entry_weight=10000)`
  - Impact: Test files updated to use new parameter name

- **Dependency Graph Namespace Prefixes** (SEM-GRAPH-COLLISION-001): `build_dependency_graph()` return type changed to prevent message/term ID collisions:
  - Previous: `term_deps` used unprefixed IDs, causing collisions when message "brand" and term "-brand" exist
  - Now: `term_deps` uses prefixed keys: `"msg:{id}"` for message->term refs, `"term:{id}"` for term->term refs
  - Rationale: FTL has separate namespaces for messages and terms, but both can have identifier "brand"
  - Example collision: Message "brand" and Term "-brand" both created `term_deps["brand"]`, second overwrites first
  - Migration: Update callers to use prefixed keys when accessing `term_deps` dictionary
  - Example before: `if "brand" in term_deps: ...`
  - Example after: `if "msg:brand" in term_deps: ... if "term:brand" in term_deps: ...`
  - Impact: Tests updated to check for prefixed keys in dependency graph results

### Fixed
- **Plural Category Precision Loss** (SEM-PLURAL-PRECISION-LOSS): NUMBER() formatting with precision now correctly affects plural category selection:
  - Previous: `NUMBER(1, minimumFractionDigits: 2)` formatted as "1.00" but selected "one" category (v=0)
  - Now: Precision parameter passed to plural rules, "1.00" with v=2 correctly selects "other" category
  - Root cause: FluentNumber preserved formatted string but discarded precision metadata before plural matching
  - Implementation: Added `precision` field to FluentNumber dataclass, modified select_plural_category to accept precision parameter
  - Impact: CLDR plural rules now see correct v operand (fraction digit count) for formatted numbers
  - Example: English plural rule `i=1 AND v=0` matches 1 but not 1.00 (v=2)
  - Babel Integration: Converts number to Decimal with specified precision via quantize() before passing to plural_form()

- **Introspection Variable Extraction** (SEM-INTROSPECTION-FUNC-ARGS): Function arguments wrapped in Placeable now correctly extracted:
  - Previous: `NUMBER({$amount}, minimumFractionDigits: 2)` did not extract "amount" variable
  - Now: Unwraps Placeable before checking for VariableReference, correctly extracts variable name
  - Root cause: IntrospectionVisitor checked `if VariableReference.guard(pos_arg)` without unwrapping Placeable
  - Implementation: Added Placeable unwrapping logic: `unwrapped_arg = pos_arg.expression if Placeable.guard(pos_arg) else pos_arg`
  - Impact: Variable extraction now complete for all FTL syntax patterns including Placeable-wrapped function arguments

### Performance
- **Parser String Concatenation** (QUADRATIC_STRING_CONCAT): Fixed O(N^2) string concatenation in comment merging and pattern continuation:
  - Previous: Repeated string concatenation for N consecutive comments: `"a" + "\n" + "b" + "\n" + "c"` = O(N^2)
  - Now: Accumulate fragments in list, join once: `["a", "\n", "b", "\n", "c"]` → `"\n".join(...)` = O(N)
  - Affected code:
    - Comment merging: `_CommentAccumulator` class replaces inline `_merge_comments()` function
    - Pattern continuation: `_TextAccumulator` class for parse_simple_pattern() and parse_pattern()
  - Implementation: List accumulation with single join operation when finalizing AST nodes
  - Impact: Large FTL files with 100+ consecutive comment lines or deep pattern continuations now parse significantly faster
  - Memory: Reduced temporary string allocations during parsing

## [0.65.0] - 2026-01-10

### Breaking Changes
- **Locale Validation Fail-Fast** (API-LOCALE-LEAK-001): FluentLocalization now validates all locale codes eagerly at construction:
  - Previous: Invalid locale codes raised ValueError during first format_value() call (lazy bundle creation)
  - Now: Invalid locale codes raise ValueError during FluentLocalization.__init__
  - Rationale: Fail-fast pattern prevents ValueError from leaking through format_value API, which documents returning error tuples, not raising exceptions
  - Impact: Users must ensure all locale codes in fallback chain have valid format before constructing FluentLocalization
  - Example failure: `FluentLocalization(["en", "invalid locale"])` now raises ValueError immediately
  - Valid format: `[a-zA-Z0-9]+([_-][a-zA-Z0-9]+)*` (BCP 47 subset)

### Fixed
- **Resolver Graceful Degradation** (SEC-RESOLVER-CRASH-001): Resolver no longer crashes on programmatically constructed ASTs with invalid NumberLiteral.raw values:
  - Previous: `Decimal(raw_str)` in _find_exact_variant raised InvalidOperation for malformed raw strings, crashing resolution
  - Now: Wrapped in try/except with fallthrough to next variant on InvalidOperation
  - Impact: Programmatic AST construction with invalid numeric literals now falls through to default variant instead of crashing
  - Example: `NumberLiteral(value=0.0, raw="invalid")` in SelectExpression variant key no longer causes crash

- **Fallback Generation Stack Safety** (SEC-FALLBACK-RECURSION-001): Added depth protection to _get_fallback_for_placeable:
  - Previous: Unbounded recursion in fallback string generation for deeply nested SelectExpressions
  - Now: Added depth parameter (default: MAX_DEPTH) with decrement on recursive calls
  - Impact: Adversarial ASTs with 100+ nested SelectExpressions in selector positions no longer cause RecursionError
  - Returns FALLBACK_INVALID when depth limit exceeded instead of crashing

- **Function Registry Signature Validation** (API-REGISTRY-SIG-MISMATCH-001): FunctionRegistry.register() now validates signature compatibility with inject_locale marker:
  - Previous: Functions marked with inject_locale=True could be registered even with incompatible signatures (< 2 positional params)
  - Now: Raises TypeError at registration time if function cannot accept locale as second positional argument
  - Impact: Fail-fast detection of signature mismatches instead of runtime TypeError during format calls
  - Example: `@fluent_function(inject_locale=True) def bad(value): ...` now fails registration with clear error

- **Serializer Identifier Validation** (SER-INVALID-OUTPUT-001): Serializer with validate=True now rejects ASTs with invalid identifier names:
  - Previous: Serializer blindly output identifier strings without grammar validation, producing invalid FTL syntax
  - Now: Validates all identifiers against FTL grammar `[a-zA-Z][a-zA-Z0-9_-]*` when validate=True
  - Impact: Programmatically constructed ASTs with spaces in identifiers rejected with SerializationValidationError
  - Example: `Identifier(name="my var")` now raises SerializationValidationError with clear message

- **Locale Validation Regex Precision** (VAL-LOCALE-REGEX-001): Locale validation regex now correctly rejects trailing newlines:
  - Previous: `$` anchor matched before trailing `\n`, allowing invalid locales like `'0\n'` to pass validation
  - Now: Uses `\Z` anchor which matches only at actual end of string
  - Impact: Property-based tests now correctly catch edge cases with trailing whitespace
  - Discovered by Hypothesis test: `test_invalid_locale_formats_rejected`

- **Validator Numeric Precision** (SEM-VALIDATOR-PRECISION-001): SemanticValidator now uses NumberLiteral.raw for variant key comparison:
  - Previous: Used `Decimal(str(key.value))` where key.value is float, causing precision loss and false duplicate detection
  - Now: Uses `Decimal(key.raw)` to preserve original source precision
  - Impact: High-precision numeric variant keys (e.g., `[0.10000000000000001]` vs `[0.1]`) no longer falsely rejected as duplicates
  - Matches resolver behavior which also uses raw strings for numeric comparison

## [0.64.0] - 2026-01-09

### Breaking Changes
- **Dependency Graph API Namespace Separation** (DEBT-GRAPH-COLLISION-001): `build_dependency_graph()` signature changed to correctly handle FTL's separate message and term namespaces:
  - Previous: `build_dependency_graph(entries: Mapping[str, tuple[set[str], set[str]]]) -> tuple[dict[str, set[str]], dict[str, set[str]]]`
  - Now: `build_dependency_graph(message_entries: Mapping[str, tuple[set[str], set[str]]], term_entries: Mapping[str, tuple[set[str], set[str]]] | None = None) -> tuple[dict[str, set[str]], dict[str, set[str]]]`
  - Rationale: Previous API used single dict with string keys, causing key collisions when a resource has both a message and term with the same identifier (e.g., "brand" message and "-brand" term)
  - Migration: Split your entries dict into separate `message_entries` and `term_entries` dicts based on entry type
  - Example before: `build_dependency_graph({"foo": (msg_refs, term_refs), "bar": ...})`
  - Example after: `build_dependency_graph(message_entries={"foo": (msg_refs, term_refs)}, term_entries={"bar": (msg_refs, term_refs)})`

### Fixed
- **Serializer Roundtrip Fidelity** (SEM-JUNK-WHITESPACE-001): Fixed redundant newline insertion before Junk entries:
  - Previous: Serializer added separator newline before all entries, including Junk, causing file growth on parse/serialize cycles
  - Now: Serializer skips separator when Junk content already contains leading whitespace
  - Impact: Prevents whitespace inflation on roundtrip when invalid FTL content has leading blank lines
  - Example: Input "msg = hello\n\n  bad" now maintains 2 newlines instead of growing to 3+ on each roundtrip

### Changed
- **Plural Matching Error Visibility** (SEM-BABEL-SILENT-001): Plural variant matching now collects diagnostic error when Babel is unavailable:
  - Previous: Silent degradation to default variant when Babel not installed, making debugging difficult
  - Now: Appends `FluentResolutionError` with code `PLURAL_SUPPORT_UNAVAILABLE` to errors tuple
  - Error message: "Plural variant matching unavailable (Babel not installed). Install with: pip install ftllexengine[babel]"
  - Behavior: Still falls back to default variant (graceful degradation preserved), but now visible in errors collection
  - Impact: Developers can now see when pluralization is being silently ignored due to missing dependency

## [0.63.0] - 2026-01-09

### Fixed
- **Depth Safety Consistency** (SEC-RECURSION-001, ARCH-VISITOR-BYPASS-001): Unified depth clamping across all subsystems:
  - FluentResolver now clamps max_nesting_depth against Python recursion limit to prevent RecursionError on constrained systems
  - GlobalDepthGuard now clamps max_depth to safe values based on sys.getrecursionlimit()
  - FluentBundle now clamps max_nesting_depth before passing to parser and resolver
  - DepthGuard dataclass automatically clamps max_depth in __post_init__
  - IntrospectionVisitor now uses proper visitor dispatch for variant patterns, ensuring consistent depth tracking
  - Created depth_clamp() utility function in core.depth_guard for reusable depth validation
  - Prevents RecursionError crashes on embedded or highly threaded systems with low stack limits

### Documentation
- **FluentLocalization Initialization Semantics** (DOCS-LOAD-SILENT-001): Corrected module docstring to accurately describe fail-silent-with-diagnostics behavior:
  - Previous: Docstring claimed "FileNotFoundError and parse errors are raised immediately"
  - Now: Documented that errors are captured in ResourceLoadResult objects with LoadStatus codes (NOT_FOUND, ERROR)
  - Added example showing how to check get_load_summary() for load failures after construction
  - Non-breaking: clarifies existing behavior without changing API

### Internal
- **Code Consolidation** (DEBT-ATTR-PARSE-001, DEBT-VAL-DUP-001): Eliminated duplicate logic across modules:
  - parse_term now uses parse_message_attributes helper instead of inline attribute parsing loop
  - Extracted select expression validation to shared count_default_variants() helper in syntax.validation_helpers
  - Both serializer and validator now use shared helper for default variant counting
  - Reduces maintenance burden and prevents behavioral drift between modules

## [0.62.0] - 2026-01-08

### Fixed
- **Parser Junk Consolidation** (IMP-PARSER-JUNK-FRAGMENT-001): Parser now correctly consolidates indented junk content:
  - Previous: Junk recovery stopped prematurely at indented lines starting with `#`, `-`, or letters, creating fragmented Junk entries
  - Root cause: `_consume_junk_lines` checked for entry-start characters after skipping spaces, without verifying the character was at column 1
  - Now: Only stops junk consumption when entry-start characters appear at column 1 (no indentation)
  - Impact: Reduces memory overhead (fewer Junk objects) and cleaner error reporting (one consolidated error instead of multiple fragments)
  - Example: Invalid block with indented comments now creates single Junk entry instead of multiple fragments
  - Per Fluent EBNF: Valid entries must start at column 1; indented lines are not valid entry starts

### Documentation
- **Attribute Resolution Semantics** (SEM-RESOLVER-ATTR-ORDER-001): Enhanced documentation of last-wins attribute resolution:
  - Added to `FluentResolver.resolve_message` docstring: Documents that duplicate attributes use last-wins semantics
  - Added to `FluentBundle.format_pattern` docstring: Clarifies last definition is used for duplicate attribute names
  - Added to `FluentBundle.has_attribute` docstring: Notes that existence check doesn't indicate which duplicate will resolve
  - Matches Fluent specification and Mozilla reference implementation behavior
  - Duplicate attributes already trigger validation warnings; this change only clarifies resolution behavior

- **FluentParseError Parameter Semantics** (API-PARSEERROR-ATTRS-001): Clarified empty string meaning for keyword-only parameters:
  - Enhanced class-level docstring to explain attribute semantics with empty string defaults
  - Enhanced `__init__` docstring to document when empty strings are used:
    - `input_value=""`: Empty string if not provided or input was genuinely empty
    - `locale_code=""`: Empty string if locale-agnostic or locale context unavailable
    - `parse_type=""`: Empty string if type cannot be determined (e.g., internal errors before type identification)
  - Non-breaking change: maintains existing API contract while improving clarity
  - Enables users to distinguish "not provided" from intentional empty values in diagnostic code

## [0.61.0] - 2026-01-08

### Added
- **Top-level API Export** (API-VALIDATION-EXPORT-001): `validate_resource` now exported at top level for consistency:
  - Previous: Required `from ftllexengine.validation import validate_resource`
  - Now: Available as `from ftllexengine import validate_resource`
  - Consistent with `parse_ftl` and `serialize_ftl` top-level exports
  - Parser-only workflows can now access all core functions from top-level import
  - No Babel dependency required (validation uses AST inspection only)

### Changed
- **Term Positional Arguments Warning** (ARCH-TERM-POSITIONAL-DISCARD-001): Term references with positional arguments now emit explicit warnings:
  - Previous: Positional arguments in term references (e.g., `-brand($val)`) were silently evaluated and discarded
  - Now: Emits `FluentResolutionError` with diagnostic code `TERM_POSITIONAL_ARGS_IGNORED`
  - Warning message: "Term '-{name}' does not accept positional arguments (got {count}). Use named arguments: -term(key: value)"
  - Per Fluent spec, terms only accept named arguments; positional args have no binding semantics
  - Helps users understand why positional arguments are ignored and how to fix their FTL
  - Expression errors in positional arguments are still caught during evaluation

- **Parser Parameter Validation** (TYPE-PARSER-DEPTH-001): FluentParserV1 now validates constructor parameters:
  - Previous: `max_nesting_depth=0` accepted but caused immediate failures on any nesting
  - Now: Raises `ValueError` if `max_nesting_depth` is specified and `<= 0`
  - Error message: "max_nesting_depth must be positive (got {value})"
  - Docstring updated to clarify valid parameter ranges
  - `max_nesting_depth=None` still uses default (100 or clamped to recursion limit)
  - Prevents user errors from invalid parameter values

### Documentation
- **Docstring Accuracy** (DOCS-CACHE-USAGE-001): Fixed `cache_usage` property docstring example:
  - Previous: Example showed `format_pattern` returning `('Hello', [])` with list for errors
  - Now: Example shows `('Hello', ())` with tuple for errors (matches actual return type)
  - Docstrings must not contradict type hints

- **Docstring Completeness** (DOCS-DATETIME-SEP-001): Enhanced `_extract_datetime_separator` docstring Returns section:
  - Previous: "Falls back to space if extraction fails"
  - Now: "The separator string between date and time components, extracted from the locale's dateTimeFormat for the specified style. Falls back to space (' ') if the style is unavailable or extraction fails."
  - Clarifies that the `style` parameter affects which format is attempted first
  - Documents full fallback behavior explicitly

## [0.60.0] - 2026-01-08

### Breaking Changes
- **Duplicate Attribute Resolution** (SEM-ATTR-DUPLICATE-RESOLVER-001): Duplicate attributes now use last-wins semantics per Fluent specification:
  - Previous: First attribute with matching name was resolved
  - Now: Last attribute with matching name is resolved (matches JavaScript object semantics and Mozilla reference implementation)
  - Impact: FTL files with duplicate attributes (which trigger validation warnings) will resolve to different values
  - Example: Message with `.label = First` and `.label = Second` now resolves to "Second" (was "First")
  - Specification: https://projectfluent.org/fluent/guide/selectors.html

### Fixed
- **Variant Key Whitespace** (SPEC-VARIANT-WHITESPACE-001): Parser now accepts newlines inside variant key brackets per Fluent specification:
  - Previous: Variant keys with newlines before/after the identifier were rejected (e.g., `[ \n one \n ]`)
  - Root cause: Used `skip_blank_inline` (spaces only) instead of `skip_blank` (spaces and newlines)
  - Now: Accepts multiline variant keys as per Fluent EBNF: `VariantKey ::= "[" blank? (NumberLiteral | Identifier) blank? "]"`
  - Example: Valid FTL now parses correctly:
    ```ftl
    items = { $count ->
        [
          one
        ] One item
       *[other] Many items
    }
    ```

- **Standalone Comment Roundtrip**: Serializer now preserves standalone comment semantics during roundtrip:
  - Previous: Standalone Comments (separate entries, not attached to messages) were serialized with only 1 blank line before the following entry
  - Previous: On re-parse, these comments became attached to the following message/term (lost standalone status)
  - Root cause: Serializer only added extra blank lines between same-type Comments, not between Comment and Message/Term
  - Now: Standalone Comments are followed by 2 blank lines to prevent attachment during re-parse
  - Attached comments (set via `message.comment`) remain attached with single blank line
  - Per Fluent spec: 0-1 blank lines = attached comment, 2+ blank lines = standalone comment

## [0.59.0] - 2026-01-08

### Security
- **RWLock Deadlock Prevention** (CONC-RWLOCK-DEADLOCK-001, CRITICAL): Fixed deadlock vulnerability in RWLock implementation:
  - Previous: Write lock reentrancy caused guaranteed deadlock (thread waiting for itself)
  - Previous: Read-to-write lock upgrade caused guaranteed deadlock (thread waiting to release own read lock)
  - Now: Write locks are reentrant - same thread can acquire write lock multiple times
  - Now: Read-to-write upgrades raise `RuntimeError` with clear guidance to prevent deadlock
  - Updated module docstring and class docstring to document upgrade limitation
  - Added `_writer_reentry_count` field to track reentrant write acquisitions
  - Test coverage: `test_rwlock_implementation.py` with write reentrancy and upgrade rejection tests

- **Depth Limit Propagation** (ARCH-DEPTH-BYPASS-001): FluentResolver now receives bundle's configured `max_nesting_depth`:
  - Previous: Custom depth limits on FluentBundle were ignored; resolver always used default MAX_DEPTH (100)
  - Now: Bundle's `max_nesting_depth` propagates to FluentResolver → ResolutionContext → GlobalDepthGuard
  - Prevents DoS via deep nesting even when bundle configured for lower limits
  - Example: `FluentBundle("en", max_nesting_depth=20)` now enforces 20-level limit in resolver

- **Serializer Validation Depth Guards** (ARCH-VALIDATION-RECURSION-001): Added recursion protection to serializer validation:
  - Previous: Validation phase (`_validate_pattern`, `_validate_expression`) lacked depth tracking
  - Previous: Deeply nested ASTs (1000+ levels) caused `RecursionError` during serialize with `validate=True`
  - Now: Validation functions accept and use `depth_guard` parameter
  - Now: Raises `SerializationDepthError` when depth limit exceeded (consistent with serialization phase)
  - `_validate_resource` creates `DepthGuard` and passes to all validation functions
  - `serialize()` function's `max_depth` parameter now controls both validation and serialization

- **Validator Call Argument Depth Tracking** (ARCH-VALIDATOR-DEPTH-001): Fixed missing depth tracking in call argument validation:
  - Previous: `_validate_call_arguments` passed `depth_guard` but didn't increment depth for each argument
  - Previous: Functions with 100 arguments, each containing nested placeables, didn't track cumulative depth
  - Now: Positional and named argument loops wrapped in `with depth_guard:` blocks
  - Consistent with `_validate_pattern_element` depth tracking pattern

- **Locale Code Length Validation** (SEC-LOCALE-UNBOUNDED-001): Enforced DoS protection for locale code length:
  - Previous: No length limit on locale codes; attacker could provide 10MB locale string
  - Previous: Long locale codes passed character validation but consumed unbounded memory in caches
  - Now: FluentBundle rejects locale codes exceeding 1000 characters (DoS prevention)
  - Now: `MAX_LOCALE_CODE_LENGTH = 35` constant defines standard BCP 47 length
  - LocaleContext.create: Logs warning and falls back to `en_US` for codes exceeding 35 characters
  - Allows extended BCP 47 private-use subtags (up to 1000 chars) while preventing memory exhaustion
  - Real-world locale codes: 2-16 characters (e.g., "en", "en-US", "zh-Hans-CN")

- **Cache Error Collection Bounding** (SEC-CACHE-ERROR-BLOAT-001): FormatCache now bounds memory from error collections:
  - Previous: Only checked formatted string size; error tuple could contain 100+ FluentError objects
  - Previous: Large error collections (each with Diagnostic traceback) consumed unbounded memory
  - Now: Added `max_errors_per_entry` parameter (default: 50)
  - Now: Calculates `total_weight = len(string) + (len(errors) * 1000 bytes/error)`
  - Now: Skips caching when error count OR total weight exceeds limits
  - Added `error_bloat_skips` counter in cache stats
  - Example: 10 errors (~10KB) + 100-char string = rejected if `max_entry_size=5000`

### Fixed
- **Serializer Comment Roundtrip** (SER-COMMENT-MERGE-001): Fixed consecutive comments merging during parse-serialize-parse roundtrip:
  - Previous: Two separate comments of the same type (e.g., `### 0` and `### 0`) serialized with single newline separator, causing parser to merge them on re-parse
  - Root cause: `_has_blank_line_between()` requires two consecutive newlines to detect blank line, but comment's own trailing newline was already consumed during parsing
  - Now: Serializer inserts extra blank line (`\n\n`) between consecutive comments of the same type
  - Applies to all comment types: resource (`###`), group (`##`), and single (`#`)
  - Preserves AST structure through unlimited roundtrips

### Changed
- **Fuzzing Test Entropy Budget** (TEST-FUZZ-ENTROPY-001): Increased entropy allowance for `test_composability`:
  - Test requires two full `ftl_resource()` strategies for thorough composability verification
  - Removed default entropy cap via `HealthCheck.data_too_large` suppression
  - Maintains full-complexity resource generation for comprehensive property testing

## [0.58.0] - 2026-01-07

### Security
- **PARSE-DEPTH-VAL-001** (LOW): Parser now validates `max_nesting_depth` against Python's recursion limit:
  - Previous: User could specify `max_nesting_depth` exceeding `sys.getrecursionlimit()`, causing `RecursionError`
  - Now: Parser clamps depth to `sys.getrecursionlimit() - 50` (reserves stack frames for parser overhead)
  - Logs warning when user-specified depth is clamped
  - Prevents DoS via misconfigured parser depth settings

### Added
- **RWLock Implementation** (PERF-BUNDLE-LOCK-CONTENTION-001): New readers-writer lock for high-concurrency FluentBundle access:
  - New module: `runtime/rwlock.py` with `RWLock` class
  - Multiple concurrent readers (format operations) execute without blocking each other
  - Writers (add_resource, add_function) acquire exclusive access
  - Writer preference prevents reader starvation in read-heavy workloads
  - Reentrant read locks allow nested read operations from same thread
  - Comprehensive test suite: `test_rwlock_implementation.py` and `test_bundle_rwlock_integration.py`

- **LoadSummary.all_clean Property** (L10N-SUM-JUNK-001): New property for strict resource validation:
  - `all_successful`: Returns True if no I/O errors (ignores Junk entries) - for load success checks
  - `all_clean`: Returns True if no errors AND no Junk entries - for validation workflows
  - Clarifies semantic distinction between "loaded successfully" and "perfectly valid"
  - Example: Resource with parse errors is "successful" but not "clean"

- **AST Span Fields** (FTL-AST-SPAN-001): All AST nodes now have `span` field for source position tracking:
  - Added `span: Span | None = None` to: `Identifier`, `Attribute`, `Variant`, `StringLiteral`, `NumberLiteral`, `CallArguments`, `NamedArgument`
  - Enables LSP/IDE features: go-to-definition, error highlighting, precise diagnostics
  - Parser does not yet populate spans (future enhancement), but fields are available for tooling

### Changed
- **FluentBundle Thread Safety** (PERF-BUNDLE-LOCK-CONTENTION-001): Replaced coarse-grained RLock with readers-writer lock:
  - Previous: All operations (read and write) acquired exclusive RLock, serializing concurrent format calls
  - Now: Read operations (format_pattern, has_message, introspect_message, etc.) execute concurrently
  - Write operations (add_resource, add_function, clear_cache) remain exclusive
  - Significant throughput improvement for multi-threaded applications (100+ concurrent format requests)

- **FluentLocalization Locale Deduplication** (L10N-DUPLICATE-LOCALE-001): Constructor now deduplicates locale codes:
  - Previous: `FluentLocalization(['en', 'de', 'en'])` stored duplicates
  - Now: Duplicates removed while preserving order: `('en', 'de')`
  - Uses `dict.fromkeys()` for efficient O(n) deduplication
  - First occurrence of each locale code is preserved

- **Number Formatting Rounding** (RES-NUM-ROUNDING-001): Switched from banker's rounding to CLDR half-up rounding:
  - Previous: Used Python's `round()` function (banker's rounding: 2.5→2, 3.5→4)
  - Now: Uses `Decimal.quantize(ROUND_HALF_UP)` for CLDR-compliant rounding (2.5→3, 3.5→4, 4.5→5)
  - Matches JavaScript `Intl.NumberFormat` and CLDR specification
  - Critical for financial applications expecting deterministic rounding
  - Affects `LocaleContext.format_number()` when `maximum_fraction_digits=0`

### Performance
- **CRLF Normalization Optimization** (PERF-PARSER-MEM-RED-001): Parser line ending normalization reduced to single pass:
  - Previous: `source.replace("\r\n", "\n").replace("\r", "\n")` created intermediate string copy
  - Now: `re.sub(r"\r\n?", "\n", source)` performs single-pass normalization
  - Reduces memory allocation for large FTL files with mixed line endings
  - No functional change, pure optimization

- **Dependency Graph Optimization** (PERF-VAL-GRAPH-REDUNDANT-001): Validation builds dependency graph once:
  - Previous: `_detect_circular_references()` and `_detect_long_chains()` each built separate graphs
  - Now: `validate_resource()` builds unified graph once, passes to both functions
  - `_build_dependency_graph()` signature extended with `known_messages` and `known_terms` parameters
  - Reduces AST traversal overhead for resources with 100+ messages
  - `_detect_circular_references()` and `_detect_long_chains()` now accept pre-built graph

### Documentation
- **FluentLocalization Initialization Behavior** (L10N-LAZY-001): Clarified eager vs. hybrid bundle creation:
  - Module docstring: Bundles created eagerly for locales loaded during init, lazily for fallback locales
  - Constructor docstring: Resources loaded eagerly (fail-fast), bundles created on-demand
  - Inline comments: Explains hybrid approach balances fail-fast with memory efficiency

- **get_load_summary() Scope** (L10N-SUM-001): Documented that summary only reflects initialization-time loading:
  - Docstring clarifies: Only resources loaded via ResourceLoader during `__init__()` are tracked
  - Resources added via `add_resource()` are NOT included in summary
  - Maintains semantic distinction between init-time (fail-fast) and runtime (dynamic) loading

- **Introspection Cache Race Condition** (INTRO-CACHE-001): Documented accepted race condition in module-level cache:
  - `_introspection_cache` (WeakKeyDictionary) is NOT thread-safe for concurrent writes
  - Pathological case: Concurrent introspection of same Message/Term from multiple threads
  - Accepted trade-off: Worst case is redundant computation (cache miss), never corruption
  - Rationale: Read-mostly workload, RLock overhead outweighs rare redundant computation
  - Alternative (thread-local cache) would reduce hit rate and increase memory
  - Permanent architectural decision prioritizing common-case performance over pathological concurrency scenarios

- **Parser Thread-Local Storage** (FTL-PAR-THREADLOCAL-001): Documented architectural decision for primitive error context:
  - `syntax/parser/primitives.py` uses thread-local storage for parse error context
  - Design choice: Implicit state via thread-local over explicit parameter threading
  - Rationale: Primitives called 100+ times per parse; explicit context would require ~10 signature changes and 200+ call site updates
  - Trade-off: Performance benefit of reduced overhead outweighs cost of implicit state for high-frequency operations
  - Thread safety: Async frameworks must call `clear_parse_error()` before each parse to prevent context leakage
  - Permanent architectural pattern balancing performance with explicitness

## [0.57.0] - 2026-01-07

### Security
- **SEC-BABEL-INCONSISTENT-001** (LOW): Babel import consistency enforced across all modules:
  - Previous: `locale_utils.py` had independent lazy Babel import with custom error handling
  - Now: All Babel imports route through `babel_compat.py` for consistent error messages
  - Eliminates duplicate import logic and ensures single source of truth for Babel availability

### Added
- **Duplicate Attribute Detection** (VAL-DUPLICATE-ATTR-001): Validation now detects duplicate attribute IDs within messages and terms:
  - New diagnostic code: `VALIDATION_DUPLICATE_ATTRIBUTE` (5107)
  - Warns when message or term has multiple attributes with same ID
  - Example: `message = Value\n    .tooltip = First\n    .tooltip = Second` triggers warning
  - Helps catch copy-paste errors and ambiguous attribute definitions

- **Shadow Conflict Detection** (FTL-VAL-CONFLICT-001): Validation warns when new resource shadows existing entries:
  - New diagnostic code: `VALIDATION_SHADOW_WARNING` (5108)
  - Emitted when message/term ID in current resource matches known bundle entry
  - Clarifies intentional override pattern vs. accidental redefinition
  - Improves multi-resource validation workflow

- **Cross-Resource Cycle Detection** (FTL-VAL-XRES-001): Circular reference detection now spans resources:
  - Previous: Cycles only detected within single resource
  - Now: Graph includes edges to known bundle entries enabling cross-resource cycle detection
  - Validates that new resource won't create cycles with existing bundle contents
  - `_detect_circular_references()` accepts `known_messages` and `known_terms` parameters

### Changed
- **Validation Pass 2 Extended**: `_collect_entries()` now performs additional checks:
  - Duplicate attribute detection within each entry
  - Shadow warnings for entries conflicting with known bundle entries
  - Accepts `known_messages` and `known_terms` optional parameters

- **Validation Pass 4 Extended**: `_detect_circular_references()` cross-resource cycle detection:
  - Builds dependency graph including edges to known entries
  - Detects cycles that span multiple resources
  - Accepts `known_messages` and `known_terms` optional parameters

## [0.56.0] - 2026-01-06

### Security
- **SEC-RESOLVER-RECURSION-BYPASS-001** (HIGH): SelectExpression selector resolution now wrapped in `expression_guard`:
  - Previous: Selector expressions bypassed depth tracking, enabling stack overflow via deeply nested selectors
  - Now: `_resolve_select_expression()` wraps selector resolution in `with context.expression_guard:`
  - Prevents DoS via malformed ASTs with recursive selector nesting

- **SEC-SERIALIZER-RECURSION-BYPASS-001** (HIGH): Serializer now tracks depth for SelectExpression selectors:
  - Previous: `_serialize_select_expression()` called `_serialize_expression(expr.selector)` without depth guard
  - Now: Selector serialization wrapped in `with depth_guard:`
  - Prevents stack overflow from deeply nested selector expressions in serialization

- **RES-DEPTH-LEAK-001** (MEDIUM): Global depth tracking via `contextvars` prevents callback bypass:
  - Previous: Custom functions could call `bundle.format_pattern()` creating fresh `ResolutionContext`, bypassing depth limits
  - Now: `GlobalDepthGuard` tracks depth across all resolution calls per-task/thread using `contextvars`
  - Custom functions attempting recursive resolution are now properly limited

- **RES-BABEL-CRASH-001** (MEDIUM): BabelImportError gracefully handled in plural matching:
  - Previous: `select_plural_category()` could raise `BabelImportError` causing format_pattern to crash
  - Now: `_resolve_select_expression()` catches `BabelImportError` and falls through to default variant
  - Parser-only installations now handle select expressions with numeric selectors gracefully

- **SEC-PARSER-UNBOUNDED-001** (MEDIUM): Parser primitives now enforce token length limits:
  - Previous: `parse_identifier()`, `parse_number()`, `parse_string_literal()` had unbounded loops
  - Now: Maximum lengths enforced (identifiers: 256 chars, numbers: 1000 chars, strings: 1M chars)
  - Prevents DoS via extremely long tokens that could exhaust memory or CPU

### Added
- **GlobalDepthGuard Class**: New context manager in `runtime/resolver.py`:
  - Uses `contextvars.ContextVar` for async-safe per-task depth tracking
  - Prevents depth limit bypass via custom function callbacks
  - Documents security threat model in docstring

- **Parser Token Length Constants**: New limits in `constants.py`:
  - `_MAX_IDENTIFIER_LENGTH`: 256 characters
  - `_MAX_NUMBER_LENGTH`: 1000 characters
  - `_MAX_STRING_LITERAL_LENGTH`: 1,000,000 characters
  - Generous limits for legitimate use while preventing abuse
  - Centralized in constants.py for auditability (used by `syntax/parser/primitives.py`)

### Changed
- **ResolutionContext Usage**: `resolve_message()` now wraps resolution in `GlobalDepthGuard`:
  - Catches `FluentResolutionError` from global depth exceeded
  - Returns fallback with collected error on depth limit
  - Maintains backwards compatibility for normal usage

## [0.55.0] - 2026-01-05

### Breaking Changes
- **Locale Code Validation Now ASCII-Only**: `FluentBundle` now rejects locale codes containing non-ASCII characters:
  - Previous: Unicode characters like `e_FR` (with accented e) passed validation
  - Now: Raises `ValueError` with message "(must be ASCII alphanumeric)"
  - Enforces BCP 47 compliance for locale identifiers
  - Prevents confusing Babel lookup failures from invalid locale propagation

### Added
- **Reference Chain Depth Validation**: `validate_resource()` now detects reference chains exceeding MAX_DEPTH:
  - New diagnostic code: `VALIDATION_CHAIN_DEPTH_EXCEEDED` (5106)
  - Warns when message/term chains would cause runtime `MAX_DEPTH_EXCEEDED`
  - Example: `msg-150 -> msg-149 -> ... -> msg-0` (150 refs) triggers warning
  - Prevents deploying FTL files that pass validation but fail at runtime
- **Cache Entry Size Limit**: `FormatCache` now supports `max_entry_size` parameter:
  - Default: 10,000 characters (prevents caching very large results)
  - New property: `oversize_skips` tracks entries skipped due to size
  - New stat: `get_stats()` includes `max_entry_size` and `oversize_skips`
  - Protects against memory exhaustion from caching large formatted strings
- **Message/Term Overwrite Warning**: `FluentBundle.add_resource()` now logs overwrite events:
  - `logger.warning("Overwriting existing message 'X' with new definition")`
  - `logger.warning("Overwriting existing term '-X' with new definition")`
  - Improves observability for cross-file duplicate detection
  - Last Write Wins semantics preserved (warning only, no behavior change)

### Changed
- **Validation Architecture Extended**: `validate_resource()` now includes 6 passes:
  - Pass 1: Syntax errors (Junk entries)
  - Pass 2: Structural (duplicates, empty messages)
  - Pass 3: Undefined references
  - Pass 4: Circular dependencies
  - Pass 5: **NEW** Chain depth analysis
  - Pass 6: Fluent spec compliance (E0001-E0013)
- **Dependency Graph Utilities Refactored**: Validation internals reorganized:
  - `_build_dependency_graph()`: Shared graph construction
  - `_compute_longest_paths()`: Memoized iterative DFS for path analysis
  - `_detect_long_chains()`: Uses shared utilities for chain depth check

## [0.54.0] - 2026-01-05

### Breaking Changes
- **Date Parsing BabelImportError**: `parse_date()` and `parse_datetime()` now raise `BabelImportError` when Babel is not installed:
  - Previous: Functions silently returned empty patterns, causing misleading "No matching date pattern found" errors
  - Now: Clear `BabelImportError` with installation instructions on first call
  - Users without Babel will see explicit guidance instead of confusing parse failures
  - Aligns date parsing with number and currency parsing behavior

### Changed
- **Parsing Module Exception Contract Clarified**: Updated docstrings across all parsing functions:
  - `parsing/__init__.py`: Now documents two error paths (parse errors in tuple, BabelImportError raised)
  - `parse_number()`, `parse_decimal()`: Module docstring updated to match existing `Raises:` section
  - `parse_currency()`: Removed misleading "No longer raises exceptions" claim, added `Raises:` section
  - `parse_date()`, `parse_datetime()`: Removed misleading "No longer raises exceptions" claim, added `Raises:` section
  - `_get_date_patterns()`, `_get_datetime_patterns()`: Updated docstrings to document BabelImportError
- **Currency Parsing Simplified**: Replaced defensive RuntimeError with type narrowing assertion:
  - Previous: Raised RuntimeError for "impossible" internal state (currency_code is None after successful resolution)
  - Now: Uses `assert` for type narrowing (code contract guarantees exactly one of code/error is None)
  - Reduces noise and aligns with type system guarantees

### Fixed
- **Documentation Contract Violation**: Parsing module docstrings previously claimed "Functions NEVER raise exceptions" while implementations raised `BabelImportError`. Documentation now accurately reflects actual behavior.

## [0.53.0] - 2026-01-04

### Added
- **Centralized Babel Compatibility Layer**: New `ftllexengine.core.babel_compat` module:
  - `is_babel_available()`: Check if Babel is installed (cached result)
  - `require_babel(feature)`: Assert Babel available, raise `BabelImportError` if not
  - `BabelImportError`: Custom exception with helpful installation instructions
  - `get_babel_locale()`, `get_locale_class()`, `get_unknown_locale_error()`: Lazy accessors
  - `get_babel_numbers()`, `get_babel_dates()`: Module-level lazy imports
  - All Babel-dependent modules now use consistent lazy import pattern
- **SelectExpression Span Tracking**: `SelectExpression` AST node now includes `span` field:
  - Tracks source location (start/end position) for tooling support
  - Enables better error messages and IDE integration

### Changed
- **Babel Import Pattern Unified**: All Babel-dependent modules refactored:
  - `runtime/plural_rules.py`: Uses lazy import inside `select_plural_category()`
  - `runtime/locale_context.py`: Lazy imports in `create()`, `format_*()` methods
  - `parsing/currency.py`: Lazy imports in `_build_currency_maps_from_cldr()`
  - `parsing/numbers.py`: Lazy imports in `parse_number()`, `parse_decimal()`
  - `parsing/dates.py`: Lazy imports in `_get_date_patterns()`, `_get_datetime_patterns()`
  - Consistent error messaging via `BabelImportError` when Babel missing
- **Cursor Line Ending Simplification**: Cursor now expects LF-normalized input:
  - `skip_line_end()`: Only recognizes `\n` as line ending
  - `skip_to_line_end()`: Only scans for `\n` character
  - Module docstring documents LF-normalization requirement
  - `FluentParserV1.parse()` continues to normalize CRLF/CR to LF before parsing
  - Direct Cursor usage requires pre-normalization: `source.replace("\r\n", "\n").replace("\r", "\n")`

### Removed
- **Dead CR Handling in Cursor**: Removed unreachable carriage return code:
  - Previous `skip_line_end()` had CR/CRLF handling that never executed
  - Parser normalizes line endings at entry point, making CR checks redundant
  - Reduces code complexity and clarifies actual behavior

## [0.52.0] - 2026-01-04

### Security
- **Parser Depth Guard for Function Calls**: Nested function calls now count toward nesting depth limit:
  - Previous: `{ NUMBER(A(B(C(...)))) }` bypassed depth limit (only placeables counted)
  - Now: Each function call increments depth, preventing stack overflow via deeply nested calls
  - Term references with arguments (`-term(arg)`) also tracked
  - `ParseContext.enter_nesting()` replaces `enter_placeable()` for unified depth tracking
- **Resolver Depth Guard for Function Arguments**: Function argument resolution now wrapped in expression guard:
  - Previous: `_resolve_function_call` evaluated arguments without depth protection
  - Now: Argument resolution uses `context.expression_guard` to prevent stack overflow
  - Closes DoS vector independent of parser fix (adversarial AST construction)

### Changed
- **Babel Import Made Lazy**: `locale_utils.py` now imports Babel on-demand:
  - `normalize_locale()` and `get_system_locale()` work without Babel (stdlib only)
  - `get_babel_locale()` imports Babel at call time with clear error message
  - Enables direct import of locale_utils without triggering ImportError

### Fixed
- **Dead Code Removed**: Carriage return (`\r`) checks removed from parser:
  - Line endings are normalized to LF at parser entry (`FluentParserV1.parse()`)
  - Removed unreachable `\r` checks in `core.py`, `whitespace.py`, `primitives.py`
  - Reduces cognitive load by accurately reflecting normalized state

## [0.51.0] - 2026-01-03

### Security
- **Expression Depth Guard Bypass Fixed**: Placeable dispatch in resolver now applies expression depth guard:
  - Previous: Pattern -> Placeable -> SelectExpression -> Variant recursion bypassed depth limiting
  - Now: `expression_guard` applied at Pattern->Placeable entry point, catching all nested expressions
  - Prevents stack overflow from deeply nested SelectExpression chains

### Breaking Changes
- **Babel Now Optional**: Core syntax parsing works without Babel:
  - `pip install ftllexengine` installs parser-only (no external dependencies)
  - `pip install ftllexengine[babel]` or `ftllexengine[full]` includes Babel
  - `FluentBundle`, `FluentLocalization`, parsing modules require Babel
  - Clear error messages when importing Babel-dependent components without Babel installed

### Added
- **Fallback Observability**: `FluentLocalization` now supports fallback tracking:
  - `on_fallback` callback parameter invoked when message resolved from non-primary locale
  - `FallbackInfo` dataclass provides `requested_locale`, `resolved_locale`, and `message_id`
  - Enables monitoring which translations are missing
- **Introspection Caching**: `introspect_message()` now uses WeakKeyDictionary cache:
  - Repeated introspection of same Message/Term returns cached result
  - `use_cache=False` parameter to disable caching (benchmarking, testing)
  - `clear_introspection_cache()` function for manual cache management
  - Automatic cleanup when Message/Term objects are garbage collected
- **Diagnostic Resolution Path**: `Diagnostic` dataclass gains `resolution_path` field:
  - Tracks message resolution stack at time of error
  - Helps debug errors in deeply nested message references
  - Displayed in `format_error()` output as `= resolution path: msg1 -> msg2 -> ...`
- **Warning Severity Levels**: `ValidationWarning` gains `severity` field:
  - `WarningSeverity.CRITICAL`: Will cause runtime failure (undefined reference)
  - `WarningSeverity.WARNING`: May cause issues (duplicate ID)
  - `WarningSeverity.INFO`: Informational only
  - Enables filtering/prioritizing warnings in CI tooling
- **API Boundary Validation**: Defensive type checking for public APIs:
  - `format_pattern()` and `format_value()` validate `args` is `Mapping | None`
  - `format_pattern()` validates `attribute` is `str | None`
  - Invalid types return error tuple instead of raising `TypeError`

### Changed
- **Package Dependencies**: `dependencies = []` (empty) in pyproject.toml:
  - Babel moved to `[project.optional-dependencies]` as `babel` and `full` extras
  - Babel added to `[dependency-groups]` dev group for testing
- **Lazy Import Architecture**: `__init__.py` uses `__getattr__` for Babel-dependent components:
  - `FluentBundle`, `FluentLocalization`, `FluentValue`, `fluent_function` lazy-loaded
  - Clear error message when Babel not installed

### Fixed
- **Validation Warning Severity**: All validation warnings now have appropriate severity:
  - Undefined references and circular references marked CRITICAL
  - Duplicate IDs and missing values marked WARNING

## [0.50.0] - 2026-01-02

### Added
- **Fuzzing Infrastructure Overhaul**: Comprehensive improvements to testing and fuzzing scripts:
  - `fuzz.sh --clean` mode: Remove all captured failures and crash artifacts
  - `fuzz.sh --list` file ages: Shows relative age (e.g., "2h ago", "5d ago") for each failure
  - `repro.py --json` flag: Machine-readable JSON output for automation
  - `repro.py` input size limit: 10 MB maximum to prevent memory exhaustion
  - Progress indicator in `fuzz.sh` for long-running non-verbose tests
- **Structure-Aware Fuzzing Enhancements**:
  - `structured.py` numeric variant key generation: FTL supports `[1]`, `[3.14]`, `[-1]` as variant keys
  - Randomized default variant position: `*[default]` can appear anywhere, not just at end
- **Seed Corpus Improvements**:
  - Deep nesting examples: `{ { { { { $level5 } } } } }` in seed corpus
  - Attribute-only message patterns: Messages with only `.attr = value` (no main value)
  - `corpus-health.py` feature detection: `term_arguments` and `numeric_variant_key`

### Changed
- **bc Dependency Eliminated**: All fuzzing scripts now use Python for duration calculations:
  - `fuzz-atheris.sh`, `fuzz-hypothesis.sh`, `run-property-tests.sh` no longer require `bc`
  - Improves portability across systems without GNU coreutils
- **JSON Output Consistency**: All fuzzing tools use proper JSON escaping:
  - `fuzz.sh` uses `python3 -c "import json,sys; ..."` for escape sequences
  - Handles newlines, control characters, and Unicode correctly
- **Crash-Proof Reporting**: `perf.py` and `structured.py` emit JSON summary on any exit:
  - `atexit` handler guarantees output even on crash or Ctrl+C
  - Logging suppressed during fuzzing to reduce noise

### Fixed
- **Bash 5.0+ Version Guard**: `fuzz-atheris.sh` now detects bash version at startup:
  - Provides clear error message with installation instructions for macOS
  - Prevents cryptic EPOCHREALTIME errors on older bash versions
- **Mypy Configuration**: `fuzz.structured` added to pyproject.toml overrides:
  - Eliminates type errors for Atheris-specific patterns
- **Test Infrastructure**: `conftest.py` properly detects all fuzz test files:
  - Pattern expanded to include `test_concurrent` and `test_resolver_cycles`

### Removed
- **Dead Code**: `scripts/replay-failures.sh` deleted:
  - Functionality superseded by `./scripts/fuzz.sh --repro`

## [0.49.0] - 2026-01-01

### Added
- **Python 3.14 CI Support**: Full test and lint matrix for Python 3.13 and 3.14:
  - GitHub Actions workflows run both versions in parallel
  - `test.yml` workflow for PR-triggered multi-version testing
  - `publish.yml` expanded to test both versions before release
- **Multi-Version Linting**: `PY_VERSION` environment variable for lint.sh:
  - `PY_VERSION=3.14 uv run --python 3.14 scripts/lint.sh` targets Python 3.14
  - Ruff, Mypy, and Pylint all respect the version parameter
  - Default remains Python 3.13 for backwards compatibility
- **Atheris Python Version Detection**: Fuzzing scripts now detect Python 3.14+ and provide clear guidance:
  - `fuzz.sh`, `fuzz-atheris.sh`, `check-atheris.sh` check Python version before attempting Atheris import
  - Exit code 3 indicates Python version incompatibility (Atheris requires 3.11-3.13)
  - Error messages explain alternatives: switch to Python 3.13 or use Hypothesis-based fuzzing

### Changed
- **PEP 563 Annotations**: Added `from __future__ import annotations` to 9 source files:
  - Enables forward references without quotes on both Python 3.13 and 3.14
  - Required for compatibility with Python 3.14's PEP 649 (deferred evaluation)
  - Files: `bundle.py`, `function_bridge.py`, `locale_context.py`, `ast.py`, `cursor.py`, `rules.py`, `formatter.py`, `introspection.py`, `localization.py`

### Documentation
- **README.md**: Added Python Version Support table showing test/lint/fuzz coverage
- **CONTRIBUTING.md**: Added comprehensive Multi-Version Development section with:
  - Prerequisites for installing Python versions with uv
  - Quick reference table for version-specific commands
  - Explanation of `PY_VERSION` environment variable behavior
  - CI behavior documentation
- **FUZZING_GUIDE.md**: Added Python Version Requirements section:
  - Table showing which fuzzing modes work on which Python versions
  - Instructions for running native fuzzing on Python 3.14 systems
  - Updated troubleshooting to clarify Atheris version requirements

## [0.48.0] - 2026-01-01

### Breaking Changes
- **Function Name Case Sensitivity Removed**: Lowercase function names now allowed:
  - Previous: Function names required uppercase (`NUMBER()`, `DATETIME()`)
  - Now: Any valid identifier accepted (`number()`, `dateTime()`, `NUMBER()`)
  - Per Fluent 1.0 EBNF: `Function ::= Identifier` with no case restriction
  - Migration: Existing uppercase names continue to work unchanged
- **Term Scope Isolation**: Terms no longer inherit calling context variables:
  - Previous: `{ -term }` from message with `$name` could access `$name` in term
  - Now: Terms receive empty variable scope; must use explicit arguments
  - Per Fluent spec: Terms are self-contained; use `-term(name: $name)` for passing values
  - Migration: Add explicit arguments to term references where needed

### Added
- **Nested Placeable Support**: Placeables inside placeables now parse correctly:
  - `{ { $var } }` - nested variable reference
  - `{ { 123 } }` - nested number literal
  - `{ { "text" } }` - nested string literal
  - Per Fluent EBNF: `InlinePlaceable ::= "{" InlineExpression "}"`
- **Cross-Resource Validation**: New parameters for `validate_resource()`:
  - `known_messages: frozenset[str]` - message IDs from other resources
  - `known_terms: frozenset[str]` - term IDs from other resources
  - References to known entries no longer produce undefined warnings
  - `FluentBundle.validate_resource()` automatically passes existing entries
- **Fast-Tier Currency Pattern**: Two-tier parsing for common currencies:
  - Fast tier: USD, EUR, GBP, JPY, CNY with common symbols
  - Falls back to full CLDR scan only when fast pattern fails
  - Reduces cold-start latency for common currency operations
- **ParseContext Propagation**: Depth tracking through expression parsing:
  - `ParseContext` passed through all expression parsing functions
  - Enables consistent nesting depth limits across parser

### Fixed
- **String Literal Line Endings**: Now rejected per Fluent specification:
  - Previous: LF/CR in string literals accepted silently
  - Now: Returns parse error; use `\\n` escape sequence for newlines
  - Per Fluent EBNF: `quoted_char ::= (any_char - special_quoted_char - line_end)`
- **Tab Before Variant Marker**: Now rejected per Fluent specification:
  - Previous: Tab before `*[other]` accepted as indentation
  - Now: Only spaces allowed for variant indentation
  - Per Fluent spec: Tabs prohibited in FTL content

### Changed
- **Thread-Local Parse Error Cleanup**: `clear_parse_error()` called at parser entry:
  - Prevents stale error context from previous parse operations
  - Ensures clean error state for each parse invocation

## [0.47.0] - 2025-12-31

### Breaking Changes
- **FluentBundle Context Manager Behavior**: `__exit__` no longer clears messages/terms:
  - Previous: Bundle cleared all registered messages and terms on context exit
  - Now: Only format cache cleared; messages and terms preserved
  - Bundle remains fully usable after exiting `with` block
  - Migration: No action required (behavior is now less surprising)

### Security
- **ASTVisitor Depth Guard Bypass Closed**: Depth protection moved to `visit()` dispatcher:
  - Previous: Depth guard only in `generic_visit()`, allowing bypass via custom visitor methods
  - Now: Every `visit()` call increments depth counter, regardless of dispatch path
  - Prevents stack overflow from adversarial ASTs traversed via custom `visit_*` methods
  - Affects: ASTVisitor, ASTTransformer, and all subclasses

### Fixed
- **Date/Datetime Pattern Trailing Whitespace**: Normalized after skipped timezone tokens:
  - Previous: Pattern `"HH:mm zzzz"` produced `"%H:%M "` with trailing space
  - Now: Trailing whitespace stripped from strptime patterns
  - Prevents "unconverted data remains" errors from timezone name inputs
- **ZZZZ Timezone Token Handling**: Now correctly mapped to `None` (skipped):
  - Previous: ZZZZ mapped to `%z` but CLDR format `"GMT-08:00"` is unparseable by strptime
  - Now: ZZZZ silently skipped like other timezone name patterns (z, v, V, O series)
  - Documentation updated to list ZZZZ as unsupported
- **Production Assert Replaced with Defensive Check**: In `parse_currency()`:
  - Previous: `assert currency_code is not None` could be disabled by `python -O`
  - Now: Explicit `if` check with `RuntimeError` for invariant violation
  - Provides protection regardless of Python optimization level

### Documentation
- **Character Offset Terminology**: Standardized across all source code:
  - `SourceSpan`: Now documents "character offset" (not "byte offset")
  - `position.py` functions: All docstrings updated to "character offset"
  - Note: Python strings measure positions in characters (Unicode code points), not bytes
- **Date Parsing Timezone Support**: Clarified ZZZZ limitation:
  - Module docstring: ZZZZ produces "GMT-08:00" format, unparseable by strptime
  - Inline comments: Updated supported/unsupported pattern lists
- **ASTVisitor Depth Protection**: Docstrings updated for new guard location:
  - `visit()`: Now documents depth protection and `DepthLimitExceededError`
  - `generic_visit()`: Notes depth protection is handled by `visit()`

## [0.46.0] - 2025-12-31

### Breaking Changes
- **ASTVisitor/ASTTransformer Initialization**: Subclasses MUST call `super().__init__()`:
  - Depth guard now initialized in base class `__init__`
  - Subclasses that skip `super().__init__()` will raise `AttributeError` on first visit
  - Migration: Add `super().__init__()` to any custom visitor `__init__` methods
- **ASTVisitor max_depth Parameter**: New optional constructor parameter:
  - `ASTVisitor(max_depth=50)` configures depth limit (default: MAX_DEPTH=100)
  - Subclasses can pass custom limits via `super().__init__(max_depth=N)`

### Security
- **ASTVisitor/ASTTransformer Depth Protection**: Guards against stack overflow:
  - Programmatically constructed adversarial ASTs could bypass parser depth limits
  - Now uses DepthGuard consistent with parser, resolver, and serializer
  - Raises `DepthLimitExceededError` when MAX_DEPTH (100) exceeded
  - Protects all visitor subclasses including validation, serialization, introspection
- **FormatCache Depth Limiting**: `_make_hashable()` now tracks recursion depth:
  - Deeply nested dict/list/set structures could exhaust stack
  - Now raises `TypeError` at MAX_DEPTH (100), triggering graceful cache bypass
  - Consistent with codebase depth protection pattern

### Changed
- **FormatCache Type Validation**: `_make_hashable()` uses explicit isinstance checks:
  - Previous: `cast(HashableValue, value)` in catch-all case (type system lie)
  - Now: Explicit pattern matching for known FluentValue types
  - Unknown types raise `TypeError` with descriptive message
  - Provides honest type representation and runtime safety
- **FormatCache._make_key Simplification**: Single-pass value conversion:
  - All values now processed through `_make_hashable()` uniformly
  - Removes conditional path that used `cast()` for direct values
  - Cleaner code flow with consistent type validation
- **Introspection Visitor Slots**: Removed redundant `_depth_guard` from subclass `__slots__`:
  - `_VariableFunctionCollector` and `_ReferenceCollector` inherit from ASTVisitor
  - Depth guard now inherited from parent class
  - Reduces memory overhead and fixes redefined-slots warnings

### Documentation
- **FALLBACK_FUNCTION_ERROR Design Rationale**: Documents "!" prefix choice:
  - Uses "!" (not valid FTL syntax) to distinguish from message references
  - Makes function errors immediately identifiable in output
- **FluentResolver.resolve_message Context Parameter**: Expanded usage guidance:
  - Documents typical vs advanced usage patterns
  - Cross-references ResolutionContext class for configuration
- **Error Terminology Consistency**: Standardized "FluentError instances" in docstrings:
  - `FluentBundle.format_pattern` return documentation
  - `FluentResolver.resolve_message` return documentation

## [0.45.0] - 2025-12-31

### Breaking Changes
- **Annotation.arguments Type**: Changed from `dict[str, str] | None` to `tuple[tuple[str, str], ...] | None`:
  - Enforces immutability for frozen dataclass
  - Preserves insertion order (dict order guarantee not always sufficient)
  - Migration: Replace `annotation.arguments["key"]` with dict conversion or iteration

### Added
- **FluentBundle.cache_usage Property**: New property for current cache entries:
  - `cache_size` returns configured limit regardless of `cache_enabled` state
  - `cache_usage` returns current number of cached entries (0 if disabled)
  - Separates configuration from runtime state
- **Introspection Span Fields**: `VariableInfo`, `FunctionCallInfo`, `ReferenceInfo` now have `span` field:
  - Enables IDE integration for go-to-definition and hover features
  - Expression AST nodes (`VariableReference`, `MessageReference`, `TermReference`, `FunctionReference`) now track source positions
  - Spans propagated through IntrospectionVisitor to info objects
  - API extension is non-breaking (default value `None` for programmatic ASTs)
- **MAX_LOOKAHEAD_CHARS Constant**: Centralized parser lookahead limit:
  - Located in `ftllexengine.constants`
  - Used by `_is_variant_marker()` for bounded lookahead (128 chars)
  - Prevents O(N^2) parsing on adversarial input

### Changed
- **Plural Rule CLDR Root Fallback**: Unknown locales now use CLDR root locale:
  - Previous: Hardcoded `abs(n) == 1` returned "one", else "other"
  - Now: Babel's CLDR root locale returns "other" for all values
  - Safer default that makes no language-specific assumptions
- **Cache Key Single-Pass Conversion**: `FormatCache._make_key()` optimized:
  - Previous: Two-pass (any() check + list comprehension)
  - Now: Single-pass inline conversion with hashability check
  - Performance improvement for cache key construction
- **FluentLocalization Lazy Bundle Storage**: `_bundles` dict optimized:
  - Previous: Pre-populated with `None` markers for all locales
  - Now: Empty dict; bundles added on first access
  - Eliminates null-check boilerplate in iteration methods
- **Copy-on-Write Function Registry**: FluentBundle defers registry copying:
  - Shared registry used directly until first `add_function()` call
  - Reduces memory allocation for bundles that never add custom functions
  - Transparent optimization (no API change)
- **Currency Code Pattern Helper**: Extracted `_get_iso_code_pattern()` method:
  - CLDR pattern manipulation for ISO code display centralized
  - Defensive null checks prevent AttributeError on edge cases
- **Whitespace Handling**: `skip_whitespace()` no longer checks for CR:
  - CR is normalized to LF at parser entry (`FluentParserV1.parse()`)
  - Simplifies whitespace definition (space + LF only)
  - Documents normalization assumption in docstring

### Fixed
- **Serializer Comment Newline**: Removed extra newline after attached comments:
  - Previous: Extra `\n` added after comment in `_serialize_message` and `_serialize_term`
  - Now: Comments followed directly by entry without double newline
  - Improves roundtrip fidelity for comment-attached entries
- **Boolean Selector Stringification**: `True`/`False` now format as `"true"`/`"false"`:
  - Previous: `str(True)` produced `"True"`, missing `[true]` variant
  - Now: Uses `_format_value()` for consistent string conversion
  - Matches Fluent spec boolean variant key expectations
- **FluentNumber Variant Matching**: Extracts `.value` for numeric comparison:
  - Previous: `FluentNumber(5)` didn't match `[5]` variant
  - Now: Numeric comparison uses underlying value, not wrapper object
- **Junk Annotation Propagation**: Preserves specific parser error codes:
  - Previous: All Junk entries reported as generic "parse-error"
  - Now: Iterates Junk annotations to extract specific codes/messages
  - Improves error diagnostics granularity
- **Template String Collision**: Uses `.replace()` instead of `.format()`:
  - Previous: `{locale}` in paths could raise `KeyError` on FTL content
  - Now: Only `{locale}` placeholder is replaced, FTL braces preserved

### Removed
- **has_timezone Dead Code**: Removed from `_babel_to_strptime()` and callers:
  - Return type changed from `tuple[str, bool, bool]` to `tuple[str, bool]`
  - Timezone tracking was unused (timezone names not stripped from input)
  - Simplifies pattern extraction API

### Security
- **PathResourceLoader Path Resolution**: Defense-in-depth for path traversal:
  - `_is_safe_path()` now explicitly `resolve()` both base and target paths
  - Prevents symlink-based path traversal bypasses
  - Complements existing `relative_to()` check

### Documentation
- **Locale Injection Protocol**: Documented in `fluent_function` decorator docstring:
  - Locale code appended after all positional arguments
  - For single-argument functions, locale becomes second positional arg
  - Protocol consistent with current implementation
- **DepthGuard Mutability Note**: Documents intentional non-frozen design
- **LocaleContext Instance Sharing**: Clarifies Flyweight pattern for cache
- **ReferenceInfo**: Enhanced docstring with examples
- **DateTime Fallback Rationale**: Documents `"{1} {0}"` pattern choice
- **CLDR Scan Latency**: Documents 200-500ms cold start for currency scan
- **Function Bridge Type Safety**: Notes runtime vs compile-time type checking
- **max_source_size Unit**: Fixed "bytes" to "characters" in docstring

## [0.44.0] - 2025-12-30

### Breaking Changes
- **FormattingError Signature**: Now accepts `str | Diagnostic` to match parent class:
  - Previous: `FormattingError(message: str, fallback_value: str)`
  - Current: `FormattingError(message: str | Diagnostic, fallback_value: str)`
  - Fixes Liskov Substitution Principle violation in exception hierarchy
  - Code passing `Diagnostic` objects to FormattingError now type-checks correctly

### Added
- **LocaleContext.is_fallback Property**: Detect when locale fallback occurred:
  - `ctx.is_fallback` returns `True` if locale was unknown and fell back to en_US
  - Enables programmatic detection without log parsing
  - Fallback still logged as warning; property provides observability
- **ParseResult[T] Type Alias**: Generic type for parsing function returns:
  - `tuple[T | None, tuple[FluentParseError, ...]]` pattern
  - Exported from `ftllexengine.parsing`
  - Improves type safety and documentation for parse_* functions
- **Word Boundary Era Stripping**: Prevents partial matches in date parsing:
  - "bad" no longer matches "AD", "cereal" no longer matches "CE"
  - Uses `_is_word_boundary()` helper for robust detection

### Changed
- **FunctionMetadata Memory**: Uses `slots=True` for smaller footprint:
  - Reduces per-instance memory by ~40 bytes
  - Matches other frozen dataclasses in codebase
- **Serializer Module Import**: DepthGuard now imported at module level:
  - Was: Runtime import inside `serialize()` with noqa comment
  - Now: Standard module-level import (circular dependency resolved)
  - Import order in `syntax/__init__.py` ensures ast loaded before serializer
- **Unified Lookahead Bound**: `_is_variant_marker()` shares counter for whitespace:
  - Inner whitespace loop now increments main `lookahead_count`
  - Enforces documented 128-char bound consistently
- **Explicit Entry Type Handling**: Bundle uses `case Comment()` not `case _`:
  - Catch-all replaced with explicit Comment handling
  - Future entry type extensions won't be silently dropped
- **Module-Level Decimal Import**: `validator.py` imports Decimal at module level:
  - Was: Runtime import inside `_variant_key_to_string()` with noqa comment
  - Now: Standard module-level import (no circular dependency for stdlib)
- **Thread-Safe Singleton Pattern**: `get_shared_registry()` uses `lru_cache`:
  - Was: Global variable with check-then-act race condition
  - Now: `functools.lru_cache(maxsize=1)` on helper function
  - Eliminates race condition on first initialization
- **DRY Position Helper**: `_get_entry_position()` extracted to module level:
  - Was: Duplicated nested function in two validation functions
  - Now: Single module-level helper shared by all callers

### Fixed
- **Singleton Race Condition**: `get_shared_registry()` thread-safe on first call
- **Era Stripping Partial Match**: Date parsing no longer strips era substrings
- **Unused Loop Variable**: Removed `_idx` from term reference positional arg loop
- **Circular Import**: Serializer can now import DepthGuard at module level

### Documentation
- **parse_number() Precision Warning**: Docstring warns about float conversion loss
- **parse_date/datetime Timezone Warning**: Docstrings warn timezone names unsupported
- **README Thread-Safety**: Updated note that all FluentBundle methods are synchronized
- **Fallback Constants Escaping**: Added comment explaining `{{`/`}}` Python escaping

## [0.43.0] - 2025-12-30

### Breaking Changes
- **Pattern Continuation Lines**: Now joined with newline (`\n`) instead of space:
  - Previous: Multi-line patterns joined with single space
  - Current: Continuation lines preserve line break per Fluent Spec 1.0 Section 4.5.2
  - Affects pattern values spanning multiple indented lines
- **Line Ending Normalization**: All line endings normalized to LF before parsing:
  - CRLF (`\r\n`) and CR (`\r`) converted to LF (`\n`)
  - Simplifies line/column tracking and comment merging logic
  - Per Fluent spec requirement for consistent AST representation

### Added
- **Column-1 Enforcement**: Top-level entries must start at column 1:
  - Indented entries now rejected as Junk with "Entry must start at column 1" annotation
  - Per Fluent specification for message/term/comment positioning
- **Pattern Blank Line Trimming**: Leading/trailing blank lines removed from patterns:
  - `_trim_pattern_blank_lines()` post-processes pattern elements
  - Per Fluent spec whitespace handling rules
- **FluentNumber Class**: Preserves numeric identity after NUMBER() formatting:
  - `FluentNumber(value, formatted)` stores both original numeric value and formatted string
  - Enables proper plural category matching (`[one]`, `[other]`) in select expressions
  - Previous: NUMBER() returned `str`, breaking plural matching
- **Selector Resilience**: SelectExpression falls back to default variant on selector failure:
  - `FluentReferenceError` and `FluentResolutionError` caught during selector evaluation
  - Error collected, default variant used instead of failing entire placeable
  - Per Fluent specification for graceful degradation
- **Junk Reporting in FluentLocalization**: `ResourceLoadResult` and `LoadSummary` expose Junk entries:
  - `ResourceLoadResult.junk_entries`: Junk entries from parsing this resource
  - `ResourceLoadResult.has_junk`: Property to check for Junk presence
  - `LoadSummary.junk_count`: Total Junk entries across all resources
  - `LoadSummary.has_junk`: Property to check for any Junk
  - `LoadSummary.get_with_junk()`: Get results containing Junk
  - `LoadSummary.get_all_junk()`: Get flattened tuple of all Junk entries

### Changed
- **Comment Merging Logic**: Uses `pos_after_blank` for accurate blank line detection:
  - Previous: Checked region before blank skipping (always empty)
  - Current: Checks region after blank skipping (correct detection)
- **Variant Key Normalization**: Uses `Decimal` for numeric key uniqueness:
  - `[1]` and `[1.0]` now correctly detected as duplicate variants
  - Previous: String comparison allowed both to coexist
- **Namespace Separation**: Messages and terms use separate ID namespaces in validation:
  - `seen_message_ids` and `seen_term_ids` tracked independently
  - Message `foo` and term `-foo` no longer flagged as duplicates
- **Documentation**: `max_source_size` now documented as "characters" not "bytes":
  - Python `len(source)` measures character count, not byte count
  - Updated in `FluentBundle`, `FluentParserV1` docstrings and error messages
- **Junk Serialization**: Only adds newline if content doesn't already end with one:
  - Prevents redundant blank lines in parse/serialize cycles
- **datetime_format Documentation**: ISO 8601 string conversion now documented:
  - Accepts `datetime | str` with `datetime.fromisoformat()` conversion
  - Raises `FormattingError` for invalid ISO 8601 format

### Fixed
- **Comment Merging**: Comments separated by blank lines no longer incorrectly merged
- **Pattern Joining**: Multi-line patterns preserve line breaks per Fluent spec
- **Column-1 Entries**: Indented top-level content now creates Junk entries
- **Line Ending Handling**: CR and CRLF line endings work correctly throughout parser
- **Pattern Whitespace**: Leading/trailing blank lines trimmed from patterns
- **Namespace Collision**: Messages and terms no longer share duplicate ID detection
- **Variant Uniqueness**: Numeric keys compared by value, not string representation
- **Selector Failures**: Graceful fallback instead of cascading failure
- **Number Plural Matching**: NUMBER() output usable as selector for plural variants
- **Junk Visibility**: FluentLocalization exposes parsing errors via load summary
- **Thread-Safe Docstring**: format_pattern() docstring updated (was outdated)

## [0.42.0] - 2025-12-29

### Breaking Changes
- **Thread-Safety Always On**: `FluentBundle.thread_safe` parameter removed:
  - All bundles are now always thread-safe via internal RLock
  - `is_thread_safe` property removed (would always return `True`)
  - Simplifies API; thread-safe mode had negligible overhead (~10ns per acquire)
- **`add_resource()` Returns Errors**: Now returns `tuple[Junk, ...]` instead of `None`:
  - Returns tuple of Junk entries encountered during parsing
  - Empty tuple indicates successful parse with no errors
  - Enables programmatic error handling without redundant `validate_resource()` call
  - Applies to both `FluentBundle.add_resource()` and `FluentLocalization.add_resource()`

### Added
- **`HashableValue` Type Alias**: Exported from `ftllexengine.runtime.cache`:
  - Defines all possible hashable values for cache keys
  - Recursive type: primitives plus `tuple[HashableValue, ...]` and `frozenset[HashableValue]`
  - Improves type safety for cache key construction
- **`introspect_term()` Method**: New method on `FluentBundle`:
  - Introspects term dependencies similar to `introspect_message()`
  - Returns `MessageIntrospection` with variables, message refs, term refs, and functions
  - Raises `KeyError` if term not found
- **Comment-Message Association**: Parser attaches single-hash comments to entries:
  - Single-hash (`#`) comments directly preceding messages/terms are attached to `comment` field
  - Group (`##`) and resource (`###`) comments remain as standalone entries
  - Blank line between comment and entry prevents association
  - Implements Fluent specification behavior

### Changed
- **Locale Normalization Lowercase**: `normalize_locale()` returns lowercase locale codes:
  - BCP-47 locale codes are case-insensitive; lowercase is canonical form
  - Prevents redundant cache entries for "en-US" vs "EN-US" vs "en_us"
  - Applies to all internal locale lookups and cache keys
- **Comment Joining**: Adjacent comments of same type are joined:
  - Multiple consecutive single-hash (`#`) comments become one Comment node
  - Content joined with newline separators
  - Span covers entire joined region
  - Implements Fluent specification behavior
- **Function Type Hints Expanded**: `number_format()` and `currency_format()` accept `Decimal`:
  - Type signature now `int | float | Decimal` matching `LocaleContext` methods
  - Enables precise monetary calculations with `Decimal` type
- **Term Argument Resolution**: Parameterized terms now properly resolve arguments:
  - `-term(arg: $value)` correctly passes arguments to term pattern
  - Arguments merged into resolution context for term's value

### Fixed
- **Surrogate Validation for `\uXXXX`**: Short Unicode escapes now reject surrogates:
  - `\uD800` through `\uDFFF` now raise parse error
  - Matches existing validation for `\UXXXXXX` escapes
  - Prevents invalid UTF-16 surrogates in FTL strings
- **Pattern Resolution Performance**: `_resolve_pattern()` uses O(N) join:
  - Previous: O(N^2) string concatenation with `result +=`
  - Fixed: Collect elements in list, return `"".join(parts)`
- **IntrospectionVisitor Term Arguments**: Traverses `TermReference.arguments`:
  - Previous: Only added term ID, missed nested variables/references
  - Fixed: Variables in term call arguments (`-term(var: $nested)`) now detected

## [0.41.0] - 2025-12-29

### Breaking Changes
- **`parse_inline_expression()` Signature Change**: Removed unused `context` parameter:
  - Previous: `parse_inline_expression(cursor, context=None)`
  - Current: `parse_inline_expression(cursor)`
  - The `context` parameter was documented as "reserved for future use" but was never utilized
  - Internal callers updated; external callers passing `context` will get `TypeError`
- **`format_datetime()` Error Handling**: Invalid ISO 8601 strings now raise `FormattingError`:
  - Previous: Returned `"{!DATETIME}"` fallback silently
  - Current: Raises `FormattingError` with `fallback_value="{!DATETIME}"`
  - Aligns with `format_number()` and `format_currency()` error propagation
  - Resolver catches exception, collects error, uses `fallback_value` for output
- **`FluentSerializer` Not Exported**: Removed from `syntax.serializer.__all__`:
  - Class remains accessible via direct import: `from ftllexengine.syntax.serializer import FluentSerializer`
  - Public API is `serialize()` function (per `syntax/__init__.py` design)
- **Localization Empty Message ID Error**: Changed error message wording:
  - Previous: `"Empty message ID"`
  - Current: `"Empty or invalid message ID"`
  - Both `format_value()` and `format_pattern()` now use consistent validation

### Changed
- **Pattern Matching for Error Type Narrowing**: `FluentResolver` uses `match/case` instead of `isinstance`:
  - Eliminates `# pylint: disable=no-member` suppression
  - Pattern matching extracts `FormattingError.fallback_value` in one step
- **Unified Validation in `FluentLocalization`**: New `_handle_message_not_found()` helper:
  - Single source of truth for message-not-found validation logic
  - Both `format_value()` and `format_pattern()` delegate to helper
  - Consistent error messages for empty, invalid, or missing message IDs

### Fixed
- **Datetime Error Collection**: Invalid ISO 8601 strings now properly collected as errors:
  - Previous: Silent fallback bypassed error collection
  - Fixed: `FormattingError` propagates through resolver, appears in `(result, errors)` tuple
  - Callers can now detect and report datetime parsing failures

## [0.40.0] - 2025-12-29

### Breaking Changes
- **Error Propagation Architecture**: Formatting functions now raise `FormattingError` instead of returning fallback values:
  - `LocaleContext.format_number()`, `format_datetime()`, `format_currency()` raise `FormattingError`
  - `FormattingError.fallback_value` contains the fallback string for resolver to use
  - Resolver catches `FormattingError`, collects it as `FluentError`, and uses `fallback_value`
  - Enables proper error reporting to callers via `(result, errors)` tuple pattern
- **Currency Module Architecture**: `CurrencyDataProvider` singleton class removed:
  - Module-level `@functools.cache` functions replace class-based singleton
  - `_build_currency_maps_from_cldr()` cached for process lifetime
  - Thread-safe via `functools.cache` internal locking
  - Aligns with `dates.py` CLDR data access pattern
- **Serializer Defaults**: `serialize()` and `FluentSerializer.serialize()` now default to `validate=True`:
  - Invalid ASTs (e.g., SelectExpression without default variant) raise `SerializationValidationError`
  - Previous default (`validate=False`) silently produced invalid FTL
  - Use `validate=False` explicitly for trusted ASTs only
- **Internal API Removals**:
  - `_get_root_dir()` method removed from `PathResourceLoader`; use `_resolved_root` cached field
  - `has_timezone` parameter removed from `_preprocess_datetime_input()` (was ignored)
  - Version provenance comments removed from source files (CHANGELOG.md is single source of truth)
- `introspect_message()` now raises `TypeError` for invalid input types:
  - Accepts only `Message` or `Term` AST nodes
  - Previously raised `AttributeError` deep in visitor traversal

### Added
- **Core Package** (`ftllexengine.core`): Shared infrastructure components:
  - `ftllexengine.core.errors.FormattingError` for formatting function error propagation
  - `ftllexengine.core.depth_guard.DepthGuard` moved from `syntax.parser.primitives`
  - Resolves circular dependency between `syntax` and `runtime` packages
- **Parser Security Configuration** on `FluentBundle`:
  - `max_source_size` parameter (default: 10 MB) limits FTL source size
  - `max_nesting_depth` parameter (default: 100) limits placeable nesting
  - `max_source_size` and `max_nesting_depth` read-only properties for introspection
- **Type Validation** in `introspect_message()`:
  - Runtime check raises `TypeError("Expected Message or Term, got X")` for invalid types
  - Provides clear error message at API boundary instead of deep `AttributeError`

### Changed
- **Error Propagation**: `LocaleContext` formatting methods propagate errors via `FormattingError`:
  - Replaces silent fallback returns that masked configuration issues
  - `FluentResolver` catches errors, adds to error list, uses `fallback_value`
  - Callers can now detect and report formatting failures
- **CLDR Data Access**: Currency module uses `@functools.cache` pattern:
  - `_get_currency_maps()` returns merged fast-tier + full CLDR data
  - `_get_currency_maps_full()` returns complete CLDR scan (lazy-loaded)
  - Consistent with `dates.py` approach; removes class-based singleton
- **Visitor Type Safety**: `IntrospectionVisitor` now typed as `ASTVisitor[None]`:
  - Explicitly declares visitor returns `None` (side-effect only)
  - `ReferenceExtractor` typed as `ASTVisitor[MessageReference | TermReference]`
- **Validation Performance**: Shared `LineOffsetCache` across validation passes:
  - Built once in `validate_resource()`, passed to all helper functions
  - Eliminates redundant O(n) source scans per validation pass
- **Path Resolution Performance**: `PathResourceLoader` caches resolved root:
  - `_resolved_root` computed once in `__post_init__`
  - Eliminates repeated `Path.resolve()` syscalls on each `load()` call
- **Test Strategy**: `ftl_select_expressions()` now ensures valid SelectExpressions:
  - Exactly one default variant (per Fluent spec)
  - Unique variant keys (prevents duplicate key validation errors)

### Fixed
- **Parser DoS Vulnerability**: Quadratic lookahead in variant detection:
  - `_is_variant_marker()` limited to prevent O(N^2) worst-case
  - Crafted input with many `[` characters no longer causes quadratic scan
- **Parser Performance**: String concatenation in loops replaced with list join:
  - `parse_string_literal()` uses `chars.append()` + `"".join(chars)`
  - Avoids O(N^2) worst-case from string immutability
- **Validation Performance**: Redundant `LineOffsetCache` construction:
  - Previous: Each helper function built separate cache (3-4x redundant scans)
  - Fixed: Single cache shared across all validation passes
- **Error Formatting Performance**: `ParseError` uses `LineOffsetCache`:
  - Previous: O(N) line/column computation per error
  - Fixed: O(log N) lookup via shared binary search index
- **Silent Formatting Failures**: `LocaleContext` now propagates errors:
  - Previous: Invalid patterns, missing locale data returned silent fallbacks
  - Fixed: `FormattingError` raised, collected by resolver, reported to caller

### Removed
- `CurrencyDataProvider` class from `parsing/currency.py`
- `_get_root_dir()` method from `PathResourceLoader`
- `has_timezone` parameter from `_preprocess_datetime_input()`

## [0.39.0] - 2025-12-29

### Breaking Changes
- FTL identifier parsing now enforces ASCII-only characters per Fluent specification:
  - Only ASCII letters `[a-zA-Z]` valid for identifier start
  - Only ASCII alphanumerics, hyphen, underscore `[a-zA-Z0-9_-]` valid for continuation
  - Unicode letters (e.g., `é`, `ñ`, `µ`) now rejected for cross-implementation compatibility
  - Affects message IDs, term IDs, variant keys, function names, variable names
- Pound sign (`£`, U+00A3) now treated as ambiguous currency symbol:
  - Requires `default_currency="GBP"` or `infer_from_locale=True` for parsing
  - Resolves to EGP for Arabic locales (`ar_*`), GBP for English locales, GBP default
  - Previously hardcoded to GBP regardless of locale context
- Timezone name stripping removed from date/datetime parsing:
  - `_strip_timezone()` function removed
  - `_TIMEZONE_STRINGS` tuple removed
  - Timezone name tokens (`z`, `zz`, `zzz`, `zzzz`, `v`, `V`, `O` series) still stripped from pattern
  - Input must be pre-stripped by caller or use UTC offset patterns (`Z`, `x`, `X` series)
  - Previous English-only stripping created inconsistent i18n behavior

### Added
- `is_identifier_start()` predicate in `syntax.parser.primitives` for ASCII-only identifier start check
- `is_identifier_char()` predicate in `syntax.parser.primitives` for ASCII-only identifier continuation check
- Locale-specific pound sign resolution:
  - `ar_EG` -> EGP (Egyptian Pound)
  - `ar` -> EGP (Arabic locales default)
  - `en_GB` -> GBP (British Pound)
  - `en_GI` -> GIP (Gibraltar Pound)
  - `en_FK` -> FKP (Falkland Islands Pound)
  - `en_SH` -> SHP (Saint Helena Pound)
  - `en_SS` -> SSP (South Sudanese Pound)

### Changed
- `DepthGuard.__enter__()` now validates depth limit BEFORE incrementing:
  - Prevents state corruption when `DepthLimitExceededError` raised
  - `__exit__` not called when `__enter__` raises; old code left depth permanently elevated
- Boolean values excluded from plural category matching in select expressions:
  - `True`/`False` no longer match `[one]`/`[other]` plural variants
  - Python's `bool <: int` inheritance previously caused incorrect dispatch
- Junk entry logging now uses `repr()` instead of `ascii()`:
  - Preserves Unicode readability while escaping control characters
  - `'Jānis'` instead of `'J\xe2nis'` in log output
- Babel imported at module level in `locale_utils.py`:
  - Lazy import pattern removed for consistency with other parsing modules
  - All parsing modules already import Babel at top level; lazy pattern provided no benefit

### Fixed
- DepthGuard context manager state latch on error (critical bug):
  - Previous: depth incremented before check, exception leaves state corrupted
  - Fixed: depth limit validated before increment, no state mutation on failure
- Boolean selector matching plural categories:
  - Previous: `True` (value 1) matched `[one]` variant due to `isinstance(True, int)`
  - Fixed: explicit boolean exclusion before plural category dispatch
- Identifier parsing accepts Unicode letters:
  - Previous: `isalpha()` accepted `µ`, `é`, `ñ` as identifier characters
  - Fixed: ASCII-only enforcement via `is_identifier_start()` and `is_identifier_char()`
- Pound sign (`£`) hardcoded to GBP regardless of locale:
  - Previous: Fast tier forced `£ -> GBP` even in Egyptian locale
  - Fixed: Locale-aware resolution via ambiguous symbol system
- Timezone stripping only worked for English:
  - Previous: Hardcoded English timezone names failed for localized input
  - Fixed: Feature removed; users must pre-strip or use UTC offset patterns

### Documented
- Hour-24 limitation in `dates.py` module docstring:
  - CLDR `k`/`kk` tokens (1-24) mapped to Python's `%H` (0-23)
  - Input "24:00" will fail to parse
  - Workaround: preprocess to normalize "24:00" to "00:00" with day increment

## [0.38.0] - 2025-12-28

### Breaking Changes
- Yen sign (`¥`, U+00A5) now treated as ambiguous currency symbol:
  - Requires `default_currency="JPY"` or `infer_from_locale=True` for parsing
  - Resolves to CNY for Chinese locales (`zh_*`), JPY otherwise
  - Previously hardcoded to JPY regardless of locale context
- `_babel_to_strptime()` internal API now returns 3 values `(pattern, has_era, has_timezone)` instead of 2

### Added
- `CurrencyDataProvider` class in `currency.py` encapsulating all currency data and loading logic:
  - Replaces module-level global variables with instance attributes
  - Provides `resolve_ambiguous_symbol()` for locale-aware symbol resolution
  - Thread-safe lazy initialization via double-check locking pattern
- Locale-aware resolution for ambiguous currency symbols:
  - `_AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION` dict for context-sensitive mappings
  - `_AMBIGUOUS_SYMBOL_DEFAULTS` dict for fallback when locale doesn't match
- `_strip_timezone()` function in `dates.py` for timezone string stripping
- `_preprocess_datetime_input()` unified preprocessing for era and timezone tokens
- `_TIMEZONE_STRINGS` tuple with comprehensive US/European timezone names and abbreviations
- `thread_safe` parameter to `FluentBundle.__init__()`:
  - When `True`, all methods use internal RLock for synchronization
  - `add_resource()` and `format_pattern()` become thread-safe
  - Default `False` to avoid performance overhead for single-threaded patterns
- `is_thread_safe` read-only property on `FluentBundle` for introspection
- `has_attribute(message_id, attribute)` method on `FluentBundle` for attribute existence checking
- Multiline variant value support in select expressions:
  - Variant values can now span multiple indented lines
  - Continuation lines are properly consumed and joined with spaces

### Changed
- Currency module architecture refactored to eliminate global mutable state:
  - Module-level singleton `_provider = CurrencyDataProvider()` maintains API compatibility
  - All global variable access replaced with provider method calls
- `_babel_to_strptime()` returns separate flags for era and timezone tokens:
  - Enables targeted preprocessing for each token type
  - Timezone tokens (z/zzzz/v/V/O) now strip timezone names from input
- Date/datetime parsing preprocessing unified via `_preprocess_datetime_input()`
- `FluentBundle.add_resource()` and `format_pattern()` now support optional thread-safe operation

### Fixed
- Yen sign (`¥`) now correctly maps to CNY for Chinese locales, JPY for others
- Global mutable state in `currency.py` replaced with encapsulated provider class
- Date parsing now succeeds for patterns containing timezone tokens (e.g., `zzzz` in `en_US`)
- Race condition in `FluentBundle` prevented via opt-in thread safety
- Parser now handles multiline variant values in select expressions

## [0.37.0] - 2025-12-28

### Breaking Changes
- `ERROR_CODES` dict removed from `syntax/validator.py`; validation errors now use `DiagnosticCode` enum
- Module-level cache functions removed from `locale_context.py`:
  - `_clear_locale_context_cache()` removed; use `LocaleContext.clear_cache()` class method
  - `_get_locale_context_cache_size()` removed; use `LocaleContext.cache_size()` class method
- Validation error codes unified under `DiagnosticCode` enum (5000-5199 range):
  - `VALIDATION_TERM_NO_VALUE` (5004)
  - `VALIDATION_SELECT_NO_DEFAULT` (5005)
  - `VALIDATION_SELECT_NO_VARIANTS` (5006)
  - `VALIDATION_VARIANT_DUPLICATE` (5007)
  - `VALIDATION_NAMED_ARG_DUPLICATE` (5010)
  - `VALIDATION_PARSE_ERROR` (5100)
  - `VALIDATION_CRITICAL_PARSE_ERROR` (5101)
  - `VALIDATION_DUPLICATE_ID` (5102)
  - `VALIDATION_NO_VALUE_OR_ATTRS` (5103)
  - `VALIDATION_UNDEFINED_REFERENCE` (5104)
  - `VALIDATION_CIRCULAR_REFERENCE` (5105)

### Added
- `LocaleContext.clear_cache()` class method for cache management
- `LocaleContext.cache_size()` class method to query cache size
- `LocaleContext.cache_info()` class method returning size, max_size, and cached locales
- `_load_single_resource()` helper method in `FluentLocalization` for cleaner initialization
- Tiered CLDR loading in `currency.py` for faster cold start:
  - Fast Tier: ~50 common currencies with hardcoded unambiguous symbols (immediate, zero CLDR overhead)
  - Full Tier: Complete CLDR scan (lazy-loaded on first cache miss)
- CLDR pattern conversion architecture documentation in `dates.py`
- Depth-limiting architecture documentation in `constants.py`
- Explicit `__all__` declarations added to 26 modules for public API clarity

### Changed
- `syntax/validator.py` migrated from `ERROR_CODES` dict to `DiagnosticCode` enum
- `validation/resource.py` migrated from hardcoded strings to `DiagnosticCode.*.name`
- `LocaleContext` cache encapsulated as class-level state (`ClassVar`) instead of module-level variables
- `FluentLocalization.__init__` resource loading extracted to `_load_single_resource()` helper

## [0.36.0] - 2025-12-27

### Breaking Changes
- `ASTVisitor[T]` generic parameter no longer has upper bound constraint; allows `None` and `list` return types
- Constants consolidated to `ftllexengine.constants` module:
  - `MAX_DEPTH` replaces `MAX_RESOLUTION_DEPTH`, `MAX_EXPRESSION_DEPTH`, `DEFAULT_MAX_NESTING_DEPTH`
  - `MAX_LOCALE_CACHE_SIZE` replaces `_MAX_LOCALE_CACHE_SIZE`
  - `MAX_SOURCE_SIZE` replaces `DEFAULT_MAX_SOURCE_SIZE`
  - `DEFAULT_CACHE_SIZE` moved from `bundle.py`
- Fallback strings unified across all modules:
  - Function errors: `{!FUNCTION_NAME}` (was `{?FUNCTION_NAME}` or `{FUNCTION_NAME(...)}`)
  - Missing variables: `{$variable}` (unchanged but now uses constant)
  - Missing terms: `{-term}` (unchanged but now uses constant)
  - Missing messages: `{message}` (unchanged but now uses constant)
  - Invalid: `{???}` (unchanged but now uses constant)
- `should_inject_locale()` removed from `function_metadata` module; use `FunctionRegistry.should_inject_locale()`

### Added
- `fluent_function(inject_locale=True)` decorator for marking custom functions requiring locale injection
- `FunctionRegistry.should_inject_locale(ftl_name)` method for locale injection check
- `FunctionRegistry.get_expected_positional_args(ftl_name)` method for positional arg count
- `ftllexengine.constants` module with centralized configuration constants
- Fallback pattern constants: `FALLBACK_INVALID`, `FALLBACK_MISSING_MESSAGE`, `FALLBACK_MISSING_VARIABLE`, `FALLBACK_MISSING_TERM`, `FALLBACK_FUNCTION_ERROR`

### Changed
- `FunctionRegistry` now encapsulates locale injection logic (was in `function_metadata`)
- All depth/cache/size limits now reference `constants.py` as single source of truth

### Performance
- Cache key generation fast path: skips expensive conversion when all values are already hashable primitives

## [0.35.0] - 2025-12-27

### Added
- `SerializationDepthError` exception for AST nesting overflow during serialization
- `max_depth` parameter to `serialize()` and `FluentSerializer.serialize()` (default: 100)
- `DepthGuard` protection to serializer preventing stack overflow from deep ASTs
- `MAX_SERIALIZATION_DEPTH` constant in `syntax.serializer` module

### Changed
- `FluentValue` type now imported from canonical location in `function_bridge.py` (consolidated from duplicate in `cache.py`)
- Serializer recursive methods now track depth via `DepthGuard` for security

### Fixed
- Decimal exact variant matching: `Decimal('1.1')` now correctly matches `[1.1]` variant
  - Previously failed due to IEEE 754 float/Decimal comparison mismatch
  - Integer Decimals (`Decimal('1')`) were unaffected; fractional Decimals now work
- Boolean selector values no longer crash variant matching
  - `isinstance(False, int)` is `True` in Python, but `Decimal("False")` raises error
  - Booleans now explicitly excluded from numeric comparison path
- Duplicate `_FluentValue` type definition in `cache.py` consolidated to single source

### Security
- Serializer now raises `SerializationDepthError` instead of `RecursionError` on deep ASTs
- Prevents stack overflow from adversarially constructed ASTs passed to `serialize()`

## [0.34.0] - 2025-12-26

### Breaking Changes
- `FunctionSignature.param_mapping` type changed from `dict[str, str]` to `tuple[tuple[str, str], ...]` for full immutability
- `get_shared_registry()` now returns a frozen registry; calling `register()` raises `TypeError`

### Added
- `FunctionRegistry.freeze()` method to prevent further modifications
- `FunctionRegistry.frozen` property to check if registry is frozen
- `FunctionSignature` documentation in DOC_04_Runtime.md

### Changed
- `FluentSerializer` now escapes ALL control characters (codepoints < 0x20 and 0x7F) using `\uHHHH` format
- `FluentBundle.add_resource()` now logs syntax errors at WARNING level regardless of `source_path` presence
- `ReferenceExtractor.visit_MessageReference()` no longer calls `generic_visit()` (performance optimization)
- `FunctionRegistry.copy()` now explicitly documented to return unfrozen copy

### Fixed
- Mutable `param_mapping` dict in frozen `FunctionSignature` dataclass violated immutability protocol
- Shared registry singleton could be modified by external code, polluting global state
- Syntax errors hidden at DEBUG level when loading FTL from in-memory strings without source_path
- Unnecessary `generic_visit()` traversal on `MessageReference` nodes (leaf nodes in AST)
- Raw control characters passed through serializer StringLiteral output

## [0.33.0] - 2025-12-26

### Added
- `PARSE_CURRENCY_CODE_INVALID` diagnostic code for invalid ISO 4217 currency codes
- ISO 4217 currency code validation against CLDR data in `parse_currency()`
- Underscore parameter collision detection in `FunctionRegistry.register()`
- Era token stripping (`_strip_era()`) for date/datetime parsing compatibility
- Missing CLDR tokens to `_BABEL_TOKEN_MAP`: fractional seconds (S/SSS/SSSSSS), hour variants (k/kk/K/KK), timezone tokens (Z/ZZZZZ/x/xxxxx/z/zzzz)
- `DepthGuard` protection to `ReferenceExtractor` for stack overflow prevention
- `_get_node_fields()` method to `ASTVisitor` for cached field introspection

### Changed
- `FluentLocalization.add_function()` now preserves lazy bundle initialization
- `_get_currency_maps()` now returns frozenset of valid ISO 4217 codes for validation
- `parse_argument_expression()` now handles TermReference, FunctionReference, and inline_placeable per FTL spec
- Era tokens (G/GG/GGG/GGGG) now map to `None` and are stripped from input before parsing
- `ASTVisitor.generic_visit()` now uses cached fields per node type for performance

### Fixed
- `add_function()` no longer defeats lazy bundle loading by eagerly creating all bundles
- Currency parsing now rejects invalid ISO 4217 codes instead of accepting any 3-letter uppercase string
- Function registration now raises `ValueError` on underscore parameter collision (e.g., `_value` and `value` mapping to same FTL parameter)

### Performance
- `ASTVisitor.generic_visit()` field introspection reduced from O(n) per visit to O(1) via class-level caching

## [0.32.0] - 2025-12-25

### Added
- CLDR stand-alone month tokens (L/LL/LLL/LLLL) to Babel pattern mapping in `dates.py`
- CLDR stand-alone weekday tokens (c/cc/ccc/cccc) to Babel pattern mapping in `dates.py`
- CLDR era tokens (G/GG/GGG/GGGG) to Babel pattern mapping in `dates.py`
- `ResolutionContext.expression_guard` property returning `DepthGuard` for context manager use
- `get_system_locale(raise_on_failure=True)` parameter for deterministic error handling

### Changed
- Serializer now uses `\u0009` for tab characters per Fluent 1.0 spec escape sequence rules
- `ResolutionContext` refactored to use `DepthGuard` internally for expression depth tracking
- `FluentBundle.for_system_locale()` now delegates to `get_system_locale()` from `locale_utils`
- `IntrospectionVisitor` now uses `DepthGuard` for recursion protection
- `validate_resource()` now includes semantic validation (Pass 5) via `SemanticValidator`
- `format_number()` and `format_currency()` type hints now accept `Decimal` in addition to `int | float`

### Fixed
- Serializer escape sequences now strictly comply with Fluent 1.0 spec (only `\\`, `\"`, `\{`, `\uHHHH`, `\UHHHHHH` allowed)
- `FluentLocalization.add_resource` docstring now documents `FluentSyntaxError` exception

## [0.31.0] - 2025-12-24

### Added
- Unified `DepthGuard` context manager in `runtime.depth_guard` for recursion limiting
- `get_babel_locale()` cached Babel Locale retrieval in `locale_utils`
- `get_system_locale()` environment variable detection in `locale_utils`
- O(1) cycle detection in `ResolutionContext` via `_seen` set field
- Expression depth tracking in `ResolutionContext` with `enter_expression()`/`exit_expression()`
- `DiagnosticFormatter` service for centralized diagnostic output formatting (Rust-style, simple, JSON)
- `OutputFormat` enum for formatter output style selection
- `get_shared_registry()` for efficient FunctionRegistry sharing across bundles
- `LoadSummary`, `ResourceLoadResult`, `LoadStatus` for eager loading diagnostics in `FluentLocalization`
- `FluentLocalization.get_load_summary()` method for introspecting resource load results

### Changed
- Serializer now escapes literal braces per Fluent spec using `{"{"}` syntax
- Parser CRLF handling improved in junk recovery via `_skip_line_ending()` method
- Locale normalization now happens at system boundary using `normalize_locale()`
- `plural_rules.py` now uses cached `get_babel_locale()` for Babel Locale parsing
- `locale_context.py` normalizes cache keys for consistent BCP-47/POSIX handling
- `currency.py` normalizes locale before dictionary lookup
- `FluentBundle` now uses `get_shared_registry()` for default function registry (performance)
- `FluentLocalization` now tracks all resource load attempts for diagnostics

### Fixed
- Parser junk recovery now correctly handles CRLF line endings
- Number parsing now handles `OverflowError` for extremely large Decimal values
- Locale cache keys consistently normalized to prevent BCP-47 vs POSIX cache misses

### Removed
- Unused `deprecation.py` module and associated test files

## [0.30.0] - 2025-12-24

### Added
- `ValidationWarning.line` and `ValidationWarning.column` fields for IDE/LSP integration
- `ValidationWarning.format()` method for human-readable warning output with position info
- Cross-type cycle detection: message->term->message cycles now detected during validation
- Documentation of line ending support (LF/CRLF supported, CR-only not supported)

### Changed
- Deprecation warnings now use `DeprecationWarning` instead of `FutureWarning` (per Python convention)
- `CommentType`, `VariableContext`, `ReferenceKind`, `FunctionCategory` now use `StrEnum` (Python 3.11+)
- `FluentLocalization` docstring now correctly describes eager resource loading behavior
- Function not found hint now includes CURRENCY (was missing from "NUMBER, DATETIME" list)

### Fixed
- `Decimal` type now triggers plural category matching (was silently falling through to exact match only)
- Unified dependency graph for cycle detection now catches message<->term cycles
- Removed dead code `_validate_message_reference` method from `SemanticValidator`

## [0.29.1] - 2025-12-23

### Changed
- Replaced pip-based workflow with uv.

## [0.29.0] - 2025-12-23

### Added
- `LineOffsetCache` class for O(log n) position lookups after O(n) precomputation
- `SerializationValidationError` exception for AST validation during serialization
- `serialize(validate=True)` parameter to validate AST before serialization
- `canonicalize_cycle()` and `make_cycle_key()` functions for consistent cycle representation
- Parser documentation explaining lookahead patterns used in grammar rules

### Changed
- `FluentLocalization` now uses lazy bundle initialization (bundles created on first access)
- `_get_date_patterns()` and `_get_datetime_patterns()` now cached per locale for performance
- `_DATETIME_PARSE_STYLES` now includes "long" for consistency with `_DATE_PARSE_STYLES`
- `ValidationResult.format()` now includes `annotation.arguments` in output
- Cycle detection now preserves directional information (A->B->C distinct from A->C->B)
- Custom functions can now receive locale injection by setting `_ftl_requires_locale = True`
- Exception handling in `FluentBundle.format_pattern()` no longer swallows internal bugs
- Exception handling in `FunctionRegistry.call()` narrowed to `TypeError` and `ValueError` only
- `None` values in SelectExpression now consistently fall through to default variant

### Fixed
- Currency parsing now removes only the matched currency symbol, not all occurrences
- Thread safety documentation clarified for `FluentBundle` mutation methods
- Removed dead `LocaleValidationError` class (was never returned by any API)
- Term reference cycle detection now works correctly (was causing RecursionError)

### Performance
- Validation position computation reduced from O(M*N) to O(n + M log n)
- Date/datetime pattern generation cached per locale

## [0.28.1] - 2025-12-22

### Fixed
- Hypothesis health check failure in `test_current_returns_correct_character` by using `flatmap` to construct valid positions.

## [0.28.0] - 2025-12-22

### Changed
- Rebranded from FTLLexBuffer to FTLLexEngine, with a new repository to match the broader architectural vision.
- The changelog has been wiped clean. A lot has changed since the last release, but we're starting fresh.
- We're officially out of Alpha. Welcome to Beta.

[0.129.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.129.0
[0.128.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.128.0
[0.127.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.127.0
[0.126.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.126.0
[0.125.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.125.0
[0.124.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.124.0
[0.123.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.123.0
[0.122.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.122.0
[0.121.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.121.0
[0.120.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.120.0
[0.119.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.119.0
[0.118.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.118.0
[0.117.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.117.0
[0.116.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.116.0
[0.115.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.115.0
[0.114.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.114.0
[0.113.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.113.0
[0.112.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.112.0
[0.111.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.111.0
[0.110.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.110.0
[0.109.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.109.0
[0.108.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.108.0
[0.107.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.107.0
[0.106.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.106.0
[0.105.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.105.0
[0.104.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.104.0
[0.103.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.103.0
[0.102.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.102.0
[0.101.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.101.0
[0.100.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.100.0
[0.99.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.99.0
[0.98.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.98.0
[0.97.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.97.0
[0.96.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.96.0
[0.95.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.95.0
[0.94.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.94.0
[0.93.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.93.0
[0.92.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.92.0
[0.91.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.91.0
[0.90.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.90.0
[0.89.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.89.0
[0.88.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.88.0
[0.87.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.87.0
[0.86.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.86.0
[0.85.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.85.0
[0.84.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.84.0
[0.83.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.83.0
[0.82.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.82.0
[0.81.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.81.0
[0.80.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.80.0
[0.79.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.79.0
[0.78.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.78.0
[0.77.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.77.0
[0.76.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.76.0
[0.75.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.75.0
[0.74.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.74.0
[0.73.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.73.0
[0.72.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.72.0
[0.71.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.71.0
[0.70.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.70.0
[0.69.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.69.0
[0.68.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.68.0
[0.67.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.67.0
[0.66.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.66.0
[0.65.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.65.0
[0.64.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.64.0
[0.63.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.63.0
[0.62.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.62.0
[0.61.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.61.0
[0.60.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.60.0
[0.59.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.59.0
[0.58.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.58.0
[0.57.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.57.0
[0.56.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.56.0
[0.55.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.55.0
[0.54.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.54.0
[0.53.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.53.0
[0.52.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.52.0
[0.51.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.51.0
[0.50.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.50.0
[0.49.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.49.0
[0.48.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.48.0
[0.47.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.47.0
[0.46.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.46.0
[0.45.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.45.0
[0.44.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.44.0
[0.43.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.43.0
[0.42.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.42.0
[0.41.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.41.0
[0.40.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.40.0
[0.39.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.39.0
[0.38.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.38.0
[0.37.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.37.0
[0.36.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.36.0
[0.35.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.35.0
[0.34.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.34.0
[0.33.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.33.0
[0.32.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.32.0
[0.31.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.31.0
[0.30.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.30.0
[0.29.1]: https://github.com/resoltico/ftllexengine/releases/tag/v0.29.1
[0.29.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.29.0
[0.28.1]: https://github.com/resoltico/ftllexengine/releases/tag/v0.28.1
[0.28.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.28.0
