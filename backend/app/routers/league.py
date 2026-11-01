"""
리그 API (시안 메인·팀 화면)
  13. GET /standings?season=                                  팀 순위
  16. GET /batters?season=&team=&sort=&qualified=&limit=       타자 순위표 (리그 상위 타자, 팀 선수 목록)
  18. GET /leaders?season=&limit=                              지표 5개별 상위 n명 (메인 '이런 타자는 어때요?')
  26. GET /pitchers?season=&team=&role=&qualified=&sort=&limit= 투수 목록 (팀 화면 투수 표, 05 능력별 순위 투수 탭)
  29. GET /pitchers/leaders?season=&role=&limit=               투수 지표 5개별 상위 n명 (메인 능력 카드 「투수」)
  31. GET /players/{player_id}/similar?season=&as=&limit=      가장 강한 지표가 비슷한 선수 (03 · 03b 아래)
  33. GET /teams/{team}/scenes?season=&limit=                  팀의 최근 장면 (06 팀 「KIA의 최근 장면」)
  35. GET /teams/{team}/games?season=&limit=                   팀의 최근 경기 (06 팀 「최근 경기」)
"""
from typing import Literal

from fastapi import APIRouter, Query

from ..db import run
from ..errors import ApiError
from ..postseason import game_tag
from ..scenes import CONFIRMED, GOOD_EVENTS, game_highlights, scene_of
from ..utils import result_of
from .players import AXIS_TAGS, PITCH_AXES

router = APIRouter(tags=["리그"])


# ------------------------------------------------------------------ 13. 팀 순위
Q_SEASONS = "MATCH (g:Game) RETURN DISTINCT g.season AS season ORDER BY season"

Q_SEASON_GAMES = """
MATCH (g:Game {season: $season, game_type: 'regular'})-[:HOME]->(h:Team), (g)-[:AWAY]->(a:Team)  // 순위는 정규시즌만 (포스트시즌.md B7)
RETURN h.team_id AS home_id, h.name AS home, a.team_id AS away_id, a.name AS away,
       g.home_final AS home_score, g.away_final AS away_score
"""


def _rank(values: list) -> list[int]:  # 공동 순위 매기기 (같은 값이면 같은 순위). values는 정렬된 상태
    ranks = []
    for i, v in enumerate(values):
        ranks.append(ranks[-1] if i and v == values[i - 1] else i + 1)
    return ranks


@router.get("/standings", summary="13. 팀 순위")
def get_standings(  # API 13: 시즌 팀 순위 (승률 = 승 ÷ (승+패), 무승부 제외 — KBO 방식)
    season: int | None = Query(None, description="생략하면 가장 최근 시즌"),
):
    seasons = [r["season"] for r in run(Q_SEASONS)]
    if not seasons:
        raise ApiError(404, "NO_GAMES", "경기 데이터가 없습니다")
    if season is None:
        season = seasons[-1]
    elif season not in seasons:
        raise ApiError(404, "SEASON_NOT_FOUND", f"{season} 시즌 경기가 없습니다")

    table = {}  # team_id → 기록
    for g in run(Q_SEASON_GAMES, season=season):
        for tid, name, mine, opp in [
            (g["home_id"], g["home"], g["home_score"], g["away_score"]),
            (g["away_id"], g["away"], g["away_score"], g["home_score"]),
        ]:
            t = table.setdefault(tid, {"team_id": tid, "team": name, "games": 0, "w": 0, "l": 0, "d": 0})
            t["games"] += 1
            t["w" if mine > opp else "l" if mine < opp else "d"] += 1

    teams = list(table.values())
    for t in teams:
        t["pct"] = round(t["w"] / (t["w"] + t["l"]), 3) if t["w"] + t["l"] else 0.0
    teams.sort(key=lambda t: (-t["pct"], -t["w"]))

    top = teams[0]
    for t, r in zip(teams, _rank([t["pct"] for t in teams])):
        t["rank"] = r
        t["gb"] = ((top["w"] - t["w"]) + (t["l"] - top["l"])) / 2  # 게임차. 1위는 0

    return {"seasons": seasons, "season": season, "teams": teams}


# ------------------------------------------------------------------ 16. 타자 순위표
Q_LATEST_STAT_SEASON = "MATCH (s:BatterSeasonStat) RETURN max(s.season) AS s"

Q_BATTERS = """
MATCH (p:Player)-[:HAS_STAT]->(s:BatterSeasonStat {season: $season})
OPTIONAL MATCH (p)-[f:PLAYS_FOR {season: $season}]->(t:Team)
WITH p, s, t, f ORDER BY f.last_date DESC
WITH p, s, head(collect(t.name)) AS team, sum(f.games) AS games   // 트레이드면 두 팀 경기 수 합
RETURN p.player_id AS player_id, p.name AS name, p.bats_throws AS bats_throws, p.position AS position,
       p.back_number AS back_number, team, games, s {.*} AS s
"""

