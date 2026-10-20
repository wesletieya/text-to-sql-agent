"""Common LLM interface with two adapters: OpenAI-compatible (Ollama, Groq, Gemini) and Anthropic.

Every call returns the text plus token counts and latency, so the pipeline can log them
and the evaluation can compute costs from eval/pricing.yaml.
"""

import json
import os
import time
from typing import Any, Protocol

from pydantic import BaseModel

DEFAULT_MAX_TOKENS = 4096

# Prefix in the model name -> (base URL, environment variable holding the API key).
OPENAI_COMPATIBLE_PROVIDERS = {
    "groq/": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini/": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
}


class LLMError(RuntimeError):
    """Raised when the model cannot produce a usable response."""


def check_not_truncated(prompt: str, prompt_tokens: int) -> None:
    """Fail loudly if the server silently cut the prompt (e.g. Ollama's default 4096 context).

    English text averages about 4 characters per token; far fewer tokens than that means
    the beginning of the prompt (the rules and the schema) was dropped.
    """
    expected = len(prompt) / 4
    if prompt_tokens and prompt_tokens < 0.6 * expected:
        raise LLMError(
            f"The server read only {prompt_tokens} of ~{expected:.0f} prompt tokens: "
            "the prompt was truncated. For Ollama, set OLLAMA_CONTEXT_LENGTH=8192 "
            "and restart Ollama."
        )


class LLMResponse(BaseModel):
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


class LLM(Protocol):
    model: str

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        """Return a JSON answer that follows schema."""
        ...


class OpenAICompatibleLLM:
    """Any server speaking the OpenAI chat API: Ollama (local), Groq, Gemini..."""

    def __init__(self, model: str, base_url: str, api_key: str) -> None:
        from openai import OpenAI

        self.model = model
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        # json_object mode is the most widely supported; the schema is also given in the prompt.
        start = time.perf_counter()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=DEFAULT_MAX_TOKENS,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        usage = response.usage
        check_not_truncated(system + user, usage.prompt_tokens if usage else 0)
        return LLMResponse(
            text=response.choices[0].message.content or "",
            model=self.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=round(latency_ms, 1),
        )


class AnthropicLLM:
    """Claude models through the official Anthropic SDK, with schema-constrained output."""

    def __init__(self, model: str) -> None:
        import anthropic

        self.model = model
        self.client = anthropic.Anthropic()

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        start = time.perf_counter()
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        latency_ms = (time.perf_counter() - start) * 1000
        if response.stop_reason == "refusal":
            raise LLMError("The model declined to answer this request")
        text = next((block.text for block in response.content if block.type == "text"), "")
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=round(latency_ms, 1),
        )


def get_llm(model: str) -> LLM:
    """Pick the adapter from the model name.

    - "claude-..."       -> Anthropic (ANTHROPIC_API_KEY)
    - "groq/<model>"     -> Groq free tier (GROQ_API_KEY)
    - "gemini/<model>"   -> Google Gemini free tier (GEMINI_API_KEY)
    - anything else      -> local Ollama (OLLAMA_BASE_URL)
    """
    if model.startswith("claude-"):
        return AnthropicLLM(model)
    for prefix, (base_url, key_env) in OPENAI_COMPATIBLE_PROVIDERS.items():
        if model.startswith(prefix):
            api_key = os.environ.get(key_env)
            if not api_key:
                raise LLMError(f"Set {key_env} in .env to use {model}")
            return OpenAICompatibleLLM(model.removeprefix(prefix), base_url, api_key)
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    return OpenAICompatibleLLM(model, base_url, api_key="ollama")


def parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating Markdown code fences around it."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise LLMError(f"The model did not return valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise LLMError("The model returned JSON that is not an object")
    return data
