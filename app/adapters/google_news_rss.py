"""Google 뉴스 RSS — 카테고리별 뉴스 커버(보조금/정치/경제/시사 등).

수집 방식: https://news.google.com/rss/search?q=<검색어>&hl=ja&gl=JP&ceid=JP:ja
  - RSS 신디케이션 피드라 리스크가 낮다.
  - config 각 카테고리의 news_queries 를 순회하며 헤드라인을 모은다.
성격: 지속 관심도(sustained) — 특정 주제의 뉴스 노출량/지속성.
"""
from __future__ import annotations

import urllib.parse

import feedparser

from ..models import RawTrendItem, SOURCE_TYPE_SUSTAINED
from .base import BaseAdapter


def _clean_headline(title: str) -> tuple[str, str]:
    """'헤드라인 - 출처' 형태에서 헤드라인과 출처를 분리."""
    if " - " in title:
        head, _, src = title.rpartition(" - ")
        return head.strip(), src.strip()
    return title.strip(), ""


class GoogleNewsRssAdapter(BaseAdapter):
    name = "google_news_rss"
    display_name = "Google 뉴스"
    default_source_type = SOURCE_TYPE_SUSTAINED
    risk = "low"

    async def fetch(self) -> list[RawTrendItem]:
        per_cat = int(self.settings.get("per_category_limit", 12))
        items: list[RawTrendItem] = []

        for cat in self.app_config.categories:
            queries = cat.get("news_queries") or []
            if not queries:
                continue
            cat_id = cat["id"]
            seen: set[str] = set()
            rank = 0
            for query in queries:
                q = urllib.parse.quote(query)
                url = f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"
                try:
                    raw = await self.http.get_bytes(url)
                except Exception:
                    # 한 검색어 실패는 건너뛰고 계속 (부분 실패 허용)
                    continue
                feed = feedparser.parse(raw)
                for entry in feed.entries:
                    headline, src = _clean_headline(entry.get("title", ""))
                    if not headline or headline in seen:
                        continue
                    seen.add(headline)
                    rank += 1
                    items.append(RawTrendItem(
                        term=headline,
                        source=self.name,
                        source_type=SOURCE_TYPE_SUSTAINED,
                        category=cat_id,
                        rank=rank,
                        metric_label="뉴스",
                        metric_value=float(max(0, per_cat * len(queries) - rank)),
                        url=entry.get("link", ""),
                        extra={"query": query, "news_source": src,
                               "published": entry.get("published", "")},
                    ))
                    if rank >= per_cat:
                        break
                if rank >= per_cat:
                    break
        return items
