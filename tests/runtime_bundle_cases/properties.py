# mypy: ignore-errors
from tests.runtime_bundle_cases import (
    CacheConfig,
    ErrorCategory,
    FluentBundle,
    FormattingIntegrityError,
    FunctionRegistry,
    SyntaxIntegrityError,
    assume,
    create_default_registry,
    event,
    example,
    given,
    logging,
    normalize_locale,
    pytest,
    st,
    validate_resource,
)


class TestBundleHypothesisProperties:
    """Property-based tests for FluentBundle boundary exploration."""

    # --- Init type validation (from test_bundle_100pct_final_coverage) ---

    @given(
        invalid_functions=st.one_of(
            st.dictionaries(
                st.text(min_size=1, max_size=10), st.integers()
            ),
            st.lists(st.text()),
            st.integers(),
            st.text(),
            st.none(),
        )
    )
    def test_init_rejects_non_function_registry(
        self, invalid_functions: object
    ) -> None:
        """FluentBundle.__init__ rejects non-FunctionRegistry functions."""
        if invalid_functions is None:
            event("type=NoneType_valid")
            return

        type_name = type(invalid_functions).__name__
        event(f"type={type_name}")

        with pytest.raises(
            TypeError,
            match="functions must be FunctionRegistry, not",
        ):
            FluentBundle(
                "en_US", functions=invalid_functions  # type: ignore[arg-type]
            )

    @example(invalid_functions={"NUMBER": lambda x: x})
    @example(invalid_functions=[])
    @example(invalid_functions=42)
    @example(invalid_functions="not_a_registry")
    @given(
        invalid_functions=st.one_of(
            st.dictionaries(
                st.text(min_size=1, max_size=5),
                st.integers(),
                min_size=1,
            ),
            st.lists(st.integers(), min_size=1),
        )
    )
    def test_init_type_error_message_includes_type_name(
        self, invalid_functions: object
    ) -> None:
        """TypeError message includes actual type name."""
        type_name = type(invalid_functions).__name__
        event(f"type={type_name}")

        with pytest.raises(TypeError) as exc_info:
            FluentBundle(
                "en_US", functions=invalid_functions  # type: ignore[arg-type]
            )

        assert type_name in str(exc_info.value)
        assert "FunctionRegistry" in str(exc_info.value)
        assert "create_default_registry" in str(exc_info.value)

    # --- Property getters (from test_bundle_100pct_final_coverage) ---

    @given(
        max_expansion_size=st.integers(
            min_value=1000, max_value=10_000_000
        ),
        locale=st.sampled_from(["en_US", "de_DE", "lv_LV", "ja_JP"]),
    )
    def test_max_expansion_size_preserved(
        self, max_expansion_size: int, locale: str
    ) -> None:
        """max_expansion_size property returns configured value."""
        if max_expansion_size < 10_000:
            event("boundary=small")
        elif max_expansion_size > 1_000_000:
            event("boundary=large")
        else:
            event("boundary=medium")

        bundle = FluentBundle(
            locale, max_expansion_size=max_expansion_size
        )
        assert bundle.max_expansion_size == max_expansion_size

    @given(
        locale=st.sampled_from(["en", "de", "lv", "pl", "ar", "ja"]),
        provide_custom_registry=st.booleans(),
    )
    def test_function_registry_preserved(
        self, locale: str, provide_custom_registry: bool
    ) -> None:
        """function_registry property returns valid registry."""
        if provide_custom_registry:
            event("registry_type=custom")
            custom_registry = create_default_registry()
            bundle = FluentBundle(locale, functions=custom_registry)
        else:
            event("registry_type=shared")
            bundle = FluentBundle(locale)

        registry = bundle.function_registry
        assert isinstance(registry, FunctionRegistry)
        assert "NUMBER" in registry

    # --- Comment handling (from test_bundle_100pct_final_coverage) ---

    @given(
        num_comments=st.integers(min_value=1, max_value=10),
        comment_style=st.sampled_from(
            ["single", "double", "triple"]
        ),
    )
    def test_comments_handled_correctly(
        self, num_comments: int, comment_style: str
    ) -> None:
        """Comment entries handled during resource registration."""
        event(f"comment_count={num_comments}")
        event(f"comment_style={comment_style}")

        marker = {"single": "#", "double": "##", "triple": "###"}[
            comment_style
        ]
        lines = [f"{marker} Comment {i}" for i in range(num_comments)]
        lines.extend(["", "msg = Hello"])

        bundle = FluentBundle("en_US")
        junk = bundle.add_resource("\n".join(lines))
        assert len(junk) == 0
        assert bundle.has_message("msg")

    @example(num_standalone=1)
    @example(num_standalone=3)
    @example(num_standalone=10)
    @given(num_standalone=st.integers(min_value=1, max_value=20))
    def test_comments_do_not_create_junk(
        self, num_standalone: int
    ) -> None:
        """Comments are skipped without creating Junk entries."""
        event(f"standalone_comments={num_standalone}")

        lines = ["### Section Header"]
        lines.extend(
            f"# Comment line {i}" for i in range(num_standalone)
        )
        lines.extend(["", "message = Value", "## Trailing comment"])

        bundle = FluentBundle("en_US")
        junk = bundle.add_resource("\n".join(lines))
        assert len(junk) == 0
        assert bundle.has_message("message")

    # --- Strict mode cache interaction ---
    # (from test_bundle_100pct_final_coverage)

    @given(
        locale=st.sampled_from(["en", "de", "lv", "pl"]),
        missing_var_name=st.text(
            alphabet=st.characters(
                min_codepoint=ord("a"), max_codepoint=ord("z")
            ),
            min_size=1,
            max_size=20,
        ),
    )
    def test_strict_mode_raises_on_cached_error(
        self, locale: str, missing_var_name: str
    ) -> None:
        """Strict mode raises FormattingIntegrityError on cached errors."""
        bundle = FluentBundle(
            locale, strict=True, cache=CacheConfig()
        )
        bundle.add_resource(
            f"msg = Hello {{ ${missing_var_name} }}"
        )

        with pytest.raises(FormattingIntegrityError) as exc1:
            bundle.format_pattern("msg", {})

        event("cache_hit_type=error")
        assert exc1.value.message_id == "msg"
        assert len(exc1.value.fluent_errors) == 1
        assert (
            exc1.value.fluent_errors[0].category
            == ErrorCategory.REFERENCE
        )

        with pytest.raises(FormattingIntegrityError) as exc2:
            bundle.format_pattern("msg", {})
        assert exc2.value.message_id == "msg"

    @given(
        locale=st.sampled_from(["en_US", "de_DE", "lv_LV"]),
        message_text=st.text(
            alphabet=st.characters(
                min_codepoint=ord("A"),
                max_codepoint=ord("z"),
                blacklist_categories=("Cc", "Cs"),
            ),
            min_size=1,
            max_size=50,
        ),
    )
    def test_strict_mode_cache_hit_without_errors(
        self, locale: str, message_text: str
    ) -> None:
        """Strict mode cached success result returns normally."""
        safe = "".join(
            c for c in message_text if c.isprintable() and c not in "{}#"
        ).strip()
        if not safe:
            safe = "Hello"

        bundle = FluentBundle(
            locale, strict=True, cache=CacheConfig()
        )
        bundle.add_resource(f"msg = {safe}")

        r1, e1 = bundle.format_pattern("msg")
        assert r1 == safe
        assert e1 == ()

        event("cache_hit_type=success")

        r2, e2 = bundle.format_pattern("msg")
        assert r2 == safe
        assert e2 == ()

    # --- Configuration preservation properties ---
    # (from test_bundle_complete_final_coverage, events added)

    @given(
        st.text(
            alphabet=st.sampled_from(["a", "b", "c", "_", "-"]),
            min_size=1,
            max_size=50,
        )
    )
    def test_valid_locale_accepted(self, locale: str) -> None:
        """Valid locale formats are accepted by FluentBundle."""
        if not locale or not locale[0].isalnum():
            event("outcome=filtered")
            return

        try:
            bundle = FluentBundle(locale)
            event("outcome=accepted")
            assert bundle.locale == normalize_locale(locale)
        except ValueError:
            event("outcome=rejected")

    @given(st.booleans())
    def test_use_isolating_preserved(
        self, use_isolating: bool
    ) -> None:
        """use_isolating configuration is preserved."""
        kind = "isolating" if use_isolating else "non_isolating"
        event(f"outcome={kind}")
        bundle = FluentBundle("en", use_isolating=use_isolating)
        assert bundle.use_isolating == use_isolating

    @given(st.booleans())
    def test_strict_mode_preserved(self, strict: bool) -> None:
        """strict mode configuration is preserved."""
        kind = "strict" if strict else "lenient"
        event(f"outcome={kind}")
        bundle = FluentBundle("en", strict=strict)
        assert bundle.strict == strict

    @given(st.integers(min_value=1, max_value=10000))
    def test_cache_config_size_preserved(self, cache_size: int) -> None:
        """cache_config.size is preserved from CacheConfig constructor."""
        if cache_size < 100:
            event("boundary=small")
        elif cache_size < 5000:
            event("boundary=medium")
        else:
            event("boundary=large")
        bundle = FluentBundle("en", cache=CacheConfig(size=cache_size))
        assert bundle.cache_config is not None
        assert bundle.cache_config.size == cache_size

    # --- Validation properties (from test_bundle_coverage, events added) ---

    @given(
        term_name=st.from_regex(
            r"[a-z][a-z0-9-]{0,10}", fullmatch=True
        )
    )
    def test_duplicate_term_generates_warning(
        self, term_name: str
    ) -> None:
        """Duplicate term IDs always generate warnings."""
        event("outcome=duplicate_warned")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl = f"-{term_name} = First\n-{term_name} = Second\n"
        result = bundle.validate_resource(ftl)
        assert any(
            "Duplicate term ID" in w.message for w in result.warnings
        )

    @given(
        term_a=st.from_regex(
            r"[a-z][a-z0-9-]{0,10}", fullmatch=True
        ),
        term_b=st.from_regex(
            r"[a-z][a-z0-9-]{0,10}", fullmatch=True
        ),
    )
    def test_undefined_term_ref_generates_warning(
        self, term_a: str, term_b: str
    ) -> None:
        """Undefined term references always generate warnings."""
        assume(term_a != term_b)
        event("outcome=undefined_warned")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl = f"-{term_a} = {{ -{term_b} }}"
        result = bundle.validate_resource(ftl)
        assert any(
            f"undefined term '-{term_b}'" in w.message
            for w in result.warnings
        )


