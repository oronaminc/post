"""Yahoo! 리얼타임 검색 (일본) — X 기반 실시간 급상승 워드.

⚠️⚠️ 리스크: 높음.
  - Yahoo! JAPAN 이용약관은 robots.txt 와 별개로 자동화된 수집/스크래핑을 제한한다.
    이 어댑터는 사용자가 명시적으로 켠 경우에만 동작하며(config enabled),
    끄려면 config.yaml 에서 sources.yahoo_realtime.enabled: false 로 두면 된다.
  - 강한 요청 간격(config http.host_delays: search.yahoo.co.jp)과 식별 UA 를 적용한다.
  - 개인정보/로그인 데이터는 다루지 않으며, 공개된 급상승 워드 랭킹만 읽는다.

파싱: 페이지의 <script id="__NEXT_DATA__"> JSON 안
     props.pageProps.pageData.buzzTrend.items[] (query/rankUp/rankDiff/tweetCount/genre)
     를 사용. 구조가 바뀌면 재귀 탐색으로 fallback.
성격: 실시간 급상승(realtime).
"""
from __future__ import annotations

import json
import re

from ..models import RawTrendItem, SOURCE_TYPE_REALTIME
from .base import BaseAdapter

URL = "https://search.yahoo.co.jp/realtime"
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)


def _find_buzz_items(obj):
    """중첩 dict/list 에서 buzzTrend.items 같은 트렌드 리스트를 찾는다."""
    # 우선 정규 경로 시도
    try:
        bt = obj["props"]["pageProps"]["pageData"]["buzzTrend"]
        merged = []
        if isinstance(bt.get("trendingItem"), dict):
            merged.append(bt["trendingItem"])
        merged.extend(bt.get("items", []) or [])
        merged.extend(bt.get("otherItems", []) or [])
        if merged:
            return merged
    except (KeyError, TypeError):
        pass

    # fallback: 'query' 키를 가진 dict 들의 리스트를 재귀 탐색
    found: list = []

    def walk(o):
        if isinstance(o, dict):
            if "query" in o and isinstance(o.get("query"), str):
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return found


class YahooRealtimeAdapter(BaseAdapter):
    name = "yahoo_realtime"
    display_name = "Yahoo! 리얼타임"
    default_source_type = SOURCE_TYPE_REALTIME
    risk = "high"

    async def fetch(self) -> list[RawTrendItem]:
        max_items = int(self.settings.get("max_items", 30))
        category = self._safe_category(self.settings.get("default_category", "trend"))

        html = await self.http.get_text(URL)
        m = NEXT_DATA_RE.search(html)
        if not m:
            raise RuntimeError("Yahoo 리얼타임 __NEXT_DATA__ 미발견 (구조 변경 가능)")
        data = json.loads(m.group(1))
        buzz = _find_buzz_items(data)
        if not buzz:
            raise RuntimeError("Yahoo 리얼타임 트렌드 항목 미발견 (구조 변경 가능)")

        items: list[RawTrendItem] = []
        seen: set[str] = set()
        rank = 0
        for entry in buzz:
            if not isinstance(entry, dict):
                continue
            term = (entry.get("query") or "").strip()
            if not term or term in seen:
                continue
            seen.add(term)
            rank += 1
            # rankUp/rankDiff: 소스가 주는 변동값. int 로 정규화.
            change = entry.get("rankDiff")
            if change is None:
                change = entry.get("rankUp")
            try:
                change = int(round(float(change))) if change is not None else None
            except (TypeError, ValueError):
                change = None
            tweet_count = entry.get("tweetCount")
            try:
                metric_value = float(tweet_count) if tweet_count is not None else float(max_items - rank + 1)
            except (TypeError, ValueError):
                metric_value = float(max_items - rank + 1)

            items.append(RawTrendItem(
                term=term,
                source=self.name,
                source_type=SOURCE_TYPE_REALTIME,
                category=category,
                rank=rank,
                metric_label="tweet" if tweet_count else "랭킹",
                metric_value=metric_value,
                url=entry.get("url") or f"https://search.yahoo.co.jp/realtime/search?p={term}",
                rank_change=change,
                extra={"genre": entry.get("genre", ""), "tweet_count": tweet_count},
            ))
            if rank >= max_items:
                break
        return items
