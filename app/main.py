"""FastAPI 앱 — REST API + 정적 대시보드 서빙 + 주기 수집 스케줄러.

한 프로세스가 데이터 수집(지역별)·번역·웹 서빙을 모두 담당한다.
실행: `python -m app`  (또는 uvicorn app.main:app)
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from fastapi.responses import PlainTextResponse

from .adapters import build_adapters
from .classify import enrich, matches_view
from .collector import Collector
from .config import DATA_DIR, ROOT_DIR, load_config
from .http_client import PoliteClient
from .report import today_kst, write_reports
from .storage import Storage
from .translate import Translator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("jptrend")

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    http = PoliteClient(
        user_agent=config.http.get("user_agent", "JP-TW-Trend-Monitor/1.1"),
        default_delay=float(config.http.get("default_delay_seconds", 1.5)),
        timeout=float(config.http.get("timeout_seconds", 20)),
        max_retries=int(config.http.get("max_retries", 3)),
        host_delays=config.http.get("host_delays", {}),
    )
    storage = Storage(DATA_DIR / "trends.sqlite")
    adapters = build_adapters(config, http, storage)
    translator = Translator(config.translation, config.http.get("user_agent", "JP-TW-Trend-Monitor/1.1"))
    collector = Collector(adapters, storage, config, translator)

    app.state.config = config
    app.state.http = http
    app.state.storage = storage
    app.state.adapters = adapters
    app.state.collector = collector

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        collector.collect_all, "interval",
        seconds=config.refresh_interval_seconds,
        id="collect_all", max_instances=1, coalesce=True,
    )

    # 일일 인사이트 리포트 (뉴스 전용, md 누적 + json 최신 스냅샷)
    report_cfg = config.raw.get("report", {}) or {}
    report_enabled = bool(report_cfg.get("enabled", True))
    report_path = ROOT_DIR / report_cfg.get("file", "reports/daily.md")
    report_json_path = ROOT_DIR / report_cfg.get("json_file", "reports/daily.json")
    app.state.report_path = report_path
    app.state.report_json_path = report_json_path

    async def _daily_report():
        try:
            await asyncio.to_thread(write_reports, storage, config, report_path, report_json_path)
        except Exception as exc:
            log.warning("일일 리포트 생성 실패: %s", exc)
    app.state.run_daily_report = _daily_report if report_enabled else None

    if report_enabled:
        hours = report_cfg.get("hours_kst", [0, 12])
        hour_expr = ",".join(str(int(h)) for h in hours)
        scheduler.add_job(
            _daily_report, "cron", hour=hour_expr, minute=0,
            timezone="Asia/Seoul", id="daily_report", max_instances=1, coalesce=True,
        )

    scheduler.start()
    app.state.scheduler = scheduler

    if config.run_on_startup:
        async def _startup():
            await collector.collect_all()
            # 오늘 리포트가 없으면 시작 시 1회 생성
            if report_enabled and report_cfg.get("run_on_startup", True):
                need = True
                if report_path.exists():
                    try:
                        need = f"# 📅 {today_kst()}" not in report_path.read_text(encoding="utf-8")
                    except Exception:
                        need = True
                if need:
                    await _daily_report()
        asyncio.create_task(_startup())

    log.info(
        "대시보드 준비 완료 — http://%s:%s (지역=%s, 갱신 %ds)",
        config.server.get("host", "127.0.0.1"),
        config.server.get("port", 8899),
        ",".join(config.enabled_region_ids),
        config.refresh_interval_seconds,
    )
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await http.aclose()


app = FastAPI(title="한국/일본/대만 트렌드 모니터링 대시보드", lifespan=lifespan)


@app.middleware("http")
async def _no_cache(request, call_next):
    """대시보드(정적 자산·인덱스)는 캐시 무효화 → 업데이트 즉시 반영."""
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def _default_region() -> str:
    ids = app.state.config.enabled_region_ids
    return ids[0] if ids else "jp"


# ------------------------------------------------------------------ API
@app.get("/api/meta")
async def api_meta():
    config = app.state.config
    storage: Storage = app.state.storage

    # 소스 메타(지역 중복 제거) — 어떤 소스가 어떤 지역을 서비스하는지
    src_meta: dict[str, dict] = {}
    for a in app.state.adapters:
        m = src_meta.setdefault(a.name, {
            "name": a.name, "display_name": a.display_name,
            "risk": a.risk, "source_type": a.default_source_type, "regions": [],
        })
        if a.region not in m["regions"]:
            m["regions"].append(a.region)

    return {
        "regions": [
            {"id": r["id"], "label": r.get("label", r["id"]), "flag": r.get("flag", "")}
            for r in config.enabled_regions
        ],
        "categories": [
            {"id": c["id"], "label": c.get("label", c["id"]), "label_ja": c.get("label_ja", "")}
            for c in config.categories
        ],
        "sources": list(src_meta.values()),
        "refresh_interval_seconds": config.refresh_interval_seconds,
        "last_updated": await asyncio.to_thread(storage.last_updated),
        "translation_enabled": bool(config.translation.get("enabled", True)),
        "classification": config.classification,
    }


@app.get("/api/sources")
async def api_sources(region: str = Query("", description="지역 필터")):
    storage: Storage = app.state.storage
    reg = region or _default_region()
    health = await asyncio.to_thread(storage.source_health, reg)
    meta = {a.name: (a.display_name, a.risk) for a in app.state.adapters}
    for h in health:
        dn, risk = meta.get(h["source"], (h["source"], "?"))
        h["display_name"] = dn
        h["risk"] = risk
    return {"region": reg, "sources": health}


@app.get("/api/trends")
async def api_trends(
    region: str = Query("", description="지역 id (jp|tw). 빈값=기본 지역"),
    category: str = Query("", description="카테고리 id 필터 (빈값=전체)"),
    view: str = Query("all", description="all | realtime | sustained"),
    source: str = Query("", description="소스 이름 필터"),
    q: str = Query("", description="검색어(원어/한국어 부분일치)"),
    sort: str = Query("rank", description="rank | change | metric | recency | term"),
    order: str = Query("asc", description="asc | desc"),
):
    config = app.state.config
    storage: Storage = app.state.storage
    reg = region or _default_region()

    items = await asyncio.to_thread(storage.get_current_items, reg)
    items = enrich(items, config.classification)
    for it in items:
        it["category_label"] = config.category_label(it.get("category", ""))

    ql = q.strip().lower()
    filtered = []
    for it in items:
        if category and it.get("category") != category:
            continue
        if source and it.get("source") != source:
            continue
        if not matches_view(it, view):
            continue
        if ql:
            hay = (it.get("term", "") + " " + (it.get("term_ko") or "")).lower()
            if ql not in hay:
                continue
        filtered.append(it)

    reverse = order == "desc"
    keymap = {
        "rank": lambda x: (x.get("source", ""), x.get("rank", 999)),
        "change": lambda x: (x.get("rank_change") if x.get("rank_change") is not None else -9999),
        "metric": lambda x: x.get("metric_value", 0.0),
        "recency": lambda x: x.get("last_seen", ""),
        "term": lambda x: x.get("term", ""),
    }
    keyfn = keymap.get(sort, keymap["rank"])
    if sort in ("change", "metric", "recency") and order == "asc":
        reverse = True
    filtered.sort(key=keyfn, reverse=reverse)

    return {
        "region": reg,
        "count": len(filtered),
        "last_updated": await asyncio.to_thread(storage.last_updated, reg),
        "items": filtered,
    }


@app.post("/api/refresh")
async def api_refresh():
    collector: Collector = app.state.collector
    asyncio.create_task(collector.collect_all())
    return JSONResponse({"status": "started"})


@app.get("/api/report", response_class=PlainTextResponse)
async def api_report():
    """누적 일일 리포트(마크다운) 원문."""
    path = app.state.report_path
    if not path.exists():
        return PlainTextResponse(
            "아직 리포트가 없습니다. POST /api/report/run 으로 생성하세요.",
            status_code=404)
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.get("/api/report.json")
async def api_report_json():
    """다른 프로젝트용 구조화 리포트(최신 스냅샷)."""
    path = app.state.report_json_path
    if not path.exists():
        return JSONResponse({"error": "no report yet"}, status_code=404)
    import json as _json
    return JSONResponse(_json.loads(path.read_text(encoding="utf-8")))


@app.post("/api/report/run")
async def api_report_run():
    """지금 즉시 오늘 리포트 생성/갱신."""
    runner = getattr(app.state, "run_daily_report", None)
    if not runner:
        return JSONResponse({"status": "disabled"})
    await runner()
    return JSONResponse({"status": "generated", "file": str(app.state.report_path)})


# ------------------------------------------------------------------ static
@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
