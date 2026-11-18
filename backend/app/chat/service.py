"""
POST /chat 의 본체 — 질문 하나를 받아 답 하나를 돌려준다. AI 호출은 질문당 1번(①)뿐이다.

  ⓪ 호출 제한: IP별 1분 · 하루, 서버 하루 상한        (limits.py)
  ① LLM: 질문 → 메뉴 + 사람 이름 + 조건표          (prompts.parse_system)
  ② DB : 이름 → 선수 ID (여러 명이면 되묻기)          (routers.players.Q_SEARCH)
  ③ 기준일(7.26) 뒤만 묻는 질문은 조회 없이 안내, 연도가 없으면 되묻기
  ④ DB : 메뉴별 미리 써 둔 Cypher로 조회              (routers.chat.search_pa / search_games / season_stats)
     메뉴에 없는 질문(other)은 서버에서 「아직 못 답함」. 로컬에서 CHAT_OTHER=on일 때만 LLM이 쓴 Cypher를 읽기 전용으로 실행
  ⑤ 답 문장: 조회 결과 숫자로 코드가 채운다           (answers.py — AI가 숫자를 옮겨 적지 않는다)
"""
import difflib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import neo4j
from pydantic import BaseModel

from .. import db
from ..errors import ApiError
from . import answers, limits, llm, prompts

LOG = Path(__file__).resolve().parents[2] / "chat_logs" / "unanswered.jsonl"  # backend/chat_logs (git 제외)
SEASONS = [2026, 2025, 2024]
# other(LLM이 쓴 Cypher)는 검증 안 된 숫자라 서버에서는 끈다. 로컬에서 어떤 질문이 메뉴 밖으로 가는지 볼 때만 on
OTHER_ON = os.getenv("CHAT_OTHER", "off").strip().lower() == "on"

_as_of: tuple[float, str | None] = (0.0, None)


def as_of() -> str | None:
    """DB의 마지막 경기일 (meta API와 같은 값). 10분 동안 기억한다 — DB를 바꿔 끼워도 곧 따라간다"""
    global _as_of
    if time.time() - _as_of[0] > 600 or not _as_of[1]:
        from ..routers.meta import Q_META
        try:
            _as_of = (time.time(), db.run(Q_META)[0]["data_as_of"])
        except Exception:  # DB가 잠깐 안 될 때 챗봇 전체가 멈추지 않게 (이전 값 유지)
            return _as_of[1]
    return _as_of[1]


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


# 메뉴마다 쓸 수 있는 사람 칸. 여기 없는 칸에 사람이 오면 조용히 버리지 않고 알린다 (버리면 조건이 빠진 채 틀린 숫자가 나온다)
USABLE = {"pa": {"batter", "pitcher", "player", "starter", "opp_starter", "players"},
          "games": {"starter", "opp_starter", "players", "batter"},
          "stats": {"player", "batter", "pitcher"}}


