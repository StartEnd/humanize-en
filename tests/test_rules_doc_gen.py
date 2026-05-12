"""Tests for ``scripts/gen_rules_doc.py`` — the plan-M9 deliverable.

Pins three things:

1. **Idempotency** — running the generator twice on the same input
   produces byte-identical output.
2. **Sync with checked-in docs** — ``docs/rules.md`` on disk must
   already reflect the current ``rules.json``. This is the CI gate
   that ``make rules-doc-check`` enforces.
3. **Surface coverage** — every category and every rule named in
   ``rules.json`` shows up in the rendered doc (the generator's
   purpose is to make the JSON discoverable, so dropping a rule
   silently would defeat it).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "gen_rules_doc.py"
RULES_JSON = REPO_ROOT / "humanize_en" / "_lang" / "en" / "data" / "rules.json"
RULES_MD = REPO_ROOT / "docs" / "rules.md"


@pytest.fixture(scope="module")
def gen_module():
    """Import ``gen_rules_doc.py`` as a module (it lives outside the package)."""
    spec = importlib.util.spec_from_file_location("gen_rules_doc", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_rules_doc"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rules() -> dict:
    return json.loads(RULES_JSON.read_text(encoding="utf-8"))


# ─── 1. Idempotency ────────────────────────────────────────────────────


def test_render_is_idempotent(gen_module, rules) -> None:
    """``render_rules_doc(rules)`` must return identical bytes on repeated
    calls — the function is pure and the rules dict is read-only."""
    a = gen_module.render_rules_doc(rules)
    b = gen_module.render_rules_doc(rules)
    assert a == b


def test_render_is_deterministic_across_dict_orderings(gen_module, rules) -> None:
    """Re-serialising the rules dict through JSON (which preserves Python
    3.7+ insertion order) should not perturb the output. This catches
    accidental ``set()`` iteration in the renderer."""
    a = gen_module.render_rules_doc(rules)
    re_serialised = json.loads(json.dumps(rules))
    b = gen_module.render_rules_doc(re_serialised)
    assert a == b


# ─── 2. On-disk sync gate ──────────────────────────────────────────────


def test_disk_doc_matches_current_rules_json(gen_module, rules) -> None:
    """``docs/rules.md`` on disk must already reflect ``rules.json``.

    If this fails, run ``make rules-doc`` (or
    ``uv run python scripts/gen_rules_doc.py``) and commit the
    result. Same check as ``make rules-doc-check``, just runnable
    from the test suite so CI catches drift even without a separate
    make-step.
    """
    expected = gen_module.render_rules_doc(rules)
    actual = RULES_MD.read_text(encoding="utf-8")
    assert actual == expected, (
        "docs/rules.md is out of sync with rules.json. "
        "Run `make rules-doc` and commit."
    )


# ─── 3. Surface coverage ───────────────────────────────────────────────


CATEGORY_NAMES = (
    "blacklist_words",
    "blacklist_phrases",
    "structural_rules",
    "rhythm_rules",
    "fake_human",
    "soul_signals",
)


def test_every_category_appears(gen_module, rules) -> None:
    out = gen_module.render_rules_doc(rules)
    for cat in CATEGORY_NAMES:
        assert f"`{cat}`" in out, f"category {cat!r} missing from rendered doc"


def test_every_rule_name_appears(gen_module, rules) -> None:
    """Each rule name (except the ``_desc`` / ``_meta`` housekeeping
    keys) must surface as a heading. This is the contract: the
    doc must be a complete index of the JSON."""
    out = gen_module.render_rules_doc(rules)
    missing: list[str] = []
    for cat in CATEGORY_NAMES:
        for rule in rules.get(cat, {}):
            if rule.startswith("_"):
                continue
            if f"`{rule}`" not in out:
                missing.append(f"{cat}.{rule}")
    assert not missing, f"rules missing from doc: {missing}"


def test_metadata_block_present(gen_module, rules) -> None:
    out = gen_module.render_rules_doc(rules)
    meta = rules.get("_meta", {})
    if "version" in meta:
        assert f"`{meta['version']}`" in out
    if "milestone" in meta:
        assert f"`{meta['milestone']}`" in out


def test_auto_generated_banner_present(gen_module, rules) -> None:
    """The doc must self-identify as auto-generated so contributors
    don't waste time editing it by hand."""
    out = gen_module.render_rules_doc(rules)
    assert "Auto-generated" in out
    assert "scripts/gen_rules_doc.py" in out


def test_total_rule_count_correct(gen_module, rules) -> None:
    out = gen_module.render_rules_doc(rules)
    expected_total = sum(
        len([k for k in rules.get(cat, {}) if not k.startswith("_")])
        for cat in CATEGORY_NAMES
    )
    assert f"Total rules: **{expected_total}**" in out


# ─── 4. CLI --check mode ───────────────────────────────────────────────


def test_check_mode_passes_in_sync_state(gen_module, tmp_path) -> None:
    """``--check`` on a freshly generated doc must exit 0."""
    rules_data = json.loads(RULES_JSON.read_text(encoding="utf-8"))
    out_path = tmp_path / "rules.md"
    out_path.write_text(gen_module.render_rules_doc(rules_data), encoding="utf-8")

    sys_argv_backup = sys.argv[:]
    sys.argv = [
        "gen_rules_doc.py",
        "--rules", str(RULES_JSON),
        "--out", str(out_path),
        "--check",
    ]
    try:
        rc = gen_module.main()
    finally:
        sys.argv = sys_argv_backup
    assert rc == 0


def test_check_mode_fails_when_doc_stale(gen_module, tmp_path) -> None:
    """``--check`` against an out-of-date doc must exit non-zero."""
    out_path = tmp_path / "stale.md"
    out_path.write_text("# stale stub\n", encoding="utf-8")

    sys_argv_backup = sys.argv[:]
    sys.argv = [
        "gen_rules_doc.py",
        "--rules", str(RULES_JSON),
        "--out", str(out_path),
        "--check",
    ]
    try:
        rc = gen_module.main()
    finally:
        sys.argv = sys_argv_backup
    assert rc == 1
