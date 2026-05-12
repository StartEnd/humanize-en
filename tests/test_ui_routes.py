"""Pin the route contract of ``humanize-en ui``.

The ``humanize-en ui`` subcommand boots :mod:`humanize_core.web.app`
via the module-level ``app`` singleton — which is constructed by
``create_app()`` **without** a ``templates_dir`` argument. That means
HTMX endpoints and the ``GET /`` route are deliberately not
registered (HTMX UI for EN is plan-M11).

These tests pin that contract in two directions:

1. The JSON API surface a user gets after ``pip install
   humanize-en[ui]`` is exactly what the README claims (no more,
   no less). A future commit that, say, accidentally removes
   ``/api/judge`` will fail here loud and fast.
2. ``GET /`` returning 404 is **expected**, not a bug — until M11
   lands a templates-equipped variant. If you change this, you must
   also update the README quickstart and the CHANGELOG M10 entry.

We use :class:`fastapi.testclient.TestClient` rather than booting
uvicorn so the tests run in <1s and don't need a free port.
"""
from __future__ import annotations

import pytest

# Skip cleanly if the [ui] extra isn't installed — keeps the base
# test suite green for users who only depend on humanize-en for
# detection/polish and never installed FastAPI.
fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")  # TestClient transport.
from fastapi.testclient import TestClient  # noqa: E402
from humanize_core.web.app import app  # noqa: E402

# Routes the README quickstart and the CLI ``ui`` banner promise.
# Keep this list in sync with humanize_en/cli/main.py:cmd_ui.
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

# Routes that exist ONLY when create_app is called with templates_dir.
# Their absence here is the M10 contract; their *presence* would mean
# someone wired in templates and we forgot to either update this list
# or the README's "GET / returns 404" note.
HTMX_ONLY_ROUTES = frozenset(
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


# ─── Positive contract: JSON API surface ─────────────────────────────────


def test_openapi_paths_match_json_contract(client: TestClient) -> None:
    """Every endpoint in EXPECTED_JSON_ROUTES is registered in OpenAPI.

    OpenAPI is the public contract — if the README says ``/api/judge``
    works, ``/openapi.json`` must list it. Drift between the two is
    how docs go stale silently.
    """
    paths = set(client.get("/openapi.json").json()["paths"].keys())
    missing = EXPECTED_JSON_ROUTES - paths
    assert not missing, f"core web app dropped JSON routes: {sorted(missing)}"


def test_no_unexpected_htmx_routes_today(client: TestClient) -> None:
    """No HTMX routes today — those are plan-M11.

    If this test starts failing, the right fix is **not** to update
    HTMX_ONLY_ROUTES — it is to bump M11 to done in the README +
    CHANGELOG and ship the templates that make ``GET /`` work.
    """
    paths = set(client.get("/openapi.json").json()["paths"].keys())
    surprises = HTMX_ONLY_ROUTES & paths
    assert not surprises, (
        f"HTMX routes appeared without a templates_dir-equipped app: "
        f"{sorted(surprises)}. Update README + CHANGELOG (M11 done) "
        f"or revert the route registration."
    )


def test_root_returns_404_until_m11(client: TestClient) -> None:
    """``GET /`` returns 404 by design (no templates wired in)."""
    r = client.get("/")
    assert r.status_code == 404, (
        f"GET / now returns {r.status_code}; if M11 (HTMX UI) is done, "
        f"remove this test and update the M10 CHANGELOG amendment."
    )


def test_health_is_live(client: TestClient) -> None:
    """Sanity: ``/health`` is always live (used by ops probes)."""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_languages_includes_en(client: TestClient) -> None:
    """The EN profile is registered via entry points; ``/api/languages``
    proves the auto-discovery actually fires from a clean process.

    This is the only place the test suite verifies the
    ``[project.entry-points."humanize_core.languages"]`` table in
    ``pyproject.toml`` actually wires the EN profile into the core
    registry. Other tests import ``humanize_en`` directly, which
    triggers the in-package fallback registration in
    ``humanize_en/__init__.py``.
    """
    r = client.get("/api/languages")
    assert r.status_code == 200
    body = r.json()
    assert "en" in body["codes"], (
        f"EN profile missing from /api/languages: {body!r}"
    )
