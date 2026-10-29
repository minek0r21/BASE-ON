"""
장면(영상) 연결 공통 — 07(매칭)·08(적재)이 같이 쓴다. 설계: docs/장면.md

  영상 목록 읽기   load_videos()   재생목록 CSV(06) 또는 영상 목록 JSON(yt_inventory.json, 34,000개)
  영상 분류(07a)   classify()      game_highlight · chapter · clip · other
  결과 파일        links_<시즌>.csv  연결 대상 종류와 상관없이 한 형식 (LINK_COLUMNS)
                   videos_<시즌>.csv 적재할 영상 (VIDEO_COLUMNS)

연결 대상(target_kind)은 셋이다: game(경기) · pa(타석) · outing(등판, 3단계).
"""
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_DIR = ROOT / "videos"

# ---------------------------------------------------------------- 결과 파일 형식
# rel: candidate(후보, CANDIDATE) · matched(연결, MATCHED_TO)
LINK_COLUMNS = ["rel", "target_kind", "target_id", "video_id", "scene_type", "precision", "start_sec", "end_sec",
                "status", "origin", "review_reason", "score", "rank", "reasons", "tags"]
VIDEO_COLUMNS = ["video_id", "title", "channel", "kind", "game_date", "published_at", "duration_sec", "embeddable"]

TARGETS = {  # target_kind → (노드 라벨, 키 속성). 08이 Cypher를 만들 때 이 표만 쓴다
    "game": ("Game", "game_pk"),
    "pa": ("PlateAppearance", "pa_id"),
    "outing": ("Outing", "outing_id"),
}
SCENE_TYPES = {"game", "home_run", "hit", "batting", "outing", "closing", "milestone"}
PRECISIONS = {"scene", "inning", "game"}


STEPS = ("game", "pa", "outing")  # 07 단계 = 결과 파일 단위 (07b 경기 하이라이트 · 07c 장면 클립 → 타석 · 07d·e 등판)


def links_path(season: int, step: str) -> Path:
    return VIDEOS_DIR / f"links_{season}_{step}.csv"


def videos_path(season: int, step: str) -> Path:
    return VIDEOS_DIR / f"videos_{season}_{step}.csv"


def write_links(rows: list[dict], season: int, step: str) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=LINK_COLUMNS)
    bad = set(df["target_kind"]) - set(TARGETS) | set(df["scene_type"].dropna()) - SCENE_TYPES \
        | set(df["precision"].dropna()) - PRECISIONS
    if bad:
        raise ValueError(f"알 수 없는 값: {bad}")
    df.to_csv(links_path(season, step), index=False, encoding="utf-8-sig")
    return df


def read_season(season: int) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """그 시즌 07 결과 파일 전부 → (영상, 연결, 읽은 단계). 영상은 video_id로 하나만"""
    steps = [s for s in STEPS if links_path(season, s).exists()]
    if not steps:
        raise SystemExit(f"{season} 시즌 07 결과가 없습니다 (videos/links_{season}_<단계>.csv). 07을 먼저 돌리세요.")
    links = pd.concat([pd.read_csv(links_path(season, s), dtype={"target_id": str, "video_id": str, "reasons": str,
                                                                "tags": str, "review_reason": str}, encoding="utf-8-sig")
                       for s in steps], ignore_index=True)
    videos = pd.concat([pd.read_csv(videos_path(season, s), dtype={"video_id": str}, encoding="utf-8-sig")
                        for s in steps], ignore_index=True).drop_duplicates("video_id")
    return videos, links, steps


# ---------------------------------------------------------------- 제목에서 팀·날짜
TEAM_WORDS = {  # 줄임말·풀네임·별칭 → 팀 코드 (긴 말부터 찾는다)
    "KIA": "HT", "기아": "HT", "타이거즈": "HT", "두산": "OB", "베어스": "OB", "LG": "LG", "트윈스": "LG",
    "삼성": "SS", "라이온즈": "SS", "롯데": "LT", "자이언츠": "LT", "SSG": "SK", "랜더스": "SK",
    "한화": "HH", "이글스": "HH", "키움": "WO", "히어로즈": "WO", "KT": "KT", "kt": "KT", "위즈": "KT",
    "NC": "NC", "다이노스": "NC",
}
CHANNEL_TEAM = {"LG": "LG", "한화": "HH", "KT": "KT", "삼성": "SS", "KIA": "HT", "두산": "OB", "롯데": "LT",
                "키움": "WO", "NC": "NC", "SSG": "SK"}
