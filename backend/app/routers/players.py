"""
선수 API
  1. GET /players?q=&role=          이름 검색
  2. GET /players/{player_id}?season= 정보 화면 (프로필·시즌 기록·백분위·최근 홈런·최근 영상)
  3. GET /players/{player_id}/games?season=&month=  기록 탭 출전 경기 목록
 19. GET /players/{player_id}/seasons             시즌 기록 탭 (시즌별 타격 기록)
"""
from typing import Literal

from fastapi import APIRouter, Query

from ..db import run
from ..errors import ApiError
from ..events import batting_line
from ..utils import batter_is_home, result_of, weekday_ko

router = APIRouter(tags=["선수"])

SEARCH_LIMIT = 20  # 검색 결과 최대 개수 (명세 미정 → 일단 20)


# ------------------------------------------------------------------ 1. 검색
Q_SEARCH = """
MATCH (p:Player)
WHERE p.name CONTAINS $q
WITH p,
     EXISTS { (p)-[:BATTED_IN]->() }  AS is_batter,
     EXISTS { (p)-[:PITCHED_IN]->() } AS is_pitcher
WHERE $role IS NULL
   OR ($role = 'batter'  AND is_batter)
   OR ($role = 'pitcher' AND is_pitcher)
// 팀 = 가장 최근 소속 (트레이드면 마지막으로 뛴 팀)
OPTIONAL MATCH (p)-[f:PLAYS_FOR]->(t:Team)
WITH p, f, t ORDER BY f.season DESC, f.last_date DESC
WITH p, head(collect(t.name)) AS team
RETURN p.player_id AS player_id, p.name AS name, team, p.position AS position, p.bats_throws AS bats_throws   // 공식 투타 (예: 우투좌타)
ORDER BY name <> $q, name    // 이름이 정확히 같은 선수를 맨 앞에
LIMIT $limit
"""         # 선수ID/이름/가장최근소속팀/타격방향/던지는 손 리턴


@router.get("/players", summary="1. 선수 이름 검색")
def search_players(  # API 1: 이름으로 선수 검색
    q: str = Query(..., min_length=1, description="검색할 이름 (일부만 써도 됨)"),
    role: Literal["batter", "pitcher"] | None = Query(None, description="batter / pitcher / 생략하면 전체"),
):
    rows = run(Q_SEARCH, q=q.strip(), role=role, limit=SEARCH_LIMIT)
    return {"players": rows}


# ------------------------------------------------------------------ 2. 선수 정보
# ① 선수, 시즌 기록 전부, 소속 전부 → 시즌은 파이썬에서 고른다
Q_PLAYER = """
MATCH (p:Player {player_id: $id})
OPTIONAL MATCH (p)-[:HAS_STAT]->(s:BatterSeasonStat)
WITH p, collect(s {.*}) AS stats
OPTIONAL MATCH (p)-[f:PLAYS_FOR]->(t:Team)
RETURN p {.player_id, .name, .position, .back_number, .bats_throws,
           birth_date: toString(p.birth_date)} AS player,
       stats,
       collect({season: f.season, team: t.name, last_date: toString(f.last_date)}) AS teams
"""

# ② 그 시즌 최근 홈런. $with_video가 true면 승인된 영상이 있는 홈런 중 가장 최근 것
Q_LAST_HR = """
MATCH (:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance {season: $season, events: 'home_run'})
      -[:PART_OF]->(g:Game)
WHERE NOT $with_video OR (pa)-[:MATCHED_TO {status: 'approved'}]->(:VideoLink)
MATCH (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
MATCH (pit:Player)-[:PITCHED_IN]->(pa)
OPTIONAL MATCH (pa)-[:MATCHED_TO {status: 'approved'}]->(v:VideoLink)
WITH pa, g, home, away, pit, collect(v)[0] AS v
RETURN pa.pa_id AS pa_id, toString(pa.date) AS date, pa.inning_half AS inning_half,
       pa.runs_scored AS runs, pa.hr_seq AS hr_seq,
       pit.player_id AS pitcher_id, pit.name AS pitcher_name,
       home.name AS home, away.name AS away,
       v.video_id AS video_id, v.title AS video_title
ORDER BY pa.date DESC, g.dh_no DESC, pa.at_bat_number DESC
LIMIT 1
"""

