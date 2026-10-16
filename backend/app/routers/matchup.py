"""
매치업 API
   6. GET /matchup?batter=&pitcher=&season=          타자 1명 vs 투수 1명 맞대결
  17. GET /players/{player_id}/matchups?season=&min_pa=  이 타자가 상대한 투수 전체 (시안 맞대결 탭)
"""
from fastapi import APIRouter, Query

from ..db import run
from ..errors import ApiError
from ..events import batting_line, events_ko
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
OPTIONAL MATCH (pa)-[m:MATCHED_TO {status: 'approved'}]->(:VideoLink)
RETURN pa.pa_id AS pa_id, toString(pa.date) AS date, pa.inning AS inning,
       pa.inning_half AS inning_half, pa.events AS events, count(m) > 0 AS has_video
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
        "plate_appearances": [{**r, "events_ko": events_ko(r["events"])} for r in rows],
    }


# ------------------------------------------------------------------ 17. 상대한 투수 전체
Q_VS_PITCHERS = """
MATCH (b:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance)<-[:PITCHED_IN]-(pit:Player)
WHERE $season IS NULL OR pa.season = $season
WITH pit, collect(pa.events) AS events, max(pa.season) AS last_season
WHERE size(events) >= $min_pa
OPTIONAL MATCH (pit)-[f:PLAYS_FOR {season: last_season}]->(t:Team)
WITH pit, events, t ORDER BY f.last_date DESC
WITH pit, events, head(collect(t.name)) AS team
RETURN pit.player_id AS player_id, pit.name AS name, team, events
ORDER BY size(events) DESC, name
"""

Q_EXISTS = "MATCH (p:Player {player_id: $id}) RETURN p.name AS name"


@router.get("/players/{player_id}/matchups", summary="17. 이 타자가 상대한 투수 목록")
def get_vs_pitchers(  # API 17: 타석 많은 투수 순. 투수를 고르면 API 6으로 자세히
    player_id: str,
    season: int | None = Query(None, description="생략하면 전체 시즌 합계"),
    min_pa: int = Query(10, ge=1, description="이 타석 수 이상 상대한 투수만 (시안 기준 10)"),
):
    who = run(Q_EXISTS, id=player_id)
    if not who:
        raise ApiError(404, "PLAYER_NOT_FOUND", "선수를 찾을 수 없습니다")

    pitchers = []
    for r in run(Q_VS_PITCHERS, id=player_id, season=season, min_pa=min_pa):
        line = batting_line(r["events"])
        line["avg"] = avg(line["h"], line["ab"])
        pitchers.append({"player_id": r["player_id"], "name": r["name"], "team": r["team"], **line})

    return {
        "batter": {"player_id": player_id, "name": who[0]["name"]},
        "season": season,
        "min_pa": min_pa,
        "pitchers": pitchers,
    }