RE_DATES = [  # (정규식, 연도 그룹 있음)
    (re.compile(r"(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})"), True),          # (2025.7.1)
    (re.compile(r"(?<![\d.])(2\d)\.(\d{1,2})\.(\d{1,2})(?![\d])"), True),  # 25.08.24. (구단 채널, 두 자리 연도)
    (re.compile(r"(?<![\d.])(\d{1,2})월\s*(\d{1,2})일"), False),          # 9월 21일
    (re.compile(r"(?<![\d./])(\d{1,2})[./](\d{1,2})(?![\d.]*\d{3})"), False),  # 5.25 · 8/14 · (06.08)
]
RE_DH = re.compile(r"DH\s*-?\s*([12])|더블헤더\s*([12])\s*차|([12])\s*차전")  # DH2 · DH-1 · 더블헤더 1차 · 2차전
# 늘 빼는 영상: 국제대회 · 올스타 · 시범경기 · 퓨처스 · 다른 종목 (티빙은 다른 종목 하이라이트도 같은 제목 형식이다).
# 포스트시즌 단어는 여기 넣지 않는다 — 정규시즌 막바지 영상도 「플레이오프 직행 확정」처럼 쓴다(버그 B1, docs/포스트시즌.md 7장).
# 정규시즌 · 포스트시즌은 날짜(겹치지 않는다)와 단계 표기(stage_in)로 가른다
RE_EXCLUDE = re.compile(r"K-BASEBALL|대한민국|국가대표|평가전|프리미어|WBC|올스타|시범경기|연습경기|스프링캠프|퓨처스|"
                        r"농구|배구|KBL|WKBL|V-리그|축구|K리그")

# 포스트시즌 단계 표기: 「WC1_」 · 「준PO2」 · 「KS 3차전」 · 「와일드카드 결정전 1차전」 · 「한국시리즈 5차전」 (docs/포스트시즌.md 7-2)
RE_STAGE = re.compile(r"(?<![A-Za-z가-힣])(WC|와일드카드(?:\s*결정전)?|준\s*PO|준\s*플레이오프|PO|플레이오프|KS|한국시리즈)"
                      r"(?![A-Za-z])\s*_?\s*(\d)?\s*(?:차전)?")
STAGE_WORD = {"WC": "WC", "와일드카드": "WC", "준PO": "SPO", "준플레이오프": "SPO", "PO": "PO", "플레이오프": "PO",
              "KS": "KS", "한국시리즈": "KS"}


def stage_in(title: str) -> tuple[str, int | None] | None:
    """제목의 포스트시즌 단계와 n차전 (없으면 None). 「준PO」의 PO를 플레이오프로 읽지 않게 앞에서부터 하나만"""
    m = RE_STAGE.search(title)
    if not m:
        return None
    word = re.sub(r"\s+|결정전", "", m.group(1))
    return STAGE_WORD[word], (int(m.group(2)) if m.group(2) else None)


RE_YEAR = re.compile(r"(?<!\d)(20[12]\d)(?!\d)")


