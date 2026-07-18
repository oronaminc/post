"""Google 트렌드 키워드 인기도 — pytrends(비공식) 로 '지속 관심도' 측정.

⚠️ 리스크: 중간.
  - pytrends 는 비공식 라이브러리라 Google 의 429(rate limit)에 자주 막힌다.
  - 그래서 전체 키워드 수를 max_keywords 로 제한하고 배치 사이에 sleep 을 둔다.
  - pytrends 미설치/오류 시 예외를 던져 컬렉터가 이 소스만 격리한다(나머지 정상).
  - pytrends 는 동기(requests) 라서 asyncio.to_thread 로 실행한다.

각 카테고리의 keywords(없으면 news_queries 첫 항목)에 대해
지난 7일 interest_over_time 평균값(0~100)을 인기도 점수로 사용.
성격: 지속 관심도(sustained).
"""
from __future__ import annotations

import asyncio
import logging

from ..models import RawTrendItem, SOURCE_TYPE_SUSTAINED
from .base import BaseAdapter

log = logging.getLogger("jptrend.adapter.pytrends")


class GoogleTrendsInterestAdapter(BaseAdapter):
    name = "google_trends_interest"
    display_name = "Google 트렌드(인기도)"
    default_source_type = SOURCE_TYPE_SUSTAINED
    risk = "medium"

    def _collect_keywords(self) -> list[tuple[str, str]]:
        """(keyword, category_id) 목록. max_keywords 로 상한."""
        max_kw = int(self.settings.get("max_keywords", 8))
        pairs: list[tuple[str, str]] = []
        for cat in self.app_config.categories:
            kws = cat.get("keywords") or cat.get("news_queries") or []
            if kws:
                pairs.append((kws[0], cat["id"]))  # 카테고리당 대표 1개
        return pairs[:max_kw]

    def _fetch_sync(self, pairs: list[tuple[str, str]]) -> list[RawTrendItem]:
        # 지연 import: 미설치 시 여기서 ImportError -> 컬렉터가 격리
        from pytrends.request import TrendReq
        import time

        geo = self.settings.get("geo", "JP")
        hl = self.settings.get("hl", "ja-JP")
        timeframe = self.settings.get("timeframe", "now 7-d")
        batch_sleep = float(self.settings.get("batch_sleep_seconds", 2))

        pytrends = TrendReq(hl=hl, tz=540)  # tz=540 = JST(UTC+9, 분단위)
        scored: list[tuple[str, str, float]] = []  # (kw, cat, score)

        # pytrends 는 한 번에 최대 5개 키워드
        for start in range(0, len(pairs), 5):
            batch = pairs[start:start + 5]
            kw_list = [k for k, _ in batch]
            try:
                pytrends.build_payload(kw_list, geo=geo, timeframe=timeframe)
                df = pytrends.interest_over_time()
            except Exception as exc:  # 429 등
                log.warning("pytrends 배치 실패(%s): %s", kw_list, exc)
                continue
            for kw, cat_id in batch:
                if kw in getattr(df, "columns", []):
                    series = df[kw]
                    score = float(series.mean()) if len(series) else 0.0
                    scored.append((kw, cat_id, score))
            time.sleep(batch_sleep)

        scored.sort(key=lambda x: x[2], reverse=True)
        items: list[RawTrendItem] = []
        for i, (kw, cat_id, score) in enumerate(scored, start=1):
            items.append(RawTrendItem(
                term=kw,
                source=self.name,
                source_type=SOURCE_TYPE_SUSTAINED,
                category=self._safe_category(cat_id),
                rank=i,
                metric_label="인기도",
                metric_value=round(score, 1),
                url=f"https://trends.google.com/trends/explore?geo={geo}&q={kw}",
                extra={"timeframe": timeframe},
            ))
        return items

    async def fetch(self) -> list[RawTrendItem]:
        pairs = self._collect_keywords()
        if not pairs:
            return []
        return await asyncio.to_thread(self._fetch_sync, pairs)
