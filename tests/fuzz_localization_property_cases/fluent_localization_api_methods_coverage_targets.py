# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# FluentLocalization API methods (coverage targets)
# ---------------------------------------------------------------------------


class TestFluentLocalizationHasAttribute:
    """Tests for has_attribute method (lines 1126-1130)."""

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        ftl=ftl_messages_with_attributes(),
    )
    def test_has_attribute_from_generated_resource(
        self, locales: list[str], ftl: str,
    ) -> None:
        """has_attribute detects attributes in generated resources."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], ftl)

        # Extract message ID from generated FTL
        first_line = ftl.split("\n", maxsplit=1)[0]
        mid = first_line.split("=")[0].strip()

        # Check for attr0 (present if attributes were generated)
        if ".attr0" in ftl:
            assert l10n.has_attribute(mid, "attr0") is True
            event("outcome=attribute_found")
        else:
            assert l10n.has_attribute(mid, "attr0") is False
            event("outcome=no_attributes")

    @given(locales=locale_chains(min_size=2, max_size=4))
    def test_has_attribute_fallback_chain(
        self, locales: list[str],
    ) -> None:
        """has_attribute searches across fallback chain."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        # Attribute only in last locale
        l10n.add_resource(
            locales[-1], "btn = Click\n    .tooltip = Help text\n",
        )
        assert l10n.has_attribute("btn", "tooltip") is True

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_has_attribute_missing_returns_false(
        self, locales: list[str],
    ) -> None:
        """has_attribute returns False for nonexistent attributes."""
        event("outcome=not_found")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], "msg = No attributes\n")
        assert l10n.has_attribute("msg", "nonexistent") is False
        assert l10n.has_attribute("missing", "attr") is False


class TestFluentLocalizationGetMessageIds:
    """Tests for get_message_ids method (lines 1142-1150)."""

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        resources=ftl_resource_sets(),
    )
    def test_get_message_ids_returns_union(
        self, locales: list[str], resources: dict[str, str],
    ) -> None:
        """get_message_ids returns union of IDs across all locales."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        all_expected: set[str] = set()
        for locale in locales:
            if locale in resources:
                l10n.add_resource(locale, resources[locale])
                # Parse message IDs from FTL
                for line in resources[locale].split("\n"):
                    if "=" in line and not line.startswith(
                        ("#", " ", "-"),
                    ):
                        mid = line.split("=")[0].strip()
                        if mid:
                            all_expected.add(mid)

        ids = l10n.get_message_ids()
        assert set(ids) == all_expected
        # No duplicates
        assert len(ids) == len(set(ids))

    @given(locales=locale_chains(min_size=2, max_size=3))
    def test_get_message_ids_primary_locale_first(
        self, locales: list[str],
    ) -> None:
        """get_message_ids orders primary locale IDs first."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], "alpha = A\n")
        l10n.add_resource(
            locales[-1], "alpha = A2\nbeta = B\n",
        )
        ids = l10n.get_message_ids()
        # alpha from primary appears before beta from fallback
        assert ids.index("alpha") < ids.index("beta")

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_get_message_ids_empty_when_no_resources(
        self, locales: list[str],
    ) -> None:
        """get_message_ids returns empty list when no resources loaded."""
        event("outcome=empty")
        l10n = FluentLocalization(locales)
        assert l10n.get_message_ids() == []


class TestFluentLocalizationGetMessageVariables:
    """Tests for get_message_variables method (lines 1169-1174)."""

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_get_message_variables_returns_variable_names(
        self, locales: list[str],
    ) -> None:
        """get_message_variables extracts variable names from message."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(
            locales[0],
            "greeting = Hello { $firstName } { $lastName }!\n",
        )
        variables = l10n.get_message_variables("greeting")
        assert "firstName" in variables
        assert "lastName" in variables

    @given(locales=locale_chains(min_size=2, max_size=3))
    def test_get_message_variables_fallback(
        self, locales: list[str],
    ) -> None:
        """get_message_variables searches fallback chain."""
        event("outcome=fallback_search")
        l10n = FluentLocalization(locales)
        l10n.add_resource(
            locales[-1], "msg = Value { $count }\n",
        )
        variables = l10n.get_message_variables("msg")
        assert "count" in variables

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_get_message_variables_raises_for_missing(
        self, locales: list[str],
    ) -> None:
        """get_message_variables raises KeyError for missing message."""
        event("outcome=key_error")
        l10n = FluentLocalization(locales)
        with pytest.raises(KeyError, match="not found"):
            l10n.get_message_variables("nonexistent")


class TestFluentLocalizationGetAllMessageVariables:
    """Tests for get_all_message_variables (lines 1188-1196)."""

    @given(locales=locale_chains(min_size=1, max_size=3))
    def test_get_all_message_variables_returns_dict(
        self, locales: list[str],
    ) -> None:
        """get_all_message_variables returns dict of msg_id -> variables."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(
            locales[0],
            "msg1 = { $name }\nmsg2 = Static text\n",
        )
        all_vars = l10n.get_all_message_variables()
        assert isinstance(all_vars, dict)
        assert "msg1" in all_vars
        assert "name" in all_vars["msg1"]
        assert "msg2" in all_vars

    @given(locales=locale_chains(min_size=2, max_size=3))
    def test_primary_locale_variables_take_precedence(
        self, locales: list[str],
    ) -> None:
        """Primary locale's variables win for duplicate message IDs."""
        event("outcome=precedence")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], "msg = { $primary }\n")
        l10n.add_resource(locales[-1], "msg = { $fallback }\n")
        all_vars = l10n.get_all_message_variables()
        assert "primary" in all_vars["msg"]


class TestFluentLocalizationIntrospectTerm:
    """Tests for introspect_term method (lines 1211-1217)."""

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_introspect_term_found(
        self, locales: list[str],
    ) -> None:
        """introspect_term returns introspection for existing term."""
        event("outcome=term_found")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], "-brand = Firefox\n")
        info = l10n.introspect_term("brand")
        assert info is not None

    @given(locales=locale_chains(min_size=2, max_size=3))
    def test_introspect_term_fallback(
        self, locales: list[str],
    ) -> None:
        """introspect_term searches fallback chain."""
        event("outcome=term_fallback")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[-1], "-product = App\n")
        info = l10n.introspect_term("product")
        assert info is not None

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_introspect_term_not_found(
        self, locales: list[str],
    ) -> None:
        """introspect_term returns None for missing term."""
        event("outcome=term_not_found")
        l10n = FluentLocalization(locales)
        info = l10n.introspect_term("nonexistent")
        assert info is None
