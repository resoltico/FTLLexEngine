"""FluentLocalization Example - Multi-Locale Fallback Chains.

Demonstrates real-world usage of FluentLocalization for handling incomplete
translations and locale fallback chains.

Scenarios covered:
1. E-commerce site with partial Latvian translations
2. Multi-region application (Baltic states)
3. Dynamic resource loading
4. Custom resource loaders

WARNING: Examples use default use_isolating=True behavior. You may see
FSI (U+2068) and PDI (U+2069) bidi isolation marks in terminal output.
These marks are CRITICAL for RTL languages and should NEVER be disabled in
production applications.

NOTE: The FSI/PDI marks above are intentionally included to show users what
bidi isolation looks like. This is educational, not a security risk.

Note on Error Handling:
    Examples use underscore pattern (result, _) to ignore errors for brevity.
    In production code, ALWAYS check the errors list and log translation issues:

    result, errors = l10n.format_value('msg')
    if errors:
        logger.warning(f"Translation errors: {errors}")

Python 3.13+.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ftllexengine import FluentLocalization
from ftllexengine.localization import PathResourceLoader


def example_1_basic_fallback() -> None:
    """Example 1: Basic two-locale fallback (Latvian → English)."""
    print("=" * 60)
    print("Example 1: Basic Fallback (lv → en)")
    print("=" * 60)

    # Create localization with fallback chain: Latvian → English
    l10n = FluentLocalization(["lv", "en"])

    # Latvian translations (incomplete)
    l10n.add_resource(
        "lv",
        """
welcome = Sveiki, { $name }!
cart = Grozs
checkout = Kase
    """,
    )

    # English translations (complete)
    l10n.add_resource(
        "en",
        """
welcome = Hello, { $name }!
cart = Cart
checkout = Checkout
payment-success = Payment successful!
payment-error = Payment failed: { $reason }
    """,
    )

    print("\nMessages in Latvian:")
    result, _ = l10n.format_value("welcome", {"name": "Anna"})
    print(f"  welcome: {result}")

    result, _ = l10n.format_value("cart")
    print(f"  cart: {result}")

    print("\nMessages falling back to English:")
    result, _ = l10n.format_value("payment-success")
    print(f"  payment-success: {result}")

    result, _ = l10n.format_value("payment-error", {"reason": "Invalid card"})
    print(f"  payment-error: {result}")

    print("\nNon-existent message:")
    result, errors = l10n.format_value("nonexistent")
    print(f"  nonexistent: {result}")
    print(f"  errors: {len(errors)} error(s)")


def example_2_three_locale_chain() -> None:
    """Example 2: Three-locale fallback chain (Baltic states)."""
    print("\n" + "=" * 60)
    print("Example 2: Three-Locale Chain (lv → lt → en)")
    print("=" * 60)

    # Localization for Baltic market: Latvian → Lithuanian → English
    l10n = FluentLocalization(["lv", "lt", "en"])

    # Latvian (most specific - only homepage)
    l10n.add_resource("lv", "home = Mājas\nwelcome = Laipni lūdzam!")

    # Lithuanian (regional fallback - homepage + about)
    l10n.add_resource("lt", "home = Namai\nabout = Apie mus\ncontact = Kontaktai")

    # English (universal fallback - complete)
    l10n.add_resource(
        "en",
        """
home = Home
about = About Us
contact = Contact
privacy = Privacy Policy
terms = Terms of Service
    """,
    )

    print("\nFallback resolution:")
    messages = ["home", "about", "contact", "privacy"]

    for msg_id in messages:
        result, errors = l10n.format_value(msg_id)
        error_msg = f" [errors: {len(errors)}]" if errors else ""
        print(f"  {msg_id}: {result}{error_msg}")


def example_3_disk_based_resources(tmp_path: Path | None = None) -> None:
    """Example 3: Loading resources from disk with PathResourceLoader."""
    print("\n" + "=" * 60)
    print("Example 3: Disk-Based Resources")
    print("=" * 60)

    # Create temporary FTL files (in real app, these would be in your project)
    if tmp_path is None:
        tmp_dir_path = tempfile.mkdtemp()
        tmp_path = Path(tmp_dir_path)

    locales_dir = tmp_path / "locales"

    # Create English resources
    en_dir = locales_dir / "en"
    en_dir.mkdir(parents=True)

    (en_dir / "ui.ftl").write_text(
        """
hello = Hello!
welcome = Welcome to our app!
    """,
        encoding="utf-8",
    )

    (en_dir / "errors.ftl").write_text(
        """
error-404 = Page not found
error-500 = Internal server error
    """,
        encoding="utf-8",
    )

    # Create Latvian resources (partial)
    lv_dir = locales_dir / "lv"
    lv_dir.mkdir(parents=True)

    (lv_dir / "ui.ftl").write_text(
        """
