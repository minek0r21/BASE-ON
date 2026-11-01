"""
선수 API
  1. GET /players?q=&role=          이름 검색
  2. GET /players/{player_id}?season= 정보 화면 (프로필·시즌 기록·백분위·최근 홈런·최근 영상)
  3. GET /players/{player_id}/games?season=&month=  기록 탭 출전 경기 목록
 19. GET /players/{player_id}/seasons             시즌 기록 탭 (시즌별 타격 기록)
 27. GET /players/{player_id}/form?season=        요즘 타격감 (경기마다 최근 20경기 OPS, 시안 F-04)
 32. GET /players/{player_id}/pitching-form?season= 요즘 투구감 (등판마다 최근 10등판 WHIP, 시안 03b)
 36. GET /players/{player_id}/scenes?season=&as=  선수의 장면 목록 (03 「장면」 · 03b 「등판」)
"""
from math import ceil
from typing import Literal

from fastapi import APIRouter, Query

from ..db import run
from ..errors import ApiError
from ..events import HITS, NOT_AB, batting_line
from ..postseason import game_tag
from ..scenes import CONFIRMED, GOOD_EVENTS, game_highlights, pa_scenes, scene_of
from ..utils import batter_is_home, result_of, weekday_ko
from .outings import outing_rows

router = APIRouter(tags=["선수"])



# ------------------------------------------------------------------ 1. 검색
# 초성 검색: 「ㄱㄷㅇ」·「김ㄷㅇ」·「김도」 모두 같은 규칙 — 자음 한 글자는 그 자음으로 시작하는 음절 전부로 바꾼 정규식
CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def name_pattern(q: str) -> str:
    """검색어 → Neo4j(자바) 정규식 조각. 완성된 글자는 그대로, 초성은 [가-깋] 같은 범위로, 그 밖은 이스케이프"""
    out = []
    for ch in q:
        i = CHOSUNG.find(ch)
        if i >= 0:
            start = 0xAC00 + i * 588  # 초성 하나에 중성 21 × 종성 28 = 588 음절
            out.append(f"[{chr(start)}-{chr(start + 587)}]")
        elif ch.isalnum():
            out.append(ch)
        else:
            out.append("\\" + ch)
    return "".join(out)


Q_SEARCH = """
MATCH (p:Player)
// 이름의 띄어쓰기는 빼고 맞춘다 (검색어도 띄어쓰기를 뺀다 — 「코엔 윈」 ↔ 「ㅋㅇㅇ」)
WITH p, replace(p.name, ' ', '') AS bare
WHERE bare =~ ('.*' + $pattern + '.*') OR any(x IN coalesce(p.former_names, []) WHERE replace(x, ' ', '') =~ ('.*' + $pattern + '.*'))
WITH p,
     EXISTS { (p)-[:BATTED_IN]->() }  AS is_batter,
     EXISTS { (p)-[:PITCHED_IN]->() } AS is_pitcher
WHERE $role IS NULL
   OR ($role = 'batter'  AND is_batter)
   OR ($role = 'pitcher' AND is_pitcher)
// 팀 = 가장 최근 소속 (트레이드면 마지막으로 뛴 팀)
OPTIONAL MATCH (p)-[f:PLAYS_FOR]->(t:Team)
WITH p, f, t ORDER BY f.season DESC, f.last_date DESC
WITH p, head(collect(t.name)) AS team, max(f.season) AS last_season
// 많이 뛴 선수 먼저: 타석 + 상대한 타자 수 (「ㄱㄷㅇ」 → 김도영이 김대우보다 앞)
WITH p, team, last_season, COUNT { (p)-[:BATTED_IN]->() } + COUNT { (p)-[:PITCHED_IN]->() } AS played
RETURN p.player_id AS player_id, p.name AS name, team, p.position AS position, p.bats_throws AS bats_throws,   // 공식 투타 (예: 우투좌타)
       last_season, coalesce(p.former_names, []) AS former_names
ORDER BY replace(name, ' ', '') <> $q, NOT replace(name, ' ', '') =~ ($pattern + '.*'), played DESC, name    // 이름이 같은 선수 → 앞부분이 맞는 선수 → 많이 뛴 순
"""  # 상한 없음 (FR-01-02): 「ㅇㅈㅎ」처럼 겹치는 초성도 덜 뛴 선수까지 모두         # 선수ID/이름/가장최근소속팀/타격방향/던지는 손 리턴


@router.get("/players", summary="1. 선수 이름 검색")
def search_players(  # API 1: 이름으로 선수 검색
    q: str = Query(..., min_length=1, description="검색할 이름 (일부만 써도 됨). 초성도 된다: ㄱㄷㅇ · 김ㄷㅇ"),
    role: Literal["batter", "pitcher"] | None = Query(None, description="batter / pitcher / 생략하면 전체"),
):
    q = "".join(q.split())
    rows = run(Q_SEARCH, q=q, pattern=name_pattern(q), role=role)
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

