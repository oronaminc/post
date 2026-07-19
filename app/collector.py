"""컬렉터 — 모든 어댑터를 격리 실행해 저장소에 적재한다.

핵심: 각 소스를 독립적으로 실행하고 예외/타임아웃을 개별 격리한다.
     한 소스가 죽어도 나머지 소스는 정상 수집된다(graceful degradation).
     실패는 runs 테이블에 status='error' 로 기록되어 대시보드 헬스에 표시된다.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

from .adapters.base import BaseAdapter
from .storage import Storage

log = logging.getLogger("jptrend.collector")

# 에러 메시지/로그에 URL이 섞여 들어올 때 API 키·토큰이 노출되지 않도록 마스킹.
_SECRET_RE = re.compile(r"([?&](?:key|api_key|apikey|token|access_token|password)=)[^&\s\"']+", re.I)


def _redact(text: str) -> str:
    return _SECRET_RE.sub(r"\1***", text or "")


class Collector:
    def __init__(self, adapters: list[BaseAdapter], storage: Storage, config):
        self.adapters = adapters
        self.storage = storage
        self.config = config
        self._lock = asyncio.Lock()  # 동시 수집 방지(스케줄러 + 수동 겹침 방지)

    async def collect_all(self) -> dict[str, str]:
        """모든 어댑터를 동시에 격리 실행. 소스명 -> 상태 요약 반환."""
        async with self._lock:
            log.info("수집 시작: %d개 소스", len(self.adapters))
            results = await asyncio.gather(
                *(self._run_one(a) for a in self.adapters),
                return_exceptions=True,  # 이중 안전장치
            )
            summary: dict[str, str] = {}
            for adapter, res in zip(self.adapters, results):
                if isinstance(res, Exception):
                    summary[adapter.name] = f"error: {res}"
                else:
                    summary[adapter.name] = res
            # 오래된 이력 정리
            try:
                await asyncio.to_thread(self.storage.prune, self.config.retention_days)
            except Exception as exc:
                log.warning("prune 실패: %s", exc)
            log.info("수집 완료: %s", summary)
            return summary

    async def _run_one(self, adapter: BaseAdapter) -> str:
        """어댑터 하나를 타임아웃/예외 격리로 실행."""
        run_id = await asyncio.to_thread(self.storage.start_run, adapter.name)
        collected_at = datetime.now(timezone.utc).isoformat()
        timeout = self.config.per_source_timeout_seconds
        try:
            items = await asyncio.wait_for(adapter.fetch(), timeout=timeout)
            count = await asyncio.to_thread(
                self.storage.save_items, run_id, collected_at, items
            )
            status = "ok" if count > 0 else "empty"
            await asyncio.to_thread(
                self.storage.finish_run, run_id, status, count, None
            )
            log.info("[%s] %s: %d건", adapter.name, status, count)
            return f"{status}: {count}건"
        except asyncio.TimeoutError:
            msg = f"타임아웃({timeout}s 초과)"
            await asyncio.to_thread(self.storage.finish_run, run_id, "error", 0, msg)
            log.warning("[%s] %s", adapter.name, msg)
            return f"error: {msg}"
        except Exception as exc:
            msg = _redact(f"{type(exc).__name__}: {exc}")
            await asyncio.to_thread(self.storage.finish_run, run_id, "error", 0, msg)
            log.warning("[%s] 실패: %s", adapter.name, msg)
            return f"error: {msg}"
