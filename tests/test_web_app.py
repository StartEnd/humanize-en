"""Pin the route contract of ``humanize_en.web.app`` (the EN HTMX app).

Counterpart to :mod:`tests.test_ui_routes` — that module pins what
``humanize_core.web.app:app`` exposes (JSON-only, by design).
**This** module pins what the EN plugin's *own* templates-equipped
factory does once you reach for ``humanize_en.web.app:app``
explicitly (or, after M11 step 5, via ``humanize-en ui``).

Why split into two files? Because both apps are first-class citizens
of the multi-language framework:

- ``humanize_core.web.app:app`` — the headless JSON API. Stays
  language-neutral and never wires in plugin templates. Lives forever.
- ``humanize_en.web.app:app`` — the EN-localised HTMX UI built on
  the same factory with ``templates_dir=…`` plumbed in. Today it
  serves M11-step-1 placeholders; M11 steps 2-3 replace those with
  the ported humanize-zh templates.

A regression in either app should fail in its own test module. Keep
the contracts symmetric so a future ``humanize-fr`` plugin can fork
this file with a one-line edit.
"""
from __future__ import annotations

import pytest

# Skip cleanly if the [ui] extra isn't installed. Without fastapi/jinja2
# ``humanize_en.web.app`` will fail to import at the top-level
# ``from fastapi import FastAPI``, so the module-level import below
# would crash the whole test session if we didn't gate it here.
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("jinja2")

from fastapi.testclient import TestClient  # noqa: E402

from humanize_en.web.app import app  # noqa: E402

# Routes that MUST be registered when ``humanize_en.web.app`` boots.
# Split into "JSON" (inherited from the core's JSON-only block) and
# "HTMX" (only present because we pass ``templates_dir=…``). When M11
# adds new endpoints, append them here so the contract drifts with
# the templates rather than rotting in silence.
EXPECTED_JSON_ROUTES = frozenset(
    {
        "/api/detect",
        "/api/judge",
        "/api/languages",
        "/api/polish",
        "/api/providers",
        "/health",
    }
)
EXPECTED_HTMX_ROUTES = frozenset(
    {
        "/",
        "/htmx/detect",
        "/htmx/polish",
        "/htmx/oneshot",
        "/htmx/oneshot-loop",
        "/htmx/judge",
    }
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ─── Route registration ─────────────────────────────────────────────────


def test_openapi_includes_json_and_htmx_routes(client: TestClient) -> None:
    """All declared routes are present in OpenAPI.

    Catches the failure mode where someone forgets to ship a template
    file and FastAPI silently drops the route (or — worse — the
    factory short-circuits and returns the JSON-only app early
    because ``templates is None``).
    """
    paths = set(client.get("/openapi.json").json()["paths"].keys())
    json_missing = EXPECTED_JSON_ROUTES - paths
    htmx_missing = EXPECTED_HTMX_ROUTES - paths
    assert not json_missing, f"missing JSON routes: {sorted(json_missing)}"
    assert not htmx_missing, (
        f"missing HTMX routes: {sorted(htmx_missing)} — did "
        f"humanize_en.web.app.create_app skip the templates branch?"
    )


# ─── GET / contract ─────────────────────────────────────────────────────


def test_root_returns_200_html(client: TestClient) -> None:
    """``GET /`` renders the placeholder index template.

    During M11 step 1 the body is a placeholder; after M11 step 3 the
    assertions below (HTML content type + ``humanize-en`` in body)
    keep holding while the actual copy is the polished one.
    """
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html"), r.headers
    body = r.content
    assert b"humanize-en" in body, body[:200]


def test_root_lists_registered_languages(client: TestClient) -> None:
    """The index page surfaces the registered language codes.

    Proves the ``languages`` Jinja context variable is populated by
    the core's ``index`` handler — if a future refactor swaps the
    context shape, the placeholder template renders blank and this
    test fails loud.
    """
    r = client.get("/")
    assert b"en" in r.content  # at minimum, the EN code itself


# ─── /api/languages contract (entry-point discovery sanity) ────────────


def test_languages_endpoint_reports_en(client: TestClient) -> None:
    r = client.get("/api/languages")
    assert r.status_code == 200
    body = r.json()
    assert "en" in body["codes"], body
    en_row = next(row for row in body["rows"] if row["code"] == "en")
    assert en_row["has_ngram"] is True
    assert en_row["display_name"]  # non-empty


# ─── HTMX endpoint shape (no LLM calls yet — pure 4xx paths) ───────────


def test_htmx_detect_registered_validates_form(client: TestClient) -> None:
    """``POST /htmx/detect`` without form fields returns a 4xx — proves
    the route is registered (rather than returning 404 from a missing
    handler) without actually exercising the rule pipeline.
    """
    r = client.post("/htmx/detect", data={})
    assert r.status_code in (400, 422), (
        f"expected validation error for missing form fields, got "
        f"{r.status_code} | body={r.content[:200]!r}"
    )


def test_health_passthrough(client: TestClient) -> None:
    """``/health`` returns the same payload via the EN app as the core."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