# ② 그 시즌 최근 홈런. $with_video가 true면 확정 장면(자동 확정·승인)이 있는 홈런 중 가장 최근 것
Q_LAST_HR = """
MATCH (:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance {season: $season, events: 'home_run', game_type: 'regular'})
      -[:PART_OF]->(g:Game)
WHERE NOT $with_video OR EXISTS { (pa)-[x:MATCHED_TO]->(:VideoLink) WHERE x.status IN ['auto_confirmed', 'approved'] AND coalesce(x.precision, 'scene') <> 'game' }
MATCH (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
MATCH (pit:Player)-[:PITCHED_IN]->(pa)
OPTIONAL MATCH (pa)-[mv:MATCHED_TO]->(v:VideoLink) WHERE mv.status IN ['auto_confirmed', 'approved'] AND coalesce(mv.precision, 'scene') <> 'game'
WITH pa, g, home, away, pit, mv, v ORDER BY mv.rank   // 클립(scene)이 챕터(inning)보다 앞
WITH pa, g, home, away, pit, collect({v: v, m: mv})[0] AS best
RETURN pa.pa_id AS pa_id, toString(pa.date) AS date, pa.inning_half AS inning_half,
       pa.runs_scored AS runs, pa.hr_seq AS hr_seq,
       pit.player_id AS pitcher_id, pit.name AS pitcher_name,
       home.name AS home, away.name AS away,
       best.v.video_id AS video_id, best.v.title AS video_title, best.v.duration_sec AS duration_sec,
       best.m.start_sec AS start_sec, best.m.end_sec AS end_sec, best.m.precision AS precision
ORDER BY pa.date DESC, g.dh_no DESC, pa.at_bat_number DESC
LIMIT 1
"""