def run_menu(menu: str, ids: dict, cond: dict) -> dict:
    from ..routers import chat as api
    if extra := [s for s in ids if s not in USABLE.get(menu, set())]:
        raise ApiError(400, "UNUSED_PERSON", f"{' · '.join(SLOT_KO[s] for s in extra)} 조건은 이 질문에서 아직 걸 수 없어요. 조건을 나눠서 물어봐 주세요.")
    if menu == "pa":
        body = pick(cond, PA_KEYS)
        batter = ids.get("batter") or (None if ids.get("pitcher") else ids.get("player"))  # pa에 player로 오면 타자로
        body.update({k: v for k, v in (("batter_id", batter), ("pitcher_id", ids.get("pitcher"))) if v})
        if starters := [i for i in (ids.get("starter"), ids.get("opp_starter")) if i]:  # 「양현종이 선발로 나온 경기에서」
            body["game_starter_ids"] = starters
        if ids.get("players"):  # 「김도영이랑 나성범이 같이 뛴 날」
            body["game_player_ids"] = ids["players"]
        return {"menu": "pa", **api.search_pa(api.PASearch(**body))}
    if menu == "games":
        body = pick(cond, GAME_KEYS)
        if ids.get("batter"):  # 「김도영이 홈런 친 날」
            body["pa_batter_id"] = ids["batter"]
            if cond.get("batter_results"):
                body["pa_results"] = cond["batter_results"]
        if not body.get("team"):  # 팀을 말하지 않았으면 선발 · 같이 뛴 선수 · 그 타자의 그 시즌(없으면 최근) 팀으로
            who = ids.get("starter") or (ids.get("players") or [None])[0] or ids.get("batter")
            if who:
                body["team"] = latest_team(who, body.get("season"))
        if not body.get("team"):
            raise ApiError(400, "NEED_TEAM", "어느 팀 기준인지 함께 말씀해 주세요. 예: KIA가 …")
        body.update({k: v for k, v in (("starter_id", ids.get("starter")), ("opp_starter_id", ids.get("opp_starter")),
                                       ("player_ids", ids.get("players"))) if v})
        return {"menu": "games", **api.search_games(api.GameSearch(**body))}
    if menu == "stats":
        if not ids.get("player") and (ids.get("batter") or ids.get("pitcher")):
            ids = {**ids, "player": ids.get("batter") or ids.get("pitcher")}
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
    """로컬 전용 (CHAT_OTHER=on). 어떤 질문이 메뉴 밖으로 가는지, AI가 어떻게 풀려는지 보고 새 메뉴 · 조건 칸 후보를 찾는 데 쓴다.
    숫자는 검증 전이라 채점 정답으로 옮기지 않는다"""
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
    log_unanswered(message, "other_ran", {"cypher": cypher, "rows": len(rows)})  # Cypher 원문은 기록에만 (응답에 싣지 않는다)
    return {"menu": "other", "conditions": [explain] if explain else [], "columns": cols, "table": rows,
            "total": len(rows), "shown": len(rows), "note": "메뉴에 없는 질문이라 자동으로 조회했어요. 참고용 (로컬 전용)"}


# ------------------------------------------------------------------ 전체
def friendly(msg: str) -> str:
    """조회 쪽 에러 문구(「모르는 구장: 고척돔」)를 사용자에게 보일 말로"""
    m = re.match(r"모르는 ([^:]+):\s*(.+)", msg)
    if not m:
        return msg
    kind, word = m.group(1).strip(), m.group(2).strip(" []'\"")
    return f"「{word}」{'은' if answers.has_batchim(word) else '는'} 아직 알아듣지 못하는 {kind} 표현이에요. 다른 말로 물어봐 주세요."


NOT_YET = "아직 답할 수 없는 질문이에요. 한 선수의 타석 · 시즌 기록이나 한 팀의 경기 결과로 물어봐 주세요."


def chat(req: ChatRequest, ip: str = "-") -> dict:
    message = req.message.strip()[:300]
    if not message:
        return say("질문을 입력해 주세요.")
    if not llm.ready():
        return say("챗봇이 지금 꺼져 있어요.", reason="off")
    if blocked := limits.limiter.check(ip):
        return say(limits.MESSAGE[blocked], reason="limited")
    return answer(req, message)