# ============================================================================
# LOCALE VALIDATION AND BUNDLE INTEGRATION COVERAGE
# ============================================================================


class TestLocaleValidationAsciiOnly:
    """Locale codes must be ASCII alphanumeric with underscore or hyphen separators."""

    def test_valid_ascii_locales_accepted(self) -> None:
        """Valid ASCII locale codes are accepted without error."""
        valid_locales = [
            "en",
            "en_US",
            "en-US",
            "de_DE",
            "lv_LV",
            "zh_Hans_CN",
            "pt_BR",
            "ja_JP",
            "ar_EG",
        ]
        for locale in valid_locales:
            bundle = FluentBundle(locale)
            assert bundle.locale == normalize_locale(locale)

    def test_unicode_locale_rejected(self) -> None:
        """Locale codes with non-ASCII characters raise ValueError."""
        invalid_locales = [
            "\xe9_FR",
            "\u65e5\u672c\u8a9e",
            "en_\xfc",
            "\xe4\xf6\xfc",
        ]
        for locale in invalid_locales:
            with pytest.raises(ValueError, match="must be ASCII alphanumeric"):
                FluentBundle(locale)

    def test_empty_locale_rejected(self) -> None:
        """Empty locale code raises ValueError."""
        with pytest.raises(ValueError, match="locale cannot be blank"):
            FluentBundle("")

    def test_invalid_format_rejected(self) -> None:
        """Invalid locale code formats raise ValueError."""
        invalid_formats = [
            "_en",
            "en_",
            "en__US",
            "en US",
            "en.US",
            "en@US",
        ]
        for locale in invalid_formats:
            with pytest.raises(ValueError, match=r"Invalid locale:"):
                FluentBundle(locale)

    @given(
        st.builds(
            lambda first, rest: first + rest,
            first=st.text(
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
                min_size=1,
                max_size=1,
            ),
            rest=st.text(
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                min_size=0,
                max_size=9,
            ),
        )
    )
    def test_ascii_alphanumeric_input_is_canonicalized_or_rejected(self, locale: str) -> None:
        """PROPERTY: ASCII locale-like input either canonicalizes or fails explicitly."""
        event(f"locale_len={len(locale)}")
        try:
            bundle = FluentBundle(locale)
        except ValueError:
            with pytest.raises(ValueError, match=r"Unknown locale identifier|Invalid locale format"):
                FluentBundle(locale)
            event("outcome=rejected")
        else:
            assert bundle.locale == normalize_locale(locale)
            event("outcome=accepted")


