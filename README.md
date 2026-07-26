# 🇰🇷🇯🇵🇹🇼 한국·일본·대만 트렌드 모니터링 대시보드

**한국·일본·대만**에서 카테고리별로 사람들이 무엇에 관심을 갖는지 한눈에 파악하는 로컬 웹 대시보드입니다.
**실시간 급상승 트렌드**와 **지속 관심도**를 구분해서 보여주고, 각 트렌드 워드에 **한국어 번역**을 함께 표시하며,
매일 **뉴스 인사이트 리포트**를 파일로 남깁니다.

- **지역**: 🇰🇷 한국 · 🇯🇵 일본 · 🇹🇼 대만 (상단에서 전환, 기본=한국)
- **카테고리**(15): 지원금 · 연예 · 정치 · 정책 · 쇼핑 · 트렌드 · 경제 · 시사 · 스포츠 · IT·테크 · 부동산 · 건강 · 국제 · 게임 · 명절·기념일
- **거의 무료·무키**: 대부분 소스와 한국어 번역이 API 키 없이 동작. 네이버·YouTube만 무료 키(선택).

---

## 빠른 실행

```bash
./run.sh                     # venv 생성 → 의존성 설치 → .env 생성 → 실행 (권장)
# 또는
pip install -r requirements.txt && python -m app
# 또는 Docker
docker build -t trend . && docker run -p 8899:8000 trend
```
→ 브라우저에서 **http://127.0.0.1:8899** (포트는 `config.yaml` `server.port`).
첫 실행 시 즉시 1회 수집·번역하고, 이후 `config.yaml` `refresh_interval_seconds`(기본 15분)마다 자동 갱신합니다.

### 로컬에서 계속 띄워두기
```bash
./scripts/service.sh start   # 백그라운드 실행(터미널 닫아도 유지) · stop · restart · status · logs
```
> **재부팅 자동 시작**까지 원하면 `./scripts/service.sh install-launchd`. 단 저장소가 `~/Desktop` 아래면
> macOS TCC 정책상 해당 파이썬에 **Full Disk Access** 부여가 필요합니다(스크립트가 안내). `~/Desktop` 밖으로 옮기면 불필요.

---

## 화면 기능

- **지역 스위처** 🇰🇷/🇯🇵/🇹🇼 + **카테고리 탭** + **뷰 토글**(전체 / 🔥 실시간 급상승 / 📈 지속 관심도)
- 소스가 여러 개일 때 **소스별 그룹 + 각 소스 1위 강조(🥇)** + 상단 **"소스별 1위 요약" 바**
- 각 항목: 순위 · 변동(▲▼/NEW) · **🇰🇷 한국어 번역** · 출처 · 카테고리 · 지표
- **검색**(원어·한국어) · **정렬**(순위/변동/지표/최신/이름) · **소스 필터** · **필터 초기화**
- **소스 상태(헬스) 스트립**(한 소스가 죽어도 나머지 정상) · **자동 갱신** · **지금 갱신**

---

## 일일 인사이트 리포트 (뉴스 전용)

매일 **KST 00시·12시**(+서버 시작 시 오늘분 없으면 1회) 나라별·카테고리별 뉴스 트렌드 + 규칙기반 인사이트를 생성합니다.
- **`reports/daily.md`**: 사람이 읽는 마크다운, **최신순 누적**(날짜+시각 섹션). 급상승 검색 · 뉴스 키워드 트렌드(기사 수) · 카테고리별 주요 뉴스 · 인사이트 · 국가 공통 화제
- **`reports/daily.json`**: **다른 프로젝트가 파싱하기 좋은 구조화 데이터**(최신 스냅샷)
- 열람 `GET /api/report`(md) · `GET /api/report.json` · 즉시 생성 `POST /api/report/run`
- 설정: `config.yaml` `report`(파일 경로, 생성 시각 `hours_kst: [0, 12]`, on/off)

---

## 스택 선택 이유

| 레이어 | 선택 | 이유 |
|---|---|---|
| 백엔드 | **Python 3.11+ / FastAPI + Uvicorn** | 수집 라이브러리(pytrends·feedparser·BeautifulSoup·httpx)가 대부분 파이썬. 수집·번역·서빙·리포트를 한 프로세스로 |
| 스케줄러 | **APScheduler**(인프로세스) | 외부 브로커 없이 주기 수집 + 일일 리포트 cron |
| 저장소 | **SQLite**(표준 라이브러리) | 설치 0. 순위 변동·지속 관심도 계산용 스냅샷 이력 + 번역 캐시 |
| 프론트 | **빌드 없는 vanilla JS SPA** | npm 빌드 없이 명령 한두 개로 실행 |
| 번역 | **무료 Google translate 엔드포인트 + SQLite 캐시** | 키 불필요·무료. 같은 워드는 1회만 번역 |

