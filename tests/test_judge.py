"""humanize_en.judge — EN format_report rendering + judge shim + _parse_json edges.

Mirrors humanize-zh/tests/test_judge.py adapted for English UI strings.
"""
from __future__ import annotations

import json

from humanize_core.judge import _parse_json
from humanize_core.llm.callable_provider import CallableProvider

from humanize_en import llm
from humanize_en.judge import format_report, judge


# ─── judge() shim ────────────────────────────────────────────────────────────


def test_en_judge_with_callable(ai_article_en, fake_judge_fn) -> None:
    llm.use_callable(fake_judge_fn, name="fake-judge", model="j1")
    result = judge(ai_article_en)
    assert "_error" not in result, result
    assert result["publishable"] is False
    assert result["_meta"]["judge_provider"] == "fake-judge::j1"


def test_collusion_same_provider_rejected(ai_article_en, fake_polish_fn, fake_judge_fn) -> None:
    writer = CallableProvider(fake_polish_fn, name="same", model="m1")
    judge_p = CallableProvider(fake_judge_fn, name="same", model="m1")
    result = judge(ai_article_en, writer_provider=writer, judge_provider=judge_p)
    assert "_error" in result
    assert "Collusion" in result["_error"]


def test_allow_self_judge_bypasses_collusion(ai_article_en, fake_polish_fn, fake_judge_fn) -> None:
    writer = CallableProvider(fake_polish_fn, name="same", model="m1")
    judge_p = CallableProvider(fake_judge_fn, name="same", model="m1")
    result = judge(
        ai_article_en,
        writer_provider=writer,
        judge_provider=judge_p,
        allow_self_judge=True,
    )
    assert "_error" not in result


def test_unconfigured_returns_error(ai_article_en) -> None:
    result = judge(ai_article_en)
    assert "_error" in result
    assert "no judge provider" in result["_error"]


def test_different_writer_and_judge_ok(ai_article_en, fake_polish_fn, fake_judge_fn) -> None:
    w = CallableProvider(fake_polish_fn, name="writer", model="w1")
    j = CallableProvider(fake_judge_fn, name="judger", model="j1")
    result = judge(ai_article_en, writer_provider=w, judge_provider=j)
    assert "_error" not in result, result
    assert result["_meta"]["writer_provider"] == "writer::w1"
    assert result["_meta"]["judge_provider"] == "judger::j1"


def test_judge_result_has_required_fields(ai_article_en, fake_judge_fn) -> None:
    llm.use_callable(fake_judge_fn, name="j", model="j1")
    result = judge(ai_article_en)
    for field in [
        "publishable", "worst_ai_sections", "unsupported_claims",
        "template_smell", "fake_human_details", "best_theses", "rewrite_brief",
    ]:
        assert field in result, f"missing field: {field}"


def test_judge_non_json_llm_returns_parse_error(ai_article_en) -> None:
    llm.use_callable(lambda _: "I think the article is fine.", name="prose", model="m1")
    result = judge(ai_article_en)
    assert "_parse_error" in result


def test_judge_empty_llm_returns_dict(ai_article_en) -> None:
    llm.use_callable(lambda _: "", name="empty", model="m1")
    result = judge(ai_article_en)
    assert isinstance(result, dict)


# ─── _parse_json edge cases ──────────────────────────────────────────────────


def test_parse_json_plain_object() -> None:
    assert _parse_json('{"publishable": true}') == {"publishable": True}


def test_parse_json_strips_markdown_fence() -> None:
    raw = '```json\n{"publishable": false, "best_theses": ["x"]}\n```'
    parsed = _parse_json(raw)
    assert parsed["publishable"] is False


def test_parse_json_handles_trailing_prose() -> None:
    raw = 'Here is the output:\n\n{"publishable": true}\n\nDone.'
    assert _parse_json(raw) == {"publishable": True}


def test_parse_json_returns_error_on_pure_prose() -> None:
    parsed = _parse_json("This is just commentary with no JSON at all.")
    assert "_parse_error" in parsed
    assert parsed["_parse_error"] == "no json found"


def test_parse_json_returns_error_on_array() -> None:
    parsed = _parse_json(json.dumps([1, 2, 3]))
    assert "_parse_error" in parsed


def test_parse_json_returns_error_on_malformed() -> None:
    parsed = _parse_json('{"unterminated: "yes')
    assert "_parse_error" in parsed


def test_parse_json_empty_returns_empty_dict() -> None:
    assert _parse_json("") == {}


def test_parse_json_clips_raw_at_500_chars() -> None:
    parsed = _parse_json("x" * 5000)
    assert "_parse_error" in parsed
    assert len(parsed["_raw"]) <= 500


# ─── format_report rendering ────────────────────────────────────────────────


def test_format_report_error_path() -> None:
    rendered = format_report({"_error": "no judge provider"})
    assert "[judge] error" in rendered
    assert "no judge provider" in rendered


def test_format_report_parse_error_path() -> None:
    rendered = format_report({"_parse_error": "bad json", "_raw": "garbage"})
    assert "JSON parse failure" in rendered
    assert "garbage" in rendered


def test_format_report_publishable_yes() -> None:
    rendered = format_report({"publishable": True, "best_theses": ["Thesis A"]})
    assert "publishable" in rendered
    assert "Thesis A" in rendered


def test_format_report_publishable_no() -> None:
    rendered = format_report({"publishable": False})
    assert "needs revision" in rendered


def test_format_report_worst_sections_as_dicts() -> None:
    rendered = format_report({
        "publishable": False,
        "worst_ai_sections": [
            {"para": "It's worth noting", "reason": "filler opener"},
        ],
    })
    assert "AI-flavoured" in rendered
    assert "It's worth noting" in rendered
    assert "filler opener" in rendered


def test_format_report_worst_sections_as_strings() -> None:
    rendered = format_report({
        "publishable": False,
        "worst_ai_sections": ["Opening is pure AI boilerplate"],
    })
    assert "Opening is pure AI boilerplate" in rendered


def test_format_report_unsupported_claims_dict_and_string() -> None:
    rendered = format_report({
        "publishable": False,
        "unsupported_claims": [
            {"claim": "200% growth", "missing_evidence": "no source link"},
            "Another unsupported assertion",
        ],
    })
    assert "Unsupported claims" in rendered
    assert "200% growth" in rendered
    assert "no source link" in rendered
    assert "Another unsupported assertion" in rendered


def test_format_report_template_smell_and_fake_human() -> None:
    rendered = format_report({
        "publishable": False,
        "template_smell": ["Moreover/Furthermore/Additionally pile-up"],
        "fake_human_details": ["The 3 AM coffee anecdote"],
    })
    assert "Template-smell" in rendered
    assert "Moreover/Furthermore" in rendered
    assert "Fabricated human details" in rendered
    assert "High risk" in rendered


def test_format_report_rewrite_brief() -> None:
    rendered = format_report({
        "publishable": False,
        "rewrite_brief": "Cut filler openers; replace enumeration with prose.",
    })
    assert "Rewrite brief" in rendered
    assert "Cut filler openers" in rendered


def test_format_report_meta_footer() -> None:
    rendered = format_report({
        "publishable": True,
        "_meta": {
            "judge_provider": "fake-judge::j1",
            "writer_provider": "fake-writer::w1",
            "article_length": 3210,
        },
    })
    assert "fake-judge::j1" in rendered
    assert "fake-writer::w1" in rendered
    assert "3,210" in rendered
