"""CLI end-to-end coverage for ``humanize_en.cli``.

Mirrors ``humanize-zh/tests/test_cli.py``. Subprocess-driven tests
verify the installed entry point behaves correctly (version, help,
detection JSON, missing-provider errors), and a smaller in-process
block exercises ``main(...)`` directly to keep coverage honest
without spawning a new interpreter per case.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable

# Env vars the LLM autodetect chain looks at. Stripped from every
# subprocess so the test machine's real keys can never bleed into
# CLI tests (which would otherwise hit a live API on ``polish`` /
# ``judge`` and turn the suite non-deterministic).
_PROVIDER_ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "MOONSHOT_API_KEY",
    "GLM_API_KEY",
    "DASHSCOPE_API_KEY",
    "OLLAMA_BASE_URL",
)


def run_cli(
    argv: list[str],
    *,
    repo_root: Path,
    env_overrides: dict | None = None,
) -> subprocess.CompletedProcess:
    """Invoke ``python -m humanize_en.cli`` and capture the result.

    All provider env vars are wiped by default. Tests that *want* a
    detected provider should pass an explicit ``env_overrides``
    mapping. ``HUMANIZE_EN_NO_DOTENV=1`` is always set so the auto
    ``.env`` loader doesn't pull stray keys from the user's cwd or
    home directory and ruin determinism.
    """
    base_env = {**os.environ}
    for k in _PROVIDER_ENV_KEYS:
        base_env.pop(k, None)
    base_env["HUMANIZE_EN_NO_DOTENV"] = "1"
    if env_overrides:
        base_env.update(env_overrides)
    return subprocess.run(
        [PYTHON, "-m", "humanize_en.cli", *argv],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=base_env,
        timeout=30,
        check=False,
    )


# ─── Subprocess-driven entry-point coverage ────────────────────────────────


def test_version(repo_root) -> None:
    r = run_cli(["--version"], repo_root=repo_root)
    assert r.returncode == 0
    assert "humanize-en" in r.stdout


def test_help_lists_subcommands(repo_root) -> None:
    r = run_cli(["--help"], repo_root=repo_root)
    assert r.returncode == 0
    for sub in ["detect", "polish", "judge", "providers", "ui"]:
        assert sub in r.stdout


def test_missing_subcommand_exits_2(repo_root) -> None:
    r = run_cli([], repo_root=repo_root)
    # argparse exits 2 when a required positional (subcommand) is missing.
    assert r.returncode == 2


def test_unknown_subcommand_exits_2(repo_root) -> None:
    r = run_cli(["nonsense"], repo_root=repo_root)
    assert r.returncode == 2


def test_providers_no_env(repo_root) -> None:
    r = run_cli(["providers"], repo_root=repo_root)
    assert r.returncode == 0
    assert "(not set)" in r.stdout
    assert "openai" in r.stdout and "anthropic" in r.stdout


def test_providers_detects_fake_deepseek(repo_root) -> None:
    r = run_cli(
        ["providers"],
        repo_root=repo_root,
        env_overrides={"DEEPSEEK_API_KEY": "sk-fake"},
    )
    assert r.returncode == 0
    assert "deepseek" in r.stdout
    assert "available" in r.stdout


def test_detect_text_output(repo_root, tmp_path, ai_article_en) -> None:
    tmp = tmp_path / "a.md"
    tmp.write_text(ai_article_en, encoding="utf-8")
    r = run_cli(["detect", str(tmp)], repo_root=repo_root)
    assert r.returncode == 0, r.stderr
    assert "rule:" in r.stdout
    assert "ngram:" in r.stdout
    assert "combined:" in r.stdout


def test_detect_json_output(repo_root, tmp_path, ai_article_en) -> None:
    tmp = tmp_path / "a.md"
    tmp.write_text(ai_article_en, encoding="utf-8")
    r = run_cli(["detect", str(tmp), "--json"], repo_root=repo_root)
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["rule"]["probability"] > 0
    assert payload["combined"]["probability"] > 0
    assert isinstance(payload["rule"]["violations"], list)


def test_detect_missing_file(repo_root) -> None:
    r = run_cli(["detect", "/nonexistent.md"], repo_root=repo_root)
    assert r.returncode == 2
    assert "file not found" in r.stderr


def test_detect_not_a_file(repo_root, tmp_path) -> None:
    r = run_cli(["detect", str(tmp_path)], repo_root=repo_root)
    assert r.returncode == 2
    assert "not a file" in r.stderr


def test_polish_without_provider_fails(repo_root, tmp_path, ai_article_en) -> None:
    tmp = tmp_path / "a.md"
    tmp.write_text(ai_article_en, encoding="utf-8")
    r = run_cli(["polish", str(tmp)], repo_root=repo_root)
    assert r.returncode == 1
    assert "no LLM provider" in r.stderr


def test_polish_unknown_provider_fails(repo_root, tmp_path, ai_article_en) -> None:
    tmp = tmp_path / "a.md"
    tmp.write_text(ai_article_en, encoding="utf-8")
    r = run_cli(
        ["polish", str(tmp), "--provider", "openai"],
        repo_root=repo_root,
    )
    # OPENAI_API_KEY is wiped, so explicit --provider openai resolves to "unavailable".
    assert r.returncode == 1
    assert "not available" in r.stderr


def test_judge_without_provider_fails(repo_root, tmp_path, ai_article_en) -> None:
    tmp = tmp_path / "a.md"
    tmp.write_text(ai_article_en, encoding="utf-8")
    r = run_cli(["judge", str(tmp)], repo_root=repo_root)
    assert r.returncode == 1
    assert "no LLM provider" in r.stderr


# ─── In-process tests (improve coverage of humanize_en.cli.main) ───────────
#
# These bypass subprocess so coverage.py can see the lines executed
# inside ``cmd_detect`` / ``cmd_polish`` / ``cmd_judge``. We rely on
# the autouse ``_clear_llm_between_tests`` fixture defined in
# ``conftest.py`` to keep the provider singleton clean.


def test_in_process_parser_builds() -> None:
    from humanize_en.cli.main import build_parser

    parser = build_parser()
    args = parser.parse_args(["detect", "foo.md", "--json"])
    assert args.command == "detect"
    assert args.file == "foo.md"
    assert args.json is True


def test_in_process_parser_polish_defaults() -> None:
    from humanize_en.cli.main import build_parser

    parser = build_parser()
    args = parser.parse_args(["polish", "foo.md"])
    assert args.command == "polish"
    assert args.scene == "analysis"
    assert args.provider is None
    assert args.out is None


def test_in_process_detect_command(tmp_path, ai_article_en, capsys) -> None:
    from humanize_en.cli.main import main

    tmp = tmp_path / "a.md"
    tmp.write_text(ai_article_en, encoding="utf-8")
    code = main(["detect", str(tmp), "--json"])
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["rule"]["probability"] > 0


def test_in_process_detect_text_output(tmp_path, ai_article_en, capsys) -> None:
    """Non-JSON detect path also runs without exceptions."""
    from humanize_en.cli.main import main

    tmp = tmp_path / "a.md"
    tmp.write_text(ai_article_en, encoding="utf-8")
    code = main(["detect", str(tmp)])
    assert code == 0
    out = capsys.readouterr().out
    assert "AI detection report" in out
    assert "rule:" in out


def test_in_process_providers_command(capsys) -> None:
    from humanize_en.cli.main import main

    code = main(["providers"])
    assert code == 0
    out = capsys.readouterr().out
    assert "openai" in out and "deepseek" in out


def test_in_process_polish_uses_active_llm(
    tmp_path, ai_article_en, fake_polish_fn, capsys
) -> None:
    """End-to-end polish path with a callable provider, no real LLM."""
    from humanize_en import llm
    from humanize_en.cli.main import main

    tmp = tmp_path / "a.md"
    tmp.write_text(ai_article_en, encoding="utf-8")
    llm.use_callable(fake_polish_fn, name="in-proc", model="v1")
    out_path = tmp_path / "out.md"
    code = main(["polish", str(tmp), "-o", str(out_path)])
    assert code == 0
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8").strip()  # non-empty


def test_in_process_judge_uses_active_llm(
    tmp_path, ai_article_en, fake_judge_fn, capsys
) -> None:
    from humanize_en import llm
    from humanize_en.cli.main import main

    tmp = tmp_path / "a.md"
    tmp.write_text(ai_article_en, encoding="utf-8")
    llm.use_callable(fake_judge_fn, name="in-proc-j", model="v1")
    out_path = tmp_path / "judge.md"
    code = main(["judge", str(tmp), "-o", str(out_path)])
    assert code == 0
    assert out_path.exists()


def test_in_process_judge_json_uses_active_llm(
    tmp_path, ai_article_en, fake_judge_fn, capsys
) -> None:
    """``judge --json`` prints valid JSON and writes the JSON to ``-o``."""
    from humanize_en import llm
    from humanize_en.cli.main import main

    tmp = tmp_path / "a.md"
    tmp.write_text(ai_article_en, encoding="utf-8")
    llm.use_callable(fake_judge_fn, name="in-proc-j", model="v1")
    out_path = tmp_path / "judge.json"
    code = main(["judge", str(tmp), "--json", "-o", str(out_path)])
    assert code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert "publishable" in payload


# ─── .env loader unit tests ─────────────────────────────────────────────────


def test_load_dotenv_sets_unset_vars(tmp_path, monkeypatch) -> None:
    from humanize_en.cli.main import _load_dotenv

    monkeypatch.delenv("HUMANIZE_EN_CLI_TEST_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "HUMANIZE_EN_CLI_TEST_KEY=secret\n"
        '# comment line should be skipped\n'
        '\n'
        'HUMANIZE_EN_CLI_TEST_QUOTED="quoted value"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("HUMANIZE_EN_CLI_TEST_QUOTED", raising=False)
    n = _load_dotenv(env)
    assert n == 2
    assert os.environ["HUMANIZE_EN_CLI_TEST_KEY"] == "secret"
    assert os.environ["HUMANIZE_EN_CLI_TEST_QUOTED"] == "quoted value"


def test_load_dotenv_does_not_override(tmp_path, monkeypatch) -> None:
    from humanize_en.cli.main import _load_dotenv

    monkeypatch.setenv("HUMANIZE_EN_CLI_PREEXISTING", "original")
    env = tmp_path / ".env"
    env.write_text("HUMANIZE_EN_CLI_PREEXISTING=override\n", encoding="utf-8")
    n = _load_dotenv(env)
    assert n == 0
    assert os.environ["HUMANIZE_EN_CLI_PREEXISTING"] == "original"


def test_load_dotenv_missing_file_returns_zero(tmp_path) -> None:
    from humanize_en.cli.main import _load_dotenv

    n = _load_dotenv(tmp_path / "does-not-exist.env")
    assert n == 0
