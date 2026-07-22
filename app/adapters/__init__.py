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
from .google_news_top import GoogleNewsTopAdapter
from .google_trends_interest import GoogleTrendsInterestAdapter
from .google_trends_rss import GoogleTrendsRssAdapter
from .naver import NaverDataLabAdapter, NaverNewsAdapter
from .news_keywords import NewsKeywordsAdapter
from .nhk_rss import NhkRssAdapter
from .ptt_taiwan import PttTaiwanAdapter
from .signal_bz import SignalBzAdapter
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
    GoogleNewsTopAdapter.name: GoogleNewsTopAdapter,
    NhkRssAdapter.name: NhkRssAdapter,
    YouTubeTrendingAdapter.name: YouTubeTrendingAdapter,
    TrendCalendarAdapter.name: TrendCalendarAdapter,
    GoogleTrendsInterestAdapter.name: GoogleTrendsInterestAdapter,
    YahooRealtimeAdapter.name: YahooRealtimeAdapter,
    PttTaiwanAdapter.name: PttTaiwanAdapter,
    SignalBzAdapter.name: SignalBzAdapter,
    NaverNewsAdapter.name: NaverNewsAdapter,
    NaverDataLabAdapter.name: NaverDataLabAdapter,
    NewsKeywordsAdapter.name: NewsKeywordsAdapter,
}


def build_adapters(config: "AppConfig", http: "PoliteClient", storage=None) -> list[BaseAdapter]:
    """config.sources × regions 를 보고 enabled 인 어댑터를 지역별로 인스턴스화."""
    adapters: list[BaseAdapter] = []
    enabled_regions = config.enabled_region_ids
    for name, settings in config.sources.items():
        cls = ADAPTER_REGISTRY.get(name)
        if cls is None:
            log.warning("알 수 없는 소스 '%s' — 레지스트리에 없음, 건너뜀", name)
            continue
        if not (settings or {}).get("enabled", True):
            log.info("소스 '%s' 비활성(enabled: false) — 건너뜀", name)
            continue
        # 이 소스가 서비스하는 지역 (미지정이면 활성 지역 전체)
        source_regions = (settings or {}).get("regions") or enabled_regions
        for region in source_regions:
            if region not in enabled_regions:
                continue
            adapters.append(cls(settings, http, config, region, storage))
            log.info("소스 '%s' 활성화 [%s] (risk=%s%s)", name, region, cls.risk,
                     ", 파생" if cls.derived else "")
    return adapters
