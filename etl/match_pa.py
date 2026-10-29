"""
07 --step pa : 장면 클립·챕터 홈런 줄 → 타석. 설계: 설계.md 7-5, docs/장면.md 5-2·5-4

07c 장면 클립 (10분 이하)
  제목의 팀 단어 + 날짜(없으면 게시일·전날)로 경기를 찾고, 그 경기 타자 이름이 나오면 타석마다 점수를 매긴다.
  타자마다 상위 3개 = 후보(CANDIDATE), 기준 점수를 넘은 1등 = 연결(MATCHED_TO).
  홈런 연결은 자동 확정 7조건(설계 7-5)을 모두 만족하면 auto_confirmed, 아니면 검수(review_reason).
  안타·타점 연결(2차)은 제목의 주장을 모두 만족하는 타석이 하나뿐일 때만 auto_confirmed (hit_reason).
07e 챕터 홈런·안타 줄 (설명란 「03:12 3회말 ○○○의 투런 홈런」 · 「5회말 ○○○ 2타점 적시타」)
  채널 팀 + 날짜로 경기를 정하고, 그 이닝에 맞는 그 타자의 타석이 하나면 자동 확정 (precision inning).
"""
import re
from collections import defaultdict

import pandas as pd
from baseon_rules.events import HITS

from prepare import build_games, build_pa, filter_season, read_pitches
from scenes import CHANNEL_TEAM, RE_EXCLUDE, chapter_end, chapter_game, chapter_lines, date_in, stage_game, teams_in

def scene_type_of(events: str) -> str:  # 타석 결과 → 장면 종류 (scenes.SCENE_TYPES)
    if events == "home_run":
        return "home_run"
    return "hit" if events in HITS else "batting"

MATCH_MIN = 70      # 자동 연결 기준 점수 (이름 50 + 결과 30 = 80이면 통과)
TOP_N = 3           # 타자마다 후보로 남길 타석 수

# ---------------------------------------------------------------- 제목 읽기 규칙
RE_INNING = re.compile(r"(\d{1,2})\s*회\s*(초|말)?")
RE_HR_SEQ = re.compile(r"(?<![\d,])(?<!통산 )(?<!통산)(?:시즌\s*)?(\d{1,2})\s*호(?!\s*도루)")  # 「통산 150호」의 「50호」를 읽지 않는다
RE_RBI = re.compile(r"(?<!\d)(?<!시즌 )(?<!시즌)(\d)\s*타점")  # "시즌 153타점" 같은 누적 기록은 제외

# 연결하지 않는 영상 (타석 결과 장면이 아님)
SKIP_WORDS = ["시구", "애국가", "수비", "캐치", "하.점.캐", "다이빙", "보살", "송구",
              "삼중살", "병살", "도루", "주루", "인터뷰", "세리머니", "판정", "비디오 판독"]
# 투수 영상 (지금은 연결 안 함. 나중에 투수 기준 매칭)
PITCHER_WORDS = ["K ", "KK", "탈삼진", "무실점", "이닝", "완봉", "완투", "세이브", "피칭", "투구",
                 "호투", "승리투수", "노히트", "퍼펙트"]

# 결과 단어 → events 묶음
EVENT_WORDS = {
    "home_run": ["홈런", "솔로", "투런", "스리런", "쓰리런", "그랜드슬램", "아치", "대포", "담장", "넘기", "넘어갑",
                 "선제포", "결승포", "쐐기포", "동점포", "역전포", "추격포", "만루포", "백투백"],
    "triple": ["3루타"],
    "double": ["2루타"],
    "hit": ["안타", "적시타", "결승타", "끝내기타", "싹쓸이"],
    "walk": ["볼넷", "밀어내기"],
    "sac_fly": ["희생플라이", "희플"],
}
HR_RUNS = {"솔로": 1, "투런": 2, "스리런": 3, "쓰리런": 3, "만루": 4, "그랜드슬램": 4}
SITUATIONS = ["끝내기", "역전", "동점"]


def kind_of(body: str, names: list[str]) -> str:  # 영상 종류
    has_event = has_event_word(body)
    skip = any(w in body for w in SKIP_WORDS) or re.search(r"(?<!적)시타", body)  # '적시타'의 '시타'는 제외
    if skip and not has_event:
        return "기타"
    if any(w in body for w in PITCHER_WORDS) and not names:
        return "투수"
    return "타자"


def find_names(body: str, candidates: set[str]) -> list[str]:  # 제목에 나온 타자 이름 (긴 이름부터, 겹치면 하나만)
    used, found = [False] * len(body), []
    for name in sorted(candidates, key=len, reverse=True):
        for m in re.finditer(re.escape(name), body):
            if not any(used[m.start():m.end()]):
                used[m.start():m.end()] = [True] * (m.end() - m.start())
                found.append((m.start(), name))
    return [n for _, n in sorted(found)]


