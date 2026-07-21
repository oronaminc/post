"""Google 뉴스 '톱스토리' — 키워드가 아닌 **인기/중요도 랭킹** 뉴스.

카테고리별 키워드 검색(관련도순)과 달리, Google 뉴스 메인 피드는
지금 **많이 읽히고 크게 다뤄지는 뉴스**를 순위로 제공한다 → '많이 본 것'에 가장 근접.
수집 방식: https://news.google.com/rss?hl=..&gl=..&ceid=..  (지역 로케일별)
성격: 실시간 급상승(realtime) — 지금 큰 뉴스.
리스크: 낮음(공개 RSS).
"""
from __future__ import annotations

import urllib.parse

import feedparser

from ..models import RawTrendItem, SOURCE_TYPE_REALTIME
from .base import BaseAdapter
from .google_news_rss import _clean_headline


class GoogleNewsTopAdapter(BaseAdapter):
    name = "google_news_top"
    display_name = "Google 뉴스 톱스토리"
    default_source_type = SOURCE_TYPE_REALTIME
    risk = "low"

    async def fetch(self) -> list[RawTrendItem]:
        locale = self._rget("locale", {}) or {}
        hl = locale.get("hl", "ko")
        gl = locale.get("gl", "KR")
        ceid = locale.get("ceid", "KR:ko")
        max_items = int(self.settings.get("max_items", 20))
        category = self._safe_category(self.settings.get("default_category", "current_affairs"))

        url = (f"https://news.google.com/rss?hl={hl}&gl={gl}"
               f"&ceid={urllib.parse.quote(ceid)}")
        raw = await self.http.get_bytes(url)
        feed = feedparser.parse(raw)

        items: list[RawTrendItem] = []
        seen: set[str] = set()
        rank = 0
        for entry in feed.entries[:max_items]:
            headline, src = _clean_headline(entry.get("title", ""))
            if not headline or headline in seen:
                continue
            seen.add(headline)
            rank += 1
            items.append(RawTrendItem(
                term=headline,
                source=self.name,
                source_type=SOURCE_TYPE_REALTIME,
                category=category,
                rank=rank,
                metric_label="인기뉴스",
                metric_value=float(max(0, max_items - rank + 1)),
                url=entry.get("link", ""),
                extra={"news_source": src, "published": entry.get("published", "")},
            ))
        return items
