# mypy: ignore-errors
from tests.runtime_bundle_cases import (
    MAX_LOCALE_LENGTH_HARD_LIMIT,
    MAX_SOURCE_SIZE,
    Any,
    CacheConfig,
    FluentBundle,
    FormattingIntegrityError,
    ResourceConflictIntegrityError,
    SyntaxIntegrityError,
    ValidationError,
    logging,
    patch,
    pytest,
)


class TestBundlePropertyAccessors:
    """Test all property accessors for complete coverage."""

    def test_locale_property_returns_configured_locale(self) -> None:
        """locale property returns the canonical locale code."""
        bundle = FluentBundle("lv_LV")
        assert bundle.locale == "lv_lv"

        bundle_ar = FluentBundle("ar_EG")
        assert bundle_ar.locale == "ar_eg"

    def test_use_isolating_property_true(self) -> None:
        """use_isolating property returns True when enabled."""
        bundle = FluentBundle("en", use_isolating=True)
        assert bundle.use_isolating is True

    def test_use_isolating_property_false(self) -> None:
        """use_isolating property returns False when disabled."""
        bundle = FluentBundle("en", use_isolating=False)
        assert bundle.use_isolating is False

    def test_strict_property_returns_configured_value(self) -> None:
        """strict property returns the strict mode boolean."""
        assert FluentBundle("en", strict=True).strict is True
        assert FluentBundle("en", strict=False).strict is False
        assert FluentBundle("en").strict is True

    def test_cache_enabled_property(self) -> None:
        """cache_enabled property reflects configuration."""
        assert FluentBundle("en", cache=CacheConfig()).cache_enabled is True
        assert FluentBundle("en").cache_enabled is False

    def test_cache_config_size_property(self) -> None:
        """cache_config.size returns configured maximum."""
        bundle = FluentBundle("en", cache=CacheConfig(size=500))
        assert bundle.cache_config is not None
        assert bundle.cache_config.size == 500

    def test_cache_usage_property_tracks_entries(self) -> None:
        """cache_usage property tracks current cached entries."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg1 = Hello\nmsg2 = World")

        assert bundle.cache_usage == 0
        bundle.format_pattern("msg1")
        assert bundle.cache_usage == 1
        bundle.format_pattern("msg2")
        assert bundle.cache_usage == 2

    def test_cache_usage_returns_zero_when_disabled(self) -> None:
        """cache_usage returns 0 when caching is disabled."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")
        assert bundle.cache_usage == 0

    def test_cache_write_once_config(self) -> None:
        """cache_config.write_once reflects configured boolean."""
        on = FluentBundle("en", cache=CacheConfig(write_once=True))
        assert on.cache_config is not None
        assert on.cache_config.write_once is True
        off = FluentBundle("en", cache=CacheConfig(write_once=False))
        assert off.cache_config is not None
        assert off.cache_config.write_once is False

    def test_cache_enable_debug_log_config(self) -> None:
        """cache_config.enable_debug_log reflects configured boolean."""
        on = FluentBundle("en", cache=CacheConfig(enable_debug_log=True))
        assert on.cache_config is not None
        assert on.cache_config.enable_debug_log is True
        off = FluentBundle("en", cache=CacheConfig(enable_debug_log=False))
        assert off.cache_config is not None
        assert off.cache_config.enable_debug_log is False

    def test_cache_max_debug_entries_config(self) -> None:
        """cache_config.max_debug_entries reflects configured maximum."""
        bundle = FluentBundle(
            "en", cache=CacheConfig(max_debug_entries=5000)
        )
        assert bundle.cache_config is not None
        assert bundle.cache_config.max_debug_entries == 5000

    def test_cache_max_entry_payload_bytes_config(self) -> None:
        """cache_config.max_entry_payload_bytes reflects configured maximum."""
        bundle = FluentBundle(
            "en", cache=CacheConfig(max_entry_payload_bytes=8000)
        )
        assert bundle.cache_config is not None
        assert bundle.cache_config.max_entry_payload_bytes == 8000

    def test_cache_max_errors_per_entry_config(self) -> None:
        """cache_config.max_errors_per_entry reflects configured maximum."""
        bundle = FluentBundle(
            "en", cache=CacheConfig(max_errors_per_entry=25)
        )
        assert bundle.cache_config is not None
        assert bundle.cache_config.max_errors_per_entry == 25

    def test_max_source_size_property(self) -> None:
        """max_source_size property returns configured or default value."""
        assert FluentBundle("en", max_source_size=500_000).max_source_size == 500_000
        assert FluentBundle("en").max_source_size == MAX_SOURCE_SIZE

    def test_max_nesting_depth_property(self) -> None:
        """max_nesting_depth property returns configured or default value."""
        assert FluentBundle("en", max_nesting_depth=50).max_nesting_depth == 50
        assert FluentBundle("en").max_nesting_depth == 100