class TestBundleOverwriteWarning:
    """Overwriting an existing message or term in add_resource logs a WARNING."""

    def test_message_overwrite_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Overwriting a message logs a warning with the message ID."""
        bundle = FluentBundle("en")

        with caplog.at_level(logging.WARNING):
            bundle.add_resource("greeting = Hello")
            bundle.add_resource("greeting = Goodbye")

        warning_messages = [
            record.message for record in caplog.records
            if record.levelno == logging.WARNING
        ]
        assert any("Overwriting existing message 'greeting'" in msg for msg in warning_messages)

    def test_term_overwrite_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Overwriting a term logs a warning with the term ID."""
        bundle = FluentBundle("en")

        with caplog.at_level(logging.WARNING):
            bundle.add_resource("-brand = Acme")
            bundle.add_resource("-brand = NewCorp")

        warning_messages = [
            record.message for record in caplog.records
            if record.levelno == logging.WARNING
        ]
        assert any("Overwriting existing term '-brand'" in msg for msg in warning_messages)

    def test_no_warning_for_new_entries(self, caplog: pytest.LogCaptureFixture) -> None:
        """No overwrite warning when adding distinct entries."""
        bundle = FluentBundle("en")

        with caplog.at_level(logging.WARNING):
            bundle.add_resource("greeting = Hello")
            bundle.add_resource("farewell = Goodbye")

        overwrite_warnings = [
            record.message for record in caplog.records
            if record.levelno == logging.WARNING and "Overwriting" in record.message
        ]
        assert len(overwrite_warnings) == 0

    def test_last_write_wins_behavior_preserved(self) -> None:
        """Last Write Wins behavior: last added resource wins on repeated key."""
        bundle = FluentBundle("en")
        bundle.add_resource("greeting = First")
        bundle.add_resource("greeting = Second")
        bundle.add_resource("greeting = Third")

        result, _ = bundle.format_pattern("greeting")
        assert result == "Third"


