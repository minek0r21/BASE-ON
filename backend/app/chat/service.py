"""
POST /chat 의 본체 — 질문 하나를 받아 답 하나를 돌려준다.

  ① LLM: 질문 → 메뉴 + 사람 이름 + 조건표          (prompts.parse_system)
  ② DB : 이름 → 선수 ID (여러 명이면 되묻기)          (routers.players.Q_SEARCH)
  ③ 연도가 없으면 되묻기
  ④ DB : 메뉴별 미리 써 둔 Cypher로 조회              (routers.chat.search_pa / search_games / season_stats)
     메뉴에 없는 질문은 LLM이 쓴 Cypher를 검사한 뒤 읽기 전용으로 실행
  ⑤ LLM: 조회 결과 → 한 줄 요약 (실패하면 정해진 문장)
숫자 · 날짜는 항상 DB에서 나오고, LLM은 질문 이해와 문장만 맡는다.
"""
import difflib
import json
import re
import time
from datetime import datetime
from pathlib import Path

import neo4j
from pydantic import BaseModel

from .. import db
from ..errors import ApiError
from . import llm, prompts

LOG = Path(__file__).resolve().parents[2] / "chat_logs" / "unanswered.jsonl"  # backend/chat_logs (git 제외)
SEASONS = [2026, 2025, 2024]


class ChatRequest(BaseModel):
    message: str
    context: dict | None = None    # 앞 답의 context (이어지는 질문용, 화면이 그대로 돌려보낸다)
    resolved: dict | None = None   # 되묻기에서 고른 값 {"batter": "52605", "season": 2025} — 같은 질문을 다시 보낼 때


def log_unanswered(message: str, reason: str, extra: dict | None = None):
    """못 답한 질문만 남긴다 (질문 문장 · 이유 · 시각. 개인정보 없음)"""
    try:
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "q": message, "reason": reason, **(extra or {})},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def say(text: str, **kw) -> dict:
    return {"type": "answer", "text": text, **kw}


# ------------------------------------------------------------------ ② 이름 → 선수
ROLE = {"batter": "batter", "pitcher": "pitcher", "player": None, "starter": "pitcher", "opp_starter": "pitcher", "players": None}
SLOT_KO = {"batter": "타자", "pitcher": "투수", "player": "선수", "starter": "선발 투수", "opp_starter": "상대 선발", "players": "선수"}


def find_player(name: str, role: str | None) -> list[dict]:
    from ..routers.players import Q_SEARCH, name_pattern
    q = "".join(name.split())
    rows = db.run(Q_SEARCH, q=q, pattern=name_pattern(q), role=role)
    exact = [r for r in rows if r["name"].replace(" ", "") == q]
    return exact or rows


PARTICLES = re.compile(r"(이랑|랑|이가|이는|이도|이의|에게|한테|상대로|선수|이|가|은|는|의|와|과|도)$")


def fix_name(name: str, message: str) -> str:
    """LLM이 이름을 잘못 옮겨 적은 경우(글자가 깨지거나 바뀜) 질문 속 가장 비슷한 낱말로 되돌린다"""
    if name.replace(" ", "") in message.replace(" ", ""):
        return name
    words = {PARTICLES.sub("", w) for w in re.findall(r"[가-힣A-Za-z]{2,}", message)}
    best = difflib.get_close_matches(name, [w for w in words if len(w) >= 2], n=1, cutoff=0.4)
    return best[0] if best else name