# ③ 확정 장면이 있는 가장 최근 타석
Q_RECENT_VIDEO = """
MATCH (:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance {game_type: 'regular'})
      -[rv:MATCHED_TO]->(v:VideoLink)
WHERE rv.status IN ['auto_confirmed', 'approved'] AND coalesce(rv.precision, 'scene') <> 'game'
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

# 시즌 기록 카드 「리그 n위」(시안 03 · 03b): 비교 대상 안에서 나보다 좋은 사람 수 + 1 (공동 순위)
Q_BAT_GROUP_STATS = """
MATCH (s:BatterSeasonStat {season: $season}) WHERE s.qualified
RETURN s {.hr, .slg, .ops, .obp, .avg} AS s
"""
Q_PITCH_GROUP_STATS = """
MATCH (s:PitcherSeasonStat {season: $season, role: $role}) WHERE s.qualified
RETURN s {.outs, .so, .whip, .avg} AS s
"""
BAT_RANK_STATS = {"hr": False, "slg": False, "ops": False, "obp": False, "avg": False}  # 값: 낮을수록 좋은가
PITCH_RANK_STATS = {"outs": False, "so": False, "whip": True, "avg": True}


def _stat_ranks(me: dict, group: list[dict], keys: dict[str, bool]) -> dict:
    out = {}
    for k, low in keys.items():
        v = me.get(k)
        out[k] = None if v is None else 1 + sum(
            1 for g in group if g.get(k) is not None and (g[k] < v if low else g[k] > v))
    return out


STAT_INTS = ["pa", "ab", "h", "hr"]
STAT_RATES = ["avg", "obp", "slg", "ops", "bb_pct", "k_pct", "iso", "ops_sd"]
PCT_KEYS = {  # 응답 이름: DB 속성
    "contact": "pct_contact",
    "hit": "pct_hit",
    "power": "pct_power",
    "eye": "pct_eye",
    "consistency": "pct_consistency",
}


# 투수 5지표 (docs/투수.md 6-1, A안). 고정 순서: (key, 이름, 원 수치 속성, 응답 metric 이름, 낮을수록 좋은가, 백분위 속성)
PITCH_AXES = [
    ("strikeout", "탈삼진", "k_pct", "k_pct", False, "pct_strikeout"),
    ("control", "제구", "bbhbp_pct", "bbhbp_pct", True, "pct_control"),
    ("chase", "유인", "chase_pct", "chase_pct", False, "pct_chase"),
    ("hit_prevention", "안타 억제", "avg", "avg_against", True, "pct_hit_prevention"),
    ("power_prevention", "장타 억제", "iso_against", "iso_against", True, "pct_power_prevention"),
]
ROLE_LABEL = {"starter": "선발", "reliever": "불펜"}

# 비교 대상 기준 (etl/prepare.py와 같은 값) — 대상 밖일 때 「규정타석의 50%(149타석)에 19타석 모자라요」 (09 예외 상태)
QUALIFY_PA_PER_GAME = 3.1 * 0.5                         # 규정타석(팀 경기 × 3.1)의 50%
PITCHER_QUALIFY = {"starter": 0.5, "reliever": 0.2}    # 이닝 ≥ 팀 경기 × 이 값 (투수.md P4)
# 타자의 주 소속팀(그 시즌 타석이 가장 많은 팀, 같으면 나중에 뛴 팀) 정규시즌 경기 수 — ETL의 team_games와 같은 계산
Q_BAT_TEAM_GAMES = """
MATCH (:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance {season: $season, game_type: 'regular'})-[:PART_OF]->(g:Game)
MATCH (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
WITH CASE pa.inning_half WHEN '말' THEN home ELSE away END AS t, count(*) AS n, max(pa.date) AS last
ORDER BY n DESC, last DESC LIMIT 1
MATCH (t)<-[:HOME|AWAY]-(tg:Game {season: $season, game_type: 'regular'})
RETURN count(tg) AS games
"""

Q_PITCHING = """
MATCH (:Player {player_id: $id})-[:HAS_PITCHING_STAT]->(s:PitcherSeasonStat {season: $season})
RETURN s {.*} AS s
"""
# 타자 축 옆 ▶ (안타·선구안): 그 시즌 그 결과의 확정 장면 중 가장 최근 것. 파워(홈런)는 last_hr_video (장면.md 6장)
Q_BAT_AXIS_SCENE = """
MATCH (:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance {season: $season, game_type: 'regular'})-[m:MATCHED_TO]->(v:VideoLink)
WHERE pa.events IN $events AND m.status IN $confirmed AND coalesce(v.playable, true) AND coalesce(m.precision, 'scene') <> 'game'
MATCH (pa)-[:PART_OF]->(g:Game), (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
RETURN pa.pa_id AS pa_id, toString(pa.date) AS date, pa.inning AS inning, pa.inning_half AS inning_half,
       pa.events AS events, pa.runs_scored AS runs, home.name AS home, away.name AS away,
       v.video_id AS video_id, v.title AS title, v.duration_sec AS duration_sec,
       m.start_sec AS start_sec, m.end_sec AS end_sec, m.precision AS precision, m.scene_type AS scene_type,
       coalesce(m.tags, []) AS tags
ORDER BY pa.date DESC, pa.at_bat_number DESC, m.rank LIMIT 1
"""
BAT_AXIS_EVENTS = {"hit": ["single", "double", "triple"], "eye": ["walk"]}


def _bat_axis_scenes(player_id: str, season: int | None) -> dict:
    out = {}
    for axis, events in BAT_AXIS_EVENTS.items():
        r = run(Q_BAT_AXIS_SCENE, id=player_id, season=season, events=events, confirmed=CONFIRMED) if season else []
        if r:
            r = r[0]
            out[axis] = {**scene_of(r), "pa_id": r["pa_id"], "date": r["date"], "inning": r["inning"],
                         "inning_half": r["inning_half"], "events": r["events"], "runs": r["runs"],
                         "opponent": r["home"] if r["inning_half"] == "초" else r["away"]}
    return out


# 같은 시즌·같은 역할 비교 대상의 백분위 (등수 계산용) + 그 시즌 비교 대상 평균 직구 구속
Q_PITCH_GROUP = """
MATCH (s:PitcherSeasonStat {season: $season}) WHERE s.qualified
RETURN collect(CASE WHEN s.role = $role THEN s {.pct_strikeout, .pct_control, .pct_chase, .pct_hit_prevention,
                                                .pct_power_prevention} END) AS group,
       collect(s.avg_velo) AS velos   // collect는 null을 건너뛴다 (직구를 안 던지는 투수)
"""


# 그 시즌 확정 등판 장면 (최근 장면·축 옆 ▶, docs/장면.md 6장). 최근 등판부터, 등판 안에서는 rank 순
Q_PITCH_SCENES = """
MATCH (:Player {player_id: $id})-[:PITCHED_GAME]->(o:Outing {season: $season, game_type: 'regular'})-[m:MATCHED_TO]->(v:VideoLink)
WHERE m.status IN $confirmed AND coalesce(v.playable, true)
RETURN o {.outing_id, .date, .outs, .so, .r, .h} AS o,
       v.video_id AS video_id, v.title AS title, v.duration_sec AS duration_sec,
       m.start_sec AS start_sec, m.end_sec AS end_sec, m.precision AS precision, m.scene_type AS scene_type,
       coalesce(m.tags, []) AS tags
ORDER BY o.date DESC, m.rank
"""
AXIS_TAGS = {"strikeout": "strikeout", "hit_prevention": "hit_prevention", "control": "control"}  # 장면이 붙는 축 (S3)


def _pitch_scenes(player_id: str, season: int) -> tuple[dict | None, dict]:
    """(최근 장면, {축 key: 장면}). 장면마다 우리 기록 한 줄(「6이닝 8K 무실점」 재료)을 붙인다"""
    rows = run(Q_PITCH_SCENES, id=player_id, season=season, confirmed=CONFIRMED)
    def pack(r):
        return {**scene_of(r), "outing_id": r["o"]["outing_id"], "date": r["o"]["date"],
                "line": {k: r["o"][k] for k in ("outs", "so", "r", "h")}}
    recent = pack(rows[0]) if rows else None
    by_axis = {}
    for key, tag in AXIS_TAGS.items():
        hit = next((r for r in rows if tag in r["tags"]), None)
        if hit:
            by_axis[key] = pack(hit)
    return recent, by_axis


def _pitching(player_id: str, season: int | None) -> dict | None:
    """API-02 pitching 칸 (docs/투수.md 6-1). 그 시즌 투구 기록이 없으면 None"""
    if season is None:
        return None
    rows = run(Q_PITCHING, id=player_id, season=season)
    if not rows:
        return None
    s = rows[0]["s"]
    qualified = bool(s.get("qualified"))
    g = run(Q_PITCH_GROUP, season=season, role=s.get("role"))[0]
    group = g["group"] if qualified else []
    league_velo = sum(g["velos"]) / len(g["velos"]) if g["velos"] else None  # 비교 대상 투수 평균 (P8)
    recent_scene, axis_scenes = _pitch_scenes(player_id, season)
    stat_ranks = (_stat_ranks(s, [r["s"] for r in run(Q_PITCH_GROUP_STATS, season=season, role=s.get("role"))],
                              PITCH_RANK_STATS) if qualified else None)
    axes = []
    for key, label, prop, metric, reverse, pct in PITCH_AXES:
        p = s.get(pct) if qualified else None
        axes.append({
            "key": key, "label": label, "metric": metric, "value": _round(s.get(prop), 4), "reverse": reverse,
            "percentile": None if p is None else int(p),
            # 등수 = 같은 역할 비교 대상 중 나보다 백분위가 높은 사람 수 + 1 (공동 순위)
            "rank": None if p is None else 1 + sum(1 for x in group if x.get(pct) is not None and x[pct] > p),
            "scene": axis_scenes.get(key),  # 이 축을 보여 주는 확정 장면 (탈삼진·안타 억제·제구만, 없으면 null)
        })
    return {
        "role": s.get("role"), "role_label": ROLE_LABEL.get(s.get("role")),
        "g": s.get("g"), "gs": s.get("gs"), "outs": s.get("outs"), "tbf": s.get("tbf"),
        "h": s.get("h"), "hr": s.get("hr"), "bb": s.get("bb"), "hbp": s.get("hbp"), "so": s.get("so"), "r": s.get("r"),
        "avg": _round(s.get("avg")), "whip": _round(s.get("whip"), 2),
        "avg_velo": s.get("avg_velo"), "league_avg_velo": _round(league_velo, 1),
        "qualified": qualified, "group_size": len(group) if qualified else None,
        "axes": axes,
        "stat_ranks": stat_ranks,  # 시즌 기록 등수 {outs, so, whip, avg} — 같은 역할 비교 대상 안. 대상 밖이면 null
        "not_qualified_message": None if qualified else "리그 비교 대상 아님(이닝 부족)",
        # 비교 대상이 되려면 필요한 아웃 수 (이닝 × 3). 대상이면 null
        "qualify_outs": None if qualified or not s.get("team_games")
        else ceil(s["team_games"] * PITCHER_QUALIFY.get(s.get("role"), 0.5) * 3),
        "recent_scene": recent_scene,  # 그 시즌 가장 최근 확정 등판 장면 (없으면 null)
    }


def _qualify_pa(player_id: str, season: int) -> int | None:
    rows = run(Q_BAT_TEAM_GAMES, id=player_id, season=season)
    return ceil(rows[0]["games"] * QUALIFY_PA_PER_GAME) if rows and rows[0]["games"] else None


def _primary_role(stats: dict | None, pitching: dict | None) -> str | None:
    """그 시즌 상대 타자 수 > 타석 수이면 투수 (투수.md P6). 둘 다 없으면 None"""
    if pitching and (stats is None or (pitching["tbf"] or 0) > (stats.get("pa") or 0)):
        return "pitcher"
    return "batter" if stats is not None else None


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


# ------------------------------------------------------------------ 11. 타자 비교
# 고정 순서 (설계 6-3): (key, 이름, 원 수치, 낮을수록 좋은가)
BAT_AXES = [("contact", "삼진회피", "k_pct", True), ("hit", "안타생산", "avg", False), ("power", "파워", "iso", False),
            ("eye", "선구안", "bb_pct", False), ("consistency", "꾸준함", "ops_sd", True)]
COMPARE_MAX = 3


@router.get("/players/compare", summary="11. 선수 비교 (2~3명, 타자끼리 · 투수끼리)")  # /players/{player_id}보다 먼저 등록해야 한다
def compare_players(  # API 11: 백분위·원 수치. 대상 밖 선수는 원 수치만 (설계 6-2, FR-06)
    ids: str = Query(..., description="선수 ID 2~3개, 쉼표로 (예: 53123,52605)"),
    season: int | None = Query(None, description="생략하면 그 기록(타자 · 투구)이 있는 첫 선수가 뛴 가장 최근 시즌"),
    as_: Literal["batter", "pitcher"] = Query("batter", alias="as", description="batter 타자끼리 / pitcher 투수끼리 (07 비교, 11-01)"),
):
    pids = list(dict.fromkeys(i.strip() for i in ids.split(",") if i.strip()))
    if not 2 <= len(pids) <= COMPARE_MAX:
        raise ApiError(400, "COMPARE_COUNT", f"비교는 {COMPARE_MAX}명까지, 2명 이상이어야 합니다")
    loaded = []
    for pid in pids:
        rows = run(Q_PLAYER, id=pid)
        if not rows:
            raise ApiError(404, "PLAYER_NOT_FOUND", f"선수를 찾을 수 없습니다: {pid}")
        loaded.append(rows[0])
    if as_ == "pitcher":
        return _compare_pitchers(loaded, season)
    if season is None:  # 타자 기록이 없는 선수(투수)가 앞에 있어도 비교는 한다 — 그 선수는 「기록 없음」으로
        first = next(([x["season"] for x in r["stats"]] for r in loaded if r["stats"]), None)
        if not first:
            raise ApiError(404, "SEASON_NOT_FOUND", "타자 기록이 있는 선수가 없습니다")
        season = max(first)
    group = [r["p"] for r in run(Q_GROUP_PCTS, season=season)]

    players = []
    for r in loaded:
        s = next((x for x in r["stats"] if x["season"] == season), None)
        teams = [t for t in r["teams"] if t["season"] is not None]
        qualified = bool(s and s.get("qualified"))
        axes = []
        for key, label, metric, reverse in BAT_AXES:
            db = PCT_KEYS[key]
            p = s.get(db) if qualified else None
            axes.append({
                "key": key, "label": label, "metric": metric, "reverse": reverse,
                "value": _round(s.get(metric)) if s else None,
                "percentile": None if p is None else int(p),
                "rank": None if p is None else 1 + sum(1 for g in group if g.get(db) is not None and g[db] > p),
            })
        players.append({
            "player_id": r["player"]["player_id"], "name": r["player"]["name"], "team": _team_of(season, teams),
            "position": r["player"]["position"], "has_stats": s is not None, "qualified": qualified,
            "stats": None if s is None else {**{k: s.get(k) for k in STAT_INTS}, **{k: _round(s.get(k)) for k in STAT_RATES}},
            "axes": axes,
            "message": None if qualified else ("리그 비교 대상 아님(타석 부족)" if s else f"{season} 시즌 타자 기록 없음"),
        })
    return {"season": season, "group_size": len(group), "players": players}


def _compare_pitchers(loaded: list[dict], season: int | None) -> dict:
    """투수끼리 비교 — API-02 pitching 칸과 같은 값. 백분위 · 등수는 각자 역할(선발 · 불펜) 비교 대상 안 기준"""
    if season is None:  # 투구 기록이 없는 선수(타자)가 앞에 있어도 비교는 한다
        first = next((rows for rows in (run(Q_PITCH_SEASONS, id=r["player"]["player_id"]) for r in loaded) if rows), None)
        if not first:
            raise ApiError(404, "SEASON_NOT_FOUND", "투구 기록이 있는 선수가 없습니다")
        season = first[0]["s"]["season"]
    players = []
    for r in loaded:
        pid = r["player"]["player_id"]
        pi = _pitching(pid, season)
        teams = [t for t in r["teams"] if t["season"] is not None]
        players.append({
            "player_id": pid, "name": r["player"]["name"], "team": _team_of(season, teams), "position": r["player"]["position"],
            "has_stats": pi is not None, "qualified": bool(pi and pi["qualified"]),
            "role": pi and pi["role"], "role_label": pi and pi["role_label"], "group_size": pi and pi["group_size"],
            "stats": None if pi is None else {k: pi[k] for k in ("g", "gs", "outs", "tbf", "h", "hr", "bb", "hbp", "so", "r", "avg", "whip")},
            "axes": [] if pi is None else [{k: a[k] for k in ("key", "label", "metric", "reverse", "value", "percentile", "rank")} for a in pi["axes"]],
            "message": None if pi and pi["qualified"] else ("리그 비교 대상 아님(이닝 부족)" if pi else f"{season} 시즌 투구 기록 없음"),
        })
    return {"season": season, "as": "pitcher", "players": players}


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

    stat_ranks = None
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
            stat_ranks = _stat_ranks(s, [r["s"] for r in run(Q_BAT_GROUP_STATS, season=season)], BAT_RANK_STATS)

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
            "video": {"video_id": h["video_id"], "title": h["video_title"], "duration_sec": h["duration_sec"],
                      "start_sec": h["start_sec"] or 0, "end_sec": h["end_sec"],
                      "precision": h["precision"] or "scene"} if h["video_id"] else None,
        }

    last_hr = last_hr_video = None
    if season is not None:
        last_hr = hr_of(False)
        last_hr_video = hr_of(True) if last_hr else None

    # ③ 최근 영상 (확정된 것만)
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

    pitching = _pitching(player_id, season)

    return {
        "player_id": player["player_id"],
        "name": player["name"],
        "team": _team_of(season, teams),
        "primary_role": _primary_role(stats, pitching),  # 그 시즌 화면: batter 타자 요약 / pitcher 투수 요약
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
        "stat_ranks": stat_ranks,   # 시즌 기록 등수 {hr, slg, ops, obp, avg} — 같은 비교 대상 안. 대상 밖이면 null
        "qualify_pa": _qualify_pa(player_id, season) if stats and not qualified else None,  # 비교 대상이 되려면 필요한 타석 수
        "last_hr": last_hr,              # 그 시즌 가장 최근 홈런 (영상 여부 상관없음)
        "last_hr_video": last_hr_video,  # 그 시즌 확정 장면(자동 확정·승인)이 있는 홈런 중 가장 최근 (없으면 null)
        "axis_scenes": _bat_axis_scenes(player_id, season) if stats else {},  # 축 옆 ▶ {hit: 안타 장면, eye: 볼넷 장면}, 없는 축은 빠짐
        "recent_video": recent_video,
        "pitching": pitching,  # 그 시즌 투수 기록·5지표 (docs/투수.md 6-1). 투구 기록이 없으면 null
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
OPTIONAL MATCH (pa)-[m:MATCHED_TO]->(v:VideoLink) WHERE m.status IN ['auto_confirmed', 'approved'] AND coalesce(v.playable, true)
WITH g, home, away, pa, m, v ORDER BY m.rank
WITH g, home, away, collect(DISTINCT pa) AS pas,
     count(CASE WHEN m IS NOT NULL AND coalesce(m.precision, 'scene') <> 'game' THEN 1 END) AS videos,
     // 「이 선수 영상」: 멀티 히트처럼 한 경기 여러 타석을 담은 영상 (docs/장면.md S13)
     collect(CASE WHEN m.precision = 'game' THEN {video_id: v.video_id, title: v.title, duration_sec: v.duration_sec,
                                                    start_sec: m.start_sec, end_sec: m.end_sec} END)[0] AS player_video
RETURN g.game_pk AS game_pk, toString(g.date) AS date, g.dh_no AS dh_no,
       g.home_final AS home_final, g.away_final AS away_final,
       g.game_type AS game_type, g.stage AS stage, g.series_game_no AS series_game_no,
       home.name AS home, away.name AS away,
       [x IN pas | x.events] AS events, head(pas).inning_half AS inning_half,
       videos, player_video
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
    rows = run(Q_GAMES, id=player_id, season=season, month=month)
    highlights = game_highlights([g["game_pk"] for g in rows])
    for g in rows:
        home = batter_is_home(g["inning_half"])
        team_score = g["home_final"] if home else g["away_final"]
        opp_score = g["away_final"] if home else g["home_final"]
        line = batting_line(g["events"])
        games.append({
            "game_pk": g["game_pk"],
            "date": g["date"],
            "weekday": weekday_ko(g["date"]),
            **game_tag(g),  # 포스트시즌이면 「준PO 2차전」 꼬리표 (PS3)
            "opponent": g["away"] if home else g["home"],
            "home": home,
            "score": {"team": team_score, "opponent": opp_score},
            "result": result_of(team_score, opp_score),
            "line": {"ab": line["ab"], "h": line["h"], "hr": line["hr"]},
            "video_count": g["videos"],
            "player_video": g["player_video"],  # 이 경기 이 선수 영상 (처음부터 재생, 없으면 null)
            "highlight": highlights.get(g["game_pk"]),  # 기본층 「이 경기 하이라이트」 (없으면 null)
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

# 투수 시즌 기록 (FR-05-04): 등판·선발·이닝·피안타·볼넷·탈삼진·피안타율·WHIP
Q_PITCH_SEASONS = """
MATCH (p:Player {player_id: $id})-[:HAS_PITCHING_STAT]->(s:PitcherSeasonStat)
OPTIONAL MATCH (p)-[f:PLAYS_FOR {season: s.season}]->(t:Team)
WITH s, t, f ORDER BY f.last_date DESC
RETURN s {.season, .role, .g, .gs, .outs, .tbf, .h, .hr, .bb, .hbp, .so, .r, .avg, .whip, .pitches, .k_pct, .bbhbp_pct} AS s,
       collect(t.name) AS teams
ORDER BY s.season DESC
"""


Q_POST_SEASONS = """
MATCH (p:Player {player_id: $id})
RETURN COLLECT { MATCH (p)-[:HAS_POST_STAT]->(s:BatterPostseasonStat) RETURN s {.*} } AS bat,
       COLLECT { MATCH (p)-[:HAS_POST_PITCHING_STAT]->(s:PitcherPostseasonStat) RETURN s {.*} } AS pit
"""


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

    pitching_seasons = []
    for r in run(Q_PITCH_SEASONS, id=player_id):
        s = r["s"]
        pitching_seasons.append({
            **{k: s.get(k) for k in ("season", "role", "g", "gs", "outs", "tbf", "h", "hr", "bb", "hbp", "so", "r", "pitches")},
            "k_pct": _round(s.get("k_pct"), 4), "bbhbp_pct": _round(s.get("bbhbp_pct"), 4),
            "role_label": ROLE_LABEL.get(s.get("role")), "teams": r["teams"],
            "avg": _round(s.get("avg")), "whip": _round(s.get("whip"), 2),
        })

    # 포스트시즌 기록 (PS1 · PS3): 시즌마다 한 줄, 백분위 없음
    post = run(Q_POST_SEASONS, id=player_id)[0]
    postseason_seasons = [{**{k: s.get(k) for k in ["season", "games", *SEASON_INTS]},
                           **{k: _round(s.get(k)) for k in ("avg", "obp", "slg", "ops")}} for s in post["bat"]]
    postseason_pitching = [{**{k: s.get(k) for k in ("season", "g", "gs", "outs", "tbf", "h", "hr", "bb", "hbp", "so", "r")},
                            "avg": _round(s.get("avg")), "whip": _round(s.get("whip"), 2)} for s in post["pit"]]

    r0 = rows[0]
    return {
        "player_id": player_id, "name": r0["name"],
        "position": r0["position"], "back_number": r0["back_number"],
        "birth_date": r0["birth_date"], "bats_throws": r0["bats_throws"],
        "seasons": seasons,
        "pitching_seasons": pitching_seasons,  # 투수 시즌 기록. 평균자책점·승패는 원천에 없어 만들지 않는다
        "postseason_seasons": sorted(postseason_seasons, key=lambda s: -s["season"]),    # 포스트시즌 타격 (없으면 빈 목록)
        "postseason_pitching": sorted(postseason_pitching, key=lambda s: -s["season"]),  # 포스트시즌 투구
    }


# ------------------------------------------------------------------ 27. 요즘 타격감
Q_FORM = """
MATCH (:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance {season: $season, game_type: 'regular'})-[:PART_OF]->(g:Game)
WITH g, collect(pa.events) AS events ORDER BY g.date, g.dh_no
RETURN toString(g.date) AS date, events
"""
Q_LEAGUE_OPS = "MATCH (s:BatterSeasonStat {season: $season}) WHERE s.qualified RETURN avg(s.ops) AS ops"
FORM_WINDOW = 20   # 최근 20경기
FORM_POINTS = 30   # 그래프 점 30개
FORM_DIFF = 0.05   # 시즌보다 .050 이상 높으면 상승, 낮으면 하락 (시안 F-04)
TB = {"single": 1, "double": 2, "triple": 3, "home_run": 4}


def _ops(events: list[str]) -> float | None:
    ab = sum(e not in NOT_AB for e in events)
    h = sum(e in HITS for e in events)
    bb, hbp, sf = events.count("walk"), events.count("hit_by_pitch"), events.count("sac_fly")
    den = ab + bb + hbp + sf
    if not den or not ab:
        return None
    return (h + bb + hbp) / den + sum(TB.get(e, 0) for e in events) / ab


@router.get("/players/{player_id}/form", summary="27. 요즘 타격감 (최근 20경기 OPS)")
def get_player_form(player_id: str, season: int = Query(..., description="시즌")):
    games = run(Q_FORM, id=player_id, season=season)
    season_ops = _ops([e for g in games for e in g["events"]])
    league = run(Q_LEAGUE_OPS, season=season)[0]["ops"]
    points = []
    for i in range(FORM_WINDOW - 1, len(games)):
        ops = _ops([e for g in games[i - FORM_WINDOW + 1:i + 1] for e in g["events"]])
        if ops is not None:
            points.append({"date": games[i]["date"], "ops": round(ops, 3)})
    points = points[-FORM_POINTS:]
    recent = points[-1]["ops"] if points else None
    verdict = None
    if recent is not None and season_ops is not None:
        d = recent - season_ops
        verdict = "up" if d >= FORM_DIFF else "down" if d <= -FORM_DIFF else "flat"
    return {"season": season, "games": len(games), "window": FORM_WINDOW,
            "season_ops": None if season_ops is None else round(season_ops, 3),
            "recent_ops": recent, "league_ops": None if league is None else round(league, 3),
            "verdict": verdict,  # up 상승 · flat 유지 · down 하락. 20경기가 안 되면 null
            "points": points}


# ------------------------------------------------------------------ 32. 요즘 투구감
Q_PITCH_FORM = """
MATCH (:Player {player_id: $id})-[:PITCHED_GAME]->(o:Outing {season: $season, game_type: 'regular'})-[:PART_OF]->(g:Game)
RETURN o.date AS date, o.outs AS outs, o.h AS h, o.bb AS bb
ORDER BY o.date, g.dh_no
"""
# 비교 대상(같은 역할 규정이닝) 평균 WHIP — 그래프 기준선
Q_LEAGUE_WHIP = """
MATCH (s:PitcherSeasonStat {season: $season}) WHERE s.qualified AND s.role = $role
RETURN avg(s.whip) AS whip
"""
PFORM_WINDOW = 10   # 최근 10등판
PFORM_POINTS = 30
PFORM_DIFF = 0.15   # 시즌보다 WHIP가 .15 이상 낮으면 좋아짐, 높으면 나빠짐 (낮을수록 좋다)


def _whip(rows: list[dict]) -> float | None:  # (피안타 + 볼넷) ÷ 이닝 — 시즌 기록(etl/prepare.py)과 같은 식
    outs = sum(r["outs"] or 0 for r in rows)
    return (sum(r["h"] or 0 for r in rows) + sum(r["bb"] or 0 for r in rows)) / (outs / 3) if outs else None


@router.get("/players/{player_id}/pitching-form", summary="32. 요즘 투구감 (최근 10등판 WHIP)")
def get_pitching_form(player_id: str, season: int = Query(..., description="시즌")):
    outings = run(Q_PITCH_FORM, id=player_id, season=season)
    season_whip = _whip(outings)
    stat = run(Q_PITCHING, id=player_id, season=season)
    role = stat[0]["s"].get("role") if stat else None
    league = run(Q_LEAGUE_WHIP, season=season, role=role)[0]["whip"] if role else None
    points = []
    for i in range(PFORM_WINDOW - 1, len(outings)):
        w = _whip(outings[i - PFORM_WINDOW + 1:i + 1])
        if w is not None:
            points.append({"date": outings[i]["date"], "whip": round(w, 2)})
    points = points[-PFORM_POINTS:]
    recent = points[-1]["whip"] if points else None
    verdict = None
    if recent is not None and season_whip is not None:
        d = recent - season_whip
        verdict = "up" if d <= -PFORM_DIFF else "down" if d >= PFORM_DIFF else "flat"
    recent_from = outings[-PFORM_WINDOW]["date"] if len(outings) >= PFORM_WINDOW else None
    return {"season": season, "outings": len(outings), "window": PFORM_WINDOW, "role": role,
            "season_whip": _round(season_whip, 2), "recent_whip": recent,
            "recent_range": [recent_from, outings[-1]["date"]] if recent_from else None,  # 최근 10등판 기간 (시안 「5.27 ~ 7.24」)
            "league_whip": _round(league, 2),   # 같은 역할 비교 대상 평균
            "verdict": verdict,  # up 좋아짐(WHIP 낮아짐) · flat 비슷 · down 나빠짐. 10등판이 안 되면 null
            "points": points}


# ------------------------------------------------------------------ 36. 선수의 장면 목록
# 타자: 그 시즌 확정 장면이 있는 타석 중 잘한 것만 (GOOD_EVENTS). 최근부터
Q_PLAYER_PAS = """
MATCH (:Player {player_id: $id})-[:BATTED_IN]->(pa:PlateAppearance {season: $season})-[:PART_OF]->(g:Game)
WHERE pa.events IN $events
MATCH (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team), (pit:Player)-[:PITCHED_IN]->(pa)
RETURN pa {.pa_id, .inning, .inning_half, .at_bat_number, .events, .hr_seq, .runs_scored, .outs_when_up,
           .final_balls, .final_strikes} AS pa,
       toString(pa.date) AS date, g.game_pk AS game_pk, g.dh_no AS dh_no,
       g.game_type AS game_type, g.stage AS stage, g.series_game_no AS series_game_no,
       home.name AS home, away.name AS away, pit.player_id AS pitcher_id, pit.name AS pitcher_name
ORDER BY date DESC, dh_no DESC, pa.at_bat_number DESC   // RETURN 뒤 pa는 위 맵이라 date가 없다 → 별칭으로 정렬
"""


@router.get("/players/{player_id}/scenes", summary="36. 선수의 장면 목록")
def get_player_scenes(
    player_id: str,
    season: int = Query(..., description="시즌"),
    as_: Literal["batter", "pitcher"] = Query("batter", alias="as", description="batter 타석 장면 / pitcher 등판 목록"),
):
    if as_ == "pitcher":  # 등판은 장면이 없어도 경기 하이라이트(기본층)가 있으니 시즌 등판 전부를 준다
        outings = outing_rows(player_id, season, None)
        return {
            "season": season, "as": "pitcher",
            "counts": {
                "outings": len(outings),
                "highlights": sum(1 for o in outings if o["highlight"]),
                "scenes": sum(1 for o in outings if o["scene"]),
                "scoreless": sum(1 for o in outings if o["line"]["r"] == 0),
                "seven_plus": sum(1 for o in outings if o["line"]["outs"] >= 21),
            },
            "outings": outings,
        }

    rows = run(Q_PLAYER_PAS, id=player_id, season=season, events=GOOD_EVENTS)
    scenes = pa_scenes([r["pa"]["pa_id"] for r in rows])
    out = []
    for r in rows:
        pa = r["pa"]
        scene = scenes.get(pa["pa_id"])
        if not scene:
            continue
        home = batter_is_home(pa["inning_half"])
        out.append({
            "pa_id": pa["pa_id"], "date": r["date"], "weekday": weekday_ko(r["date"]), "game_pk": r["game_pk"],
            **game_tag(r),
            "opponent": r["away"] if home else r["home"], "home": home,
            "inning": pa["inning"], "inning_half": pa["inning_half"],
            "events": pa["events"], "kind": "home_run" if pa["events"] == "home_run" else "on_base",
            "hr_seq": pa["hr_seq"], "runs": pa["runs_scored"],
            "outs": pa["outs_when_up"], "count": {"balls": pa["final_balls"], "strikes": pa["final_strikes"]},
            "pitcher": {"player_id": r["pitcher_id"], "name": r["pitcher_name"]},
            "scene": scene,
        })
    hr_total = sum(1 for r in rows if r["pa"]["events"] == "home_run")
    return {
        "season": season, "as": "batter",
        "counts": {
            "scenes": len(out),
            "home_runs": hr_total,                                   # 그 시즌 홈런 (장면 여부 상관없음)
            "home_run_scenes": sum(1 for x in out if x["kind"] == "home_run"),
            "on_base_scenes": sum(1 for x in out if x["kind"] == "on_base"),
        },
        "scenes": out,
    }
