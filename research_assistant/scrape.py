from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class PageCandidate:
    url: str
    label: str


_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ResearchAssistant/0.1; +https://example.com/bot)"
}


def _same_site(base_url: str, other_url: str) -> bool:
    a = urlparse(base_url)
    b = urlparse(other_url)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc)


def _normalize_url(u: str) -> str:
    parsed = urlparse(u)
    if not parsed.scheme:
        return "https://" + u.lstrip("/")
    return u


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_page_text(html: str, *, max_chars: int = 6000) -> tuple[str, str, str]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = _clean_text(soup.title.get_text(" ")) if soup.title else ""
    meta = soup.find("meta", attrs={"name": "description"})
    meta_desc = _clean_text(meta.get("content", "")) if meta else ""

    text = _clean_text(soup.get_text(" "))
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"

    return title, meta_desc, text


def discover_key_pages(
    base_url: str,
    *,
    max_pages: int = 8,
    timeout_s: int = 20,
) -> list[PageCandidate]:
    base_url = _normalize_url(base_url)
    r = requests.get(base_url, headers=_DEFAULT_HEADERS, timeout=timeout_s)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    anchors = soup.find_all("a", href=True)
    links: list[str] = []
    for a in anchors:
        href = a.get("href") or ""
        href = href.strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        abs_url = urljoin(base_url, href)
        if _same_site(base_url, abs_url):
            links.append(abs_url.split("#", 1)[0])

    def label_for(url: str) -> str:
        path = urlparse(url).path.lower()
        if any(k in path for k in ("/about", "about-us", "our-story", "company")):
            return "about"
        if any(k in path for k in ("/services", "/service", "/solutions", "/what-we-do")):
            return "services"
        if any(k in path for k in ("/contact", "/get-in-touch")):
            return "contact"
        if any(k in path for k in ("/pricing", "/plans", "/packages")):
            return "pricing"
        if any(k in path for k in ("/case", "/work", "/portfolio", "/customers")):
            return "work"
        if any(k in path for k in ("/blog", "/insights", "/resources", "/articles")):
            return "blog"
        return ""

    # prioritize pages by label; always include home
    seen: set[str] = set()
    out: list[PageCandidate] = [PageCandidate(url=base_url, label="home")]
    seen.add(base_url)

    prioritized = sorted(
        (u for u in links if u not in seen),
        key=lambda u: (0 if label_for(u) else 1, len(urlparse(u).path)),
    )

    for u in prioritized:
        if len(out) >= max_pages:
            break
        lbl = label_for(u)
        if not lbl:
            continue
        if u in seen:
            continue
        out.append(PageCandidate(url=u, label=lbl))
        seen.add(u)

    return out


def fetch_pages(
    pages: Iterable[PageCandidate],
    *,
    timeout_s: int = 25,
) -> list[dict]:
    results: list[dict] = []
    for p in pages:
        try:
            r = requests.get(p.url, headers=_DEFAULT_HEADERS, timeout=timeout_s)
            r.raise_for_status()
            title, meta_desc, text = extract_page_text(r.text)
            results.append(
                {
                    "url": p.url,
                    "label": p.label,
                    "title": title,
                    "meta_description": meta_desc,
                    "text_excerpt": text,
                }
            )
        except Exception as e:  # best-effort scraping
            results.append(
                {
                    "url": p.url,
                    "label": p.label,
                    "title": "",
                    "meta_description": "",
                    "text_excerpt": "",
                    "error": str(e),
                }
            )
    return results