def resolve_people(people: dict, resolved: dict, message: str) -> tuple[dict | None, dict | None]:
    """people(이름) → ids. 되물어야 하면 (None, 되묻기 답), 못 찾으면 (None, 안내 답)"""
    ids: dict = {}
    for slot, role in ROLE.items():
        names = people.get(slot) or []
        names = names if isinstance(names, list) else [names]
        found = []
        for i, name in enumerate(n for n in names if n):
            key = slot if slot != "players" else f"players.{i}"
            if resolved.get(key):
                found.append(resolved[key]); continue
            name = fix_name(name, message)
            cands = find_player(name, role)
            if not cands:
                log_unanswered(message, "player_not_found", {"name": name})
                return None, say(f"「{name}」 선수를 찾지 못했어요. 이름을 다시 확인해 주세요.")
            if len(cands) > 1:
                return None, {"type": "clarify", "slot": key, "text": f"「{name}」 선수가 여러 명이에요. 누구를 말씀하시는 건가요?",
                              "options": [{"value": c["player_id"],
                                           "label": f"{c['name']} ({c.get('team') or '팀 없음'} · {c.get('position') or ''} · {c.get('last_season') or ''})"}
                                          for c in cands[:6]]}
            found.append(cands[0]["player_id"])
        if found:
            ids[slot] = found if slot == "players" else found[0]
    return ids, None


# ------------------------------------------------------------------ ④ 메뉴별 조회
PA_KEYS = ["results", "season", "date_from", "date_to", "stadium", "bat_team", "pit_team", "home_away", "inning_from", "inning_to",
           "inning_half", "situations", "bases", "outs", "balls", "strikes", "pitch_names", "speed_min", "speed_max", "video_only"]
GAME_KEYS = ["team", "opponent", "season", "date_from", "date_to", "home_away", "result"]


def pick(cond: dict, keys: list[str]) -> dict:
    return {k: cond[k] for k in keys if cond.get(k) not in (None, "", [])}


def latest_team(player_id: str, season: int | None = None) -> str | None:
    r = db.run("""MATCH (:Player {player_id: $id})-[f:PLAYS_FOR]->(t:Team) WHERE $season IS NULL OR f.season = $season
                  RETURN t.name AS team ORDER BY f.season DESC, f.last_date DESC LIMIT 1""", id=player_id, season=season)
    return r[0]["team"] if r else None


def run_menu(menu: str, ids: dict, cond: dict) -> dict:
    from ..routers import chat as api
    if menu == "pa":
        body = pick(cond, PA_KEYS)
        body.update({k: v for k, v in (("batter_id", ids.get("batter")), ("pitcher_id", ids.get("pitcher"))) if v})
        return {"menu": "pa", **api.search_pa(api.PASearch(**body))}
    if menu == "games":
        body = pick(cond, GAME_KEYS)
        if not body.get("team"):  # 팀을 말하지 않았으면 선발 · 같이 뛴 선수의 그 시즌(없으면 최근) 팀으로
            who = ids.get("starter") or (ids.get("players") or [None])[0]
            if who:
                body["team"] = latest_team(who, body.get("season"))
        if not body.get("team"):
            raise ApiError(400, "NEED_TEAM", "어느 팀 기준인지 함께 말씀해 주세요. 예: KIA가 …")
        body.update({k: v for k, v in (("starter_id", ids.get("starter")), ("opp_starter_id", ids.get("opp_starter")),
                                       ("player_ids", ids.get("players"))) if v})
        return {"menu": "games", **api.search_games(api.GameSearch(**body))}
    if menu == "stats":
        if not ids.get("player"):
            raise ApiError(400, "NEED_PLAYER", "어느 선수의 기록인지 말씀해 주세요.")
        return {"menu": "stats", **api.season_stats(player_id=ids["player"], season=int(cond["season"]))}
    raise ApiError(400, "BAD_MENU", menu)


# ------------------------------------------------------------------ ④' 메뉴에 없는 질문 → LLM이 쓴 Cypher
BANNED = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|CALL|FOREACH|USE|SHOW|TERMINATE|GRANT|DENY|REVOKE)\b|apoc\.|dbms\.|db\.", re.I)


