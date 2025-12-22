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

## [0.28.1] - 2025-12-22

### Fixed
- Hypothesis health check failure in `test_current_returns_correct_character` by using `flatmap` to construct valid positions.

## [0.28.0] - 2025-12-22

### Changed
- Rebranded from FTLLexBuffer to FTLLexEngine, with a new repository to match the broader architectural vision.
- The changelog has been wiped clean. A lot has changed since the last release, but we're starting fresh.
- We're officially out of Alpha. Welcome to Beta.

[0.28.1]: https://github.com/resoltico/ftllexengine/releases/tag/v0.28.1
[0.28.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.28.0