def answer(req: ChatRequest, message: str) -> dict:
    t0 = time.time()
    resolved = req.resolved or {}
    day = as_of()
    try:
        parsed = llm.complete_json(prompts.parse_system(day),
                                   json.dumps({"question": message, "previous": (req.context or {}).get("parsed")}, ensure_ascii=False))
    except llm.LLMError as e:
        log_unanswered(message, "llm_error", {"error": str(e)[:200]})
        return say("지금 질문을 이해하는 데 문제가 생겼어요. 잠시 뒤 다시 시도해 주세요.", error=True)

    menu = parsed.get("menu")
    people = parsed.get("people") or {}
    cond = {k: v for k, v in (parsed.get("cond") or {}).items() if v not in (None, "", [])}
    ctx = {"parsed": {"menu": menu, "people": people, "cond": cond, "year_given": True}}  # 이어 묻기 · 채점용
    if menu == "chat" or menu not in ("pa", "games", "stats", "other"):
        return say(parsed.get("reply") or "선수 · 타석 · 경기 기록을 물어봐 주세요. 예: 김도영 2024 홈런 영상")
    if menu == "other" and not OTHER_ON:
        log_unanswered(message, "other_off", {"parsed": parsed})  # 자주 나오는 질문 → 메뉴 · 조건 칸 후보
        return say(NOT_YET, menu="other", reason="other_off", as_of=day, context=ctx)  # 채점이 menu를 본다
    # ③ 기준일 뒤만 묻는 질문 — 조회해도 0건이니 바로 안내한다 (「없어요」로 오해하지 않게. 이름 되묻기보다 먼저)
    if answers.after_as_of(cond, day):
        log_unanswered(message, "after_as_of", {"parsed": parsed})
        return say(f"BASE:ON에는 {answers.as_of_ko(day)} 경기까지 기록이 있어요.", menu=menu, reason="after_as_of", as_of=day, context=ctx)

    prev = ((req.context or {}).get("parsed") or {}).get("people") or {}  # 이어 묻기: 앞 질문의 사람 이름도 이름 바로잡기 후보로
    hint = message + " " + " ".join(str(n) for v in prev.values() for n in (v if isinstance(v, list) else [v]) if n)
    for k, v in list(people.items()):  # 바로잡은 이름을 조건표에 다시 적는다 (이어 묻기가 깨진 이름을 물려받지 않게)
        people[k] = [fix_name(n, hint) for n in v if n] if isinstance(v, list) else (fix_name(v, hint) if v else v)
    ids, stop = resolve_people(people, resolved, hint)
    if stop:
        return stop

    if "season" in resolved:
        cond["season"] = resolved["season"] or None   # 0 = 전체 시즌
    # ③ 연도 되묻기 — 연도도 날짜도 없으면 (stats는 시즌이 꼭 필요)
    no_when = not cond.get("season") and not cond.get("date_from") and not cond.get("date_to")
    if menu in ("pa", "games", "stats") and no_when and not parsed.get("year_given") and "season" not in resolved:
        opts = [{"value": s, "label": answers.season_label(s, day)} for s in SEASONS] \
            + ([] if menu == "stats" else [{"value": 0, "label": "전체 (2024~)"}])
        return {"type": "clarify", "slot": "season", "text": "어느 시즌을 말씀하시는 건가요?", "options": opts}
    if menu == "stats" and not cond.get("season"):
        cond["season"] = SEASONS[0]
    # 연도 없이 "7월 이후"였던 질문: 시즌을 고르면 그 해 날짜로 다시 해석하도록 질문에 연도를 붙여 다시 돈다 (호출 제한은 이미 셌다)
    if "season" in resolved and resolved["season"] and parsed.get("year_given") is False and re.search(r"\d+\s*월", message):
        if not message.startswith(f"{resolved['season']}년"):
            req2 = ChatRequest(message=f"{resolved['season']}년 {message}", context=req.context, resolved=resolved)
            return answer(req2, req2.message)

    try:
        result = run_menu(menu, ids, cond) if menu != "other" else run_other(message, ids)
    except ApiError as e:  # 조건을 못 알아들으면 그대로 알린다 (other로 넘겨 숫자를 지어내게 하지 않는다)
        log_unanswered(message, e.code, {"detail": e.message, "parsed": parsed})
        if e.code in ("UNUSED_PERSON", "BAD_MENU"):
            return say(NOT_YET, as_of=day)
        return say(friendly(e.message), as_of=day)
    except llm.LLMError as e:
        log_unanswered(message, "llm_error", {"error": str(e)[:200]})
        return say("지금 질문을 처리하는 데 문제가 생겼어요. 잠시 뒤 다시 시도해 주세요.", error=True)
    if result.get("type") == "answer" and "menu" not in result:
        return result  # run_other가 안내 문장으로 끝낸 경우

    if result.get("total") == 0:
        log_unanswered(message, "zero_rows", {"parsed": parsed})
    if menu == "stats":
        result["conditions"] = [x for x in (result.get("name"), answers.season_label(result.get("season"), day), "정규시즌") if x]
    elif day:  # 현재 시즌은 「2026 시즌(7월 26일까지)」로
        cur = f"{day[:4]} 시즌"
        result["conditions"] = [answers.season_label(int(day[:4]), day) if c == cur else c for c in result.get("conditions") or []]
    if menu == "pa" and not answers.asks_who(message):
        result.pop("by_batter", None)
    result["text"] = answers.text_for(menu, result, cond, day)
    result["type"] = "answer"
    result["as_of"] = day
    result["context"] = {"parsed": {"menu": menu, "people": people, "cond": cond, "year_given": True}}
    result["ms"] = int((time.time() - t0) * 1000)
    return result
