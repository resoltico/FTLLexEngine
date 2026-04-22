---
afad: "3.5"
version: "0.163.0"
domain: INDEX
updated: "2026-04-22"
route:
  keywords: [api index, routing, FluentBundle, FluentLocalization, parse_ftl, FunctionRegistry, FrozenFluentError, introspection]
  questions: ["where is a symbol documented?", "which file documents the runtime APIs?", "which file documents locale parsing and introspection APIs?", "where are syntax, parsing, and diagnostics references?"]
---

# FTLLexEngine API Reference Index

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
| `CacheAuditLogEntry` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `CacheAuditLogEntry` |
| `WriteLogEntry` | [DOC_04_Runtime.md](DOC_04_Runtime.md) | `WriteLogEntry` |
| `detect_cycles` | [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md) | `detect_cycles` |
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
| `WarningSeverity` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `WarningSeverity` |
| `Diagnostic` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `Diagnostic` |
| `DiagnosticCode` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `DiagnosticCode` |
| `DiagnosticFormatter` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `DiagnosticFormatter` |
| `OutputFormat` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `OutputFormat` |
| `SourceSpan` | [DOC_05_Diagnostics.md](DOC_05_Diagnostics.md) | `SourceSpan` |
| `scripts/validate_docs.py` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/validate_docs.py` |
| `scripts/validate_version.py` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/validate_version.py` |
| `scripts/run_examples.py` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/run_examples.py` |
| `check.sh` | [DOC_06_Testing.md](DOC_06_Testing.md) | `check.sh` |
| `scripts/lint.sh` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/lint.sh` |
| `scripts/test.sh` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/test.sh` |
| `scripts/fuzz_hypofuzz.sh` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/fuzz_hypofuzz.sh` |
| `scripts/fuzz_atheris.sh` | [DOC_06_Testing.md](DOC_06_Testing.md) | `scripts/fuzz_atheris.sh` |
| `pytest.mark.fuzz` | [DOC_06_Testing.md](DOC_06_Testing.md) | `pytest.mark.fuzz` |

## Guide Links

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
- [CUSTOM_FUNCTIONS_GUIDE.md](CUSTOM_FUNCTIONS_GUIDE.md)
- [LOCALE_GUIDE.md](LOCALE_GUIDE.md)
- [PARSING_GUIDE.md](PARSING_GUIDE.md)
- [RELEASE_PROTOCOL.md](RELEASE_PROTOCOL.md)
- [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md)
