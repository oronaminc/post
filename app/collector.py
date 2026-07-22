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
    def __init__(self, adapters: list[BaseAdapter], storage: Storage, config, translator=None):
        self.adapters = adapters
        self.storage = storage
        self.config = config
        self.translator = translator
        self._lock = asyncio.Lock()  # 동시 수집 방지(스케줄러 + 수동 겹침 방지)

    async def collect_all(self) -> dict[str, str]:
        """모든 어댑터를 동시에 격리 실행. 소스명 -> 상태 요약 반환."""
        async with self._lock:
            # 1차 소스 먼저, 그 결과를 재료로 쓰는 파생 소스는 2차로 실행
            primary = [a for a in self.adapters if not a.derived]
            derived = [a for a in self.adapters if a.derived]
            log.info("수집 시작: 1차 %d개 · 파생 %d개", len(primary), len(derived))
            r1 = await asyncio.gather(
                *(self._run_one(a) for a in primary), return_exceptions=True)
            r2 = await asyncio.gather(
                *(self._run_one(a) for a in derived), return_exceptions=True)
            ordered = primary + derived
            results = list(r1) + list(r2)
            summary: dict[str, str] = {}
            for adapter, res in zip(ordered, results):
                key = f"{adapter.name}@{adapter.region}"
                if isinstance(res, Exception):
                    summary[key] = f"error: {res}"
                else:
                    summary[key] = res
            # 현재 표시될 트렌드 워드 중 미번역분을 한국어로 번역(캐시)
            try:
                await self._translate_current()
            except Exception as exc:
                log.warning("번역 단계 실패(무시): %s", exc)
            # 오래된 이력 정리
            try:
                await asyncio.to_thread(self.storage.prune, self.config.retention_days)
            except Exception as exc:
                log.warning("prune 실패: %s", exc)
            log.info("수집 완료: %s", summary)
            return summary

    async def _translate_current(self) -> None:
        """각 지역 현재 항목 중 term_ko 가 없는(미번역) 워드만 번역해 캐시에 저장.

        청크 단위로 저장해 콜드스타트에도 번역이 점진적으로 나타나게 한다.
        """
        if not self.translator or not getattr(self.translator, "enabled", False):
            return
        missing: set[str] = set()
        for region in self.config.enabled_region_ids:
            items = await asyncio.to_thread(self.storage.get_current_items, region)
            for it in items:
                # 이미 번역돼 있거나(term_ko) 번역이 불필요한(한국어 등) 워드는 제외
                # → 상한(max_new)이 실제 번역 대상에만 적용되게.
                if not it.get("term_ko") and self.translator.needs_translation(it["term"]):
                    missing.add(it["term"])
        if not missing:
            return
        pending = list(missing)[: self.translator.max_new]  # 주기당 상한
        chunk_size = 40
        saved = 0
        for i in range(0, len(pending), chunk_size):
            chunk = pending[i:i + chunk_size]
            translated = await self.translator.translate(chunk)
            if translated:
                await asyncio.to_thread(self.storage.save_translations, translated)
                saved += len(translated)
        if saved:
            log.info("번역 캐시 저장: %d건", saved)

    async def _run_one(self, adapter: BaseAdapter) -> str:
        """어댑터 하나를 타임아웃/예외 격리로 실행."""
        run_id = await asyncio.to_thread(self.storage.start_run, adapter.name, adapter.region)
        collected_at = datetime.now(timezone.utc).isoformat()
        timeout = self.config.per_source_timeout_seconds
        try:
            items = await asyncio.wait_for(adapter.fetch(), timeout=timeout)
            for it in items:                 # 어댑터의 지역을 각 항목에 stamp
                it.region = adapter.region
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
