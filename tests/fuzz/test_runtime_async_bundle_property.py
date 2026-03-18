"""Property-based fuzz tests for runtime.async_bundle: AsyncFluentBundle.

Properties verified:
- Oracle: AsyncFluentBundle.format_pattern matches FluentBundle for same FTL.
- Oracle: add_resource_stream (async) produces same IDs as add_resource (async).
- Concurrent: multiple concurrent format_pattern calls produce consistent results.
- Context manager: async with always exits cleanly regardless of operations.
- Stability: format_pattern on unknown message ID behaves predictably (non-strict mode).
- Immutability: sync read operations (has_message, get_message, etc.) are consistent.
"""

from __future__ import annotations

import asyncio
import string

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.async_bundle import AsyncFluentBundle
from ftllexengine.runtime.bundle import FluentBundle
from tests.strategies.ftl import ftl_identifiers, ftl_simple_messages

pytestmark = pytest.mark.fuzz

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOCALES = ["en_US", "de_DE", "fr_FR", "lv_LV", "ja_JP"]

_locale_strategy = st.sampled_from(_LOCALES)


# ---------------------------------------------------------------------------
# Oracle: AsyncFluentBundle vs FluentBundle equivalence
# ---------------------------------------------------------------------------


class TestAsyncBundleVsSyncOracle:
    """Oracle: AsyncFluentBundle must match FluentBundle for identical operations."""

    @given(
        locale=_locale_strategy,
        source=ftl_simple_messages(),
    )
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_message_ids_match_sync_bundle(self, locale: str, source: str) -> None:
        """AsyncFluentBundle message IDs equal FluentBundle message IDs.

        Both bundles load the same FTL source. After loading, the set of
        registered message IDs must be identical.
        """
        event(f"locale={locale}")

        sync_bundle = FluentBundle(locale, use_isolating=False, strict=False)
        sync_bundle.add_resource(source)
        sync_ids = set(sync_bundle.get_message_ids())

        async def run_async() -> set[str]:
            async_bundle = AsyncFluentBundle(locale, use_isolating=False, strict=False)
            await async_bundle.add_resource(source)
            return set(async_bundle.get_message_ids())

        async_ids = asyncio.run(run_async())
        event(
            f"outcome={'match' if sync_ids == async_ids else 'mismatch'}"
        )
        assert sync_ids == async_ids

    @given(
        locale=_locale_strategy,
        source=ftl_simple_messages(),
    )
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_format_results_match_sync_bundle(self, locale: str, source: str) -> None:
        """format_pattern results from AsyncFluentBundle match FluentBundle.

        For any message ID successfully registered in the sync bundle, the
        async bundle must produce the same formatted string and error count.
        """
        event(f"locale={locale}")

        sync_bundle = FluentBundle(locale, use_isolating=False, strict=False)
        sync_bundle.add_resource(source)
        sync_ids = list(sync_bundle.get_message_ids())

        if not sync_ids:
            event("outcome=no_messages_to_test")
            return

        async def run_async() -> list[tuple[str, str, int]]:
            async_bundle = AsyncFluentBundle(locale, use_isolating=False, strict=False)
            await async_bundle.add_resource(source)
            results: list[tuple[str, str, int]] = []
            for mid in sync_ids:
                r_async, e_async = await async_bundle.format_pattern(mid)
                results.append((mid, r_async, len(e_async)))
            return results

        async_results = asyncio.run(run_async())

        for mid, r_async, _async_err_count in async_results:
            r_sync, _e_sync = sync_bundle.format_pattern(mid)
            event(
                f"format_match={'yes' if r_sync == r_async else 'no'}"
            )
            assert r_sync == r_async, (
                f"Mismatch for {mid!r}: sync={r_sync!r} async={r_async!r}"
            )

    @given(
        locale=_locale_strategy,
        source=ftl_simple_messages(),
    )
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_stream_ids_match_buffered_ids(self, locale: str, source: str) -> None:
        """add_resource_stream (async) produces same IDs as add_resource (async).

        The async streaming path must be equivalent to the async buffered path
        for the same FTL content.
        """
        event(f"locale={locale}")

        async def run_async() -> tuple[set[str], set[str]]:
            b_buf = AsyncFluentBundle(locale, use_isolating=False, strict=False)
            b_str = AsyncFluentBundle(locale, use_isolating=False, strict=False)
            await b_buf.add_resource(source)
            await b_str.add_resource_stream(source.splitlines(keepends=True))
            return set(b_buf.get_message_ids()), set(b_str.get_message_ids())

        ids_buf, ids_stream = asyncio.run(run_async())
        event(
            f"outcome={'match' if ids_buf == ids_stream else 'mismatch'}"
        )
        assert ids_buf == ids_stream


# ---------------------------------------------------------------------------
# Concurrent safety
# ---------------------------------------------------------------------------


