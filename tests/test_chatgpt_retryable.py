from agents.chatgpt_analyst_agent import _retryable_openai


class _Exc429(Exception):
    status_code = 429


def test_retryable_detects_status_code() -> None:
    assert _retryable_openai(_Exc429()) is True


def test_retryable_false_on_generic() -> None:
    assert _retryable_openai(RuntimeError("boom")) is False
