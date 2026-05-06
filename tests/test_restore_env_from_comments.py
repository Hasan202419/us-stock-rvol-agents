"""restore_dotenv_active: tiklash va takror bosq."""

from __future__ import annotations

from agents.restore_dotenv_active import active_assignments, build_merge, comment_defaults, rebuild_lines


def test_duplicate_empty_keeps_prior_value() -> None:
    lines = [
        "# OPENAI_API_KEY=fallback-openai-model-xxxxxxxx",
        "OPENAI_API_KEY=good-key-openai-model-xxxxxxxx",
        "",
        'OPENAI_API_KEY=""',
        "OPENAI_API_KEY=",
    ]
    defs = comment_defaults(lines)
    act = active_assignments(lines)
    merged, dups = build_merge(defs, act)
    assert "OPENAI_API_KEY" in dups
    assert merged["OPENAI_API_KEY"].startswith("good-key")
    out, rm = rebuild_lines(lines, merged)
    openai_assigns = [l for l in out if not l.strip().startswith("#") and l.strip().startswith("OPENAI_API_KEY=")]
    assert len(openai_assigns) == 1


def test_all_empty_fallback_to_comment() -> None:
    lines = ["# POLYGON_API_KEY=poly_fallback_xxxxxxxx", "POLYGON_API_KEY=", "POLYGON_API_KEY="]
    merged, _ = build_merge(comment_defaults(lines), active_assignments(lines))
    assert merged["POLYGON_API_KEY"] == "poly_fallback_xxxxxxxx"


def test_github_token_from_comment_when_active_blank() -> None:
    lines = ["# GITHUB_TOKEN=ghp_restore_test_token_xxxxxxxx", "GITHUB_TOKEN="]
    merged, __ = build_merge(comment_defaults(lines), active_assignments(lines))
    assert merged["GITHUB_TOKEN"].startswith("ghp_restore_test")
