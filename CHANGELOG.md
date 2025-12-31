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
