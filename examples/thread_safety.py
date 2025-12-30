"""Thread Safety Example - Demonstrating Safe Multi-threaded FluentBundle Usage.

This example shows the recommended patterns for using FluentBundle in multi-threaded
applications.

Thread Safety:
    FluentBundle is ALWAYS thread-safe. All public methods are synchronized
    via internal RLock. This prevents race conditions when add_resource()
    is called concurrently with format_pattern(). RLock overhead is negligible
    (~10ns per acquire) for typical usage patterns.

Demonstrates:
1. Single-threaded initialization pattern (recommended for static resources)
2. Concurrent read operations (always safe)
3. Thread-local bundles (alternative for per-thread customization)
4. Dynamic resource loading (always safe without manual locks)

WARNING: Examples use use_isolating=False for cleaner terminal output.
NEVER disable bidi isolation in production applications that support RTL languages.

Python 3.13+.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ftllexengine import FluentBundle


# Example 1: Single-threaded initialization (RECOMMENDED)
def example_1_recommended_pattern() -> None:
    """Example 1: Load all resources during startup, then share bundle for reads."""
    print("=" * 60)
    print("Example 1: Recommended Pattern - Single-threaded Init")
    print("=" * 60)

    # Step 1: Load resources during application startup (single-threaded)
    bundle = FluentBundle("en", use_isolating=False)
    bundle.add_resource("""
hello = Hello, { $name }!
items = { $count ->
    [one] one item
   *[other] { $count } items
}
    """)

    print("[STARTUP] Resources loaded (single-threaded)")

    # Step 2: Share bundle across threads for read-only operations (safe)
    def worker(thread_id: int, bundle_ref: FluentBundle) -> None:
        """Worker function that reads from shared bundle."""
        for _ in range(3):
            result, _ = bundle_ref.format_pattern("hello", {"name": f"Thread-{thread_id}"})
            print(f"  [Thread-{thread_id}] {result}")
            time.sleep(0.01)  # Simulate work

    print("\n[CONCURRENT READS] Multiple threads reading from shared bundle:")

    threads = []
    for tid in range(3):
        t = threading.Thread(target=worker, args=(tid, bundle))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("\n[SUCCESS] All threads completed safely")


# Example 2: ThreadPoolExecutor with shared bundle
def example_2_threadpool_pattern() -> None:
    """Example 2: Using ThreadPoolExecutor with shared bundle."""
    print("\n" + "=" * 60)
    print("Example 2: ThreadPoolExecutor Pattern")
    print("=" * 60)

    # Initialize bundle once
    bundle = FluentBundle("en", use_isolating=False)
    bundle.add_resource("""
processing = Processing { $filename }...
status = Status: { $status }
    """)

    print("[SETUP] Bundle initialized")

    # Function that reads from bundle
    def process_file(filename: str, bundle_ref: FluentBundle) -> str:
        """Simulate file processing with localized messages."""
        result, _ = bundle_ref.format_pattern("processing", {"filename": filename})
        time.sleep(0.05)  # Simulate work
        status_msg, _ = bundle_ref.format_pattern("status", {"status": "completed"})
        return f"{result} -> {status_msg}"

    files = [f"file{i}.txt" for i in range(5)]

    print(f"\n[PROCESSING] {len(files)} files concurrently:")

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_file, f, bundle): f for f in files}

        for future in as_completed(futures):
            result = future.result()
            print(f"  {result}")

    print("\n[SUCCESS] All files processed")


# Example 3: Thread-local bundles (alternative for per-thread customization)
def example_3_thread_local_bundles() -> None:
    """Example 3: Each thread gets its own bundle (for per-thread customization)."""
    print("\n" + "=" * 60)
    print("Example 3: Thread-local Bundles")
    print("=" * 60)
    print("[NOTE] Useful when each thread needs different resources or functions\n")

    # Thread-local storage for bundles
    thread_local = threading.local()

    def get_or_create_bundle() -> FluentBundle:
        """Get bundle for current thread (creates if needed)."""
        if not hasattr(thread_local, "bundle"):
            # Each thread creates its own bundle
            bundle: FluentBundle = FluentBundle("en", use_isolating=False)
            thread_local.bundle = bundle
            thread_local.bundle.add_resource("""
worker-msg = Worker thread { $tid } initialized
task = Processing task { $task_id }
            """)
            print(f"  [Thread-{threading.current_thread().ident}] Created bundle")

        # Type ignore: threading.local() has dynamic attributes
        return thread_local.bundle  # type: ignore[no-any-return]

    def worker_with_local_bundle(task_id: int) -> None:
        """Worker that uses thread-local bundle."""
        bundle = get_or_create_bundle()

        tid = threading.current_thread().ident
        result, _ = bundle.format_pattern("worker-msg", {"tid": tid})
        print(f"  {result}")

        task_result, _ = bundle.format_pattern("task", {"task_id": task_id})
        print(f"  {task_result}")

    print("[EXECUTION] Creating thread-local bundles:")

    threads = []
    for i in range(3):
        t = threading.Thread(target=worker_with_local_bundle, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("\n[SUCCESS] Thread-local bundles pattern complete")


# Example 4: Dynamic resource loading (always safe in v0.42.0+)
def example_4_dynamic_loading() -> None:
    """Example 4: Dynamic resource loading - always thread-safe.

    As of v0.42.0, FluentBundle is ALWAYS thread-safe.
    No special configuration or manual locks needed.
    """
    print("\n" + "=" * 60)
    print("Example 4: Dynamic Resource Loading (Always Safe)")
    print("=" * 60)
    print("[INFO] FluentBundle is always thread-safe as of v0.42.0")
    print("[INFO] No manual locks or special parameters needed\n")

    # Create bundle - thread safety is automatic
    bundle = FluentBundle("en", use_isolating=False)
    bundle.add_resource("initial = Initial message")

    print("[SETUP] Bundle created (always thread-safe)")

    def add_and_read(worker_id: int) -> None:
        """Worker that dynamically adds and reads resources - fully thread-safe."""
        # Add resource (thread-safe - no manual locking needed)
        ftl = f"dynamic-{worker_id} = Dynamic message from worker {worker_id}"
        bundle.add_resource(ftl)
        print(f"  [Worker-{worker_id}] Added resource")
        time.sleep(0.01)

        # Read message (thread-safe)
        result, _ = bundle.format_pattern(f"dynamic-{worker_id}")
        print(f"  [Worker-{worker_id}] {result}")

    print("[EXECUTION] Dynamic loading with built-in thread safety:")

    threads = []
    for i in range(3):
        t = threading.Thread(target=add_and_read, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("\n[SUCCESS] Dynamic loading pattern complete")
    print("[NOTE] No manual locking required - RLock handles synchronization")


# Main execution
if __name__ == "__main__":
    example_1_recommended_pattern()
    example_2_threadpool_pattern()
    example_3_thread_local_bundles()
    example_4_dynamic_loading()

    print("\n" + "=" * 60)
    print("[SUCCESS] All thread safety examples complete!")
    print("=" * 60)
    print("\nRECOMMENDATIONS:")
    print("  - Static resources: Use Example 1 (single-threaded init)")
    print("  - Dynamic resources: Use Example 4 (always safe)")
    print("  - Per-thread customization: Use Example 3 (thread-local)")
    print("\n[NOTE] As of v0.42.0, all FluentBundle instances are thread-safe.")