# 선수마다 그 시즌 장면 수 — 카드의 '장면 N'. 선수 화면 「장면」 탭(API-36)과 같은 기준:
# 잘한 타석(GOOD_EVENTS) 중 확정 · 재생 가능한 타석 장면(경기 단위 영상 제외)이 있는 타석 수, 정규 · 포스트시즌 함께 (11-01 사용자)
Q_SCENE_COUNTS = """
MATCH (p:Player)-[:BATTED_IN]->(pa:PlateAppearance {season: $season})
WHERE pa.events IN $events
  AND EXISTS { (pa)-[m:MATCHED_TO]->(v:VideoLink)
               WHERE m.status IN $confirmed AND coalesce(m.precision, 'scene') <> 'game' AND coalesce(v.playable, true) }
RETURN p.player_id AS player_id, count(pa) AS n
"""

AXES = {  # 응답 이름: DB 속성 (백분위, 클수록 좋음)
    "contact": "pct_contact",
    "hit": "pct_hit",
    "power": "pct_power",
    "eye": "pct_eye",
    "consistency": "pct_consistency",
}
SORTS = {"ops": "ops", "avg": "avg", "hr": "hr", "pa": "pa", **AXES}


def _axis_ranks(qualified: list[dict]) -> dict:  # 비교 대상 안에서 지표별 순위 (시안 '파워 2위')
    ranks = {}  # player_id → {axis: 순위}
    for axis, key in AXES.items():
        has = sorted([b for b in qualified if b["s"].get(key) is not None], key=lambda b: -b["s"][key])
        for b, r in zip(has, _rank([b["s"][key] for b in has])):
            ranks.setdefault(b["player_id"], {})[axis] = r
    return ranks


@router.get("/batters", summary="16. 타자 순위표")
def get_batters(  # API 16: 리그 상위 타자 / 지표별 TOP / 팀 타자 목록에 같이 씀
    season: int | None = Query(None, description="생략하면 가장 최근 시즌"),
    team: str | None = Query(None, description="팀 이름 (예: KIA). 생략하면 리그 전체"),
    sort: Literal["ops", "avg", "hr", "pa", "contact", "hit", "power", "eye", "consistency"] = Query("ops"),
    qualified: bool = Query(True, description="true면 리그 비교 대상(규정타석 50% 이상)만"),
    limit: int = Query(20, ge=1, le=500),
):
    if season is None:
        season = run(Q_LATEST_STAT_SEASON)[0]["s"]

    rows = run(Q_BATTERS, season=season)
    group = [b for b in rows if b["s"].get("qualified")]
    ranks = _axis_ranks(group)

    if qualified:
        rows = group
    if team:
        rows = [b for b in rows if b["team"] == team]

    key = SORTS[sort]
    rows = [b for b in rows if b["s"].get(key) is not None]
    rows.sort(key=lambda b: -b["s"][key])
    rows = rows[:limit]

    scenes = {r["player_id"]: r["n"] for r in run(Q_SCENE_COUNTS, season=season, events=GOOD_EVENTS, confirmed=CONFIRMED)}
    league_avg, hr_scenes = None, {}
    if sort in AXES:  # 지표로 정렬하면 05 능력별 순위: 비교 대상 평균 원 수치 + 대표 장면(그 시즌 최근 홈런 장면)
        vk = LEADER_VALUE[sort][0]
        vals = [b["s"][vk] for b in group if b["s"].get(vk) is not None]
        league_avg = _round(sum(vals) / len(vals), 4) if vals else None
        hr_scenes = {r["player_id"]: {**scene_of(r), "pa_id": r["pa_id"], "date": r["date"], "hr_seq": r["hr_seq"]}
                     for r in run(Q_LATEST_HR_SCENES, ids=[b["player_id"] for b in rows], season=season, confirmed=CONFIRMED)}

    batters = []
    for i, b in enumerate(rows, 1):
        s = b["s"]
        r = ranks.get(b["player_id"])  # 비교 대상이 아니면 None
        best = sorted(r.items(), key=lambda x: x[1])[:2] if r else []
        batters.append({
            "rank": i,
            "player_id": b["player_id"],
            "name": b["name"],
            "team": b["team"],
            "position": b["position"],
            "back_number": b["back_number"],
            "bats_throws": b["bats_throws"],
            "qualified": bool(s.get("qualified")),
            "games": b["games"],
            "pa": s.get("pa"),
            "avg": None if s.get("avg") is None else round(s["avg"], 3),
            "hr": s.get("hr"),
            "ops": None if s.get("ops") is None else round(s["ops"], 3),
            # 실제 수치 (시안 「실제 수치 보기」 · 「100명 평균」 · 팀 화면 표)
            **{k: s.get(k) for k in ("ab", "h", "b2", "b3", "bb", "hbp", "sf", "so")},
            **{k: None if s.get(k) is None else round(s[k], 4) for k in ("obp", "slg", "iso", "k_pct", "bb_pct", "ops_sd")},
            "percentiles": {a: (None if s.get(k) is None else int(s[k])) for a, k in AXES.items()} if r else None,
            "axis_ranks": r,                                    # {"power": 2, ...} 또는 null
            "strengths": [{"axis": a, "rank": n} for a, n in best],  # 잘하는 것 2개
            "scene_count": scenes.get(b["player_id"], 0),           # 장면 수 (선수 화면 장면 탭과 같은 기준)
            **({"scene": hr_scenes.get(b["player_id"])} if sort in AXES else {}),  # 대표 장면 (없으면 null)
        })

    return {
        "season": season,
        "sort": sort,
        "group_size": len(group),  # 비교 대상 인원 (시안 '100명 중'의 100 자리)
        "league_avg": league_avg,  # 지표로 정렬했을 때 비교 대상 평균 원 수치(LEADER_VALUE), 아니면 null
        "batters": batters,
    }


