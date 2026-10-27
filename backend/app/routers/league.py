"""
리그 API (시안 메인·팀 화면)
  13. GET /standings?season=                                  팀 순위
  16. GET /batters?season=&team=&sort=&qualified=&limit=       타자 순위표 (리그 상위 타자, 팀 선수 목록)
  18. GET /leaders?season=&limit=                              지표 5개별 상위 n명 (메인 '이런 타자는 어때요?')
  26. GET /pitchers?season=&team=&limit=                       투수 목록 (팀 화면 투수 표)
  28. GET /standings/history?season=                           순위 변동 (달마다 마지막 날 순위, 시안 「순위 변동 보기」)
"""
from typing import Literal

from fastapi import APIRouter, Query

from ..db import run
from ..errors import ApiError

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
            "scene_count": scenes.get(b["player_id"], 0),           # 승인된 장면 수
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


# ------------------------------------------------------------------ 26. 투수 목록
Q_PITCHERS = """
MATCH (p:Player)-[:HAS_PITCHING_STAT]->(s:PitcherSeasonStat {season: $season})
OPTIONAL MATCH (p)-[f:PLAYS_FOR {season: $season}]->(t:Team)
WITH p, s, t, f ORDER BY f.last_date DESC
WITH p, s, head(collect(t.name)) AS team
WHERE $team IS NULL OR team = $team
RETURN p.player_id AS player_id, p.name AS name, p.back_number AS back_number, p.bats_throws AS bats_throws, team,
       s {.g, .gs, .outs, .tbf, .h, .hr, .bb, .hbp, .so, .r, .avg, .whip, .role, .qualified} AS s
ORDER BY s.outs DESC
LIMIT $limit
"""


@router.get("/pitchers", summary="26. 투수 목록 (팀 화면)")
def get_pitchers(  # API 26: 그 시즌 투수 기록, 이닝 많은 순
    season: int | None = Query(None, description="생략하면 가장 최근 시즌"),
    team: str | None = Query(None, description="팀 이름 (예: KIA). 생략하면 리그 전체"),
    limit: int = Query(500, ge=1, le=1000),
):
    if season is None:
        season = run(Q_LATEST_STAT_SEASON)[0]["s"]
    out = []
    for r in run(Q_PITCHERS, season=season, team=team, limit=limit):
        s = r["s"]
        out.append({"player_id": r["player_id"], "name": r["name"], "team": r["team"], "back_number": r["back_number"],
                    "bats_throws": r["bats_throws"], "role": s.get("role"), "qualified": bool(s.get("qualified")),
                    **{k: s.get(k) for k in ("g", "gs", "outs", "tbf", "h", "hr", "bb", "hbp", "so", "r")},
                    "avg": None if s.get("avg") is None else round(s["avg"], 3),
                    "whip": None if s.get("whip") is None else round(s["whip"], 2)})
    return {"season": season, "pitchers": out}


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
