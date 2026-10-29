"""
parquet(투구 한 줄 = 공 하나)를 스키마의 노드·관계 모양으로 가공한다.
DB에는 아무것도 쓰지 않는다. 적재 스크립트(01, 02)가 이 파일의 함수를 불러 쓴다.

직접 실행하면 가공 결과만 요약해서 보여준다(드라이 런):
    python etl/prepare.py
"""
import numpy as np
import pandas as pd
from baseon_rules.events import HITS, NOT_AB

from common import KBO_PBP_DIR

COLUMNS = [
    "game_pk", "game_date", "home_team", "away_team", "inning", "inning_topbot",
    "at_bat_number", "pitch_number", "batter", "pitcher", "batter_name", "pitcher_name",
    "balls", "strikes", "home_score", "away_score", "post_home_score", "post_away_score",
    "on_1b", "on_2b", "on_3b", "events", "runs_scored", "pitch_result",
    "pitch_type", "_naver_pitch_name", "release_speed_kmh",
    "outs_when_up", "post_outs", "post_on_1b", "post_on_2b", "post_on_3b",  # 투수 아웃·실점 귀속용
    "plate_x", "plate_z", "sz_top", "sz_bot",  # 투수 유인(체이스율): 투구 위치 ft (docs/투수.md 3-3)
]
STR_COLS = [
    "game_pk", "game_date", "home_team", "away_team", "inning_topbot", "batter", "pitcher",
    "batter_name", "pitcher_name", "on_1b", "on_2b", "on_3b", "events", "pitch_result",
    "pitch_type", "_naver_pitch_name", "post_on_1b", "post_on_2b", "post_on_3b",
]

TEAM_NAMES = {
    "HT": "KIA", "OB": "두산", "LG": "LG", "SS": "삼성", "LT": "롯데",
    "SK": "SSG", "HH": "한화", "WO": "키움", "KT": "KT", "NC": "NC",
}

SEASONS = (2024, 2025, 2026)  # 사용하는 시즌. 2023은 쓰지 않음 (원본 파일은 그대로 두고 읽을 때 뺀다)

# 포스트시즌 (docs/포스트시즌.md 4장): kbo_pbp_<시즌>_post.parquet에 단계·n차전 열이 더 있다.
# 모든 투구 줄에 game_type(regular · postseason)을 붙이고, 시즌 기록 · 백분위 · 비교 대상은 정규시즌만으로 계산한다 (PS1)
POST_EXTRA = ["round_code", "series_game_no"]
STAGE = {"kbo_ps_wd": "WC", "kbo_ps_sp": "SPO", "kbo_ps_po": "PO", "kbo_ps_ks": "KS"}

QUALIFY_RATE = 3.1   # 규정타석 = 팀 경기 수 × 3.1
QUALIFY_SHARE = 0.5  # 그중 50% 이상이면 백분위 대상
MONTH_MIN_PA = 20    # 꾸준함: 20타석 이상인 달만 (설계 D3)
MONTH_MIN_COUNT = 3  # 그런 달이 3개 이상이어야 계산
MONTH_MERGE = {3: 4, 10: 9}  # 개막 주간뿐인 3월은 4월에, 시즌 끝 10월은 9월에 합친다 (설계 D3)


# ---------------------------------------------------------------- 읽기
def read_pitches(data_dir=KBO_PBP_DIR) -> pd.DataFrame:
    """시즌별 파일(kbo_pbp_<시즌>.parquet)에서 사용 시즌만 읽는다. 2023 파일은 열지 않는다."""
    paths = [data_dir / f"kbo_pbp_{y}.parquet" for y in SEASONS]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise SystemExit(f"원본 파일이 없습니다: {data_dir} 의 {', '.join(missing)}\n"
                         "python scripts/get_data.py 로 받거나 .env의 KBO_PBP_DIR을 확인하세요.")
    reg = pd.concat([pd.read_parquet(p, columns=COLUMNS) for p in paths], ignore_index=True)
    reg = reg.assign(game_type="regular", round_code=None, series_game_no=pd.NA)
    post_paths = [data_dir / f"kbo_pbp_{y}_post.parquet" for y in SEASONS]
    post = [pd.read_parquet(p, columns=COLUMNS + POST_EXTRA).assign(game_type="postseason") for p in post_paths if p.exists()]
    df = pd.concat([reg, *post], ignore_index=True)
    df["series_game_no"] = df["series_game_no"].astype("Int64")
    df = df[df["game_date"].astype("string").str[:4].isin([str(y) for y in SEASONS])]
    return clean(df)


def regular(frame: pd.DataFrame) -> pd.DataFrame:
    """정규시즌 줄만 (시즌 기록 · 백분위 · 비교 대상 · 홈런 n호는 정규시즌만 — PS1)"""
    return frame[frame["game_type"].eq("regular")]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in STR_COLS:
        s = df[c].astype("string").str.strip()
        df[c] = s.mask(s == "")  # 빈 문자열은 값 없음으로
    df["_naver_pitch_name"] = df["_naver_pitch_name"].replace("싱커", "투심")
    return df.sort_values(["game_pk", "at_bat_number", "pitch_number"]).reset_index(drop=True)


