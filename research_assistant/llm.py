from __future__ import annotations

import json
import os
from typing import Any, Callable

from openai import OpenAI


def resolve_provider_config() -> tuple[str, str]:
    """
    Returns (base_url, api_key) for an OpenAI-compatible provider.
    Priority:
    - OPENAI_API_KEY (+ optional OPENAI_BASE_URL)
    - GROQ_API_KEY (auto base_url: Groq OpenAI-compatible endpoint)
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
    if api_key:
        return (base_url or "https://api.openai.com/v1", api_key)

    groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if groq_key:
        return ("https://api.groq.com/openai/v1", groq_key)

    raise RuntimeError("No API key found. Set OPENAI_API_KEY or GROQ_API_KEY in your environment/.env.")


def list_available_models(client: OpenAI) -> list[str]:
    """
    Returns model IDs from the provider. Best-effort: failures return [].
    """
    try:
        models = client.models.list()
        return sorted([m.id for m in models.data if getattr(m, "id", None)])
    except Exception:
        return []


def default_model_for(base_url: str) -> str:
    env_model = (os.getenv("LLM_MODEL") or "").strip()
    if env_model:
        return env_model
    if "groq.com" in base_url:
        # `llama-3.1-70b-versatile` was decommissioned; Groq recommends `llama-3.3-70b-versatile`.
        return "llama-3.3-70b-versatile"
    return "gpt-4o-mini"


def get_client() -> tuple[OpenAI, str]:
    base_url, api_key = resolve_provider_config()
    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, base_url


ToolHandler = Callable[[dict[str, Any]], Any]


def run_tool_call(tool_name: str, tool_args: dict[str, Any], handlers: dict[str, ToolHandler]) -> str:
    if tool_name not in handlers:
        raise RuntimeError(f"Unknown tool: {tool_name}")
    result = handlers[tool_name](tool_args)
    return json.dumps(result, ensure_ascii=False)


def chat_with_tools(
    *,
    client: OpenAI,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    handlers: dict[str, ToolHandler],
    temperature: float = 0.2,
    max_turns: int = 6,
) -> str:
    """
    Minimal tool-calling loop using OpenAI-compatible Chat Completions.
    """
    for _ in range(max_turns):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
        )
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []

        # Append the assistant message exactly once (with optional tool_calls).
        assistant_payload: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if tool_calls:
            assistant_payload["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]
        messages.append(assistant_payload)

        if not tool_calls:
            return (msg.content or "").strip()

        for tc in tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            tool_json = run_tool_call(name, args, handlers)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_json})

    raise RuntimeError("Tool-calling loop exceeded max_turns; try simplifying inputs or disabling tools.")

