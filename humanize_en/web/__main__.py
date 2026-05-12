"""Allow ``python -m humanize_en.web`` to launch a dev server.

Mirrors :mod:`humanize_zh.web.__main__` so the same muscle memory
works against either plugin. The CLI subcommand ``humanize-en ui``
is the recommended entry point; this module exists for direct
invocation during development (it skips the
``humanize_en.cli.main`` argparse layer entirely).
"""
from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m humanize_en.web",
        description=(
            "Run the humanize-en web UI (FastAPI + Jinja2 + HTMX). "
            "Plan-M11 work-in-progress; until M11 step 5 ships the "
            "full translated template kit, the rendered pages are "
            "placeholder stubs."
        ),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--reload",
        action="store_true",
        help="auto-reload on code change (dev only)",
    )
    args = parser.parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        print(
            "error: 'uvicorn' is required. "
            "Install with: pip install 'humanize-en[ui]'",
            file=sys.stderr,
        )
        return 2

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(f"humanize-en UI: http://{args.host}:{args.port}/")
    uvicorn.run(
        "humanize_en.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
