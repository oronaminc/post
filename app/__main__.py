"""`python -m app` 진입점 — config 의 host/port 로 uvicorn 실행."""
from __future__ import annotations

import uvicorn

from .config import load_config


def main() -> None:
    config = load_config()
    host = config.server.get("host", "127.0.0.1")
    port = int(config.server.get("port", 8000))
    # reload 없이 단일 프로세스로 실행 (스케줄러/인메모리 상태 유지)
    uvicorn.run("app.main:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
