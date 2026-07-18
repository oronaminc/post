"""config.yaml + .env 로딩.

설정은 얇은 래퍼(AppConfig)로 감싸서 각 모듈이 필요한 부분만 꺼내 쓴다.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# 프로젝트 루트 = 이 파일의 부모의 부모 (app/config.py -> app -> root)
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.yaml"
DATA_DIR = ROOT_DIR / "data"


class AppConfig:
    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.categories: list[dict] = raw.get("categories", []) or []
        self.sources: dict[str, dict] = raw.get("sources", {}) or {}
        self.collection: dict = raw.get("collection", {}) or {}
        self.classification: dict = raw.get("classification", {}) or {}
        self.http: dict = raw.get("http", {}) or {}
        self.server: dict = raw.get("server", {}) or {}

    # --- 편의 접근자 ---
    @property
    def category_ids(self) -> list[str]:
        return [c["id"] for c in self.categories]

    def category_label(self, category_id: str) -> str:
        for c in self.categories:
            if c["id"] == category_id:
                return c.get("label", category_id)
        return category_id

    def category_by_id(self, category_id: str) -> dict | None:
        for c in self.categories:
            if c["id"] == category_id:
                return c
        return None

    @property
    def refresh_interval_seconds(self) -> int:
        return int(self.collection.get("refresh_interval_seconds", 900))

    @property
    def per_source_timeout_seconds(self) -> float:
        return float(self.collection.get("per_source_timeout_seconds", 30))

    @property
    def retention_days(self) -> int:
        return int(self.collection.get("retention_days", 14))

    @property
    def run_on_startup(self) -> bool:
        return bool(self.collection.get("run_on_startup", True))

    def env(self, key: str, default: str | None = None) -> str | None:
        return os.getenv(key, default)


def load_config(path: str | os.PathLike | None = None) -> AppConfig:
    """.env 를 먼저 로드하고 config.yaml 을 읽어 AppConfig 반환."""
    load_dotenv(ROOT_DIR / ".env")
    cfg_path = Path(path or os.getenv("APP_CONFIG") or DEFAULT_CONFIG_PATH)
    if not cfg_path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    DATA_DIR.mkdir(exist_ok=True)
    return AppConfig(raw)