# ------------------------------------------------------------------ 18. 지표별 상위 n명
LEADER_VALUE = {  # 지표: (화면에 보여줄 실제 기록, 그 이름)
    "contact": ("k_pct", "삼진 비율"),
    "hit": ("avg", "타율"),
    "power": ("iso", "순수 장타력"),
    "eye": ("bb_pct", "볼넷 비율"),
    "consistency": ("ops_sd", "월별 OPS 표준편차"),
}


@router.get("/leaders", summary="18. 지표별 상위 타자 (메인)")
def get_leaders(  # API 18: 백분위 5개 지표마다 리그 상위 n명을 한 번에
    season: int | None = Query(None, description="생략하면 가장 최근 시즌"),
    limit: int = Query(3, ge=1, le=20, description="지표마다 몇 명"),
):
    if season is None:
        season = run(Q_LATEST_STAT_SEASON)[0]["s"]

    group = [b for b in run(Q_BATTERS, season=season) if b["s"].get("qualified")]
    by_id = {b["player_id"]: b for b in group}
    ranks = _axis_ranks(group)

    leaders = {}
    for axis, (value_key, label) in LEADER_VALUE.items():
        top = sorted(
            [(pid, r[axis]) for pid, r in ranks.items() if axis in r], key=lambda x: x[1]
        )[:limit]
        leaders[axis] = {
            "label": label,
            "players": [
                {
                    "rank": rank,
                    "player_id": pid,
                    "name": by_id[pid]["name"],
                    "team": by_id[pid]["team"],
                    "position": by_id[pid]["position"],
                    "value": None if by_id[pid]["s"].get(value_key) is None
                             else round(by_id[pid]["s"][value_key], 3),
                    "percentile": int(by_id[pid]["s"][AXES[axis]]),
                }
                for pid, rank in top
            ],
        }

    return {"season": season, "group_size": len(group), "leaders": leaders}


# ------------------------------------------------------------------ 26. 투수 목록 · 29. 투수 지표별 상위
Q_PITCHERS = """
MATCH (p:Player)-[:HAS_PITCHING_STAT]->(s:PitcherSeasonStat {season: $season})
OPTIONAL MATCH (p)-[f:PLAYS_FOR {season: $season}]->(t:Team)
WITH p, s, t, f ORDER BY f.last_date DESC
WITH p, s, head(collect(t.name)) AS team
RETURN p.player_id AS player_id, p.name AS name, p.back_number AS back_number, p.bats_throws AS bats_throws, team,
       s {.*} AS s
ORDER BY s.outs DESC
"""

# 투수마다 그 시즌 등판 장면 수 (메인 순위 「장면 n」). 선수 화면 「등판」 탭 「장면 있음」(API-36)과 같은 기준:
# 확정 · 재생 가능한 장면이 있는 등판 수 (영상 수가 아니라 등판 수), 정규 · 포스트시즌 함께
Q_PITCHER_SCENE_COUNTS = """
MATCH (p:Player)-[:PITCHED_GAME]->(o:Outing {season: $season})
WHERE EXISTS { (o)-[m:MATCHED_TO]->(v:VideoLink) WHERE m.status IN $confirmed AND coalesce(v.playable, true) }
RETURN p.player_id AS player_id, count(o) AS n
"""