def guard(cypher: str) -> str:
    """읽기 전용 문장만 통과. 마지막 LIMIT이 없거나 크면 20으로"""
    c = cypher.strip().rstrip(";").strip()
    if ";" in c:
        raise ValueError("문장이 여러 개예요")
    if BANNED.search(c):
        raise ValueError("읽기 전용이 아닌 명령이 있어요")
    if not re.match(r"^(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND)\b", c, re.I) or not re.search(r"\bRETURN\b", c, re.I):
        raise ValueError("MATCH … RETURN 모양이 아니에요")
    m = re.search(r"\bLIMIT\s+(\d+)\s*$", c, re.I)
    if not m:
        c += "\nLIMIT 20"
    elif int(m.group(1)) > 20:
        c = c[: m.start(1)] + "20"
    return c


def plain(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, list):
        return [plain(x) for x in v]
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    return str(v)  # 날짜 · 노드 등


def run_read(cypher: str) -> tuple[list[str], list[list]]:
    """읽기 전용 트랜잭션 + 10초 제한. 문법은 EXPLAIN으로 먼저 확인"""
    @neo4j.unit_of_work(timeout=10)
    def explain(tx):
        tx.run("EXPLAIN " + cypher).consume()

    @neo4j.unit_of_work(timeout=10)
    def fetch(tx):
        r = tx.run(cypher)
        return r.keys(), [list(x.values()) for x in r]

    with db._driver.session(database=db.DATABASE, default_access_mode=neo4j.READ_ACCESS) as s:
        s.execute_read(explain)
        cols, rows = s.execute_read(fetch)
    return list(cols), [[plain(v) for v in row] for row in rows]


def run_other(message: str, ids: dict) -> dict:
    flat = {}
    for slot, v in ids.items():
        for x in (v if isinstance(v, list) else [v]):
            flat[f"{SLOT_KO[slot]} {x}"] = x
    out = llm.complete_json(prompts.cypher_system(flat), message)
    cypher, explain = out.get("cypher"), out.get("explain") or ""
    if not cypher:
        log_unanswered(message, "other_no_cypher")
        return say("아직 답할 수 없는 질문이에요. 선수 · 타석 · 경기 · 시즌 기록으로 물어봐 주세요.")
    try:
        cols, rows = run_read(guard(cypher))
    except (ValueError, neo4j.exceptions.Neo4jError) as e:
        log_unanswered(message, "other_cypher_error", {"cypher": cypher, "error": str(e)[:300]})
        return say("이 질문은 아직 정확히 찾지 못했어요. 조금 다르게 물어봐 주세요.")
    return {"menu": "other", "conditions": [explain] if explain else [], "columns": cols, "table": rows,
            "total": len(rows), "shown": len(rows), "note": "메뉴에 없는 질문이라 자동으로 조회했어요. 참고용으로 봐 주세요.",
            "cypher": cypher}


# ------------------------------------------------------------------ ⑤ 요약
def summarize(message: str, result: dict) -> str:
    slim = {k: result.get(k) for k in ("menu", "conditions", "total", "shown", "record", "name", "season", "columns") if k in result}
    if result.get("rows"):
        slim["rows"] = [{k: r.get(k) for k in ("date", "batter", "pitcher", "bat_team", "pit_team", "inning", "inning_half", "result",
                                                "opponent", "team_score", "opp_score") if r.get(k) is not None} for r in result["rows"][:10]]
    if result.get("table"):
        slim["table"] = result["table"][:10]
    for k in ("batting", "pitching"):
        if result.get(k):  # 소수는 3자리로 (0.3091 → 0.309)
            slim[k] = {x: (round(y, 3) if isinstance(y, float) else y) for x, y in result[k].items()
                       if not x.startswith("pct_") and x not in ("stat_id",)}
    try:
        return llm.complete(prompts.SUMMARY_SYSTEM, json.dumps({"question": message, "result": slim}, ensure_ascii=False)).strip()
    except llm.LLMError:
        n = result.get("total")
        return f"조건에 맞는 기록이 {n}개 있어요." if n else ("조건에 맞는 기록이 없어요." if n == 0 else "기록을 찾았어요.")


