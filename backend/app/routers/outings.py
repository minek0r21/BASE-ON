"""
등판(투수 × 경기) API — docs/장면.md 7장
  23. GET /players/{player_id}/outings?season=&month=   투수 경기 기록: 등판 목록 + 등판 장면 + 경기 하이라이트
  24. GET /outings/{outing_id}/video                    등판의 확정 장면 (보너스층)
"""
from fastapi import APIRouter, Query

from ..db import run
from ..errors import ApiError
from ..postseason import game_tag
from ..scenes import CONFIRMED, game_highlights, outing_scenes, scene_of
from ..utils import result_of, weekday_ko

router = APIRouter(tags=["등판"])

Q_OUTING_MONTHS = """
MATCH (:Player {player_id: $id})-[:PITCHED_GAME]->(o:Outing)
RETURN o.season AS season, collect(DISTINCT toInteger(substring(o.date, 5, 2))) AS months
"""

Q_OUTINGS = """
MATCH (:Player {player_id: $id})-[:PITCHED_GAME]->(o:Outing {season: $season})-[:PART_OF]->(g:Game)
WHERE toInteger(substring(o.date, 5, 2)) = $month
MATCH (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
WITH o, g, home, away, COUNT { (:Player {player_id: $id})-[:PITCHED_IN]->(x:PlateAppearance)-[:PART_OF]->(g) } AS n,
     reduce(s = 0, x IN [(:Player {player_id: $id})-[:PITCHED_IN]->(q:PlateAppearance)-[:PART_OF]->(g) | coalesce(q.pitch_count, 0)] | s + x) AS pitches
RETURN o {.outing_id, .date, .team_id, .outs, .tbf, .so, .bb, .hbp, .h, .hr, .r, .starter, .finisher} AS o, pitches,
       g.game_pk AS game_pk, g.dh_no AS dh_no, g.home_final AS home_final, g.away_final AS away_final,
       g.game_type AS game_type, g.stage AS stage, g.series_game_no AS series_game_no,
       home.team_id AS home_id, home.name AS home, away.name AS away
ORDER BY o.date DESC, g.dh_no DESC
"""


@router.get("/players/{player_id}/outings", summary="23. 투수 경기 기록 (등판 목록)")
def get_player_outings(  # API 23: 시즌·월 + 그 달 등판
    player_id: str,
    season: int | None = Query(None, description="생략하면 이 투수가 던진 가장 최근 시즌"),
    month: int | None = Query(None, ge=1, le=12, description="생략하면 그 시즌 가장 최근 달"),
):
    by_season = {r["season"]: sorted(r["months"]) for r in run(Q_OUTING_MONTHS, id=player_id) if r["season"]}
    seasons = sorted(by_season)
    if not seasons:
        return {"seasons": [], "season": None, "months": [], "month": None, "outings": []}
    if season is None:
        season = seasons[-1]
    elif season not in by_season:
        raise ApiError(404, "SEASON_NOT_FOUND", f"{season} 시즌에 등판 기록이 없습니다")
    months = by_season[season]
    if month is None:
        month = months[-1]
    elif month not in months:
        raise ApiError(404, "MONTH_NOT_FOUND", f"{season}년 {month}월에 등판 기록이 없습니다")

    rows = run(Q_OUTINGS, id=player_id, season=season, month=month)
    scenes = outing_scenes([r["o"]["outing_id"] for r in rows])
    highlights = game_highlights([r["game_pk"] for r in rows])
    out = []
    for r in rows:
        o = r["o"]
        home = o["team_id"] == r["home_id"]
        team_score = r["home_final"] if home else r["away_final"]
        opp_score = r["away_final"] if home else r["home_final"]
        out.append({
            "outing_id": o["outing_id"], "game_pk": r["game_pk"], "date": o["date"], "weekday": weekday_ko(o["date"]),
            **game_tag(r),  # 포스트시즌 등판이면 「KS 3차전」 꼬리표 (PS3)
            "opponent": r["away"] if home else r["home"], "home": home,
            "score": {"team": team_score, "opponent": opp_score}, "result": result_of(team_score, opp_score),
            "role": "선발" if o["starter"] else "구원",
            "line": {**{k: o[k] for k in ("outs", "tbf", "so", "bb", "hbp", "h", "hr", "r")}, "pitches": r["pitches"]},  # 투구 수 = 타석 투구 수 합
            "scene": scenes.get(o["outing_id"]),         # 보너스층: 이 등판의 확정 장면 (없으면 null)
            "highlight": highlights.get(r["game_pk"]),   # 기본층: 이 경기 하이라이트
        })
    return {"seasons": seasons, "season": season, "months": months, "month": month, "outings": out}


Q_OUTING_VIDEOS = """
MATCH (o:Outing {outing_id: $id})
OPTIONAL MATCH (o)-[m:MATCHED_TO]->(v:VideoLink)
WHERE m.status IN $confirmed AND coalesce(v.playable, true)
WITH o, m, v ORDER BY m.rank
RETURN o.outing_id AS outing_id,
       collect(CASE WHEN v IS NULL THEN null ELSE {video_id: v.video_id, title: v.title, duration_sec: v.duration_sec,
               start_sec: m.start_sec, end_sec: m.end_sec, precision: m.precision, scene_type: m.scene_type,
               tags: coalesce(m.tags, [])} END) AS videos
"""


@router.get("/outings/{outing_id}/video", summary="24. 등판의 확정 장면")
def get_outing_video(outing_id: str):  # API 24
    rows = run(Q_OUTING_VIDEOS, id=outing_id, confirmed=CONFIRMED)
    if not rows:
        raise ApiError(404, "OUTING_NOT_FOUND", "등판을 찾을 수 없습니다")
    return {"outing_id": outing_id, "videos": [scene_of(v) for v in rows[0]["videos"]]}
