# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# ResourceLoadResult property invariants
# ---------------------------------------------------------------------------


class TestResourceLoadResultProperties:
    """Property invariants for ResourceLoadResult data class."""

    @given(
        status=st.sampled_from(list(LoadStatus)),
        locale=st.sampled_from(["en", "de", "fr", "lv"]),
        resource_id=st.sampled_from(["main.ftl", "ui.ftl"]),
    )
    def test_status_properties_are_mutually_exclusive(
        self, status: LoadStatus, locale: str, resource_id: str,
    ) -> None:
        """Exactly one status property is True for any LoadStatus."""
        event(f"status={status.value}")
        result = ResourceLoadResult(
            locale=locale, resource_id=resource_id, status=status,
        )
        flags = [result.is_success, result.is_not_found, result.is_error]
        assert sum(flags) == 1

    @given(
        junk_count=st.integers(min_value=0, max_value=5),
    )
    def test_has_junk_iff_junk_entries_nonempty(
        self, junk_count: int,
    ) -> None:
        """has_junk is True iff junk_entries is non-empty."""
        event(f"junk_count={junk_count}")
        junk_entries = tuple(
            Junk(
                content=f"invalid{i}",
                span=Span(start=i * 10, end=i * 10 + 7),
            )
            for i in range(junk_count)
        )
        result = ResourceLoadResult(
            locale="en", resource_id="test.ftl",
            status=LoadStatus.SUCCESS, junk_entries=junk_entries,
        )
        assert result.has_junk == (junk_count > 0)
