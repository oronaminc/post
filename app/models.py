"""정규화된 트렌드 데이터 모델.

모든 어댑터는 소스가 무엇이든 `RawTrendItem` 리스트를 반환한다.
컬렉터가 여기에 수집 시각(collected_at)을 찍어 저장소에 넣는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# 소스가 성격상 '실시간 급상승'인지 '지속 관심도'인지 선언하는 값.
SOURCE_TYPE_REALTIME = "realtime"   # 실시간 급상승
SOURCE_TYPE_SUSTAINED = "sustained"  # 지속 관심도


@dataclass
class RawTrendItem:
    """한 소스에서 나온 트렌드 항목 한 건 (정규화 형태)."""

    term: str                       # 트렌드 워드 / 헤드라인
    source: str                     # 소스(어댑터) 이름
    source_type: str                # SOURCE_TYPE_REALTIME | SOURCE_TYPE_SUSTAINED
    category: str                   # 카테고리 id (config의 categories[].id)
    rank: int                       # 소스 내 순위(1부터)
    metric_label: str = ""          # 지표 이름 (예: "검색량", "tweet", "views", "인기도")
    metric_value: float = 0.0       # 지표 수치 (정렬용)
    url: str = ""                   # 관련 링크
    rank_change: Optional[int] = None  # 소스가 직접 제공하는 변동(+는 상승). 없으면 None
    extra: dict[str, Any] = field(default_factory=dict)  # 소스별 부가정보

    def clean(self) -> "RawTrendItem":
        """빈 term 방지 및 필드 정리."""
        self.term = (self.term or "").strip()
        self.source_type = self.source_type or SOURCE_TYPE_REALTIME
        if self.rank < 1:
            self.rank = 1
        return self
