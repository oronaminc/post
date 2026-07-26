"""일일 뉴스 트렌드 인사이트 리포트.

하루 여러 번(기본 KST 00시·12시) 나라별·카테고리별 뉴스 트렌드를 요약하고
규칙기반 인사이트를 붙여 두 형태로 출력한다:
  - `reports/daily.md`  : 사람이 읽는 마크다운(최신순 누적, 날짜+시각 섹션)
  - `reports/daily.json`: 다른 프로젝트가 파싱하기 좋은 구조화 데이터(최신 스냅샷)

동영상/YouTube는 제외 — 뉴스 전용.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("jptrend.report")

KST = ZoneInfo("Asia/Seoul")
_SEARCH_SOURCES = ["signal_bz", "google_trends_rss", "yahoo_realtime",
                   "trend_calendar", "ptt_taiwan"]
_NEWS_SOURCES = ["google_news_top", "google_news_rss", "naver_news", "nhk_rss"]


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _ko(item: dict) -> str:
    ko = (item.get("term_ko") or "").strip()
    return ko if ko and ko != (item.get("term") or "").strip() else item.get("term", "")


def _by_source(storage, region: str) -> dict[str, list[dict]]:
    by_src: dict[str, list[dict]] = defaultdict(list)
    for it in storage.get_current_items(region):
        by_src[it.get("source", "")].append(it)
    for s in by_src:
        by_src[s].sort(key=lambda x: x.get("rank", 999))
    return by_src


# ----------------------------------------------------------- 데이터 구축
def build_report_data(storage, config) -> dict:
    now = datetime.now(KST)
    data: dict = {
        "generated_at": now.isoformat(timespec="minutes"),
        "date": now.strftime("%Y-%m-%d"),
        "slot": now.strftime("%H시"),
        "regions": {},
        "common_topics": [],
    }
    cross: dict[str, set[str]] = defaultdict(set)

    for r in config.enabled_regions:
        rid = r["id"]
        by_src = _by_source(storage, rid)

        rt: list[str] = []
        for s in _SEARCH_SOURCES:
            rt.extend(it["term"] for it in by_src.get(s, [])[:8])
        rt = list(dict.fromkeys(rt))[:12]

        nk: list[dict] = []
        for it in by_src.get("news_keywords", [])[:15]:
            ko = _ko(it)
            nk.append({
                "term": it["term"],
                "term_ko": ko if ko and ko != it["term"] else None,
                "articles": int(it["metric_value"]),
                "category": it.get("category"),
                "category_label": it.get("category_label") or it.get("category"),
            })
            cross[ko or it["term"]].add(rid)

        cat_raw: dict[str, list[dict]] = defaultdict(list)
        for s in _NEWS_SOURCES:
            for it in by_src.get(s, []):
                cat_raw[it.get("category", "")].append(it)
        category_news: dict[str, dict] = {}
        for c in config.categories:
            arts = cat_raw.get(c["id"], [])
            if not arts:
                continue
            top = arts[0]
            ko = _ko(top)
            category_news[c["id"]] = {
                "label": c["label"],
                "headline": top["term"],
                "headline_ko": ko if ko and ko != top["term"] else None,
                "url": top.get("url", ""),
            }

        insights: list[str] = []
        if nk:
            insights.append(f"오늘 최다 화제: {nk[0]['term']} ({nk[0]['articles']}개 기사)")
        search_set = set(rt)
        overlap = [k["term"] for k in nk if any(k["term"] in s or s in k["term"] for s in search_set)]
        overlap = list(dict.fromkeys(overlap))[:5]
        if overlap:
            insights.append("검색·뉴스 동시 급상승(강한 트렌드): " + ", ".join(overlap))
        if cat_raw:
            busiest = max(config.categories, key=lambda c: len(cat_raw.get(c["id"], [])))
            if cat_raw.get(busiest["id"]):
                insights.append(f"뉴스가 가장 많은 카테고리: {busiest['label']}")

        data["regions"][rid] = {
            "label": r.get("label", rid),
            "flag": r.get("flag", ""),
            "realtime_search": rt,
            "news_keywords": nk,
            "category_news": category_news,
            "insights": insights,
        }

    common = [{"term": k, "regions": sorted(regs)}
              for k, regs in cross.items() if len(regs) >= 2 and len(k) >= 2]
    common.sort(key=lambda x: -len(x["regions"]))
    data["common_topics"] = common[:8]
    return data


# ----------------------------------------------------------- 렌더링
def render_markdown(data: dict, config) -> str:
    out: list[str] = [f"# 📅 {data['date']} {data['slot']} 트렌드 인사이트",
                      f"_생성: {data['generated_at']}_", ""]
    for r in config.enabled_regions:
        rid = r["id"]
        rd = data["regions"].get(rid)
        if not rd:
            continue
        out.append(f"## {rd['flag']} {rd['label']}")
        out.append("")
        if rd["realtime_search"]:
            out.append("**🔥 실시간 급상승 검색**: " + " · ".join(rd["realtime_search"]))
            out.append("")
        if rd["news_keywords"]:
            out.append("**📰 뉴스 키워드 트렌드** _(괄호=다룬 기사 수)_")
            for k in rd["news_keywords"]:
                extra = f" — {k['term_ko']}" if k["term_ko"] else ""
                out.append(f"- **{k['term']}**{extra} ({k['articles']}) · {k['category_label']}")
            out.append("")
        if rd["category_news"]:
            out.append("**🗂 카테고리별 주요 뉴스**")
            for c in config.categories:
                cn = rd["category_news"].get(c["id"])
                if not cn:
                    continue
                extra = f" _( {cn['headline_ko']} )_" if cn["headline_ko"] else ""
                out.append(f"- **{cn['label']}**: {cn['headline']}{extra}")
            out.append("")
        if rd["insights"]:
            out.append("**💡 인사이트**")
            out.extend(f"- {ins}" for ins in rd["insights"])
            out.append("")
        out.append("")

    if data["common_topics"]:
        flags = {r["id"]: r.get("flag", "") for r in config.enabled_regions}
        out.append("## 🌏 종합 인사이트 (국가 공통 화제)")
        for c in data["common_topics"]:
            out.append(f"- **{c['term']}** — " + "".join(flags.get(x, "") for x in c["regions"]) + " 공통")
        out.append("")
    out.append("---")
    out.append("")
    return "\n".join(out)


# ----------------------------------------------------------- 파일 출력
def write_reports(storage, config, md_path: str | Path, json_path: str | Path | None = None) -> str:
    data = build_report_data(storage, config)
    md_path = Path(md_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    section = render_markdown(data, config).rstrip() + "\n\n"
    header_prefix = f"# 📅 {data['date']} {data['slot']}"
    existing = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    if existing:
        parts = re.split(r"(?=^# 📅 )", existing, flags=re.M)
        parts = [p for p in parts if not p.startswith(header_prefix)]
        existing = "".join(parts)
    md_path.write_text(section + existing.lstrip(), encoding="utf-8")

    # 다른 프로젝트용 구조화 JSON(최신 스냅샷)
    if json_path:
        json_path = Path(json_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("리포트 갱신: %s (%s %s)", md_path, data["date"], data["slot"])
    return str(md_path)


# 하위호환 별칭
def append_daily_report(storage, config, path, json_path=None) -> str:
    return write_reports(storage, config, path, json_path)
