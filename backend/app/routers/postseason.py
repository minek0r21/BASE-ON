"""
포스트시즌 API — docs/포스트시즌.md 8-1 (PS6 · PS7)
  25. GET /postseason?season=   메인 「포스트시즌 코너」: 기간 · 시리즈별 결과 · 경기 · 명장면
"""
from fastapi import APIRouter, Query

from ..db import run
from ..errors import ApiError
from ..postseason import STAGE_NAME, STAGE_ORDER, period, stage_label
from ..scenes import CONFIRMED, game_highlights
from ..utils import result_of

router = APIRouter(tags=["포스트시즌"])

WINS_NEEDED = {"SPO": 3, "PO": 3, "KS": 4}  # 와일드카드는 따로 (4위가 1승 안고 시작 — 1승 또는 무승부면 4위, 5위는 2승)
SCENES_PER_SERIES = 3
PITCH_MIN_OUTS = 15  # 명장면 투수: 5이닝 이상 무실점 선발, 또는 무실점으로 경기를 끝낸 투수

Q_LATEST_POST_SEASON = "MATCH (g:Game {game_type: 'postseason'}) RETURN max(g.season) AS s"

Q_GAMES = """
MATCH (g:Game {season: $season, game_type: 'postseason'})-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
RETURN g.game_pk AS game_pk, g.stage AS stage, g.series_game_no AS n, toString(g.date) AS date,
       home.name AS home, away.name AS away, g.home_final AS home_final, g.away_final AS away_final
ORDER BY g.date, g.series_game_no
"""

# 명장면 후보 타석: 끝내기 · 역전 · 리드(결승타 판단용) · 홈런. 확정 장면은 rank 가장 앞선 것 하나 (없으면 null)
Q_PA_SCENES = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance {season: $season, game_type: 'postseason'})-[:PART_OF]->(g:Game)
WHERE pa.situation IN ['끝내기', '역전', '리드'] OR pa.events = 'home_run'
OPTIONAL MATCH (pa)-[m:MATCHED_TO]->(v:VideoLink) WHERE m.status IN $confirmed AND coalesce(v.playable, true) AND coalesce(m.precision, 'scene') <> 'game'
WITH b, pa, g, m, v ORDER BY m.rank
WITH b, pa, g, collect(CASE WHEN v IS NULL THEN null ELSE {video_id: v.video_id, title: v.title,
        duration_sec: v.duration_sec, start_sec: m.start_sec, end_sec: m.end_sec, precision: m.precision} END)[0] AS clip
RETURN g.game_pk AS game_pk, pa.pa_id AS pa_id, pa.at_bat_number AS ab, pa.inning AS inning, pa.inning_half AS half,
       pa.events AS events, pa.runs_scored AS runs, pa.situation AS situation, pa.post_hr_seq AS post_hr_seq,
       b.player_id AS player_id, b.name AS name, clip
"""

Q_OUTING_SCENES = """
MATCH (p:Player)-[:PITCHED_GAME]->(o:Outing {season: $season, game_type: 'postseason'})-[:PART_OF]->(g:Game)
WHERE o.r = 0 AND (o.outs >= $min_outs OR o.finisher)
MATCH (o)-[m:MATCHED_TO]->(v:VideoLink) WHERE m.status IN $confirmed AND coalesce(v.playable, true)
WITH p, o, g, m, v ORDER BY m.rank
WITH p, o, g, collect({video_id: v.video_id, title: v.title, duration_sec: v.duration_sec,
        start_sec: m.start_sec, end_sec: m.end_sec, precision: m.precision})[0] AS clip
RETURN g.game_pk AS game_pk, o.outing_id AS outing_id, o.outs AS outs, o.so AS so, o.starter AS starter,
       p.player_id AS player_id, p.name AS name, clip