# ------------------------------------------------------------------ 전체
def chat(req: ChatRequest) -> dict:
    t0 = time.time()
    message = req.message.strip()[:300]
    resolved = req.resolved or {}
    if not message:
        return say("질문을 입력해 주세요.")
    if not llm.ready():
        return say("챗봇의 LLM 키가 아직 설정되지 않았어요 (.env의 LLM_PROVIDER · 키).")
    try:
        parsed = llm.complete_json(prompts.parse_system(),
                                   json.dumps({"question": message, "previous": (req.context or {}).get("parsed")}, ensure_ascii=False))
    except llm.LLMError as e:
        log_unanswered(message, "llm_error", {"error": str(e)[:200]})
        return say("지금 질문을 이해하는 데 문제가 생겼어요. 잠시 뒤 다시 시도해 주세요.", error=True)

    menu = parsed.get("menu")
    people = parsed.get("people") or {}
    cond = parsed.get("cond") or {}
    if menu == "chat" or menu not in ("pa", "games", "stats", "other"):
        return say(parsed.get("reply") or "선수 · 타석 · 경기 기록을 물어봐 주세요. 예: 김도영 2024 홈런 영상")

    ids, stop = resolve_people(people, resolved, message)
    if stop:
        return stop

    # ③ 연도 되묻기 — 연도도 날짜도 없으면 (stats는 시즌이 꼭 필요)
    if "season" in resolved:
        cond["season"] = resolved["season"] or None   # 0 = 전체 시즌
    no_when = not cond.get("season") and not cond.get("date_from") and not cond.get("date_to")
    if menu in ("pa", "games", "stats") and no_when and not parsed.get("year_given") and "season" not in resolved:
        opts = [{"value": s, "label": f"{s} 시즌"} for s in SEASONS] + ([] if menu == "stats" else [{"value": 0, "label": "전체 (2024~)"}])
        return {"type": "clarify", "slot": "season", "text": "어느 시즌을 말씀하시는 건가요?", "options": opts}
    if menu == "stats" and not cond.get("season"):
        cond["season"] = SEASONS[0]
    # 연도 없이 "7월 이후"였던 질문: 시즌을 고르면 그 해 날짜로 다시 해석하도록 질문에 연도를 붙여 다시 돈다
    if "season" in resolved and resolved["season"] and parsed.get("year_given") is False and re.search(r"\d+\s*월", message):
        req2 = ChatRequest(message=f"{resolved['season']}년 {message}", context=req.context,
                           resolved={k: v for k, v in resolved.items() if k != "season"} | {"season": resolved["season"]})
        if not message.startswith(f"{resolved['season']}년"):
            return chat(req2)

    try:
        result = run_menu(menu, ids, cond) if menu != "other" else run_other(message, ids)
    except ApiError as e:
        log_unanswered(message, e.code, {"detail": e.message, "parsed": parsed})
        if menu != "other" and e.code in ("BAD_CONDITION",):
            try:
                result = run_other(message, ids)
            except llm.LLMError:
                return say(e.message)
        else:
            return say(e.message)
    except llm.LLMError as e:
        log_unanswered(message, "llm_error", {"error": str(e)[:200]})
        return say("지금 질문을 처리하는 데 문제가 생겼어요. 잠시 뒤 다시 시도해 주세요.", error=True)
    if result.get("type") == "answer" and "menu" not in result:
        return result  # run_other가 안내 문장으로 끝낸 경우

    if result.get("total") == 0:
        log_unanswered(message, "zero_rows", {"parsed": parsed})
    result["text"] = summarize(message, result)
    result["type"] = "answer"
    result["context"] = {"parsed": {"menu": menu, "people": people, "cond": cond, "year_given": True}}
    result["ms"] = int((time.time() - t0) * 1000)
    return result