def stage_game(title: str, games, published_at: str) -> tuple[bool, object]:
    """(단계 표기가 있나, 그 단계 + n차전 경기 — 없으면 None). games: 그 시즌 경기(namedtuple · stage · series_game_no).
    단계 + n차전이 있으면 날짜와 상관없이 그 경기다(서스펜디드 2024 KS 1차전처럼 영상 날짜와 기록 날짜가 다를 수 있다).
    다른 해의 같은 「KS 3차전」을 잡지 않게: 게시일(KST)이 경기일 ~ 45일 뒤 안이고, 제목의 연도 · 두 팀이 그 경기와 맞아야 한다"""
    st = stage_in(title)
    if not st:
        return False, None
    stage, n = st
    if n is None:
        return True, None
    pub = (pd.Timestamp(published_at) + pd.Timedelta(hours=9)).tz_localize(None).normalize()
    years = set(RE_YEAR.findall(title))
    teams = teams_in(title, None)
    hit = [g for g in games if getattr(g, "stage", None) == stage and getattr(g, "series_game_no", None) == n
           and pd.Timestamp(g.date) <= pub <= pd.Timestamp(g.date) + pd.Timedelta(days=45)
           and (not years or g.date[:4] in years)
           and (len(teams) < 2 or teams <= {g.home_team, g.away_team})]
    return True, (hit[0] if len(hit) == 1 else None)


def teams_in(title: str, channel: str | None) -> set[str]:
    found, rest = set(), title
    for w in sorted(TEAM_WORDS, key=len, reverse=True):
        if w in rest:
            found.add(TEAM_WORDS[w])
            rest = rest.replace(w, " ")
    if len(found) <= 1 and channel in CHANNEL_TEAM:  # 구단 채널: 「4.23 vs NC」·「… 김민」처럼 자기 팀은 안 쓴다
        found.add(CHANNEL_TEAM[channel])
    return found


def date_in(title: str, published_at: str) -> str | None:
    """제목의 경기 날짜 (YYYY-MM-DD). 연도가 없으면 게시 연도 (3~11월만 정규시즌 날짜로 본다)"""
    year = int(published_at[:4])
    for rx, has_year in RE_DATES:
        for m in rx.finditer(title):
            y, mo, d = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if has_year \
                else (year, int(m.group(1)), int(m.group(2)))
            if y < 100:
                y += 2000
            if 3 <= mo <= 11 and 1 <= d <= 31:
                try:
                    return pd.Timestamp(y, mo, d).strftime("%Y-%m-%d")
                except ValueError:
                    continue
    return None


# ---------------------------------------------------------------- 챕터 영상 (설명란 「03:50 5회말 …」)
RE_CHAPTER_ROW = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(.*)$")
RE_INNING = re.compile(r"(\d{1,2})\s*회\s*(초|말)?")


def chapter_lines(description: str) -> list[tuple[int, str]]:
    """설명란 → [(시작 초, 그 줄 글)]"""
    out = []
    for row in (description or "").splitlines():
        m = RE_CHAPTER_ROW.match(row)
        if m:
            sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m.group(3) \
                else int(m.group(1)) * 60 + int(m.group(2))
            out.append((sec, m.group(4)))
    return out


def chapter_game(title: str, channel: str | None, published_at: str, lines: list[tuple[int, str]],
                 games_by_date: dict, season: int):
    """챕터 영상 → 경기 하나 (못 정하면 None). 날짜 = 제목·첫 두 줄, 없으면 게시일(KST)·전날.
    팀 = 제목의 팀 단어, 없으면 채널 팀. 더블헤더처럼 후보가 둘 이상이면 None"""
    td = date_in(title, published_at) or next((date_in(t, published_at) for _, t in lines[:2]
                                               if date_in(t, published_at)), None)
    pub = (pd.Timestamp(published_at) + pd.Timedelta(hours=9)).normalize()
    dates = [td] if td else [pub.strftime("%Y-%m-%d"), (pub - pd.Timedelta(days=1)).strftime("%Y-%m-%d")]
    if RE_EXCLUDE.search(title):
        return None
    staged, sg = stage_game(title, [g for gs in games_by_date.values() for g in gs], published_at)
    if sg is not None:
        return sg
    if not any(d.startswith(str(season)) for d in dates):
        return None
    teams = teams_in(title, channel) or ({CHANNEL_TEAM[channel]} if channel in CHANNEL_TEAM else set())
    gs = [g for d in dates for g in games_by_date.get(d, []) if teams & {g.home_team, g.away_team}]
    if len(teams) >= 2:
        gs = [g for g in gs if {g.home_team, g.away_team} <= teams] or gs
    return gs[0] if len(gs) == 1 else None


