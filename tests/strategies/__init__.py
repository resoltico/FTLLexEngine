"""Hypothesis strategies for FTLLexEngine property-based testing.

This package provides reusable strategies for generating test data
across multiple test modules. Strategies are organized by domain:

- ftl: FTL syntax, AST nodes, and parser-related strategies
- fiscal: FiscalCalendar, FiscalDelta, and date strategies
- iso: Territory codes, currency codes, and locale strategies
- diagnostics: Diagnostic codes, errors, validation, and formatter strategies

Usage:
    from tests.strategies import ftl_identifiers, territory_codes
    from tests.strategies.fiscal import reasonable_dates, fiscal_deltas
    from tests.strategies.iso import territory_codes, currency_codes
    from tests.strategies.ftl import ftl_message_nodes, ftl_patterns
    from tests.strategies.diagnostics import diagnostics, source_spans

Event-Emitting Strategies (HypoFuzz-Optimized):
    These strategies emit hypothesis.event() calls for coverage-guided fuzzing:
    - ftl_chaos_source, ftl_pathological_nesting, ftl_multiline_chaos_source
    - ftl_boundary_depth_placeables, ftl_reference_placeables
    - ftl_circular_references, ftl_semantically_broken, ftl_invalid_ftl
    - ftl_financial_numbers, ftl_attribute_nodes
    - fiscal_delta_by_magnitude, date_by_boundary, fiscal_calendar_by_type
    - currency_by_decimals, territory_by_region, locale_by_script
    - source_spans, frozen_error_contexts, diagnostics, diagnostic_codes
    - error_categories, validation_errors, validation_warnings
    - validation_results
"""

# Diagnostics strategies
from .diagnostics import (
    annotation_nodes,
    diagnostic_codes,
    diagnostics,
    error_categories,
    frozen_error_contexts,
    source_spans,
    validation_errors,
    validation_results,
    validation_warnings,
)

# Fiscal calendar strategies
from .fiscal import (
    date_by_boundary,
    fiscal_boundary_crossing_pair,
    fiscal_calendar_by_type,
    fiscal_calendars,
    fiscal_delta_by_magnitude,
    fiscal_deltas,
    fiscal_periods,
    month_end_policies,
    month_end_policy_with_event,
    reasonable_dates,
)
from .ftl import (
    # Constants
    FTL_IDENTIFIER_FIRST_CHARS,
    FTL_IDENTIFIER_REST_CHARS,
    FTL_RESERVED_KEYWORDS,
    FTL_SAFE_CHARS,
    IDENTIFIER_PARTS,
    UNICODE_CHARS,
    # String strategies (for parsing)
    any_ast_entry,
    any_ast_pattern_element,
    blank_line,
    blank_lines_sequence,
    camel_case_identifiers,
    deeply_nested_message_chain,
    deeply_nested_placeables,
    deeply_nested_select,
    fluent_numbers,
    ftl_attribute_nodes,
    ftl_boundary_depth_messages,
    ftl_boundary_depth_placeables,
    ftl_boundary_identifiers,
    ftl_chaos_source,
    ftl_chaos_text,
    ftl_circular_references,
    ftl_comment_nodes,
    ftl_comments,
    ftl_deep_placeables,
    ftl_deeply_nested_selects,
    ftl_empty_pattern_messages,
    ftl_financial_numbers,
    ftl_function_names,
    ftl_identifier_boundary,
    ftl_identifiers,
    ftl_identifiers_with_keywords,
    ftl_invalid_bad_identifier_start,
    ftl_invalid_double_equals,
    ftl_invalid_ftl,
    ftl_invalid_missing_value,
    ftl_invalid_select_no_default,
    ftl_invalid_unclosed_placeable,
    ftl_invalid_unterminated_string,
    ftl_junk_nodes,
    ftl_message_nodes,
    ftl_message_with_whitespace_edge_cases,
    ftl_messages_with_placeables,
    ftl_multiline_chaos_source,
    ftl_multiline_messages,
    ftl_number_literals,
    ftl_numbers,
    ftl_pathological_nesting,
    ftl_patterns,
    ftl_placeables,
    ftl_reference_placeables,
    ftl_resource_with_whitespace_chaos,
    ftl_resources,
    ftl_select_expressions,
    ftl_select_expressions_with_number_keys,
    ftl_select_with_whitespace_variants,
    ftl_semantically_broken,
    ftl_simple_messages,
    ftl_simple_text,
    ftl_string_literals,
    ftl_term_nodes,
    ftl_terms,
    ftl_text_elements,
    ftl_unicode_stress_text,
    ftl_unicode_text,
    ftl_valid_with_injected_error,
    ftl_variable_references,
    ftl_variants,
    message_with_many_attributes,
    mixed_line_endings_text,
    mutate_identifier,
    mutate_message,
    mutate_pattern,
    mutate_text_element,
    pattern_with_leading_blank_lines,
    placeable_with_whitespace,
    resolver_edge_case_args,
    resolver_mixed_args,
    resolver_number_args,
    resolver_string_args,
    snake_case_identifiers,
    swap_variant_keys,
    text_with_tabs,
    text_with_trailing_whitespace,
    variable_indent_multiline_pattern,
    variant_key_with_whitespace,
    wide_resource,
)