def has_event_word(text: str) -> bool:
    return any(w in text for words in EVENT_WORDS.values() for w in words)


def segment_for(body: str, name: str, names: list[str]) -> str:  # 이 선수 이름부터 다음 선수 이름 전까지
    start = body.find(name)
    ends = [body.find(n, start + len(name)) for n in names if n != name]
    ends = [e for e in ends if e > start]
    seg = body[start:min(ends)] if ends else body[start:]
    # "구자욱과 디아즈의 백투백 홈런"처럼 결과가 뒤 선수 쪽에 몰려 있으면 뒤까지 본다
    if has_event_word(seg):
        return seg
    # "…시즌 45호 홈런을 그린 KIA 슈퍼스타 김도영!"처럼 이름이 하나뿐이고 결과가 이름 앞에 있으면 제목 전체
    return body if len(set(names)) <= 1 and not has_event_word(body[start:]) else body[start:]


def score_pa(pa: pd.Series, seg: str, body: str) -> tuple[int, list[str]]:  # 타석 하나의 점수와 맞은 요소
    score, why = 50, ["이름"]
    ev = pa["events"]
    # 이름 뒤에 가장 먼저 나오는 결과 단어 하나만 본다 ("홈런과 연속 안타" → 홈런)
    hits = [(seg.find(w), k) for k, words in EVENT_WORDS.items() for w in words if w in seg]
    wanted = [min(hits)[1]] if hits else []
    if wanted:
        ok = any(ev == k or (k == "hit" and ev in HITS) for k in wanted)
        score += 30 if ok else -30
        if ok:
            why.append({"home_run": "홈런", "hit": "안타", "triple": "3루타", "double": "2루타",
                        "walk": "볼넷", "sac_fly": "희생플라이"}[next(k for k in wanted if ev == k or (k == "hit" and ev in HITS))])
    elif ("타점" in seg or "득점" in seg) and pa["runs_scored"] > 0:
        score += 20
        why.append("타점")
    # 적시타·결승타·싹쓸이는 점수가 난 타석이어야 한다
    if any(w in seg for w in ["적시타", "결승타", "싹쓸이", "타점"]) and ev != "home_run":
        if pa["runs_scored"] > 0:
            score += 10
            why.append("득점")
        else:
            score -= 10
    m = re.search(r"([1-4])\s*점\s*홈런", seg)  # "3점 홈런"
    hr_words = dict(HR_RUNS, **({m.group(0): int(m.group(1))} if m else {}))
    for word, runs in hr_words.items():
        if word in seg and ev == "home_run":
            if pa["runs_scored"] == runs:
                score += 10
                why.append(word)
            else:
                score -= 20
            break
    m = RE_RBI.search(seg)
    if m and pa["runs_scored"] == int(m.group(1)):
        score += 10
        why.append(f"{m.group(1)}타점")
    for s in SITUATIONS:
        if s in seg:
            if pa["situation"] == s:
                score += 30 if s == "끝내기" else 10  # 끝내기 타석은 경기에 하나뿐이라 강한 단서
                why.append(s)
            break
    m = RE_INNING.search(body)
    if m:
        if pa["inning"] == int(m.group(1)) and (not m.group(2) or pa["inning_half"] == m.group(2)):
            score += 10
            why.append(f"{m.group(1)}회")
    m = RE_HR_SEQ.search(seg)
    if m and ev == "home_run" and hr_no(pa) == int(m.group(1)):
        score += 10
        why.append(f"{m.group(1)}호")
    if isinstance(pa["pitcher_name"], str) and pa["pitcher_name"] in body:
        score += 10
        why.append("투수")
    return score, why


# ---------------------------------------------------------------- 홈런 자동 확정 (설계 7-5)
GAP_MIN = 20  # 조건 7: 1·2등 점수 차
EXCLUDE = re.compile(r"인터뷰|터뷰|후토크|덕아웃캠|비하인드|직캠|Mic'd|마이크|굿즈|기념\s*유니폼|유니폼\s*(?:&|실물|출시|공개|판매)|"
                     r"애프터|브이로그|TALK|톡\]")  # 조건 6 — 장면 아님 → 연결하지 않는다 (S15)
COMPILE = re.compile(r"모음")  # 한 경기(제목 날짜) 모음은 연타석처럼, 여러 경기 모음은 연결하지 않는다 (S15)
ROBBED = re.compile(r"(안타|홈런|장타|[23]루타)[을를]?\s*(지우|지운|지워|훔치|훔친|삭제|막아|막는|뺏|빼앗|도둑|낚아|잡아|건져|가로채)"
                    r"|(안타|홈런|장타)성\s*타구")  # 「안타를 지우는 박주홍」 · 「안타성 타구를 낚아채는」 = 수비 장면