def chapter_end(lines: list[tuple[int, str]], i: int, duration_sec: int) -> int:
    """i번째 줄 구간의 끝 = 다음 줄 시각 (마지막 줄이면 +60초, 영상 길이를 넘지 않게)"""
    return lines[i + 1][0] if i + 1 < len(lines) else min(lines[i][0] + 60, duration_sec)


def dh_in(title: str) -> int | None:
    if stage_in(title):  # 「KS 2차전」의 「2차전」은 더블헤더가 아니다
        return None
    m = RE_DH.search(title)
    return int(next(g for g in m.groups() if g)) if m else None


# ---------------------------------------------------------------- 영상 목록 읽기
def load_videos(path: str | Path) -> pd.DataFrame:
    """영상 목록 → VIDEO_COLUMNS + description·playlists (분류용).
    - .json: yt_inventory.json (id·channel·title·description·published·sec·embeddable·playlists)
    - .csv : 06이 만든 재생목록 CSV (video_id·published_at·duration_sec·embeddable·title). 채널은 KBO 공식"""
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    if path.suffix == ".json":
        items = json.loads(path.read_text(encoding="utf-8"))
        v = pd.DataFrame({
            "video_id": [x["id"] for x in items],
            "title": [x["title"] for x in items],
            "channel": [x.get("channel") for x in items],
            "published_at": [x["published"] for x in items],
            "duration_sec": [x.get("sec") for x in items],
            "embeddable": [x.get("embeddable", True) for x in items],
            "description": [x.get("description") or "" for x in items],
            "playlists": [x.get("playlists") or [] for x in items],
        })
    else:
        v = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        v["channel"] = "KBO"
        v["description"] = ""
        v["playlists"] = [[] for _ in range(len(v))]
        v["embeddable"] = v["embeddable"].map(lambda s: str(s).lower() == "true")
    v["duration_sec"] = pd.to_numeric(v["duration_sec"], errors="coerce").fillna(0).astype(int)
    v["kind"] = [classify(t, d, s, p) for t, d, s, p in zip(v["title"], v["description"], v["duration_sec"], v["playlists"])]
    return v


# ---------------------------------------------------------------- 07a 영상 분류
RE_CHAPTER_LINE = re.compile(r"(?m)^\s*\d{1,2}:\d{2}")
CLIP_MAX_SEC = 600        # 장면·등판 클립은 10분 이하 (설계 7-4)
HIGHLIGHT_MIN_SEC = 300   # 경기 하이라이트는 5분 이상. 보통 12분 안팎이지만 일찍 끝난 경기는 7~10분이다(2024 25경기)
CHAPTER_MIN_SEC = 300     # 챕터 영상은 5분 이상 + 설명란 시각 3줄 이상 (구단 채널 H/L은 6분대도 있다)
# 「하이라이트」가 있어도 경기 요약이 아닌 것: 크보모먼트·KBO 모먼트 클립(제목 끝에 「야구 하이라이트」가 붙는다), 모음류
RE_NOT_GAME_HL = re.compile(r"모먼트|모음|명장면|베스트|BEST|TOP\s*\d|주간|월간")


def n_chapters(description: str) -> int:
    return len(RE_CHAPTER_LINE.findall(description or ""))


def classify(title: str, description: str, duration_sec: int, playlists: list) -> str:
    """game_highlight: 경기 전체 요약(제목 「하이라이트」, 모먼트·모음 아님, 5분 이상)
    · chapter: 설명란에 이닝별 시각이 3줄 이상인 하이라이트
    · clip: 10분 이하 짧은 영상 · other: 그 밖(긴 비하인드 등)"""
    is_hl = (("하이라이트" in title or any("H/L" in p for p in playlists)) and not RE_NOT_GAME_HL.search(title)
             and duration_sec >= HIGHLIGHT_MIN_SEC)
    if n_chapters(description) >= 3 and duration_sec >= CHAPTER_MIN_SEC:
        return "chapter"
    if is_hl:
        return "game_highlight"
    if 0 < duration_sec <= CLIP_MAX_SEC:
        return "clip"
    return "other"
