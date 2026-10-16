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
]
STR_COLS = [
    "game_pk", "game_date", "home_team", "away_team", "inning_topbot", "batter", "pitcher",
    "batter_name", "pitcher_name", "on_1b", "on_2b", "on_3b", "events", "pitch_result",
    "pitch_type", "_naver_pitch_name",
]

TEAM_NAMES = {
    "HT": "KIA", "OB": "두산", "LG": "LG", "SS": "삼성", "LT": "롯데",
    "SK": "SSG", "HH": "한화", "WO": "키움", "KT": "KT", "NC": "NC",
}

SEASONS = (2024, 2025, 2026)  # 사용하는 시즌. 2023은 쓰지 않음 (원본 파일은 그대로 두고 읽을 때 뺀다)

QUALIFY_RATE = 3.1   # 규정타석 = 팀 경기 수 × 3.1
QUALIFY_SHARE = 0.5  # 그중 50% 이상이면 백분위 대상
MONTH_MIN_PA = 30    # 꾸준함: 30타석 이상인 달만
MONTH_MIN_COUNT = 3  # 그런 달이 3개 이상이어야 계산


# ---------------------------------------------------------------- 읽기
def read_pitches(data_dir=KBO_PBP_DIR) -> pd.DataFrame:
    """시즌별 파일(kbo_pbp_<시즌>.parquet)에서 사용 시즌만 읽는다. 2023 파일은 열지 않는다."""
    paths = [data_dir / f"kbo_pbp_{y}.parquet" for y in SEASONS]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise SystemExit(f"원본 파일이 없습니다: {data_dir} 의 {', '.join(missing)}\n"
                         "python scripts/get_data.py 로 받거나 .env의 KBO_PBP_DIR을 확인하세요.")
    df = pd.concat([pd.read_parquet(p, columns=COLUMNS) for p in paths], ignore_index=True)
    df = df[df["game_date"].astype("string").str[:4].isin([str(y) for y in SEASONS])]
    return clean(df)


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
    ).reset_index()
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

    # 그 시즌 이 타자의 몇 번째 홈런
    pa = pa.sort_values(["batter", "season", "date", "game_pk", "at_bat_number"])
    is_hr = pa["events"].eq("home_run")
    seq = is_hr.astype(int).groupby([pa["batter"], pa["season"]]).cumsum()
    pa["hr_seq"] = seq.where(is_hr)

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
    "events", "runs_scored", "hr_seq",
    "home_score", "away_score", "post_home_score", "post_away_score", "situation",
    "on_1b", "on_2b", "on_3b",
    "pitch_count", "final_balls", "final_strikes",
    "last_pitch_type", "last_pitch_name", "last_pitch_speed",
]
INT_PROPS = [
    "at_bat_number", "season", "inning", "pa_no", "runs_scored", "hr_seq",
    "home_score", "away_score", "post_home_score", "post_away_score",
    "pitch_count", "final_balls", "final_strikes",
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
    """0~100. 비교 대상 중 몇 %를 앞서는지. 값이 없으면 null."""
    v = values.dropna()
    n = len(v)
    if n < 2:
        return pd.Series(np.nan, index=values.index)
    rank = v.rank(method="average", ascending=higher_is_better)  # 1 = 가장 나쁨
    return ((rank - 1) / (n - 1) * 100).round().reindex(values.index)


def build_batter_stats(pa: pd.DataFrame, games: pd.DataFrame, plays_for: pd.DataFrame) -> pd.DataFrame:
    p = pa.rename(columns={"batter": "player_id"})
    s = _rates(_counts(p, ["player_id", "season"]))
    s["bb_pct"] = _div(s["bb"], s["pa"])
    s["k_pct"] = _div(s["so"], s["pa"])
    s["iso"] = s["slg"] - s["avg"]

    # 꾸준함: 30타석 이상인 달의 월별 OPS 표준편차 (그런 달이 3개 미만이면 null)
    p = p.assign(month=p["date"].str[5:7].astype(int))
    m = _rates(_counts(p, ["player_id", "season", "month"]))
    m = m[(m["pa"] >= MONTH_MIN_PA) & m["ops"].notna()]
    sd = m.groupby(["player_id", "season"])["ops"].agg(["std", "count"])
    sd["ops_sd"] = m.groupby(["player_id", "season"])["ops"].std(ddof=0)
    sd.loc[sd["count"] < MONTH_MIN_COUNT, "ops_sd"] = np.nan
    s = s.merge(sd[["ops_sd"]].reset_index(), on=["player_id", "season"], how="left")

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


def build_pitcher_stats(df: pd.DataFrame, pa: pd.DataFrame) -> pd.DataFrame:
    p = pa.rename(columns={"pitcher": "player_id"})
    s = _counts(p, ["player_id", "season"])
    s["avg"] = _div(s["h"], s["ab"])

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

    s["stat_id"] = s["player_id"] + "_" + s["season"].astype(str)
    return s


PITCHER_PROPS = ["stat_id", "season", "g", "gs", "h", "hr", "bb", "hbp", "so", "ab", "avg", "pitches", "avg_velo"]


def pitcher_rows(s: pd.DataFrame) -> list[dict]:
    from common import to_records

    props = s[PITCHER_PROPS].copy()
    props["avg"] = props["avg"].round(4)
    props["avg_velo"] = props["avg_velo"].round(1)
    rows = to_records(s[["player_id", "stat_id"]])
    for r, p in zip(rows, to_records(props)):
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
