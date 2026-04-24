"""Streaming Resource Examples.

Demonstrates the line-oriented resource APIs that avoid requiring one
pre-assembled source string before parsing:

1. ``FluentBundle.add_resource_stream()``
2. ``parse_stream_ftl()``
3. ``FluentLocalization.add_resource_stream()``

Python 3.13+.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from ftllexengine import FluentBundle, FluentLocalization, parse_stream_ftl
from ftllexengine.localization import PathResourceLoader


def example_bundle_stream_load() -> None:
    """Load one bundle from a file handle and parse the same stream directly."""
    print("=" * 68)
    print("Example 1: FluentBundle.add_resource_stream")
    print("=" * 68)

    with TemporaryDirectory() as tmp:
        source_path = Path(tmp) / "messages.ftl"
        source_path.write_text(
            "hello = Hello from orbit\n"
            "status = Cargo ready\n",
            encoding="utf-8",
        )

        bundle = FluentBundle("en_US", use_isolating=False)
        with source_path.open(encoding="utf-8") as handle:
            junk = bundle.add_resource_stream(handle, source_path=str(source_path))
        assert junk == ()

        status, errors = bundle.format_pattern("status")
        assert errors == ()
        assert status == "Cargo ready"
        print(f"[OK] Formatted status: {status}")

        with source_path.open(encoding="utf-8") as handle:
            entry_ids = [
                entry.id.name
                for entry in parse_stream_ftl(handle)
                if hasattr(entry, "id")
            ]
        assert entry_ids == ["hello", "status"]
        print(f"[OK] Parsed entries: {entry_ids}")

    print("[PASS] Bundle stream loading works")


def example_localization_stream_load() -> None:
    """Add a streamed resource to one locale inside a fallback chain."""
    print("\n" + "=" * 68)
    print("Example 2: FluentLocalization.add_resource_stream")
    print("=" * 68)

    with TemporaryDirectory() as tmp:
        base = Path(tmp) / "locales"
        (base / "de_de").mkdir(parents=True)
        (base / "en_us").mkdir(parents=True)
        (base / "de_de" / "messages.ftl").write_text("hello = Hallo\n", encoding="utf-8")
        (base / "en_us" / "messages.ftl").write_text("hello = Hello\n", encoding="utf-8")

        extra = Path(tmp) / "extra_de.ftl"
        extra.write_text("shipment = Zusatzdatei\n", encoding="utf-8")

        loader = PathResourceLoader(str(base / "{locale}"))
        l10n = FluentLocalization(["de_DE", "en_US"], ["messages.ftl"], loader)

        with extra.open(encoding="utf-8") as handle:
            junk = l10n.add_resource_stream("de_DE", handle, source_path=str(extra))
        assert junk == ()

        shipment, errors = l10n.format_value("shipment")
        assert errors == ()
        assert shipment == "Zusatzdatei"
        print(f"[OK] Localized streamed message: {shipment}")

    print("[PASS] Localization stream loading works")


if __name__ == "__main__":
    example_bundle_stream_load()
    example_localization_stream_load()
    print("\n[SUCCESS] Streaming resource examples complete!")