hello = Sveiki!
welcome = Laipni lūdzam mūsu lietotnē!
    """,
        encoding="utf-8",
    )

    # Note: errors.ftl doesn't exist for Latvian - will fall back to English

    # Create localization with disk loader
    loader = PathResourceLoader(str(locales_dir / "{locale}"))
    l10n = FluentLocalization(["lv", "en"], ["ui.ftl", "errors.ftl"], loader)

    print(f"\nLoaded from: {locales_dir}")
    print("\nUI messages (from lv/ui.ftl):")
    result, _ = l10n.format_value("hello")
    print(f"  hello: {result}")

    print("\nError messages (fallback to en/errors.ftl):")
    result, _ = l10n.format_value("error-404")
    print(f"  error-404: {result}")


def example_4_custom_loader() -> None:
    """Example 4: Custom resource loader (in-memory)."""
    print("\n" + "=" * 60)
    print("Example 4: Custom In-Memory Loader")
    print("=" * 60)

    class InMemoryLoader:
        """Custom loader that stores FTL in memory (e.g., database, cache)."""

        def __init__(self) -> None:
            self.resources: dict[tuple[str, str], str] = {}

        def add(self, locale: str, resource_id: str, ftl_source: str) -> None:
            """Add FTL resource to memory."""
            self.resources[(locale, resource_id)] = ftl_source

        def load(self, locale: str, resource_id: str) -> str:
            """Load FTL resource from memory."""
            key = (locale, resource_id)
            if key not in self.resources:
                msg = f"Resource not found: {locale}/{resource_id}"
                raise FileNotFoundError(msg)
            return self.resources[key]

    # Create loader and populate
    loader = InMemoryLoader()

    loader.add("en", "main.ftl", "hello = Hello!\nwelcome = Welcome!")
    loader.add("lv", "main.ftl", "hello = Sveiki!")

    # Use with FluentLocalization
    l10n = FluentLocalization(["lv", "en"], ["main.ftl"], loader)

    print("\nLoaded from in-memory cache:")
    result, _ = l10n.format_value("hello")
    print(f"  hello (lv): {result}")

    result, _ = l10n.format_value("welcome")
    print(f"  welcome (en fallback): {result}")


def example_4b_database_cache_loader() -> None:
    """Example 4b: Database/Cache loader (production pattern)."""
    print("\n" + "=" * 60)
    print("Example 4b: Database/Cache Loader (Production)")
    print("=" * 60)

    class DatabaseResourceLoader:
        """Load FTL resources from database or cache (Redis, Memcached, etc.).

        This example shows a production-ready pattern for loading translations
        from a centralized storage system. In real applications, replace the
        dict with actual database queries or cache client calls.
        """

        def __init__(self) -> None:
            # Simulate database/cache storage
            # In production: self.db = Database() or self.cache = Redis()
            self._storage: dict[tuple[str, str], str] = {}

        def seed_database(self) -> None:
            """Simulate seeding database with FTL resources.

            In production, this would be:
            - Loading from .ftl files during deployment
            - Importing translations from translation management system (Pontoon, Crowdin)
            - Pulling from version control
            """
            self._storage[("en", "main.ftl")] = """
# English translations
welcome = Welcome to our application!
logout = Log out
profile = My Profile
settings = Settings
help = Help & Support
"""

            self._storage[("lv", "main.ftl")] = """
# Latvian translations (partial)
welcome = Laipni lūdzam mūsu lietotnē!
logout = Iziet
profile = Mans profils
"""

            self._storage[("en", "errors.ftl")] = """
# Error messages
error-404 = Page not found
error-500 = Internal server error
error-network = Network connection lost
"""

            print("[DATABASE] Seeded with FTL resources")

        def load(self, locale: str, resource_id: str) -> str:
            """Load FTL resource from database/cache.

            In production:
            ```python
            # Redis example
            key = f"ftl:{locale}:{resource_id}"
            cached = self.cache.get(key)
            if cached:
                return cached.decode('utf-8')

            # Database fallback
            result = self.db.query(
                "SELECT content FROM ftl_resources WHERE locale=? AND resource_id=?",
                (locale, resource_id)
            )
            if not result:
                raise FileNotFoundError(f"Resource not found: {locale}/{resource_id}")

            content = result[0]['content']
            # Cache for future requests
            self.cache.setex(key, 3600, content.encode('utf-8'))
            return content
            ```
            """
            key = (locale, resource_id)
            if key not in self._storage:
                msg = f"Resource not found in database: {locale}/{resource_id}"
                raise FileNotFoundError(msg)
            return self._storage[key]

    # Initialize loader and seed database
    loader = DatabaseResourceLoader()
    loader.seed_database()

    # Create localization with database-backed resources
    l10n = FluentLocalization(["lv", "en"], ["main.ftl", "errors.ftl"], loader)

    print("\nLoading from database/cache:")

    # Main navigation (from main.ftl)
    result, _ = l10n.format_value("welcome")
    print(f"  welcome (lv): {result}")

    result, _ = l10n.format_value("settings")
    print(f"  settings (en fallback): {result}")

    # Error messages (from errors.ftl)
    result, _ = l10n.format_value("error-404")
    print(f"  error-404 (en): {result}")

    print("\n[PRODUCTION PATTERN] Benefits:")
    print("  - Centralized translation storage")
    print("  - Version control for translations")
    print("  - A/B testing different translations")
    print("  - Dynamic updates without redeployment")
    print("  - Cache layer for performance")


def example_5_e_commerce_complete() -> None:
    """Example 5: Complete E-Commerce Application."""
    print("\n" + "=" * 60)
    print("Example 5: E-Commerce Application (Realistic)")
    print("=" * 60)

    # Localization for Latvian e-commerce site
    l10n = FluentLocalization(["lv", "en"])

    # Latvian translations (core shopping experience)
    l10n.add_resource(
        "lv",
        """