# 지표 옆 ▶ = 그 지표 태그가 붙은 확정 등판 장면 중 가장 최근 것 (API-02 axes[].scene과 같은 기준, 장면.md 6장)
Q_PITCHER_AXIS_SCENES = """
UNWIND $ids AS pid
CALL (pid) {
  MATCH (:Player {player_id: pid})-[:PITCHED_GAME]->(o:Outing {season: $season, game_type: 'regular'})-[m:MATCHED_TO]->(v:VideoLink)
  WHERE m.status IN $confirmed AND coalesce(v.playable, true) AND $tag IN coalesce(m.tags, [])
  RETURN o, m, v ORDER BY o.date DESC, m.rank LIMIT 1
}
RETURN pid AS player_id, o.outing_id AS outing_id, o.date AS date, o {.outs, .so, .r, .h} AS line,
       v.video_id AS video_id, v.title AS title, v.duration_sec AS duration_sec,
       m.start_sec AS start_sec, m.end_sec AS end_sec, m.precision AS precision, m.scene_type AS scene_type,
       coalesce(m.tags, []) AS tags
"""

P_AXES = {key: (label, prop, metric, reverse, pct) for key, label, prop, metric, reverse, pct in PITCH_AXES}
P_SORTS = Literal["outs", "whip", "avg", "so", "strikeout", "control", "chase", "hit_prevention", "power_prevention"]


def _pitcher_rows(season: int) -> list[dict]:
    return run(Q_PITCHERS, season=season)


def _pitch_axis_ranks(rows: list[dict]) -> dict:
    """비교 대상(규정이닝 · 같은 역할) 안에서 지표별 등수. 등수 = 백분위가 나보다 높은 사람 수 + 1 (API-02와 같음)"""
    ranks: dict = {}
    for role in {r["s"].get("role") for r in rows}:
        group = [r for r in rows if r["s"].get("qualified") and r["s"].get("role") == role]
        for key, (_, _, _, _, pct) in P_AXES.items():
            vals = [r["s"][pct] for r in group if r["s"].get(pct) is not None]
            for r in group:
                p = r["s"].get(pct)
                if p is not None:
                    ranks.setdefault(r["player_id"], {})[key] = 1 + sum(1 for v in vals if v > p)
    return ranks


def _round(v, n):
    return None if v is None else round(v, n)