---

## 아키텍처 & 확장

각 소스는 `app/adapters/base.py` 의 `BaseAdapter` 를 상속해 `fetch()` → `list[RawTrendItem]` 만 구현합니다.
어댑터는 **(소스 × 지역)** 조합으로 인스턴스화되고, 컬렉터가 **타임아웃+예외 격리**로 실행합니다(한 소스/지역이 죽어도 나머지 정상).

- **파생 소스**(`derived=True`): 1차 소스 수집 후 2단계로 실행되어 다른 소스 결과를 재료로 씀 → `news_keywords`, `naver_datalab`.
- **급상승 vs 지속**: 소스 선언 `source_type` + 이력(새 진입/순위 상승=급상승, 여러 수집 반복=지속). 임계값 `config.yaml` `classification`.
- **한국어 번역**: 미번역 워드만 번역해 `translations` 캐시. 한국어·영문(AI·EU) 워드는 스킵.

**확장:**
- 새 소스 = `app/adapters/`에 어댑터 → `adapters/__init__.py` `ADAPTER_REGISTRY` 등록 → `config.yaml` `sources`에 설정.
- 새 지역 = `config.yaml` `regions` + 각 소스 `geo`/`locale`·카테고리 `news_queries`/`keywords`에 지역 키.
- 새 카테고리 = `config.yaml` `categories`에 지역별 검색어 포함해 추가.

---

## 데이터 소스별 수집 방식 & 법적 주의점

> ⚖️ **원칙**: 각 사이트의 이용약관·robots.txt를 존중하고, 공개된 랭킹/헤드라인만 읽으며, 개인정보·로그인 데이터는 다루지 않습니다.
> 스크래핑 소스는 식별 UA + 사이트별 요청 간격으로 저빈도 접근합니다.

| 소스 | 지역 | 수집 방식 | 리스크 |
|---|:---:|---|:---:|
| **뉴스 키워드 트렌드** `news_keywords` | KR·JP·TW | 파생·무네트워크 — 수집된 뉴스에서 키워드 추출→**문서빈도(기사 수)** 랭킹(여러 매체가 다룬 주제=트렌드) | 🟢 없음 |
| **Google 뉴스 톱스토리** | KR·JP·TW | 공개 RSS 메인 피드 — 키워드X, **인기/중요도 랭킹**('많이 본 뉴스'에 근접) | 🟢 낮음 |
| **Google 뉴스** | KR·JP·TW | RSS 검색(지역 로케일·언어별 검색어, 최근 `when:2d`) | 🟢 낮음 |
| **Google 트렌드(일간)** | KR·JP·TW | 공개 RSS `trending/rss?geo=…` (robots ✅) | 🟢 낮음 |
| **Google 트렌드(인기도)** | KR·JP·TW | 비공식 `pytrends`(7일 관심도) | 🟡 중간 — 429 잦음, 실패 시 자동 degrade |
| **signal.bz 실시간 검색어** | KR | 공개 집계 API(JSON) — 폐지된 네이버/다음 실검 대체 | 🟢 낮음 — 제3자 집계 |
| **네이버 뉴스** `naver_news` | KR | 공식 API(NCP API Hub, 검색·뉴스) | 🟢 낮음 — 무료 키 |
| **네이버 검색관심도** `naver_datalab` | KR | 파생 — 급상승 워드를 데이터랩에 넣어 네이버 검색관심도로 랭킹 | 🟢 낮음 — 무료 키 |
| **NHK 뉴스** | JP | 공식 RSS(`.nhk` 리다이렉트 자동 추적) | 🟢 낮음 |
| **트렌드 캘린더** | JP | 스크래핑(X 통합 랭킹) — robots ✅ | 🟡 중간 — 제3자 약관 |
| **Yahoo! 리얼타임** | JP | 스크래핑(`__NEXT_DATA__` JSON) | 🔴 **높음 — Yahoo! JAPAN 약관이 자동수집 제한** |
| **PTT(批踢踢)** | TW | 스크래핑(게시판 인기글·추천수) — robots 없음 | 🟡 중간 — 대만 최대 커뮤니티 |
| ~~YouTube 급상승~~ | — | 기본 비활성(별도 도구에서 관리, `YOUTUBE_API_KEY`로 활성화) | — |

