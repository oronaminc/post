"""'실시간 급상승' vs '지속 관심도' 분류/보강.

각 항목은 소스가 선언한 source_type 을 1차 축으로 삼되,
이력 기반 지표(등장 횟수/지속 시간/순위 변동)로 다음 태그를 덧붙인다.
  - is_rising     : 이번에 순위가 크게 오르거나 새로 진입한 급상승
  - is_persistent : 여러 수집에 걸쳐 오래 반복 등장한 지속 관심

뷰 필터(main.py /api/trends 의 view):
  - realtime  : source_type == realtime
  - sustained : source_type == sustained  또는  is_persistent
  - all       : 전체
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import SOURCE_TYPE_REALTIME, SOURCE_TYPE_SUSTAINED


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def enrich(items: list[dict[str, Any]], classification: dict) -> list[dict[str, Any]]:
    persist_min_occ = int(classification.get("persist_min_occurrences", 3))
    persist_min_hours = float(classification.get("persist_min_hours", 6))

    for it in items:
        rc = it.get("rank_change")
        occ = int(it.get("occurrences", 1) or 1)

        first = _parse_iso(it.get("first_seen"))
        last = _parse_iso(it.get("last_seen"))
        span_hours = 0.0
        if first and last:
            span_hours = (last - first).total_seconds() / 3600.0
        it["span_hours"] = round(span_hours, 1)

        # 지속 관심: 충분히 여러 번 + 충분히 오래 등장
        it["is_persistent"] = occ >= persist_min_occ and span_hours >= persist_min_hours

        # 급상승: 순위가 오르거나(변동 +) 새로 진입(occ==1) 하고 realtime 성격
        is_new = occ <= 1
        moved_up = rc is not None and rc > 0
        it["is_rising"] = bool(
            (it.get("source_type") == SOURCE_TYPE_REALTIME) and (is_new or moved_up)
        )

        # 화면 표시용 상태 라벨
        if it["is_persistent"]:
            it["status"] = "sustained"
        elif it["is_rising"]:
            it["status"] = "rising"
        else:
            it["status"] = it.get("source_type", SOURCE_TYPE_REALTIME)

    return items


def matches_view(item: dict[str, Any], view: str) -> bool:
    if view in ("", "all"):
        return True
    if view == "realtime":
        return item.get("source_type") == SOURCE_TYPE_REALTIME
    if view == "sustained":
        return item.get("source_type") == SOURCE_TYPE_SUSTAINED or item.get("is_persistent")
    return True
