# 🇯🇵🇹🇼 일본·대만 트렌드 모니터링 대시보드

**일본**과 **대만**에서 카테고리별로 사람들이 무엇에 관심을 갖는지 한눈에 파악하는 로컬 웹 대시보드입니다.
**실시간 급상승 트렌드**와 **지속 관심도**를 구분해서 보여주고, 각 트렌드 워드에 **한국어 번역**을 함께 표시합니다.

- 지역: 🇯🇵 일본 / 🇹🇼 대만 (상단에서 클릭 전환, `config.yaml` 에서 추가 가능)
- 카테고리: 보조금 · 연예 · 정치 · 쇼핑 · 트렌드 · 경제 · 시사 (설정에서 추가/삭제)
- 모든 데이터 소스·번역은 **무료**(API 키 불필요; 번역은 무료 엔드포인트 + 캐시)

---

## 빠른 실행

### 방법 A — 스크립트 한 방 (권장)
```bash
./run.sh
```
가상환경 생성 → 의존성 설치 → `.env` 생성 → 서버 실행까지 자동. 브라우저에서 **http://127.0.0.1:8899** 접속.
(포트는 `config.yaml` 의 `server.port` 에서 변경)

### 방법 B — 수동 (2개 명령)
```bash
pip install -r requirements.txt
python -m app
```

### 방법 C — Docker
```bash
docker build -t jp-trend .
docker run -p 8899:8000 jp-trend   # → http://127.0.0.1:8899
```

> **API 키 불필요.** 모든 소스(공개 RSS/스크래핑/pytrends)와 한국어 번역이 키 없이 동작합니다.
> (YouTube 어댑터는 기본 비활성 상태이며, 쓰려면 `.env` 의 `YOUTUBE_API_KEY` + config 활성화가 필요합니다.)

첫 실행 시 즉시 1회 수집·번역하고, 이후 `config.yaml` 의 `refresh_interval_seconds`(기본 15분)마다 자동 갱신합니다.

### 로컬에서 계속 띄워두기 (백그라운드 상시 실행)
```bash
./scripts/service.sh start     # 백그라운드 실행 (터미널 닫아도 유지)
./scripts/service.sh status    # 실행/응답 상태
./scripts/service.sh logs      # 로그 보기
./scripts/service.sh stop      # 중지
./scripts/service.sh restart   # 재시작
```
`start` 는 `nohup` 으로 띄워 **터미널을 닫아도 계속 실행**됩니다(추가 권한 불필요).

> **재부팅 후 자동 시작까지** 원하면 `./scripts/service.sh install-launchd` 를 실행하세요.
> 단, 이 저장소가 `~/Desktop` 아래라 macOS 프라이버시(TCC) 정책상 **Full Disk Access** 를
> 해당 파이썬 실행파일에 부여해야 백그라운드 launchd 에이전트가 파일을 읽을 수 있습니다
> (스크립트가 정확한 경로와 등록 명령을 안내합니다). 권한 부여가 부담되면 저장소를
> `~/Desktop` 밖(예: `~/apps/post`)으로 옮기면 그 제약이 사라집니다.

---

## 화면 기능

- **지역 스위처**(🇯🇵/🇹🇼) — 상단에서 클릭 한 번으로 전환
- **카테고리 탭** + **뷰 토글**(`전체` / `🔥 실시간 급상승` / `📈 지속 관심도`)
- **각 워드**: 순위 · 변동(▲▼/NEW) · **🇰🇷 한국어 번역** · 출처 · 카테고리 · 지표
- **검색**(원어·한국어 모두) · **정렬**(순위/변동/지표/최신/이름) · **소스 필터**
- **소스 상태(헬스) 스트립**: 지역별 소스 성공/오류 표시(⚠️는 리스크 소스). 한 소스가 죽어도 나머지는 정상
- **자동 갱신** + **지금 갱신** 버튼

---

## 스택 선택 이유

