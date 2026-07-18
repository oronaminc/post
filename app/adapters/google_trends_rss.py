"""Google 트렌드 (일본) 일간 급상승 — 공식 공개 RSS.

수집 방식: https://trends.google.com/trending/rss?geo=JP
  - robots.txt 실측: /trending/rss 는 허용 (/explore? 만 Disallow).
  - 공개 RSS 피드라 리스크가 낮다.
각 item: <title>=트렌드 워드, <ht:approx_traffic>=대략 검색량,
        <ht:news_item>=관련 뉴스(제목/URL/출처).
성격: 실시간 급상승(realtime).
"""
from __future__ import annotations

import re

import feedparser

from ..models import RawTrendItem, SOURCE_TYPE_REALTIME
from .base import BaseAdapter


def _traffic_to_number(text: str) -> float:
    """'1,000+' / '2万+' 같은 표기를 대략 숫자로."""
    if not text:
        return 0.0
    t = text.replace(",", "").replace("+", "").strip()
    mult = 1.0
    if "万" in t:
        mult = 10000.0
        t = t.replace("万", "")
    m = re.search(r"[\d.]+", t)
    return float(m.group()) * mult if m else 0.0


class GoogleTrendsRssAdapter(BaseAdapter):
    name = "google_trends_rss"
    display_name = "Google 트렌드(일간)"
    default_source_type = SOURCE_TYPE_REALTIME
    risk = "low"

    async def fetch(self) -> list[RawTrendItem]:
        geo = self.settings.get("geo", "JP")
        max_items = int(self.settings.get("max_items", 25))
        category = self._safe_category(self.settings.get("default_category", "trend"))
        url = f"https://trends.google.com/trending/rss?geo={geo}"

        raw = await self.http.get_bytes(url)
        feed = feedparser.parse(raw)

        items: list[RawTrendItem] = []
        for i, entry in enumerate(feed.entries[:max_items], start=1):
            term = (entry.get("title") or "").strip()
            if not term:
                continue
            traffic_txt = entry.get("ht_approx_traffic", "") or ""
            # 관련 뉴스 첫 건을 링크/출처로
            news_url = ""
            news_source = ""
            news_items = entry.get("ht_news_item") or entry.get("ht_news_items")
            if isinstance(news_items, dict):
                news_items = [news_items]
            if isinstance(news_items, list) and news_items:
                first = news_items[0]
                news_url = first.get("ht_news_item_url", "") if isinstance(first, dict) else ""
            picture_source = entry.get("ht_picture_source", "") or ""

            items.append(RawTrendItem(
                term=term,
                source=self.name,
                source_type=SOURCE_TYPE_REALTIME,
                category=category,
                rank=i,
                metric_label="검색량",
                metric_value=_traffic_to_number(traffic_txt),
                url=news_url or f"https://www.google.com/search?q={term}",
                extra={
                    "approx_traffic": traffic_txt,
                    "news_source": news_source or picture_source,
                },
            ))
        return items
