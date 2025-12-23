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

[0.29.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.29.0
[0.28.1]: https://github.com/resoltico/ftllexengine/releases/tag/v0.28.1
[0.28.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.28.0