# =============================================================================
# Locale Validation
# =============================================================================


class TestBundleLocaleValidation:
    """Test locale code validation in __init__."""

    def test_rejects_invalid_characters(self) -> None:
        """Locale with special characters raises ValueError."""
        with pytest.raises(ValueError, match=r"Invalid locale: 'en@invalid'"):
            FluentBundle("en@invalid")

    def test_rejects_spaces(self) -> None:
        """Locale with spaces raises ValueError."""
        with pytest.raises(ValueError, match=r"Invalid locale: 'en US'"):
            FluentBundle("en US")

    def test_rejects_non_ascii(self) -> None:
        """Locale with non-ASCII characters raises ValueError."""
        with pytest.raises(ValueError, match=r"Invalid locale: 'ën_FR'"):
            FluentBundle("\u00ebn_FR")

    def test_accepts_hyphen_separator(self) -> None:
        """Locale with hyphen separator accepted."""
        assert FluentBundle("en-US").locale == "en_us"

    def test_accepts_underscore_separator(self) -> None:
        """Locale with underscore separator accepted."""
        assert FluentBundle("en_US").locale == "en_us"

    def test_exceeding_max_length_rejected(self) -> None:
        """Locale exceeding MAX_LOCALE_LENGTH_HARD_LIMIT raises ValueError."""
        long_locale = "a" * (MAX_LOCALE_LENGTH_HARD_LIMIT + 1)
        with pytest.raises(ValueError, match="locale exceeds maximum length"):
            FluentBundle(long_locale)

    def test_exceeding_max_length_shows_truncated(self) -> None:
        """Error message includes truncated locale and actual length."""
        long_locale = "X" * (MAX_LOCALE_LENGTH_HARD_LIMIT + 100)
        with pytest.raises(
            ValueError, match="locale exceeds maximum length"
        ) as exc_info:
            FluentBundle(long_locale)
        error_msg = str(exc_info.value)
        assert long_locale[:50] in error_msg
        assert str(len(long_locale)) in error_msg


# =============================================================================
# Special Methods (__repr__)
# =============================================================================