### 네이버 (권장, 무료 키 · NCP API Hub)
한국은 네이버 검색 점유율이 높아 대표성이 큽니다. 단 네이버는 `robots.txt`가 `Disallow: /`(전면 금지)이고 뉴스 RSS도 폐지돼 **스크래핑 불가** → 합법 경로는 **공식 API**(2024년 이후 **NCP API Hub**로 이관)뿐입니다.
- **발급/활성화**: [ncloud.com](https://www.ncloud.com) 콘솔 → **API Hub** → 애플리케이션 등록 → **검색(뉴스)** 과 **데이터랩(검색어트렌드)** 를 각각 활성화/구독 → `.env` 의 `NAVER_CLIENT_ID`·`NAVER_CLIENT_SECRET`.
- 인증 헤더 `X-NCP-APIGW-API-KEY-ID` / `X-NCP-APIGW-API-KEY`. 엔드포인트: 뉴스 `naverapihub.apigw.ntruss.com/search/v1/news`, 검색어트렌드 `naverapihub.apigw.ntruss.com/search-trend/v1/search` (config로 덮어쓰기 가능).
- 키 없거나 미활성 시 네이버 소스만 헬스에 오류로 표시되고 나머지는 정상.
- **signal.bz**(키 불필요)가 폐지된 실검을 대체해 한국 실시간 급상승을 이미 커버합니다.

### 대만(TW)
**Google 트렌드/뉴스 TW(zh-TW) + pytrends TW + PTT(批踢踢)**. PTT는 Google 계열이 아닌 현지 소셜 트렌드로, 게시판별 인기글을 카테고리로 매핑합니다(八卦→시사, 股票→경제, 電影→연예 등). Yahoo·트렌드캘린더는 대만판이 없어 일본 전용, trends24/getdaytrends는 대만 페이지 없음, Dcard는 봇 차단이라 제외.

### ⚠️ 리스크 안내
- **Yahoo! 리얼타임**: JAPAN 약관이 robots와 무관하게 자동수집 제한. 사용자가 켠 경우만 동작(`sources.yahoo_realtime.enabled: false`로 끔). 사용 책임은 이용자.
- **번역 엔드포인트**: 무료·비공식 Google translate. 캐시+동시요청 제한+주기당 상한으로 최소 호출(`translation.enabled: false`로 끔).

---

## 설정 (`config.yaml`)

```yaml
regions:        # kr, jp, tw … (첫 항목이 기본 지역)
categories:     # 카테고리. news_queries/keywords 는 지역별 {kr:[...], jp:[...], tw:[...]}
sources:        # 소스별 enabled·regions·지역별 파라미터(geo/locale)·recency 등
translation:    # 번역 on/off, 동시요청/주기당 상한
report:         # 일일 리포트 파일 경로·생성 시각(hours_kst)
collection:     # refresh_interval_seconds, per_source_timeout_seconds, retention_days
classification: # 지속 판정 임계값
http:           # UA, 사이트별 요청 간격(host_delays)
server:         # host/port (기본 127.0.0.1:8899)
```

---

## 프로젝트 구조

```
post/
├── CLAUDE.md · README.md · config.yaml · requirements.txt
├── run.sh · Dockerfile · .env.example · scripts/service.sh
└── app/
    ├── __main__.py        # python -m app 진입점
    ├── main.py            # FastAPI · 라우트 · 스케줄러(수집/리포트)
    ├── config.py          # config.yaml + .env, 지역/지역별 쿼리 헬퍼
    ├── models.py          # RawTrendItem
    ├── http_client.py     # 예의 바른 공용 HTTP 클라이언트(GET/POST)
    ├── translate.py       # 무료 한국어 번역
    ├── keywords.py        # 뉴스 키워드 추출(문서빈도, 조각 병합)
    ├── report.py          # 일일 인사이트 리포트(md 누적 + json)
    ├── storage.py         # SQLite (스냅샷·변동·지속·번역 캐시)
    ├── collector.py       # (소스×지역) 격리 실행 · 2단계(파생) · 번역
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
| `GET /api/report` · `GET /api/report.json` | 일일 리포트(md · 구조화 json) |
| `POST /api/report/run` | 리포트 즉시 생성 |

---

## 면책
개인 연구/모니터링 목적의 **로컬 실행**을 전제로 합니다. 스크래핑 대상과 번역 엔드포인트의 약관·robots.txt는
변경될 수 있으니 사용 전 확인하세요. 🔴 리스크 소스(Yahoo! 리얼타임)와 비공식 번역 사용 책임은 이용자에게 있습니다.
상업적 재배포·대량 수집에는 적합하지 않습니다.
