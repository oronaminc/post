"""PTT (批踢踢) — 대만 최대 커뮤니티의 인기글. 대만 전용 소스.

Google 계열이 아닌 **대만 현지 소셜 트렌드**를 커버한다.
수집 방식: ptt.cc 의 각 게시판 index 페이지(서버 렌더 HTML)를 파싱.
  - `div.r-ent` 행에서 제목 / 추천수(nrec: 숫자·'爆'=100↑) / 링크 추출.
  - 추천수로 정렬해 '지금 뜨는 글'을 뽑는다.
  - 게시판 → 카테고리 매핑(config)으로 경제/정치/연예/시사 등에 배치.
robots.txt: ptt.cc 는 robots.txt 가 없음(제약 미선언). 그래도 저빈도·식별 UA로 접근.
over18 게시판은 공개 연령확인 쿠키(over18=1)만 전송(로그인/개인정보 아님).
성격: 실시간 급상승(realtime) — 현재 활발히 논의되는 글.
리스크: 중간(제3자 사이트 스크래핑).
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from ..models import RawTrendItem, SOURCE_TYPE_REALTIME
from .base import BaseAdapter

BASE = "https://www.ptt.cc"


def _parse_push(text: str) -> int:
    """추천수 파싱: 숫자 / '爆'(100+) / 'XN'(반대 다수)/공백."""
    t = (text or "").strip()
    if t == "爆":
        return 100
    if t.startswith("X"):  # X1~X9 = 대량 비추천 → 인기글 아님
        return 0
    if t.isdigit():
        return int(t)
    return 0


# 실제 트렌드가 아닌 게시판 운영성 글(공지/집중글 등)은 제외
_SKIP_TAGS = ("[公告]", "[集中]", "[板務]", "[申請]", "[問卷]")


def _is_admin_post(title: str) -> bool:
    return any(tag in title for tag in _SKIP_TAGS)


class PttTaiwanAdapter(BaseAdapter):
    name = "ptt_taiwan"
    display_name = "PTT (대만)"
    default_source_type = SOURCE_TYPE_REALTIME
    risk = "medium"

    async def fetch(self) -> list[RawTrendItem]:
        boards = self.settings.get("boards", []) or []
        per_board = int(self.settings.get("per_board_limit", 8))
        min_push = int(self.settings.get("min_push", 5))

        items: list[RawTrendItem] = []
        saw_articles = False

        for b in boards:
            board = b.get("name")
            if not board:
                continue
            category = self._safe_category(b.get("category", "trend"))
            url = f"{BASE}/bbs/{board}/index.html"
            try:
                # over18=1: 공개 연령확인 쿠키(로그인/개인정보 아님)
                html = await self.http.get_text(url, headers={"Cookie": "over18=1"})
            except Exception:
                # 한 게시판 실패는 건너뛰고 계속(부분 실패 허용)
                continue

            soup = BeautifulSoup(html, "html.parser")
            container = soup.select_one(".r-list-container") or soup
            board_articles: list[tuple[int, str, str]] = []
            # 문서 순서대로 순회하다 구분선(.r-list-sep)을 만나면 중단
            #  → 구분선 아래의 고정 공지글(置底)은 제외.
            for el in container.find_all(class_=["r-ent", "r-list-sep"]):
                classes = el.get("class", [])
                if "r-list-sep" in classes:
                    break
                a = el.select_one(".title a")
                if not a:  # 삭제된 글
                    continue
                saw_articles = True
                nrec = el.select_one(".nrec")
                push = _parse_push(nrec.text if nrec else "")
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if title and href and not _is_admin_post(title):
                    board_articles.append((push, title, href))

            board_articles.sort(key=lambda x: x[0], reverse=True)
            picked = 0
            for push, title, href in board_articles:
                if push < min_push:
                    continue
                items.append(RawTrendItem(
                    term=title,
                    source=self.name,
                    source_type=SOURCE_TYPE_REALTIME,
                    category=category,
                    rank=0,  # 아래에서 전체 재랭크
                    metric_label="추천",
                    metric_value=float(push),
                    url=BASE + href,
                    extra={"board": board, "push": push},
                ))
                picked += 1
                if picked >= per_board:
                    break

        if not saw_articles:
            raise RuntimeError("PTT 게시판에서 글을 찾지 못함 (구조 변경/차단 가능)")

        # 전체를 추천수 순으로 재랭크
        items.sort(key=lambda it: it.metric_value, reverse=True)
        for i, it in enumerate(items, start=1):
            it.rank = i
        return items
