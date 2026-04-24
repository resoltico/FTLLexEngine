"""AsyncFluentBundle examples for asyncio applications.

Demonstrates:

1. Async context-manager usage
2. Concurrent ``format_pattern()`` calls
3. ``add_resource_stream()`` in async code

Python 3.13+.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from ftllexengine import AsyncFluentBundle


async def example_async_context_manager() -> None:
    """Format a currency message through the async wrapper."""
    print("=" * 68)
    print("Example 1: Async context manager")
    print("=" * 68)

    async with AsyncFluentBundle("en_US", use_isolating=False) as bundle:
        await bundle.add_resource('price = Total: { CURRENCY($amount, currency: "USD") }')
        result, errors = await bundle.format_pattern("price", {"amount": Decimal("99.99")})
        assert errors == ()
        assert result == "Total: $99.99"
        print(f"[OK] Formatted price: {result}")

    print("[PASS] Async context-manager formatting works")


async def example_concurrent_formatting() -> None:
    """Show concurrent async formatting against one shared bundle."""
    print("\n" + "=" * 68)
    print("Example 2: Concurrent async formatting")
    print("=" * 68)

    bundle = AsyncFluentBundle("en_US", use_isolating=False)
    await bundle.add_resource("counter = Count: { $n }")

    results = await asyncio.gather(
        *(bundle.format_pattern("counter", {"n": i}) for i in range(5))
    )
    texts = [text for text, errors in results if errors == ()]
    assert texts == [f"Count: {i}" for i in range(5)]
    print(f"[OK] Concurrent results: {texts}")

    print("[PASS] Concurrent async formatting works")


async def example_stream_loading() -> None:
    """Load streamed FTL lines through the async wrapper."""
    print("\n" + "=" * 68)
    print("Example 3: Async add_resource_stream")
    print("=" * 68)

    bundle = AsyncFluentBundle("en_US", use_isolating=False)
    junk = await bundle.add_resource_stream(["hello = Hello!\n", "status = Ready\n"])
    assert junk == ()
    assert bundle.has_message("hello")

    status, errors = await bundle.format_pattern("status")
    assert errors == ()
    assert status == "Ready"
    print(f"[OK] Stream-loaded status: {status}")

    print("[PASS] Async stream loading works")


async def main() -> None:
    """Run all async examples."""
    await example_async_context_manager()
    await example_concurrent_formatting()
    await example_stream_loading()
    print("\n[SUCCESS] Async bundle examples complete!")


if __name__ == "__main__":
    asyncio.run(main())