| 레이어 | 선택 | 이유 |
|---|---|---|
| 백엔드 | **Python 3.11+ / FastAPI + Uvicorn** | 수집 라이브러리(pytrends·feedparser·BeautifulSoup·httpx)가 대부분 파이썬. 수집·번역·서빙을 한 프로세스로 |
| 스케줄러 | **APScheduler** (인프로세스) | 외부 브로커 없이 주기 수집 |
| 저장소 | **SQLite** (표준 라이브러리) | 설치 0. 순위 변동·지속 관심도 계산용 스냅샷 이력 + **번역 캐시** 저장 |
| 프론트 | **빌드 없는 vanilla JS SPA** | npm 빌드 없이 "명령 한두 개"로 실행 |
| 번역 | **무료 Google translate 엔드포인트 + SQLite 캐시** | 키 불필요·무료. 같은 워드는 1회만 번역 |

---

## 아키텍처 & 어댑터 패턴

각 소스는 `app/adapters/base.py` 의 `BaseAdapter` 를 상속하고 `fetch()` → `list[RawTrendItem]` 만 구현합니다.
어댑터는 **(소스 × 지역)** 조합으로 인스턴스화되어(예: `google_trends_rss@jp`, `google_trends_rss@tw`),
컬렉터가 각각을 **타임아웃 + 예외 격리**로 실행합니다. → 한 소스/지역이 실패해도 나머지는 정상(graceful).

**새 소스 추가(3단계):** ① `app/adapters/` 에 어댑터 작성 → ② `adapters/__init__.py` 의 `ADAPTER_REGISTRY` 등록 → ③ `config.yaml` `sources` 에 `regions` 포함 설정 추가.

**새 지역 추가:** `config.yaml` `regions` 에 항목 추가 + 각 소스의 `geo`/`locale`·카테고리의 `news_queries`/`keywords` 에 해당 지역 키 추가.

### 급상승 vs 지속 관심도
소스가 선언한 `source_type` 을 1차 축으로, 이력 기반으로 **급상승**(새 진입/순위 상승) / **지속**(여러 수집에 걸쳐 오래 등장)을 태그합니다. 임계값은 `config.yaml` 의 `classification`.

### 한국어 번역
수집 후 현재 표시 항목 중 **미번역 워드만** 무료 엔드포인트로 번역하고 SQLite `translations` 에 캐시합니다.
동시요청·주기당 상한(`config.translation`)으로 과호출을 막고, 실패 워드는 원어만 표시합니다(graceful).

---

## 데이터 소스별 수집 방식 & 법적 주의점

> ⚖️ **원칙**: 각 사이트의 이용약관·robots.txt를 존중하고, 공개된 랭킹/헤드라인만 읽으며,
> 개인정보·로그인 데이터는 다루지 않습니다. 스크래핑 소스는 식별 UA + 사이트별 요청 간격으로 저빈도 접근합니다.

| 소스 | 지역 | 수집 방식 | robots.txt(실측) | 리스크 |
|---|:---:|---|:---:|:---:|
| **Google 트렌드(일간)** | JP·TW | 공개 RSS `trending/rss?geo=JP\|TW` | ✅ 허용(`/explore?`만 차단) | 🟢 낮음 |
| **Google 뉴스** | JP·TW | RSS `news.google.com/rss/search` (지역 로케일·언어별 검색어) | ✅ 신디케이션 | 🟢 낮음 |
| **Google 트렌드(인기도)** | JP·TW | 비공식 `pytrends`, 키워드별 7일 관심도 | (내부 API) | 🟡 중간 — 429 잦음, 미설치/실패 시 자동 degrade |
| **NHK 뉴스** | JP | 공식 RSS(`.nhk` 도메인 리다이렉트 자동 추적) | 공식 제공 | 🟢 낮음 |
| **트렌드 캘린더** | JP | 스크래핑(X 통합 랭킹 앵커) | ✅ 랭킹 페이지 미차단 | 🟡 중간 — 제3자 약관, 저빈도 |
| **Yahoo! 리얼타임** | JP | 스크래핑(`__NEXT_DATA__` JSON) | `/realtime` 미차단이나… | 🔴 **높음 — Yahoo! JAPAN 약관이 자동수집 제한** |
| ~~YouTube 급상승~~ | — | (기본 비활성 — 별도 도구에서 관리) | 공식 API | — |