class TestBundleIntegration:
    """Integration tests via FluentBundle for multi-module coverage."""

    def test_variant_key_failed_number_parse(self) -> None:
        """Number-like variant key that fails parse falls through to identifier."""
        bundle = FluentBundle("en_US", strict=False)
        bundle.add_resource(
            "msg = { $val ->\n"
            "    [-.test] Match\n"
            "   *[other] Other\n"
            "}\n"
        )
        result, _ = bundle.format_pattern(
            "msg", {"val": "-.test"}
        )
        assert result is not None

    def test_identifier_as_function_argument(self) -> None:
        """Identifier becomes MessageReference in function call arguments."""
        bundle = FluentBundle("en_US")

        def test_func(val: str | int) -> str:
            return str(val)

        bundle.add_function("TEST", test_func)
        bundle.add_resource("ref = value")
        bundle.add_resource("msg = { TEST(ref) }")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert result is not None

    def test_comment_with_crlf_ending(self) -> None:
        """Comment with CRLF line ending is parsed correctly."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("# Comment\r\nmsg = value")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "value" in result

    def test_full_coverage_integration(self) -> None:
        """Integration test exercising parser, resolver, and validator together."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "# Comment\n"
            "msg1 = { $val }\n"
            "msg2 = { NUMBER($val) }\n"
            "msg3 = { -term }\n"
            "msg4 = { other.attr }\n"
            "sel = { 42 ->\n"
            "    [42] Match\n"
            "   *[other] Other\n"
            "}\n"
            "-brand = Firefox\n"
            "    .version = 1.0\n"
            "empty =\n"
            "    .attr = Value\n"
        )
        r1, _ = bundle.format_pattern("msg1", {"val": "t"})
        r2, _ = bundle.format_pattern("msg2", {"val": 42})
        r3, _ = bundle.format_pattern("sel")
        assert all(r is not None for r in [r1, r2, r3])

        validation = validate_resource(
            "msg = { $val }\n-term = Firefox\n"
        )
        assert validation is not None


class TestBundleLocaleValidationBeforeLoading:
    """Locale validation happens before any resource loading attempt."""

    def test_locale_validation_before_resource_loading(self) -> None:
        """Invalid locale raises ValueError immediately, before resource loading."""
        with pytest.raises(ValueError, match="must be ASCII alphanumeric"):
            FluentBundle("\xe9_FR")