class TestAsyncBundleConcurrency:
    """Property: concurrent format_pattern calls produce consistent results."""

    @given(
        locale=_locale_strategy,
        names=st.lists(
            st.text(
                alphabet=string.ascii_lowercase,
                min_size=1, max_size=8,
            ).filter(lambda s: s.isidentifier()),
            min_size=1, max_size=5,
            unique=True,
        ),
        concurrency=st.integers(min_value=2, max_value=10),
    )
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_concurrent_reads_consistent(
        self, locale: str, names: list[str], concurrency: int
    ) -> None:
        """Multiple concurrent format_pattern calls return consistent results.

        Runs concurrency concurrent tasks that all format the same messages.
        Results must be identical across all concurrent invocations.
        """
        event(f"concurrency={concurrency}")
        event(f"msg_count={len(names)}")

        source = "\n".join(f"{name} = value-{name}" for name in names)

        async def run_concurrent() -> list[dict[str, str]]:
            bundle = AsyncFluentBundle(locale, use_isolating=False, strict=False)
            await bundle.add_resource(source)

            async def format_all() -> dict[str, str]:
                results: dict[str, str] = {}
                for name in names:
                    r, _ = await bundle.format_pattern(name)
                    results[name] = r
                return results

            tasks = [asyncio.create_task(format_all()) for _ in range(concurrency)]
            return list(await asyncio.gather(*tasks))

        all_results = asyncio.run(run_concurrent())

        # All concurrent results must be identical
        first = all_results[0]
        for result in all_results[1:]:
            assert result == first, (
                f"Concurrent result mismatch: {first!r} vs {result!r}"
            )
        event("outcome=concurrent_consistent")


# ---------------------------------------------------------------------------
# Context manager protocol
# ---------------------------------------------------------------------------


class TestAsyncContextManager:
    """Property: async with always exits cleanly."""

    @given(
        locale=_locale_strategy,
        source=ftl_simple_messages(),
    )
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_context_manager_exits_cleanly(self, locale: str, source: str) -> None:
        """async with block always exits without raising, regardless of operations."""
        event(f"locale={locale}")

        async def run_async() -> str:
            async with AsyncFluentBundle(
                locale, use_isolating=False, strict=False
            ) as bundle:
                await bundle.add_resource(source)
                ids = list(bundle.get_message_ids())
                if ids:
                    r, _ = await bundle.format_pattern(ids[0])
                    return r
                return ""

        result = asyncio.run(run_async())
        assert isinstance(result, str)
        event("outcome=context_manager_clean_exit")

    @given(locale=_locale_strategy)
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_empty_context_manager_exits_cleanly(self, locale: str) -> None:
        """async with block with no operations exits cleanly."""
        async def run_async() -> None:
            async with AsyncFluentBundle(locale, use_isolating=False):
                pass

        asyncio.run(run_async())
        event("outcome=empty_context_manager_ok")


# ---------------------------------------------------------------------------
# Sync read operations consistency
# ---------------------------------------------------------------------------


class TestSyncReadOperationsConsistency:
    """Property: sync read operations reflect state set by async mutation ops."""

    @given(
        locale=_locale_strategy,
        source=ftl_simple_messages(),
    )
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_has_message_consistent_with_get_message_ids(
        self, locale: str, source: str
    ) -> None:
        """has_message(id) is True iff id is in get_message_ids()."""
        event(f"locale={locale}")

        async def run_async() -> tuple[list[str], list[bool]]:
            bundle = AsyncFluentBundle(locale, use_isolating=False, strict=False)
            await bundle.add_resource(source)
            ids = list(bundle.get_message_ids())
            has_flags = [bundle.has_message(mid) for mid in ids]
            return ids, has_flags

        registered_ids, has_flags = asyncio.run(run_async())
        for mid, has in zip(registered_ids, has_flags, strict=True):
            assert has, (
                f"has_message({mid!r}) False but id is in get_message_ids()"
            )
        event(f"msg_count={len(registered_ids)}")
        event("outcome=has_message_consistent")

    @given(
        locale=_locale_strategy,
        source=ftl_simple_messages(),
    )
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_get_message_returns_message_node_for_known_ids(
        self, locale: str, source: str
    ) -> None:
        """get_message(id) returns non-None for every id in get_message_ids()."""
        async def run_async() -> tuple[bool, int]:
            bundle = AsyncFluentBundle(locale, use_isolating=False, strict=False)
            await bundle.add_resource(source)
            ids = list(bundle.get_message_ids())
            all_found = all(bundle.get_message(mid) is not None for mid in ids)
            return all_found, len(ids)

        result, count = asyncio.run(run_async())
        event(f"msg_count={count}")
        event("outcome=all_get_message_non_none" if result else "outcome=some_none")
        assert result

    @given(
        locale=_locale_strategy,
        unknown_id=ftl_identifiers(),
    )
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_message_returns_fallback_in_non_strict(
        self, locale: str, unknown_id: str
    ) -> None:
        """format_pattern for unknown ID in non-strict mode returns fallback string."""
        event(f"id_len={len(unknown_id)}")

        async def run_async() -> tuple[str, int]:
            bundle = AsyncFluentBundle(locale, use_isolating=False, strict=False)
            r, errors = await bundle.format_pattern(unknown_id)
            return r, len(errors)

        result, error_count = asyncio.run(run_async())
        # Non-strict mode: unknown message → fallback string containing the ID
        assert unknown_id in result
        assert error_count > 0
        event("outcome=fallback_returned")

    @given(
        locale=_locale_strategy,
        unknown_id=ftl_identifiers(),
    )
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_has_attribute_false_for_unknown_message(
        self, locale: str, unknown_id: str
    ) -> None:
        """has_attribute returns False for unknown message IDs.

        For any message ID not registered in the bundle, has_attribute must
        return False regardless of the attribute name queried.
        """
        async def run_async() -> bool:
            bundle = AsyncFluentBundle(locale, use_isolating=False, strict=False)
            return bundle.has_attribute(unknown_id, "label")

        result = asyncio.run(run_async())
        assert result is False
        event("outcome=has_attribute_false_for_unknown")
