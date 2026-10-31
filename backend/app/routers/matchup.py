"""
매치업 API
   6. GET /matchup?batter=&pitcher=&season=          타자 1명 vs 투수 1명 맞대결
  17. GET /players/{player_id}/matchups?season=&min_pa=&as=  이 타자가 상대한 투수 전체 (as=pitcher면 이 투수가 상대한 타자 전체)
  37. GET /matchup/forecast?batter=&pitcher=&season=  다음에 붙으면 — 타석 결과별 예상 확률
"""
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Query

from ..db import run
from ..errors import ApiError
from ..events import batting_line, events_ko
from ..postseason import game_tag
from ..utils import avg

router = APIRouter(tags=["매치업"])


# ------------------------------------------------------------------ 6. 맞대결
Q_NAMES = """
MATCH (p:Player) WHERE p.player_id IN [$batter, $pitcher]
RETURN p.player_id AS player_id, p.name AS name
"""

Q_MATCHUP = """
MATCH (:Player {player_id: $batter})-[:BATTED_IN]->(pa:PlateAppearance)<-[:PITCHED_IN]-(:Player {player_id: $pitcher})
WHERE $season IS NULL OR pa.season = $season
MATCH (pa)-[:PART_OF]->(g:Game)
OPTIONAL MATCH (pa)-[m:MATCHED_TO]->(:VideoLink) WHERE m.status IN ['auto_confirmed', 'approved'] AND coalesce(m.precision, 'scene') <> 'game'
WITH pa, g, count(m) > 0 AS has_video  // 집계 뒤 ORDER BY는 투영한 변수만 쓸 수 있어서 pa·g를 넘긴다
RETURN pa.pa_id AS pa_id, toString(pa.date) AS date, pa.inning AS inning,
       pa.inning_half AS inning_half, pa.events AS events, has_video,
       g.game_type AS game_type, g.stage AS stage, g.series_game_no AS series_game_no
ORDER BY pa.date DESC, g.dh_no DESC, pa.at_bat_number DESC
"""


@router.get("/matchup", summary="6. 타자 vs 투수 맞대결")
def get_matchup(  # API 6: 두 선수의 맞대결 요약 + 타석 목록 (최근 순)
    batter: str = Query(..., description="타자 ID"),
    pitcher: str = Query(..., description="투수 ID"),
    season: int | None = Query(None, description="생략하면 전체 시즌 합계"),
):
    names = {r["player_id"]: r["name"] for r in run(Q_NAMES, batter=batter, pitcher=pitcher)}
    if batter not in names or pitcher not in names:
        raise ApiError(404, "PLAYER_NOT_FOUND", "선수를 찾을 수 없습니다")

    rows = run(Q_MATCHUP, batter=batter, pitcher=pitcher, season=season)
    line = batting_line([r["events"] for r in rows])
    line["avg"] = avg(line["h"], line["ab"])

    return {
        "batter": {"player_id": batter, "name": names[batter]},
        "pitcher": {"player_id": pitcher, "name": names[pitcher]},
        "season": season,
        "summary": line,  # 맞대결이 없으면 pa 0, avg null
        "plate_appearances": [{**r, **game_tag(r), "events_ko": events_ko(r["events"])} for r in rows],  # 정규 · 포스트시즌 함께, 포스트시즌은 꼬리표
    }


# ------------------------------------------------------------------ 17. 상대한 투수 전체
Q_VS_PITCHERS = """
MATCH (b:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance)<-[:PITCHED_IN]-(pit:Player)
WHERE ($season IS NULL OR pa.season = $season) AND pa.game_type = 'regular'   // 정규시즌만 (시안 「정규시즌 누적」)
WITH pit, collect(pa.events) AS events
WHERE size(events) >= $min_pa
OPTIONAL MATCH (pit)-[f:PLAYS_FOR]->(t:Team)                                    // 팀은 지금(가장 최근) 소속
WITH pit, events, t ORDER BY f.season DESC, f.last_date DESC
WITH pit, events, head(collect(t.name)) AS team
RETURN pit.player_id AS player_id, pit.name AS name, team, events
ORDER BY size(events) DESC, name
"""

Q_VS_BATTERS = """
MATCH (pit:Player {player_id: $id})-[:PITCHED_IN]->(pa:PlateAppearance)<-[:BATTED_IN]-(b:Player)
WHERE ($season IS NULL OR pa.season = $season) AND pa.game_type = 'regular'
WITH b, collect(pa.events) AS events
WHERE size(events) >= $min_pa
OPTIONAL MATCH (b)-[f:PLAYS_FOR]->(t:Team)
WITH b, events, t ORDER BY f.season DESC, f.last_date DESC
WITH b, events, head(collect(t.name)) AS team
RETURN b.player_id AS player_id, b.name AS name, team, events
ORDER BY size(events) DESC, name
"""

