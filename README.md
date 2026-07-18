# 🇯🇵 일본 트렌드 모니터링 대시보드

일본에서 **카테고리별로 사람들이 무엇에 관심을 갖는지** 한눈에 파악하는 로컬 웹 대시보드입니다.
**실시간 급상승 트렌드**와 **지속 관심도**를 구분해서 보여주는 것이 핵심입니다.

카테고리: 보조금 · 연예 · 정치 · 쇼핑 · 트렌드 · 경제 · 시사 (설정 파일에서 추가/삭제 가능)

---

## 빠른 실행

### 방법 A — 스크립트 한 방 (권장)
```bash
./run.sh
```
가상환경 생성 → 의존성 설치 → `.env` 생성 → 서버 실행까지 자동으로 처리합니다.
브라우저에서 **http://127.0.0.1:8899** 접속. (포트는 `config.yaml` 의 `server.port` 에서 변경)

### 방법 B — 수동 (2개 명령)
```bash
pip install -r requirements.txt
python -m app
```

### 방법 C — Docker
```bash
docker build -t jp-trend .
docker run -p 8899:8000 --env-file .env jp-trend   # → http://127.0.0.1:8899
# 컨테이너 내부는 8000, Dockerfile CMD 가 host 0.0.0.0 으로 바인딩합니다.
```

