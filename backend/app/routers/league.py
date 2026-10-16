"""
리그 API (시안 메인·팀 화면)
  13. GET /standings?season=                                  팀 순위
  16. GET /batters?season=&team=&sort=&qualified=&limit=       타자 순위표 (리그 상위 타자, 팀 선수 목록)
  18. GET /leaders?season=&limit=                              지표 5개별 상위 n명 (메인 '이런 타자는 어때요?')
"""
from typing import Literal

from fastapi import APIRouter, Query

from ..db import run
from ..errors import ApiError

router = APIRouter(tags=["리그"])


# ------------------------------------------------------------------ 13. 팀 순위
Q_SEASONS = "MATCH (g:Game) RETURN DISTINCT g.season AS season ORDER BY season"

Q_SEASON_GAMES = """
MATCH (g:Game {season: $season})-[:HOME]->(h:Team), (g)-[:AWAY]->(a:Team)
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
MATCH (p:Player)-[:BATTED_IN]->(:PlateAppearance {season: $season})-[:MATCHED_TO {status: 'approved'}]->(v:VideoLink)
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
