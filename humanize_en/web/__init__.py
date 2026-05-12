"""humanize_en.web — FastAPI + Jinja2 + HTMX + Tailwind UI for English.

This subpackage is the **first consumer** of
:func:`humanize_core.web.app.create_app` ``(templates_dir=…)``. The
sibling ZH plugin ships a 430-line standalone FastAPI app that
predates the multi-language factory and does *not* use it — by
building on the factory we exercise the core's plugin-templates
contract for real, and any plumbing rough edges we hit get fixed in
``humanize-core`` rather than papered over here.

Run with::

    humanize-en ui                     # CLI subcommand (recommended)
    python -m humanize_en.web          # equivalent
    uvicorn humanize_en.web.app:app    # production via uvicorn directly

This module ships as part of plan-M11 (see ``docs/plan.md`` §M11 for
the milestone scope, the template-port checklist, and the
``test_ui_routes.py → test_web_app.py`` migration story).
"""
from __future__ import annotations

from .app import app, create_app

__all__ = ["app", "create_app"]
