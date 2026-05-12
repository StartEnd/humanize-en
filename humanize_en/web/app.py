"""humanize_en.web.app — FastAPI application factory (M11 step 1).

Thin shim over :func:`humanize_core.web.app.create_app` that hands
in this package's ``templates/`` directory so the core's HTMX
endpoints (``GET /``, ``/htmx/{detect,polish,oneshot,oneshot-loop,
judge}``) register and render English fragments.

The actual route handlers live in ``humanize_core.web.app`` — the
factory closes over ``templates_dir`` and binds it to the
:class:`fastapi.templating.Jinja2Templates` instance used by every
``TemplateResponse``. By keeping this file thin we get
language-routing for free (the core uses a ``lang`` form field on
every HTMX endpoint) and any plumbing fix the framework ships also
benefits the EN UI without a code change here.

M11 is intentionally split across multiple commits:

- **Step 1 (this commit).** Minimal stubs for ``index.html`` and
  ``_error.html`` so the architecture compiles end-to-end: the
  factory registers all HTMX routes, ``GET /`` returns 200, and
  ``tests/test_web_app.py`` pins the contract.
- **Steps 2-3.** Port humanize-zh's 9 templates verbatim, then
  translate copy + replace Chinese-service references.
- **Step 5.** Repoint ``humanize_en/cli/main.py:cmd_ui`` from
  ``humanize_core.web.app:app`` (JSON-only) to
  ``humanize_en.web.app:app`` (this module), update README +
  CHANGELOG to reflect the new default surface.

Until step 5 lands, this subpackage is reachable only via direct
import (``python -c "from humanize_en.web.app import app"``) and
via the future ``python -m humanize_en.web`` entry point — the
``humanize-en ui`` CLI still serves the JSON-only core app, exactly
as the M10 amendment in ``CHANGELOG.md`` documents.
"""
from __future__ import annotations

from pathlib import Path

try:
    from fastapi import FastAPI
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "humanize-en web UI requires the 'ui' extra. "
        "Run: pip install 'humanize-en[ui]'"
    ) from e

from humanize_core.web.app import create_app as _core_create_app

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"


def create_app() -> FastAPI:
    """Build the EN FastAPI app with HTMX templates wired in.

    Returns the :class:`fastapi.FastAPI` instance produced by
    :func:`humanize_core.web.app.create_app` with this package's
    ``templates/`` dir handed in. Unlike the core's module-level
    ``app = create_app()`` (which deliberately gets ``templates_dir=None``
    so the JSON API stays language-neutral), this factory always
    registers the HTMX routes.

    Re-exported as :data:`humanize_en.web.app` for easy uvicorn
    string-targeting (``humanize_en.web.app:app``).
    """
    return _core_create_app(templates_dir=TEMPLATES_DIR)


# Module-level singleton so ``uvicorn humanize_en.web.app:app`` and
# ``humanize-en ui`` (post-step-5) both work without forcing callers
# to call create_app() themselves.
app = create_app()


__all__ = ["app", "create_app", "TEMPLATES_DIR"]
