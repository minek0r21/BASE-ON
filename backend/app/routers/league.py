"""
리그 API (시안 메인·팀 화면)
  13. GET /standings?season=                                  팀 순위
  16. GET /batters?season=&team=&sort=&qualified=&limit=       타자 순위표 (리그 상위 타자, 팀 선수 목록)
  18. GET /leaders?season=&limit=                              지표 5개별 상위 n명 (메인 '이런 타자는 어때요?')
  26. GET /pitchers?season=&team=&role=&qualified=&sort=&limit= 투수 목록 (팀 화면 투수 표, 05 능력별 순위 투수 탭)
  28. GET /standings/history?season=                           순위 변동 (달마다 마지막 날 순위, 시안 「순위 변동 보기」)
  29. GET /pitchers/leaders?season=&role=&limit=               투수 지표 5개별 상위 n명 (메인 능력 카드 「투수」)
"""
from typing import Literal

from fastapi import APIRouter, Query

from ..db import run
from ..errors import ApiError
from ..scenes import CONFIRMED, scene_of
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

# 선수마다 그 시즌 승인된 장면(영상) 수 — 카드의 '장면 N' 표시
Q_SCENE_COUNTS = """
MATCH (p:Player)-[:BATTED_IN]->(:PlateAppearance {season: $season, game_type: 'regular'})-[m:MATCHED_TO]->(v:VideoLink)
WHERE m.status IN ['auto_confirmed', 'approved']
RETURN p.player_id AS player_id, count(DISTINCT v) AS n
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

    scenes = {r["player_id"]: r["n"] for r in run(Q_SCENE_COUNTS, season=season)}

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
            "scene_count": scenes.get(b["player_id"], 0),           # 확정 장면 수 (자동 확정·승인)
        })

    return {
        "season": season,
        "sort": sort,
        "group_size": len(group),  # 비교 대상 인원 (시안 '100명 중'의 100 자리)
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

# 투수마다 그 시즌 확정 등판 장면 수 (메인 순위 「장면 n」)
Q_PITCHER_SCENE_COUNTS = """
MATCH (p:Player)-[:PITCHED_GAME]->(:Outing {season: $season, game_type: 'regular'})-[m:MATCHED_TO]->(v:VideoLink)
WHERE m.status IN $confirmed AND coalesce(v.playable, true)
RETURN p.player_id AS player_id, count(DISTINCT v) AS n
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
                    "scene_count": scenes.get(r["player_id"], 0),                                  # 그 시즌 확정 등판 장면 수
                    **({"scene": axis_scenes.get(r["player_id"])} if sort in AXIS_TAGS else {})})  # 그 지표 대표 장면 (없으면 null)

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


# ------------------------------------------------------------------ 28. 순위 변동
Q_SEASON_RESULTS = """
MATCH (g:Game {season: $season, game_type: 'regular'})-[:HOME]->(h:Team), (g)-[:AWAY]->(a:Team)
RETURN toString(g.date) AS date, h.name AS home, a.name AS away, g.home_final AS hs, g.away_final AS as_
ORDER BY date
"""


@router.get("/standings/history", summary="28. 순위 변동 (달마다)")
def get_standings_history(season: int = Query(..., description="시즌")):
    rows = run(Q_SEASON_RESULTS, season=season)
    if not rows:
        raise ApiError(404, "SEASON_NOT_FOUND", f"{season} 시즌 경기가 없습니다")
    rec: dict = {}
    marks = []
    last_month = None

    def snapshot(label, date):
        teams = sorted(rec, key=lambda t: (-(rec[t]["w"] / max(1, rec[t]["w"] + rec[t]["l"])), -rec[t]["w"]))
        marks.append({"label": label, "date": date, "ranks": {t: i + 1 for i, t in enumerate(teams)}})

    for i, r in enumerate(rows):
        for t, mine, opp in ((r["home"], r["hs"], r["as_"]), (r["away"], r["as_"], r["hs"])):
            x = rec.setdefault(t, {"w": 0, "l": 0, "g": 0})
            x["g"] += 1
            if mine > opp:
                x["w"] += 1
            elif mine < opp:
                x["l"] += 1
        month = int(r["date"][5:7])
        nxt = rows[i + 1]["date"] if i + 1 < len(rows) else None
        if nxt is None:
            done = all(x["g"] >= 144 for x in rec.values())
            snapshot("최종" if done else f"{month}.{int(r['date'][8:10])}", r["date"])
        elif int(nxt[5:7]) != month and month >= 4:  # 3월(개막 몇 경기)은 4월에 합친다
            snapshot(f"{month}월", r["date"])
    return {"season": season, "checkpoints": marks}