> **YouTube 를 쓰려면**: `.env.example` 을 `.env` 로 복사하고 `YOUTUBE_API_KEY` 를 채우세요
> (무료, [Google Cloud Console](https://console.cloud.google.com/) → *YouTube Data API v3* 사용 설정 → API 키).
> 키가 없으면 YouTube 소스만 자동으로 건너뜁니다. 나머지는 그대로 동작합니다.

첫 실행 시 백그라운드로 즉시 1회 수집하며, 이후 `config.yaml` 의 `refresh_interval_seconds`(기본 15분)마다 자동 갱신합니다.

---

## 화면 기능

- **카테고리 탭**: 전체 + 카테고리별 필터
- **뷰 토글**: `전체` / `🔥 실시간 급상승` / `📈 지속 관심도`
- **각 워드 표시**: 순위 · 변동(▲▼/NEW) · 출처 배지 · 카테고리 · 지표(검색량/tweet/조회수/인기도)
- **검색 · 정렬**(순위/변동/지표/최신/이름) · **소스 필터**
- **소스 상태(헬스) 스트립**: 소스별 성공/빈결과/오류를 색으로 표시(⚠️는 리스크 소스). 한 소스가 죽어도 나머지는 정상 동작
- **자동 갱신** + **지금 갱신** 버튼(서버에 즉시 수집 요청)

---

## 스택 선택 이유

| 레이어 | 선택 | 이유 |
|---|---|---|
| 백엔드 | **Python 3.11+ / FastAPI + Uvicorn** | 트렌드 수집용 라이브러리(pytrends·feedparser·BeautifulSoup·httpx)가 대부분 파이썬. **수집과 웹 서빙을 한 언어·한 프로세스**로 처리해 실행이 단순 |
| 스케줄러 | **APScheduler** (인프로세스) | 외부 브로커 없이 주기 수집. 갱신 주기를 config로 조절 |
| 저장소 | **SQLite** (표준 라이브러리) | 설치 0, 파일 1개. **순위 변동·지속 관심도 계산에 과거 스냅샷 이력이 필수**라 반드시 필요 |
| 프론트 | **빌드 없는 단일 SPA** (vanilla JS + CSS) | npm/webpack 빌드 단계가 없어 "명령 한두 개"로 실행. 탭/검색/정렬/자동갱신을 JSON API 위에서 처리 |
| 설정 | **config.yaml** | 카테고리·소스 on/off·주기·키워드·rate limit을 코드 수정 없이 변경 |

---

## 아키텍처

```
                    ┌────────────────────── FastAPI (app/main.py) ──────────────────────┐
브라우저  ◀── HTTP ──▶│  /            정적 대시보드 (app/static/*)                          │
                    │  /api/trends  현재 트렌드(+변동/지속 계산)                          │
                    │  /api/sources 소스 헬스                                             │
                    │  /api/meta    카테고리/소스/주기                                    │
                    │  /api/refresh 즉시 수집 트리거                                      │
                    └───────────▲───────────────────────────────────────────▲───────────┘
                                │ 읽기                                        │ 주기 실행
                       ┌────────┴────────┐                          ┌────────┴─────────┐
                       │ Storage(SQLite) │◀── 적재 ──── Collector ──│  APScheduler     │
                       └─────────────────┘   (격리 실행)            └──────────────────┘
                                                   │
                          ┌──────────────┬─────────┼──────────┬──────────────┐
                       Adapters (app/adapters/*)  각 소스를 어댑터로 분리
                       Google트렌드RSS · Google뉴스RSS · NHK RSS · YouTube API
                       · 트렌드캘린더(스크랩) · pytrends인기도 · Yahoo리얼타임(스크랩)
```

### 어댑터 패턴 (소스 추가/교체가 쉬움)
모든 소스는 `app/adapters/base.py` 의 `BaseAdapter` 를 상속하고 `fetch()` → `list[RawTrendItem]` 만 구현합니다.
새 소스 추가는 3단계:
1. `app/adapters/` 에 어댑터 클래스 작성 (`fetch()` 구현)
2. `app/adapters/__init__.py` 의 `ADAPTER_REGISTRY` 에 등록
3. `config.yaml` 의 `sources` 에 설정 블록 추가

컬렉터는 각 어댑터를 **타임아웃 + 예외 격리**로 실행하므로, 한 소스가 실패해도 나머지는 정상 수집됩니다(결과는 헬스에 `error`로 표시).

### "실시간 급상승" vs "지속 관심도" 판정
- 1차 축: 각 소스가 선언한 `source_type`(트렌딩 피드=급상승, 뉴스/인기도=지속)
- 이력 보강(`app/classify.py`):
  - **급상승(rising)**: realtime 소스이면서 새로 진입(이력상 첫 등장)했거나 순위가 상승
  - **지속(sustained)**: 여러 수집에 걸쳐(`persist_min_occurrences`회 이상) 오래(`persist_min_hours`시간 이상) 반복 등장
  - 이 임계값은 `config.yaml` 의 `classification` 에서 조절

---

## 데이터 소스별 수집 방식 & 법적 주의점

> ⚖️ **원칙**: 각 사이트의 **이용약관과 robots.txt를 존중**하고, 공개된 랭킹/헤드라인만 읽으며,
> **개인정보·로그인 필요 데이터는 다루지 않습니다.** 스크래핑 소스는 식별 가능한 User-Agent와
> 사이트별 요청 간격(`http.host_delays`)으로 **저빈도** 접근합니다. 아래 리스크 등급을 반드시 확인하세요.

| 소스 | 수집 방식 | 왜 이 방식인가 | robots.txt(실측) | 리스크 |
|---|---|---|:---:|:---:|
| **Google 트렌드(일간)** | 공식 공개 RSS `trends.google.com/trending/rss?geo=JP` | 공식 API가 없지만 RSS는 공개 제공. pytrends 스크래핑보다 안정적 | ✅ 허용 (`/explore?`만 Disallow) | 🟢 낮음 |
| **Google 뉴스** | RSS `news.google.com/rss/search?q=…` (카테고리 키워드별) | 신디케이션용 RSS. 보조금/정치/경제/시사를 키워드로 커버 | ✅ 신디케이션 | 🟢 낮음 |
| **NHK 뉴스** | 공식 RSS `nhk.or.jp/rss/news/<cat>.xml` | 방송사 공식 RSS. 요청 시 `.nhk` 브랜드 도메인으로 리다이렉트되며 자동 추적 | 공식 제공 | 🟢 낮음 |
| **YouTube 급상승** | **공식** YouTube Data API v3 (`chart=mostPopular&regionCode=JP`) | 스크래핑 대신 공식 무료 API(쿼터 제한). 가장 안정적. API 키 필요 | 공식 API | 🟢 낮음 |
| **트렌드 캘린더** | HTML 스크래핑 (`jp.trend-calendar.com`, X/Google 통합 랭킹) | 공식 API 없음. 랭킹 워드가 `twitter.com/search?q=…` 앵커로 노출되어 순서=순위로 파싱 | ✅ 랭킹 페이지 미차단(wp-*/author/category만 Disallow) | 🟡 중간 — 제3자 사이트 약관. 저빈도 접근 |
| **Google 트렌드(인기도)** | 비공식 `pytrends`, 키워드별 7일 관심도 | 키워드별 **지속 관심도**를 얻는 공식 무료 수단이 없음 | (내부 API) | 🟡 중간 — 비공식, 429 rate-limit 잦음. 키워드 수 제한·배치 sleep 적용. 미설치 시 자동 비활성화 |
| **Yahoo! 리얼타임** | HTML 스크래핑 (`__NEXT_DATA__` JSON 파싱) | X 기반 실시간 급상승 워드의 공식 API가 없음 | `/realtime`은 미차단이나… | 🔴 **높음 — Yahoo! JAPAN 이용약관이 robots와 별개로 자동수집을 제한.** 아래 경고 참고 |

### ⚠️ Yahoo! 리얼타임 관련 경고 (반드시 읽기)
- Yahoo! JAPAN 이용약관은 robots.txt 허용 여부와 **무관하게** 자동화된 데이터 수집/스크래핑을 제한합니다.
- 이 소스는 **사용자가 명시적으로 켠 경우에만** 동작합니다. **끄려면** `config.yaml` 에서
  `sources.yahoo_realtime.enabled: false` 로 바꾸면 됩니다.
- 켜두더라도 강한 요청 간격(`http.host_delays: search.yahoo.co.jp: 4.0초`)과 식별 UA로 접근하며,
  공개된 급상승 워드 랭킹만 읽습니다. **차단·약관 위반 리스크는 사용자 책임**이니 사용 전 약관을 확인하세요.

### 스크래핑 예의 장치 (공통, `app/http_client.py`)
- 도구를 식별하는 `User-Agent` (`config.yaml` 의 `http.user_agent`)
- 호스트별 최소 요청 간격 (`http.default_delay_seconds`, `http.host_delays`)
- 429/5xx/타임아웃에 **지수 백오프 재시도**
- 리다이렉트 자동 추적

리스크가 부담되면 해당 소스를 `enabled: false` 로 끄고 **공식 RSS/API 소스만**으로도 충분히 동작합니다.

---

## 설정 (`config.yaml`)

```yaml
categories:          # 카테고리 추가/삭제. news_queries=Google뉴스 검색어, keywords=pytrends, nhk_cats=NHK
sources:             # 소스별 enabled 토글, 파라미터, 카테고리 매핑
collection:
  refresh_interval_seconds: 900   # 자동 갱신 주기
  per_source_timeout_seconds: 30  # 소스별 타임아웃
  retention_days: 14              # 이력 보관(변동/지속 계산용)
classification:
  persist_min_occurrences: 3      # '지속' 판정 최소 등장 횟수
  persist_min_hours: 6            # '지속' 판정 최소 지속 시간
http:
  host_delays:                    # 사이트별 요청 간격(예의)
    search.yahoo.co.jp: 4.0
server: { host: 127.0.0.1, port: 8000 }
```

**카테고리 추가 예시**: `categories:` 아래에 `- id: sports / label: 스포츠 / news_queries: ["スポーツ"]` 만 추가하고 서버 재시작.

---

## 프로젝트 구조

```
post/
├── config.yaml            # 카테고리·소스·주기 설정
├── requirements.txt       # 의존성 (pytrends는 선택)
├── run.sh                 # 한 방 실행 스크립트
├── Dockerfile
├── .env.example           # YOUTUBE_API_KEY 등
└── app/
    ├── __main__.py        # python -m app 진입점
    ├── main.py            # FastAPI 앱 · 라우트 · 스케줄러
    ├── config.py          # config.yaml + .env 로딩
    ├── models.py          # RawTrendItem
    ├── http_client.py     # 예의 바른 공용 HTTP 클라이언트
    ├── storage.py         # SQLite (스냅샷·변동·지속)
    ├── collector.py       # 어댑터 격리 실행
    ├── classify.py        # 급상승/지속 판정
    ├── adapters/          # 소스별 어댑터 (어댑터 패턴)
    │   ├── base.py
    │   ├── __init__.py    # ADAPTER_REGISTRY
    │   ├── google_trends_rss.py
    │   ├── google_news_rss.py
    │   ├── nhk_rss.py
    │   ├── youtube_trending.py
    │   ├── trend_calendar.py
    │   ├── google_trends_interest.py
    │   └── yahoo_realtime.py
    └── static/            # 대시보드 (index.html · style.css · app.js)
```

## API

| 엔드포인트 | 설명 |
|---|---|
| `GET /api/trends?category=&view=&source=&q=&sort=&order=` | 현재 트렌드(변동/지속 계산 포함) |
| `GET /api/sources` | 소스별 헬스 |
| `GET /api/meta` | 카테고리·소스·갱신주기·마지막 갱신 |
| `POST /api/refresh` | 즉시 수집 트리거(백그라운드) |

---

## 면책
이 도구는 **개인 연구/모니터링 목적의 로컬 실행**을 전제로 합니다. 스크래핑 대상 사이트의
이용약관·robots.txt는 변경될 수 있으니 사용 전 직접 확인하세요. 특히 🔴 리스크 소스(Yahoo! 리얼타임)의
사용 책임은 이용자에게 있습니다. 상업적 재배포나 대량 수집에는 적합하지 않습니다.
