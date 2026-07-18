"""SQLite 저장소.

과거 스냅샷 이력을 보관해서
  - 순위 변동(rank_change)
  - 지속 관심도(여러 수집에 걸쳐 반복 등장)
를 계산할 수 있게 한다. 로컬 단일 파일이라 설치가 필요 없다.

메서드는 모두 동기(sync)다. 비동기 컬렉터/핸들러에서는
`asyncio.to_thread` 로 감싸 이벤트 루프를 막지 않는다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import RawTrendItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL,          -- ok | empty | error
    item_count   INTEGER DEFAULT 0,
    error        TEXT
);
CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL,
    collected_at TEXT NOT NULL,
    source       TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    category     TEXT NOT NULL,
    rank         INTEGER NOT NULL,
    term         TEXT NOT NULL,
    metric_label TEXT,
    metric_value REAL,
    url          TEXT,
    rank_change  INTEGER,
    extra        TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
CREATE INDEX IF NOT EXISTS idx_items_term    ON items(term, source);
CREATE INDEX IF NOT EXISTS idx_items_run     ON items(run_id);
CREATE INDEX IF NOT EXISTS idx_items_collect ON items(collected_at);
CREATE INDEX IF NOT EXISTS idx_runs_source   ON runs(source, id);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ runs
    def start_run(self, source: str) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (source, started_at, status) VALUES (?, ?, 'running')",
                (source, _now_iso()),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, item_count: int, error: str | None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE runs SET finished_at=?, status=?, item_count=?, error=? WHERE id=?",
                (_now_iso(), status, item_count, error, run_id),
            )

    def save_items(self, run_id: int, collected_at: str, items: Iterable[RawTrendItem]) -> int:
        rows = []
        for it in items:
            it.clean()
            if not it.term:
                continue
            rows.append((
                run_id, collected_at, it.source, it.source_type, it.category,
                it.rank, it.term, it.metric_label, it.metric_value, it.url,
                it.rank_change, json.dumps(it.extra, ensure_ascii=False),
            ))
        if not rows:
            return 0
        with self._lock, self._connect() as conn:
            conn.executemany(
                """INSERT INTO items
                   (run_id, collected_at, source, source_type, category, rank, term,
                    metric_label, metric_value, url, rank_change, extra)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
        return len(rows)

    # --------------------------------------------------------------- queries
    def _latest_ok_run_ids(self, conn: sqlite3.Connection) -> dict[str, int]:
        """소스별 가장 최근 성공 수집(run) id."""
        rows = conn.execute(
            """SELECT source, MAX(id) AS rid FROM runs
               WHERE status IN ('ok','empty') GROUP BY source"""
        ).fetchall()
        return {r["source"]: r["rid"] for r in rows}

    def _prev_ok_run_id(self, conn: sqlite3.Connection, source: str, before_id: int) -> int | None:
        row = conn.execute(
            """SELECT id FROM runs WHERE source=? AND status IN ('ok','empty') AND id<?
               ORDER BY id DESC LIMIT 1""",
            (source, before_id),
        ).fetchone()
        return row["id"] if row else None

    def get_current_items(self) -> list[dict[str, Any]]:
        """각 소스의 최신 수집 결과 + 변동/지속 지표를 계산해 반환."""
        with self._lock, self._connect() as conn:
            latest = self._latest_ok_run_ids(conn)
            if not latest:
                return []

            # 이전 run의 (term -> rank) 매핑: 소스가 rank_change를 안 줄 때 계산용
            prev_rank: dict[str, dict[str, int]] = {}
            for source, rid in latest.items():
                prid = self._prev_ok_run_id(conn, source, rid)
                if prid is None:
                    continue
                prows = conn.execute(
                    "SELECT term, rank FROM items WHERE run_id=?", (prid,)
                ).fetchall()
                prev_rank[source] = {r["term"]: r["rank"] for r in prows}

            # 지속성 지표: term별 등장 수집 횟수 & 최초/최근 시각 (보관기간 내 전체)
            persist = {}
            for r in conn.execute(
                """SELECT term,
                          COUNT(DISTINCT run_id) AS occ,
                          MIN(collected_at) AS first_seen,
                          MAX(collected_at) AS last_seen
                   FROM items GROUP BY term"""
            ).fetchall():
                persist[r["term"]] = (r["occ"], r["first_seen"], r["last_seen"])

            run_ids = list(latest.values())
            placeholders = ",".join("?" * len(run_ids))
            rows = conn.execute(
                f"SELECT * FROM items WHERE run_id IN ({placeholders}) ORDER BY source, rank",
                run_ids,
            ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            d["extra"] = json.loads(d.get("extra") or "{}")
            # rank_change: 소스 제공값 우선, 없으면 이전 run과 비교
            rc = d.get("rank_change")
            if rc is None:
                prev = prev_rank.get(d["source"], {}).get(d["term"])
                if prev is not None:
                    rc = prev - d["rank"]  # +면 순위 상승
            d["rank_change"] = rc
            occ, first_seen, last_seen = persist.get(d["term"], (1, d["collected_at"], d["collected_at"]))
            d["occurrences"] = occ
            d["first_seen"] = first_seen
            d["last_seen"] = last_seen
            results.append(d)
        return results

    def source_health(self) -> list[dict[str, Any]]:
        """소스별 최신 수집 상태(대시보드 헬스 표시용)."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """SELECT r.* FROM runs r
                   JOIN (SELECT source, MAX(id) AS rid FROM runs GROUP BY source) m
                     ON r.id = m.rid
                   ORDER BY r.source"""
            ).fetchall()
        return [dict(r) for r in rows]

    def last_updated(self) -> str | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT MAX(collected_at) AS ts FROM items").fetchone()
        return row["ts"] if row else None

    def prune(self, retention_days: int) -> int:
        """보관기간을 넘긴 오래된 이력 삭제."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM items WHERE collected_at < ?", (cutoff,))
            deleted = cur.rowcount
            conn.execute(
                "DELETE FROM runs WHERE finished_at IS NOT NULL AND finished_at < ?",
                (cutoff,),
            )
        return deleted
