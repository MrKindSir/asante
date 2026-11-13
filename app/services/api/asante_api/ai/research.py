"""Bounded web + social research collectors for Asante story evidence."""
from __future__ import annotations

import asyncio
import html
import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from .activity import report_progress

USER_AGENT = (
    "Mozilla/5.0 (compatible; AsanteResearch/1.0; +https://asante.local) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BOILER = re.compile(
    r"cookie|subscribe|newsletter|sign up|javascript|privacy policy|terms of (use|service)|skip to|accept all|all rights reserved|share this|related articles",
    re.I,
)
PRIVATE_HOSTS = re.compile(
    r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|0\.0\.0\.0|\[::1\]|metadata\.google)",
    re.I,
)
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
SEED_PATH = Path(__file__).resolve().parent / "data" / "youtube_testdata.txt"


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .-")
    return text.strip()


def clean_excerpt(text: str) -> str:
    lines = []
    for chunk in re.split(r"[\n\r]+", html.unescape(text or "")):
        line = clean_text(chunk)
        words = line.split()
        if len(words) < 6:
            continue
        if BOILER.search(line) and len(words) < 14:
            continue
        if sum(ch.isalpha() for ch in line) < len(line) * 0.55:
            continue
        lines.append(line)
    return (" ".join(lines) if lines else clean_text(text))[:1500]


def host_of(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    if PRIVATE_HOSTS.search(parsed.netloc):
        return False
    if parsed.username or parsed.password:
        return False
    return True


def _evidence_item(**fields: object) -> dict:
    url = str(fields.get("url") or "")
    excerpt = clean_excerpt(str(fields.get("excerpt") or ""))
    title = clean_text(str(fields.get("title") or url))[:200]
    body = excerpt or title
    return {
        "title": title or url,
        "url": url,
        "excerpt": excerpt or title,
        "collector": fields.get("collector") or "web search",
        "status": fields.get("status") or "retrieved",
        "publisher": fields.get("publisher") or host_of(url),
        "retrievedAt": fields.get("retrievedAt") or datetime.now(timezone.utc).isoformat(),
        "contentHash": sha256(body.encode("utf-8")).hexdigest(),
        "platform": fields.get("platform") or "",
        "retrievalState": fields.get("retrievalState") or {
            "web search": "search_snippet",
            "social video": "social_search_snippet",
            "social catalogue": "social_catalogue_entry",
            "youtube oembed": "metadata_only",
            "page": "page_excerpt",
            "news": "news_headline",
            "pasted url": "direct_url_metadata",
        }.get(str(fields.get("collector") or ""), "metadata_only"),
        "duplicateGroup": sha256((url.split("#", 1)[0].rstrip("/") or body).lower().encode("utf-8")).hexdigest()[:20],
    }


def search_web(query: str, max_results: int = 8) -> list[dict]:
    hits: list[dict] = []
    try:
        from ddgs import DDGS
    except Exception:
        return hits
    ddgs = DDGS()
    try:
        results = ddgs.text(query, region="za-en", max_results=max_results)
    finally:
        close = getattr(ddgs, "close", None)
        if close:
            close()
    for item in results or []:
        url = item.get("href") or item.get("url") or ""
        if not is_safe_url(url):
            continue
        hits.append(
            _evidence_item(
                title=item.get("title") or url,
                url=url,
                excerpt=item.get("body") or "",
                collector="web search",
                status="retrieved",
                platform="web",
            )
        )
    return hits


def search_social(query: str, max_results: int = 6) -> list[dict]:
    """YouTube / social discovery via DuckDuckGo video search + optional seed catalogue."""
    hits: list[dict] = []
    try:
        from ddgs import DDGS
    except Exception:
        DDGS = None  # type: ignore
    if DDGS is not None:
        ddgs = DDGS()
        try:
            results = ddgs.videos(query, max_results=max_results)
        except Exception:
            results = []
        finally:
            close = getattr(ddgs, "close", None)
            if close:
                close()
        for item in results or []:
            url = item.get("content") or item.get("url") or item.get("embed_url") or ""
            if not url.startswith("http"):
                continue
            if url.startswith("http://"):
                url = "https://" + url[len("http://") :]
            if not is_safe_url(url):
                continue
            hits.append(
                _evidence_item(
                    title=item.get("title") or url,
                    url=url,
                    excerpt=item.get("description") or item.get("publisher") or item.get("title") or "",
                    collector="social video",
                    status="retrieved",
                    platform="youtube" if host_of(url) in YOUTUBE_HOSTS or "youtube" in host_of(url) else "social",
                    publisher=item.get("publisher") or host_of(url),
                )
            )
    hits.extend(seed_social_matches(query))
    return hits


def seed_social_matches(query: str) -> list[dict]:
    if not SEED_PATH.exists():
        return []
    text = SEED_PATH.read_text(encoding="utf-8", errors="ignore")
    terms = [part.lower() for part in re.findall(r"[a-zA-Z]{4,}", query)][:8]
    blocks = re.split(r"\n-{3,}\n|\n{3,}", text)
    matches: list[dict] = []
    for block in blocks:
        lowered = block.lower()
        if terms and not any(term in lowered for term in terms):
            continue
        title = ""
        for line in block.splitlines():
            line = line.strip()
            if line and not line.startswith("http") and "views" not in line.lower():
                title = clean_text(line)[:160]
                break
        urls = re.findall(r"https://[^\s]+", block)
        excerpt = clean_excerpt(block)[:700]
        if not title and not urls:
            continue
        url = urls[0] if urls and is_safe_url(urls[0]) else f"https://www.youtube.com/results?search_query={quote(title or query)}"
        if not is_safe_url(url):
            continue
        matches.append(
            _evidence_item(
                title=title or "Seeded social catalogue match",
                url=url,
                excerpt=excerpt or title,
                collector="social catalogue",
                status="retrieved",
                platform="youtube",
                publisher="youtube.com",
            )
        )
        if len(matches) >= 3:
            break
    return matches


def news_items(xml: str) -> list[dict]:
    items: list[dict] = []
    for block in re.findall(r"<item>(.*?)</item>", xml, flags=re.S)[:6]:
        title = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, flags=re.S)
        link = re.search(r"<link>(.*?)</link>", block, flags=re.S)
        headline = clean_text(title.group(1)) if title else ""
        url = link.group(1).strip() if link else ""
        if headline and is_safe_url(url) and headline != "Google News":
            items.append(
                _evidence_item(
                    title=headline,
                    url=url,
                    excerpt=headline,
                    collector="news",
                    status="retrieved",
                    platform="news",
                )
            )
    return items