def sample_games(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """빠른 시험용: 가장 최근 n경기만 남긴다."""
    keep = (
        df[["game_pk", "game_date"]].drop_duplicates()
        .sort_values(["game_date", "game_pk"]).tail(n)["game_pk"]
    )
    return df[df["game_pk"].isin(set(keep))].reset_index(drop=True)


# ---------------------------------------------------------------- 경기
def filter_season(df: pd.DataFrame, season: int) -> pd.DataFrame:
    """한 시즌의 투구만 남긴다. 시즌 단위로 자르기 때문에 홈런 순번·백분위 계산에 영향이 없다."""
    if season not in SEASONS:
        raise SystemExit(f"{season} 시즌은 사용하지 않습니다. 사용 시즌: {SEASONS}")
    return df[df["game_date"].str[:4] == str(season)].reset_index(drop=True)


def build_games(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("game_pk", sort=False)
    games = g.agg(
        date=("game_date", "first"),
        home_team=("home_team", "first"),
        away_team=("away_team", "first"),
        home_final=("post_home_score", "last"),  # 경기 마지막 공의 타석 후 점수
        away_final=("post_away_score", "last"),
        innings=("inning", "max"),
        last_ab=("at_bat_number", "max"),
        game_type=("game_type", "first"),
        round_code=("round_code", "first"),
        series_game_no=("series_game_no", "first"),
    ).reset_index()
    games["stage"] = games["round_code"].map(STAGE)  # 정규시즌은 NaN → null
    games["season"] = games["date"].str[:4].astype(int)
    games["dh_no"] = games["game_pk"].str[12].astype(int)  # 13번째 글자: 0 일반, 1·2 더블헤더
    return games


def build_teams(games: pd.DataFrame) -> pd.DataFrame:
    codes = sorted(set(games["home_team"]) | set(games["away_team"]))
    return pd.DataFrame({"team_id": codes, "name": [TEAM_NAMES.get(c, c) for c in codes]})


# ---------------------------------------------------------------- 타석
def build_pa(df: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    keys = ["game_pk", "at_bat_number"]
    grp = df.groupby(keys, sort=False)
    pa = grp.tail(1).merge(grp.size().rename("pitch_count").reset_index(), on=keys)

    # 결과가 빈 타석(이닝 도중 경기 종료, 견제사로 이닝 종료 등)은 제외
    pa = pa[pa["events"].notna()].copy()

    pa["pa_id"] = pa["game_pk"] + "_" + pa["at_bat_number"].astype(int).astype(str)
    pa["date"] = pa["game_date"]
    pa["season"] = pa["game_date"].str[:4].astype(int)
    top = pa["inning_topbot"].eq("top")
    pa["inning_half"] = np.where(top, "초", "말")
    pa["bat_team"] = np.where(top, pa["away_team"], pa["home_team"])
    pa["pit_team"] = np.where(top, pa["home_team"], pa["away_team"])

    for base in ["1b", "2b", "3b"]:
        pa[f"on_{base}"] = pa[f"on_{base}"].notna()

    # 상황(공격팀 기준): 타석 전후 점수 차이로 판단
    bat_pre = np.where(top, pa["away_score"], pa["home_score"])
    opp_pre = np.where(top, pa["home_score"], pa["away_score"])
    bat_post = np.where(top, pa["post_away_score"], pa["post_home_score"])
    opp_post = np.where(top, pa["post_home_score"], pa["post_away_score"])
    pre = bat_pre - opp_pre
    post = bat_post - opp_post
    last_ab = pa["game_pk"].map(games.set_index("game_pk")["last_ab"])
    walkoff = (~top) & (pa["inning"] >= 9) & (pre <= 0) & (post > 0) & (pa["at_bat_number"] == last_ab)
    pa["situation"] = np.select(
        [walkoff, (pre < 0) & (post > 0), (pre < 0) & (post == 0), (pre == 0) & (post > 0)],
        ["끝내기", "역전", "동점", "리드"],
        default="없음",
    )

    # 그 경기에서 이 타자의 몇 번째 타석
    pa = pa.sort_values(["game_pk", "at_bat_number"])
    pa["pa_no"] = pa.groupby(["game_pk", "batter"]).cumcount() + 1

    # 그 시즌 이 타자의 몇 번째 홈런 — 정규시즌 안에서만(hr_seq), 포스트시즌은 그 해 포스트시즌 안에서(post_hr_seq, PS5)
    pa = pa.sort_values(["batter", "season", "date", "game_pk", "at_bat_number"])
    is_hr = pa["events"].eq("home_run")
    seq = is_hr.astype(int).groupby([pa["batter"], pa["season"], pa["game_type"]]).cumsum()
    is_reg = pa["game_type"].eq("regular")
    pa["hr_seq"] = seq.where(is_hr & is_reg)
    pa["post_hr_seq"] = seq.where(is_hr & ~is_reg)

    pa = pa.rename(columns={
        "balls": "final_balls",
        "strikes": "final_strikes",
        "pitch_type": "last_pitch_type",
        "_naver_pitch_name": "last_pitch_name",
        "release_speed_kmh": "last_pitch_speed",
    })
    return pa.sort_values(["game_pk", "at_bat_number"]).reset_index(drop=True)


PA_PROPS = [
    "pa_id", "game_pk", "at_bat_number", "season", "inning", "inning_half", "pa_no",
    "events", "runs_scored", "hr_seq", "game_type", "post_hr_seq",
    "home_score", "away_score", "post_home_score", "post_away_score", "situation",
    "on_1b", "on_2b", "on_3b", "outs_when_up",
    "pitch_count", "final_balls", "final_strikes",
    "last_pitch_type", "last_pitch_name", "last_pitch_speed",
]
INT_PROPS = [
    "at_bat_number", "season", "inning", "pa_no", "runs_scored", "hr_seq", "post_hr_seq",
    "home_score", "away_score", "post_home_score", "post_away_score",
    "pitch_count", "final_balls", "final_strikes", "outs_when_up",
]


def pa_rows(pa: pd.DataFrame) -> list[dict]:
    from common import to_records

    props = pa[PA_PROPS].copy()
    for c in INT_PROPS:
        props[c] = props[c].astype("Int64")  # 정수로 저장 (빈 값은 null)
    props["last_pitch_speed"] = props["last_pitch_speed"].round(1)
    prop_list = to_records(props)
    base = to_records(pa[["pa_id", "date", "game_pk", "batter", "pitcher"]])
    for b, p in zip(base, prop_list):
        b["props"] = p
    return base


# ---------------------------------------------------------------- 선수, 소속
def build_players(df: pd.DataFrame, pa: pd.DataFrame) -> pd.DataFrame:
    # 이름: 가장 최근 경기에 쓰인 이름
    names = pd.concat([
        df[["batter", "batter_name", "game_date", "game_pk", "at_bat_number"]]
        .set_axis(["player_id", "name", "date", "game_pk", "ab"], axis=1),
        df[["pitcher", "pitcher_name", "game_date", "game_pk", "at_bat_number"]]
        .set_axis(["player_id", "name", "date", "game_pk", "ab"], axis=1),
    ])
    names = names[names["name"].notna()].sort_values(["date", "game_pk", "ab"])
    players = names.groupby("player_id")["name"].last().reset_index()
    # 투타·포지션·등번호·생년월일은 선수 프로필 CSV에서 넣는다 (05_load_profile.py)
    return players


def build_plays_for(pa: pd.DataFrame) -> pd.DataFrame:
    pa = regular(pa)  # 소속·경기 수는 정규시즌 기준 (포스트시즌 소속은 같은 팀)
    rows = pd.concat([
        pa[["batter", "season", "bat_team", "game_pk", "date"]].set_axis(
            ["player_id", "season", "team_id", "game_pk", "date"], axis=1),
        pa[["pitcher", "season", "pit_team", "game_pk", "date"]].set_axis(
            ["player_id", "season", "team_id", "game_pk", "date"], axis=1),
    ])
    return rows.groupby(["player_id", "season", "team_id"]).agg(
        games=("game_pk", "nunique"), first_date=("date", "min"), last_date=("date", "max"),
    ).reset_index()


# ---------------------------------------------------------------- 시즌 기록
def _counts(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    ev = frame["events"]
    flags = pd.DataFrame({
        "pa": 1,
        "h": ev.isin(HITS),
        "b2": ev.eq("double"),
        "b3": ev.eq("triple"),
        "hr": ev.eq("home_run"),
        "bb": ev.eq("walk"),
        "hbp": ev.eq("hit_by_pitch"),
        "so": ev.eq("strikeout"),
        "sf": ev.eq("sac_fly"),
        "sh": ev.eq("sac_bunt"),
        "ci": ev.eq("catcher_interference"),
    }).astype(int)
    for k in keys:
        flags[k] = frame[k].values
    c = flags.groupby(keys).sum().reset_index()
    c["ab"] = c["pa"] - c["bb"] - c["hbp"] - c["sf"] - c["sh"] - c["ci"]
    return c


def _div(a, b):
    return (a / b.where(b > 0)).astype(float)


def _rates(c: pd.DataFrame) -> pd.DataFrame:
    tb = c["h"] + c["b2"] + 2 * c["b3"] + 3 * c["hr"]
    c["avg"] = _div(c["h"], c["ab"])
    c["obp"] = _div(c["h"] + c["bb"] + c["hbp"], c["ab"] + c["bb"] + c["hbp"] + c["sf"])
    c["slg"] = _div(tb, c["ab"])
    c["ops"] = c["obp"] + c["slg"]
    return c


def _percentile(values: pd.Series, higher_is_better: bool) -> pd.Series:
    """0~99. 나보다 나쁜 선수 수 ÷ n × 100 반올림 (설계 D3). 동률은 같은 값, 값이 없으면 null.
    1위는 (n−1)/n×100 → 100이 나오지 않아 「상위 0%」가 생기지 않는다."""
    v = values.dropna()
    n = len(v)
    if n == 0:
        return pd.Series(np.nan, index=values.index)
    worse = v.rank(method="min", ascending=higher_is_better) - 1  # 나보다 나쁜 선수 수 (동률은 세지 않음)
    return np.floor(worse / n * 100 + 0.5).reindex(values.index)  # 사사오입 (pandas round는 짝수 쪽 반올림)


def _ops_sd(p: pd.DataFrame) -> pd.DataFrame:
    """꾸준함: 3월→4월 · 10월→9월을 합친 뒤 20타석 이상인 달의 월별 OPS 모표준편차 (그런 달이 3개 미만이면 null)"""
    p = p.assign(month=p["date"].str[5:7].astype(int).replace(MONTH_MERGE))
    m = _rates(_counts(p, ["player_id", "season", "month"]))
    m = m[(m["pa"] >= MONTH_MIN_PA) & m["ops"].notna()]
    sd = m.groupby(["player_id", "season"])["ops"].agg(["std", "count"])
    sd["ops_sd"] = m.groupby(["player_id", "season"])["ops"].std(ddof=0)
    sd.loc[sd["count"] < MONTH_MIN_COUNT, "ops_sd"] = np.nan
    return sd[["ops_sd"]].reset_index()


def build_batter_stats(pa: pd.DataFrame, games: pd.DataFrame, plays_for: pd.DataFrame) -> pd.DataFrame:
    pa, games = regular(pa), regular(games)  # 시즌 기록 · 백분위 · 비교 대상은 정규시즌만 (PS1)
    p = pa.rename(columns={"batter": "player_id"})
    s = _rates(_counts(p, ["player_id", "season"]))
    s["bb_pct"] = _div(s["bb"], s["pa"])
    s["k_pct"] = _div(s["so"], s["pa"])
    s["iso"] = s["slg"] - s["avg"]

    s = s.merge(_ops_sd(p), on=["player_id", "season"], how="left")

    # 백분위 대상: 규정타석(팀 경기 수 × 3.1)의 50% 이상.
    # 트레이드된 선수는 그 시즌 타석이 가장 많은 팀 기준 (같으면 나중에 뛴 팀). 타석 수는 모든 팀 합계
    team_games = pd.concat([
        games[["season", "home_team"]].rename(columns={"home_team": "team_id"}),
        games[["season", "away_team"]].rename(columns={"away_team": "team_id"}),
    ]).groupby(["season", "team_id"]).size().rename("team_games").reset_index()
    main_team = (
        p.groupby(["player_id", "season", "bat_team"])
        .agg(team_pa=("pa_id", "size"), last_date=("date", "max")).reset_index()
        .sort_values(["team_pa", "last_date"])
        .groupby(["player_id", "season"])["bat_team"].last()
        .rename("team_id").reset_index()
    )
    s = s.merge(main_team, on=["player_id", "season"], how="left").merge(
        team_games, on=["season", "team_id"], how="left")
    s["qualified"] = s["pa"] >= s["team_games"] * QUALIFY_RATE * QUALIFY_SHARE

    metrics = {  # 백분위 이름: (기준 수치, 높을수록 좋은가)
        "pct_contact": ("k_pct", False),
        "pct_hit": ("avg", True),
        "pct_power": ("iso", True),
        "pct_eye": ("bb_pct", True),
        "pct_consistency": ("ops_sd", False),
    }
    for col in metrics:
        s[col] = np.nan
    for season, idx in s[s["qualified"]].groupby("season").groups.items():
        for col, (base, higher) in metrics.items():
            s.loc[idx, col] = _percentile(s.loc[idx, base], higher)

    s["stat_id"] = s["player_id"] + "_" + s["season"].astype(str)
    return s


BATTER_PROPS = [
    "stat_id", "season", "pa", "ab", "h", "b2", "b3", "hr", "bb", "hbp", "so", "sf", "sh",
    "avg", "obp", "slg", "ops", "bb_pct",
    "k_pct", "iso", "ops_sd",
    "pct_contact", "pct_hit", "pct_power", "pct_eye", "pct_consistency", "qualified",
]
BATTER_RATE_COLS = ["avg", "obp", "slg", "ops", "bb_pct", "k_pct", "iso", "ops_sd"]
PCT_COLS = ["pct_contact", "pct_hit", "pct_power", "pct_eye", "pct_consistency"]


def batter_rows(s: pd.DataFrame) -> list[dict]:
    from common import to_records

    props = s[BATTER_PROPS].copy()
    props[BATTER_RATE_COLS] = props[BATTER_RATE_COLS].round(4)
    for c in PCT_COLS:
        props[c] = props[c].astype("Int64")
    props["qualified"] = props["qualified"].astype(bool)
    rows = to_records(s[["player_id", "stat_id"]])
    for r, p in zip(rows, to_records(props)):
        r["props"] = p
    return rows


# ---------------------------------------------------------------- 투수 귀속 (아웃·실점)
BASES = ("3b", "2b", "1b")  # 앞 주자부터 (먼저 홈에 들어온다고 본다)


def pa_ends(df: pd.DataFrame) -> pd.DataFrame:
    """타석마다 마지막 공 한 줄. 결과 없는 타석(주루 아웃으로 이닝 종료 등)도 남긴다 — 그 아웃·득점도 투수 몫이다.
    outs = 이 타석에서 잡은 아웃 (원천 post_outs − outs_when_up)."""
    e = df.groupby(["game_pk", "at_bat_number"], sort=False).tail(1).copy()
    e["season"] = e["game_date"].str[:4].astype(int)
    e["outs"] = (e["post_outs"] - e["outs_when_up"]).astype(int)
    return e.sort_values(["game_pk", "at_bat_number"]).reset_index(drop=True)


def charge_runs(ends: pd.DataFrame) -> pd.DataFrame:
    """실점을 주자를 내보낸 투수에게 매긴다 (공식 기록의 책임 주자 규칙).
    - 반 이닝마다 「주자 → 책임 투수」를 들고 간다. 타자가 출루하면 그 타석 투수가 책임진다.
    - 대주자(같은 루에 다른 선수)는 바뀐 주자의 책임을 이어받는다.
    - 한 타석에서 루를 떠난 주자 중 앞 주자부터 runs_scored만큼 득점한 것으로 본다(타자는 맨 뒤).
    한계: 야수선택으로 주자가 바뀌는 경우의 세부 규칙과, 타석 도중 교체 시점의 볼카운트 규칙(D2)은 반영하지 않는다.
    반환: game_pk · at_bat_number · pitcher(책임 투수) · runs"""
    out = []
    for (_, _, _), g in ends.groupby(["game_pk", "inning", "inning_topbot"], sort=False):
        resp: dict[str, str] = {}
        prev_post: dict[str, str] = {}
        for r in g.itertuples(index=False):
            pre = {b: getattr(r, f"on_{b}") for b in BASES if isinstance(getattr(r, f"on_{b}"), str)}
            post = {b: getattr(r, f"post_on_{b}") for b in BASES if isinstance(getattr(r, f"post_on_{b}"), str)}
            for b, runner in pre.items():  # 대주자: 같은 루의 이전 주자 책임을 이어받음
                old = prev_post.get(b)
                if old and old != runner and old not in pre.values() and old in resp:
                    resp[runner] = resp.pop(old)
                resp.setdefault(runner, r.pitcher)  # 출처를 모르는 주자는 지금 투수
            post_ids = set(post.values())
            leaving = [pre[b] for b in BASES if b in pre and pre[b] not in post_ids]
            if r.batter not in post_ids and r.batter not in pre.values():
                leaving.append(r.batter)
            runs = int(r.runs_scored or 0)
            for i in range(runs):
                who = leaving[i] if i < len(leaving) else None
                out.append((r.game_pk, r.at_bat_number, resp.get(who, r.pitcher) if who else r.pitcher, 1))
            for runner in leaving:
                resp.pop(runner, None)
            if r.batter in post_ids:
                resp[r.batter] = r.pitcher
            prev_post = post
    c = pd.DataFrame(out, columns=["game_pk", "at_bat_number", "pitcher", "runs"])
    return c.groupby(["game_pk", "at_bat_number", "pitcher"], as_index=False)["runs"].sum()


# 투수 5지표 (docs/투수.md, A안 확정 10-20). 백분위 이름: (기준 수치, 높을수록 좋은가)
PITCHER_AXES = {
    "pct_strikeout": ("k_pct", True),               # 탈삼진 = 삼진 ÷ 상대 타자
    "pct_control": ("bbhbp_pct", False),            # 제구 = (볼넷 + 사구) ÷ 상대 타자
    "pct_chase": ("chase_pct", True),               # 유인 = 존 밖 공에 한 스윙 ÷ 존 밖 공
    "pct_hit_prevention": ("avg", False),           # 안타 억제 = 피안타율
    "pct_power_prevention": ("iso_against", False),  # 장타 억제 = 피장타율 − 피안타율
}
PITCHER_QUALIFY = {"starter": 0.5, "reliever": 0.2}  # 비교 대상: 이닝 ≥ 주 소속팀 경기 수 × 이 값 (투수.md P4)
ZONE_HALF_WIDTH = 17 / 24  # 홈플레이트 반폭 ft
BALL_RADIUS = 0.1208       # 공 반지름 ft — 공 일부라도 걸치면 존 안 (Statcast와 같은 판정)


def chase_counts(df: pd.DataFrame) -> pd.DataFrame:
    """투수·시즌별 존 밖 공(o_pitches)과 그중 스윙(o_swings). 번트 시도(V·W)와 희생번트 타석의 마지막 공은 뺀다.
    투구 위치가 없는 공(0.04~0.38%)은 뺀다."""
    d = df[df["pitch_number"].gt(0)]
    loc = d[["plate_x", "plate_z", "sz_top", "sz_bot"]].notna().all(axis=1)
    inz = ((d["plate_x"].abs() <= ZONE_HALF_WIDTH + BALL_RADIUS)
           & (d["plate_z"] <= d["sz_top"] + BALL_RADIUS) & (d["plate_z"] >= d["sz_bot"] - BALL_RADIUS))
    last = ~d.duplicated(["game_pk", "at_bat_number"], keep="last")
    # 타석 중간 공은 events가 비어 있어 비교 결과가 NA가 된다 → 거짓으로 채운다 (NA가 아래 & 로 번지지 않게)
    bunt = d["pitch_result"].isin(["V", "W"]) | (last & d["events"].eq("sac_bunt").fillna(False))
    out_zone = (loc & ~inz.fillna(False) & ~bunt).fillna(False)
    swing = d["pitch_result"].isin(["S", "F", "H"]).fillna(False)  # 헛스윙·파울·타격
    c = pd.DataFrame({"player_id": d["pitcher"], "season": d["game_date"].str[:4].astype(int),
                      "o_pitches": out_zone.astype(int), "o_swings": (out_zone & swing).astype(int)})
    return c.groupby(["player_id", "season"], as_index=False)[["o_pitches", "o_swings"]].sum()


def build_pitcher_stats(df: pd.DataFrame, pa: pd.DataFrame) -> pd.DataFrame:
    df, pa = regular(df), regular(pa)  # 시즌 기록 · 백분위 · 비교 대상은 정규시즌만 (PS1)
    p = pa.rename(columns={"pitcher": "player_id"})
    s = _rates(_counts(p, ["player_id", "season"]))  # avg = 피안타율, slg = 피장타율
    s = s.rename(columns={"pa": "tbf"})  # 투수에게는 「상대 타자」

    # 아웃(결과 없는 타석 포함)·실점(책임 주자 기준)
    ends = pa_ends(df)
    outs = ends.groupby(["pitcher", "season"])["outs"].sum().rename("outs")
    charged = charge_runs(ends)
    # 시즌은 경기 날짜로 (경기 ID 앞자리는 포스트시즌이면 4444·3333… — 버그 B2)
    charged["season"] = charged["game_pk"].map(ends.groupby("game_pk")["season"].first())
    r = charged.groupby(["pitcher", "season"])["runs"].sum().rename("r")
    io = pd.concat([outs, r], axis=1).fillna(0).astype(int).rename_axis(["player_id", "season"]).reset_index()
    s = s.merge(io, on=["player_id", "season"], how="left")
    s[["outs", "r"]] = s[["outs", "r"]].fillna(0).astype(int)

    s = s.merge(p.groupby(["player_id", "season"])["game_pk"].nunique().rename("g").reset_index(),
                on=["player_id", "season"])
    # 선발: 그 경기에서 그 팀의 첫 번째 투수
    first = p.sort_values("at_bat_number").groupby(["game_pk", "pit_team"]).first().reset_index()
    gs = first.groupby(["player_id", "season"]).size().rename("gs").reset_index()
    s = s.merge(gs, on=["player_id", "season"], how="left")
    s["gs"] = s["gs"].fillna(0).astype(int)

    d = df.assign(season=df["game_date"].str[:4].astype(int)).rename(columns={"pitcher": "player_id"})
    pitches = d.groupby(["player_id", "season"]).size().rename("pitches")
    velo = d[d["pitch_type"].eq("FF")].groupby(["player_id", "season"])["release_speed_kmh"].mean().rename("avg_velo")
    s = s.merge(pitches.reset_index(), on=["player_id", "season"], how="left")
    s = s.merge(velo.reset_index(), on=["player_id", "season"], how="left")

    # 5지표 원 수치
    s = s.merge(chase_counts(df), on=["player_id", "season"], how="left")
    s[["o_pitches", "o_swings"]] = s[["o_pitches", "o_swings"]].fillna(0).astype(int)
    s["k_pct"] = _div(s["so"], s["tbf"])
    s["bbhbp_pct"] = _div(s["bb"] + s["hbp"], s["tbf"])
    s["chase_pct"] = _div(s["o_swings"], s["o_pitches"])
    s["iso_against"] = s["slg"] - s["avg"]
    s["whip"] = _div(s["h"] + s["bb"], s["outs"] / 3)

    # 역할: 등판의 절반 이상을 선발 → starter (투수.md P3)
    s["role"] = np.where(s["gs"] * 2 >= s["g"], "starter", "reliever")
    # 주 소속팀 = 그 시즌 상대 타자가 가장 많은 팀 (같으면 나중에 뛴 팀). 팀 경기 수 = 그 팀이 수비한 경기 수
    main_team = (
        p.groupby(["player_id", "season", "pit_team"])
        .agg(n=("pa_id", "size"), last_date=("date", "max")).reset_index()
        .sort_values(["n", "last_date"])
        .groupby(["player_id", "season"])["pit_team"].last().rename("team_id").reset_index()
    )
    team_games = pa.groupby(["season", "pit_team"])["game_pk"].nunique().rename("team_games").reset_index() \
        .rename(columns={"pit_team": "team_id"})
    s = s.merge(main_team, on=["player_id", "season"], how="left").merge(team_games, on=["season", "team_id"], how="left")
    s["qualified"] = (s["outs"] / 3) >= s["team_games"] * s["role"].map(PITCHER_QUALIFY)

    # 백분위: 같은 시즌·같은 역할의 비교 대상 안에서만 (D3 식)
    for col in PITCHER_AXES:
        s[col] = np.nan
    for _, idx in s[s["qualified"]].groupby(["season", "role"]).groups.items():
        for col, (base, higher) in PITCHER_AXES.items():
            s.loc[idx, col] = _percentile(s.loc[idx, base], higher)

    s["stat_id"] = s["player_id"] + "_" + s["season"].astype(str)
    return s


def build_outings(df: pd.DataFrame, pa: pd.DataFrame) -> pd.DataFrame:
    """등판 = 투수 한 명 × 경기 하나 (docs/장면.md 3-5). 투수 경기 기록과 등판 장면 연결의 대상.
    아웃은 결과 없는 타석 포함(pa_ends), 실점은 책임 주자 기준(charge_runs)."""
    # 등판 목록은 타석 끝 공 기준(결과 없는 타석 포함) — 견제로 이닝만 끝내고 내려간 투수도 등판이다
    ends = pa_ends(df)
    ends["pit_team"] = np.where(ends["inning_topbot"].eq("top"), ends["home_team"], ends["away_team"])
    c = ends.groupby(["game_pk", "pitcher"]).agg(
        season=("season", "first"), date=("game_date", "first"), team_id=("pit_team", "first"),
        first_ab=("at_bat_number", "min"), last_ab=("at_bat_number", "max"), outs=("outs", "sum"),
    ).reset_index().rename(columns={"pitcher": "player_id"})
    runs = charge_runs(ends).groupby(["game_pk", "pitcher"])["runs"].sum().rename("r") \
        .rename_axis(["game_pk", "player_id"]).reset_index()
    p = pa.rename(columns={"pitcher": "player_id"})
    counts = _counts(p, ["game_pk", "player_id"]).rename(columns={"pa": "tbf"})
    c = c.merge(runs, on=["game_pk", "player_id"], how="left").merge(counts, on=["game_pk", "player_id"], how="left")
    num = ["r", "tbf", "so", "bb", "hbp", "h", "hr"]
    c[num] = c[num].fillna(0).astype(int)
    c["outs"] = c["outs"].astype(int)
    team = c.groupby(["game_pk", "team_id"])
    c["starter"] = team["first_ab"].transform("min").eq(c["first_ab"])   # 그 팀 첫 투수
    c["finisher"] = team["last_ab"].transform("max").eq(c["last_ab"])    # 그 팀 마지막 투수
    c["team_pitchers"] = team["player_id"].transform("size")            # 완투·완봉 판정
    c["outing_id"] = c["game_pk"] + "_" + c["player_id"]
    c["game_type"] = c["game_pk"].map(ends.groupby("game_pk")["game_type"].first())
    return c.sort_values(["game_pk", "first_ab"]).reset_index(drop=True)


OUTING_PROPS = ["outing_id", "season", "date", "team_id", "outs", "tbf", "so", "bb", "hbp", "h", "hr", "r",
                "starter", "finisher", "team_pitchers", "game_type"]


def outing_rows(o: pd.DataFrame) -> list[dict]:
    from common import to_records

    props = o[OUTING_PROPS].copy()
    for b in ("starter", "finisher"):
        props[b] = props[b].astype(bool)
    rows = to_records(o[["outing_id", "player_id", "game_pk"]])
    for r, p in zip(rows, to_records(props)):
        r["props"] = p
    return rows


PITCHER_PROPS = ["stat_id", "season", "g", "gs", "tbf", "outs", "r", "h", "b2", "b3", "hr", "bb", "hbp", "so",
                 "sf", "sh", "ab", "avg", "slg", "whip", "pitches", "avg_velo",
                 "k_pct", "bbhbp_pct", "chase_pct", "iso_against", "o_pitches", "o_swings",
                 "role", "team_id", "team_games", "qualified", *PITCHER_AXES]
PITCHER_RATE_COLS = ["avg", "slg", "whip", "k_pct", "bbhbp_pct", "chase_pct", "iso_against"]


def pitcher_rows(s: pd.DataFrame) -> list[dict]:
    from common import to_records

    props = s[PITCHER_PROPS].copy()
    props[PITCHER_RATE_COLS] = props[PITCHER_RATE_COLS].round(4)
    props["avg_velo"] = props["avg_velo"].round(1)
    for c in PITCHER_AXES:
        props[c] = props[c].astype("Int64")
    props["qualified"] = props["qualified"].astype(bool)
    rows = to_records(s[["player_id", "stat_id"]])
    for r, p in zip(rows, to_records(props)):
        r["props"] = p
    return rows


# ---------------------------------------------------------------- 포스트시즌 기록 (PS1: 따로 · 백분위 없음)
BATTER_POST_PROPS = ["stat_id", "season", "games", "pa", "ab", "h", "b2", "b3", "hr", "bb", "hbp", "so", "sf", "sh",
                     "avg", "obp", "slg", "ops"]
PITCHER_POST_PROPS = ["stat_id", "season", "g", "gs", "tbf", "outs", "r", "h", "b2", "b3", "hr", "bb", "hbp", "so",
                      "sf", "sh", "ab", "avg", "slg", "whip"]


def build_batter_post_stats(pa: pd.DataFrame) -> pd.DataFrame:
    p = pa[pa["game_type"].eq("postseason")].rename(columns={"batter": "player_id"})
    if p.empty:
        return pd.DataFrame(columns=["player_id", *BATTER_POST_PROPS])
    s = _rates(_counts(p, ["player_id", "season"]))
    s = s.merge(p.groupby(["player_id", "season"])["game_pk"].nunique().rename("games").reset_index(), on=["player_id", "season"])
    s["stat_id"] = s["player_id"] + "_" + s["season"].astype(str) + "_post"
    return s


def build_pitcher_post_stats(df: pd.DataFrame, pa: pd.DataFrame) -> pd.DataFrame:
    df, pa = df[df["game_type"].eq("postseason")], pa[pa["game_type"].eq("postseason")]
    if pa.empty:
        return pd.DataFrame(columns=["player_id", *PITCHER_POST_PROPS])
    p = pa.rename(columns={"pitcher": "player_id"})
    s = _rates(_counts(p, ["player_id", "season"])).rename(columns={"pa": "tbf"})
    ends = pa_ends(df)
    outs = ends.groupby(["pitcher", "season"])["outs"].sum().rename("outs")
    charged = charge_runs(ends)
    charged["season"] = charged["game_pk"].map(ends.groupby("game_pk")["season"].first())
    r = charged.groupby(["pitcher", "season"])["runs"].sum().rename("r")
    io = pd.concat([outs, r], axis=1).fillna(0).astype(int).rename_axis(["player_id", "season"]).reset_index()
    s = s.merge(io, on=["player_id", "season"], how="left")
    s[["outs", "r"]] = s[["outs", "r"]].fillna(0).astype(int)
    s = s.merge(p.groupby(["player_id", "season"])["game_pk"].nunique().rename("g").reset_index(), on=["player_id", "season"])
    first = p.sort_values("at_bat_number").groupby(["game_pk", "pit_team"]).first().reset_index()
    gs = first.groupby(["player_id", "season"]).size().rename("gs").reset_index()
    s = s.merge(gs, on=["player_id", "season"], how="left")
    s["gs"] = s["gs"].fillna(0).astype(int)
    s["whip"] = _div(s["h"] + s["bb"], s["outs"] / 3)
    s["stat_id"] = s["player_id"] + "_" + s["season"].astype(str) + "_post"
    return s


def post_rows(s: pd.DataFrame, props: list[str]) -> list[dict]:
    from common import to_records

    rates = [c for c in ("avg", "obp", "slg", "ops", "whip") if c in props]
    pr = s[props].copy()
    pr[rates] = pr[rates].astype(float).round(4)
    rows = to_records(s[["player_id", "stat_id"]])
    for r, p in zip(rows, to_records(pr)):
        r["props"] = p
    return rows


# ---------------------------------------------------------------- 드라이 런
def build_all(df: pd.DataFrame) -> dict:
    games = build_games(df)
    pa = build_pa(df, games)
    plays_for = build_plays_for(pa)
    return {
        "games": games,
        "teams": build_teams(games),
        "pa": pa,
        "players": build_players(df, pa),
        "plays_for": plays_for,
        "batter_stats": build_batter_stats(pa, games, plays_for),
        "pitcher_stats": build_pitcher_stats(df, pa),
    }


if __name__ == "__main__":
    print("parquet 읽는 중…")
    data = build_all(read_pitches())
    for k, v in data.items():
        print(f"{k:14s} {len(v):>8,}행")
    pa = data["pa"]
    print("\n타석 상황 분포:", pa["situation"].value_counts().to_dict())
    bs = data["batter_stats"]
    print("시즌별 백분위 대상 타자 수:", bs[bs["qualified"]].groupby("season").size().to_dict())
