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

[Unreleased]: https://github.com/resoltico/ftllexengine/compare/v0.35.0...HEAD
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
