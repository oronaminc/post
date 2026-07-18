"""트렌드 캘린더 (jp.trend-calendar.com) — 통합 트렌드 랭킹 스크래핑.

⚠️ 리스크: 중간. 제3자 사이트 스크래핑.
  - robots.txt 실측: 랭킹 페이지는 Disallow 대상이 아님(wp-*/author/category 등만 차단).
  - 그래도 제3자 사이트이므로 저빈도 + 예의(느린 요청 간격, 식별 UA)로 접근한다.
    (요청 간격은 config http.host_delays 로 조절)

파싱: 페이지 내 트렌드 워드는 `twitter.com/search?q=<word>` 앵커로 노출되며,
     등장 순서가 곧 랭킹이다. 앵커 텍스트를 워드로, 순서를 순위로 사용.
성격: 실시간 급상승(realtime) — X 기반 급상승 워드 집계.
"""
from __future__ import annotations

import re
import urllib.parse

from bs4 import BeautifulSoup

from ..models import RawTrendItem, SOURCE_TYPE_REALTIME
from .base import BaseAdapter

BASE_URL = "https://jp.trend-calendar.com/"


class TrendCalendarAdapter(BaseAdapter):
    name = "trend_calendar"
    display_name = "트렌드 캘린더"
    default_source_type = SOURCE_TYPE_REALTIME
    risk = "medium"

    async def fetch(self) -> list[RawTrendItem]:
        max_items = int(self.settings.get("max_items", 30))
        category = self._safe_category(self.settings.get("default_category", "trend"))

        html = await self.http.get_text(BASE_URL)
        soup = BeautifulSoup(html, "html.parser")

        items: list[RawTrendItem] = []
        seen: set[str] = set()
        rank = 0
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "twitter.com/search" not in href and "x.com/search" not in href:
                continue
            term = a.get_text(strip=True)
            if not term:
                # 텍스트가 없으면 href의 q= 파라미터에서 복원
                m = re.search(r"[?&]q=([^&]+)", href)
                if m:
                    term = urllib.parse.unquote(m.group(1))
            term = term.strip()
            if not term or term in seen:
                continue
            seen.add(term)
            rank += 1
            items.append(RawTrendItem(
                term=term,
                source=self.name,
                source_type=SOURCE_TYPE_REALTIME,
                category=category,
                rank=rank,
                metric_label="랭킹",
                metric_value=float(max(0, max_items - rank + 1)),
                url=href,
                extra={"platform": "X"},
            ))
            if rank >= max_items:
                break

        if not items:
            # 사이트 구조가 바뀌면 명시적으로 실패시켜 헬스에 드러나게 한다.
            raise RuntimeError("트렌드 캘린더에서 랭킹 앵커를 찾지 못함 (구조 변경 가능)")
        return items
