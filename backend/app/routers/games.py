"""
경기 API
   4. GET /games/{game_pk}/plate-appearances?player=   기록 탭: 경기 요약 + 이 선수 타석 목록
  14. GET /games?date=                                 메인: 날짜별 경기 일정 (+ 그 경기 홈런)
  15. GET /home-runs?season=&limit=&video_only=       메인: 최근 홈런 장면 (기본: 확정 장면(자동 확정·승인)이 있는 홈런만)
"""
from datetime import date as Date

from fastapi import APIRouter, Query

from ..db import run
from ..errors import ApiError
from ..events import batting_line, events_ko
from ..postseason import game_tag, hr_label, period
from ..scenes import CONFIRMED, game_highlights
from ..utils import result_of

router = APIRouter(tags=["경기"])


# ------------------------------------------------------------------ 4. 경기별 타석
Q_GAME = """
MATCH (g:Game {game_pk: $game})-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
RETURN g.game_pk AS game_pk, toString(g.date) AS date, g.innings AS innings, g.season AS season,
       g.home_final AS home_final, g.away_final AS away_final,
       g.game_type AS game_type, g.stage AS stage, g.series_game_no AS series_game_no,
       home.name AS home, away.name AS away
"""

Q_GAME_PAS = """
MATCH (:Player {player_id: $player})-[:BATTED_IN]->(pa:PlateAppearance)-[:PART_OF]->(:Game {game_pk: $game})
MATCH (pit:Player)-[:PITCHED_IN]->(pa)
OPTIONAL MATCH (pa)-[m:MATCHED_TO]->(v:VideoLink) WHERE m.status IN $confirmed AND coalesce(m.precision, 'scene') <> 'game'  // 경기 단위 영상은 타석 ▶가 아니다
WITH pa, pit, m, v ORDER BY m.rank
RETURN pa {.pa_id, .pa_no, .at_bat_number, .inning, .inning_half, .events, .runs_scored, .hr_seq, .post_hr_seq,
           .game_type, .on_1b, .on_2b, .on_3b, .outs_when_up, .final_balls, .final_strikes} AS pa,
       pit.player_id AS pitcher_id, pit.name AS pitcher_name,
       count(m) > 0 AS has_video, collect(v.video_id)[0] AS video_id
ORDER BY pa.at_bat_number   // 반환 맵에 at_bat_number가 있어야 정렬된다 (없으면 순서가 뒤섞임 — STATUS 알려진 문제)
"""


@router.get("/games/{game_pk}/plate-appearances", summary="4. 경기 요약 + 이 선수 타석 목록")
def get_game_pas(  # API 4: 기록 탭에서 경기를 펼쳤을 때
    game_pk: str,
    player: str = Query(..., description="타석을 볼 선수 ID"),
):
    g = run(Q_GAME, game=game_pk)
    if not g:
        raise ApiError(404, "GAME_NOT_FOUND", "경기를 찾을 수 없습니다")
    g = g[0]

    rows = run(Q_GAME_PAS, game=game_pk, player=player, confirmed=CONFIRMED)
    pas = []
    for r in rows:
        pa = r["pa"]
        pas.append({
            "pa_id": pa["pa_id"],
            "pa_no": pa["pa_no"],
            "inning": pa["inning"],
            "inning_half": pa["inning_half"],
            "events": pa["events"],
            "events_ko": events_ko(pa["events"]),
            "runs_scored": pa["runs_scored"],
            "hr_seq": pa["hr_seq"],
            "post_hr_seq": pa["post_hr_seq"],
            "hr_label": hr_label(g["season"], pa["game_type"], pa["hr_seq"], pa["post_hr_seq"]),  # 「시즌 45호」 · 「2026 포스트시즌 2호」
            "runners": {"on_1b": pa["on_1b"], "on_2b": pa["on_2b"], "on_3b": pa["on_3b"]},
            "outs": pa["outs_when_up"], "count": {"balls": pa["final_balls"], "strikes": pa["final_strikes"]},
            "pitcher": {"player_id": r["pitcher_id"], "name": r["pitcher_name"]},
            "has_video": r["has_video"],
            "video_id": r["video_id"],  # 썸네일용 (재생 구간은 API-05)
        })

    line = batting_line([p["events"] for p in pas])
    return {
        "game": {
            "game_pk": g["game_pk"],
            "date": g["date"],
            **game_tag(g),
            "away": {"team": g["away"], "score": g["away_final"]},
            "home": {"team": g["home"], "score": g["home_final"]},
            "innings": g["innings"],
            "highlight": game_highlights([game_pk]).get(game_pk),  # 기본층 「이 경기 하이라이트」 (없으면 null)
        },
        "line": {"ab": line["ab"], "h": line["h"], "hr": line["hr"], "bb": line["bb"]},
        "plate_appearances": pas,  # 이 경기에 이 선수 타석이 없으면 빈 목록
    }


