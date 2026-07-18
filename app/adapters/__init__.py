"""어댑터 레지스트리.

새 소스를 추가하려면 아래 ADAPTER_REGISTRY 에 `이름: 클래스` 를 등록하고,
config.yaml 의 sources 에 같은 이름으로 설정 블록을 넣으면 된다.
build_adapters() 가 config 를 보고 활성 어댑터만 조립한다.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import BaseAdapter
from .google_news_rss import GoogleNewsRssAdapter
from .google_trends_interest import GoogleTrendsInterestAdapter
from .google_trends_rss import GoogleTrendsRssAdapter
from .nhk_rss import NhkRssAdapter
from .trend_calendar import TrendCalendarAdapter
from .yahoo_realtime import YahooRealtimeAdapter
from .youtube_trending import YouTubeTrendingAdapter

if TYPE_CHECKING:
    from ..config import AppConfig
    from ..http_client import PoliteClient

log = logging.getLogger("jptrend.adapters")

#: 이름 -> 어댑터 클래스
ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    GoogleTrendsRssAdapter.name: GoogleTrendsRssAdapter,
    GoogleNewsRssAdapter.name: GoogleNewsRssAdapter,
    NhkRssAdapter.name: NhkRssAdapter,
    YouTubeTrendingAdapter.name: YouTubeTrendingAdapter,
    TrendCalendarAdapter.name: TrendCalendarAdapter,
    GoogleTrendsInterestAdapter.name: GoogleTrendsInterestAdapter,
    YahooRealtimeAdapter.name: YahooRealtimeAdapter,
}


def build_adapters(config: "AppConfig", http: "PoliteClient") -> list[BaseAdapter]:
    """config.sources 를 보고 enabled 인 어댑터만 인스턴스화."""
    adapters: list[BaseAdapter] = []
    for name, settings in config.sources.items():
        cls = ADAPTER_REGISTRY.get(name)
        if cls is None:
            log.warning("알 수 없는 소스 '%s' — 레지스트리에 없음, 건너뜀", name)
            continue
        if not (settings or {}).get("enabled", True):
            log.info("소스 '%s' 비활성(enabled: false) — 건너뜀", name)
            continue
        adapters.append(cls(settings, http, config))
        log.info("소스 '%s' 활성화 (risk=%s)", name, cls.risk)
    return adapters