@router.get("/pitchers", summary="26. 투수 목록 (팀 화면 · 능력별 순위)")
def get_pitchers(  # API 26: 그 시즌 투수 기록. 기본은 이닝 많은 순 (팀 화면 투수 표)
    season: int | None = Query(None, description="생략하면 가장 최근 시즌"),
    team: str | None = Query(None, description="팀 이름 (예: KIA). 생략하면 리그 전체"),
    role: Literal["starter", "reliever"] | None = Query(None, description="선발 · 불펜. 생략하면 모두"),
    qualified: bool = Query(False, description="true면 리그 비교 대상(규정이닝)만"),
    sort: P_SORTS = Query("outs", description="outs · so는 많은 순, whip · avg는 낮은 순, 지표 5개는 백분위 높은 순"),
    limit: int = Query(500, ge=1, le=1000),
):
    if season is None:
        season = run(Q_LATEST_STAT_SEASON)[0]["s"]
    all_rows = _pitcher_rows(season)
    ranks = _pitch_axis_ranks(all_rows)
    rows = [r for r in all_rows
            if (team is None or r["team"] == team)
            and (role is None or r["s"].get("role") == role)
            and (not qualified or r["s"].get("qualified"))]

    league_avg = None
    if sort in P_AXES:
        pct = P_AXES[sort][4]
        rows = [r for r in rows if r["s"].get(pct) is not None]
        rows.sort(key=lambda r: -r["s"][pct])
        prop = P_AXES[sort][1]
        group = [r["s"][prop] for r in all_rows if r["s"].get("qualified") and r["s"].get(prop) is not None
                 and (role is None or r["s"].get("role") == role)]
        league_avg = _round(sum(group) / len(group), 4) if group else None  # 시안 05 「리그 평균 20.0%」
    elif sort in ("whip", "avg"):
        rows = [r for r in rows if r["s"].get(sort) is not None]
        rows.sort(key=lambda r: r["s"][sort])
    else:
        rows.sort(key=lambda r: -(r["s"].get(sort) or 0))
    rows = rows[:limit]

    scenes = {r["player_id"]: r["n"] for r in run(Q_PITCHER_SCENE_COUNTS, season=season, confirmed=CONFIRMED)}
    axis_scenes = {}
    if sort in AXIS_TAGS:  # 지표 옆 ▶가 있는 지표(탈삼진 · 제구 · 안타 억제)로 정렬했을 때만
        for r in run(Q_PITCHER_AXIS_SCENES, ids=[x["player_id"] for x in rows], season=season,
                     tag=AXIS_TAGS[sort], confirmed=CONFIRMED):
            axis_scenes[r["player_id"]] = {**scene_of(r), "outing_id": r["outing_id"], "date": r["date"], "line": r["line"]}
    elif sort in P_AXES:  # 태그가 없는 지표(유인 · 장타 억제)는 대표 장면 = 그 시즌 최근 확정 등판 장면 (장면.md 6장)
        for r in run(Q_LATEST_OUTING_SCENES, ids=[x["player_id"] for x in rows], season=season, confirmed=CONFIRMED):
            axis_scenes[r["player_id"]] = {**scene_of(r), "outing_id": r["outing_id"], "date": r["date"], "line": r["line"]}

    out = []
    for i, r in enumerate(rows, 1):
        s = r["s"]
        q = bool(s.get("qualified"))
        out.append({"rank": i, "player_id": r["player_id"], "name": r["name"], "team": r["team"], "back_number": r["back_number"],
                    "bats_throws": r["bats_throws"], "role": s.get("role"), "qualified": q,
                    **{k: s.get(k) for k in ("g", "gs", "outs", "tbf", "h", "hr", "bb", "hbp", "so", "r")},
                    "avg": _round(s.get("avg"), 3),
                    "whip": _round(s.get("whip"), 2),
                    "metrics": {k: _round(s.get(a[1]), 4) for k, a in P_AXES.items()},             # 지표 원 수치 (k_pct 등)
                    "percentiles": {k: (None if s.get(a[4]) is None else int(s[a[4]])) for k, a in P_AXES.items()} if q else None,
                    "axis_ranks": ranks.get(r["player_id"]),                                       # 같은 역할 비교 대상 안 등수
                    "scene_count": scenes.get(r["player_id"], 0),                                  # 장면이 있는 등판 수 (등판 탭 「장면 있음」과 같음)
                    **({"scene": axis_scenes.get(r["player_id"])} if sort in P_AXES else {})})  # 그 지표 대표 장면 (없으면 null)

    group_size = sum(1 for r in all_rows if r["s"].get("qualified") and (role is None or r["s"].get("role") == role))
    return {"season": season, "sort": sort, "role": role,
            "group_size": group_size,   # 비교 대상 인원 (시안 「선발 46명 중」)
            "league_avg": league_avg,   # 지표로 정렬했을 때 비교 대상 평균 원 수치, 아니면 null
            "pitchers": out}


@router.get("/pitchers/leaders", summary="29. 투수 지표별 상위 (메인)")
def get_pitcher_leaders(  # API 29: 투수 5지표마다 비교 대상 상위 n명 (API-18의 투수판)
    season: int | None = Query(None, description="생략하면 가장 최근 시즌"),
    role: Literal["starter", "reliever"] = Query("starter", description="비교 대상 역할 (시안 메인은 선발)"),
    limit: int = Query(3, ge=1, le=20, description="지표마다 몇 명"),
):
    if season is None:
        season = run(Q_LATEST_STAT_SEASON)[0]["s"]
    group = [r for r in _pitcher_rows(season) if r["s"].get("qualified") and r["s"].get("role") == role]
    ranks = _pitch_axis_ranks(group)
    leaders = {}
    for key, (label, prop, metric, reverse, pct) in P_AXES.items():
        top = sorted([r for r in group if r["s"].get(pct) is not None], key=lambda r: -r["s"][pct])[:limit]
        leaders[key] = {
            "label": label, "metric": metric, "reverse": reverse,  # reverse = 원 수치가 낮을수록 좋음
            "players": [{"rank": ranks[r["player_id"]][key], "player_id": r["player_id"], "name": r["name"],
                         "team": r["team"], "value": _round(r["s"].get(prop), 4), "percentile": int(r["s"][pct])}
                        for r in top],
        }
    return {"season": season, "role": role, "group_size": len(group), "leaders": leaders}


