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

[0.31.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.31.0
[0.30.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.30.0
[0.29.1]: https://github.com/resoltico/ftllexengine/releases/tag/v0.29.1
[0.29.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.29.0
[0.28.1]: https://github.com/resoltico/ftllexengine/releases/tag/v0.28.1
[0.28.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.28.0
