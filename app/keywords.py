"""뉴스 헤드라인에서 '많이 다뤄진 키워드' 추출 (무설치·순수 파이썬).

핵심 아이디어(사용자 요청):
  하나의 기사가 뜨는 건 단독보도일 수 있다. 하지만 **하나의 주제를 여러 매체가
  동시에 다루면** 그 키워드의 '문서빈도(등장 기사 수)'가 높아진다 → 진짜 트렌드.
  그래서 키워드를 뽑아 **몇 개 기사에서 다뤘나**로 랭킹한다. (= 집단적 관심의 근사치)

언어별 후보 추출:
  - 한국어(kr): 공백 토큰화 + 조사/접미 제거.
  - 일본어(ja): 한자·가타카나 구간의 n-gram(2~4).
  - 중국어(zh, 대만): 한자 구간의 n-gram(2~4).
  - 공통: 영문/약어 토큰.
불용어 + 부분문자열 정리로 노이즈를 줄인다. 외부 형태소분석기 없이 동작한다.
"""
from __future__ import annotations

import re
from collections import defaultdict

# ' - 언론사' / ' – 매체' 같은 출처 접미 제거
_SRC_SUFFIX = re.compile(r"\s*[-–—]\s*[^-–—]{1,24}$")
_PUNCT = re.compile(r"[\[\]()（）「」『』<>《》【】…·、,\.!?\"'“”‘’|/\\:;~%＄$#*■◆▶=]+")

_KR = re.compile(r"[가-힣]{2,}")
_JA_KANJI = re.compile(r"[一-鿿々〆ヶ]{2,}")
_KATA = re.compile(r"[ァ-ヴー]{2,}")
_HAN = re.compile(r"[一-鿿]{2,}")
_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9]+")

# 한국어 조사/접미(뒤에서 벗겨냄)
_KR_JOSA = (
    "으로써", "으로", "에서", "에게", "께서", "까지", "부터", "이라며", "라며", "이라고",
    "라고", "한다", "했다", "하는", "하고", "되며", "된다", "했던", "이라", "에는",
    "에도", "로도", "만에", "와의", "과의", "의", "를", "을", "이", "가", "은", "는",
    "도", "에", "와", "과", "로", "들", "만", "측", "발",
)

_STOP = {
    "kr": {"이런", "저런", "그런", "때문", "위해", "대한", "관련", "오늘", "내일", "어제",
            "이번", "지난", "올해", "최근", "현재", "대해", "통해", "우리", "국내", "전날",
            "이후", "이날", "기자", "속보", "단독", "종합", "영상", "사진", "경우", "상황",
            "논란", "공식", "결국", "그냥", "밝혀", "밝힌", "말했", "전했", "나선", "예정",
            "무슨", "한편", "지난해", "가운데", "이라는", "라는",
            # generic
            "한국", "미국", "중국", "일본", "최대", "최고", "최초", "지원", "포토", "공개",
            "발표", "오전", "오후", "이상", "이하", "사람", "이유", "모습", "활용", "대상",
            "방안", "추진", "강화", "확대", "개최", "완료", "시작", "종료", "각각", "여러",
            "모든", "다시", "이제", "정도", "기존", "특히", "가장", "실제", "당국", "전체",
            "일부", "관계자", "했다는", "한다는", "라며", "면서", "대비", "위한", "관측",
            "우려", "속출", "논란속", "이라고", "무단"},
    "ja": {"発表", "報道", "速報", "関連", "今日", "明日", "昨日", "今回", "記事", "写真",
            "動画", "独占", "解説", "一覧", "詳細", "掲載", "公開", "開催", "実施",
            # generic
            "日本", "可能性", "最大", "最高", "決定", "大会", "発生", "開始", "予定",
            "検討", "対応", "参加", "影響", "状況", "場合", "一部", "関係", "今後",
            "全国", "地域", "世界", "情報", "理由", "方法", "内容", "結果", "以上",
            "以下", "本当", "自分", "場所", "時間", "現在", "会見", "一方", "注目",
            "話題", "本日", "確認", "必要", "使用", "利用", "問題", "予想"},
    "zh": {"今天", "報導", "報道", "新聞", "影片", "照片", "獨家", "快訊", "記者", "相關",
            "指出", "表示", "發生", "如何", "為何", "這個", "一名", "公開",
            # generic
            "台灣", "中國", "專家", "一次", "全台", "來了", "目前", "今年", "民眾",
            "影響", "可能", "引發", "爆發", "傳出", "驚傳", "網友", "網路", "以及",
            "知道", "發現", "出現", "進行", "造成", "成為", "結束", "方式", "問題",
            "情況", "地方", "畫面", "最新", "是否", "不是", "什麼", "怎麼", "這樣",
            "一起", "持續", "沒有", "還是", "竟然", "直接", "完整", "整理",
            "一次看", "都能", "打造", "曝光", "回應", "遭到", "疑似", "宣布"},
}