def extract_text(page_html: str, url: str) -> tuple[str, str]:
    title = ""
    found = re.search(r"<title>(.*?)</title>", page_html, flags=re.I | re.S)
    if found:
        title = clean_text(found.group(1))
    text = ""
    try:
        import trafilatura

        text = trafilatura.extract(page_html, url=url, include_comments=False, include_tables=True) or ""
    except Exception:
        text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", page_html, flags=re.I)
        text = clean_text(text)
    return title, clean_excerpt(text)


async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url, timeout=15, follow_redirects=True)
    response.raise_for_status()
    if not is_safe_url(str(response.url)):
        raise ValueError("redirected to a blocked destination")
    kind = response.headers.get("content-type", "")
    if "html" not in kind and "xml" not in kind and "text" not in kind:
        return ""
    return response.text


async def youtube_oembed(client: httpx.AsyncClient, url: str) -> dict | None:
    if host_of(url) not in YOUTUBE_HOSTS and "youtube.com" not in host_of(url):
        return None
    endpoint = f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json"
    response = await client.get(endpoint, timeout=12)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        return None
    return _evidence_item(
        title=data.get("title") or url,
        url=url,
        excerpt=f"{data.get('author_name') or 'YouTube'} · {data.get('title') or ''}",
        collector="youtube oembed",
        status="retrieved",
        platform="youtube",
        publisher=data.get("author_name") or "youtube.com",
    )


