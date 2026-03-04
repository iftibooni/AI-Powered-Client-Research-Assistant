from __future__ import annotations

import argparse
import json
import os
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


def ddg_html_search(query: str, *, max_results: int = 5, timeout_s: int = 25) -> list[dict[str, str]]:
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
                "provider": "duckduckgo_html",
            }
        )
        if len(out) >= max_results:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--max-results", type=int, default=5)
    args = ap.parse_args()

    # If you later want to swap this for a paid API, keep the interface stable.
    results = ddg_html_search(args.query, max_results=max(1, min(10, args.max_results)))
    payload = {"query": args.query, "results": results, "env": {"TAVILY_API_KEY_set": bool(os.getenv("TAVILY_API_KEY"))}}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

