"""
챗봇 조회 API. 조회 4개는 LLM 없이 조건표만으로 돈다. 질문 해석은 /chat (app/chat/service.py)

  GET  /chat/status            챗봇을 켤지 (서버에 AI 키가 있나) + 기록 기준일 — 화면이 💬 버튼을 그릴지 정한다
  GET  /chat/players?name=     이름 → 선수 후보 (여러 명이면 되묻기에 쓴다)
  POST /chat/search/pa         타석 검색 (조건표 → 총 개수 + 최근 10개 + 확정 영상)
  POST /chat/search/games      경기 검색 (팀 기준 → 경기 목록 + 승 · 패 · 무 · 승률)
  GET  /chat/stats             시즌 기록 (선수 + 시즌 → 저장된 지표 전부)
  POST /chat                   챗봇 본체 (질문 → 답). 본체 로직은 app/chat/service.py

Cypher는 미리 써 둔 조건 조각만 골라 붙인다. 값은 항상 파라미터로 넘긴다 (사용자 입력을 문장에 넣지 않는다).
"""
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from ..chat import terms
from ..db import run
from ..errors import ApiError
from ..events import events_ko
from ..scenes import CONFIRMED
from .players import Q_SEARCH, name_pattern

router = APIRouter(prefix="/chat", tags=["챗봇"])
LIMIT = 10


def bad(msg: str):
    raise ApiError(400, "BAD_CONDITION", msg)


# ------------------------------------------------------------------ 이름 → 선수
@router.get("/players", summary="챗봇: 이름 → 선수 후보")
def find_players(
    name: str = Query(..., min_length=1),
    role: Literal["batter", "pitcher"] | None = Query(None),
):
    q = "".join(name.split())
    rows = run(Q_SEARCH, q=q, pattern=name_pattern(q), role=role)
    exact = [r for r in rows if r["name"].replace(" ", "") == q]
    pool = exact or rows
    return {
        "status": "none" if not pool else "one" if len(pool) == 1 else "many",
        "candidates": [{k: r[k] for k in ("player_id", "name", "team", "position", "last_season")} for r in pool[:8]],
    }


# ------------------------------------------------------------------ 타석 검색
class PASearch(BaseModel):
    batter_id: str | None = None
    pitcher_id: str | None = None
    results: list[str] | None = Field(None, description="안타 · 장타 · 출루 · 홈런 · 2루타 … 또는 events 값")
    season: int | None = None
    date_from: str | None = Field(None, description="YYYY-MM-DD")
    date_to: str | None = None
    stadium: str | None = Field(None, description="잠실 · 고척 … (홈팀으로 판단)")
    bat_team: str | None = None
    pit_team: str | None = None
    home_away: Literal["home", "away"] | None = Field(None, description="타자 팀 기준")
    inning_from: int | None = None
    inning_to: int | None = None
    inning_half: Literal["초", "말"] | None = None
    situations: list[str] | None = Field(None, description="끝내기 · 역전 · 동점 · 리드")
    bases: str | None = Field(None, description="주자 없음 · 1루 · 2루 · 3루 · 1,2루 · 1,3루 · 2,3루 · 만루 · 득점권")
    outs: int | None = None
    balls: int | None = None
    strikes: int | None = None
    pitch_names: list[str] | None = Field(None, description="마지막 공 구종 (DB 값)")
    speed_min: float | None = None
    speed_max: float | None = None
    game_type: Literal["regular", "postseason", "all"] = "regular"
    video_only: bool = False
    offset: int = 0