async def enrich_page(client: httpx.AsyncClient, item: dict) -> dict:
    url = item["url"]
    if host_of(url) in YOUTUBE_HOSTS or "youtube.com" in host_of(url):
        try:
            embedded = await youtube_oembed(client, url)
            if embedded:
                return embedded
        except Exception:
            pass
        # Keep the social discovery row as usable evidence.
        return {**item, "status": "retrieved", "excerpt": item.get("excerpt") or item.get("title") or url}

    try:
        page_html = await fetch_html(client, url)
        title, excerpt = extract_text(page_html, url)
        if excerpt:
            return _evidence_item(
                title=title or item.get("title") or url,
                url=url,
                excerpt=excerpt,
                collector="page",
                status="retrieved",
                retrievalState="page_excerpt",
                platform=item.get("platform") or "web",
                publisher=host_of(url),
            )
    except Exception:
        pass
    # Never drop a discovered source: promote the search snippet.
    excerpt = item.get("excerpt") or item.get("title") or url
    return _evidence_item(
        title=item.get("title") or url,
        url=url,
        excerpt=excerpt,
        collector=item.get("collector") or "web search",
        status="retrieved",
        platform=item.get("platform") or "web",
        publisher=item.get("publisher") or host_of(url),
    )


async def collect_evidence(query: str, extra_urls: list[str] | None = None) -> tuple[list[dict], list[str]]:
    evidence: list[dict] = []
    notes: list[str] = []
    query = clean_text(query)[:240]
    if not query:
        raise ValueError("No research query was supplied.")

    headers = {"user-agent": USER_AGENT, "accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        await report_progress("search", "Researcher → Web collector: search for candidate references.", [query])
        try:
            hits = await asyncio.to_thread(search_web, query)
        except Exception as error:
            hits = []
            notes.append(f"Web search failed: {error.__class__.__name__}.")
        evidence.extend(hits)
        await report_progress("search", f"Web collector returned {len(hits)} candidates.", notes[-1:] if not hits else [])

        await report_progress("search", "Researcher → Social/video collector: look for relevant candidate records.", [query])
        try:
            social = await asyncio.to_thread(search_social, query)
        except Exception as error:
            social = []
            notes.append(f"Social search failed: {error.__class__.__name__}.")
        evidence.extend(social)
        await report_progress("search", f"Social/video collector returned {len(social)} candidates.", notes[-1:] if not social else [])

        await report_progress("search", "Researcher → News collector: search news headlines.", [query])
        news_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-ZA&gl=ZA&ceid=ZA:en"
        try:
            news = await client.get(news_url, timeout=12)
            news.raise_for_status()
            articles = news_items(news.text)
        except Exception as error:
            articles = []
            notes.append(f"News search failed: {error.__class__.__name__}.")
        evidence.extend(articles)
        await report_progress("search", f"News collector returned {len(articles)} candidates.", notes[-1:] if not articles else [])

        extras = []
        for url in (extra_urls or [])[:5]:
            if is_safe_url(url):
                extras.append(_evidence_item(title=url, url=url, excerpt=url, collector="pasted url", status="retrieved", platform="web"))
        evidence.extend(extras)

        # Enrich a bounded set; enrichment never removes a source.
        targets = []
        seen: set[str] = set()
        for item in evidence:
            url = item.get("url") or ""
            if not url or url in seen or not is_safe_url(url):
                continue
            seen.add(url)
            targets.append(item)
            if len(targets) >= 8:
                break

        await report_progress("retrieval", f"Retrieving available excerpts for up to {len(targets)} candidate references.")
        enriched: list[dict] = []
        for item in targets:
            enriched.append(await enrich_page(client, item))
            await report_progress("retrieval", "Candidate reference processed; availability is recorded without claiming verification.", [str(item.get("url") or ""), str(enriched[-1].get("retrievalState") or "metadata_only")])
        # Keep remaining discovered rows that were not enriched yet.
        for item in evidence:
            url = item.get("url") or ""
            if url and url not in {row.get("url") for row in enriched} and is_safe_url(url):
                enriched.append(_evidence_item(**item))

        # Deduplicate by URL, prefer longer excerpts.
        by_url: dict[str, dict] = {}
        for item in enriched:
            url = item["url"]
            current = by_url.get(url)
            if current is None or len(item.get("excerpt") or "") > len(current.get("excerpt") or ""):
                by_url[url] = item
        evidence = list(by_url.values())[:12]

    if not evidence:
        raise RuntimeError("Research produced no usable sources. Retry with a clearer claim or place.")
    await report_progress("comparison", f"Deduplicated candidates by URL; retained {len(evidence)} sources. Claims still require human interpretation.")
    notes.append(f"Collected {len(evidence)} usable sources across web, news and social collectors.")
    return evidence, notes
