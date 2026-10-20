"""Tests for agent/llm.py helpers (no network calls)."""

import pytest

from agent.llm import (
    AnthropicLLM,
    LLMError,
    OpenAICompatibleLLM,
    check_not_truncated,
    get_llm,
    parse_json,
)


def test_plain_model_name_goes_to_local_ollama() -> None:
    llm = get_llm("qwen2.5-coder:7b")
    assert isinstance(llm, OpenAICompatibleLLM)
    assert llm.model == "qwen2.5-coder:7b"


def test_groq_prefix_needs_its_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        get_llm("groq/llama-3.3-70b-versatile")


def test_groq_prefix_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test")
    assert get_llm("groq/llama-3.3-70b-versatile").model == "llama-3.3-70b-versatile"


def test_claude_models_use_the_anthropic_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert isinstance(get_llm("claude-opus-5-5"), AnthropicLLM)


def test_parse_json_accepts_code_fences() -> None:
    assert parse_json('```json\n{"sql": "SELECT 1"}\n```') == {"sql": "SELECT 1"}


@pytest.mark.parametrize("text", ["not json", "[1, 2]"])
def test_parse_json_rejects_non_objects(text: str) -> None:
    with pytest.raises(LLMError):
        parse_json(text)


def test_truncated_prompt_is_detected() -> None:
    with pytest.raises(LLMError, match="truncated"):
        check_not_truncated("x" * 20_000, prompt_tokens=2_000)


def test_complete_prompt_passes() -> None:
    check_not_truncated("x" * 20_000, prompt_tokens=4_800)