class TestBundleSpecialMethods:
    """Test __repr__ for complete coverage."""

    def test_repr_shows_locale_and_counts(self) -> None:
        """__repr__ returns string with locale and message/term counts."""
        bundle = FluentBundle("lv_LV")
        repr_str = repr(bundle)
        assert "FluentBundle" in repr_str
        assert "lv_lv" in repr_str
        assert "messages=0" in repr_str
        assert "terms=0" in repr_str

    def test_repr_reflects_counts_after_adding_resources(self) -> None:
        """__repr__ shows accurate counts after adding resources."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg1 = Hello\nmsg2 = World\n-brand = Firefox")
        repr_str = repr(bundle)
        assert "messages=2" in repr_str
        assert "terms=1" in repr_str


# =============================================================================
# for_system_locale Factory Method
# =============================================================================


class TestBundleForSystemLocale:
    """Test for_system_locale classmethod."""

    def test_creates_bundle_with_detected_locale(self) -> None:
        """for_system_locale creates bundle with system locale."""
        with patch(
            "ftllexengine.runtime.bundle_lifecycle.get_system_locale",
            return_value="en_US",
        ):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "en_us"

    def test_passes_configuration_parameters(self) -> None:
        """for_system_locale passes all configuration parameters."""
        with patch(
            "ftllexengine.runtime.bundle_lifecycle.get_system_locale",
            return_value="de_DE",
        ):
            bundle = FluentBundle.for_system_locale(
                use_isolating=False,
                cache=CacheConfig(size=2000),
                strict=True,
                max_source_size=500_000,
            )
            assert bundle.locale == "de_de"
            assert bundle.use_isolating is False
            assert bundle.cache_enabled is True
            assert bundle.cache_config is not None
            assert bundle.cache_config.size == 2000
            assert bundle.strict is True
            assert bundle.max_source_size == 500_000

    def test_raises_when_locale_unavailable(self) -> None:
        """for_system_locale raises RuntimeError when locale unavailable."""
        with patch(
            "ftllexengine.runtime.bundle_lifecycle.get_system_locale",
            side_effect=RuntimeError("Cannot determine system locale"),
        ), pytest.raises(RuntimeError, match="Cannot determine"):
            FluentBundle.for_system_locale()

    def test_falls_back_to_env_vars_when_getlocale_fails(self) -> None:
        """for_system_locale uses env vars when getlocale() returns None."""
        with patch("locale.getlocale", return_value=(None, None)), patch.dict(
            "os.environ", {"LC_ALL": "de_DE"}, clear=False
        ):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "de_de"

    def test_tries_lc_messages_when_lc_all_missing(self) -> None:
        """for_system_locale tries LC_MESSAGES when LC_ALL not set."""
        with patch("locale.getlocale", return_value=(None, None)), patch.dict(
            "os.environ", {"LC_MESSAGES": "fr_FR"}, clear=True
        ):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "fr_fr"

    def test_tries_lang_when_others_missing(self) -> None:
        """for_system_locale tries LANG as final fallback."""
        with patch("locale.getlocale", return_value=(None, None)), patch.dict(
            "os.environ", {"LANG": "es_ES"}, clear=True
        ):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "es_es"

    def test_raises_when_no_locale_found(self) -> None:
        """for_system_locale raises RuntimeError with no locale."""
        with (
            patch("locale.getlocale", return_value=(None, None)),
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(
                RuntimeError, match="Could not determine system locale"
            ),
        ):
            FluentBundle.for_system_locale()

    def test_normalizes_posix_format(self) -> None:
        """for_system_locale strips encoding suffix and normalizes."""
        with patch("locale.getlocale", return_value=("en_US.UTF-8", None)):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "en_us"
            assert "UTF-8" not in bundle.locale

    def test_handles_locale_without_encoding(self) -> None:
        """for_system_locale handles locale without encoding suffix."""
        with patch("locale.getlocale", return_value=("pl_PL", None)):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "pl_pl"


# =============================================================================
# Resource Management (add_resource, comments, terms)
# =============================================================================


class TestBundleResourceManagement:
    """Test add_resource edge cases, comment handling, term attributes."""

    def test_add_resource_with_comments(self) -> None:
        """Comments are parsed but not registered as messages."""
        bundle = FluentBundle("en")
        ftl_source = (
            "# Standalone comment\nmsg1 = Hello\n\n"
            "## Section comment\nmsg2 = World\n\n"
            "### Resource comment\n-term = Value\n"
        )
        junk = bundle.add_resource(ftl_source)
        assert len(junk) == 0
        assert bundle.has_message("msg1")
        assert bundle.has_message("msg2")
        assert len(bundle.get_message_ids()) == 2

    def test_standalone_comment_only_resource(self) -> None:
        """Resource containing only comments is valid."""
        bundle = FluentBundle("en")
        junk = bundle.add_resource(
            "# Comment\n## Section\n### Resource\n"
        )
        assert len(junk) == 0
        assert len(bundle.get_message_ids()) == 0

    def test_consecutive_comments(self) -> None:
        """Multiple consecutive comments hit Comment->loop branch."""
        bundle = FluentBundle("en")
        ftl = "## Section 1\n## Section 2\n### Resource\nmsg = Value\n"
        junk = bundle.add_resource(ftl)
        assert len(junk) == 0
        assert bundle.has_message("msg")

    def test_message_without_value_only_attributes(self) -> None:
        """Message with no value, only attributes, is registered."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("msg =\n    .attr1 = Value 1\n    .attr2 = Value 2\n")
        assert bundle.has_message("msg")

    def test_term_with_multiple_attributes(self) -> None:
        """Term with attributes is registered successfully."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            "-brand = Firefox\n    .gender = masculine\n"
            "    .case = nominative\n"
        )
        assert bundle is not None

    def test_add_resource_clears_cache(self) -> None:
        """add_resource clears cache when enabled."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("first = First")
        bundle.format_pattern("first")
        assert bundle.get_cache_stats()["size"] > 0  # type: ignore[index]
        bundle.add_resource("second = Second")
        assert bundle.get_cache_stats()["size"] == 0  # type: ignore[index]

    def test_duplicate_terms_are_rejected(self, caplog: Any) -> None:
        """Duplicate term definitions fail closed inside one resource."""
        bundle = FluentBundle("en")
        with pytest.raises(ResourceConflictIntegrityError, match="-brand"):
            bundle.add_resource("-brand = Firefox\n-brand = Chrome\n")
        assert caplog.records == []

    def test_multiple_duplicate_terms_are_rejected(self, caplog: Any) -> None:
        """Multiple duplicate terms fail as one audited conflict set."""
        bundle = FluentBundle("en")
        with pytest.raises(ResourceConflictIntegrityError, match="-brand, -version"):
            bundle.add_resource(
                "-brand = First\n-version = First\n"
                "-brand = Second\n-version = Second\n"
            )
        assert caplog.records == []

    def test_comments_with_debug_logging(self, caplog: Any) -> None:
        """Comments are processed at debug level without errors."""
        caplog.set_level(logging.DEBUG)
        bundle = FluentBundle("en")
        ftl = (
            "# Comment before term\n"
            "-brand = Firefox\n"
        )
        junk = bundle.add_resource(ftl)
        assert len(junk) == 0


