from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


def _ddg_html_search(query: str, *, max_results: int = 5, timeout_s: int = 25) -> list[dict[str, str]]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    r = requests.get(url, timeout=timeout_s, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[dict[str, str]] = []
    for res in soup.select(".result"):
        a = res.select_one(".result__a")
        snippet = res.select_one(".result__snippet")
        if not a:
            continue
        out.append(
            {
                "title": (a.get_text(" ") or "").strip(),
                "url": (a.get("href") or "").strip(),
                "snippet": (snippet.get_text(" ") if snippet else "").strip(),
            }
        )
        if len(out) >= max_results:
            break
    return out


def _tavily_search(query: str, *, max_results: int = 5, timeout_s: int = 25) -> list[dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("TAVILY_API_KEY not set")
    r = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": query, "max_results": max_results, "include_answer": False},
        timeout=timeout_s,
    )
    r.raise_for_status()
    data = r.json()
    results = data.get("results", []) or []
    out = []
    for item in results[:max_results]:
        out.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", "") or item.get("snippet", ""),
            }
        )
    return out


def _serper_search(query: str, *, max_results: int = 5, timeout_s: int = 25) -> list[dict[str, Any]]:
    key = os.getenv("SERPER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("SERPER_API_KEY not set")
    r = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json={"q": query, "num": max_results},
        timeout=timeout_s,
    )
    r.raise_for_status()
    data = r.json()
    organic = data.get("organic", []) or []
    out = []
    for item in organic[:max_results]:
        out.append(
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
        )
    return out


def search_web(query: str, *, max_results: int = 5) -> list[dict[str, Any]]:
    """
    Best-effort search:
    - Tavily (if key)
    - Serper (if key)
    - DuckDuckGo HTML scrape fallback (no key)
    """
    key_tavily = os.getenv("TAVILY_API_KEY", "").strip()
    key_serper = os.getenv("SERPER_API_KEY", "").strip()

    if key_tavily:
        return _tavily_search(query, max_results=max_results)
    if key_serper:
        return _serper_search(query, max_results=max_results)
    return _ddg_html_search(query, max_results=max_results)


def run_external_search_cli(query: str, *, max_results: int = 5) -> dict[str, Any]:
    """
    Demonstrates calling an external tool/script, then parsing its JSON output.
    """
    script_path = os.path.join(os.getcwd(), "tools", "simple_search_cli.py")
    cmd = [sys.executable, script_path, "--query", query, "--max-results", str(max_results)]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"search cli failed: {p.stderr.strip() or p.stdout.strip()}")
    try:
        return json.loads(p.stdout)
    except Exception as e:
        raise RuntimeError(f"search cli returned non-json: {e}") from e