# ISO standards strategies
from .iso import (
    all_alpha2_codes,
    all_alpha3_codes,
    currency_by_decimals,
    currency_codes,
    four_decimal_currencies,
    language_codes,
    locale_by_script,
    locale_codes,
    locale_formatted_decimals,
    locale_formatted_numbers,
    malformed_locales,
    territory_by_region,
    territory_codes,
    three_decimal_currencies,
    two_decimal_currencies,
    zero_decimal_currencies,
)

# ruff: noqa: RUF022 - __all__ organized by category for readability
__all__ = [
    # FTL Constants
    "FTL_IDENTIFIER_FIRST_CHARS",
    "FTL_IDENTIFIER_REST_CHARS",
    "FTL_RESERVED_KEYWORDS",
    "FTL_SAFE_CHARS",
    "IDENTIFIER_PARTS",
    "UNICODE_CHARS",
    # FTL String strategies
    "ftl_identifiers",
    "ftl_identifiers_with_keywords",
    "ftl_identifier_boundary",
    "ftl_simple_text",
    "ftl_unicode_text",
    "ftl_unicode_stress_text",
    "ftl_simple_messages",
    "ftl_messages_with_placeables",
    "ftl_terms",
    "ftl_comments",
    "ftl_numbers",
    "ftl_financial_numbers",
    # FTL Identifier case strategies
    "snake_case_identifiers",
    "camel_case_identifiers",
    # FTL AST strategies
    "ftl_text_elements",
    "ftl_variable_references",
    "ftl_number_literals",
    "ftl_string_literals",
    "ftl_attribute_nodes",
    "ftl_placeables",
    "ftl_deep_placeables",
    "ftl_reference_placeables",
    "ftl_patterns",
    "ftl_variants",
    "ftl_select_expressions",
    "ftl_select_expressions_with_number_keys",
    "ftl_message_nodes",
    "ftl_comment_nodes",
    "ftl_junk_nodes",
    "ftl_term_nodes",
    "ftl_resources",
    "any_ast_entry",
    "any_ast_pattern_element",
    # FTL Edge case strategies
    "ftl_boundary_identifiers",
    "ftl_empty_pattern_messages",
    "ftl_multiline_messages",
    # FTL Recursive strategies
    "ftl_deeply_nested_selects",
    # FTL AST mutation strategies
    "mutate_identifier",
    "mutate_text_element",
    "mutate_pattern",
    "mutate_message",
    "swap_variant_keys",
    # FTL Resolver argument strategies
    "resolver_string_args",
    "resolver_number_args",
    "resolver_mixed_args",
    "resolver_edge_case_args",
    # FTL Deeply nested AST strategies
    "deeply_nested_placeables",
    "deeply_nested_message_chain",
    "deeply_nested_select",
    "wide_resource",
    "message_with_many_attributes",
    # FTL Whitespace strategies
    "blank_line",
    "blank_lines_sequence",
    "text_with_trailing_whitespace",
    "text_with_tabs",
    "mixed_line_endings_text",
    "variant_key_with_whitespace",
    "placeable_with_whitespace",
    "variable_indent_multiline_pattern",
    "pattern_with_leading_blank_lines",
    "ftl_message_with_whitespace_edge_cases",
    "ftl_select_with_whitespace_variants",
    "ftl_resource_with_whitespace_chaos",
    # FTL Negative oracle strategies
    "ftl_invalid_select_no_default",
    "ftl_invalid_unclosed_placeable",
    "ftl_invalid_unterminated_string",
    "ftl_invalid_bad_identifier_start",
    "ftl_invalid_double_equals",
    "ftl_invalid_missing_value",
    "ftl_invalid_ftl",
    "ftl_valid_with_injected_error",
    # Function bridge strategies
    "ftl_function_names",
    "fluent_numbers",
    # FTL HypoFuzz-optimized event-emitting strategies
    "ftl_chaos_source",
    "ftl_chaos_text",
    "ftl_multiline_chaos_source",
    "ftl_pathological_nesting",
    "ftl_boundary_depth_placeables",
    "ftl_boundary_depth_messages",
    "ftl_circular_references",
    "ftl_semantically_broken",
    # Fiscal strategies
    "fiscal_calendars",
    "fiscal_deltas",
    "month_end_policies",
    "reasonable_dates",
    # Fiscal HypoFuzz-optimized event-emitting strategies
    "fiscal_delta_by_magnitude",
    "date_by_boundary",
    "fiscal_calendar_by_type",
    "month_end_policy_with_event",
    # ISO strategies
    "territory_codes",
    "all_alpha2_codes",
    "currency_codes",
    "all_alpha3_codes",
    "zero_decimal_currencies",
    "two_decimal_currencies",
    "three_decimal_currencies",
    "four_decimal_currencies",
    "locale_codes",
    "language_codes",
    "malformed_locales",
    # ISO HypoFuzz-optimized event-emitting strategies
    "currency_by_decimals",
    "territory_by_region",
    "locale_by_script",
    # Locale-formatted number strategies
    "locale_formatted_numbers",
    "locale_formatted_decimals",
    # Fiscal additional strategies
    "fiscal_periods",
    "fiscal_boundary_crossing_pair",
    # Diagnostics strategies
    "source_spans",
    "frozen_error_contexts",
    "error_categories",
    "diagnostic_codes",
    "diagnostics",
    "annotation_nodes",
    # Diagnostics HypoFuzz-optimized event-emitting strategies
    "validation_errors",
    "validation_warnings",
    "validation_results",
]
