"""Shared pytest fixtures for humanize-en tests.

Mirrors humanize-zh/tests/conftest.py — same ``clean_registry``
fixture pattern so test files lifted from there compile against
the EN plugin with no changes. Also exposes a small set of
CLI-oriented fixtures (``repo_root``, ``ai_article_en``,
``fake_polish_fn``, ``fake_judge_fn``) that ``tests/test_cli.py``
relies on.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from humanize_en import llm

# ─── Sample article ─────────────────────────────────────────────────────────

AI_ARTICLE_EN = """# Analysis

It's worth noting that this platform is not just a tool but a comprehensive,
holistic solution that fundamentally transforms how users approach complex
challenges in the dynamic landscape.

Moreover, it leverages cutting-edge methodologies. Furthermore, it delivers
sustained value across multiple stakeholder ecosystems. Additionally, it
underscores the importance of strategic alignment.

In conclusion, this transformative approach will not only enhance operational
efficiency but also foster sustainable innovation in the long term.
"""


@pytest.fixture
def ai_article_en() -> str:
    """A short English article seeded with AI tells for detection tests."""
    return AI_ARTICLE_EN


# ─── LLM provider fixtures ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_llm_between_tests():
    """Ensure each test starts with no active provider so tests can't leak.

    The active-provider singleton lives in ``humanize_core.llm`` and is
    shared between the core framework and every installed plugin. If a
    test sets a provider and forgets to clear it, the next test sees the
    stale provider and may accidentally hit a real LLM (or hang waiting
    for one). Wiping the slot before *and* after every test keeps the
    suite hermetic.
    """
    llm.clear()
    yield
    llm.clear()


@pytest.fixture
def fake_polish_fn() -> Callable[[str], str]:
    """Deterministic callable that simulates polishing by removing AI tells.

    Detects the EN polish prompt (``"Task: De-AI polishing pass"``)
    so we can return a believable EN rewrite. Any other prompt is
    treated as a generic completion request and gets a passthrough
    canned response.
    """

    def _fn(prompt: str) -> str:
        if "Task: De-AI polishing pass" in prompt:
            return (
                "# Analysis\n\n"
                "This platform is a comprehensive solution.\n\n"
                "It solves real problems for its users by closing the loop "
                "between pain point and outcome, and it does so without "
                "fanfare.\n\n"
                "A case study worth studying.\n"
            )
        return "stub-response"

    return _fn


@pytest.fixture
def fake_judge_fn() -> Callable[[str], str]:
    """Deterministic callable that returns a valid judge JSON response.

    Matches on the EN judge prompt marker shipped in the EN
    plugin's ``prompt_pack.judge_user_template`` (note the wording
    differs slightly from ``humanize_core.prompt.JUDGE_PROMPT_EN``
    — the plugin's pack uses *"English long-form article"*, the core
    fallback uses *"long-form English article"* — so we match the
    common substring ``"long-form"`` plus ``"article"`` to be
    resilient to either path).
    """

    def _fn(prompt: str) -> str:
        if "long-form" in prompt and "article" in prompt:
            return json.dumps(
                {
                    "publishable": False,
                    "worst_ai_sections": [
                        {
                            "para": "It's worth noting",
                            "reason": "filler opener + template scaffolding",
                        }
                    ],
                    "unsupported_claims": [],
                    "template_smell": ["Moreover / Furthermore / Additionally pile-up"],
                    "fake_human_details": [],
                    "best_theses": [],
                    "rewrite_brief": (
                        "Cut filler openers; replace enumeration with prose; "
                        "concretise the value proposition."
                    ),
                }
            )
        return "stub-response"

    return _fn


# ─── Repository paths ────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo_root() -> Path:
    """Absolute path of the humanize-en repo root (parent of ``tests/``)."""
    return REPO_ROOT


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
