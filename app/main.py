"""FastAPI 앱 — REST API + 정적 대시보드 서빙 + 주기 수집 스케줄러.

한 프로세스가 데이터 수집과 웹 서빙을 모두 담당한다.
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

from .adapters import build_adapters
from .classify import enrich, matches_view
from .collector import Collector
from .config import DATA_DIR, load_config
from .http_client import PoliteClient
from .storage import Storage

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
        user_agent=config.http.get("user_agent", "JP-Trend-Monitor/1.0"),
        default_delay=float(config.http.get("default_delay_seconds", 1.5)),
        timeout=float(config.http.get("timeout_seconds", 20)),
        max_retries=int(config.http.get("max_retries", 3)),
        host_delays=config.http.get("host_delays", {}),
    )
    storage = Storage(DATA_DIR / "trends.sqlite")
    adapters = build_adapters(config, http)
    collector = Collector(adapters, storage, config)

    app.state.config = config
    app.state.http = http
    app.state.storage = storage
    app.state.adapters = adapters
    app.state.collector = collector

    # 주기 수집 스케줄러
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        collector.collect_all,
        "interval",
        seconds=config.refresh_interval_seconds,
        id="collect_all",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler

    if config.run_on_startup:
        # 첫 데이터를 백그라운드로 즉시 수집 (서버 기동을 막지 않음)
        asyncio.create_task(collector.collect_all())

    log.info(
        "대시보드 준비 완료 — http://%s:%s (갱신 주기 %ds)",
        config.server.get("host", "127.0.0.1"),
        config.server.get("port", 8000),
        config.refresh_interval_seconds,
    )
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await http.aclose()


app = FastAPI(title="일본 트렌드 모니터링 대시보드", lifespan=lifespan)


# ------------------------------------------------------------------ API
@app.get("/api/meta")
async def api_meta():
    config = app.state.config
    storage: Storage = app.state.storage
    return {
        "categories": [
            {"id": c["id"], "label": c.get("label", c["id"]),
             "label_ja": c.get("label_ja", "")}
            for c in config.categories
        ],
        "sources": [
            {"name": a.name, "display_name": a.display_name, "risk": a.risk,
             "source_type": a.default_source_type}
            for a in app.state.adapters
        ],
        "refresh_interval_seconds": config.refresh_interval_seconds,
        "last_updated": await asyncio.to_thread(storage.last_updated),
        "classification": config.classification,
    }


@app.get("/api/sources")
async def api_sources():
    storage: Storage = app.state.storage
    health = await asyncio.to_thread(storage.source_health)
    # 표시 이름/리스크 매핑 덧붙이기
    meta = {a.name: (a.display_name, a.risk) for a in app.state.adapters}
    for h in health:
        dn, risk = meta.get(h["source"], (h["source"], "?"))
        h["display_name"] = dn
        h["risk"] = risk
    return {"sources": health}


@app.get("/api/trends")
async def api_trends(
    category: str = Query("", description="카테고리 id 필터 (빈값=전체)"),
    view: str = Query("all", description="all | realtime | sustained"),
    source: str = Query("", description="소스 이름 필터"),
    q: str = Query("", description="검색어(부분일치)"),
    sort: str = Query("rank", description="rank | change | metric | recency | term"),
    order: str = Query("asc", description="asc | desc"),
):
    config = app.state.config
    storage: Storage = app.state.storage

    items = await asyncio.to_thread(storage.get_current_items)
    items = enrich(items, config.classification)

    # 카테고리 라벨 부착
    for it in items:
        it["category_label"] = config.category_label(it.get("category", ""))

    # 필터
    ql = q.strip().lower()
    filtered = []
    for it in items:
        if category and it.get("category") != category:
            continue
        if source and it.get("source") != source:
            continue
        if not matches_view(it, view):
            continue
        if ql and ql not in (it.get("term", "").lower()):
            continue
        filtered.append(it)

    # 정렬
    reverse = order == "desc"
    keymap = {
        "rank": lambda x: (x.get("source", ""), x.get("rank", 999)),
        "change": lambda x: (x.get("rank_change") if x.get("rank_change") is not None else -9999),
        "metric": lambda x: x.get("metric_value", 0.0),
        "recency": lambda x: x.get("last_seen", ""),
        "term": lambda x: x.get("term", ""),
    }
    keyfn = keymap.get(sort, keymap["rank"])
    # change/metric/recency 는 큰 값이 먼저 오는 게 자연스러워 기본 내림차순
    if sort in ("change", "metric", "recency") and order == "asc":
        reverse = True
    filtered.sort(key=keyfn, reverse=reverse)

    return {"count": len(filtered), "items": filtered}


@app.post("/api/refresh")
async def api_refresh():
    """즉시 수집 트리거 (백그라운드)."""
    collector: Collector = app.state.collector
    asyncio.create_task(collector.collect_all())
    return JSONResponse({"status": "started"})


# ------------------------------------------------------------------ static
@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