def pa_where(c: PASearch) -> tuple[str, dict, list[str]]:
    """조건표 → (WHERE 문, 파라미터, 사람이 읽는 조건)"""
    w, p, said = [], {}, []
    try:
        ev = terms.events_of(c.results)
        bt, pt = terms.team_of(c.bat_team), terms.team_of(c.pit_team)
        st = terms.stadium_teams(c.stadium)
    except ValueError as e:
        bad(str(e))
    if c.batter_id:
        w.append("b.player_id = $batter"); p["batter"] = c.batter_id
    if c.pitcher_id:
        w.append("pit.player_id = $pitcher"); p["pitcher"] = c.pitcher_id
    if ev:
        w.append("pa.events IN $events"); p["events"] = ev; said.append(" · ".join(c.results))
    if c.season:
        w.append("pa.season = $season"); p["season"] = c.season; said.append(f"{c.season} 시즌")
    if c.date_from:
        w.append("pa.date >= date($date_from)"); p["date_from"] = c.date_from; said.append(f"{c.date_from} 이후")
    if c.date_to:
        w.append("pa.date <= date($date_to)"); p["date_to"] = c.date_to; said.append(f"{c.date_to}까지")
    if st:
        w.append("h.name IN $stadium"); p["stadium"] = st; said.append(f"{c.stadium}({'·'.join(st)} 홈경기)")
    if bt:
        w.append("bt.name = $bat_team"); p["bat_team"] = bt; said.append(f"{bt} 공격")
    if pt:
        w.append("pt.name = $pit_team"); p["pit_team"] = pt; said.append(f"상대 {pt}")
    if c.home_away:
        w.append("pa.inning_half = $ha"); p["ha"] = "말" if c.home_away == "home" else "초"; said.append("홈" if c.home_away == "home" else "원정")
    if c.inning_from is not None:
        w.append("pa.inning >= $inn_from"); p["inn_from"] = c.inning_from
    if c.inning_to is not None:
        w.append("pa.inning <= $inn_to"); p["inn_to"] = c.inning_to
    if c.inning_from is not None or c.inning_to is not None:
        a, z = c.inning_from, c.inning_to
        said.append(f"{a}회" if a == z else f"{a}회 이후" if z is None else f"{z}회까지" if a is None else f"{a}~{z}회")
    if c.inning_half:
        w.append("pa.inning_half = $half"); p["half"] = c.inning_half; said.append(f"{c.inning_half}")
    # AI가 「득점권」 · 「만루」 같은 주자 말을 상황 칸에 넣는 일이 있다 → 주자 칸으로 옮긴다
    if moved := [s for s in c.situations or [] if s == terms.RISP or s in terms.BASES]:
        c.bases = c.bases or moved[0]
        c.situations = [s for s in c.situations if s not in moved] or None
    if c.situations:
        if bad_s := [s for s in c.situations if s not in terms.SITUATIONS]:
            bad(f"모르는 상황: {bad_s}")
        w.append("pa.situation IN $sits"); p["sits"] = c.situations; said.append(" · ".join(c.situations))
    if c.bases:
        if c.bases == terms.RISP:
            w.append("(pa.on_2b OR pa.on_3b)")
        elif c.bases in terms.BASES:
            b1, b2, b3 = terms.BASES[c.bases]
            w.append("pa.on_1b = $b1 AND pa.on_2b = $b2 AND pa.on_3b = $b3"); p.update(b1=b1, b2=b2, b3=b3)
        else:
            bad(f"모르는 주자 상황: {c.bases}")
        said.append(c.bases)
    if c.outs is not None:
        w.append("pa.outs_when_up = $outs"); p["outs"] = c.outs; said.append(f"{c.outs}아웃")
    if c.balls is not None:
        w.append("pa.final_balls = $balls"); p["balls"] = c.balls
    if c.strikes is not None:
        w.append("pa.final_strikes = $strikes"); p["strikes"] = c.strikes
    if c.balls is not None or c.strikes is not None:
        said.append(f"카운트 {c.balls if c.balls is not None else '-'}-{c.strikes if c.strikes is not None else '-'}")
    if c.pitch_names:
        try:
            pn = terms.pitches_of(c.pitch_names)
        except ValueError as e:
            bad(str(e))
        w.append("pa.last_pitch_name IN $pitches"); p["pitches"] = pn; said.append(" · ".join(c.pitch_names))
    if c.speed_min is not None:
        w.append("pa.last_pitch_speed >= $smin"); p["smin"] = c.speed_min; said.append(f"{c.speed_min:g}km 이상")
    if c.speed_max is not None:
        w.append("pa.last_pitch_speed <= $smax"); p["smax"] = c.speed_max; said.append(f"{c.speed_max:g}km 이하")
    if c.game_type != "all":
        w.append("coalesce(pa.game_type, 'regular') = $gt"); p["gt"] = c.game_type
        said.append("포스트시즌" if c.game_type == "postseason" else "정규시즌")  # 기본값도 화면에 밝힌다
    if c.video_only:
        w.append("EXISTS { (pa)-[x:MATCHED_TO]->(:VideoLink) WHERE x.status IN $confirmed AND coalesce(x.precision, 'scene') <> 'game' }")
        said.append("영상 있는 것만")
    p["confirmed"] = CONFIRMED
    return (" WHERE " + " AND ".join(w)) if w else "", p, said


