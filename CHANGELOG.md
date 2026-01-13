<!--
RETRIEVAL_HINTS:
  keywords: [changelog, release notes, version history, breaking changes, migration, what's new]
  answers: [what changed in version, breaking changes, release history, version changes]
  related: [docs/MIGRATION.md]
-->
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
