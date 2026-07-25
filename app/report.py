"""일일 뉴스 트렌드 인사이트 리포트 (한 파일에 매일 누적).

매일 정해진 시각에, 나라별·카테고리별 뉴스 트렌드를 요약하고 규칙기반 인사이트를
붙여 하나의 마크다운 파일에 최신순으로 누적한다. (동영상/YouTube는 제외 — 뉴스 전용)

인사이트(규칙기반):
  - 오늘 최다 화제(뉴스 키워드 문서빈도 1위)
  - 검색·뉴스 동시 급상승(급상승 검색어와 뉴스 키워드의 교집합) = 강한 트렌드
  - 뉴스가 가장 많은 카테고리
  - 국가 공통 화제(한국어 번역 기준으로 2개국 이상에서 등장)
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("jptrend.report")

KST = ZoneInfo("Asia/Seoul")
# 급상승 검색 성격 소스(지역별로 존재하는 것만 쓰임)
_SEARCH_SOURCES = ["signal_bz", "google_trends_rss", "yahoo_realtime",
                   "trend_calendar", "ptt_taiwan"]
_NEWS_SOURCES = ["google_news_top", "google_news_rss", "naver_news", "nhk_rss"]


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _ko(item: dict) -> str:
    """표시용: 한국어 번역이 있으면 그걸(원어와 다를 때)."""
    ko = (item.get("term_ko") or "").strip()
    return ko if ko and ko != (item.get("term") or "").strip() else item.get("term", "")


def _region_items_by_source(storage, region: str) -> dict[str, list[dict]]:
    items = storage.get_current_items(region)
    by_src: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_src[it.get("source", "")].append(it)
    for s in by_src:
        by_src[s].sort(key=lambda x: x.get("rank", 999))
    return by_src


def generate_report(storage, config) -> str:
    date = today_kst()
    out: list[str] = [f"# 📅 {date} 트렌드 인사이트", ""]
    cross: dict[str, set[str]] = defaultdict(set)  # 한국어 키워드 -> {region}

    for r in config.enabled_regions:
        rid, flag, label = r["id"], r.get("flag", ""), r.get("label", r["id"])
        by_src = _region_items_by_source(storage, rid)

        out.append(f"## {flag} {label}")
        out.append("")

        # 실시간 급상승 검색
        rt: list[str] = []
        for s in _SEARCH_SOURCES:
            rt.extend(it["term"] for it in by_src.get(s, [])[:8])
        rt = list(dict.fromkeys(rt))[:12]
        if rt:
            out.append("**🔥 실시간 급상승 검색**: " + " · ".join(rt))
            out.append("")

        # 뉴스 키워드 트렌드 (여러 매체가 다룬 주제)
        nk = by_src.get("news_keywords", [])[:15]
        if nk:
            out.append("**📰 뉴스 키워드 트렌드** _(괄호=다룬 기사 수)_")
            for it in nk:
                ko = _ko(it)
                extra = f" — {ko}" if ko and ko != it["term"] else ""
                label_cat = it.get("category_label") or it.get("category", "")
                out.append(f"- **{it['term']}**{extra} ({int(it['metric_value'])}) · {label_cat}")
                cross[ko or it["term"]].add(rid)
            out.append("")

        # 카테고리별 주요 뉴스 (있는 카테고리만)
        cat_news: dict[str, list[dict]] = defaultdict(list)
        for s in _NEWS_SOURCES:
            for it in by_src.get(s, []):
                cat_news[it.get("category", "")].append(it)
        cat_lines: list[str] = []
        for c in config.categories:
            arts = cat_news.get(c["id"], [])
            if not arts:
                continue
            top = arts[0]
            ko = _ko(top)
            extra = f" _( {ko} )_" if ko and ko != top["term"] else ""
            cat_lines.append(f"- **{c['label']}**: {top['term']}{extra}")
        if cat_lines:
            out.append("**🗂 카테고리별 주요 뉴스**")
            out.extend(cat_lines)
            out.append("")

        # 인사이트 (규칙기반)
        insights: list[str] = []
        if nk:
            insights.append(f"오늘 최다 화제: **{nk[0]['term']}** ({int(nk[0]['metric_value'])}개 기사)")
        search_set = set(rt)
        overlap: list[str] = []
        for it in nk:
            t = it["term"]
            if any(t in s or s in t for s in search_set):
                overlap.append(t)
        overlap = list(dict.fromkeys(overlap))[:5]
        if overlap:
            insights.append("검색·뉴스 동시 급상승(강한 트렌드): " + ", ".join(overlap))
        if cat_news:
            busiest = max(config.categories, key=lambda c: len(cat_news.get(c["id"], [])))
            if cat_news.get(busiest["id"]):
                insights.append(f"뉴스가 가장 많은 카테고리: **{busiest['label']}**")
        if insights:
            out.append("**💡 인사이트**")
            out.extend(f"- {ins}" for ins in insights)
            out.append("")
        out.append("")

    # 국가 공통 화제 (한국어 번역 기준 2개국 이상)
    flags = {r["id"]: r.get("flag", "") for r in config.enabled_regions}
    common = [(k, regs) for k, regs in cross.items()
              if len(regs) >= 2 and len(k) >= 2]
    common.sort(key=lambda x: -len(x[1]))
    if common:
        out.append("## 🌏 종합 인사이트 (국가 공통 화제)")
        for k, regs in common[:8]:
            out.append(f"- **{k}** — " + "".join(flags.get(x, "") for x in regs) + " 공통")
        out.append("")

    out.append("---")
    out.append("")
    return "\n".join(out)


def append_daily_report(storage, config, path: str | Path) -> str:
    """오늘 섹션을 생성해 파일 최상단에 upsert(같은 날짜 있으면 교체)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    section = generate_report(storage, config).rstrip() + "\n\n"
    date = today_kst()

    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing:
        # 날짜 헤더 기준으로 쪼개서 오늘 섹션 제거(중복 방지)
        parts = re.split(r"(?=^# 📅 )", existing, flags=re.M)
        parts = [p for p in parts if not p.startswith(f"# 📅 {date}")]
        existing = "".join(parts)

    path.write_text(section + existing.lstrip(), encoding="utf-8")
    log.info("일일 리포트 갱신: %s (%s)", path, date)
    return str(path)