"""

EVENT_KO = {"single": "안타", "double": "2루타", "triple": "3루타", "home_run": "홈런", "walk": "볼넷",
            "hit_by_pitch": "몸에 맞는 공", "sac_fly": "희생플라이", "field_error": "실책 출루", "field_out": "땅볼 · 뜬공"}
HR_KO = {1: "솔로 홈런", 2: "2점 홈런", 3: "3점 홈런", 4: "만루 홈런"}


def _winner_of(stage: str, games: list[dict]) -> tuple[dict, str | None]:
    """(팀별 승수, 시리즈 승자 — 아직이면 None). 무승부는 승수에 넣지 않는다"""
    teams = list(dict.fromkeys(t for g in games for t in (g["home"], g["away"])))
    wins = {t: 0 for t in teams}
    for g in games:
        r = result_of(g["home_final"], g["away_final"])
        if r != "D":
            wins[g["home"] if r == "W" else g["away"]] += 1
    if stage == "WC":  # 4위 = 1차전 홈 팀. 이기거나 비기면 4위가 올라가고, 5위는 두 번 이겨야 한다
        top = games[0]["home"]
        other = next((t for t in teams if t != top), None)
        if any(result_of(g["home_final"], g["away_final"]) != "L" and g["home"] == top
               or result_of(g["away_final"], g["home_final"]) != "L" and g["away"] == top for g in games):
            return wins, top
        return wins, other if other and wins[other] >= 2 else None
    need = WINS_NEEDED.get(stage)
    return wins, next((t for t, w in wins.items() if need and w >= need), None)


def _clip(c: dict | None) -> dict | None:
    if not c:
        return None
    return {"video_id": c["video_id"], "title": c["title"], "duration_sec": c["duration_sec"],
            "start_sec": c["start_sec"] or 0, "end_sec": c["end_sec"], "precision": c["precision"] or "scene"}


def _pa_scenes(rows: list[dict], games: dict) -> list[dict]:
    """명장면 규칙 (8장): ① 끝내기 ② 역전 ③ 홈런(점수 큰 순) ④ 그 경기 결승타. 한 타석은 가장 높은 종류 하나로"""
    go_ahead = {}  # 경기 → 이긴 팀의 마지막 역전 · 리드 · 끝내기 타석 (그 뒤로 리드를 내주지 않았다)
    for r in sorted(rows, key=lambda r: r["ab"]):
        g = games[r["game_pk"]]
        bat_home = r["half"] == "말"
        won = result_of(g["home_final"], g["away_final"]) == ("W" if bat_home else "L")
        if won and r["situation"] in ("끝내기", "역전", "리드"):
            go_ahead[r["game_pk"]] = r["pa_id"]
    out = []
    for r in rows:
        if not r["clip"]:
            continue
        g = games[r["game_pk"]]
        hr = r["events"] == "home_run"
        what = HR_KO.get(r["runs"], "홈런") if hr else EVENT_KO.get(r["events"], r["events"])
        if r["situation"] == "끝내기":
            kind, pri, label = "walkoff", 0, f"끝내기 {what}"
        elif r["situation"] == "역전":
            kind, pri, label = "comeback", 1, f"역전 {what}"
        elif hr:
            kind, pri, label = "home_run", 2 + (4 - (r["runs"] or 1)) / 10, what
        elif go_ahead.get(r["game_pk"]) == r["pa_id"]:
            kind, pri, label = "go_ahead", 3, f"결승 {what}"
        else:
            continue
        if hr and r["post_hr_seq"]:
            label += f" (포스트시즌 {r['post_hr_seq']}호)"
        out.append({"kind": kind, "pri": pri, "game_pk": r["game_pk"], "pa_id": r["pa_id"], "outing_id": None,
                    "label": f"{r['name']} {r['inning']}회{r['half']} {label} · {stage_label(g['stage'], g['n'])}",
                    "player": {"player_id": r["player_id"], "name": r["name"]}, "clip": _clip(r["clip"])})
    return out


def _pitch_scenes(rows: list[dict], games: dict) -> list[dict]:
    out = []
    for r in rows:
        g = games[r["game_pk"]]
        inn = f"{r['outs'] // 3}" + (f" {r['outs'] % 3}/3" if r["outs"] % 3 else "")
        what = f"{inn}이닝 무실점" + (f" {r['so']}K" if r["so"] else "") if r["starter"] else "무실점 마무리"
        out.append({"kind": "pitching", "pri": 2.5, "game_pk": r["game_pk"], "pa_id": None, "outing_id": r["outing_id"],
                    "label": f"{r['name']} {what} · {stage_label(g['stage'], g['n'])}",
                    "player": {"player_id": r["player_id"], "name": r["name"]}, "clip": _clip(r["clip"])})
    return out


def _pick(cands: list[dict], n: int) -> list[dict]:
    """우선순위 순으로 n개. 먼저 경기가 겹치지 않게 고르고, 모자라면 같은 경기에서 더"""
    cands = sorted(cands, key=lambda c: (c["pri"], c["game_pk"]))
    picked, seen = [], set()
    for c in cands:
        if c["game_pk"] not in seen and len(picked) < n:
            picked.append(c)
            seen.add(c["game_pk"])
    for c in cands:
        if c not in picked and len(picked) < n:
            picked.append(c)
    return [{k: v for k, v in c.items() if k != "pri"} for c in sorted(picked, key=lambda c: c["pri"])]


@router.get("/postseason", summary="25. 포스트시즌 코너 (메인)")
def get_postseason(  # API 25: 기간 중에만 메인에 그린다 (period.active, PS6)
    season: int | None = Query(None, description="생략하면 포스트시즌 경기가 있는 가장 최근 시즌"),
):
    if season is None:
        season = run(Q_LATEST_POST_SEASON)[0]["s"]
        if season is None:
            raise ApiError(404, "NO_POSTSEASON", "포스트시즌 경기 데이터가 없습니다")
    rows = run(Q_GAMES, season=season)
    games = {g["game_pk"]: g for g in rows}
    highlights = game_highlights(list(games))
    pa_scenes = _pa_scenes(run(Q_PA_SCENES, season=season, confirmed=CONFIRMED), games)
    pitch_scenes = _pitch_scenes(run(Q_OUTING_SCENES, season=season, confirmed=CONFIRMED, min_outs=PITCH_MIN_OUTS), games)

    series = []
    for stage in STAGE_ORDER:
        gs = [g for g in rows if g["stage"] == stage]
        if not gs:
            continue
        wins, winner = _winner_of(stage, gs)
        pks = {g["game_pk"] for g in gs}
        series.append({
            "stage": stage, "name": STAGE_NAME[stage], "teams": list(wins), "wins": wins, "winner": winner,
            "games": [{"game_pk": g["game_pk"], "series_game_no": g["n"], "date": g["date"],
                       "stage_label": stage_label(stage, g["n"]),
                       "away": {"team": g["away"], "score": g["away_final"]},
                       "home": {"team": g["home"], "score": g["home_final"]},
                       "highlight": highlights.get(g["game_pk"])} for g in gs],
            "scenes": _pick([c for c in pa_scenes + pitch_scenes if c["game_pk"] in pks], SCENES_PER_SERIES),
        })
    return {"season": season, "period": period(season), "series": series}
