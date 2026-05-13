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
  the same factory with ``templates_dir=…`` plumbed in. Serves the
  full ported template kit as of M11 Phase A+B.

A regression in either app should fail in its own test module. Keep
the contracts symmetric so a future ``humanize-fr`` plugin can fork
this file with a one-line edit.

Structure
---------
- Route registration: assert all JSON + HTMX routes are present.
- ``GET /`` contract: 200 HTML with EN translated copy.
- ``/api/languages``: entry-point discovery sanity.
- HTMX 4xx paths: endpoint registration without LLM calls.
- HTMX fragment shape: real pipeline with stub LLM providers from
  conftest (``fake_polish_fn`` / ``fake_judge_fn`` / ``ai_article_en``).
"""
from __future__ import annotations

from collections.abc import Callable

import pytest

# Skip cleanly if the [ui] extra isn't installed. Without fastapi/jinja2
# ``humanize_en.web.app`` will fail to import at the top-level
# ``from fastapi import FastAPI``, so the module-level import below
# would crash the whole test session if we didn't gate it here.
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("jinja2")

from fastapi.testclient import TestClient  # noqa: E402

from humanize_en import llm  # noqa: E402
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


# ─── HTMX endpoint shape (4xx paths — no LLM needed) ──────────────────


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


# ─── HTMX fragment shape (real pipeline with stub providers) ────────────
# These tests wire a deterministic ``llm.use_callable`` provider so we
# can exercise the full detect → template-render path without hitting a
# real LLM. The ``_clear_llm_between_tests`` autouse fixture in
# conftest.py clears the provider before and after each test.


AI_TEXT = (
    "It is worth noting that this comprehensive platform leverages cutting-edge "
    "synergies to deliver value. Moreover, it is important to understand that "
    "the solution is not just about technology — it is about people. "
    "In conclusion, this approach delves into the root causes of the problem "
    "and provides a robust framework for sustainable growth."
)


def test_htmx_detect_returns_score_fragment(client: TestClient) -> None:
    """``POST /htmx/detect`` with real text renders the detect result fragment.

    The detect endpoint is pure Python — no LLM. This test exercises
    the full rule + n-gram pipeline and asserts the result fragment
    contains the score card structure.
    """
    r = client.post("/htmx/detect", data={"text": AI_TEXT, "lang": "en"})
    assert r.status_code == 200, r.content[:300]
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "Rule hits" in body or "rule" in body.lower(), (
        "detect result fragment missing rule score section"
    )
    assert "/100" in body, "score card should show N/100"


def test_htmx_polish_returns_fragment(
    client: TestClient, fake_polish_fn: Callable[[str], str]
) -> None:
    """``POST /htmx/polish`` renders ``_polish_result.html`` with EN copy."""
    llm.use_callable(fake_polish_fn, name="stub-polish", model="v1")
    r = client.post(
        "/htmx/polish",
        data={"text": AI_TEXT, "lang": "en", "scene": "analysis"},
    )
    assert r.status_code == 200, r.content[:300]
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "Polished article" in body, "missing EN result header"
    assert "Copied" in body or "Copy" in body, "missing copy button"
    assert "朱雀" not in body and "润色" not in body, "ZH copy leaked into EN fragment"


def test_htmx_oneshot_returns_fragment(
    client: TestClient, fake_polish_fn: Callable[[str], str]
) -> None:
    """``POST /htmx/oneshot`` renders ``_oneshot_result.html`` with EN copy."""
    llm.use_callable(fake_polish_fn, name="stub-oneshot", model="v1")
    r = client.post(
        "/htmx/oneshot",
        data={"text": AI_TEXT, "lang": "en", "scene": "analysis"},
    )
    assert r.status_code == 200, r.content[:300]
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "Polished article" in body or "Done" in body, "missing result header"
    assert "Re-score" in body or "detect" in body, "missing pipe-to-detect button"
    assert "朱雀" not in body, "ZH service reference leaked"


def test_htmx_judge_returns_fragment(
    client: TestClient, fake_judge_fn: Callable[[str], str]
) -> None:
    """``POST /htmx/judge`` renders ``_judge_result.html`` with EN verdicts."""
    llm.use_callable(fake_judge_fn, name="stub-judge", model="v1")
    r = client.post(
        "/htmx/judge",
        data={"text": AI_TEXT, "lang": "en", "allow_self_judge": "true"},
    )
    assert r.status_code == 200, r.content[:300]
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "Publishable" in body or "Needs revision" in body or "Full report" in body, (
        f"missing EN verdict copy in judge fragment; body[:400]={body[:400]!r}"
    )
    assert "评审" not in body, "ZH copy leaked into EN judge fragment"


def test_htmx_loop_returns_fragment(
    client: TestClient,
    fake_polish_fn: Callable[[str], str],
    fake_judge_fn: Callable[[str], str],
) -> None:
    """``POST /htmx/oneshot-loop`` (1 round) renders ``_loop_result.html``.

    We use ``allow_self_judge=true`` with the single stub provider and
    cap at 1 round so the test finishes quickly (2 LLM calls total).
    """
    llm.use_callable(fake_polish_fn, name="stub-loop", model="v1")
    r = client.post(
        "/htmx/oneshot-loop",
        data={
            "text": AI_TEXT,
            "lang": "en",
            "rounds": "1",
            "target_ai_score": "0",
            "allow_self_judge": "true",
        },
    )
    assert r.status_code == 200, r.content[:300]
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "Per-round trace" in body or "Closed-loop" in body or "round" in body.lower(), (
        f"missing loop fragment structure; body[:400]={body[:400]!r}"
    )
    assert "各轮" not in body, "ZH copy leaked into EN loop fragment"


def test_index_has_en_copy_no_chinese_leakage(client: TestClient) -> None:
    """``GET /`` serves the full translated index page with no Chinese copy."""
    r = client.get("/")
    body = r.text
    for phrase in ("30-second start", "One-shot polish", "GPTZero", "OPENAI_API_KEY"):
        assert phrase in body, f"expected EN phrase missing from index: {phrase!r}"
    for zh in ("朱雀", "中文文章", "公众号", "小红书"):
        assert zh not in body, f"Chinese copy leaked into EN index: {zh!r}"
