"""네이버 공식 Open API — 한국 전용.

네이버는 robots.txt 가 전면 Disallow 라 스크래핑이 불가하고, 뉴스 RSS 도 폐지됐다.
합법적으로 네이버 데이터를 쓰는 유일한 길은 **공식 Open API**다(무료, 개발자 등록 필요).
  - 발급: https://developers.naver.com → 애플리케이션 등록 → Client ID/Secret
  - .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 를 넣으면 활성화. 없으면 graceful.

두 어댑터:
  · NaverNewsAdapter    : 검색 API(뉴스) — 카테고리별 네이버 뉴스. sustained.
  · NaverDataLabAdapter : 데이터랩 검색어트렌드 — 카테고리 키워드의 네이버 검색 관심도.
    한국은 네이버 검색 점유율이 높아 Google 트렌드보다 대표성이 있다. sustained.
"""
from __future__ import annotations

import html
import re
import urllib.parse
from datetime import date, timedelta

from ..models import RawTrendItem, SOURCE_TYPE_SUSTAINED
from .base import BaseAdapter

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    """네이버 검색 결과의 <b> 태그·HTML 엔티티 제거."""
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


class _NaverBase(BaseAdapter):
    def _auth_headers(self) -> dict[str, str]:
        cid = self.app_config.env("NAVER_CLIENT_ID")
        sec = self.app_config.env("NAVER_CLIENT_SECRET")
        if not cid or not sec:
            raise RuntimeError(
                "NAVER_CLIENT_ID/SECRET 미설정 — .env 에 넣으면 활성화됩니다 "
                "(developers.naver.com 에서 무료 발급)."
            )
        return {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec}


class NaverNewsAdapter(_NaverBase):
    name = "naver_news"
    display_name = "네이버 뉴스"
    default_source_type = SOURCE_TYPE_SUSTAINED
    risk = "low"

    async def fetch(self) -> list[RawTrendItem]:
        headers = self._auth_headers()  # 키 없으면 여기서 예외 → 소스만 error
        per_cat = int(self.settings.get("per_category_limit", 8))
        sort = self.settings.get("sort", "date")  # date | sim
        items: list[RawTrendItem] = []

        for cat in self.app_config.categories:
            cat_id = cat["id"]
            queries = self.app_config.news_queries(cat_id, self.region)
            if not queries:
                continue
            q = urllib.parse.quote(queries[0])
            url = (f"https://openapi.naver.com/v1/search/news.json"
                   f"?query={q}&display={per_cat}&sort={sort}")
            try:
                resp = await self.http.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                continue  # 한 카테고리 실패는 건너뜀
            seen: set[str] = set()
            rank = 0
            for it in data.get("items", []):
                title = _clean(it.get("title", ""))
                if not title or title in seen:
                    continue
                seen.add(title)
                rank += 1
                items.append(RawTrendItem(
                    term=title,
                    source=self.name,
                    source_type=SOURCE_TYPE_SUSTAINED,
                    category=cat_id,
                    rank=rank,
                    metric_label="네이버뉴스",
                    metric_value=float(max(0, per_cat - rank + 1)),
                    url=it.get("link") or it.get("originallink", ""),
                    extra={"pubDate": it.get("pubDate", "")},
                ))
        return items


class NaverDataLabAdapter(_NaverBase):
    name = "naver_datalab"
    display_name = "네이버 데이터랩(검색트렌드)"
    default_source_type = SOURCE_TYPE_SUSTAINED
    risk = "low"

    async def fetch(self) -> list[RawTrendItem]:
        headers = {**self._auth_headers(), "Content-Type": "application/json"}
        days = int(self.settings.get("window_days", 30))
        end = date.today()
        start = end - timedelta(days=days)

        # 카테고리 키워드로 키워드그룹 구성 (그룹명=카테고리 id)
        groups: list[dict] = []
        group_cat: dict[str, str] = {}
        for cat in self.app_config.categories:
            kws = self.app_config.keywords(cat["id"], self.region)
            if not kws:
                continue
            groups.append({"groupName": cat["id"], "keywords": kws[:5]})
            group_cat[cat["id"]] = cat["id"]
        if not groups:
            return []

        scored: list[tuple[str, str, float]] = []  # (groupName, keyword_label, ratio)
        # 데이터랩은 요청당 키워드그룹 최대 5개
        for i in range(0, len(groups), 5):
            batch = groups[i:i + 5]
            body = {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "timeUnit": "date",
                "keywordGroups": batch,
            }
            try:
                resp = await self.http.post(
                    "https://openapi.naver.com/v1/datalab/search",
                    headers=headers, json=body,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                continue
            for res in data.get("results", []):
                gname = res.get("title", "")
                series = res.get("data", []) or []
                ratio = float(series[-1].get("ratio", 0.0)) if series else 0.0
                label = (res.get("keywords") or [gname])[0]
                scored.append((gname, label, ratio))

        scored.sort(key=lambda x: x[2], reverse=True)
        items: list[RawTrendItem] = []
        for rank, (gname, label, ratio) in enumerate(scored, start=1):
            items.append(RawTrendItem(
                term=label,
                source=self.name,
                source_type=SOURCE_TYPE_SUSTAINED,
                category=self._safe_category(group_cat.get(gname, "trend")),
                rank=rank,
                metric_label="네이버검색",
                metric_value=round(ratio, 1),
                url=f"https://search.naver.com/search.naver?query={urllib.parse.quote(label)}",
                extra={"window_days": days},
            ))
        return items
