"""트렌드 워드 한국어 번역 (무료·키 불필요).

- Google의 공개 translate 엔드포인트(client=gtx)를 사용한다. **API 키가 필요 없고 무료**다.
  단, 이는 비공식 엔드포인트라 과도한 호출 시 일시 차단될 수 있으므로:
    · 동시 요청 수 제한(concurrency)
    · 한 주기당 새 번역 수 제한(max_new_per_cycle)
    · **번역 결과는 SQLite에 캐시**하여 같은 워드는 다시는 번역하지 않는다.
  실패한 워드는 조용히 건너뛰고 원어만 표시한다(graceful).
- sl=auto 라 일본어/중국어(대만) 모두 자동 감지해 한국어로 번역한다.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger("jptrend.translate")

GTX_URL = "https://translate.googleapis.com/translate_a/single"


def _mostly_korean(text: str) -> bool:
    """글자의 절반 이상이 한글이면 이미 한국어로 간주(번역 불필요)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    hangul = sum(1 for c in letters if "가" <= c <= "힣")
    return hangul / len(letters) >= 0.5


class Translator:
    def __init__(self, settings: dict, user_agent: str):
        self.enabled = bool(settings.get("enabled", True))
        self.target = settings.get("target_lang", "ko")
        self.max_new = int(settings.get("max_new_per_cycle", 300))
        self.concurrency = int(settings.get("concurrency", 5))
        self.timeout = float(settings.get("timeout_seconds", 10))
        self.user_agent = user_agent

    async def _translate_one(self, client: httpx.AsyncClient, term: str) -> str | None:
        params = {"client": "gtx", "sl": "auto", "tl": self.target, "dt": "t", "q": term}
        try:
            r = await client.get(GTX_URL, params=params)
            r.raise_for_status()
            data = r.json()
            segments = data[0] or []
            ko = "".join(seg[0] for seg in segments if seg and seg[0]).strip()
            return ko or None
        except Exception as exc:
            log.debug("번역 실패 '%s': %s", term, exc)
            return None

    async def translate(self, terms: list[str]) -> dict[str, str]:
        """미번역 term 리스트 → {term: 한국어}. 실패 term은 생략."""
        if not self.enabled:
            return {}
        # 중복 제거 + 이미 한국어인 워드 제외(target=ko) + 상한
        skip_korean = self.target == "ko"
        uniq = [
            t for t in dict.fromkeys(terms)
            if t and t.strip() and not (skip_korean and _mostly_korean(t))
        ][: self.max_new]
        if not uniq:
            return {}
        sem = asyncio.Semaphore(self.concurrency)
        out: dict[str, str] = {}

        async with httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            async def worker(term: str) -> None:
                async with sem:
                    ko = await self._translate_one(client, term)
                    if ko:
                        out[term] = ko

            await asyncio.gather(*(worker(t) for t in uniq), return_exceptions=True)

        log.info("번역 완료: %d/%d", len(out), len(uniq))
        return out