# =============================================================================
# Type Validation (add_resource, validate_resource, format_pattern)
# =============================================================================


class TestBundleTypeValidation:
    """Test type validation at API boundaries."""

    def test_add_resource_rejects_bytes(self) -> None:
        """add_resource raises TypeError for bytes with decode suggestion."""
        bundle = FluentBundle("en")
        with pytest.raises(TypeError, match=r"source must be str, not bytes"):
            bundle.add_resource(b"msg = Hello")  # type: ignore[arg-type]
        with pytest.raises(TypeError, match=r"source.decode\('utf-8'\)"):
            bundle.add_resource(b"msg = Hello")  # type: ignore[arg-type]

    def test_add_resource_rejects_int(self) -> None:
        """add_resource raises TypeError for non-string types."""
        bundle = FluentBundle("en")
        with pytest.raises(TypeError, match=r"source must be str"):
            bundle.add_resource(42)  # type: ignore[arg-type]

    def test_validate_resource_rejects_bytes(self) -> None:
        """validate_resource raises TypeError for bytes."""
        bundle = FluentBundle("en")
        with pytest.raises(TypeError, match=r"source must be str, not bytes"):
            bundle.validate_resource(b"msg = Hello")  # type: ignore[arg-type]

    def test_format_pattern_empty_message_id(self) -> None:
        """format_pattern with empty message ID returns fallback."""
        bundle = FluentBundle("en", strict=False)
        result, errors = bundle.format_pattern("")
        assert result == "{???}"
        assert len(errors) == 1

    def test_format_pattern_invalid_args_type(self) -> None:
        """format_pattern with non-Mapping args returns fallback."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Hello")
        result, errors = bundle.format_pattern("msg", [])  # type: ignore[arg-type]
        assert result == "{???}"
        assert len(errors) == 1

    def test_format_pattern_invalid_attribute_type(self) -> None:
        """format_pattern with non-string attribute returns fallback."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Hello")
        result, errors = bundle.format_pattern(
            "msg", {}, attribute=123  # type: ignore[arg-type]
        )
        assert result == "{???}"
        assert len(errors) == 1

    def test_strict_mode_raises_on_empty_message_id(self) -> None:
        """format_pattern in strict mode raises on empty message ID."""
        bundle = FluentBundle("en", strict=True)
        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern("")

    def test_strict_mode_raises_on_invalid_args_type(self) -> None:
        """format_pattern in strict mode raises on invalid args type."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Hello")
        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern("msg", [])  # type: ignore[arg-type]

    def test_strict_mode_raises_on_invalid_attribute_type(self) -> None:
        """format_pattern in strict mode raises on invalid attribute type."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Hello")
        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern(
                "msg", {}, attribute=123  # type: ignore[arg-type]
            )


# =============================================================================
# Strict Mode (syntax errors, formatting errors, caching)
# =============================================================================