### 대만(TW) 소스에 대해
대만은 **Google 트렌드 TW + Google 뉴스 TW(중국어 zh-TW) + pytrends TW** 로 커버합니다.
- Yahoo! 리얼타임은 일본 전용(대만판 없음), 트렌드 캘린더도 대만판(`tw.trend-calendar.com`)이 없어 **일본 전용**입니다.
- 대만용 X/소셜 트렌드 사이트(trends24·getdaytrends 등)는 현재 안정적인 무료 접근이 어려워 제외했습니다.
  필요하면 어댑터 패턴으로 손쉽게 추가할 수 있습니다.

### ⚠️ Yahoo! 리얼타임 경고
Yahoo! JAPAN 약관은 robots.txt와 무관하게 자동 수집을 제한합니다. 이 소스는 사용자가 켠 경우에만 동작하며,
**끄려면** `config.yaml` 에서 `sources.yahoo_realtime.enabled: false`. 사용 책임은 이용자에게 있습니다.

### ⚠️ 번역 엔드포인트에 대해
한국어 번역은 무료·키 불필요한 **비공식** Google translate 엔드포인트를 사용합니다. 과도한 호출 시 일시 차단될 수 있어
**캐시 + 동시요청 제한 + 주기당 상한**으로 최소 호출만 합니다. 끄려면 `config.yaml` 의 `translation.enabled: false`.

---

## 설정 (`config.yaml`)

```yaml
regions:        # 지역(타겟) — jp, tw … 추가 가능
categories:     # 카테고리. news_queries/keywords 는 지역별 {jp:[...], tw:[...]}
sources:        # 소스별 enabled·regions·지역별 파라미터(geo/locale)
translation:    # 한국어 번역 on/off, 동시요청/주기당 상한
collection:     # refresh_interval_seconds, per_source_timeout_seconds, retention_days
classification: # 지속 판정 임계값
http:           # UA, 사이트별 요청 간격
server:         # host/port (기본 127.0.0.1:8899)
```

---

## 프로젝트 구조

```
post/
├── config.yaml            # 지역·카테고리·소스·번역 설정
├── requirements.txt       # 의존성 (pytrends는 선택)
├── run.sh · Dockerfile · .env.example
└── app/
    ├── __main__.py        # python -m app 진입점
    ├── main.py            # FastAPI · 라우트(지역별) · 스케줄러
    ├── config.py          # config.yaml + .env, 지역/지역별 쿼리 헬퍼
    ├── models.py          # RawTrendItem (region 포함)
    ├── http_client.py     # 예의 바른 공용 HTTP 클라이언트
    ├── translate.py       # 무료 한국어 번역
    ├── storage.py         # SQLite (지역별 스냅샷·변동·지속·번역 캐시)
    ├── collector.py       # (소스×지역) 격리 실행 + 번역 단계
    ├── classify.py        # 급상승/지속 판정
    ├── adapters/          # 소스별 어댑터 (어댑터 패턴)
    └── static/            # 대시보드 (index.html · style.css · app.js)
```

## API

| 엔드포인트 | 설명 |
|---|---|
| `GET /api/trends?region=&category=&view=&source=&q=&sort=&order=` | 지역별 현재 트렌드(변동/지속/한국어 포함) |
| `GET /api/sources?region=` | 지역별 소스 헬스 |
| `GET /api/meta` | 지역·카테고리·소스·갱신주기 |
| `POST /api/refresh` | 즉시 수집 트리거 |

---

## 면책
개인 연구/모니터링 목적의 **로컬 실행**을 전제로 합니다. 스크래핑 대상과 번역 엔드포인트의 약관·robots.txt는
변경될 수 있으니 사용 전 확인하세요. 🔴 리스크 소스(Yahoo! 리얼타임)와 비공식 번역 사용 책임은 이용자에게 있습니다.
상업적 재배포·대량 수집에는 적합하지 않습니다.