MULTI = re.compile(r"멀티\s*홈런|멀티포|연타석|백투백")  # 조건 4 예외: 그날 홈런 여럿을 한 영상에
HR_WORDS = EVENT_WORDS["home_run"]
# 그날 홈런이 여럿일 때 어느 홈런인지 가려 주는 단서 (score_pa의 reasons에 맞은 것만 들어간다): n호 · n회 · n타점 · 솔로~만루
DISTINCT = re.compile(r"\d+호|\d+회|\d타점|솔로|투런|스리런|쓰리런|만루|그랜드슬램|끝내기")


def hr_no(p) -> int | None:
    """홈런 n호: 정규시즌은 hr_seq(시즌 n호), 포스트시즌은 post_hr_seq(그 해 포스트시즌 n호, docs/포스트시즌.md PS5)"""
    v = p["hr_seq"] if p.get("game_type", "regular") == "regular" else p.get("post_hr_seq")
    return None if pd.isna(v) else int(v)


def hr_mismatch(p, seg: str, title: str, game_rbi: int | None = None) -> list[str]:
    """오매칭 기계 검사 — 제목의 n호·이닝·끝내기·타점이 그 타석과 어긋나면 검수 (설계 7-5).
    n타점은 그 타석 타점이나 그 경기 이 타자 총 타점(「5타점 멀티 홈런」) 중 하나와 맞으면 된다 (S14)"""
    bad = []
    m = RE_HR_SEQ.search(seg)
    if m and hr_no(p) != int(m.group(1)):
        bad.append(f"{m.group(1)}호≠{hr_no(p)}")
    m = RE_INNING.search(seg) or RE_INNING.search(title)
    if m and (p["inning"] != int(m.group(1)) or (m.group(2) and p["inning_half"] != m.group(2))):
        bad.append(f"{m.group(0)}≠{p['inning']}회{p['inning_half']}")
    if "끝내기" in seg and p["situation"] != "끝내기":
        bad.append("끝내기")
    m = re.search(r"([1-4])\s*점\s*홈런", seg)
    words = dict(HR_RUNS, **({m.group(0): int(m.group(1))} if m else {}))
    for w, runs in words.items():
        if w in seg and p["runs_scored"] != runs:
            bad.append(f"{w}≠{p['runs_scored']}점")
            break
    m = RE_RBI.search(seg)
    if m and int(m.group(1)) not in (p["runs_scored"], game_rbi):
        bad.append(f"{m.group(1)}타점≠{p['runs_scored']}")
    return bad


# ---------------------------------------------------------------- 안타·타점 자동 확정 (장면.md 5-2, 2차)
# 제목이 주장하는 것(결과 · 적시 · n타점 · 끝내기·역전·동점 · n회)을 모두 만족하는 타석이 딱 하나일 때만 확정한다.
# 한 경기에 안타가 여럿인 일이 흔해서, 홈런처럼 점수 차(GAP)만으로는 고르지 않는다.
HIT_KINDS = {"hit": {"single", "double", "triple"}, "double": {"double"}, "triple": {"triple"},
             "sac_fly": {"sac_fly"}, "walk": {"walk"}}
HIT_SUMMARY = re.compile(r"\d\s*안타|멀티\s*히트|맹타|맹활약|불방망이")  # 한 경기 여러 타석을 묶은 영상
RUN_WORDS = ("적시", "결승타", "싹쓸이", "타점", "밀어내기")


def claimed_kind(seg: str) -> str | None:  # 이 타자 구간에서 가장 먼저 나오는 결과 단어의 종류 (score_pa와 같은 규칙)
    found = [(seg.find(w), k) for k, words in EVENT_WORDS.items() for w in words if w in seg]
    return min(found)[1] if found else None


def fits_claim(q, kind: str, seg: str, title: str) -> bool:
    """타석 q가 제목의 주장을 모두 만족하나"""
    if q["events"] not in HIT_KINDS[kind]:
        return False
    if any(w in seg for w in RUN_WORDS) and q["runs_scored"] <= 0:
        return False
    rbis = [int(x) for x in RE_RBI.findall(seg)]  # 「6타점 경기! … 2타점 적시타」 → 하나라도 맞으면
    if rbis and q["runs_scored"] not in rbis:
        return False
    for s in SITUATIONS:
        # 제목의 「역전」은 지고 있던 팀이 그 이닝에 앞서 나간 것 — 이 타석 직전에 동점이었어도(리드) 「역전 적시타」라 쓴다
        if s in seg and not (q["situation"] == s or (s == "역전" and q["situation"] == "리드")):
            return False
    m = RE_INNING.search(seg) or RE_INNING.search(title)
    if m and (q["inning"] != int(m.group(1)) or (m.group(2) and q["inning_half"] != m.group(2))):
        return False
    return True


