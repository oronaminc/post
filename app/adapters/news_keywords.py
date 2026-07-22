"""뉴스 키워드 트렌드 — 여러 매체가 동시에 다룬 키워드를 랭킹.

파생 소스(derived): 1차로 수집된 뉴스(구글/네이버/NHK 등)를 재료로,
헤드라인에서 키워드를 뽑아 **문서빈도(등장 기사 수)** 로 랭킹한다.
  → 단독보도 1건보다, '여러 곳에서 다뤄진 주제'가 상위로 올라온다(진짜 트렌드).
성격: 실시간 급상승(realtime) — 지금 뉴스로 많이 생성되는 키워드.
네트워크 호출 없음(로컬 집계) → 리스크 없음.
"""
from __future__ import annotations

import asyncio
import urllib.parse

from ..keywords import REGION_LANG, build_exclude, extract_trends
from ..models import RawTrendItem, SOURCE_TYPE_REALTIME
from .base import BaseAdapter

# 지역별 뉴스검색 링크(키워드 클릭 시)
_SEARCH = {
    "kr": "https://search.naver.com/search.naver?where=news&query=",
    "jp": "https://news.google.com/search?q=",
    "tw": "https://news.google.com/search?q=",
}


class NewsKeywordsAdapter(BaseAdapter):
    name = "news_keywords"
    display_name = "뉴스 키워드 트렌드"
    default_source_type = SOURCE_TYPE_REALTIME
    risk = "low"
    derived = True

    async def fetch(self) -> list[RawTrendItem]:
        if not self.storage:
            return []
        news_sources = set(self.settings.get(
            "news_sources",
            ["google_news_rss", "google_news_top", "naver_news", "nhk_rss"],
        ))
        min_articles = int(self.settings.get("min_articles", 3))
        top = int(self.settings.get("max_items", 25))
        lang = REGION_LANG.get(self.region, "kr")

        rows = await asyncio.to_thread(self.storage.get_current_items, self.region)
        docs: list[tuple[str, str]] = [
            (r.get("term", ""), r.get("category", "trend"))
            for r in rows if r.get("source") in news_sources
        ]
        if not docs:
            return []

        # 카테고리 검색어(seed)는 제외 — 검색 때문에 문서빈도가 인위적으로 높음
        seeds: set[str] = set()
        for c in self.app_config.categories:
            seeds.update(self.app_config.news_queries(c["id"], self.region))
            seeds.update(self.app_config.keywords(c["id"], self.region))
        exclude = build_exclude(seeds, lang)

        trends = extract_trends(docs, lang, min_df=min_articles, top=top, exclude=exclude)
        search_url = _SEARCH.get(self.region, _SEARCH["kr"])
        items: list[RawTrendItem] = []
        for i, kw in enumerate(trends, start=1):
            items.append(RawTrendItem(
                term=kw["term"],
                source=self.name,
                source_type=SOURCE_TYPE_REALTIME,
                category=self._safe_category(kw["category"]),
                rank=i,
                metric_label="기사수",
                metric_value=float(kw["df"]),
                url=search_url + urllib.parse.quote(kw["term"]),
                extra={"articles": kw["df"]},
            ))
        return items
