"""Telegram expandable framework HTML."""

from __future__ import annotations

from agents.telegram_framework_html import (
    ANALYST_LLM_SYSTEM_APPENDIX,
    build_telegram_framework_appendices_html,
)


def test_build_appendices_contains_expandable_and_three_sections() -> None:
    html_out = build_telegram_framework_appendices_html()
    assert "blockquote expandable" in html_out
    assert "Professional analyst" in html_out
    assert "Volume ignition" in html_out
    assert "HASAN AI" in html_out


def test_llm_appendix_non_empty() -> None:
    assert "REASON" in ANALYST_LLM_SYSTEM_APPENDIX
    assert len(ANALYST_LLM_SYSTEM_APPENDIX) > 80
