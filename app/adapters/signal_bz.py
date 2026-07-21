"""signal.bz 실시간 검색어 — 한국 전용.

폐지된 네이버/다음 실시간 검색어(실검)를 대체하는 **집계 서비스**의 공개 API.
  - 엔드포인트: https://api.signal.bz/news/realtime (JSON, 키 불필요·무료)
  - top10: [{rank, keyword, state}] — state: n(신규)/+(상승)/-(하락)/s(변동없음)
  - 네이버를 직접 스크래핑하지 않는다(네이버 robots.txt 는 전면 Disallow).
    signal.bz 는 여러 포털의 실시간 트렌드를 합법적으로 집계·제공하는 제3자 API다.
성격: 실시간 급상승(realtime).
리스크: 낮음(공개 집계 API). 다만 비공식 제3자 서비스임을 README 에 명시.
"""
from __future__ import annotations

import urllib.parse

from ..models import RawTrendItem, SOURCE_TYPE_REALTIME
from .base import BaseAdapter

API_URL = "https://api.signal.bz/news/realtime"


class SignalBzAdapter(BaseAdapter):
    name = "signal_bz"
    display_name = "실시간 검색어(signal.bz)"
    default_source_type = SOURCE_TYPE_REALTIME
    risk = "low"

    async def fetch(self) -> list[RawTrendItem]:
        category = self._safe_category(self.settings.get("default_category", "trend"))
        resp = await self.http.get(API_URL)
        resp.raise_for_status()
        data = resp.json()

        top = data.get("top10") or []
        items: list[RawTrendItem] = []
        for entry in top:
            keyword = (entry.get("keyword") or "").strip()
            if not keyword:
                continue
            rank = int(entry.get("rank") or (len(items) + 1))
            state = entry.get("state", "")
            # state 로 상승/신규 힌트 (매그니튜드는 없음 → 표식만)
            rank_change = None
            if state == "+":
                rank_change = 1
            elif state == "-":
                rank_change = -1
            items.append(RawTrendItem(
                term=keyword,
                source=self.name,
                source_type=SOURCE_TYPE_REALTIME,
                category=category,
                rank=rank,
                metric_label="실검",
                metric_value=float(max(0, 11 - rank)),
                url=f"https://search.naver.com/search.naver?query={urllib.parse.quote(keyword)}",
                rank_change=rank_change,
                extra={"state": state},
            ))
        if not items:
            raise RuntimeError("signal.bz 응답에 top10 이 없음 (구조 변경 가능)")
        return items