def hit_reason(p, pool: pd.DataFrame, seg: str, title: str) -> str | None:
    """안타·타점 연결의 검수 이유 (None = 자동 확정). pool = 이 타자가 그 기간에 친 타석 전부"""
    kind = claimed_kind(seg)
    if kind not in HIT_KINDS:
        return "not_hr"  # 결과 단어가 없거나(「타점」만) 홈런 단어 → 사람이
    if HIT_SUMMARY.search(seg):
        return "multi_hit"
    ok = [q["pa_id"] for _, q in pool.iterrows() if fits_claim(q, kind, seg, title)]
    if p["pa_id"] not in ok:
        return "claim_mismatch"
    return "multi_hit" if len(ok) > 1 else None


PUB_SAME_DAY_HOUR = 14  # 이 시각(KST) 전에 올린 영상은 그날 경기 전이다 → 전날까지의 홈런만 본다
PUB_MAX_LAG = 1         # 올린 날 − 홈런 날이 이 일수 안일 때만


def latest_day_before(dates: list[str], published_at: str) -> str | None:
    """올린 시각 직전의 날짜(그 타자가 그 결과를 낸 날 중). 오후 2시 전에 올렸으면 전날까지, 하루 안일 때만 (S12)"""
    pub = (pd.Timestamp(published_at) + pd.Timedelta(hours=9)).tz_localize(None)
    cutoff = (pub.normalize() + pd.Timedelta(days=0 if pub.hour < PUB_SAME_DAY_HOUR else 1)).strftime("%Y-%m-%d")
    prior = [d for d in dates if d < cutoff]
    if not prior or (pub.normalize() - pd.Timestamp(max(prior))).days > PUB_MAX_LAG:
        return None
    return max(prior)


def latest_hr_before(hrs: list[tuple[str, str]], published_at: str) -> str | None:
    """올린 시각 규칙 (docs/장면.md S12): 올린 시각 직전에 친 그 타자의 홈런. 하루 안이고 그날 홈런이 하나일 때만.
    hrs = 그 타자 홈런 [(pa_id, 날짜)] 날짜 · 타석 순. 날짜가 적힌 영상 2,008개로 잰 정확도 99.7% (사흘 안 홈런 여럿인 경우 99.1%)"""
    pub = (pd.Timestamp(published_at) + pd.Timedelta(hours=9)).tz_localize(None)
    cutoff = (pub.normalize() + pd.Timedelta(days=0 if pub.hour < PUB_SAME_DAY_HOUR else 1)).strftime("%Y-%m-%d")
    prior = [(pid, d) for pid, d in hrs if d < cutoff]
    if not prior:
        return None
    pid, d = prior[-1]
    if (pub.normalize() - pd.Timestamp(d)).days > PUB_MAX_LAG or sum(1 for _, x in prior if x == d) > 1:
        return None
    return pid


def game_level_hit(pool: pd.DataFrame, seg: str, title: str, published_at: str | None = None) -> pd.Series | None:
    """멀티 히트 영상 → 경기 단위로 붙일 타석 (docs/장면.md S13). 후보 안타가 모두 한 경기에 있을 때만, 그 경기 이 타자의 첫 안타.
    묶음(「3안타 맹타」)은 그 기간 안타 전부, 아니면(「복귀 첫 타석부터 안타」 · 적시타 둘) 주장에 맞는 타석이 후보"""
    if HIT_SUMMARY.search(seg):
        fits = pool[pool["events"].isin(HITS)]
    else:
        kind = claimed_kind(seg)
        fits = pool[[fits_claim(q, kind, seg, title) for _, q in pool.iterrows()]] if kind in HIT_KINDS else pool.iloc[:0]
    if not fits.empty and fits["game_pk"].nunique() > 1 and published_at:  # 날짜 없는 제목: 올린 시각 직전 경기 (S14)
        day = latest_day_before(sorted(fits["date"].unique()), published_at)
        fits = fits[fits["date"].eq(day)]
    if fits.empty or fits["game_pk"].nunique() != 1:
        return None
    rep = fits[~fits["events"].eq("home_run")].sort_values("at_bat_number")
    return rep.iloc[0] if len(rep) else None


