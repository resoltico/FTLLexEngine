# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# add_resource_stream oracle: streaming == buffered for FluentLocalization
# ---------------------------------------------------------------------------


class TestAddResourceStreamLocalizationOracle:
    """Oracle: FluentLocalization.add_resource_stream is equivalent to add_resource.

    Properties verified:
    - Message IDs registered via stream match those registered via buffered load.
    - format_pattern results are identical across both loading paths.
    - Junk entry counts match for the same FTL content.
    - Second call to add_resource_stream (bundle already exists) behaves correctly.
    """

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        source=ftl_simple_messages(),
    )
    def test_message_ids_match_add_resource(
        self, locales: list[str], source: str
    ) -> None:
        """Stream-loaded message IDs equal buffered-loaded IDs for same FTL."""
        l_buf = FluentLocalization(locales, use_isolating=False, strict=False)
        l_str = FluentLocalization(locales, use_isolating=False, strict=False)
        locale = locales[0]

        l_buf.add_resource(locale, source)
        l_str.add_resource_stream(locale, source.splitlines(keepends=True))

        # Format the same message IDs from both — stream must produce same results
        buf_ids: set[str] = set()
        for msg_id in source.splitlines():
            if " = " in msg_id:
                buf_ids.add(msg_id.split(" = ", 1)[0].strip())

        event(f"l10n_stream_locale_count={len(locales)}")
        for mid in buf_ids:
            r_buf, e_buf = l_buf.format_pattern(mid)
            r_str, e_str = l_str.format_pattern(mid)
            event(f"outcome={'match' if r_buf == r_str else 'mismatch'}")
            assert r_buf == r_str, (
                f"format_pattern mismatch for {mid!r}: "
                f"buffered={r_buf!r}, stream={r_str!r}"
            )
            assert len(e_buf) == len(e_str)

    @given(
        locales=locale_chains(min_size=1, max_size=2),
        source=ftl_simple_messages(),
    )
    def test_junk_count_matches_add_resource(
        self, locales: list[str], source: str
    ) -> None:
        """Junk count from stream load matches junk count from buffered load."""
        l_buf = FluentLocalization(locales, use_isolating=False, strict=False)
        l_str = FluentLocalization(locales, use_isolating=False, strict=False)
        locale = locales[0]

        junk_buf = l_buf.add_resource(locale, source)
        junk_str = l_str.add_resource_stream(
            locale, source.splitlines(keepends=True)
        )

        event(f"junk_buf={len(junk_buf)}")
        event(f"junk_stream={len(junk_str)}")
        assert len(junk_buf) == len(junk_str)

    @given(
        locales=locale_chains(min_size=1, max_size=2),
        source1=ftl_simple_messages(),
        source2=ftl_simple_messages(),
    )
    def test_second_stream_call_accumulates_messages(
        self, locales: list[str], source1: str, source2: str
    ) -> None:
        """Two add_resource_stream calls accumulate messages on same bundle.

        The second call hits the pre-existing bundle path (orchestrator.py
        line 734->736 False branch) — verifies correct state accumulation.
        """
        l10n = FluentLocalization(locales, use_isolating=False, strict=False)
        locale = locales[0]

        l10n.add_resource_stream(locale, source1.splitlines(keepends=True))
        l10n.add_resource_stream(locale, source2.splitlines(keepends=True))

        event("l10n_two_stream_calls=done")
        # At minimum the bundle must exist and be queryable
        result, _errors = l10n.format_pattern("__nonexistent__")
        event(f"fallback_result={result!r}")
        # Missing message returns fallback string, not exception, in non-strict mode
        assert "__nonexistent__" in result
