"""
POST /chat 의 본체 — 질문 하나를 받아 답 하나를 돌려준다. AI 호출은 질문당 1번(①)뿐이다.

  ⓪ 호출 제한: IP별 1분 · 하루, 서버 하루 상한        (limits.py)
  ① LLM: 질문 → 메뉴 + 사람 이름 + 조건표          (prompts.parse_system)
  ② DB : 이름 → 선수 ID (여러 명이면 되묻기)          (routers.players.Q_SEARCH)
  ③ 기준일(7.26) 뒤만 묻는 질문은 조회 없이 안내, 연도가 없으면 되묻기
  ④ DB : 메뉴별 미리 써 둔 Cypher로 조회              (routers.chat.search_pa / search_games / season_stats)
     메뉴에 없는 질문(other)은 서버에서 「아직 못 답함」. 로컬에서 CHAT_OTHER=on일 때만 LLM이 쓴 Cypher를 읽기 전용으로 실행
  ⑤ 답 문장: 조회 결과 숫자로 코드가 채운다           (answers.py — AI가 숫자를 옮겨 적지 않는다)
  기록이 아닌 야구 질문(talk)만 AI가 일반 설명으로 답한다 (talk.py, 「BASE:ON 기록 아님」 꼬리표). 못 답한 질문은 가까운 메뉴 버튼 · 화면 링크
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
from . import answers, checks, limits, llm, prompts, talk, terms
from .registry import MENUS

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


NICK = re.compile(r"(?<=..)(형|이|선수|님)$")  # 「도영이」 · 「창기형」 → 이름 부분
_ALL: list = []


def all_names() -> list[str]:
    if not _ALL:
        _ALL.extend(r["name"] for r in db.run("MATCH (p:Player) RETURN DISTINCT p.name AS name"))
    return _ALL


def narrow(cands: list[dict], teams: list[str], season: int | None) -> list[dict]:
    """여러 명이면 질문에 나온 팀 · 시즌에 뛴 선수로 좁힌다 (「재훈 한화 24」). 좁혀서 0명이면 그대로"""
    if len(cands) <= 1 or not (teams or season):
        return cands
    ids = [c["player_id"] for c in cands]
    for t, s in ((teams, season), (teams, None), ([], season)):
        if not t and s is None:
            continue
        keep = {r["id"] for r in db.run(
            """MATCH (p:Player)-[f:PLAYS_FOR]->(t:Team) WHERE p.player_id IN $ids AND (size($teams) = 0 OR t.name IN $teams)
               AND ($season IS NULL OR f.season = $season) RETURN DISTINCT p.player_id AS id""", ids=ids, teams=t, season=s)}
        got = [c for c in cands if c["player_id"] in keep]
        if got:
            return got
    return cands


def regular(cands: list[dict], season: int | None) -> list[dict]:
    """이름만 부른 경우(「지훈이」) 좁혀도 여럿이면, 그 시즌(없으면 전체) 출장이 다른 후보의 3배 이상인 주전 한 명 —
    팬이 이름만 부르는 건 대개 주전이다. 답에는 성까지 붙은 이름이 나가서 사용자가 바로 알아본다"""
    if len(cands) <= 1:
        return cands
    rows = db.run("""UNWIND $ids AS id MATCH (p:Player {player_id: id})
        RETURN id, COUNT { (p)-[:BATTED_IN]->(x) WHERE $season IS NULL OR x.season = $season }
                 + COUNT { (p)-[:PITCHED_IN]->(y) WHERE $season IS NULL OR y.season = $season } AS n""",
                  ids=[c["player_id"] for c in cands], season=season)
    n = sorted(((r["n"], r["id"]) for r in rows), reverse=True)
    if len(n) >= 2 and n[0][0] >= 3 * max(n[1][0], 1):
        return [c for c in cands if c["player_id"] == n[0][1]]
    return cands


def lookup(name: str, role: str | None, message: str, teams: list[str], season: int | None) -> list[dict]:
    """이름 → 후보. AI가 옮긴 이름 → 질문 속 낱말 → 별칭 꼬리(이 · 형) 뗀 이름 → 비슷한 이름(오타) 순서로"""
    bare = message.replace(" ", "")
    tries = [name] if name.replace(" ", "") in bare else [fix_name(name, message), name]
    if name.replace(" ", "") not in bare:  # AI가 지어낸 이름(창기형 → 임창민)이면 질문 낱말에서 찾는다
        vocab = {*terms.TEAMS, *terms.METRICS, *terms.EVENT_GROUPS, *terms.STADIUMS}
        tries += [w for w in (PARTICLES.sub("", w) for w in re.findall(r"[가-힣]{2,5}", message)) if w not in vocab]
    tries += [NICK.sub("", t) for t in tries if NICK.search(t)]
    for t in dict.fromkeys(x for x in tries if len(x) >= 2):
        cands = find_player(t, role)
        if cands:
            cands = narrow(cands, teams, season)
            partial = all(c["name"].replace(" ", "") != t for c in cands)
            return regular(cands, season) if partial else cands
    # 오타 (나승업 → 나승엽, 김진우 → 김진욱): 자모로 풀어 가장 비슷한 이름 → 팀 · 시즌으로 좁힌다. 그래도 여럿이면 되묻기.
    # 글자 단위로 재면 「김진」만 같은 김태진도 같은 점수라 엉뚱한 선수로 답했다 (11-16 dev4)
    key = jamo(NICK.sub("", tries[0]))
    scored = sorted(((difflib.SequenceMatcher(None, key, jamo(n)).ratio(), n) for n in all_names()), reverse=True)[:5]
    best = [n for s, n in scored if s >= 0.8 and s >= scored[0][0] - 0.02]
    cands = [c for n in best for c in find_player(n, role) if c["name"] == n]
    return narrow(cands, teams, season) if len(best) == 1 else cands  # 비슷한 이름이 여럿이면 좁히지 않고 되묻는다


def jamo(s: str) -> str:
    """한글 음절 → 초성 · 중성 · 종성 (오타 비교용)"""
    out = []
    for ch in s:
        o = ord(ch) - 0xAC00
        if 0 <= o < 11172:
            out += [chr(0x1100 + o // 588), chr(0x1161 + o % 588 // 28)] + ([chr(0x11A7 + o % 28)] if o % 28 else [])
        else:
            out.append(ch)
    return "".join(out)


def resolve_people(people: dict, resolved: dict, message: str, teams: list[str] | None = None,
                   season: int | None = None) -> tuple[dict | None, dict | None]:
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
            near = checks.team_near(message, NICK.sub("", name)) if len(teams or []) > 1 else None
            cands = lookup(name, role, message, [near] if near else teams or [], season)
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


# ------------------------------------------------------------------ ④ 메뉴별 조회 — 실행 방법은 등록부(registry.MENUS)에
def run_menu(menu: str, ids: dict, cond: dict) -> dict:
    m = MENUS.get(menu)
    if not m:
        raise ApiError(400, "BAD_MENU", menu)
    return {"menu": menu, **m.run(ids, cond)}


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


# ------------------------------------------------------------------ 못 답한 질문의 기본 답 — 숫자는 지어내지 않고, 이미 답할 수 있는 가까운 질문 · 사이트 화면으로 잇는다
CHAT_GUIDE = "선수 · 팀 기록이나 장면을 물어봐 주세요. 예: 김도영 2026 홈런 영상 · 올해 홈런 1위 · KIA 2026년 7월 성적"
NOT_YET = "이 질문은 아직 답할 수 없어요."
NOT_YET_NONE = "이 질문은 아직 답할 수 없어요. 한 선수의 타석 · 시즌 기록, 한 팀의 경기 결과, 시즌 순위로 물어봐 주세요."


def alternatives(people: dict, cond: dict) -> tuple[list[dict], list[dict]]:
    """(질문 버튼, 화면 링크). 이름이 한 명으로 딱 찾아지는 선수 · 팀만 쓴다 (되묻지 않는다)"""
    season = cond.get("season") if isinstance(cond.get("season"), int) else SEASONS[0]
    asks, links = [], []
    names = [n for v in people.values() for n in (v if isinstance(v, list) else [v]) if isinstance(n, str) and n]
    for name in list(dict.fromkeys(names))[:2]:
        cands = find_player(name, None)
        if len(cands) != 1:
            continue
        nm, pid = cands[0]["name"], cands[0]["player_id"]
        res = (cond.get("results") or [None])[0]
        asks.append({"label": f"{nm} {season} {res} 목록" if res else f"{nm} {season} 시즌 기록",
                     "ask": f"{nm} {season} {res} 목록" if res else f"{nm} {season} 시즌 기록"})
        links.append({"label": f"{nm} 선수 화면", "href": f"/players/?id={pid}"})
    team = cond.get("team") or cond.get("bat_team")
    if team and len(asks) < 2:
        asks.append({"label": f"{team} {season} 경기 결과", "ask": f"{team} {season} 시즌 경기"})
        links.append({"label": f"{team} 팀 화면", "href": f"/teams/?team={team}"})
    return asks[:2], links[:2]


# ------------------------------------------------------------------ 전체


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
    prev = (req.context or {}).get("parsed")
    try:
        parsed = llm.complete_json(prompts.parse_system(day), json.dumps({"question": message, "previous": prev}, ensure_ascii=False))
        if checks.needs_pa(parsed, message):  # 장면 조건이 있는데 시즌 기록으로 → 한 번 더 (드물다, 조건 칸을 AI가 채워야 해서)
            parsed = llm.complete_json(prompts.parse_system(day), json.dumps(
                {"question": message, "previous": prev, "hint": "회 · 주자 · 구장 · 상대 같은 장면 조건이 있다 → menu는 pa"}, ensure_ascii=False))
    except llm.LLMError as e:
        log_unanswered(message, "llm_error", {"error": str(e)[:200]})
        return say("지금 질문을 이해하는 데 문제가 생겼어요. 잠시 뒤 다시 시도해 주세요.", error=True)
    fixed = checks.fix_season(parsed, message, day, follow_up=bool(prev))  # 연도는 질문 글자를 믿는다
    fixed += checks.other_to_stats(parsed, message) + checks.result_only(parsed, message) + checks.fix_cond(parsed, message)
    if parsed.get("menu") == "other" and not any((parsed.get("people") or {}).values()) and not parsed.get("cond"):
        parsed["menu"] = "talk"  # 선수 · 팀 · 시즌 없는 메뉴 밖 질문 = 규칙 · 용어 · 관람 질문 → 일반 설명 (꼬리표 붙음)
        fixed.append("other→talk")

    menu = parsed.get("menu")
    people = parsed.get("people") or {}
    cond = {k: v for k, v in (parsed.get("cond") or {}).items() if v not in (None, "", [])}
    ctx = {"parsed": {"menu": menu, "people": people, "cond": cond, "year_given": True}}  # 이어 묻기 · 채점용
    if menu == "talk":  # 기록 숫자가 아닌 야구 질문 → AI 일반 설명 (talk.py, 꼬리표 · 숫자 거르기)
        try:
            text, safe = talk.answer(message)
        except llm.LLMError as e:
            log_unanswered(message, "llm_error", {"error": str(e)[:200]})
            return say("지금 질문을 처리하는 데 문제가 생겼어요. 잠시 뒤 다시 시도해 주세요.", error=True)
        if not safe:
            log_unanswered(message, "talk_record_like", {"parsed": parsed})
        return say(text, menu="talk", tag="일반 설명 · BASE:ON 기록 아님", context=ctx)
    if menu == "chat" or (menu not in MENUS and menu != "other"):
        # AI가 쓴 인사말(reply)은 검사 없이 나가서 「…있습니다」 · 「…물어봐 주세요!」처럼 말투가 섞였다 (11-16 디버깅) → 정해진 안내 + 기록
        log_unanswered(message, "chat", {"parsed": {k: v for k, v in parsed.items() if k != "reply"}, "reply": (parsed.get("reply") or "")[:200]})
        asks, links = alternatives(people, cond)
        return say(CHAT_GUIDE, menu="chat", reason="chat", as_of=day, context=ctx, suggestions=asks, links=links)
    if menu == "other" and not OTHER_ON:
        log_unanswered(message, "other_off", {"parsed": parsed})  # 자주 나오는 질문 → 메뉴 · 조건 칸 후보
        asks, links = alternatives(people, cond)
        return say(NOT_YET if asks or links else NOT_YET_NONE, menu="other", reason="other_off", as_of=day, context=ctx,
                   suggestions=asks, links=links)  # 채점이 menu를 본다
    # ③ 기준일 뒤만 묻는 질문 — 조회해도 0건이니 바로 안내한다 (「없어요」로 오해하지 않게. 이름 되묻기보다 먼저)
    if answers.after_as_of(cond, day):
        log_unanswered(message, "after_as_of", {"parsed": parsed})
        return say(f"BASE:ON에는 {answers.as_of_ko(day)} 경기까지 기록이 있어요.", menu=menu, reason="after_as_of", as_of=day, context=ctx)

    teams = checks.teams_in(message)
    season_hint = cond.get("season") or resolved.get("season") or None
    if answers.before_data(cond, SEASONS[-1]):  # 2024 전 시즌 — 「없어요」로 답하면 그해 기록이 없었던 것처럼 읽힌다
        log_unanswered(message, "before_data", {"parsed": parsed})
        return say(f"BASE:ON에는 {SEASONS[-1]} 시즌부터 기록이 있어요.", menu=menu, reason="before_data", as_of=day, context=ctx)
    ids, stop = resolve_people(people, resolved, message, teams, int(season_hint) if season_hint else None)
    if stop:
        return {**stop, "context": ctx}  # 되묻기 · 못 찾음도 이 질문이 「앞 질문」 — 「작년에는?」이 그 전 답에 붙지 않게
    if menu == "games" and not cond.get("team"):  # 팀을 안 말했으면 선발 · 같이 뛴 선수의 그 시즌 팀 (답 조건 · 이어 묻기에 남게 여기서)
        who = ids.get("starter") or (ids.get("players") or [None])[0]
        if who:
            from .registry import latest_team
            if t := latest_team(who, int(season_hint) if season_hint else None):
                cond["team"] = t
    if menu == "pa":  # 선수 옆에 쓴 팀(그 선수 소속)을 상대 팀 칸에 넣은 경우 — 자기 팀과는 맞붙지 않으니 지운다
        for slot, key in (("batter", "pit_team"), ("pitcher", "bat_team")):
            if ids.get(slot) and cond.get(key):
                from .registry import latest_team
                try:
                    if terms.team_of(cond[key]) == latest_team(ids[slot], int(season_hint) if season_hint else None):
                        fixed.append(f"{key} {cond.pop(key)}→없음 (선수 소속)")
                except ValueError:
                    pass

    if "season" in resolved:
        cond["season"] = resolved["season"] or None   # 0 = 전체 시즌
    # ③ 연도 되묻기 — 연도도 날짜도 없으면 (stats는 시즌이 꼭 필요)
    no_when = not cond.get("season") and not cond.get("date_from") and not cond.get("date_to")
    need = MENUS[menu].season if menu in MENUS else None  # 메뉴마다 등록부에 적어 둔다
    if need and no_when and not parsed.get("year_given") and "season" not in resolved:
        opts = [{"value": s, "label": answers.season_label(s, day)} for s in SEASONS] \
            + ([{"value": 0, "label": "전체 (2024~)"}] if need == "ask" else [])
        return {"type": "clarify", "slot": "season", "text": "어느 시즌을 말씀하시는 건가요?", "options": opts,
                "context": ctx}  # 고르지 않고 「작년에는?」으로 이어 물어도 이 질문에 붙게 (11-16 디버깅: 그 전 답에 붙었다)
    if need == "ask_one" and not cond.get("season"):
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
        text = f"「{e.message.split(': ', 1)[-1]}」 조건은 아직 알아듣지 못해요. 다르게 물어봐 주세요." if e.code == "BAD_CONDITION" and e.message.startswith("모르는") else e.message
        return say(text, menu=menu, reason=e.code, as_of=day, context=ctx)  # 메뉴는 남긴다 (채점이 어느 단계에서 틀렸는지 본다)
    except llm.LLMError as e:
        log_unanswered(message, "llm_error", {"error": str(e)[:200]})
        return say("지금 질문을 처리하는 데 문제가 생겼어요. 잠시 뒤 다시 시도해 주세요.", error=True)
    if result.get("type") == "answer" and "menu" not in result:
        return result  # run_other가 안내 문장으로 끝낸 경우

    if result.get("total") == 0:
        log_unanswered(message, "zero_rows", {"parsed": parsed})
    if menu == "stats":
        result["conditions"] = [answers.season_label(result.get("season"), day), "정규시즌"]
    elif day:  # 현재 시즌은 「2026 시즌(7월 26일까지)」로
        cur = f"{day[:4]} 시즌"
        result["conditions"] = [answers.season_label(int(day[:4]), day) if c == cur else c for c in result.get("conditions") or []]
    result["text"] = MENUS[menu].text(result, cond, day) if menu in MENUS else answers.other_text(result)
    result["type"] = "answer"
    result["as_of"] = day
    result["context"] = {"parsed": {"menu": menu, "people": people, "cond": cond, "year_given": True}}
    if fixed:
        result["context"]["fixed"] = fixed  # 코드가 고친 것 (채점 · 로그에서 본다)
    result["ms"] = int((time.time() - t0) * 1000)
    return result