PA_MATCH = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance)<-[:PITCHED_IN]-(pit:Player)
MATCH (pa)-[:PART_OF]->(g:Game)-[:HOME]->(h:Team), (g)-[:AWAY]->(a:Team)
WITH b, pit, pa, g, h, a,
     CASE pa.inning_half WHEN '초' THEN a ELSE h END AS bt,
     CASE pa.inning_half WHEN '초' THEN h ELSE a END AS pt
"""
PA_ROWS = """
WITH b, pit, pa, g, h, a, bt, pt ORDER BY pa.date DESC, g.dh_no DESC, pa.at_bat_number DESC
SKIP $offset LIMIT $limit
OPTIONAL MATCH (pa)-[m:MATCHED_TO]->(v:VideoLink)
  WHERE m.status IN $confirmed AND coalesce(m.precision, 'scene') <> 'game' AND coalesce(v.playable, true)
WITH b, pit, pa, g, h, a, bt, pt, m, v ORDER BY m.rank
WITH b, pit, pa, g, h, a, bt, pt, collect({v: v, m: m})[0] AS best
RETURN pa.pa_id AS pa_id, toString(pa.date) AS date, g.game_pk AS game_pk, g.game_type AS game_type,
       b.player_id AS batter_id, b.name AS batter, pit.player_id AS pitcher_id, pit.name AS pitcher,
       bt.name AS bat_team, pt.name AS pit_team, h.name AS home, a.name AS away,
       pa.inning AS inning, pa.inning_half AS inning_half, pa.events AS events, pa.runs_scored AS runs,
       pa.situation AS situation, pa.outs_when_up AS outs, pa.on_1b AS on_1b, pa.on_2b AS on_2b, pa.on_3b AS on_3b,
       pa.final_balls AS balls, pa.final_strikes AS strikes,
       pa.last_pitch_name AS pitch, pa.last_pitch_speed AS speed, pa.hr_seq AS hr_seq,
       best.v.video_id AS video_id, best.v.title AS video_title, best.v.duration_sec AS duration_sec,
       best.m.start_sec AS start_sec, best.m.end_sec AS end_sec, best.m.precision AS precision