def match_pa(videos: pd.DataFrame, season: int) -> tuple[list, pd.DataFrame, dict]:
    """07c 장면 클립 + 07e 챕터 홈런 줄 → 타석. 반환: 연결 줄, 못 한 영상, 영상별 경기 날짜(적재할 영상)"""
    df = filter_season(read_pitches(), season)
    games = build_games(df)
    pa = build_pa(df, games)
    pa["bat_name"] = pa["batter_name"]
    by_game = {k: g for k, g in pa.groupby("game_pk")}
    games_by_date: dict = defaultdict(list)
    for g in games.itertuples(index=False):
        games_by_date[g.date].append(g)
    hr_day = pa[pa["events"].eq("home_run")].groupby(["date", "batter"]).size().to_dict()  # 조건 4
    game_rbi = pa.groupby(["game_pk", "batter"])["runs_scored"].sum().to_dict()  # 「5타점 멀티 홈런」 (S14)
    ev_dates = {(b, k): sorted(set(x["date"])) for k, evs in (("hr", {"home_run"}), ("hit", HITS))
                for b, x in pa[pa["events"].isin(evs)].groupby("batter")}
    hr_names = pa[pa["events"].eq("home_run")].groupby(["bat_name", "date"])["batter"].apply(set).to_dict()  # 동명이인 (S15)

    def anchor_of(p) -> pd.Series:
        """경기 단위로 붙일 타석: 그 경기 이 타자의 첫 안타(홈런 제외), 없으면 첫 타석 (S13 · S15)"""
        g = by_game[p["game_pk"]]
        mine = g[g["batter"].eq(p["batter"])].sort_values("at_bat_number")
        hit = mine[mine["events"].isin(HITS - {"home_run"})]
        return (hit if len(hit) else mine).iloc[0]

    def game_known(p, kind: str, td, published_at) -> bool:
        """이 영상이 그 타자의 「그 경기」 영상인 것이 확실한가: 제목 날짜 또는 올린 시각 직전 날 + 그날 이 타자 경기가 하나"""
        day = td or latest_day_before(ev_dates.get((p["batter"], kind), []), published_at)
        if day != p["date"]:
            return False
        return pa_by_day.get((day, p["batter"]), pa.iloc[:0])["game_pk"].nunique() == 1
    hrs_of = {b: list(zip(x["pa_id"], x["date"])) for b, x in
              pa[pa["events"].eq("home_run")].sort_values(["date", "at_bat_number"]).groupby("batter")}  # 올린 시각 규칙
    season_homonyms = pa.groupby("bat_name")["batter"].nunique().to_dict()  # 이름 → 그 시즌 선수 수
    pa_by_day = {k: g for k, g in pa.groupby(["date", "batter"])}  # 날짜 없는 안타 제목: 3일 안 타석
    game_of_video: dict = {}
    game_list = list(games.itertuples(index=False))
    links, skipped, stats = [], [], defaultdict(int)

    # ---- 07c 장면 클립
    for v in videos[videos["kind"].eq("clip")].itertuples():
        t = v.title
        base = {"video_id": v.video_id, "title": t}
        if RE_EXCLUDE.search(t) or not has_event_word(t) or ROBBED.search(t):
            continue
        _, sg = stage_game(t, game_list, v.published_at)  # 포스트시즌 「준PO2」 → 날짜와 상관없이 그 경기 (날짜가 있는 것과 같게 본다)
        td = sg.date if sg is not None else date_in(t, v.published_at)  # 조건 2: 제목에 날짜
        pub = (pd.Timestamp(v.published_at) + pd.Timedelta(hours=9)).normalize()
        days = lambda n: [(pub - pd.Timedelta(days=k)).strftime("%Y-%m-%d") for k in range(n)]  # noqa: E731
        dates = [td] if td else days(2)
        if not any(d.startswith(str(season)) for d in dates):
            continue
        teams = teams_in(t, v.channel)
        # 팀 단어가 없으면(KBO 채널 쇼츠 「디아즈의 … 만루 홈런」) 그 날짜 경기 전부에서 이름을 찾는다
        gs = [sg] if sg is not None else [
            g for d in dates for g in games_by_date.get(d, [])
            if not teams or (teams <= {g.home_team, g.away_team} if len(teams) >= 2 else teams & {g.home_team, g.away_team})]
        if not gs:
            skipped.append({**base, "reason": "경기 없음"})
            continue
        gpa = pd.concat([by_game[g.game_pk] for g in gs if g.game_pk in by_game])
        names = find_names(t, set(gpa["bat_name"].dropna()))
        alias = {n: n for n in names}  # 제목에 나온 말 → 타자 이름
        if not names and v.channel in CHANNEL_TEAM:
            # 구단 채널은 이름만 쓰기도 한다(NC 「휘집」·키움 「치홍이 형」) → 그 팀 타자의 이름(성 제외)이 하나로 정해질 때만
            mine = gpa[gpa["bat_team"].eq(CHANNEL_TEAM[v.channel])]["bat_name"].dropna().unique()
            given: dict = defaultdict(set)
            for full in mine:
                if len(full) == 3:
                    given[full[1:]].add(full)
            tokens = find_names(t, {g for g, fulls in given.items() if len(fulls) == 1})
            alias = {tok: next(iter(given[tok])) for tok in tokens}
            names = tokens
        kind = kind_of(t, names)
        if kind != "타자":
            skipped.append({**base, "reason": f"{kind} 영상"})
            continue
        if not names:
            skipped.append({**base, "reason": "타자 이름 없음"})
            continue

        for name in names:
            seg = segment_for(t, name, names)
            cand = gpa[gpa["bat_name"] == alias[name]]
            homonym = cand["batter"].nunique() > 1  # 같은 날 같은 이름 타자 둘 (김민혁·이재원)
            scored = sorted(((*score_pa(p, seg, t), p) for _, p in cand.iterrows()),
                            key=lambda x: (-x[0], x[2]["at_bat_number"]))
            multi = bool(MULTI.search(seg))
            for rank, (score, why, p) in enumerate(scored[:TOP_N], 1):
                gap = score - scored[1][0] if len(scored) > 1 and rank == 1 else None
                matched = score >= MATCH_MIN and (rank == 1 or (multi and p["events"] == "home_run"))
                link = {"target_kind": "pa", "target_id": p["pa_id"], "video_id": v.video_id,
                        "score": score, "rank": rank, "reasons": "+".join(why)}
                links.append({**link, "rel": "candidate"})
                game_of_video[v.video_id] = p["game_pk"]
                if not matched:
                    continue
                st = scene_type_of(p["events"])
                reason = None
                precision = "scene"
                if st != "home_run":
                    # 안타·타점 (2차): 날짜가 있으면 그 경기, 없으면 게시일 포함 3일 안의 이 타자 타석 중에서 주장에 맞는 것이 하나뿐이어야
                    pool = cand[cand["batter"].eq(p["batter"])] if td else \
                        pd.concat([pa_by_day.get((d, p["batter"]), pa.iloc[:0]) for d in days(3)])
                    reason = hit_reason(p, pool, seg, t)
                    if "끝내기" in seg and p["situation"] == "끝내기":  # 끝내기는 한 경기에 하나 → 볼넷 · 희생플라이 · 사구도 그 타석 (S15)
                        reason = None
                    if reason in ("multi_hit", "claim_mismatch") and COMPILE.search(t) and td:
                        reason = "multi_hit"  # 한 경기 모음 → 경기 단위
                    if reason == "multi_hit":
                        rep = game_level_hit(pool, seg, t, None if td else v.published_at)
                        if rep is not None:  # 한 경기 영상 → 타석이 아니라 「그 경기 이 선수 영상」으로 (처음부터 재생)
                            reason, precision, st = None, "game", scene_type_of(rep["events"])
                            link["target_id"] = rep["pa_id"]
                            link["reasons"] += "+경기 단위"
                    if reason == "claim_mismatch" and len(names) <= 3 and p["events"] in HITS \
                            and game_known(p, "hit", td, v.published_at):
                        # 「구본혁&박해민이 만들어 낸 동점타와 역전 적시타」: 어느 타석인지는 몰라도 그 경기 이 선수 영상 (S15)
                        rep = anchor_of(p)
                        reason, precision, st = None, "game", scene_type_of(rep["events"])
                        link["target_id"] = rep["pa_id"]
                        link["reasons"] += "+경기 단위"
                    if reason is None:
                        if not teams and season_homonyms.get(alias[name], 1) > 1:
                            reason = "ambiguous"
                        elif EXCLUDE.search(t) or (COMPILE.search(t) and not td):
                            reason = "excluded_words"
                        elif homonym:
                            reason = "ambiguous"
                else:
                    bad = hr_mismatch(p, seg, t, game_rbi.get((p["game_pk"], p["batter"])))
                    # 날짜 없는 제목: 게시일 포함 3일 안에 그 타자 홈런이 딱 하나일 때만 (장면.md S10).
                    # 제목의 「시즌 n호」가 그 타석과 맞으면 날짜처럼 하나로 정해진다 (김도영 44 · 45호 연이틀)
                    window_hr = sum(hr_day.get((d, p["batter"]), 0) for d in days(3))
                    m_seq = RE_HR_SEQ.search(seg)
                    seq_ok = bool(m_seq) and hr_no(p) == int(m_seq.group(1))  # 「시즌 20호」가 그 타석과 맞으면 어느 홈런인지 정해진다
                    if seq_ok:
                        window_hr = 1
                    hrs = hrs_of.get(p["batter"], [])
                    pub_ok = not td and latest_hr_before(hrs, v.published_at) == p["pa_id"]  # 올린 시각 규칙 (S12)
                    if COMPILE.search(t) and td:  # 「블레인과 김주원의 홈런포 모음 | 9.9」: 한 경기 모음은 연타석처럼 (S15)
                        multi = True
                    if not td and multi and window_hr != 1:  # 날짜 없는 연타석 · 멀티 홈런: 올린 시각 직전 홈런 날의 홈런 전부 (S14)
                        day = latest_day_before([d for _, d in hrs], v.published_at)
                        if day != p["date"]:
                            continue  # 다른 날 홈런 후보는 연결하지 않는다
                        window_hr = 1
                    if not any(w in seg for w in HR_WORDS):
                        reason = "not_hr_title"  # 제목은 「안타」인데 그 타석이 홈런 (score_pa의 안타는 홈런을 포함)
                    elif not td and window_hr != 1 and not pub_ok:
                        reason = "no_title_date"  # 사흘 안 홈런이 여럿이고, 올린 시각 직전 홈런도 이 타석이 아니다
                    elif not teams and season_homonyms.get(alias[name], 1) > 1 and \
                            len(set().union(*[hr_names.get((alias[name], d), set()) for d in ([td] if td else days(3))])) != 1:
                        reason = "ambiguous"  # 팀 없는 제목 + 같은 이름 선수 여럿, 그 기간 그 이름으로 홈런 친 선수도 여럿 (S15)
                    elif EXCLUDE.search(t) or (COMPILE.search(t) and not td):
                        reason = "excluded_words"
                    elif homonym:
                        reason = "ambiguous"
                    elif bad:
                        reason = "claim_mismatch"
                        link["reasons"] += " | " + "; ".join(bad)
                    elif hr_day.get((p["date"], p["batter"]), 0) > 1 and not multi and not seq_ok \
                            and not (DISTINCT.search(link["reasons"]) and (gap or 0) >= 10):
                        reason = "multi_hr"  # 그날 홈런 여럿인데 제목에 어느 홈런인지 가려 줄 단서가 없음
                    elif gap is not None and gap < GAP_MIN and not multi and not seq_ok and not pub_ok:
                        reason = "low_gap"
                    fallback = reason in ("multi_hr", "no_title_date") or (reason == "not_hr_title" and HIT_SUMMARY.search(seg))
                    if fallback and not homonym and game_known(p, "hr" if reason != "not_hr_title" else "hit", td, v.published_at):
                        # 어느 홈런인지 모르지만 그 경기 이 선수 영상인 것은 확실 → 경기 단위 (S15). 홈런 장면 수에는 넣지 않는다
                        rep = anchor_of(p)
                        reason, precision, st = None, "game", "batting"
                        link["target_id"] = rep["pa_id"]
                        link["reasons"] += "+경기 단위"
                if reason == "excluded_words":  # 인터뷰 · 직캠 · 여러 경기 모음 = 장면 아님 → 연결하지 않는다 (S15)
                    stats[(st, "excluded")] += 1
                    continue
                status = "auto_confirmed" if reason is None else "pending"
                stats[(st, status)] += 1
                links.append({**link, "rel": "matched", "scene_type": st, "precision": precision, "start_sec": 0,
                              "end_sec": v.duration_sec, "status": status, "origin": "auto", "review_reason": reason})

    # ---- 07e 챕터 홈런 줄
    for v in videos[videos["kind"].eq("chapter")].itertuples():
        lines = chapter_lines(v.description)
        g = chapter_game(v.title, v.channel, v.published_at, lines, games_by_date, season)
        if g is None or g.game_pk not in by_game:
            continue
        gpa = by_game[g.game_pk]
        roster = set(gpa["bat_name"].dropna())
        for i, (sec, text) in enumerate(lines):
            im = RE_INNING.search(text)
            if not im:
                continue
            if not any(w in text for w in HR_WORDS):
                # 안타·타점 줄 (2차): 「5회말 ○○○ 2타점 적시타」 → 그 이닝에 주장을 모두 만족하는 그 타자 타석이 하나면 확정
                for name in find_names(text, roster):
                    seg = segment_for(text, name, find_names(text, roster))
                    kind = claimed_kind(seg)
                    if kind not in HIT_KINDS or HIT_SUMMARY.search(seg):
                        continue
                    c = gpa[gpa["bat_name"].eq(name)]
                    c = c[[fits_claim(q, kind, seg, text) for _, q in c.iterrows()]]
                    for _, p in c.iterrows():
                        status = "auto_confirmed" if len(c) == 1 else "pending"
                        stats[("hit_chapter", status)] += 1
                        game_of_video[v.video_id] = p["game_pk"]
                        links.append({"rel": "matched", "target_kind": "pa", "target_id": p["pa_id"],
                                      "video_id": v.video_id, "scene_type": scene_type_of(p["events"]), "precision": "inning",
                                      "start_sec": sec, "end_sec": chapter_end(lines, i, v.duration_sec), "status": status,
                                      "origin": "auto", "review_reason": None if len(c) == 1 else "ambiguous",
                                      "score": 80, "rank": None, "reasons": f"챕터+{im.group(0)}+{kind}"})
                continue
            found = find_names(text, roster)
            for name in found:
                seg = segment_for(text, name, found)
                if not any(w in seg for w in HR_WORDS):
                    continue  # 홈런이 이 타자 쪽 말이 아님
                c = gpa[(gpa["bat_name"] == name) & (gpa["inning"] == int(im.group(1))) & gpa["events"].eq("home_run")]
                if im.group(2):
                    c = c[c["inning_half"] == im.group(2)]
                for _, p in c.iterrows():
                    status = "auto_confirmed" if len(c) == 1 else "pending"
                    stats[("home_run_chapter", status)] += 1
                    game_of_video[v.video_id] = p["game_pk"]
                    links.append({"rel": "matched", "target_kind": "pa", "target_id": p["pa_id"],
                                  "video_id": v.video_id, "scene_type": "home_run", "precision": "inning",
                                  "start_sec": sec, "end_sec": chapter_end(lines, i, v.duration_sec), "status": status,
                                  "origin": "auto", "review_reason": None if len(c) == 1 else "ambiguous",
                                  "score": 80, "rank": None, "reasons": f"챕터+{im.group(0)}+홈런"})

    # (대상, 영상, 관계) 쌍마다 하나로 (같은 영상에 이름이 두 번 나오면 겹친다) → 연결 순서 rank
    lk = pd.DataFrame(links)
    if len(lk):
        lk["_s"] = lk["status"].map({"auto_confirmed": 0, "pending": 1}).fillna(2)
        lk["_p"] = lk["precision"].map({"scene": 0, "inning": 1}).fillna(2)
        lk = lk.sort_values(["rel", "target_id", "video_id", "_s", "score"], ascending=[True, True, True, True, False]) \
            .drop_duplicates(["rel", "target_id", "video_id"])
        m = lk["rel"].eq("matched")
        lk.loc[m, "rank"] = lk[m].sort_values(["target_id", "_s", "_p", "start_sec"]).groupby("target_id").cumcount() + 1
        links = lk.drop(columns=["_s", "_p"]).to_dict("records")

    miss = pd.DataFrame(skipped)
    hr_total = int(pa["events"].eq("home_run").sum())
    hr_conf = lk[(lk["rel"] == "matched") & lk["scene_type"].eq("home_run") & lk["status"].eq("auto_confirmed")]["target_id"].nunique() if len(lk) else 0
    hr_any = lk[(lk["rel"] == "matched") & lk["scene_type"].eq("home_run")]["target_id"].nunique() if len(lk) else 0
    print(f"\n{season} 홈런 {hr_total}개 중 자동 확정 장면 {hr_conf}개 ({hr_conf / max(hr_total, 1):.1%}), 검수 포함 {hr_any}개 ({hr_any / max(hr_total, 1):.1%})")
    hit_total = int(pa["events"].isin(HIT_KINDS["hit"]).sum())
    hit_m = lk[(lk["rel"] == "matched") & lk["scene_type"].eq("hit")] if len(lk) else lk
    hit_conf = hit_m[hit_m["status"].eq("auto_confirmed")]["target_id"].nunique() if len(lk) else 0
    print(f"{season} 안타(1·2·3루타) {hit_total}개 중 자동 확정 장면 {hit_conf}개 ({hit_conf / max(hit_total, 1):.1%}), "
          f"검수 포함 {hit_m['target_id'].nunique() if len(lk) else 0}개")
    print("연결 종류·상태:", dict(stats))
    if len(lk):
        print("검수 이유:", lk[lk["rel"].eq("matched")]["review_reason"].value_counts().to_dict())
    print("연결 못 한 이유:", miss["reason"].value_counts().to_dict() if len(miss) else {})
    date_of = dict(zip(games["game_pk"], games["date"]))  # 경기 ID에서 자르지 않는다 (포스트시즌 ID 앞자리는 4444·3333… — B3)
    game_date = {vid: date_of[gp] for vid, gp in game_of_video.items()}
    return links, miss, game_date