# ③ 승인된 영상 중 가장 최근 타석
Q_RECENT_VIDEO = """
MATCH (:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance)
      -[:MATCHED_TO {status: 'approved'}]->(v:VideoLink)
MATCH (pa)-[:PART_OF]->(g:Game)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
RETURN pa.pa_id AS pa_id, toString(pa.date) AS date, pa.inning_half AS inning_half,
       v.video_id AS video_id, v.title AS title,
       home.name AS home, away.name AS away
ORDER BY pa.date DESC, g.dh_no DESC, pa.at_bat_number DESC
LIMIT 1
"""

# 같은 시즌 비교 대상(qualified) 타자들의 백분위 → 등수 계산용
Q_GROUP_PCTS = """
MATCH (s:BatterSeasonStat {season: $season})
WHERE s.qualified
RETURN s {.pct_contact, .pct_hit, .pct_power, .pct_eye, .pct_consistency} AS p
"""

STAT_INTS = ["pa", "ab", "h", "hr"]
STAT_RATES = ["avg", "obp", "slg", "ops", "bb_pct", "k_pct", "iso", "ops_sd"]
PCT_KEYS = {  # 응답 이름: DB 속성
    "contact": "pct_contact",
    "hit": "pct_hit",
    "power": "pct_power",
    "eye": "pct_eye",
    "consistency": "pct_consistency",
}


def _opponent(row: dict) -> str:  # 상대 팀 이름 구하기 (초→홈팀, 말→원정팀)
    """초 공격이면 타자는 원정팀 → 상대는 홈팀."""
    return row["home"] if row["inning_half"] == "초" else row["away"]


def _round(v, n=3):  # 소수 셋째 자리까지 반올림 (값 없으면 None)
    return None if v is None else round(float(v), n)


def _pick_season(season, stats, teams):  # 보여줄 시즌 고르기 (없으면 최근 시즌)
    """season이 없으면 가장 최근 시즌. 그 시즌에 뛴 적이 없으면 404."""
    played = {s["season"] for s in stats} | {t["season"] for t in teams}
    if season is None:
        if not played:
            return None
        # 타자 기록이 있으면 그중 최근 시즌, 없으면(투수만) 소속 기준 최근 시즌
        return max(s["season"] for s in stats) if stats else max(played)
    if season not in played:
        raise ApiError(404, "SEASON_NOT_FOUND", f"{season} 시즌 기록이 없습니다")
    return season


def _team_of(season, teams):  # 그 시즌 마지막 소속팀 (트레이드 대비)
    """그 시즌 소속 중 마지막으로 뛴 팀 (트레이드 대비)."""
    same = [t for t in teams if t["season"] == season]
    if not same:
        return None
    return max(same, key=lambda t: t["last_date"] or "")["team"]


