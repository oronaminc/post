"""YouTube 급상승 (일본) — 공식 YouTube Data API v3.

수집 방식: videos.list?chart=mostPopular&regionCode=JP
  - 공식 무료 API(쿼터 제한). .env 의 YOUTUBE_API_KEY 필요.
  - 키가 없으면 예외를 던져 컬렉터가 해당 소스만 'error'로 격리 → 나머지는 정상.
videoCategoryId 를 config 의 category_map 으로 우리 카테고리에 매핑.
성격: 실시간 급상승(realtime).
"""
from __future__ import annotations

from ..models import RawTrendItem, SOURCE_TYPE_REALTIME
from .base import BaseAdapter

API_URL = "https://www.googleapis.com/youtube/v3/videos"


class MissingApiKey(RuntimeError):
    pass


class YouTubeTrendingAdapter(BaseAdapter):
    name = "youtube_trending"
    display_name = "YouTube 급상승"
    default_source_type = SOURCE_TYPE_REALTIME
    risk = "low"

    async def fetch(self) -> list[RawTrendItem]:
        api_key = self.app_config.env("YOUTUBE_API_KEY")
        if not api_key:
            raise MissingApiKey(
                "YOUTUBE_API_KEY 미설정 — .env 에 키를 넣으면 활성화됩니다."
            )

        region = self.settings.get("region", "JP")
        max_items = int(self.settings.get("max_items", 40))
        cat_map: dict[str, str] = {str(k): v for k, v in (self.settings.get("category_map") or {}).items()}
        default_cat = self._safe_category(self.settings.get("default_category", "trend"))

        params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": region,
            "maxResults": min(max_items, 50),
            "key": api_key,
        }
        resp = await self.http.get(API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        items: list[RawTrendItem] = []
        for i, v in enumerate(data.get("items", [])[:max_items], start=1):
            snippet = v.get("snippet", {})
            stats = v.get("statistics", {})
            title = (snippet.get("title") or "").strip()
            if not title:
                continue
            yt_cat = str(snippet.get("categoryId", ""))
            category = self._safe_category(cat_map.get(yt_cat, default_cat), default_cat)
            views = float(stats.get("viewCount", 0) or 0)
            items.append(RawTrendItem(
                term=title,
                source=self.name,
                source_type=SOURCE_TYPE_REALTIME,
                category=category,
                rank=i,
                metric_label="조회수",
                metric_value=views,
                url=f"https://www.youtube.com/watch?v={v.get('id','')}",
                extra={
                    "channel": snippet.get("channelTitle", ""),
                    "yt_category_id": yt_cat,
                    "views": int(views),
                },
            ))
        return items
