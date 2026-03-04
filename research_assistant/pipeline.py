from __future__ import annotations

import json
import re
from typing import Any

import requests
from pydantic import ValidationError

from research_assistant.llm import chat_with_tools
from research_assistant.schema import ResearchOutput, WebsiteBasics
from research_assistant.scrape import discover_key_pages, extract_page_text, fetch_pages
from research_assistant.search_tool import run_external_search_cli, search_web


def _snip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _extract_json_object(text: str) -> dict[str, Any]:
    """
    Best-effort: pull the first top-level JSON object from model output.
    """
    text = text.strip()
    # Find first JSON object by matching braces depth, so we can ignore
    # any trailing notes the model might add after the object.
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output.")

    depth = 0
    end = None
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        raise ValueError("Unbalanced braces in model output; could not extract JSON.")

    snippet = text[start:end]
    return json.loads(snippet)


def _tool_fetch_url(args: dict[str, Any]) -> dict[str, Any]:
    url = (args.get("url") or "").strip()
    if not url:
        return {"error": "missing url"}
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        title, meta, text = extract_page_text(r.text, max_chars=6000)
        return {"url": url, "title": title, "meta_description": meta, "text_excerpt": text}
    except Exception as e:
        return {"url": url, "error": str(e)}


def _tool_web_search(args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query") or "").strip()
    max_results = int(args.get("max_results") or 5)
    max_results = max(1, min(10, max_results))
    if not query:
        return {"error": "missing query"}
    try:
        return {"query": query, "results": search_web(query, max_results=max_results)}
    except Exception as e:
        return {"query": query, "error": str(e)}


TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for competitors, industry trends, and positioning examples.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch a URL and return title/meta/text excerpt.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]


def run_research(
    *,
    client,
    model: str,
    url: str,
    niche_hint: str = "",
    use_tools: bool = True,
    use_external_search: bool = True,
) -> ResearchOutput:
    # 1) Scrape site pages
    candidates = discover_key_pages(url, max_pages=8)
    normalized_url = candidates[0].url if candidates else url
    pages_raw = fetch_pages(candidates)

    # 2) Optional: call external tool (simple CLI script) for seed competitor/trend results
    external_sources: dict[str, Any] = {}
    if use_external_search:
        try:
            external_sources["competitors_search"] = run_external_search_cli(
                f"{normalized_url} competitors",
                max_results=5,
            )
            external_sources["trends_search"] = run_external_search_cli(
                f"{niche_hint or normalized_url} industry trends",
                max_results=5,
            )
        except Exception as e:
            external_sources["external_search_error"] = str(e)

    # 3) Ask LLM for structured research output
    page_briefs = []
    for p in pages_raw:
        page_briefs.append(
            {
                "label": p.get("label", ""),
                "url": p.get("url", ""),
                "title": _snip(p.get("title", ""), 180),
                "meta_description": _snip(p.get("meta_description", ""), 240),
                "text_excerpt": _snip(p.get("text_excerpt", ""), 1500),
                "error": p.get("error", ""),
            }
        )

    system = (
        "You are an AI research assistant for a digital marketing agency. "
        "Given a client's website content and optional web search snippets, produce a concise, practical onboarding brief. "
        "Return ONLY valid JSON (no markdown) with the exact keys requested."
    )

    user = {
        "input_url": normalized_url,
        "niche_hint": niche_hint,
        "scraped_pages": page_briefs,
        "external_sources": external_sources,
        "required_json_shape": {
            "basics": WebsiteBasics.model_json_schema(),
            "summary": "string",
            "positioning_ideas": [
                {
                    "angle": "string",
                    "who_its_for": "string",
                    "key_benefit": "string",
                    "proof_points": ["string"],
                    "sample_tagline": "string",
                }
            ],
            "competitors": [{"name": "string", "url": "string", "notes": "string"}],
            "content_ideas": [
                {
                    "title": "string",
                    "format": "blog|landing_page|comparison|case_study|email|linkedin|twitter|youtube|webinar|lead_magnet|other",
                    "intent": "awareness|consideration|decision",
                    "why_it_works": "string",
                    "outline_points": ["string"],
                }
            ],
        },
        "constraints": [
            "If the website content is sparse, infer carefully and say so in summary.",
            "Generate 3–6 positioning_ideas.",
            "Generate 5–10 content_ideas tailored to the niche.",
            "Competitors can be inferred from search snippets; avoid hallucinating exact facts if not supported.",
        ],
    }

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]

    if use_tools:
        content = chat_with_tools(
            client=client,
            model=model,
            messages=messages,
            tools=TOOLS_SPEC,
            handlers={"web_search": _tool_web_search, "fetch_url": _tool_fetch_url},
            temperature=0.2,
            max_turns=6,
        )
    else:
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
        content = (resp.choices[0].message.content or "").strip()

    data = _extract_json_object(content)

    # 4) Normalize model output a bit before validation (e.g. unknown literals)
    raw_content_ideas = list(data.get("content_ideas", []) or [])
    allowed_formats = {
        "blog",
        "landing_page",
        "comparison",
        "case_study",
        "email",
        "linkedin",
        "twitter",
        "youtube",
        "webinar",
        "lead_magnet",
        "other",
    }
    allowed_intents = {"awareness", "consideration", "decision"}
    for ci in raw_content_ideas:
        if not isinstance(ci, dict):
            continue
        fmt = str(ci.get("format", "") or "").lower()
        if fmt not in allowed_formats:
            ci["format"] = "other"
        intent = str(ci.get("intent", "") or "").lower()
        if intent not in allowed_intents:
            ci["intent"] = "awareness"

    # 5) Validate + assemble final output
    output = ResearchOutput(
        input_url=normalized_url,
        fetched_pages=page_briefs,
        basics=data.get("basics", {}),
        summary=data.get("summary", ""),
        positioning_ideas=data.get("positioning_ideas", []),
        competitors=data.get("competitors", []),
        content_ideas=raw_content_ideas,
        sources={"external": external_sources},
    )

    try:
        return ResearchOutput.model_validate(output.model_dump())
    except ValidationError:
        # If validation fails due to partial fields, return best-effort already-coerced model
        return output