@router.get("/players/{player_id}", summary="2. 선수 정보 (정보 화면)")
def get_player(  # API 2: 정보 화면 데이터 한 번에
    player_id: str,
    season: int | None = Query(None, description="시즌. 생략하면 그 선수가 뛴 가장 최근 시즌"),
):
    # ① 선수·시즌 기록·팀
    rows = run(Q_PLAYER, id=player_id)
    if not rows:
        raise ApiError(404, "PLAYER_NOT_FOUND", "선수를 찾을 수 없습니다")
    player = rows[0]["player"]
    stats_all = rows[0]["stats"]
    teams = [t for t in rows[0]["teams"] if t["season"] is not None]

    season = _pick_season(season, stats_all, teams)
    s = next((x for x in stats_all if x["season"] == season), None)

    if s is None:  # 투수만 했거나 그 시즌 타자 기록이 없음
        stats, qualified, percentiles, axis_ranks, group_size = None, False, None, None, None
    else:
        stats = {k: s.get(k) for k in STAT_INTS}
        stats.update({k: _round(s.get(k)) for k in STAT_RATES})
        qualified = bool(s.get("qualified"))
        percentiles = axis_ranks = group_size = None
        if qualified:
            percentiles = {
                k: (None if s.get(db) is None else int(s[db])) for k, db in PCT_KEYS.items()
            }
            group = [r["p"] for r in run(Q_GROUP_PCTS, season=season)]
            group_size = len(group)
            axis_ranks = {  # 등수 = 나보다 백분위가 높은 사람 수 + 1 (공동 순위)
                k: (None if s.get(db) is None
                    else 1 + sum(1 for g in group if g.get(db) is not None and g[db] > s[db]))
                for k, db in PCT_KEYS.items()
            }

    # ② 최근 홈런 (last_hr: 그냥 가장 최근 홈런 / last_hr_video: 영상이 있는 홈런 중 가장 최근)
    def hr_of(with_video):
        hr = run(Q_LAST_HR, id=player_id, season=season, with_video=with_video)
        if not hr:
            return None
        h = hr[0]
        return {
            "pa_id": h["pa_id"],
            "date": h["date"],
            "opponent": _opponent(h),
            "pitcher": {"player_id": h["pitcher_id"], "name": h["pitcher_name"]},
            "runs": h["runs"],
            "hr_seq": h["hr_seq"],
            "video": {"video_id": h["video_id"], "title": h["video_title"]} if h["video_id"] else None,
        }

    last_hr = last_hr_video = None
    if season is not None:
        last_hr = hr_of(False)
        last_hr_video = hr_of(True) if last_hr else None

    # ③ 최근 영상 (승인된 것만)
    recent_video = None
    v = run(Q_RECENT_VIDEO, id=player_id)
    if v:
        v = v[0]
        recent_video = {
            "video_id": v["video_id"],
            "title": v["title"],
            "date": v["date"],
            "opponent": _opponent(v),
            "pa_id": v["pa_id"],
        }

    return {
        "player_id": player["player_id"],
        "name": player["name"],
        "team": _team_of(season, teams),
        "position": player["position"],        # 선수 프로필 (05_load_profile.py)
        "back_number": player["back_number"],
        "birth_date": player["birth_date"],
        "bats_throws": player["bats_throws"],  # 공식 표기 (예: 우투좌타)
        "season": season,
        "stats": stats,
        "qualified": qualified,
        "percentiles": percentiles,
        "axis_ranks": axis_ranks,   # 지표별 등수 {"power": 2, ...}. 비교 대상이 아니면 null
        "group_size": group_size,   # 비교 대상 인원 ("150명 중 2위"의 150)
        "last_hr": last_hr,              # 그 시즌 가장 최근 홈런 (영상 여부 상관없음)
        "last_hr_video": last_hr_video,  # 그 시즌 승인된 영상이 있는 홈런 중 가장 최근 (없으면 null)
        "recent_video": recent_video,
    }


# ------------------------------------------------------------------ 3. 출전 경기
# 드롭다운용: 이 선수가 타석에 선 시즌과 그 시즌의 달
Q_SEASON_MONTHS = """
MATCH (p:Player {player_id: $id})
OPTIONAL MATCH (p)-[:BATTED_IN]->(pa:PlateAppearance)
RETURN pa.season AS season, collect(DISTINCT pa.date.month) AS months
"""

# 그 달에 이 선수가 나온 경기들 (경기마다 타석 결과를 모음)
Q_GAMES = """
MATCH (:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance {season: $season})-[:PART_OF]->(g:Game)
WHERE pa.date.month = $month
MATCH (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
OPTIONAL MATCH (pa)-[m:MATCHED_TO {status: 'approved'}]->(:VideoLink)
WITH g, home, away, collect(DISTINCT pa) AS pas, count(m) AS videos
RETURN g.game_pk AS game_pk, toString(g.date) AS date, g.dh_no AS dh_no,
       g.home_final AS home_final, g.away_final AS away_final,
       home.name AS home, away.name AS away,
       [x IN pas | x.events] AS events, head(pas).inning_half AS inning_half,
       videos
ORDER BY g.date DESC, g.dh_no DESC
"""


