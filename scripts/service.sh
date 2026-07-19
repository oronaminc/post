#!/usr/bin/env bash
# 일본/대만 트렌드 모니터 — 로컬 상시 실행 관리 스크립트
#
#   ./scripts/service.sh start     # 백그라운드로 실행(터미널 닫아도 유지)
#   ./scripts/service.sh stop      # 중지
#   ./scripts/service.sh restart   # 재시작
#   ./scripts/service.sh status    # 상태 확인
#   ./scripts/service.sh logs      # 실행 로그 보기
#   ./scripts/service.sh install-launchd   # (선택) 재부팅에도 자동 시작 — 아래 주의 참고
#
# ⚠️ 이 저장소는 ~/Desktop 아래에 있습니다. macOS는 Desktop/Documents/Downloads를
#    프라이버시(TCC)로 보호하므로, 백그라운드 launchd 에이전트는 Full Disk Access가
#    없으면 이 폴더의 파일을 읽지 못합니다(재부팅 자동시작 불가).
#    → 평소에는 'start'(터미널 컨텍스트, 권한 문제 없음)를 쓰면 됩니다.
#    → 재부팅 자동시작까지 원하면 install-launchd 안내를 따르세요.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/.venv/bin/python"
LOG="$REPO/data/service.log"
PORT="$(grep -E '^[[:space:]]*port:' "$REPO/config.yaml" | head -1 | grep -oE '[0-9]+' || echo 8899)"
LABEL="com.oronaminc.jptrend"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

port_pid() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true; }

stop_server() {
  local pid; pid="$(port_pid)"
  if [ -n "$pid" ]; then echo "  · :$PORT 프로세스 종료(PID $pid)"; kill $pid 2>/dev/null || true; sleep 1; fi
}

ensure_env() {
  if [ ! -x "$PY" ]; then
    echo "▶ .venv 생성 + 의존성 설치…"
    python3 -m venv "$REPO/.venv"
    "$REPO/.venv/bin/pip" install -q --upgrade pip
    "$REPO/.venv/bin/pip" install -q -r "$REPO/requirements.txt"
  fi
  [ -f "$REPO/.env" ] || cp "$REPO/.env.example" "$REPO/.env" 2>/dev/null || true
  mkdir -p "$REPO/data"
}

do_status() {
  local pid; pid="$(port_pid)"
  if [ -n "$pid" ]; then echo "실행 중 ✅  (PID $pid)"; else echo "중지됨 ❌"; fi
  local code; code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://127.0.0.1:$PORT/api/meta" 2>/dev/null || true)"
  echo "http://127.0.0.1:$PORT  → HTTP ${code:-000}"
}

case "${1:-}" in
  start)
    ensure_env
    if [ -n "$(port_pid)" ]; then echo "이미 실행 중 (PID $(port_pid))"; do_status; exit 0; fi
    cd "$REPO"
    # nohup: 터미널을 닫아도(SIGHUP) 계속 실행. 로그는 service.log 로.
    nohup "$PY" -m app >> "$LOG" 2>&1 &
    disown 2>/dev/null || true
    echo "▶ 백그라운드 실행 시작 (로그: $LOG)"
    sleep 6
    do_status
    ;;
  stop)
    stop_server
    echo "✔ 중지"
    ;;
  restart)
    stop_server; sleep 1; "$0" start
    ;;
  status)
    do_status
    ;;
  logs)
    tail -n 40 -f "$LOG"
    ;;
  install-launchd)
    ensure_env
    cat <<NOTE
[재부팅 자동시작(launchd) 설정]
이 저장소가 ~/Desktop 아래라 macOS TCC 때문에 launchd 에이전트에는
Full Disk Access가 필요합니다. 아래 순서로 하세요:

  1) 시스템 설정 → 개인정보 보호 및 보안 → '전체 디스크 접근 권한(Full Disk Access)'
     에서 '+' 를 눌러 다음 파이썬 실행파일을 추가하고 켜기:
        $PY
     (심볼릭 링크면 실제 python3 경로도 함께 추가하세요:
        $(readlink -f "$PY" 2>/dev/null || echo "$PY") )
  2) 그런 다음 이 스크립트가 만든 plist 를 등록:
        launchctl bootstrap gui/\$(id -u) "$PLIST"

plist 를 생성합니다…
NOTE
    stop_server
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>-m</string><string>app</string></array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PL
    echo "✔ plist 생성됨: $PLIST"
    echo "   위 1)번(Full Disk Access) 후 2)번 명령으로 등록하세요."
    echo "   해제:  launchctl bootout gui/\$(id -u)/$LABEL && rm '$PLIST'"
    ;;
  *)
    echo "사용법: $0 {start|stop|restart|status|logs|install-launchd}"
    exit 1
    ;;
esac