class TestBundleStrictMode:
    """Test strict mode syntax and formatting error handling."""

    def test_raises_syntax_integrity_error_on_junk(self) -> None:
        """Strict mode raises SyntaxIntegrityError for junk entries."""
        bundle = FluentBundle("en", strict=True)
        with pytest.raises(
            SyntaxIntegrityError, match=r"Strict mode: .* syntax error"
        ):
            bundle.add_resource("msg = \n!!invalid!!")

    def test_error_includes_source_path(self) -> None:
        """Strict mode error includes source_path when provided."""
        bundle = FluentBundle("en", strict=True)
        with pytest.raises(
            SyntaxIntegrityError, match=r"locales/en/messages.ftl"
        ) as exc_info:
            bundle.add_resource(
                "msg = \n!!invalid!!",
                source_path="locales/en/messages.ftl",
            )
        assert exc_info.value.source_path == "locales/en/messages.ftl"

    def test_error_truncates_long_summary(self) -> None:
        """Strict mode truncates to first 3 junk entries."""
        bundle = FluentBundle("en", strict=True)
        invalid_ftl = (
            "msg1 =\n!!e1!!\nmsg2 =\n!!e2!!\n"
            "msg3 =\n!!e3!!\nmsg4 =\n!!e4!!\n"
        )
        with pytest.raises(
            SyntaxIntegrityError, match=r"and \d+ more"
        ):
            bundle.add_resource(invalid_ftl)

    def test_does_not_mutate_bundle_on_error(self) -> None:
        """Strict mode does not partially populate bundle on syntax error."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg1 = Hello")
        assert len(bundle.get_message_ids()) == 1

        with pytest.raises(SyntaxIntegrityError):
            bundle.add_resource("msg2 = World\n!!invalid!!")
        assert len(bundle.get_message_ids()) == 1

    def test_formatting_integrity_error_on_missing_var(self) -> None:
        """Strict mode raises FormattingIntegrityError for missing vars."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Hello { $name }")
        with pytest.raises(FormattingIntegrityError, match=r"Strict mode"):
            bundle.format_pattern("msg", {})

    def test_formatting_error_includes_message_id(self) -> None:
        """Strict mode formatting error includes message ID."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("greeting = Hello { $name }")
        with pytest.raises(
            FormattingIntegrityError, match=r"greeting"
        ) as exc_info:
            bundle.format_pattern("greeting", {})
        assert exc_info.value.message_id == "greeting"

    def test_formatting_error_truncates_multiple_errors(self) -> None:
        """Strict mode error truncates to first 3 formatting errors."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = { $a } { $b } { $c } { $d }")
        with pytest.raises(FormattingIntegrityError, match=r"and \d+ more"):
            bundle.format_pattern("msg", {})


# =============================================================================
# Validation (circular refs, undefined refs, duplicates, syntax errors)
# =============================================================================


