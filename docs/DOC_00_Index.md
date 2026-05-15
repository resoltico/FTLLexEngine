---
afad: "4.0"
version: "0.167.0"
domain: INDEX
updated: "2026-05-15"
route:
  keywords: [api index, docs index, documentation map, routing, FluentBundle, FluentLocalization, parse_ftl, FunctionRegistry, FrozenFluentError, introspection, detect_cycles, entry_dependency_set]
  questions: ["where is a symbol documented?", "which file documents the runtime APIs?", "which file documents locale parsing, introspection, and analysis APIs?", "where are syntax, parsing, diagnostics, and dependency-graph references?", "where is the complete index of Markdown docs under docs/?"]
---

# FTLLexEngine Documentation And API Index

<!--
Premise: Readers need one complete navigation page, not only a symbol router.
Reason: This file now does two jobs clearly: it inventories every Markdown document in `docs/`
and it routes public symbols to the reference file that defines them.
-->

## Documentation Map

### Start Here

| File | Purpose |
|:-----|:--------|
| [DOC_00_Index.md](DOC_00_Index.md) | This file: complete docs map plus API routing table |
| [QUICK_REFERENCE.md](QUICK_REFERENCE.md) | Short recipes for common tasks |
| [WORKFLOW_TOUR.md](WORKFLOW_TOUR.md) | End-to-end usage examples |
| [TERMINOLOGY.md](TERMINOLOGY.md) | Definitions for project vocabulary |
| [MIGRATION.md](MIGRATION.md) | Upgrade notes and breaking-change guidance |

### Core Reference