ORDER BY pa.date DESC, g.dh_no DESC, pa.at_bat_number DESC
"""


def names_of(ids: list[str]) -> dict[str, str]:
    ids = [i for i in ids if i]
    return {r["id"]: r["name"] for r in run("MATCH (p:Player) WHERE p.player_id IN $ids RETURN p.player_id AS id, p.name AS name", ids=ids)} if ids else {}


@router.post("/search/pa", summary="챗봇: 타석 검색")
def search_pa(c: PASearch):
    if not (c.batter_id or c.pitcher_id or c.bat_team or c.pit_team):
        bad("타자 · 투수 · 팀 중 하나는 있어야 해요")
    where, p, said = pa_where(c)
    nm = names_of([c.batter_id, c.pitcher_id])
    head = [x for x in (nm.get(c.batter_id), c.pitcher_id and f"투수 {nm.get(c.pitcher_id)}") if x]
    total = run(PA_MATCH + where + " RETURN count(pa) AS n", **p)[0]["n"]
    rows = run(PA_MATCH + where + PA_ROWS, **p, offset=c.offset, limit=LIMIT)
    for r in rows:
        r["result"] = events_ko(r["events"])
        r["video"] = None if not r["video_id"] else {
            "video_id": r["video_id"], "title": r["video_title"], "duration_sec": r["duration_sec"],
            "start_sec": r["start_sec"] or 0, "end_sec": r["end_sec"], "precision": r["precision"] or "scene"}
        for k in ("video_id", "video_title", "duration_sec", "start_sec", "end_sec", "precision"):
            r.pop(k)
    return {"conditions": head + said, "total": total, "shown": len(rows), "offset": c.offset, "rows": rows}


# ------------------------------------------------------------------ 경기 검색
class GameSearch(BaseModel):
    team: str
    opponent: str | None = None
    season: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    home_away: Literal["home", "away"] | None = None
    starter_id: str | None = Field(None, description="이 팀 선발 투수")
    opp_starter_id: str | None = Field(None, description="상대 팀 선발 투수")
    player_ids: list[str] | None = Field(None, description="이 팀으로 모두 출전한 선수")
    result: Literal["승", "패", "무"] | None = None
    game_type: Literal["regular", "postseason", "all"] = "regular"
    offset: int = 0


GAME_MATCH = """
MATCH (g:Game)-[:HOME]->(h:Team), (g)-[:AWAY]->(a:Team)
WHERE h.name = $team OR a.name = $team
WITH g, h, a, h.name = $team AS is_home
WITH g, is_home, CASE WHEN is_home THEN h ELSE a END AS my, CASE WHEN is_home THEN a ELSE h END AS opp,
     CASE WHEN is_home THEN g.home_final ELSE g.away_final END AS my_r,
     CASE WHEN is_home THEN g.away_final ELSE g.home_final END AS opp_r
