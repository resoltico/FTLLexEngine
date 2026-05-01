# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# LoadSummary aggregation invariants
# ---------------------------------------------------------------------------


class TestLoadSummaryAggregation:
    """Property invariants for LoadSummary post_init aggregation."""

    @given(
        success_n=st.integers(min_value=0, max_value=5),
        not_found_n=st.integers(min_value=0, max_value=5),
        error_n=st.integers(min_value=0, max_value=5),
    )
    def test_status_counts_sum_to_total(
        self, success_n: int, not_found_n: int, error_n: int,
    ) -> None:
        """successful + not_found + errors == total_attempted."""
        total = success_n + not_found_n + error_n
        event(f"total={total}")
        results: list[ResourceLoadResult] = []
        for i in range(success_n):
            results.append(ResourceLoadResult(
                f"en{i}", f"s{i}.ftl", LoadStatus.SUCCESS,
            ))
        for i in range(not_found_n):
            results.append(ResourceLoadResult(
                f"nf{i}", f"n{i}.ftl", LoadStatus.NOT_FOUND,
            ))
        for i in range(error_n):
            results.append(ResourceLoadResult(
                f"er{i}", f"e{i}.ftl", LoadStatus.ERROR,
                error=OSError(f"fail{i}"),
            ))

        summary = LoadSummary(results=tuple(results))
        assert summary.total_attempted == total
        assert summary.successful == success_n
        assert summary.not_found == not_found_n
        assert summary.errors == error_n
        assert summary.successful + summary.not_found + summary.errors == total

    @given(
        junk_per_result=st.lists(
            st.integers(min_value=0, max_value=3),
            min_size=1, max_size=5,
        ),
    )
    def test_junk_count_is_total_across_results(
        self, junk_per_result: list[int],
    ) -> None:
        """junk_count sums junk_entries lengths across all results."""
        expected_total = sum(junk_per_result)
        event(f"total_junk={expected_total}")
        results: list[ResourceLoadResult] = []
        for idx, jc in enumerate(junk_per_result):
            junk = tuple(
                Junk(
                    content=f"j{idx}_{j}",
                    span=Span(start=0, end=1),
                )
                for j in range(jc)
            )
            results.append(ResourceLoadResult(
                "en", f"f{idx}.ftl", LoadStatus.SUCCESS,
                junk_entries=junk,
            ))

        summary = LoadSummary(results=tuple(results))
        assert summary.junk_count == expected_total
        assert summary.has_junk == (expected_total > 0)

    @given(
        success_n=st.integers(min_value=0, max_value=3),
        not_found_n=st.integers(min_value=0, max_value=3),
        error_n=st.integers(min_value=0, max_value=3),
    )
    def test_filter_methods_partition_results(
        self, success_n: int, not_found_n: int, error_n: int,
    ) -> None:
        """get_errors + get_not_found + get_successful == all results."""
        event(f"error_n={error_n}")
        results: list[ResourceLoadResult] = []
        for i in range(success_n):
            results.append(ResourceLoadResult(
                "en", f"s{i}.ftl", LoadStatus.SUCCESS,
            ))
        for i in range(not_found_n):
            results.append(ResourceLoadResult(
                "de", f"n{i}.ftl", LoadStatus.NOT_FOUND,
            ))
        for i in range(error_n):
            results.append(ResourceLoadResult(
                "fr", f"e{i}.ftl", LoadStatus.ERROR,
                error=OSError("fail"),
            ))

        summary = LoadSummary(results=tuple(results))
        assert len(summary.get_successful()) == success_n
        assert len(summary.get_not_found()) == not_found_n
        assert len(summary.get_errors()) == error_n

    @given(
        locale=st.sampled_from(["en", "de", "fr"]),
        n=st.integers(min_value=0, max_value=4),
    )
    def test_get_by_locale_filters_correctly(
        self, locale: str, n: int,
    ) -> None:
        """get_by_locale returns only matching-locale results."""
        event(f"filter_count={n}")
        results: list[ResourceLoadResult] = []
        for i in range(n):
            results.append(ResourceLoadResult(
                locale, f"f{i}.ftl", LoadStatus.SUCCESS,
            ))
        # Add results for other locales
        results.append(ResourceLoadResult(
            "xx", "other.ftl", LoadStatus.SUCCESS,
        ))

        summary = LoadSummary(results=tuple(results))
        filtered = summary.get_by_locale(locale)
        assert len(filtered) == n
        assert all(r.locale == locale for r in filtered)

    @given(
        junk_counts=st.lists(
            st.integers(min_value=0, max_value=3),
            min_size=1, max_size=4,
        ),
    )
    def test_get_all_junk_flattens_correctly(
        self, junk_counts: list[int],
    ) -> None:
        """get_all_junk returns flattened tuple of all Junk entries."""
        expected_total = sum(junk_counts)
        event(f"flatten_total={expected_total}")
        results: list[ResourceLoadResult] = []
        all_junk: list[Junk] = []
        for idx, jc in enumerate(junk_counts):
            junk_entries = tuple(
                Junk(
                    content=f"j{idx}_{j}",
                    span=Span(start=0, end=1),
                )
                for j in range(jc)
            )
            all_junk.extend(junk_entries)
            results.append(ResourceLoadResult(
                "en", f"f{idx}.ftl", LoadStatus.SUCCESS,
                junk_entries=junk_entries,
            ))

        summary = LoadSummary(results=tuple(results))
        flattened = summary.get_all_junk()
        assert len(flattened) == expected_total
        for j in all_junk:
            assert j in flattened

    @given(
        has_errors=st.booleans(),
        has_not_found=st.booleans(),
        has_junk=st.booleans(),
    )
    def test_all_successful_and_all_clean_semantics(
        self, has_errors: bool, has_not_found: bool, has_junk: bool,
    ) -> None:
        """all_successful ignores junk; all_clean requires zero junk."""
        event(f"errors={has_errors}")
        event(f"not_found={has_not_found}")
        results: list[ResourceLoadResult] = []
        # Always add at least one success
        junk = (
            (Junk(content="j", span=Span(start=0, end=1)),)
            if has_junk else ()
        )
        results.append(ResourceLoadResult(
            "en", "main.ftl", LoadStatus.SUCCESS, junk_entries=junk,
        ))
        if has_errors:
            results.append(ResourceLoadResult(
                "de", "err.ftl", LoadStatus.ERROR, error=OSError("f"),
            ))
        if has_not_found:
            results.append(ResourceLoadResult(
                "fr", "nf.ftl", LoadStatus.NOT_FOUND,
            ))

        summary = LoadSummary(results=tuple(results))

        expected_all_successful = not has_errors and not has_not_found
        assert summary.all_successful == expected_all_successful

        expected_all_clean = (
            not has_errors and not has_not_found and not has_junk
        )
        assert summary.all_clean == expected_all_clean

    @given(
        has_errors=st.booleans(),
    )
    def test_has_errors_property(self, has_errors: bool) -> None:
        """has_errors is True iff errors > 0."""
        event(f"has_errors={has_errors}")
        results: list[ResourceLoadResult] = [
            ResourceLoadResult("en", "ok.ftl", LoadStatus.SUCCESS),
        ]
        if has_errors:
            results.append(ResourceLoadResult(
                "de", "err.ftl", LoadStatus.ERROR, error=OSError("f"),
            ))
        summary = LoadSummary(results=tuple(results))
        assert summary.has_errors == has_errors