# ------------------------------------------------------------------ 14. 날짜별 경기 일정
Q_LATEST_DATE = "MATCH (g:Game) RETURN max(g.date) AS d"

Q_DAY_GAMES = """
MATCH (g:Game {date: $date})-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
OPTIONAL MATCH (pa:PlateAppearance {events: 'home_run'})-[:PART_OF]->(g)
OPTIONAL MATCH (b:Player)-[:BATTED_IN]->(pa)
OPTIONAL MATCH (pa)-[m:MATCHED_TO]->(:VideoLink) WHERE m.status IN ['auto_confirmed', 'approved'] AND coalesce(m.precision, 'scene') <> 'game'
WITH g, home, away, pa, b, count(m) > 0 AS has_video
ORDER BY pa.at_bat_number
WITH g, home, away,
     collect(CASE WHEN pa IS NULL THEN NULL ELSE {
         pa_id: pa.pa_id, inning: pa.inning, inning_half: pa.inning_half,
         runs: pa.runs_scored, hr_seq: pa.hr_seq, post_hr_seq: pa.post_hr_seq,
         runners: {on_1b: pa.on_1b, on_2b: pa.on_2b, on_3b: pa.on_3b}, count: {balls: pa.final_balls, strikes: pa.final_strikes}, outs: pa.outs_when_up,
         batter: {player_id: b.player_id, name: b.name}, has_video: has_video
     } END) AS home_runs
RETURN g.game_pk AS game_pk, g.dh_no AS dh_no, g.innings AS innings, g.season AS season,
       g.game_type AS game_type, g.stage AS stage, g.series_game_no AS series_game_no,
       home.name AS home, away.name AS away,
       g.home_final AS home_final, g.away_final AS away_final, home_runs
ORDER BY g.dh_no, home
"""

# 이닝별 점수 · 안타 (시안 경기 일정 점수판). 반 이닝 득점 = 그 반 이닝 마지막 타석 뒤 점수 − 첫 타석 앞 점수
Q_LINES = """
UNWIND $games AS gpk
MATCH (pa:PlateAppearance)-[:PART_OF]->(:Game {game_pk: gpk})
WITH gpk, pa.inning AS inn, pa.inning_half AS half,
     min(CASE pa.inning_half WHEN '초' THEN pa.away_score ELSE pa.home_score END) AS pre,
     max(CASE pa.inning_half WHEN '초' THEN pa.post_away_score ELSE pa.post_home_score END) AS post,
     sum(CASE WHEN pa.events IN ['single', 'double', 'triple', 'home_run'] THEN 1 ELSE 0 END) AS h
RETURN gpk, inn, half, post - pre AS runs, h
"""

Q_PREV_NEXT = """
OPTIONAL MATCH (a:Game) WHERE a.date < $date
WITH max(a.date) AS prev
OPTIONAL MATCH (b:Game) WHERE b.date > $date
RETURN toString(prev) AS prev, toString(min(b.date)) AS next
"""


def _line(rows: list[dict], innings: int | None) -> dict:
    n = max([innings or 9, *[r["inn"] for r in rows]])
    out = {"away": [None] * n, "home": [None] * n, "away_h": 0, "home_h": 0}
    for r in rows:
        side = "away" if r["half"] == "초" else "home"
        out[side][r["inn"] - 1] = r["runs"]
        out[side + "_h"] += r["h"]
    return out


@router.get("/games", summary="14. 날짜별 경기 일정 (메인)")
def get_games_by_date(  # API 14: 그날 경기 결과와 홈런 (시안 메인 '경기 일정')
    date: Date | None = Query(None, description="YYYY-MM-DD. 생략하면 데이터의 마지막 경기일"),
):
    if date is None:
        date = run(Q_LATEST_DATE)[0]["d"]  # Neo4j 날짜 → 그대로 다시 넘겨도 됨
        if date is None:
            raise ApiError(404, "NO_GAMES", "경기 데이터가 없습니다")

    rows = run(Q_DAY_GAMES, date=date)
    pks = [g["game_pk"] for g in rows]
    lines: dict = {}
    for r in run(Q_LINES, games=pks):
        lines.setdefault(r["gpk"], []).append(r)
    highlights = game_highlights(pks)
    games = []
    for g in rows:
        games.append({
            "game_pk": g["game_pk"],
            "dh_no": g["dh_no"],
            "innings": g["innings"],
            **game_tag(g),
            "away": {"team": g["away"], "score": g["away_final"],
                     "result": result_of(g["away_final"], g["home_final"])},
            "home": {"team": g["home"], "score": g["home_final"],
                     "result": result_of(g["home_final"], g["away_final"])},
            "home_runs": [{**h, "hr_label": hr_label(g["season"], g["game_type"], h["hr_seq"], h["post_hr_seq"])}
                          for h in g["home_runs"]],
            "line": _line(lines.get(g["game_pk"], []), g["innings"]),  # 이닝별 점수 · 안타 (없는 반 이닝은 null = 홈팀이 안 한 말)
            "highlight": highlights.get(g["game_pk"]),
        })

    nav = run(Q_PREV_NEXT, date=date)[0]
    return {
        "date": str(date),
        "prev_date": nav["prev"],  # 앞뒤로 경기가 있는 날 (화살표용). 없으면 null
        "next_date": nav["next"],
        "games": games,            # 경기 없는 날이면 빈 목록
    }


