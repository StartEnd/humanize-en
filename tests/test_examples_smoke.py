"""Smoke tests for ``examples/*.py``.

We don't actually run the LLM-bound examples (02 polish, 03 iterative
loop) in CI — they need network + provider keys — but we **do**
verify that:

1. Every example file compiles cleanly (no SyntaxError, no broken
   imports). This catches the cheap class of bug where someone
   updates ``humanize_en.__init__`` and forgets to bump the
   example to match.
2. The two purely-offline examples (``01_detect_only`` and
   ``04_inject_rules_into_prompt``) actually run end-to-end and
   produce non-trivial output. The README points new users at
   these as the first thing they should try; "first thing breaks
   on a fresh checkout" is the worst possible onboarding.
3. The directory matches the README index (every script listed in
   ``examples/README.md`` exists; every script on disk is listed).
   Mirrors the contract humanize-zh maintains.
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
EXAMPLES_README = EXAMPLES_DIR / "README.md"

# Scripts the README documents (in numeric order — drives the
# parametrised "compiles" test and the README-table consistency
# check). Update both this tuple and the README table together.
EXPECTED_SCRIPTS = (
    "01_detect_only.py",
    "02_polish_with_llm.py",
    "03_iterative_loop.py",
    "04_inject_rules_into_prompt.py",
)

# Scripts that must run end-to-end without an LLM provider. Add
# new no-LLM examples here, not to the LLM-bound list.
NO_LLM_SCRIPTS = (
    "01_detect_only.py",
    "04_inject_rules_into_prompt.py",
)


# ─── 1. Compile-clean ──────────────────────────────────────────────────


@pytest.mark.parametrize("script", EXPECTED_SCRIPTS)
def test_example_compiles(script: str) -> None:
    """Every example imports cleanly under the current package layout.

    We use ``compile(open(...).read(), filename, 'exec')`` rather
    than importing because the example scripts execute their ``main()``
    when imported as ``__main__``; we only want to validate syntax
    + that every ``from humanize_en import ...`` line resolves.
    Importing via ``spec.loader.exec_module`` would also call
    ``main()`` which is what we want to *avoid* for the LLM examples.
    """
    path = EXAMPLES_DIR / script
    src = path.read_text(encoding="utf-8")
    # Step 1: syntax check.
    compile(src, str(path), "exec")
    # Step 2: import resolution check — we walk the AST for top-level
    # ``from humanize_en import ...`` statements and try them out.
    import ast

    tree = ast.parse(src, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "humanize_en":
            for alias in node.names:
                __import__("humanize_en", fromlist=[alias.name])
                module = sys.modules["humanize_en"]
                assert hasattr(module, alias.name), (
                    f"example {script} imports humanize_en.{alias.name} "
                    f"but the package does not expose it"
                )


# ─── 2. End-to-end smoke (no-LLM only) ─────────────────────────────────


@pytest.mark.parametrize("script", NO_LLM_SCRIPTS)
def test_no_llm_example_runs_clean(script: str) -> None:
    """The example ``main()`` runs without raising and prints
    *something*. We invoke the script as a subprocess so its
    ``sys.path`` manipulation (``insert(0, ...)``) takes effect
    exactly as the user would experience it.
    """
    path = EXAMPLES_DIR / script
    result = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"example {script} failed (rc={result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert result.stdout.strip(), (
        f"example {script} ran but produced no stdout — likely a "
        f"silent early-return regression"
    )


# ─── 3. README ↔ filesystem consistency ────────────────────────────────


def test_every_documented_script_exists() -> None:
    """Every script listed in ``EXPECTED_SCRIPTS`` is on disk."""
    missing = [s for s in EXPECTED_SCRIPTS if not (EXAMPLES_DIR / s).exists()]
    assert not missing, f"missing example files: {missing}"


def test_every_on_disk_script_is_documented() -> None:
    """No mystery scripts in ``examples/`` — every ``.py`` file is in
    ``EXPECTED_SCRIPTS`` (and therefore in the README table)."""
    on_disk = sorted(p.name for p in EXAMPLES_DIR.glob("*.py"))
    extras = set(on_disk) - set(EXPECTED_SCRIPTS)
    assert not extras, (
        f"undocumented scripts in examples/: {extras} — "
        f"add them to examples/README.md and EXPECTED_SCRIPTS"
    )


def test_readme_table_references_each_script() -> None:
    """The README table must mention each expected filename verbatim.

    Sanity-check that the docs and the constants here don't drift.
    """
    readme = EXAMPLES_README.read_text(encoding="utf-8")
    missing = [s for s in EXPECTED_SCRIPTS if s not in readme]
    assert not missing, f"examples/README.md misses scripts: {missing}"


# ─── 4. Smoke-detect that the example's prose actually triggers rules ──


def test_example_01_prose_triggers_detector() -> None:
    """The example 01 article was hand-tuned to be a deliberate AI
    sample (paradigm shift, leverage, in conclusion, …). If a
    rule-set refactor mutes it, the example is no longer
    pedagogically useful — catch that here rather than in a
    confused user's GitHub issue.
    """
    # Load the example module's ARTICLE constant directly so we
    # don't have to re-parse stdout.
    spec = importlib.util.spec_from_file_location(
        "_example_01", EXAMPLES_DIR / "01_detect_only.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Patch main() to a no-op so importing doesn't execute it.
    sys.modules["_example_01"] = mod
    try:
        # Suppress any I/O while loading.
        with redirect_stdout(io.StringIO()):
            spec.loader.exec_module(mod)
        from humanize_en import score

        result = score(mod.ARTICLE)
        assert result.total >= 25, (
            f"example 01 article scored {result.total} — too low to "
            f"demonstrate the detector. Did the rule weights change? "
            f"Either retune ARTICLE or relax this lower bound."
        )
    finally:
        sys.modules.pop("_example_01", None)
