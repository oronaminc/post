"""NHK 뉴스 — 공식 RSS.

수집 방식: https://www.nhk.or.jp/rss/news/<cat>.xml
  - NHK 공식 RSS. 요청 시 브랜드 TLD(news.web.nhk)로 301 리다이렉트되며,
    PoliteClient 가 리다이렉트를 자동 추적한다.
  - config sources.nhk_rss.feeds 에서 NHK 카테고리 -> 우리 카테고리 매핑.
성격: 지속 관심도(sustained).
"""
from __future__ import annotations

import feedparser

from ..models import RawTrendItem, SOURCE_TYPE_SUSTAINED
from .base import BaseAdapter


class NhkRssAdapter(BaseAdapter):
    name = "nhk_rss"
    display_name = "NHK 뉴스"
    default_source_type = SOURCE_TYPE_SUSTAINED
    risk = "low"

    async def fetch(self) -> list[RawTrendItem]:
        feeds: dict[str, str] = self.settings.get("feeds", {}) or {}
        per_feed = int(self.settings.get("per_feed_limit", 12))
        items: list[RawTrendItem] = []

        for nhk_cat, cat_id in feeds.items():
            category = self._safe_category(cat_id)
            url = f"https://www.nhk.or.jp/rss/news/{nhk_cat}.xml"
            try:
                raw = await self.http.get_bytes(url)
            except Exception:
                # 한 피드가 죽어도 나머지 피드는 계속 수집
                continue
            feed = feedparser.parse(raw)
            for i, entry in enumerate(feed.entries[:per_feed], start=1):
                title = (entry.get("title") or "").strip()
                if not title:
                    continue
                items.append(RawTrendItem(
                    term=title,
                    source=self.name,
                    source_type=SOURCE_TYPE_SUSTAINED,
                    category=category,
                    rank=i,
                    metric_label="뉴스",
                    metric_value=float(max(0, per_feed - i + 1)),
                    url=entry.get("link", ""),
                    extra={"nhk_cat": nhk_cat, "published": entry.get("published", "")},
                ))
        return items