class TestBundleValidation:
    """Test validate_resource warning and error detection."""

    def test_detects_circular_message_refs(self) -> None:
        """Circular message references generate warnings."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource(
            "msg1 = { msg2 }\nmsg2 = { msg1 }\n"
        )
        assert any(
            "Circular message reference" in w.message
            for w in result.warnings
        )

    def test_detects_self_referencing_message(self) -> None:
        """Message referencing itself detected as circular."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("msg = { msg }\n")
        assert len(result.warnings) > 0

    def test_detects_circular_term_refs(self) -> None:
        """Circular term references generate warnings."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource(
            "-term1 = { -term2 }\n-term2 = { -term1 }\n"
        )
        assert any(
            "Circular term reference" in w.message
            for w in result.warnings
        )

    def test_detects_self_referencing_term(self) -> None:
        """Term referencing itself detected as circular."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("-term = { -term }\n")
        assert len(result.warnings) > 0

    def test_detects_term_attribute_circular_ref(self) -> None:
        """Circular reference in term attribute detected."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource(
            "-term = Value\n    .attr = { -term.attr }\n"
        )
        assert len(result.warnings) > 0

    def test_detects_nested_term_circular_ref(self) -> None:
        """Three-way circular term reference detected."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource(
            "-t1 = { -t2 }\n-t2 = { -t3 }\n-t3 = { -t1 }\n"
        )
        assert len(result.warnings) > 0

    def test_detects_undefined_message_ref(self) -> None:
        """Undefined message reference generates warning."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("msg = { undefined }\n")
        assert any(
            "undefined" in w.message.lower() for w in result.warnings
        )

    def test_detects_undefined_term_ref_from_message(self) -> None:
        """Message referencing undefined term generates warning."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("msg = { -undefined_term }\n")
        assert len(result.warnings) > 0

    def test_detects_undefined_term_ref_from_term(self) -> None:
        """Term referencing undefined term generates warning."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource("-term-a = { -term-b }\n")
        assert any(
            "undefined term '-term-b'" in w.message
            for w in result.warnings
        )

    def test_detects_undefined_message_ref_from_term(self) -> None:
        """Term referencing undefined message generates warning."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("-term = { undefined_msg }\n")
        assert len(result.warnings) > 0

    def test_term_referencing_defined_message_no_warning(self) -> None:
        """Term referencing a defined message does not warn."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource(
            "greeting = Hello\n-term = { greeting }\n"
        )
        assert not any(
            "undefined message" in w.message for w in result.warnings
        )

    def test_detects_duplicate_term_id(self) -> None:
        """Duplicate term ID generates warning."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource(
            "-brand = Firefox\n-brand = Chrome\n"
        )
        assert any(
            "Duplicate term ID" in w.message for w in result.warnings
        )

    def test_message_without_value_validates(self) -> None:
        """Message with only attributes validates successfully."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource("msg =\n    .attr = Value\n")
        assert result.is_valid

    def test_term_with_attributes_validates(self) -> None:
        """Term with attributes validates successfully."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource(
            "-term = Base\n    .attr1 = A1\n    .attr2 = A2\n"
        )
        assert result.is_valid

    def test_handles_critical_syntax_error(self) -> None:
        """Critical syntax errors produce validation errors."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("msg = {{ invalid")
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_critical_error_returns_validation_error(self) -> None:
        """Critical errors are ValidationError instances."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource("msg = {{ broken")
        assert all(
            isinstance(e, ValidationError) for e in result.errors
        )

    def test_integration_all_warning_types(self) -> None:
        """Resource with all warning types produces correct warnings."""
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl = (
            "msg-dup = First\nmsg-dup = Second\n"
            "-term-dup = First\n-term-dup = Second\n"
            "circ-a = { circ-b }\ncirc-b = { circ-a }\n"
            "-tc-a = { -tc-b }\n-tc-b = { -tc-a }\n"
            "msg-undef = { missing-msg }\n"
            "-term-undef = { -missing-term }\n"
            "msg-attrs =\n    .attr = Value\n"
            "-term-attrs = Base\n    .attr = Attribute\n"
        )
        result = bundle.validate_resource(ftl)
        warnings = " ".join(w.message for w in result.warnings)
        assert "Duplicate message ID" in warnings
        assert "Duplicate term ID" in warnings
        assert "Circular message reference" in warnings
        assert "Circular term reference" in warnings
        assert "undefined message" in warnings
        assert "undefined term" in warnings

    def test_message_without_value_no_crash(self) -> None:
        """Validation doesn't crash on empty-value message."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("empty =\n")
        assert result is not None


# =============================================================================
# Cache Management
# =============================================================================


class TestBundleCacheManagement:
    """Test clear_cache, get_cache_stats, cache invalidation."""

    def test_clear_cache_when_enabled(self) -> None:
        """clear_cache removes all cached format results."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg1 = Hello\nmsg2 = World")
        bundle.format_pattern("msg1")
        bundle.format_pattern("msg2")
        assert bundle.cache_usage == 2
        bundle.clear_cache()
        assert bundle.cache_usage == 0

    def test_clear_cache_when_disabled(self) -> None:
        """clear_cache succeeds when cache is disabled."""
        bundle = FluentBundle("en")
        bundle.clear_cache()
        assert bundle.get_cache_stats() is None

    def test_clear_cache_resets_to_empty(self) -> None:
        """clear_cache resets the format cache to empty state."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = Hello")
        bundle.clear_cache()
        assert bundle.cache_usage == 0

    def test_get_cache_stats_returns_dict_when_enabled(self) -> None:
        """get_cache_stats returns dict with hits/misses when enabled."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg", {})
        bundle.format_pattern("msg", {})
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_get_cache_stats_returns_none_when_disabled(self) -> None:
        """get_cache_stats returns None when caching is disabled."""
        bundle = FluentBundle("en")
        assert bundle.get_cache_stats() is None

    def test_format_pattern_caches_result(self) -> None:
        """format_pattern caches results when cache enabled."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = Hello")
        result1, _ = bundle.format_pattern("msg")
        stats1 = bundle.get_cache_stats()
        assert stats1 is not None
        assert stats1["misses"] == 1
        result2, _ = bundle.format_pattern("msg")
        stats2 = bundle.get_cache_stats()
        assert stats2 is not None
        assert stats2["hits"] == 1
        assert result1 == result2


# -- Introspection (variables, introspect_message/term, has_attribute) -------