# Navigation
home = Mājas
products = Produkti
cart = Grozs
account = Konts

# Shopping
add-to-cart = Pievienot grozam
checkout = Kase
total = Kopā: { NUMBER($amount, minimumFractionDigits: 2) } EUR

# Product
product-price = { NUMBER($price, minimumFractionDigits: 2) } EUR
in-stock = Pieejams
out-of-stock = Nav pieejams
    """,
    )

    # English fallback (complete)
    l10n.add_resource(
        "en",
        """
# Navigation
home = Home
products = Products
cart = Cart
account = Account

# Shopping
add-to-cart = Add to Cart
checkout = Checkout
total = Total: { NUMBER($amount, minimumFractionDigits: 2) } EUR

# Product
product-price = { NUMBER($price, minimumFractionDigits: 2) } EUR
in-stock = In Stock
out-of-stock = Out of Stock

# User actions (not in Latvian yet)
wishlist = Wishlist
compare = Compare Products
reviews = Customer Reviews
shipping-info = Shipping Information
return-policy = Return Policy
    """,
    )

    print("\nCore shopping experience (Latvian):")
    nav_items = ["home", "products", "cart", "account"]
    for item in nav_items:
        result, _ = l10n.format_value(item)
        print(f"  {item}: {result}")

    print("\nAdvanced features (English fallback):")
    advanced = ["wishlist", "compare", "reviews"]
    for item in advanced:
        result, _ = l10n.format_value(item)
        print(f"  {item}: {result}")

    print("\nDynamic content:")
    result, _ = l10n.format_value("total", {"amount": 49.99})
    print(f"  total: {result}")


def example_6_checking_message_availability() -> None:
    """Example 6: Checking message availability before formatting."""
    print("\n" + "=" * 60)
    print("Example 6: Checking Message Availability")
    print("=" * 60)

    l10n = FluentLocalization(["lv", "en"])
    l10n.add_resource("lv", "hello = Sveiki!")
    l10n.add_resource("en", "hello = Hello!\ngoodbye = Goodbye!")

    print("\nChecking message availability:")
    messages = ["hello", "goodbye", "nonexistent"]

    for msg_id in messages:
        available = l10n.has_message(msg_id)
        status = "[OK] Available" if available else "[WARN] Not found"
        print(f"  {msg_id}: {status}")

        if available:
            result, _ = l10n.format_value(msg_id)
            print(f"    → {result}")


def example_7_iterating_bundles() -> None:
    """Example 7: Advanced - Iterating through bundles."""
    print("\n" + "=" * 60)
    print("Example 7: Iterating Bundles (Advanced)")
    print("=" * 60)

    l10n = FluentLocalization(["lv", "en", "lt"])
    l10n.add_resource("lv", "msg1 = Latvian")
    l10n.add_resource("en", "msg1 = English\nmsg2 = English message 2")
    l10n.add_resource("lt", "msg3 = Lithuanian")

    print("\nBundle inspection:")
    for bundle in l10n.get_bundles():
        print(f"\nLocale: {bundle.locale}")
        # Check which messages this bundle has
        for msg_id in ["msg1", "msg2", "msg3"]:
            has_msg = bundle.has_message(msg_id)
            status = "[OK]" if has_msg else "[--]"
            print(f"  {msg_id}: {status}")


# Main execution
if __name__ == "__main__":
    example_1_basic_fallback()
    example_2_three_locale_chain()

    # Create temp directory for disk example
    with tempfile.TemporaryDirectory() as tmp_dir_main:
        example_3_disk_based_resources(Path(tmp_dir_main))

    example_4_custom_loader()
    example_4b_database_cache_loader()
    example_5_e_commerce_complete()
    example_6_checking_message_availability()
    example_7_iterating_bundles()

    print("\n" + "=" * 60)
    print("[SUCCESS] All examples complete!")
    print("=" * 60)