| File | Purpose |
|:-----|:--------|
| [DOC_01_Core.md](DOC_01_Core.md) | Core entry points such as `FluentBundle`, `FluentLocalization`, and resource loading |
| [DOC_02_Types.md](DOC_02_Types.md) | Public semantic and support types |
| [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md) | Fluent AST node types |
| [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | Fluent AST expression nodes |
| [DOC_03_Parsing.md](DOC_03_Parsing.md) | FTL parsing, serialization, and validation APIs |
| [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | Locale-aware parsing APIs for numbers, dates, and currency |

### Runtime, Introspection, And Diagnostics

| File | Purpose |
|:-----|:--------|
| [DOC_04_Runtime.md](DOC_04_Runtime.md) | Runtime formatting, cache, function, and bundle support APIs |
| [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | Locale utilities, constants, and runtime helpers |
| [DOC_04_Introspection.md](DOC_04_Introspection.md) | Message, locale, currency, and territory introspection APIs |
| [DOC_04_Analysis.md](DOC_04_Analysis.md) | Dependency-graph and cycle-analysis APIs |
| [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | Diagnostics, validation results, and formatter APIs |
| [DOC_05_Errors.md](DOC_05_Errors.md) | Error and integrity exception types |

### Guides

| File | Purpose |
|:-----|:--------|
| [CUSTOM_FUNCTIONS_GUIDE.md](CUSTOM_FUNCTIONS_GUIDE.md) | Registering and using custom Fluent functions |
| [LOCALE_GUIDE.md](LOCALE_GUIDE.md) | Locale normalization, fallback, and orchestration behavior |
| [PARSING_GUIDE.md](PARSING_GUIDE.md) | Practical locale-aware parsing examples |
| [TYPE_HINTS_GUIDE.md](TYPE_HINTS_GUIDE.md) | Type-checking expectations and examples |
| [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md) | Resource and message-schema validation workflow |
| [THREAD_SAFETY.md](THREAD_SAFETY.md) | Thread-safety guarantees and concurrency model |
| [DATA_INTEGRITY_ARCHITECTURE.md](DATA_INTEGRITY_ARCHITECTURE.md) | Integrity model, cache evidence, and fail-closed boundaries |

### Tooling And Operations

| File | Purpose |
|:-----|:--------|
| [DEVELOPER_DEVCONTAINER.md](DEVELOPER_DEVCONTAINER.md) | Canonical contributor container workflow |
| [DOC_06_Testing.md](DOC_06_Testing.md) | Verification commands, docs validation, and example execution |
| [FUZZING_GUIDE.md](FUZZING_GUIDE.md) | Fuzzing overview and workflows |
| [FUZZING_GUIDE_ATHERIS.md](FUZZING_GUIDE_ATHERIS.md) | Atheris-specific fuzzing workflow |
| [FUZZING_GUIDE_HYPOFUZZ.md](FUZZING_GUIDE_HYPOFUZZ.md) | HypoFuzz-specific workflow |
| [RELEASE_PROTOCOL.md](RELEASE_PROTOCOL.md) | Release, packaging, and publication procedure |

## Routing Table

| Symbol | File | Section |
|:-------|:-----|:--------|
| `FluentBundle` | [DOC_01_Core.md](DOC_01_Core.md) | `FluentBundle` |
| `AsyncFluentBundle` | [DOC_01_Core.md](DOC_01_Core.md) | `AsyncFluentBundle` |
| `FluentLocalization` | [DOC_01_Core.md](DOC_01_Core.md) | `FluentLocalization` |
| `LocalizationBootConfig` | [DOC_01_Core.md](DOC_01_Core.md) | `LocalizationBootConfig` |
| `PathResourceLoader` | [DOC_01_Core.md](DOC_01_Core.md) | `PathResourceLoader` |
| `ResourceLoader` | [DOC_01_Core.md](DOC_01_Core.md) | `ResourceLoader` |
| `LoadStatus` | [DOC_01_Core.md](DOC_01_Core.md) | `LoadStatus` |
| `LoadSummary` | [DOC_01_Core.md](DOC_01_Core.md) | `LoadSummary` |
| `ResourceLoadResult` | [DOC_01_Core.md](DOC_01_Core.md) | `ResourceLoadResult` |
| `FallbackInfo` | [DOC_01_Core.md](DOC_01_Core.md) | `FallbackInfo` |
| `LocalizationCacheStats` | [DOC_01_Core.md](DOC_01_Core.md) | `LocalizationCacheStats` |
| `UNLIMITED` | [DOC_02_Types.md](DOC_02_Types.md) | `UNLIMITED` |
| `UnlimitedLimit` | [DOC_02_Types.md](DOC_02_Types.md) | `UnlimitedLimit` |
| `FluentNumber` | [DOC_02_Types.md](DOC_02_Types.md) | `FluentNumber` |
| `FluentValue` | [DOC_02_Types.md](DOC_02_Types.md) | `FluentValue` |
| `ParseResult` | [DOC_02_Types.md](DOC_02_Types.md) | `ParseResult` |
| `LocaleCode` | [DOC_02_Types.md](DOC_02_Types.md) | `LocaleCode` |
| `MessageId` | [DOC_02_Types.md](DOC_02_Types.md) | `MessageId` |
| `ResourceId` | [DOC_02_Types.md](DOC_02_Types.md) | `ResourceId` |
| `FTLSource` | [DOC_02_Types.md](DOC_02_Types.md) | `FTLSource` |
| `CurrencyCode` | [DOC_02_Types.md](DOC_02_Types.md) | `CurrencyCode` |
| `TerritoryCode` | [DOC_02_Types.md](DOC_02_Types.md) | `TerritoryCode` |
| `Span` | [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md) | `Span` |
| `Annotation` | [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md) | `Annotation` |
| `Identifier` | [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md) | `Identifier` |
| `Resource` | [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md) | `Resource` |
| `Message` | [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md) | `Message` |
| `Term` | [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md) | `Term` |
| `Attribute` | [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md) | `Attribute` |
| `Comment` | [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md) | `Comment` |
| `Junk` | [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md) | `Junk` |
| `Pattern` | [DOC_02_SyntaxTypes.md](DOC_02_SyntaxTypes.md) | `Pattern` |
| `TextElement` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `TextElement` |
| `Placeable` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `Placeable` |
| `SelectExpression` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `SelectExpression` |
| `Variant` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `Variant` |
| `StringLiteral` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `StringLiteral` |
| `NumberLiteral` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `NumberLiteral` |
| `VariableReference` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `VariableReference` |
| `MessageReference` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `MessageReference` |
| `TermReference` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `TermReference` |
| `FunctionReference` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `FunctionReference` |
| `CallArguments` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `CallArguments` |
| `NamedArgument` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `NamedArgument` |
| `Entry` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `Entry` |
| `PatternElement` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `PatternElement` |
| `Expression` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `Expression` |
| `SelectorExpression` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `SelectorExpression` |
| `FTLLiteral` | [DOC_02_SyntaxExpressions.md](DOC_02_SyntaxExpressions.md) | `FTLLiteral` |
| `MessageVariableValidationResult` | [DOC_02_Types.md](DOC_02_Types.md) | `MessageVariableValidationResult` |
| `MessageIntrospection` | [DOC_02_Types.md](DOC_02_Types.md) | `MessageIntrospection` |
| `VariableInfo` | [DOC_02_Types.md](DOC_02_Types.md) | `VariableInfo` |
| `FunctionCallInfo` | [DOC_02_Types.md](DOC_02_Types.md) | `FunctionCallInfo` |
| `ReferenceInfo` | [DOC_02_Types.md](DOC_02_Types.md) | `ReferenceInfo` |
| `TerritoryInfo` | [DOC_02_Types.md](DOC_02_Types.md) | `TerritoryInfo` |
| `CurrencyInfo` | [DOC_02_Types.md](DOC_02_Types.md) | `CurrencyInfo` |
| `CommentType` | [DOC_02_Types.md](DOC_02_Types.md) | `CommentType` |
| `VariableContext` | [DOC_02_Types.md](DOC_02_Types.md) | `VariableContext` |
| `ReferenceKind` | [DOC_02_Types.md](DOC_02_Types.md) | `ReferenceKind` |
| `parse_ftl` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `parse_ftl` |
| `parse_stream_ftl` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `parse_stream_ftl` |
| `serialize_ftl` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `serialize_ftl` |
| `validate_resource` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `validate_resource` |
| `FluentParserV1` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `FluentParserV1` |
| `parse` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `parse` |
| `parse_stream` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `parse_stream` |
| `serialize` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `serialize` |
| `Cursor` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `Cursor` |
| `ftllexengine.syntax.ParseResult` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `ftllexengine.syntax.ParseResult` |
| `ParseError` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `ParseError` |
| `SerializationValidationError` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `SerializationValidationError` |
| `SerializationDepthError` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `SerializationDepthError` |
| `ASTVisitor` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `ASTVisitor` |
| `ASTTransformer` | [DOC_03_Parsing.md](DOC_03_Parsing.md) | `ASTTransformer` |
| `parse_decimal` | [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | `parse_decimal` |
| `parse_fluent_number` | [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | `parse_fluent_number` |
| `parse_date` | [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | `parse_date` |
| `parse_datetime` | [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | `parse_datetime` |
| `parse_currency` | [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | `parse_currency` |
| `is_valid_decimal` | [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | `is_valid_decimal` |
| `is_valid_date` | [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | `is_valid_date` |
| `is_valid_datetime` | [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | `is_valid_datetime` |
| `is_valid_currency` | [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | `is_valid_currency` |
| `clear_date_caches` | [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | `clear_date_caches` |
| `clear_currency_caches` | [DOC_03_LocaleParsing.md](DOC_03_LocaleParsing.md) | `clear_currency_caches` |
| `CacheConfig` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `CacheConfig` |
| `FunctionRegistry` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `FunctionRegistry` |
| `fluent_function` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `fluent_function` |
| `create_default_registry` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `create_default_registry` |
| `get_shared_registry` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `get_shared_registry` |
| `number_format` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `number_format` |
| `datetime_format` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `datetime_format` |
| `currency_format` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `currency_format` |
| `select_plural_category` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `select_plural_category` |
| `make_fluent_number` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `make_fluent_number` |
| `clear_module_caches` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `clear_module_caches` |
| `CacheDebugLogEntry` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `CacheDebugLogEntry` |
| `CacheIntegrityEvent` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `CacheIntegrityEvent` |
| `CacheIntegrityEventKind` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `CacheIntegrityEventKind` |
| `detect_cycles` | [DOC_04_Analysis.md](DOC_04_Analysis.md) | `detect_cycles` |
| `entry_dependency_set` | [DOC_04_Analysis.md](DOC_04_Analysis.md) | `entry_dependency_set` |
| `make_cycle_key` | [DOC_04_Analysis.md](DOC_04_Analysis.md) | `make_cycle_key` |
| `normalize_locale` | [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | `normalize_locale` |
| `get_system_locale` | [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | `get_system_locale` |
| `require_locale_code` | [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | `require_locale_code` |
| `require_currency_code` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `require_currency_code` |
| `require_territory_code` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `require_territory_code` |
| `is_valid_currency_code` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `is_valid_currency_code` |
| `is_valid_territory_code` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `is_valid_territory_code` |
| `get_currency_decimal_digits` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `get_currency_decimal_digits` |
| `get_cldr_version` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `get_cldr_version` |
| `__version__` | [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | `__version__` |
| `__fluent_spec_version__` | [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | `__fluent_spec_version__` |
| `__spec_url__` | [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | `__spec_url__` |
| `__recommended_encoding__` | [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | `__recommended_encoding__` |
| `require_date` | [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | `require_date` |
| `require_datetime` | [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | `require_datetime` |
| `require_fluent_number` | [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | `require_fluent_number` |
| `validate_message_variables` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `validate_message_variables` |
| `introspect_message` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `introspect_message` |
| `extract_variables` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `extract_variables` |
| `extract_references` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `extract_references` |
| `extract_references_by_attribute` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `extract_references_by_attribute` |
| `clear_introspection_cache` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `clear_introspection_cache` |
| `get_territory` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `get_territory` |
| `get_currency` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `get_currency` |
| `list_territories` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `list_territories` |
| `list_currencies` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `list_currencies` |
| `get_territory_currencies` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `get_territory_currencies` |
| `clear_iso_cache` | [DOC_04_Introspection.md](DOC_04_Introspection.md) | `clear_iso_cache` |
| `FrozenFluentError` | [DOC_05_Errors.md](DOC_05_Errors.md) | `FrozenFluentError` |
| `ErrorCategory` | [DOC_05_Errors.md](DOC_05_Errors.md) | `ErrorCategory` |
| `ParseTypeLiteral` | [DOC_05_Errors.md](DOC_05_Errors.md) | `ParseTypeLiteral` |
| `FrozenErrorContext` | [DOC_05_Errors.md](DOC_05_Errors.md) | `FrozenErrorContext` |
| `BabelImportError` | [DOC_05_Errors.md](DOC_05_Errors.md) | `BabelImportError` |
| `ErrorTemplate` | [DOC_05_Errors.md](DOC_05_Errors.md) | `ErrorTemplate` |
| `DataIntegrityError` | [DOC_05_Errors.md](DOC_05_Errors.md) | `DataIntegrityError` |
| `IntegrityContext` | [DOC_05_Errors.md](DOC_05_Errors.md) | `IntegrityContext` |
| `CacheCorruptionError` | [DOC_05_Errors.md](DOC_05_Errors.md) | `CacheCorruptionError` |
| `ImmutabilityViolationError` | [DOC_05_Errors.md](DOC_05_Errors.md) | `ImmutabilityViolationError` |
| `IntegrityCheckFailedError` | [DOC_05_Errors.md](DOC_05_Errors.md) | `IntegrityCheckFailedError` |
| `FormattingIntegrityError` | [DOC_05_Errors.md](DOC_05_Errors.md) | `FormattingIntegrityError` |
| `SyntaxIntegrityError` | [DOC_05_Errors.md](DOC_05_Errors.md) | `SyntaxIntegrityError` |
| `WriteConflictError` | [DOC_05_Errors.md](DOC_05_Errors.md) | `WriteConflictError` |
| `ValidationResult` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `ValidationResult` |
| `ValidationError` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `ValidationError` |
| `ValidationWarning` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `ValidationWarning` |
| `ParserAnnotation` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `ParserAnnotation` |
| `WarningSeverity` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `WarningSeverity` |
| `Diagnostic` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `Diagnostic` |
| `DiagnosticCode` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `DiagnosticCode` |
| `DiagnosticFormatter` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `DiagnosticFormatter` |
| `OutputFormat` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `OutputFormat` |
| `SourceSpan` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `SourceSpan` |
| `scripts/validate_docs.py` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/validate_docs.py` |
| `scripts/validate_version.py` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/validate_version.py` |
| `scripts/validate-devcontainer.sh` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/validate-devcontainer.sh` |
| `scripts/run_examples.py` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/run_examples.py` |
| `check.sh` | [DOC_06_Testing.md](DOC_06_Testing.md) | `check.sh` |
| `scripts/lint.sh` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/lint.sh` |
| `scripts/test.sh` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/test.sh` |
| `scripts/fuzz_hypofuzz.sh` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/fuzz_hypofuzz.sh` |
| `scripts/fuzz_atheris.sh` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/fuzz_atheris.sh` |
| `pytest.mark.fuzz` | [DOC_06_Testing.md](DOC_06_Testing.md) | `pytest.mark.fuzz` |
