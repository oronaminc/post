#!/usr/bin/env bash
# 일본 트렌드 모니터 — 한 방 실행 스크립트
# 처음이면 가상환경 생성 + 의존성 설치 후 서버를 띄운다.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if [ ! -d ".venv" ]; then
  echo "▶ 가상환경(.venv) 생성 중…"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "▶ 의존성 설치 중…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "ℹ  .env 를 생성했습니다. YouTube 를 쓰려면 YOUTUBE_API_KEY 를 채우세요."
fi

echo "▶ 대시보드 실행 → http://127.0.0.1:8899  (Ctrl+C 로 종료)"
exec python -m app
