# CLAUDE.md

한국·일본·대만 트렌드 모니터링 대시보드. 로컬 실행 웹앱(수집·번역·서빙·일일리포트 한 프로세스).
Python 3.11+ / FastAPI + APScheduler + SQLite / 빌드 없는 vanilla JS 프론트.

## 실행 · 개발

```bash
./scripts/service.sh start|stop|restart|status|logs   # 백그라운드 상시 실행(권장)
python -m app                                          # 포그라운드 실행
./run.sh                                               # venv+설치+실행 한 방
```
- 대시보드: **http://127.0.0.1:8899** (포트는 `config.yaml` `server.port`)
- 서버 재시작해야 코드/설정 변경이 반영됨(`no-reload`). 서버 종료는 **포트→PID로만** (아래 주의).
- 로그: `data/service.log` · DB: `data/trends.sqlite` · 리포트: `reports/`(gitignore)

## 아키텍처

- **어댑터 패턴**: 각 소스는 `app/adapters/base.py`의 `BaseAdapter` 상속, `fetch()→list[RawTrendItem]`만 구현.
  어댑터는 **(소스 × 지역)** 조합으로 생성(`google_news_rss@kr` 등). 컬렉터가 타임아웃+예외 격리로 실행(한 소스 죽어도 나머지 정상).
- **파생 소스**(`derived=True`): 1차 소스 수집 후 **2단계**로 실행되어 `self.storage`로 다른 소스 결과를 재료로 씀.
  - `news_keywords`(app/keywords.py): 뉴스 헤드라인에서 키워드 추출→**문서빈도(기사 수)** 랭킹. 순수 파이썬(형태소분석기 X). 불용어/seed제외/조각병합은 `app/keywords.py`에서 튜닝.
  - `naver_datalab`: 급상승 워드를 네이버 데이터랩에 넣어 네이버 검색관심도로 랭킹.
- **저장소**(SQLite): 지역별 스냅샷 이력(변동/지속 계산) + 번역 캐시(`translations`).
- **번역**(app/translate.py): 무료 Google gtx 엔드포인트, 미번역 워드만, 캐시. 한국어/영문(AI·EU) 워드는 스킵.
- **일일 리포트**(app/report.py): KST 00·12시 + 시작 시 오늘분 없으면 1회. `reports/daily.md`(누적) + `reports/daily.json`(구조화 스냅샷).

## 확장

- **새 소스**: `app/adapters/`에 어댑터 → `adapters/__init__.py` `ADAPTER_REGISTRY` 등록 → `config.yaml` `sources`에 `regions` 포함 설정.
- **새 지역**: `config.yaml` `regions` 추가 + 각 소스 `geo`/`locale`·카테고리 `news_queries`/`keywords`에 지역 키 추가.
- **새 카테고리**: `config.yaml` `categories`에 지역별 `news_queries`/`keywords` 포함해 추가.

## 주의 (gotchas)

- ⚠️ **프로세스 종료는 포트→PID로만** (`lsof -tiTCP:8899 -sTCP:LISTEN | xargs kill`). `pkill -f "python -m app"`는 사용자의 다른 `app.*` 프로세스까지 죽임 — 금지.
- **API 키(선택)**: 네이버는 **NCP API Hub**(ncloud) 키 `NAVER_CLIENT_ID/SECRET`(헤더 `X-NCP-APIGW-*`). YouTube는 `YOUTUBE_API_KEY`(기본 비활성). 없으면 해당 소스만 graceful.
- **리스크 소스**: `yahoo_realtime`(약관), 스크래핑들은 저빈도·식별 UA. 끄려면 config `enabled: false`.
- macOS TCC: 저장소가 `~/Desktop` 아래라 launchd 자동시작은 Full Disk Access 필요(그래서 기본은 nohup).
- **변경 후 항상 GitHub(origin)에 push** (사용자 상시 요청). SSH 리모트 사용.