# 지역 id -> 언어 코드
REGION_LANG = {"kr": "kr", "jp": "ja", "tw": "zh"}


def _strip_josa(w: str) -> str:
    for j in _KR_JOSA:
        if w.endswith(j) and len(w) - len(j) >= 2:
            return w[: -len(j)]
    return w


def clean_headline(title: str) -> str:
    t = _SRC_SUFFIX.sub("", title or "")
    return _PUNCT.sub(" ", t)


def _ngrams(run: str, lo: int = 2, hi: int = 4):
    for n in range(lo, hi + 1):
        for i in range(len(run) - n + 1):
            yield run[i:i + n]


def candidates(title: str, lang: str) -> set[str]:
    """헤드라인 하나에서 키워드 후보 집합."""
    t = clean_headline(title)
    out: set[str] = set()
    for w in _LATIN.findall(t):
        if len(w) >= 2:
            out.add(w)
    if lang == "kr":
        for w in _KR.findall(t):
            w = _strip_josa(w)
            if len(w) >= 2 and w not in _STOP["kr"]:
                out.add(w)
    elif lang == "ja":
        # 가타카나는 한 단어이므로 통째로 (n-gram으로 쪼개지 않음)
        for run in _KATA.findall(t):
            if 2 <= len(run) <= 12 and run not in _STOP["ja"]:
                out.add(run)
        # 한자 복합어는 n-gram (짧으면 통째로)
        for run in _JA_KANJI.findall(t):
            if len(run) <= 4:
                if run not in _STOP["ja"]:
                    out.add(run)
            else:
                for g in _ngrams(run):
                    if g not in _STOP["ja"]:
                        out.add(g)
    else:  # zh
        for run in _HAN.findall(t):
            for g in _ngrams(run):
                if g not in _STOP["zh"]:
                    out.add(g)
    return out


def build_exclude(seeds, lang: str) -> set[str]:
    """카테고리 검색어(seed)와 그 조각을 제외셋으로. seed는 검색으로 인해
    해당 카테고리 기사에 항상 들어가 문서빈도가 인위적으로 높기 때문."""
    exclude: set[str] = set()
    for s in seeds:
        s = (s or "").strip()
        if not s:
            continue
        exclude.add(s.lower())
        if lang in ("ja", "zh"):
            for g in _ngrams(s, 2, 4):
                exclude.add(g.lower())
    return exclude


def extract_trends(docs: list[tuple[str, str]], lang: str,
                   min_df: int = 3, top: int = 25,
                   exclude: set[str] | None = None) -> list[dict]:
    """docs: [(headline, category)]. 문서빈도(df) 랭킹 키워드 리스트 반환.

    반환: [{term, df, category}] — df=그 키워드를 다룬 (중복제거된) 기사 수.
    exclude: 제외할 워드(소문자) — 카테고리 검색어 등.
    """
    exclude = exclude or set()
    df: dict[str, int] = defaultdict(int)
    cat_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    seen_titles: set[str] = set()
    for title, category in docs:
        title = (title or "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        for c in candidates(title, lang):
            if c.lower() in exclude:
                continue
            df[c] += 1
            cat_count[c][category] += 1

    items = [(term, n) for term, n in df.items() if n >= min_df]

    # CJK 부분문자열 정리: 더 긴 키워드에 포함되고 빈도가 비슷하면 짧은 건 버림
    if lang in ("ja", "zh"):
        items.sort(key=lambda x: (-len(x[0]), -x[1]))
        kept: list[tuple[str, int]] = []
        for term, n in items:
            if any(term in k and term != k and n <= kn * 1.34 for k, kn in kept):
                continue
            kept.append((term, n))
        items = kept

    items.sort(key=lambda x: x[1], reverse=True)
    result = []
    for term, n in items[:top]:
        cat = max(cat_count[term].items(), key=lambda kv: kv[1])[0]
        result.append({"term": term, "df": n, "category": cat})
    return result
