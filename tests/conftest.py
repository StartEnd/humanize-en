"""Shared pytest fixtures for humanize-en tests.

Mirrors humanize-zh/tests/conftest.py — same ``clean_registry``
fixture pattern so test files lifted from there compile against
the EN plugin with no changes.
"""

from __future__ import annotations

import pytest

# ─── Registry snapshot fixture ──────────────────────────────────────────────
#
# Drops existing registry state for the duration of the test and
# restores it on teardown. Same shape as humanize-zh's fixture but
# imports from humanize-core directly (we don't depend on
# humanize-zh's ``_core`` shim package).

@pytest.fixture
def clean_registry():
    """Drop existing registry state, restore on teardown.

    Forces ``_DISCOVERY_DONE = True`` after reset so the next
    ``get_language`` / ``list_languages`` call does **not** trigger
    entry-point discovery (which would silently re-register ``en``
    from this package's own pyproject entry point and break tests that
    assert "registry is empty here"). Tests that explicitly want to
    exercise discovery should flip the flag back to ``False``
    themselves inside the test body.
    """
    from humanize_core import language_registry as reg
    from humanize_core.language_registry import reset_for_tests

    with reg._LOCK:
        snapshot = dict(reg._PROFILES)
        snapshot_done = reg._DISCOVERY_DONE
    reset_for_tests()
    with reg._LOCK:
        reg._DISCOVERY_DONE = True
    yield
    reset_for_tests()
    with reg._LOCK:
        reg._PROFILES.update(snapshot)
        reg._DISCOVERY_DONE = snapshot_done