Q_EXISTS = "MATCH (p:Player {player_id: $id}) RETURN p.name AS name"


def _tag(rows: list[dict], tag_min_pa: int, pitcher_view: bool) -> tuple[str | None, str | None]:
    """(강했던 상대, 약했던 상대) ID. tag_min_pa타석 이상 상대 중 상대 타율이 가장 높은 / 낮은 선수.
    타자 화면은 타율이 높으면 강했던 상대, 투수 화면은 반대(상대 타율이 낮으면 강했던 상대). 같으면 타석이 많은 쪽"""
    pool = [r for r in rows if r["pa"] >= tag_min_pa and r["avg"] is not None]
    if len(pool) < 2:
        return None, None
    hi = max(pool, key=lambda r: (r["avg"], r["pa"]))["player_id"]
    lo = min(pool, key=lambda r: (r["avg"], -r["pa"]))["player_id"]
    return (lo, hi) if pitcher_view else (hi, lo)


@router.get("/players/{player_id}/matchups", summary="17. 이 타자가 상대한 투수 목록")
def get_vs_pitchers(  # API 17: 타석 많은 투수 순. 투수를 고르면 API 6으로 자세히
    player_id: str,
    season: int | None = Query(None, description="생략하면 전체 시즌 합계"),
    min_pa: int = Query(10, ge=1, description="이 타석 수 이상 상대한 투수만 (시안 기준 10)"),
    as_: Literal["batter", "pitcher"] = Query("batter", alias="as", description="batter: 이 타자가 상대한 투수 / pitcher: 이 투수가 상대한 타자"),
    tag_min_pa: int = Query(15, ge=1, description="「강했어요 · 약했어요」를 붙일 최소 타석 (작은 표본 제외)"),
):
    who = run(Q_EXISTS, id=player_id)
    if not who:
        raise ApiError(404, "PLAYER_NOT_FOUND", "선수를 찾을 수 없습니다")

    if as_ == "pitcher":
        batters = []
        for r in run(Q_VS_BATTERS, id=player_id, season=season, min_pa=min_pa):
            line = batting_line(r["events"])
            line["avg"] = avg(line["h"], line["ab"])
            batters.append({"player_id": r["player_id"], "name": r["name"], "team": r["team"], **line})
        strong, weak = _tag(batters, tag_min_pa, pitcher_view=True)
        for b in batters:
            b["tag"] = "strong" if b["player_id"] == strong else "weak" if b["player_id"] == weak else None
        return {"pitcher": {"player_id": player_id, "name": who[0]["name"]}, "season": season, "min_pa": min_pa,
                "tag_min_pa": tag_min_pa, "strongest": strong, "weakest": weak, "batters": batters}

    pitchers = []
    for r in run(Q_VS_PITCHERS, id=player_id, season=season, min_pa=min_pa):
        line = batting_line(r["events"])
        line["avg"] = avg(line["h"], line["ab"])
        pitchers.append({"player_id": r["player_id"], "name": r["name"], "team": r["team"], **line})
    strong, weak = _tag(pitchers, tag_min_pa, pitcher_view=False)
    for x in pitchers:
        x["tag"] = "strong" if x["player_id"] == strong else "weak" if x["player_id"] == weak else None  # 강했어요 · 약했어요

    return {
        "batter": {"player_id": player_id, "name": who[0]["name"]},
        "season": season,
        "min_pa": min_pa,
        "tag_min_pa": tag_min_pa,
        "strongest": strong,   # 가장 강했던 상대 ID (없으면 null)
        "weakest": weak,       # 가장 약했던 상대 ID
        "pitchers": pitchers,
    }


# ------------------------------------------------------------------ 37. 맞대결 예상
# 타석 결과 6갈래의 확률을 log5(오즈비) 방식으로 낸다: 타자 오즈 × 투수 오즈 ÷ 리그 오즈 → 여섯 개 합이 1이 되게 나눈다.
#  · 2루타 · 3루타는 드물어 따로 두면 몇 개 차이로 확률이 튄다 → 「2·3루타」 한 갈래, 장타율의 루타 수는 리그 2루타 : 3루타 비율로
#  · 타자 = 그 시즌 이 투수 손(좌투 · 우투) 상대 비율, 투수 = 그 시즌 이 타자 쪽(좌타 · 우타) 상대 비율, 리그 = 같은 좌우 조합 평균
#  · 표본이 작으면 흔들리므로 좌우 비율은 시즌 전체 비율 쪽으로(SPLIT_K), 시즌 전체 비율은 리그 쪽으로(SEASON_K) 당긴다
#  · 직접 맞대결(정규시즌 전체)은 타석 수만큼만 섞는다: 맞대결 n타석 ÷ (n + H2H_K)
#  · 투타 정보가 없으면 좌우를 빼고 시즌 전체 비율 · 리그 전체 평균으로 계산한다
OUTCOMES = ("single", "xbh", "home_run", "bb", "so", "out")   # xbh = 2루타 + 3루타
HIT_OUT = ("single", "xbh", "home_run")
SEASON_K = 100   # 시즌 비율을 리그 쪽으로 당기는 세기 (타석 수로 셈)
SPLIT_K = 200    # 좌우 비율을 시즌 전체 쪽으로 당기는 세기
H2H_K = 100      # 직접 맞대결을 섞는 세기 — 21타석이면 약 17%
EDGE = 0.08      # 예상 OPS가 같은 좌우 리그 평균보다 8% 넘게 높으면 타자 우세, 낮으면 투수 우세