WITH g, is_home, my, opp, my_r, opp_r, CASE WHEN my_r > opp_r THEN '승' WHEN my_r < opp_r THEN '패' ELSE '무' END AS res
"""
APPEARED = """EXISTS { MATCH (:Player {player_id: pid})-[:BATTED_IN]->(x:PlateAppearance)-[:PART_OF]->(g) WHERE (x.inning_half = '말') = is_home }
 OR EXISTS { MATCH (:Player {player_id: pid})-[:PITCHED_GAME]->(o:Outing)-[:PART_OF]->(g) WHERE o.team_id = my.team_id }"""
STARTER = """EXISTS { MATCH (:Player {player_id: $%s})-[:PITCHED_GAME]->(o:Outing {starter: true})-[:PART_OF]->(g) WHERE o.team_id = %s.team_id }"""


@router.post("/search/games", summary="챗봇: 경기 검색 (승률)")
def search_games(c: GameSearch):
    try:
        team, opp = terms.team_of(c.team), terms.team_of(c.opponent)
    except ValueError as e:
        bad(str(e))
    w, p, said = [], {"team": team}, [team]
    if opp:
        w.append("opp.name = $opp"); p["opp"] = opp; said.append(f"상대 {opp}")
    if c.season:
        w.append("g.season = $season"); p["season"] = c.season; said.append(f"{c.season} 시즌")
    if c.date_from:
        w.append("g.date >= date($date_from)"); p["date_from"] = c.date_from; said.append(f"{c.date_from} 이후")
    if c.date_to:
        w.append("g.date <= date($date_to)"); p["date_to"] = c.date_to; said.append(f"{c.date_to}까지")
    if c.home_away:
        w.append("is_home = $is_home"); p["is_home"] = c.home_away == "home"; said.append("홈" if c.home_away == "home" else "원정")
    nm = names_of([c.starter_id, c.opp_starter_id, *(c.player_ids or [])])
    if c.starter_id:
        w.append(STARTER % ("starter", "my")); p["starter"] = c.starter_id; said.append(f"선발 {nm.get(c.starter_id)}")
    if c.opp_starter_id:
        w.append(STARTER % ("opp_starter", "opp")); p["opp_starter"] = c.opp_starter_id; said.append(f"상대 선발 {nm.get(c.opp_starter_id)}")
    if c.player_ids:
        w.append(f"ALL(pid IN $players WHERE {APPEARED})"); p["players"] = c.player_ids
        said.append(" · ".join(nm.get(i, i) for i in c.player_ids) + " 출전")
    if c.game_type != "all":
        w.append("coalesce(g.game_type, 'regular') = $gt"); p["gt"] = c.game_type
        said.append("포스트시즌" if c.game_type == "postseason" else "정규시즌")
    where =(" WHERE " + " AND ".join(w)) if w else ""
    rec = run(GAME_MATCH + where + " RETURN res, count(*) AS n", **p)
    n = {r["res"]: r["n"] for r in rec}
    wins, loss, draw = n.get("승", 0), n.get("패", 0), n.get("무", 0)
    if c.result:
        where += (" AND " if where else " WHERE ") + "res = $res"; p["res"] = c.result; said.append(f"{c.result}한 경기")
    rows = run(GAME_MATCH + where + """
        RETURN g.game_pk AS game_pk, toString(g.date) AS date, g.game_type AS game_type, properties(g)['stage'] AS stage,  // 포스트시즌이 없는 DB에서도 경고 없이
               is_home, my.name AS team, opp.name AS opponent, my_r AS team_score, opp_r AS opp_score, res AS result
        ORDER BY g.date DESC, g.dh_no DESC SKIP $offset LIMIT $limit""", **p, offset=c.offset, limit=LIMIT)
    total = sum(n.values()) if not c.result else n.get(c.result, 0)
    return {"conditions": said, "total": total, "shown": len(rows), "offset": c.offset,
            "record": {"win": wins, "loss": loss, "draw": draw,
                       "win_pct": round(wins / (wins + loss), 3) if wins + loss else None},  # 무승부는 승률에서 뺀다
            "rows": rows}


# ------------------------------------------------------------------ 시즌 기록
@router.get("/stats", summary="챗봇: 시즌 기록")
def season_stats(player_id: str = Query(...), season: int = Query(...)):
    rows = run("""
        MATCH (p:Player {player_id: $id})-[:HAS_STAT|HAS_PITCHING_STAT]->(s) WHERE s.season = $season  // 투수 기록은 HAS_PITCHING_STAT
        RETURN p.name AS name, labels(s)[0] AS kind, s {.*} AS stat""", id=player_id, season=season)
    if not rows:
        raise ApiError(404, "NO_SEASON_RECORD", f"{season} 시즌 기록이 없어요")
    return {"player_id": player_id, "name": rows[0]["name"], "season": season,
            "batting": next((r["stat"] for r in rows if r["kind"] == "BatterSeasonStat"), None),
            "pitching": next((r["stat"] for r in rows if r["kind"] == "PitcherSeasonStat"), None)}


# ------------------------------------------------------------------ 챗봇 본체
@router.get("/status", summary="챗봇: 켜졌나 + 기록 기준일")
def status():
    from ..chat import llm
    from ..chat.service import as_of
    return {"enabled": llm.ready(), "as_of": as_of()}


@router.post("", summary="챗봇: 질문 하나 → 답 (호출 제한 → 질문 이해 → 되묻기 → 조회 → 답 문장)")
def chat(req: "ChatRequest", request: Request):
    from ..chat.service import chat as run_chat
    # 서버에서는 Caddy가 넘긴 X-Forwarded-For가 client.host가 된다 (uvicorn --proxy-headers --forwarded-allow-ips)
    return run_chat(req, ip=request.client.host if request.client else "-")


from ..chat.service import ChatRequest  # noqa: E402  (위 함수의 입력 모양. service가 이 파일을 늦게 불러서 순환이 없다)
