"""Tests for BrowserLock cross-platform file locking.

Run with: python test_browser_lock.py
   or:    python -m pytest test_browser_lock.py -v
"""

import subprocess
import sys
import time
from pathlib import Path

# Allow running as both pytest and standalone
try:
    import pytest
except ImportError:
    pytest = None

from council_browser import BrowserBusyError, BrowserLock


def test_acquire_release():
    """Lock acquire succeeds, release succeeds, fd is cleaned up."""
    lock = BrowserLock()
    lock.acquire()
    assert lock._fd is not None, "fd should be set after acquire"
    assert lock.LOCK_PATH.exists(), "lock file should exist"
    lock.release()
    assert lock._fd is None, "fd should be None after release"


def test_double_acquire_fails():
    """Second process cannot acquire a lock held by the first."""
    lock = BrowserLock()
    lock.acquire()
    try:
        # Write a temp script for the child process (avoids -c quoting issues on Windows)
        script_dir = Path(__file__).resolve().parent
        tmp_script = script_dir / "_test_lock_child.py"
        tmp_script.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(script_dir)!r})\n"
            "from council_browser import BrowserLock, BrowserBusyError\n"
            "lock = BrowserLock()\n"
            "try:\n"
            "    lock.acquire()\n"
            '    print("ACQUIRED")\n'
            "    lock.release()\n"
            "except BrowserBusyError:\n"
            '    print("BUSY")\n',
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(tmp_script)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "BUSY" in result.stdout, f"Expected BUSY, got stdout={result.stdout!r} stderr={result.stderr!r}"
    finally:
        lock.release()
        try:
            tmp_script.unlink()
        except Exception:
            pass


def test_release_then_reacquire():
    """After release, a new lock instance can acquire successfully."""
    lock1 = BrowserLock()
    lock1.acquire()
    lock1.release()

    lock2 = BrowserLock()
    lock2.acquire()
    assert lock2._fd is not None, "second acquire should succeed after first release"
    lock2.release()


def test_context_manager():
    """BrowserLock works as a context manager."""
    with BrowserLock() as lock:
        assert lock._fd is not None
    # After exiting context, fd should be released
    assert lock._fd is None


if __name__ == "__main__":
    tests = [test_acquire_release, test_double_acquire_fails, test_release_then_reacquire, test_context_manager]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS: {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__} — {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