# ------------------------------------------------------------------ 31. 비슷한 선수
# 카드 ▶ = 대표 장면 (장면.md 6장): 타자는 그 시즌 확정 홈런 장면 중 최근, 투수는 확정 등판 장면 중 최근
Q_LATEST_HR_SCENES = """
UNWIND $ids AS pid
CALL (pid) {
  MATCH (:Player {player_id: pid})-[:BATTED_IN]->(pa:PlateAppearance {season: $season, game_type: 'regular', events: 'home_run'})-[m:MATCHED_TO]->(v:VideoLink)
  WHERE m.status IN $confirmed AND coalesce(m.precision, 'scene') <> 'game' AND coalesce(v.playable, true)
  RETURN pa, m, v ORDER BY pa.date DESC, pa.at_bat_number DESC, m.rank LIMIT 1
}
RETURN pid AS player_id, pa.pa_id AS pa_id, toString(pa.date) AS date, pa.hr_seq AS hr_seq,
       v.video_id AS video_id, v.title AS title, v.duration_sec AS duration_sec,
       m.start_sec AS start_sec, m.end_sec AS end_sec, coalesce(m.precision, 'scene') AS precision,
       m.scene_type AS scene_type, coalesce(m.tags, []) AS tags
"""

Q_LATEST_OUTING_SCENES = """
UNWIND $ids AS pid
CALL (pid) {
  MATCH (:Player {player_id: pid})-[:PITCHED_GAME]->(o:Outing {season: $season, game_type: 'regular'})-[m:MATCHED_TO]->(v:VideoLink)
  WHERE m.status IN $confirmed AND coalesce(v.playable, true)
  RETURN o, m, v ORDER BY o.date DESC, m.rank LIMIT 1
}
RETURN pid AS player_id, o.outing_id AS outing_id, o.date AS date, o {.outs, .so, .r, .h} AS line,
       v.video_id AS video_id, v.title AS title, v.duration_sec AS duration_sec,
       m.start_sec AS start_sec, m.end_sec AS end_sec, m.precision AS precision, m.scene_type AS scene_type,
       coalesce(m.tags, []) AS tags
"""

BAT_AXIS_LABEL = {"contact": "삼진회피", "hit": "안타생산", "power": "파워", "eye": "선구안", "consistency": "꾸준함"}


def _neighbors(order: list[str], me: str, n: int) -> list[str]:
    """지표 순위(order, 1위부터)에서 나보다 바로 위 선수를 먼저, 모자라면 바로 아래로 n명. 결과는 순위 순"""
    i = order.index(me)
    above = order[max(0, i - n):i]
    below = order[i + 1:i + 1 + (n - len(above))]
    return above + below


@router.get("/players/{player_id}/similar", summary="31. 비슷한 선수 (가장 강한 지표 기준)")
def get_similar(  # API 31: 시안 03 「파워가 비슷한 타자」 · 03b 「장타를 잘 안 맞는 비슷한 투수」
    player_id: str,
    season: int | None = Query(None, description="생략하면 가장 최근 시즌"),
    as_: Literal["batter", "pitcher"] | None = Query(None, alias="as", description="생략하면 그 시즌 비교 대상인 쪽 (둘 다면 상대 타자 수 > 타석 수일 때 투수)"),
    limit: int = Query(4, ge=1, le=10),
):
    if season is None:
        season = run(Q_LATEST_STAT_SEASON)[0]["s"]
    batters = [b for b in run(Q_BATTERS, season=season) if b["s"].get("qualified")]
    pitchers = [r for r in _pitcher_rows(season) if r["s"].get("qualified")]
    me_b = next((b for b in batters if b["player_id"] == player_id), None)
    me_p = next((r for r in pitchers if r["player_id"] == player_id), None)
    if as_ is None:
        as_ = "pitcher" if me_p and (not me_b or (me_p["s"].get("tbf") or 0) > (me_b["s"].get("pa") or 0)) else "batter"
    empty = {"season": season, "as": as_, "axis": None, "label": None, "players": []}

    if as_ == "batter":
        if not me_b:
            return {**empty, "reason": "리그 비교 대상 아님(타석 부족)"}
        pct = {a: me_b["s"].get(k) for a, k in AXES.items() if me_b["s"].get(k) is not None}
        axis = max(pct, key=lambda a: pct[a])  # 가장 강한 점 (같으면 지표 순서 앞)
        ranks = _axis_ranks(batters)
        order = [b["player_id"] for b in sorted([b for b in batters if b["s"].get(AXES[axis]) is not None],
                                                  key=lambda b: (ranks[b["player_id"]][axis], b["player_id"]))]
        by_id = {b["player_id"]: b for b in batters}
        picked = _neighbors(order, player_id, limit)
        scenes = {r["player_id"]: {**scene_of(r), "pa_id": r["pa_id"], "date": r["date"], "hr_seq": r["hr_seq"]}
                  for r in run(Q_LATEST_HR_SCENES, ids=picked, season=season, confirmed=CONFIRMED)}
        value_key, value_label = LEADER_VALUE[axis]
        players = [{"player_id": pid, "name": by_id[pid]["name"], "team": by_id[pid]["team"],
                    "rank": ranks[pid][axis], "value": _round(by_id[pid]["s"].get(value_key), 3),
                    "percentile": int(by_id[pid]["s"][AXES[axis]]),
                    "ops": _round(by_id[pid]["s"].get("ops"), 3), "hr": by_id[pid]["s"].get("hr"),
                    "scene": scenes.get(pid)} for pid in picked]
        return {"season": season, "as": as_, "axis": axis, "label": BAT_AXIS_LABEL[axis], "value_label": value_label,
                "my_rank": ranks[player_id][axis], "group_size": len(batters), "players": players}

    if not me_p:
        return {**empty, "reason": "리그 비교 대상 아님(이닝 부족)"}
    role = me_p["s"].get("role")
    group = [r for r in pitchers if r["s"].get("role") == role]
    pct = {k: me_p["s"].get(a[4]) for k, a in P_AXES.items() if me_p["s"].get(a[4]) is not None}
    axis = max(pct, key=lambda k: pct[k])
    label, prop, metric, reverse, pkey = P_AXES[axis]
    ranks = _pitch_axis_ranks(group)
    order = [r["player_id"] for r in sorted([r for r in group if r["s"].get(pkey) is not None],
                                              key=lambda r: (ranks[r["player_id"]][axis], r["player_id"]))]
    by_id = {r["player_id"]: r for r in group}
    picked = _neighbors(order, player_id, limit)
    scenes = {r["player_id"]: {**scene_of(r), "outing_id": r["outing_id"], "date": r["date"], "line": r["line"]}
              for r in run(Q_LATEST_OUTING_SCENES, ids=picked, season=season, confirmed=CONFIRMED)}
    players = [{"player_id": pid, "name": by_id[pid]["name"], "team": by_id[pid]["team"],
                "rank": ranks[pid][axis], "value": _round(by_id[pid]["s"].get(prop), 4),
                "percentile": int(by_id[pid]["s"][pkey]),
                "whip": _round(by_id[pid]["s"].get("whip"), 2), "so": by_id[pid]["s"].get("so"),
                "scene": scenes.get(pid)} for pid in picked]
    return {"season": season, "as": as_, "axis": axis, "label": label, "metric": metric, "reverse": reverse,
            "role": role, "my_rank": ranks[player_id][axis], "group_size": len(group), "players": players}