@router.get("/players/{player_id}/games", summary="3. 출전 경기 목록 (기록 탭)")
def get_player_games(  # API 3: 시즌·월 드롭다운 + 그 달 출전 경기
    player_id: str,
    season: int | None = Query(None, description="생략하면 이 선수가 뛴 가장 최근 시즌"),
    month: int | None = Query(None, ge=1, le=12, description="생략하면 그 시즌 가장 최근 달"),
):
    rows = run(Q_SEASON_MONTHS, id=player_id)
    if not rows:
        raise ApiError(404, "PLAYER_NOT_FOUND", "선수를 찾을 수 없습니다")

    by_season = {r["season"]: sorted(r["months"]) for r in rows if r["season"] is not None}
    seasons = sorted(by_season)
    if not seasons:  # 타석이 하나도 없는 선수 (투수만)
        return {"seasons": [], "season": None, "months": [], "month": None, "games": []}

    if season is None:
        season = seasons[-1]
    elif season not in by_season:
        raise ApiError(404, "SEASON_NOT_FOUND", f"{season} 시즌에 타석 기록이 없습니다")

    months = by_season[season]
    if month is None:
        month = months[-1]
    elif month not in months:
        raise ApiError(404, "MONTH_NOT_FOUND", f"{season}년 {month}월에 타석 기록이 없습니다")

    games = []
    for g in run(Q_GAMES, id=player_id, season=season, month=month):
        home = batter_is_home(g["inning_half"])
        team_score = g["home_final"] if home else g["away_final"]
        opp_score = g["away_final"] if home else g["home_final"]
        line = batting_line(g["events"])
        games.append({
            "game_pk": g["game_pk"],
            "date": g["date"],
            "weekday": weekday_ko(g["date"]),
            "opponent": g["away"] if home else g["home"],
            "home": home,
            "score": {"team": team_score, "opponent": opp_score},
            "result": result_of(team_score, opp_score),
            "line": {"ab": line["ab"], "h": line["h"], "hr": line["hr"]},
            "video_count": g["videos"],
        })

    return {"seasons": seasons, "season": season, "months": months, "month": month, "games": games}


# ------------------------------------------------------------------ 19. 시즌 기록
Q_SEASONS = """
MATCH (p:Player {player_id: $id})
OPTIONAL MATCH (p)-[:HAS_STAT]->(s:BatterSeasonStat)
OPTIONAL MATCH (p)-[f:PLAYS_FOR {season: s.season}]->(t:Team)
WITH p, s, t, f ORDER BY f.last_date DESC
WITH p, s, collect(t.name) AS teams, sum(f.games) AS games
RETURN p.name AS name, p.position AS position, p.back_number AS back_number,
       toString(p.birth_date) AS birth_date, p.bats_throws AS bats_throws, s {.*} AS s, teams, games
ORDER BY s.season DESC
"""

SEASON_INTS = ["pa", "ab", "h", "b2", "b3", "hr", "bb", "hbp", "so", "sf", "sh"]
SEASON_RATES = ["avg", "obp", "slg", "ops", "iso", "bb_pct", "k_pct"]


@router.get("/players/{player_id}/seasons", summary="19. 시즌별 기록 (시즌 기록 탭)")
def get_player_seasons(  # API 19: 시즌마다 한 줄. 최근 시즌부터
    player_id: str,
):
    rows = run(Q_SEASONS, id=player_id)
    if not rows:
        raise ApiError(404, "PLAYER_NOT_FOUND", "선수를 찾을 수 없습니다")

    seasons = []
    for r in rows:
        s = r["s"]
        if s is None:  # 타자 기록이 없는 선수 (투수만)
            continue
        row = {"season": s["season"], "teams": r["teams"], "games": r["games"]}
        row.update({k: s.get(k) for k in SEASON_INTS})
        row.update({k: _round(s.get(k)) for k in SEASON_RATES})
        seasons.append(row)

    r0 = rows[0]
    return {
        "player_id": player_id, "name": r0["name"],
        "position": r0["position"], "back_number": r0["back_number"],
        "birth_date": r0["birth_date"], "bats_throws": r0["bats_throws"],
        "seasons": seasons,
    }
