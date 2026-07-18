"""어댑터 베이스 클래스.

새 데이터 소스를 추가하려면:
  1. BaseAdapter 를 상속한 클래스를 이 패키지에 만들고 `fetch()` 를 구현한다.
  2. adapters/__init__.py 의 ADAPTER_REGISTRY 에 등록한다.
  3. config.yaml 의 sources 에 설정 블록을 추가한다.
그러면 컬렉터/대시보드가 자동으로 인식한다.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..models import RawTrendItem, SOURCE_TYPE_REALTIME

if TYPE_CHECKING:
    from ..config import AppConfig
    from ..http_client import PoliteClient

log = logging.getLogger("jptrend.adapter")


class BaseAdapter(ABC):
    #: config.yaml 의 sources 키와 일치해야 하는 소스 이름
    name: str = "base"
    #: 이 소스의 기본 성격 (개별 항목에서 덮어쓸 수 있음)
    default_source_type: str = SOURCE_TYPE_REALTIME
    #: 사람이 읽는 표시 이름
    display_name: str = "Base"
    #: 이용약관/차단 리스크 등급 (low | medium | high) — 대시보드/헬스 표시용
    risk: str = "low"

    def __init__(self, settings: dict, http: "PoliteClient", app_config: "AppConfig"):
        self.settings = settings or {}
        self.http = http
        self.app_config = app_config

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("enabled", True))

    @abstractmethod
    async def fetch(self) -> list[RawTrendItem]:
        """트렌드 항목들을 수집해 반환. 실패 시 예외를 던지면 컬렉터가 격리 처리한다."""
        raise NotImplementedError

    # 편의: 카테고리 id 유효성 보정 (설정에 없는 id면 default로)
    def _safe_category(self, category_id: str | None, default: str = "trend") -> str:
        ids = self.app_config.category_ids
        if category_id in ids:
            return category_id
        return default if default in ids else (ids[0] if ids else "trend")
