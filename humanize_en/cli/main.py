"""humanize_en.cli.main — CLI entry point.

Mirrors :mod:`humanize_zh.cli.main` so contributors who know one
plugin's CLI can read the other without context-switching. The main
differences vs the ZH CLI are:

- The ``--lang`` flag is **gone**: the EN plugin is mono-language by
  construction (its shims pin ``lang="en"``). To polish Chinese,
  install ``humanize-zh``.
- ``humanize-en ui`` boots :mod:`humanize_en.web.app`, which serves
  the **full HTMX + JSON API** (plan-M11, shipped). Open the printed
  URL in a browser for the single-page UI; the ``/api/...`` endpoints
  are also available for programmatic use.
- ``.humanize-en.env`` (or ``HUMANIZE_EN_NO_DOTENV=1`` to opt out).

Usage::

    humanize-en detect FILE [--json] [--has-notes]
    humanize-en polish FILE [-o OUT] [--scene analysis] [--provider NAME]
    humanize-en judge  FILE [-o OUT] [--writer NAME] [--judge NAME] [--json]
                            [--allow-self-judge]
    humanize-en providers                  # list auto-detectable providers
    humanize-en ui                          # HTMX web UI + JSON API

Global options:
    -v/--verbose     INFO-level logs
    --version        print version and exit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import NoReturn

from .. import __version__
from .. import llm as _llm_module
from ..combined import combined_score
from ..detect import score
from ..judge import format_report as format_judge_report
from ..judge import judge
from ..ngram_check import ngram_score
from ..postprocess import postprocess_humanize

logger = logging.getLogger("humanize_en")


# ─── Helpers ────────────────────────────────────────────────────────────────

def _read_file(path_str: str) -> tuple[Path, str]:
    path = Path(path_str)
    if not path.exists():
        _die(f"file not found: {path}", code=2)
    if not path.is_file():
        _die(f"not a file: {path}", code=2)
    try:
        return path, path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        _die(f"cannot read {path} as UTF-8: {e}", code=2)


def _die(msg: str, code: int = 1) -> NoReturn:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def _ensure_provider(name: str | None = None) -> None:
    """Ensure an LLM provider is active. Try explicit name first, then autodetect."""
    if _llm_module.has_active():
        return
    if name:
        detected = _llm_module.autodetect(prefer=[name])
        if detected is None:
            _die(
                f"provider {name!r} not available from env. Set its API key "
                f"or pass an LLMProvider instance via SDK."
            )
        return
    if _llm_module.autodetect() is None:
        _die(
            "no LLM provider configured. Set one of "
            f"{_llm_module.required_env_keys_hint()}."
        )


# ─── detect ─────────────────────────────────────────────────────────────────

def cmd_detect(args: argparse.Namespace) -> int:
    path, text = _read_file(args.file)

    rule = score(text, has_notes=args.has_notes)
    try:
        ng = ngram_score(text)
        ng_prob = ng.ai_probability
        ng_level = ng.level
        ng_avail = ng.available
    except Exception as e:  # noqa: BLE001
        logger.warning("ngram check failed: %s", e)
        ng_prob, ng_level, ng_avail = 0.0, "UNAVAILABLE", False

    cs = combined_score(text, has_notes=args.has_notes)

    if args.json:
        payload = {
            "file": str(path),
            "chars": len(text),
            "rule": {
                "probability": rule.total,
                "level": rule.level,
                "violations": [
                    {"category": v.category, "rule": v.rule, "count": v.count, "sample": v.sample}
                    for v in rule.violations
                ],
            },
            "ngram": {
                "probability": ng_prob,
                "level": ng_level,
                "available": ng_avail,
            },
            "combined": {
                "probability": cs.combined_probability,
                "level": cs.combined_level,
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("# AI detection report")
    print(f"file:    {path}")
    print(f"chars:   {len(text):,}")
    print()
    print(f"rule:      {rule.total:>5.1f} / 100  ({rule.level})")
    print(
        f"ngram:     {ng_prob:>5.1f} / 100  ({ng_level})"
        + ("" if ng_avail else "  [resources missing]")
    )
    print(f"combined:  {cs.combined_probability:>5.1f} / 100  ({cs.combined_level})")

    if rule.violations:
        print()
        print("top violations:")
        for v in rule.violations[:10]:
            sample = v.sample[:50] + ("..." if len(v.sample) > 50 else "")
            print(f"  - {v.category}.{v.rule} x{v.count}: {sample!r}")

    return 0


# ─── polish ─────────────────────────────────────────────────────────────────

def cmd_polish(args: argparse.Namespace) -> int:
    _ensure_provider(args.provider)
    path, text = _read_file(args.file)

    out_path = Path(args.out) if args.out else path.with_suffix(".polished.md")

    polished, after, before = postprocess_humanize(
        text,
        scene=args.scene,
        provider=args.provider,
    )
    out_path.write_text(polished, encoding="utf-8")
    print(f"✓ output: {out_path}")

    if before is not None and after is not None:
        delta = before.total - after.total
        print(f"  AI score: {before.total:.1f} → {after.total:.1f} (Δ {delta:+.1f})")

    return 0


# ─── judge ──────────────────────────────────────────────────────────────────

def cmd_judge(args: argparse.Namespace) -> int:
    # If --judge is omitted, judge() pulls the active provider — make sure one exists.
    if args.judge is None:
        _ensure_provider(None)
    path, text = _read_file(args.file)

    result = judge(
        text,
        writer_provider=args.writer,
        judge_provider=args.judge,
        allow_self_judge=args.allow_self_judge,
    )

    out_path = Path(args.out) if args.out else path.with_suffix(".judge.md")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.out:
            out_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\nreport saved: {out_path}", file=sys.stderr)
        return 0 if "_error" not in result else 3

    report = format_judge_report(result)
    print(report)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nreport saved: {out_path}", file=sys.stderr)
    return 0 if "_error" not in result else 3


# ─── ui / providers ─────────────────────────────────────────────────────────

def cmd_ui(args: argparse.Namespace) -> int:
    """Launch the EN HTMX web UI (FastAPI + Jinja2 + HTMX + Tailwind).

    Boots :mod:`humanize_en.web.app`, which calls the core factory
    with ``templates_dir`` pointing at this package's English
    templates. Serves:

    * ``GET /`` — single-page HTMX UI (detect / polish / judge tabs)
    * ``POST /htmx/{detect,polish,oneshot,oneshot-loop,judge}`` —
      HTMX endpoints that return rendered HTML fragments
    * ``/api/detect``, ``/api/polish``, ``/api/judge``,
      ``/api/providers``, ``/api/languages``, ``/health`` —
      JSON API (same surface as the bare core, but the EN profile
      is always registered)
    """
    try:
        import uvicorn
    except ImportError:
        _die(
            "the 'ui' extra is required to run the JSON API server. "
            "Install with: pip install 'humanize-en[ui]'"
        )
    print(f"humanize-en UI: http://{args.host}:{args.port}/")
    uvicorn.run(
        "humanize_en.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def cmd_providers(args: argparse.Namespace) -> int:
    """List providers auto-detectable from environment variables."""
    rows = _llm_module.list_providers()
    print(f"{'provider':<12} {'env var':<22} {'status':<12}")
    print("-" * 48)
    available = []
    for row in rows:
        marker = "✓ available" if row["available"] else "  (not set)"
        print(f"{row['name']:<12} {row['env']:<22} {marker}")
        if row["available"]:
            available.append(row["name"])
    print()
    if available:
        print(f"active provider will autodetect in order: {available[0]}")
    else:
        print("no providers detected. Set at least one env var above.")
    return 0


# ─── Main parser ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="humanize-en",
        description="English AI text humanization — detect / polish / judge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  humanize-en detect article.md\n"
            "  humanize-en polish article.md -o polished.md --provider deepseek\n"
            "  humanize-en judge  article.md --writer deepseek --judge anthropic\n"
            "  humanize-en providers\n"
            "  humanize-en ui                # JSON API (HTMX UI is plan-M11)\n"
        ),
    )
    p.add_argument("--version", action="version", version=f"humanize-en {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="enable INFO logging")
    sub = p.add_subparsers(dest="command", required=True)

    # detect
    sp = sub.add_parser("detect", help="rule + ngram + combined detection")
    sp.add_argument("file", help="path to .md / .txt file")
    sp.add_argument("--json", action="store_true", help="emit JSON")
    sp.add_argument(
        "--has-notes",
        action="store_true",
        help="article has companion notes (relaxes fake_human-style rules)",
    )
    sp.set_defaults(func=cmd_detect)

    # polish
    sp = sub.add_parser("polish", help="LLM polish — strip AI tells")
    sp.add_argument("file", help="path to .md / .txt file")
    sp.add_argument("-o", "--out", help="output path (default: <file>.polished.md)")
    sp.add_argument(
        "--scene",
        default="analysis",
        choices=["analysis", "essay", "academic", "blog"],
        help="writing scene preset",
    )
    sp.add_argument(
        "--provider",
        default=None,
        help="provider name (openai/anthropic/deepseek/...)",
    )
    sp.set_defaults(func=cmd_polish)

    # judge
    sp = sub.add_parser("judge", help="LLM final-review verdict")
    sp.add_argument("file", help="path to .md / .txt file")
    sp.add_argument("-o", "--out", help="output report path")
    sp.add_argument(
        "--writer",
        default=None,
        help="writer provider (collusion check only)",
    )
    sp.add_argument("--judge", default=None, help="judge provider")
    sp.add_argument("--json", action="store_true", help="emit JSON instead of report")
    sp.add_argument(
        "--allow-self-judge",
        action="store_true",
        help="allow writer == judge (not recommended)",
    )
    sp.set_defaults(func=cmd_judge)

    # providers
    sp = sub.add_parser("providers", help="list auto-detectable providers")
    sp.set_defaults(func=cmd_providers)

    # ui — HTMX web UI + JSON API (M11 shipped).
    sp = sub.add_parser(
        "ui",
        help="launch the HTMX web UI + JSON API server",
    )
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument(
        "--reload",
        action="store_true",
        help="auto-reload on code change (dev only)",
    )
    sp.set_defaults(func=cmd_ui)

    return p


def _load_dotenv(path: Path) -> int:
    """Minimal .env loader — sets variables not already in os.environ. Returns # of vars set.

    Format::

        KEY=value
        KEY="quoted value"
        # comment
    """
    if not path.is_file():
        return 0
    n = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    # Auto-load ./.env and ~/.humanize-en.env if present (SaaS-friendly).
    # Set HUMANIZE_EN_NO_DOTENV=1 to disable (used by tests).
    if os.environ.get("HUMANIZE_EN_NO_DOTENV") != "1":
        cwd_env = Path.cwd() / ".env"
        home_env = Path.home() / ".humanize-en.env"
        loaded = _load_dotenv(cwd_env) + _load_dotenv(home_env)
    else:
        loaded = 0

    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
    )
    if loaded and args.verbose:
        logger.info("[humanize-en] loaded %d vars from .env files", loaded)

    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        print("\n[humanize-en] interrupted", file=sys.stderr)
        return 130
    except Exception as e:  # noqa: BLE001
        if args.verbose:
            logger.exception("unexpected error")
        else:
            print(f"error: {e}", file=sys.stderr)
            print("run with -v to see the full traceback", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