# ------------------------------------------------------------------ 33. 팀의 최근 장면
# 그 팀 타자의 홈런 장면 + 그 팀 투수의 등판 장면 (잘한 장면만 — 장면.md S8). 타자 팀은 초 = 원정, 말 = 홈
Q_TEAM_HR_SCENES = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance {season: $season, game_type: 'regular', events: 'home_run'})-[:PART_OF]->(g:Game)
MATCH (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
WITH b, pa, g, CASE pa.inning_half WHEN '초' THEN away.name ELSE home.name END AS team,
     CASE pa.inning_half WHEN '초' THEN home.name ELSE away.name END AS opponent
WHERE team = $team
CALL (pa) {
  MATCH (pa)-[m:MATCHED_TO]->(v:VideoLink)
  WHERE m.status IN $confirmed AND coalesce(m.precision, 'scene') <> 'game' AND coalesce(v.playable, true)
  RETURN v, m ORDER BY m.rank, v.published_at LIMIT 1
}
RETURN 'home_run' AS kind, toString(pa.date) AS date, g.dh_no AS dh_no, pa.at_bat_number AS seq, opponent,
       b.player_id AS player_id, b.name AS name, pa.pa_id AS pa_id, pa.hr_seq AS hr_seq, pa.inning AS inning,
       pa.inning_half AS inning_half, pa.runs_scored AS runs, null AS outing_id, null AS line, null AS role,
       v.video_id AS video_id, v.title AS title, v.duration_sec AS duration_sec,
       m.start_sec AS start_sec, m.end_sec AS end_sec, coalesce(m.precision, 'scene') AS precision,
       m.scene_type AS scene_type, coalesce(m.tags, []) AS tags
"""

Q_TEAM_OUTING_SCENES = """
MATCH (t:Team {name: $team})
MATCH (p:Player)-[:PITCHED_GAME]->(o:Outing {season: $season, game_type: 'regular', team_id: t.team_id})-[:PART_OF]->(g:Game)
MATCH (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
CALL (o) {
  MATCH (o)-[m:MATCHED_TO]->(v:VideoLink)
  WHERE m.status IN $confirmed AND coalesce(v.playable, true)
  RETURN v, m ORDER BY m.rank LIMIT 1
}
RETURN 'outing' AS kind, o.date AS date, g.dh_no AS dh_no, 0 AS seq,
       CASE WHEN home.team_id = t.team_id THEN away.name ELSE home.name END AS opponent,
       p.player_id AS player_id, p.name AS name, null AS pa_id, null AS hr_seq, null AS inning, null AS inning_half,
       null AS runs, o.outing_id AS outing_id, o {.outs, .so, .r, .h} AS line,
       CASE WHEN o.starter THEN '선발' ELSE '구원' END AS role,
       v.video_id AS video_id, v.title AS title, v.duration_sec AS duration_sec,
       m.start_sec AS start_sec, m.end_sec AS end_sec, m.precision AS precision, m.scene_type AS scene_type,
       coalesce(m.tags, []) AS tags
"""

Q_TEAM_EXISTS = "MATCH (t:Team {name: $team}) RETURN t.team_id AS id"


@router.get("/teams/{team}/scenes", summary="33. 팀의 최근 장면 (06 팀)")
def get_team_scenes(  # API 33: 그 팀 선수들의 홈런 · 등판 장면, 최신순 + 시즌 장면 수
    team: str,
    season: int | None = Query(None, description="생략하면 가장 최근 시즌"),
    limit: int = Query(12, ge=1, le=100),
):
    if not run(Q_TEAM_EXISTS, team=team):
        raise ApiError(404, "TEAM_NOT_FOUND", "팀을 찾을 수 없습니다")
    if season is None:
        season = run(Q_LATEST_STAT_SEASON)[0]["s"]
    hrs = run(Q_TEAM_HR_SCENES, team=team, season=season, confirmed=CONFIRMED)
    outs = run(Q_TEAM_OUTING_SCENES, team=team, season=season, confirmed=CONFIRMED)
    rows = sorted(hrs + outs, key=lambda r: (r["date"], r["dh_no"] or 0, r["seq"] or 0), reverse=True)
    scenes = []
    for r in rows[:limit]:
        item = {"kind": r["kind"], "date": r["date"], "opponent": r["opponent"],
                "player": {"player_id": r["player_id"], "name": r["name"]}, "scene": scene_of(r)}
        if r["kind"] == "home_run":
            item.update({"pa_id": r["pa_id"], "hr_seq": r["hr_seq"], "inning": r["inning"],
                         "inning_half": r["inning_half"], "runs": r["runs"]})
        else:
            item.update({"outing_id": r["outing_id"], "role": r["role"], "line": r["line"]})  # 「6이닝 8K 무실점」 재료
        scenes.append(item)
    return {"team": team, "season": season,
            "counts": {"home_run_scenes": len(hrs), "pitcher_scenes": len(outs), "total": len(hrs) + len(outs)},
            "scenes": scenes}


# ------------------------------------------------------------------ 35. 팀의 최근 경기
Q_TEAM_GAMES = """
MATCH (t:Team {name: $team})
MATCH (g:Game {season: $season})-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
WHERE home = t OR away = t
RETURN g.game_pk AS game_pk, toString(g.date) AS date, g.dh_no AS dh_no, g.innings AS innings,
       g.game_type AS game_type, g.stage AS stage, g.series_game_no AS series_game_no,
       home = t AS is_home, CASE WHEN home = t THEN away.name ELSE home.name END AS opponent,
       CASE WHEN home = t THEN g.home_final ELSE g.away_final END AS score,
       CASE WHEN home = t THEN g.away_final ELSE g.home_final END AS opp_score
ORDER BY g.date DESC, g.dh_no DESC
LIMIT $limit
"""


@router.get("/teams/{team}/games", summary="35. 팀의 최근 경기 (06 팀)")
def get_team_games(  # API 35: 시안 06 「최근 경기」 카드 5장 — 날짜 · 홈/원정 · 상대 · 점수 · 승패 · 경기 하이라이트
    team: str,
    season: int | None = Query(None, description="생략하면 가장 최근 시즌"),
    limit: int = Query(5, ge=1, le=30),
):
    if not run(Q_TEAM_EXISTS, team=team):
        raise ApiError(404, "TEAM_NOT_FOUND", "팀을 찾을 수 없습니다")
    if season is None:
        season = run(Q_LATEST_STAT_SEASON)[0]["s"]
    rows = run(Q_TEAM_GAMES, team=team, season=season, limit=limit)
    highlights = game_highlights([r["game_pk"] for r in rows])
    games = [{"game_pk": r["game_pk"], "date": r["date"], "dh_no": r["dh_no"], "innings": r["innings"], **game_tag(r),
              "home": r["is_home"], "opponent": r["opponent"], "score": {"team": r["score"], "opponent": r["opp_score"]},
              "result": result_of(r["score"], r["opp_score"]),
              "highlight": highlights.get(r["game_pk"])}
             for r in rows]
    return {"team": team, "season": season, "games": games}
