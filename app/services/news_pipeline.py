"""Orchestrate news fetch post-processing: filter, dedup, enrich."""

from __future__ import annotations

from app.services.news_filters import (
    apply_age_filter,
    apply_category_prefs,
    apply_keyword_blacklist,
    apply_source_prefs,
    cluster_duplicates,
)
from app.services.news_prefs import (
    ensure_categories_seen,
    get_age_filter,
    get_category_prefs,
    get_keyword_blacklist,
    get_read_urls,
    get_saved_urls,
    get_source_prefs,
)


def collect_discovery(articles: list[dict]) -> tuple[set[str], set[str]]:
    sources: set[str] = set()
    categories: set[str] = set()
    for article in articles:
        if article.get("source"):
            sources.add(article["source"])
        for cat in article.get("categories") or []:
            if cat:
                categories.add(cat)
    return sources, categories


def process_feed(articles: list[dict]) -> list[dict]:
    """Run full pipeline and enrich items with read/saved flags."""
    age_prefs = get_age_filter()
    keywords = get_keyword_blacklist()
    source_prefs = get_source_prefs()
    category_prefs = get_category_prefs()

    categories_seen: set[str] = set()
    for article in articles:
        for cat in article.get("categories") or []:
            if cat:
                categories_seen.add(cat)
    ensure_categories_seen(categories_seen)
    if categories_seen:
        category_prefs = get_category_prefs()

    filtered = apply_age_filter(articles, age_prefs)
    filtered = apply_keyword_blacklist(filtered, keywords)
    filtered = apply_source_prefs(filtered, source_prefs)
    filtered = apply_category_prefs(filtered, category_prefs)
    clustered = cluster_duplicates(filtered)

    read_urls = get_read_urls()
    saved_urls = get_saved_urls()
    return [_enrich_item(item, read_urls, saved_urls) for item in clustered]


def _enrich_article(article: dict, read_urls: set[str], saved_urls: set[str]) -> dict:
    out = dict(article)
    url = out.get("url", "")
    out["read"] = url in read_urls
    out["saved"] = url in saved_urls
    if out.get("type") is None:
        out["type"] = "article"
    return out


def _enrich_item(item: dict, read_urls: set[str], saved_urls: set[str]) -> dict:
    if item.get("type") == "cluster":
        articles = [
            _enrich_article(a, read_urls, saved_urls) for a in item.get("articles", [])
        ]
        primary = articles[0] if articles else {}
        out = dict(item)
        out["articles"] = articles
        out["read"] = all(a.get("read") for a in articles) if articles else False
        out["saved"] = primary.get("url", "") in saved_urls
        return out
    return _enrich_article(item, read_urls, saved_urls)


def flatten_urls(items: list[dict]) -> list[str]:
    urls = []
    for item in items:
        if item.get("type") == "cluster":
            for a in item.get("articles", []):
                if a.get("url"):
                    urls.append(a["url"])
        elif item.get("url"):
            urls.append(item["url"])
    return urls
