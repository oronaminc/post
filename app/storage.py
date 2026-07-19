"""SQLite 저장소.

과거 스냅샷 이력을 보관해서
  - 순위 변동(rank_change)
  - 지속 관심도(여러 수집에 걸쳐 반복 등장)
를 계산할 수 있게 한다. 지역(region)별로 분리 저장하며,
트렌드 워드의 한국어 번역은 translations 캐시에 1회만 저장한다.

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
    region       TEXT NOT NULL DEFAULT 'jp',
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL,          -- ok | empty | error
    item_count   INTEGER DEFAULT 0,
    error        TEXT
);
CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL,
    region       TEXT NOT NULL DEFAULT 'jp',
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
CREATE TABLE IF NOT EXISTS translations (
    term          TEXT PRIMARY KEY,
    term_ko       TEXT,
    translated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_term    ON items(term, source);
CREATE INDEX IF NOT EXISTS idx_items_run     ON items(run_id);
CREATE INDEX IF NOT EXISTS idx_items_region  ON items(region);
CREATE INDEX IF NOT EXISTS idx_items_collect ON items(collected_at);
CREATE INDEX IF NOT EXISTS idx_runs_source   ON runs(source, region, id);
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
    def start_run(self, source: str, region: str = "jp") -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (source, region, started_at, status) VALUES (?, ?, ?, 'running')",
                (source, region, _now_iso()),
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
                run_id, it.region, collected_at, it.source, it.source_type, it.category,
                it.rank, it.term, it.metric_label, it.metric_value, it.url,
                it.rank_change, json.dumps(it.extra, ensure_ascii=False),
            ))
        if not rows:
            return 0
        with self._lock, self._connect() as conn:
            conn.executemany(
                """INSERT INTO items
                   (run_id, region, collected_at, source, source_type, category, rank, term,
                    metric_label, metric_value, url, rank_change, extra)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
        return len(rows)

    # --------------------------------------------------------------- queries
    def _latest_ok_run_ids(self, conn: sqlite3.Connection, region: str) -> dict[str, int]:
        """지역 내 소스별 가장 최근 성공 수집(run) id."""
        rows = conn.execute(
            """SELECT source, MAX(id) AS rid FROM runs
               WHERE status IN ('ok','empty') AND region=? GROUP BY source""",
            (region,),
        ).fetchall()
        return {r["source"]: r["rid"] for r in rows}

    def _prev_ok_run_id(self, conn: sqlite3.Connection, source: str, region: str, before_id: int) -> int | None:
        row = conn.execute(
            """SELECT id FROM runs WHERE source=? AND region=? AND status IN ('ok','empty') AND id<?
               ORDER BY id DESC LIMIT 1""",
            (source, region, before_id),
        ).fetchone()
        return row["id"] if row else None

    def get_current_items(self, region: str = "jp") -> list[dict[str, Any]]:
        """지역의 각 소스 최신 수집 결과 + 변동/지속/한국어번역을 붙여 반환."""
        with self._lock, self._connect() as conn:
            latest = self._latest_ok_run_ids(conn, region)
            if not latest:
                return []

            prev_rank: dict[str, dict[str, int]] = {}
            for source, rid in latest.items():
                prid = self._prev_ok_run_id(conn, source, region, rid)
                if prid is None:
                    continue
                prows = conn.execute(
                    "SELECT term, rank FROM items WHERE run_id=?", (prid,)
                ).fetchall()
                prev_rank[source] = {r["term"]: r["rank"] for r in prows}

            # 지속성: 이 지역에서 term별 등장 수집 횟수 & 최초/최근 시각
            persist: dict[str, tuple] = {}
            for r in conn.execute(
                """SELECT term,
                          COUNT(DISTINCT run_id) AS occ,
                          MIN(collected_at) AS first_seen,
                          MAX(collected_at) AS last_seen
                   FROM items WHERE region=? GROUP BY term""",
                (region,),
            ).fetchall():
                persist[r["term"]] = (r["occ"], r["first_seen"], r["last_seen"])

            run_ids = list(latest.values())
            placeholders = ",".join("?" * len(run_ids))
            rows = conn.execute(
                f"""SELECT i.*, t.term_ko AS term_ko
                    FROM items i LEFT JOIN translations t ON t.term = i.term
                    WHERE i.run_id IN ({placeholders}) ORDER BY i.source, i.rank""",
                run_ids,
            ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            d["extra"] = json.loads(d.get("extra") or "{}")
            rc = d.get("rank_change")
            if rc is None:
                prev = prev_rank.get(d["source"], {}).get(d["term"])
                if prev is not None:
                    rc = prev - d["rank"]
            d["rank_change"] = rc
            occ, first_seen, last_seen = persist.get(d["term"], (1, d["collected_at"], d["collected_at"]))
            d["occurrences"] = occ
            d["first_seen"] = first_seen
            d["last_seen"] = last_seen
            results.append(d)
        return results

    def source_health(self, region: str | None = None) -> list[dict[str, Any]]:
        """소스별(지역별) 최신 수집 상태."""
        with self._lock, self._connect() as conn:
            if region:
                rows = conn.execute(
                    """SELECT r.* FROM runs r
                       JOIN (SELECT source, MAX(id) AS rid FROM runs WHERE region=? GROUP BY source) m
                         ON r.id = m.rid
                       ORDER BY r.source""",
                    (region,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT r.* FROM runs r
                       JOIN (SELECT source, region, MAX(id) AS rid FROM runs GROUP BY source, region) m
                         ON r.id = m.rid
                       ORDER BY r.region, r.source"""
                ).fetchall()
        return [dict(r) for r in rows]

    def last_updated(self, region: str | None = None) -> str | None:
        with self._lock, self._connect() as conn:
            if region:
                row = conn.execute(
                    "SELECT MAX(collected_at) AS ts FROM items WHERE region=?", (region,)
                ).fetchone()
            else:
                row = conn.execute("SELECT MAX(collected_at) AS ts FROM items").fetchone()
        return row["ts"] if row else None

    # ---------------------------------------------------------- translations
    def get_cached_translations(self, terms: Iterable[str]) -> dict[str, str]:
        terms = list({t for t in terms if t})
        if not terms:
            return {}
        out: dict[str, str] = {}
        with self._lock, self._connect() as conn:
            for i in range(0, len(terms), 400):
                chunk = terms[i:i + 400]
                ph = ",".join("?" * len(chunk))
                for r in conn.execute(
                    f"SELECT term, term_ko FROM translations WHERE term IN ({ph})", chunk
                ).fetchall():
                    if r["term_ko"]:
                        out[r["term"]] = r["term_ko"]
        return out

    def save_translations(self, mapping: dict[str, str]) -> int:
        rows = [(term, ko, _now_iso()) for term, ko in mapping.items() if term and ko]
        if not rows:
            return 0
        with self._lock, self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO translations (term, term_ko, translated_at) VALUES (?,?,?)",
                rows,
            )
        return len(rows)

    # ----------------------------------------------------------------- prune
    def prune(self, retention_days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM items WHERE collected_at < ?", (cutoff,))
            deleted = cur.rowcount
            conn.execute(
                "DELETE FROM runs WHERE finished_at IS NOT NULL AND finished_at < ?",
                (cutoff,),
            )
        return deleted