# ============================================================================
# TestAddResourceStream
# ============================================================================


class TestAddResourceStream:
    """FluentBundle.add_resource_stream incremental resource loading."""

    def test_single_message_from_lines(self) -> None:
        """add_resource_stream loads a single message from a line list."""
        bundle = FluentBundle("en")
        bundle.add_resource_stream(["greeting = Hello\n"])
        assert bundle.has_message("greeting")

    def test_multiple_messages_blank_separated(self) -> None:
        """Multiple messages separated by blank lines are all registered."""
        bundle = FluentBundle("en")
        bundle.add_resource_stream(["msg1 = One\n", "\n", "msg2 = Two\n"])
        assert bundle.has_message("msg1")
        assert bundle.has_message("msg2")

    def test_empty_stream_registers_nothing(self) -> None:
        """Empty line iterable registers no messages."""
        bundle = FluentBundle("en")
        bundle.add_resource_stream([])
        assert not bundle.has_message("anything")

    def test_returns_empty_junk_tuple_on_clean_source(self) -> None:
        """Clean FTL stream returns empty junk tuple."""
        bundle = FluentBundle("en")
        junk = bundle.add_resource_stream(["msg = Value\n"])
        assert junk == ()

    def test_returns_junk_on_parse_error(self) -> None:
        """Junk entries from invalid FTL are returned (not raised) in non-strict mode."""
        bundle = FluentBundle("en", strict=False)
        junk = bundle.add_resource_stream(["    invalid = indented\n"])
        assert len(junk) >= 1

    def test_strict_mode_raises_on_junk(self) -> None:
        """Strict mode raises SyntaxIntegrityError when the stream contains junk."""
        bundle = FluentBundle("en", strict=True)
        with pytest.raises(SyntaxIntegrityError):
            bundle.add_resource_stream(["    invalid = indented\n"])

    def test_source_path_threads_through(self) -> None:
        """source_path kwarg is accepted without error."""
        bundle = FluentBundle("en")
        bundle.add_resource_stream(
            ["greeting = Hello\n"], source_path="locales/en/ui.ftl"
        )
        assert bundle.has_message("greeting")

    def test_format_works_after_stream_load(self) -> None:
        """Messages loaded via add_resource_stream are formattable."""
        bundle = FluentBundle("en")
        bundle.add_resource_stream(["greeting = Hello, { $name }!\n"])
        result, errors = bundle.format_pattern("greeting", {"name": "World"})
        assert errors == ()
        assert result == "Hello, \u2068World\u2069!"

    def test_generator_input_accepted(self) -> None:
        """Generator (not just list) is accepted as lines argument."""
        bundle = FluentBundle("en")

        def gen() -> object:
            yield "msg = From generator\n"

        bundle.add_resource_stream(gen())  # type: ignore[arg-type]
        assert bundle.has_message("msg")

    def test_equivalence_with_add_resource(self) -> None:
        """add_resource_stream produces same messages as add_resource for same content."""
        source = "msg1 = One\n\nmsg2 = Two\n"
        b1 = FluentBundle("en")
        b1.add_resource(source)
        b2 = FluentBundle("en")
        b2.add_resource_stream(source.splitlines(keepends=True))
        assert b1.has_message("msg1") == b2.has_message("msg1")
        assert b1.has_message("msg2") == b2.has_message("msg2")
        r1, _ = b1.format_pattern("msg1")
        r2, _ = b2.format_pattern("msg1")
        assert r1 == r2

    @given(
        names=st.lists(
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(
                    min_codepoint=ord("a"),
                    max_codepoint=ord("z"),
                ),
            ),
            min_size=1,
            max_size=10,
        )
    )
    def test_all_messages_reachable_after_stream_load(
        self, names: list[str]
    ) -> None:
        """All messages loaded via stream are reachable via has_message."""
        event(f"msg_count={len(names)}")
        unique_names = list(dict.fromkeys(names))
        source = "\n\n".join(f"{name} = Value" for name in unique_names) + "\n"
        bundle = FluentBundle("en")
        bundle.add_resource_stream(source.splitlines(keepends=True))
        for name in unique_names:
            assert bundle.has_message(name), f"Missing: {name}"