Q_FC_BATTER = """
MATCH (b:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance {season: $season, game_type: 'regular'})<-[:PITCHED_IN]-(pit:Player)
RETURN pa.events AS e, pit.bats_throws AS bt
"""
Q_FC_PITCHER = """
MATCH (pit:Player {player_id: $id})-[:PITCHED_IN]->(pa:PlateAppearance {season: $season, game_type: 'regular'})<-[:BATTED_IN]-(b:Player)
RETURN pa.events AS e, b.bats_throws AS bt
"""
Q_FC_LEAGUE = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance {season: $season, game_type: 'regular'})<-[:PITCHED_IN]-(pit:Player)
RETURN b.bats_throws AS bbt, pit.bats_throws AS pbt, pa.events AS e, count(*) AS n
"""
Q_FC_H2H = """
MATCH (:Player {player_id: $batter})-[:BATTED_IN]->(pa:PlateAppearance {game_type: 'regular'})<-[:PITCHED_IN]-(:Player {player_id: $pitcher})
RETURN pa.events AS e
"""
Q_FC_PLAYERS = """
MATCH (p:Player) WHERE p.player_id IN [$batter, $pitcher]
OPTIONAL MATCH (p)-[f:PLAYS_FOR]->(t:Team)
WITH p, t ORDER BY f.season DESC, f.last_date DESC
RETURN p.player_id AS player_id, p.name AS name, p.bats_throws AS bt, head(collect(t.name)) AS team
"""


def _outcome(e: str) -> str:  # 타석 결과 → 6갈래 (희생타 · 실책 · 야수선택 · 병살은 아웃 쪽)
    if e in ("single", "home_run"):
        return e
    if e in ("double", "triple"):
        return "xbh"
    if e in ("walk", "hit_by_pitch"):
        return "bb"
    if e == "strikeout":
        return "so"
    return "out"


def _throws(bt: str | None) -> str | None:  # 「우투좌타」 → 우
    return bt[0] if bt and len(bt) >= 4 and bt[1] == "투" else None


def _bats(bt: str | None, vs_throws: str | None) -> str | None:  # 「우투좌타」 → 좌. 양타는 투수 반대 손
    side = bt[2] if bt and len(bt) >= 4 and bt[3] == "타" else None
    if side == "양":
        return {"우": "좌", "좌": "우"}.get(vs_throws or "")
    return side


def _counts(events) -> dict:
    c = dict.fromkeys(OUTCOMES, 0)
    for e in events:
        c[_outcome(e)] += 1
    return c


def _rates(c: dict, prior: dict, k: float) -> dict:  # 표본이 작을수록 prior 쪽으로
    n = sum(c.values())
    return {o: (c[o] + k * prior[o]) / (n + k) for o in OUTCOMES}


def _share(c: dict) -> dict:
    n = sum(c.values()) or 1
    return {o: c[o] / n for o in OUTCOMES}


@lru_cache(maxsize=8)
def _league(season: int) -> tuple[dict, float]:
    """((타자 쪽, 투수 손) → 6갈래 수, 2·3루타 하나의 평균 루타). 키 None은 전체. 데이터가 바뀌지 않아 시즌마다 한 번만 센다"""
    out: dict = {}
    xb = {"double": 0, "triple": 0}
    for r in run(Q_FC_LEAGUE, season=season):
        th = _throws(r["pbt"])
        side = _bats(r["bbt"], th)
        keys = [None, (side, th)] if side and th else [None]
        for key in keys:
            out.setdefault(key, dict.fromkeys(OUTCOMES, 0))[_outcome(r["e"])] += r["n"]
        if r["e"] in xb:
            xb[r["e"]] += r["n"]
    n = xb["double"] + xb["triple"]
    return out, (2 * xb["double"] + 3 * xb["triple"]) / n if n else 2.0


def _line(p: dict, xbh_tb: float) -> dict:  # 확률 → 예상 타율 · 출루율 · 장타율 · OPS (희생타는 아웃에 들어 있어 타수 = 1 − 볼넷)
    ab = 1 - p["bb"]
    h = sum(p[o] for o in HIT_OUT)
    obp = h + p["bb"]
    slg = (p["single"] + p["xbh"] * xbh_tb + p["home_run"] * 4) / ab if ab else 0
    return {"avg": round(h / ab, 3) if ab else None, "obp": round(obp, 3), "slg": round(slg, 3), "ops": round(obp + slg, 3)}


def _odds(x: float) -> float:
    return x / (1 - x) if x < 1 else 1e9


@router.get("/matchup/forecast", summary="37. 맞대결 예상 (다음에 붙으면)")
def get_forecast(  # API 37: 타석 결과 6갈래 예상 확률 + 예상 타율 · OPS + 같은 좌우 리그 평균 + 직접 맞대결
    batter: str = Query(..., description="타자 ID"),
    pitcher: str = Query(..., description="투수 ID"),
    season: int = Query(..., description="기준 시즌 (타자 · 투수 · 리그 비율을 이 시즌으로)"),
):
    who = {r["player_id"]: r for r in run(Q_FC_PLAYERS, batter=batter, pitcher=pitcher)}
    if batter not in who or pitcher not in who:
        raise ApiError(404, "PLAYER_NOT_FOUND", "선수를 찾을 수 없습니다")
    b_rows = run(Q_FC_BATTER, id=batter, season=season)
    p_rows = run(Q_FC_PITCHER, id=pitcher, season=season)
    if not b_rows or not p_rows:
        raise ApiError(404, "NO_SEASON_RECORD", f"{season} 시즌 {'타석' if not b_rows else '투구'} 기록이 없어 예상할 수 없어요")

    league, xbh_tb = _league(season)
    th = _throws(who[pitcher]["bt"])
    side = _bats(who[batter]["bt"], th)
    hand = (side, th) if side and th and (side, th) in league else None

    lg_all = _share(league[None])
    lg = _share(league[hand]) if hand else lg_all
    b_season = _rates(_counts(r["e"] for r in b_rows), lg_all, SEASON_K)
    p_season = _rates(_counts(r["e"] for r in p_rows), lg_all, SEASON_K)
    if hand:  # 좌우: 타자는 이 손 투수 상대, 투수는 이 쪽 타자 상대
        b_split = _counts(r["e"] for r in b_rows if _throws(r["bt"]) == th)
        p_split = _counts(r["e"] for r in p_rows if _bats(r["bt"], th) == side)
        b_rate, p_rate = _rates(b_split, b_season, SPLIT_K), _rates(p_split, p_season, SPLIT_K)
        b_n, p_n = sum(b_split.values()), sum(p_split.values())
    else:
        b_rate, p_rate = b_season, p_season
        b_n, p_n = len(b_rows), len(p_rows)

    raw = {o: _odds(b_rate[o]) * _odds(p_rate[o]) / _odds(lg[o]) if lg[o] else 0 for o in OUTCOMES}
    raw = {o: v / (1 + v) for o, v in raw.items()}  # 오즈 → 확률
    total = sum(raw.values())
    model = {o: raw[o] / total for o in OUTCOMES}

    h2h_events = [r["e"] for r in run(Q_FC_H2H, batter=batter, pitcher=pitcher)]
    h2h_n = len(h2h_events)
    w = h2h_n / (h2h_n + H2H_K)
    h2h = _share(_counts(h2h_events)) if h2h_n else model
    prob = {o: (1 - w) * model[o] + w * h2h[o] for o in OUTCOMES}

    me, base = _line(prob, xbh_tb), _line(lg, xbh_tb)
    ratio = me["ops"] / base["ops"] if base["ops"] else 1
    h2h_line = batting_line(h2h_events)
    return {
        "season": season,
        "batter": {"player_id": batter, "name": who[batter]["name"], "team": who[batter]["team"], "bats": side},
        "pitcher": {"player_id": pitcher, "name": who[pitcher]["name"], "team": who[pitcher]["team"], "throws": th},
        "platoon": f"{side}타 vs {th}투" if hand else None,   # 좌우를 반영했으면 「좌타 vs 우투」
        "basis": {"batter_pa": b_n, "pitcher_tbf": p_n, "h2h_pa": h2h_n, "h2h_weight": round(w, 3)},
        "probs": {o: round(v, 3) for o, v in prob.items()},     # 타석당 확률 6갈래 (합 1)
        "expected": me,                                          # 예상 타율 · 출루율 · 장타율 · OPS
        "league": {"probs": {o: round(v, 3) for o, v in lg.items()}, **base},  # 같은 좌우 조합 리그 평균
        "edge": "batter" if ratio > 1 + EDGE else "pitcher" if ratio < 1 - EDGE else "even",
        "h2h": {"pa": h2h_n, "ab": h2h_line["ab"], "h": h2h_line["h"], "hr": h2h_line["hr"], "avg": avg(h2h_line["h"], h2h_line["ab"])},

    }