# ------------------------------------------------------------------ 15. 최근 홈런
Q_LATEST_SEASON = "MATCH (g:Game) RETURN max(g.season) AS s"

Q_HOME_RUNS = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance {season: $season, events: 'home_run'})-[:PART_OF]->(g:Game)
WHERE (pa.game_type = 'regular' OR $with_post)   // 포스트시즌 홈런은 포스트시즌 기간에만 (PS7)
  AND (NOT $video_only OR EXISTS { (pa)-[x:MATCHED_TO]->(:VideoLink) WHERE x.status IN ['auto_confirmed', 'approved'] AND coalesce(x.precision, 'scene') <> 'game' })
MATCH (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
MATCH (pit:Player)-[:PITCHED_IN]->(pa)
OPTIONAL MATCH (pa)-[m:MATCHED_TO]->(v:VideoLink) WHERE m.status IN ['auto_confirmed', 'approved'] AND coalesce(m.precision, 'scene') <> 'game'
WITH pa, g, b, pit, home, away, count(m) > 0 AS has_video, collect(v)[0] AS v
ORDER BY pa.date DESC, g.dh_no DESC, pa.at_bat_number DESC
LIMIT $limit
RETURN pa.pa_id AS pa_id, toString(pa.date) AS date, pa.inning AS inning,
       pa.inning_half AS inning_half, pa.runs_scored AS runs, pa.hr_seq AS hr_seq, pa.post_hr_seq AS post_hr_seq,
       g.game_type AS game_type, g.stage AS stage, g.series_game_no AS series_game_no,
       pa.situation AS situation,
       pa.on_1b AS on_1b, pa.on_2b AS on_2b, pa.on_3b AS on_3b,
       pa.final_balls AS balls, pa.final_strikes AS strikes, pa.outs_when_up AS outs,
       b.player_id AS batter_id, b.name AS batter_name, b.position AS batter_position,
       pit.player_id AS pitcher_id, pit.name AS pitcher_name,
       home.name AS home, away.name AS away, has_video,
       v.video_id AS video_id, v.title AS video_title
"""


@router.get("/home-runs", summary="15. 최근 홈런 (메인)")
def get_recent_home_runs(  # API 15: 리그 전체 최근 홈런 (시안 메인 '최근 홈런 장면')
    season: int | None = Query(None, description="생략하면 가장 최근 시즌"),
    limit: int = Query(9, ge=1, le=50, description="몇 개까지"),
    video_only: bool = Query(True, description="true면 확정 장면(자동 확정·승인)이 있는 홈런만 (메인 '최근 홈런 장면'), false면 모든 홈런"),
):
    if season is None:
        season = run(Q_LATEST_SEASON)[0]["s"]

    with_post = period(season)["active"]  # 포스트시즌 기간이면 포스트시즌 홈런도 최신순으로 섞는다 (PS7)
    home_runs = []
    for r in run(Q_HOME_RUNS, season=season, limit=limit, video_only=video_only, with_post=with_post):
        bat_home = r["inning_half"] == "말"
        home_runs.append({
            "pa_id": r["pa_id"],
            "date": r["date"],
            "inning": r["inning"],
            "inning_half": r["inning_half"],
            "runs": r["runs"],
            "hr_seq": r["hr_seq"],
            "post_hr_seq": r["post_hr_seq"],
            "hr_label": hr_label(season, r["game_type"], r["hr_seq"], r["post_hr_seq"]),
            **game_tag(r),
            "situation": r["situation"],
            "runners": {"on_1b": r["on_1b"], "on_2b": r["on_2b"], "on_3b": r["on_3b"]},  # 홈런 때 주자 (썸네일 중계 표시)
            "count": {"balls": r["balls"], "strikes": r["strikes"]},                      # 홈런 공의 볼카운트
            "outs": r["outs"],                                                             # 홈런 때 아웃 수
            "batter": {"player_id": r["batter_id"], "name": r["batter_name"],
                       "team": r["home"] if bat_home else r["away"],
                       "position": r["batter_position"]},
            "pitcher": {"player_id": r["pitcher_id"], "name": r["pitcher_name"]},
            "opponent": r["away"] if bat_home else r["home"],
            "has_video": r["has_video"],
            "video": {"video_id": r["video_id"], "title": r["video_title"]} if r["video_id"] else None,
        })
    return {"season": season, "video_only": video_only, "includes_postseason": with_post, "home_runs": home_runs}
