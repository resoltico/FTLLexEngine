"""Thread Safety Example - Demonstrating Safe Multi-threaded FluentBundle Usage.

This example shows the recommended patterns for using FluentBundle in multi-threaded
applications.

Thread Safety Options (v0.38.0+):
- Default (thread_safe=False): NOT thread-safe for writes (add_resource, add_function).
  Once resources are loaded, bundles are safe for concurrent reads.
- Opt-in (thread_safe=True): Full thread-safety via RLock synchronization.
  All operations are thread-safe, suitable for dynamic loading scenarios.

Demonstrates:
1. Single-threaded initialization pattern (recommended for static resources)
2. Concurrent read operations (safe)
3. Thread-local bundles (alternative for dynamic loading)
4. Legacy lock-based dynamic loading (superseded by thread_safe=True)
5. Built-in thread safety with thread_safe=True (recommended for dynamic use)

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


# Example 3: Thread-local bundles (alternative for dynamic loading)
def example_3_thread_local_bundles() -> None:
    """Example 3: Each thread gets its own bundle (avoids locking)."""
    print("\n" + "=" * 60)
    print("Example 3: Thread-local Bundles")
    print("=" * 60)

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


# Example 4: Lock-based dynamic loading (LEGACY - superseded by thread_safe=True)
def example_4_lock_based_dynamic_loading() -> None:
    """Example 4: Legacy manual lock pattern (superseded by thread_safe=True)."""
    print("\n" + "=" * 60)
    print("Example 4: Lock-based Dynamic Loading (LEGACY)")
    print("=" * 60)
    print("[DEPRECATED] This pattern is superseded by thread_safe=True (see Example 5)")
    print("[NOTE] Shown for backwards compatibility understanding\n")

    bundle = FluentBundle("en", use_isolating=False)
    bundle.add_resource("initial = Initial message")

    # Lock for protecting writes
    bundle_lock = threading.Lock()

    def add_resource_safely(ftl_source: str) -> None:
        """Thread-safe resource addition."""
        with bundle_lock:
            bundle.add_resource(ftl_source)
            print(f"  [Thread-{threading.current_thread().ident}] Added resource")

    def read_message(message_id: str) -> str:
        """Thread-safe message reading."""
        with bundle_lock:
            result, errors = bundle.format_pattern(message_id)
            if errors:
                return f"{{Error: {message_id}}}"
            return result

    # Simulate dynamic loading
    def dynamic_worker(worker_id: int) -> None:
        """Worker that dynamically adds resources."""
        # Add a resource (locked)
        ftl = f"dynamic-{worker_id} = Dynamic message from worker {worker_id}"
        add_resource_safely(ftl)
        time.sleep(0.01)

        # Read the message (locked)
        result = read_message(f"dynamic-{worker_id}")
        print(f"  [Worker-{worker_id}] {result}")

    print("[EXECUTION] Dynamic resource loading with locks:")

    threads = []
    for i in range(3):
        t = threading.Thread(target=dynamic_worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("\n[SUCCESS] Lock-based pattern complete")
    print("[NOTE] Consider using thread_safe=True instead (see Example 5)")


# Example 5: Built-in thread safety (v0.38.0+, RECOMMENDED for dynamic use)
def example_5_builtin_thread_safety() -> None:
    """Example 5: Use thread_safe=True for full thread-safety (v0.38.0+)."""
    print("\n" + "=" * 60)
    print("Example 5: Built-in Thread Safety (v0.38.0+)")
    print("=" * 60)
    print("[RECOMMENDED] For dynamic resource loading scenarios\n")

    # Create thread-safe bundle with built-in RLock synchronization
    bundle = FluentBundle("en", use_isolating=False, thread_safe=True)
    bundle.add_resource("initial = Initial message")

    # Verify thread safety is enabled
    print(f"[SETUP] Bundle created with is_thread_safe={bundle.is_thread_safe}")

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

    print("\n[SUCCESS] Built-in thread safety pattern complete")
    print("[NOTE] No manual locking required - RLock handles synchronization")


# Main execution
if __name__ == "__main__":
    example_1_recommended_pattern()
    example_2_threadpool_pattern()
    example_3_thread_local_bundles()
    example_4_lock_based_dynamic_loading()
    example_5_builtin_thread_safety()

    print("\n" + "=" * 60)
    print("[SUCCESS] All thread safety examples complete!")
    print("=" * 60)
    print("\nRECOMMENDATIONS:")
    print("  - Static resources: Use Example 1 (single-threaded init)")
    print("  - Dynamic resources: Use Example 5 (thread_safe=True)")
