"""Performance Benchmarks for Resource Loaders.

This example benchmarks different resource loader implementations to help you
choose the optimal pattern for your production environment:

1. In-Memory Loader (dict-based)
2. Disk Loader (PathResourceLoader)
3. Database/Cache Loader (simulated Redis/Memcached)

Includes:
- Throughput measurements (ops/sec)
- Latency measurements (milliseconds)
- Memory usage tracking
- Cache hit rate analysis
- Best practice recommendations

WARNING: Examples use use_isolating=False for cleaner output.
NEVER disable bidi isolation in production applications.

Python 3.13+.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from ftllexengine import FluentLocalization
from ftllexengine.localization import PathResourceLoader


class BenchmarkTimer:
    """Simple timer for benchmarking operations."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    def __enter__(self) -> BenchmarkTimer:
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self.end_time = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds."""
        return (self.end_time - self.start_time) * 1000

    @property
    def elapsed_sec(self) -> float:
        """Elapsed time in seconds."""
        return self.end_time - self.start_time


# Sample FTL resources for benchmarking
SAMPLE_FTL_EN = """
# English translations
welcome = Welcome to our application!
greeting = Hello, { $name }!
farewell = Goodbye, { $name }!
product-count = You have { $count ->
    [one] one product
   *[other] { $count } products
} in your cart.
error-404 = Page not found
error-500 = Internal server error
logout = Log out
profile = My Profile
settings = Settings
help = Help & Support
"""

SAMPLE_FTL_LV = """
# Latvian translations
welcome = Laipni lūdzam mūsu lietotnē!
greeting = Sveiki, { $name }!
farewell = Uz redzēšanos, { $name }!
product-count = Jūsu grozā ir { $count ->
    [zero] { $count } produktu
    [one] { $count } produkts
   *[other] { $count } produkti
}.
logout = Iziet
profile = Mans profils
settings = Iestatījumi
"""


class InMemoryLoader:
    """In-memory loader (fastest - no I/O)."""

    def __init__(self) -> None:
        self._storage: dict[tuple[str, str], str] = {}
        self._access_count = 0

    def seed(self, locale: str, resource_id: str, content: str) -> None:
        """Add resource to memory."""
        self._storage[(locale, resource_id)] = content

    def load(self, locale: str, resource_id: str) -> str:
        """Load resource from memory."""
        self._access_count += 1
        key = (locale, resource_id)
        if key not in self._storage:
            msg = f"Resource not found: {locale}/{resource_id}"
            raise FileNotFoundError(msg)
        return self._storage[key]

    def describe_path(self, locale: str, resource_id: str) -> str:
        """Return in-memory path description."""
        return f"memory:{locale}/{resource_id}"


class SimulatedDatabaseLoader:
    """Simulated database loader with cache (realistic production pattern)."""

    def __init__(self, cache_enabled: bool = True, db_latency_ms: float = 5.0) -> None:
        """Initialize with optional cache and configurable latency.

        Args:
            cache_enabled: Enable in-memory cache layer
            db_latency_ms: Simulated database latency in milliseconds
        """
        self._db_storage: dict[tuple[str, str], str] = {}
        self._cache: dict[tuple[str, str], str] = {}
        self.cache_enabled = cache_enabled
        self.db_latency_ms = db_latency_ms

        # Statistics
        self.db_hits = 0
        self.cache_hits = 0
        self.total_loads = 0

    def seed(self, locale: str, resource_id: str, content: str) -> None:
        """Add resource to database."""
        self._db_storage[(locale, resource_id)] = content

    def load(self, locale: str, resource_id: str) -> str:
        """Load resource with cache fallback to database."""
        self.total_loads += 1
        key = (locale, resource_id)

        # Check cache first
        if self.cache_enabled and key in self._cache:
            self.cache_hits += 1
            return self._cache[key]

        # Simulate database query latency
        time.sleep(self.db_latency_ms / 1000)

        # Database lookup
        if key not in self._db_storage:
            msg = f"Resource not found in database: {locale}/{resource_id}"
            raise FileNotFoundError(msg)

        content = self._db_storage[key]
        self.db_hits += 1

        # Cache for future requests
        if self.cache_enabled:
            self._cache[key] = content

        return content

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        if self.total_loads == 0:
            return 0.0
        return (self.cache_hits / self.total_loads) * 100

    def clear_cache(self) -> None:
        """Clear cache (for benchmarking)."""
        self._cache.clear()
        self.cache_hits = 0
        self.db_hits = 0
        self.total_loads = 0

    def describe_path(self, locale: str, resource_id: str) -> str:
        """Return simulated database path description."""
        return f"db:{locale}/{resource_id}"


def benchmark_loader_initialization(
    loader_name: str, loader: Any, locales: list[str], resource_ids: list[str]
) -> float:
    """Benchmark FluentLocalization initialization with loader.

    Args:
        loader_name: Loader description
        loader: Resource loader instance
        locales: List of locale codes
        resource_ids: List of resource IDs

    Returns:
        Initialization time in milliseconds
    """
    print(f"\n[BENCHMARK] {loader_name} - Initialization")

    with BenchmarkTimer("init") as timer:
        # Create FluentLocalization - measures init time only
        _ = FluentLocalization(locales, resource_ids, loader, use_isolating=False)

    print(f"  Time: {timer.elapsed_ms:.2f} ms")
    throughput = len(resource_ids) * len(locales) / timer.elapsed_sec
    print(f"  Throughput: {throughput:.0f} resources/sec")

    return timer.elapsed_ms


def benchmark_loader_formatting(
    loader_name: str, l10n: FluentLocalization, iterations: int = 1000
) -> tuple[float, float]:
    """Benchmark message formatting performance.

    Args:
        loader_name: Loader description
        l10n: FluentLocalization instance
        iterations: Number of format operations

    Returns:
        Tuple of (total_time_ms, ops_per_sec)
    """
    print(f"\n[BENCHMARK] {loader_name} - Message Formatting")

    # Warm-up (important for cached loaders)
    for _ in range(10):
        l10n.format_value("welcome")

    # Benchmark
    messages = ["welcome", "greeting", "farewell", "logout", "profile"]
    total_ops = iterations * len(messages)

    with BenchmarkTimer("format") as timer:
        for _ in range(iterations):
            for msg_id in messages:
                l10n.format_value(msg_id, {"name": "Test"})

    ops_per_sec = total_ops / timer.elapsed_sec
    avg_latency_ms = timer.elapsed_ms / total_ops

    print(f"  Total operations: {total_ops:,}")
    print(f"  Total time: {timer.elapsed_ms:.2f} ms")
    print(f"  Throughput: {ops_per_sec:,.0f} ops/sec")
    print(f"  Avg latency: {avg_latency_ms:.4f} ms")

    return timer.elapsed_ms, ops_per_sec


def main() -> None:  # noqa: PLR0915  # pylint: disable=too-many-statements,too-many-locals
    """Run comprehensive loader benchmarks.

    Complexity unavoidable: Example demonstrates 4 loader patterns with detailed
    benchmarking and reporting. High statement count is intentional for complete demo.
    """
    print("=" * 70)
    print("FTLLexEngine Resource Loader Performance Benchmarks")
    print("=" * 70)

    # Configuration
    ITERATIONS = 1000  # noqa: N806  # pylint: disable=invalid-name  # Constant configuration value
    locales = ["lv", "en"]
    resource_ids = ["main.ftl"]

    # Store results
    results: dict[str, dict[str, float]] = {}

    # ========================================================================
    # Benchmark 1: In-Memory Loader (Baseline - Fastest)
    # ========================================================================
    print("\n" + "=" * 70)
    print("Benchmark 1: In-Memory Loader (dict-based)")
    print("=" * 70)
    print("Use case: Small apps, embedded translations, maximum performance")

    memory_loader = InMemoryLoader()
    memory_loader.seed("en", "main.ftl", SAMPLE_FTL_EN)
    memory_loader.seed("lv", "main.ftl", SAMPLE_FTL_LV)

    init_time = benchmark_loader_initialization(
        "In-Memory", memory_loader, locales, resource_ids
    )

    l10n_memory = FluentLocalization(locales, resource_ids, memory_loader, use_isolating=False)
    format_time, ops_per_sec = benchmark_loader_formatting("In-Memory", l10n_memory, ITERATIONS)

    results["in_memory"] = {
        "init_ms": init_time,
        "format_ms": format_time,
        "ops_per_sec": ops_per_sec,
    }

    # ========================================================================
    # Benchmark 2: Disk Loader (PathResourceLoader)
    # ========================================================================
    print("\n" + "=" * 70)
    print("Benchmark 2: Disk Loader (PathResourceLoader)")
    print("=" * 70)
    print("Use case: Standard deployments, file-based translations")

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create FTL files
        locales_dir = Path(tmp_dir) / "locales"
        (locales_dir / "en").mkdir(parents=True)
        (locales_dir / "lv").mkdir(parents=True)
        (locales_dir / "en" / "main.ftl").write_text(SAMPLE_FTL_EN, encoding="utf-8")
        (locales_dir / "lv" / "main.ftl").write_text(SAMPLE_FTL_LV, encoding="utf-8")

        disk_loader = PathResourceLoader(str(locales_dir / "{locale}"))

        init_time = benchmark_loader_initialization(
            "Disk", disk_loader, locales, resource_ids
        )

        l10n_disk = FluentLocalization(locales, resource_ids, disk_loader, use_isolating=False)
        format_time, ops_per_sec = benchmark_loader_formatting("Disk", l10n_disk, ITERATIONS)

        results["disk"] = {
            "init_ms": init_time,
            "format_ms": format_time,
            "ops_per_sec": ops_per_sec,
        }

    # ========================================================================
    # Benchmark 3: Database Loader WITHOUT Cache (Worst Case)
    # ========================================================================
    print("\n" + "=" * 70)
    print("Benchmark 3: Database Loader WITHOUT Cache (Worst Case)")
    print("=" * 70)
    print("Use case: Dynamic translations, no cache layer (NOT RECOMMENDED)")

    db_loader_nocache = SimulatedDatabaseLoader(cache_enabled=False, db_latency_ms=5.0)
    db_loader_nocache.seed("en", "main.ftl", SAMPLE_FTL_EN)
    db_loader_nocache.seed("lv", "main.ftl", SAMPLE_FTL_LV)

    init_time = benchmark_loader_initialization(
        "Database (no cache)", db_loader_nocache, locales, resource_ids
    )

    l10n_db_nocache = FluentLocalization(
        locales, resource_ids, db_loader_nocache, use_isolating=False
    )
    format_time, ops_per_sec = benchmark_loader_formatting(
        "Database (no cache)", l10n_db_nocache, ITERATIONS // 10  # Fewer iterations
    )

    results["db_nocache"] = {
        "init_ms": init_time,
        "format_ms": format_time,
        "ops_per_sec": ops_per_sec,
    }

    # ========================================================================
    # Benchmark 4: Database Loader WITH Cache (Recommended)
    # ========================================================================
    print("\n" + "=" * 70)
    print("Benchmark 4: Database Loader WITH Cache (Production Pattern)")
    print("=" * 70)
    print("Use case: Centralized translations with Redis/Memcached cache")

    db_loader_cached = SimulatedDatabaseLoader(cache_enabled=True, db_latency_ms=5.0)
    db_loader_cached.seed("en", "main.ftl", SAMPLE_FTL_EN)
    db_loader_cached.seed("lv", "main.ftl", SAMPLE_FTL_LV)

    init_time = benchmark_loader_initialization(
        "Database (cached)", db_loader_cached, locales, resource_ids
    )

    l10n_db_cached = FluentLocalization(
        locales, resource_ids, db_loader_cached, use_isolating=False
    )
    format_time, ops_per_sec = benchmark_loader_formatting(
        "Database (cached)", l10n_db_cached, ITERATIONS
    )

    results["db_cached"] = {
        "init_ms": init_time,
        "format_ms": format_time,
        "ops_per_sec": ops_per_sec,
    }

    print("\n[CACHE STATS] Database Loader (cached)")
    print(f"  Total loads: {db_loader_cached.total_loads}")
    print(f"  Cache hits: {db_loader_cached.cache_hits}")
    print(f"  DB hits: {db_loader_cached.db_hits}")
    print(f"  Cache hit rate: {db_loader_cached.cache_hit_rate:.1f}%")

    # ========================================================================
    # Results Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    print("\nInitialization Time (lower is better):")
    print(f"  In-Memory:         {results['in_memory']['init_ms']:>8.2f} ms  (baseline)")
    disk_ratio = results["disk"]["init_ms"] / results["in_memory"]["init_ms"]
    print(f"  Disk:              {results['disk']['init_ms']:>8.2f} ms  ({disk_ratio:.1f}x slower)")
    db_nocache_ratio = results["db_nocache"]["init_ms"] / results["in_memory"]["init_ms"]
    nocache_ms = results["db_nocache"]["init_ms"]
    print(f"  DB (no cache):     {nocache_ms:>8.2f} ms  ({db_nocache_ratio:.1f}x slower)")
    db_cached_ratio = results["db_cached"]["init_ms"] / results["in_memory"]["init_ms"]
    cached_ms = results["db_cached"]["init_ms"]
    print(f"  DB (cached):       {cached_ms:>8.2f} ms  ({db_cached_ratio:.1f}x slower)")

    print("\nMessage Formatting Throughput (higher is better):")
    print(f"  In-Memory:         {results['in_memory']['ops_per_sec']:>8,.0f} ops/sec  (baseline)")
    baseline_ops = results["in_memory"]["ops_per_sec"]
    disk_pct = results["disk"]["ops_per_sec"] / baseline_ops
    disk_ops = results["disk"]["ops_per_sec"]
    print(f"  Disk:              {disk_ops:>8,.0f} ops/sec  ({disk_pct:.1%} of baseline)")
    nocache_pct = results["db_nocache"]["ops_per_sec"] / baseline_ops
    nocache_ops = results["db_nocache"]["ops_per_sec"]
    print(f"  DB (no cache):     {nocache_ops:>8,.0f} ops/sec  ({nocache_pct:.1%} of baseline)")
    cached_pct = results["db_cached"]["ops_per_sec"] / baseline_ops
    cached_ops = results["db_cached"]["ops_per_sec"]
    print(f"  DB (cached):       {cached_ops:>8,.0f} ops/sec  ({cached_pct:.1%} of baseline)")

    # ========================================================================
    # Recommendations
    # ========================================================================
    print("\n" + "=" * 70)
    print("PRODUCTION RECOMMENDATIONS")
    print("=" * 70)

    print("\n1. SMALL APPLICATIONS (<100 messages, single-server)")
    print("   Recommendation: In-Memory Loader")
    print("   Rationale: Zero I/O overhead, simple deployment")
    print("   Example: Microservices, CLI tools, embedded translations")

    print("\n2. STANDARD APPLICATIONS (file-based translations)")
    print("   Recommendation: Disk Loader (PathResourceLoader)")
    print("   Rationale: Standard workflow, version controlled files")
    print("   Example: Web apps, desktop apps with .ftl files in repo")

    print("\n3. LARGE-SCALE APPLICATIONS (multi-server, dynamic updates)")
    print("   Recommendation: Database + Cache Loader")
    print("   Rationale: Centralized management, A/B testing, zero downtime updates")
    print("   Example: SaaS platforms, enterprise apps, CDN-backed translations")
    print("   CRITICAL: ALWAYS use cache layer (Redis, Memcached)")

    print("\n4. HYBRID APPROACH (recommended for flexibility)")
    print("   Pattern: In-Memory cache + Disk/DB fallback")
    print("   ```python")
    print("   # Load once at startup, keep in memory")
    print("   bundle = FluentBundle('en')")
    print("   bundle.add_resource(Path('locale/en/main.ftl').read_text())")
    print("   # Share bundle across request handlers (read-only)")
    print("   ```")

    print("\n" + "=" * 70)
    print("KEY TAKEAWAYS")
    print("=" * 70)
    print("[OK] In-Memory: Fastest, but static (requires deployment to update)")
    print("[OK] Disk: Good balance, standard workflow")
    print("[WARN] Database (no cache): SLOW - only for rare dynamic updates")
    print("[OK] Database (cached): Production-ready for centralized management")
    print("\nBest practice: Load resources once at startup, share bundles across")
    print("               request handlers for read-only operations")

    print("\n" + "=" * 70)
    print("[OK] Benchmarks complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
