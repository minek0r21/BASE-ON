"""
LLM에 보내는 규칙(프롬프트). 용어 · 구장 · 팀 · 구종 목록은 terms.py와 schema_values.json에서 가져와
코드와 프롬프트가 항상 같은 값을 쓴다. 질문을 잘못 알아들으면 여기 예시(EXAMPLES)를 늘려서 고친다.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import terms
from .registry import MENUS

SCHEMA = Path(__file__).with_name("schema_values.json")


def schema() -> dict:
    try:
        return json.loads(SCHEMA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"values": {}, "properties": {}, "relations": []}


def last_date() -> str:
    v = schema()["values"].get("last_date") or {}
    return next(iter(v), "2026-07-26")


# ------------------------------------------------------------------ 1. 질문 → 조건표
# 메뉴 · 조건 칸 · 예시는 registry.MENUS에서 만든다. other · chat은 메뉴가 아니라 「못 답함」 · 「대화」 표시라 여기 둔다

# 출력 모양을 Gemini responseJsonSchema로 고정해 봤더니(11-10, 채점 27개) 15개만 맞았다 — 작은 모델이 안 물은 칸을
# 엉뚱한 값으로 채웠다(result=승 · balls=0). 고정 없이는 25~26개. 그래서 값 목록은 아래 규칙 글로만 주고, 모르는 값은 조회 쪽(terms.py)이 거른다

META_MENUS = [
    ("other", "위 메뉴로 안 되는 기록 질문 (여러 선수 비교 · 합계 · 이닝별 · 월별 · 상대 팀별 집계 등). people · cond는 아는 만큼 채운다"),
    ("talk", "기록 숫자가 아닌 야구 질문 (용어 · 규칙 · 관람 · 응원 · 입문). 예: OPS가 뭐야, 인필드 플라이가 뭐야, 직관 처음인데 뭘 알아야 해"),
    ("chat", "인사 · 서비스 사용법 · 야구와 관계없는 말 → reply에 짧게 답한다"),
]
META_EXAMPLES = [
    ("김도영이랑 최정 2025 홈런 누가 더 많아",
     {"menu": "other", "people": {"players": ["김도영", "최정"]}, "cond": {"season": 2025, "results": ["홈런"]}, "year_given": True}),
    ("희생플라이가 뭐야", {"menu": "talk", "people": {}, "cond": {}, "year_given": False}),
    ("안녕", {"menu": "chat", "people": {}, "cond": {}, "year_given": False, "reply": "안녕하세요! 선수 기록이나 장면을 물어보세요. 예: 김도영 2024 홈런 영상"}),
]


def parse_format() -> str:
    menus = " | ".join(f'"{m}"' for m in [*MENUS, *(k for k, _ in META_MENUS)])
    return """{
  "menu": %s,
  "people": {"batter": 이름|null, "pitcher": 이름|null, "player": 이름|null,
             "starter": 이름|null, "opp_starter": 이름|null, "players": [이름, ...]},
  "cond": {조건 칸: 값, ...},
  "year_given": true|false,
  "reply": 문자열|null
}""" % menus


def examples(today) -> str:
    fill = {"{this_year}": today.year, "{last_year}": today.year - 1}
    out = []
    for q, a in [*(e for m in MENUS.values() for e in m.examples), *META_EXAMPLES]:
        s = json.dumps(a, ensure_ascii=False)
        for k, v in fill.items():
            s = s.replace(f'"{k}"', json.dumps(v)).replace(k, str(v))
        out.append(f"질문: {q}\n답: {s}")
    return "\n\n".join(out)


def parse_system(as_of: str | None = None) -> str:
    today = datetime.now(timezone(timedelta(hours=9))).date()  # 한국 날짜 (서버는 UTC일 수 있다)
    menu_lines = "\n".join(f"- {m.id}: {m.prompt}" for m in MENUS.values()) + "\n" + "\n".join(f"- {k}: {v}" for k, v in META_MENUS)
    slot_lines = "\n".join(f"{m.id} 메뉴 칸: {m.slots}" for m in MENUS.values())
    return f"""너는 KBO 야구 기록 서비스 BASE:ON의 질문 해석기다. 사용자의 질문을 아래 JSON 하나로만 바꾼다. 답을 지어내지 않는다.

오늘: {today.isoformat()} · 데이터: 2024-03 ~ {as_of or last_date()} 정규시즌 (그 뒤 기록은 없다. 그 뒤 날짜를 물어도 날짜는 그대로 옮긴다 — 시스템이 안내한다)

[메뉴]
{menu_lines}

[출력 형식]
{parse_format()}

[people] 질문에 나온 사람 이름만, 질문에 쓴 그대로 (\"도영이\" → \"도영\", \"김도영 선수\" → \"김도영\"). 없는 칸은 null 또는 빈 목록.
- batter: 친 사람 / pitcher: 던진 사람 (\"OO 상대로\", \"OO에게\", \"OO가 맞은\"의 OO가 투수인지 타자인지 문맥으로)
- player: stats · rank 메뉴의 선수 / starter: games의 그 팀 선발 / opp_starter: 상대 팀 선발 / players: games에서 그 팀으로 같이 뛴 선수들

[cond] {slot_lines}
- metrics에 쓸 수 있는 말: {', '.join(terms.METRICS)}  (\"방어율\" = 평균자책점, \"K\" = 삼진, \"홈런 맞은 거\" = 피홈런)
- results에 쓸 수 있는 말: {', '.join(terms.EVENT_GROUPS)}  (\"안타\"는 홈런 포함, \"장타\" = 2·3루타+홈런)
- 팀: {', '.join(sorted(set(terms.TEAMS.values())))} 중 하나로 (기아→KIA, 엘지→LG, 쓱→SSG)
- pa에서 \"플로리얼 한화\" \"엘지 문보경\"처럼 선수 이름 옆에 붙은 팀은 그 선수 소속이다 → bat_team · pit_team에 넣지 않는다. 상대 팀은 \"한화 상대로\" \"한화 투수한테\"처럼 말할 때만
- \"8회 이후\" · \"득점권\" · \"만루\" · \"잠실에서\" · \"OO 상대로\"처럼 장면 조건이 붙은 개수는 stats가 아니라 pa (시즌 기록에는 그 조건이 없다)
- stadium: {', '.join(terms.STADIUMS)}
- situations(점수 상황): {', '.join(terms.SITUATIONS)} / bases(주자): {', '.join(terms.BASES)}, {terms.RISP} — 득점권 · 만루는 situations가 아니라 bases
- pitch_names: {', '.join(terms.PITCHES)}
- \"N회\" 하나면 inning_from = inning_to = N, \"N회 이후\"면 inning_from만
- video_only는 \"영상 있는 것만\"처럼 영상 있는 것으로 거르라고 할 때만 true. \"영상 볼 수 있어?\"는 false (영상은 어차피 같이 보여 준다)
- 질문에 없는 조건 · 값이 없는 칸은 넣지 않는다 (null로 쓰지 않는다)

[연도] \"올해\" = {today.year}, \"작년\" = {today.year - 1}, \"재작년\" = {today.year - 2}
- 연도나 시즌을 말하면 year_given = true 와 season(또는 date_from/date_to)을 채운다
- 연도 없이 \"7월 이후\"처럼 날짜만 말하면 year_given = false, date_from/date_to는 넣지 않는다 (시스템이 연도를 되묻는다)
- \"어제\" · \"지난주\"처럼 날짜가 정해지는 말은 오늘 기준 날짜로 바꾸고 year_given = true
- \"전체 시즌\" · \"통산\" · \"지금까지\"처럼 모든 시즌을 말하면 year_given = true, season은 넣지 않는다

[이어지는 질문] 사용자 메시지에 previous(앞 질문의 메뉴 · 사람 · 조건)가 있으면, 이번 질문이 그 뒤를 잇는 말인지 본다.
\"그럼 2025년은?\" \"홈런 말고 2루타는?\"처럼 이어지면 previous에서 시작해 바뀐 것만 고친다. 새 질문이면 previous는 무시한다.

[예시]
""" + examples(today)


# 답 문장은 AI가 쓰지 않는다 — answers.py가 조회 결과 숫자로 채운다 (틀린 숫자가 나올 수 없게)


# ------------------------------------------------------------------ 2. 메뉴에 없는 질문 → Cypher (로컬 전용, CHAT_OTHER=on)
def cypher_system(ids: dict[str, str]) -> str:
    sc = schema()
    vals = sc["values"]
    return f"""너는 Neo4j Cypher 작성기다. KBO 야구 기록 그래프 DB에서 사용자 질문에 답할 읽기 전용 Cypher 하나를 쓴다.

[관계] {' · '.join(sc['relations'])}
[속성] {json.dumps(sc['properties'], ensure_ascii=False)}
[값]
- PlateAppearance.events: {', '.join(vals.get('events', {}))}  (안타 = single·double·triple·home_run)
- PlateAppearance.situation: {', '.join(vals.get('situation', {}))} / inning_half: 초 | 말
- PlateAppearance.last_pitch_name: {', '.join(vals.get('last_pitch_name', {}))}
- Team.name: {', '.join(sorted(set(terms.TEAMS.values())))} / Team.team_id: {', '.join(vals.get('teams', {}))}
- 날짜 속성(date)은 Date 타입: pa.date >= date('2025-07-01'). season은 정수.
- 공격 팀 = 초면 원정(AWAY) 팀, 말이면 홈(HOME) 팀. 경기 점수: Game.home_final · away_final.
- 타자 시즌 기록: (Player)-[:HAS_STAT]->(BatterSeasonStat), 투수: (Player)-[:HAS_PITCHING_STAT]->(PitcherSeasonStat).
  qualified = 사이트 비교 대상 (타자: 타석 ≥ 팀 경기 수 × 3.1 × 0.5, 투수: 이닝 ≥ 팀 경기 수 × 선발 0.5 · 구원 0.2). 투수 role = starter | reliever.
  타율 · OPS 같은 비율 순위는 qualified인 선수만, 홈런 · 삼진 같은 개수 순위는 전체. 투수 비율(WHIP · 피안타율) 순위는 선발(role = starter) 비교 대상만.
  이닝은 outs(아웃 수) ÷ 3. 주자 칸(on_1b · on_2b · on_3b)은 true/false라 = true로 비교한다 (IS NOT NULL 금지).
  소속 팀 (Player)-[:PLAYS_FOR {{season}}]->(Team)은 시즌마다 있다 — 꼭 f.season = 그 시즌으로 거른다 (안 거르면 같은 선수가 여러 줄).
- 오늘: {datetime.now(timezone(timedelta(hours=9))).date().isoformat()} · \"올해\" = {datetime.now(timezone(timedelta(hours=9))).year}, \"작년\" = 그 전 해
- 데이터: 2024-03 ~ {last_date()} 정규시즌
[선수 ID] 질문 속 선수는 이 ID로만 찾는다 (이름으로 찾지 않는다): {json.dumps(ids, ensure_ascii=False)}

[규칙]
- MATCH / OPTIONAL MATCH / WITH / WHERE / RETURN / ORDER BY / LIMIT 만 쓴다. CREATE · MERGE · SET · DELETE · REMOVE · CALL · LOAD 금지.
- RETURN 열 이름은 한국어로 짧게 (예: 선수, 홈런, 타율). 숫자로 시작하는 이름은 백틱으로 감싼다 (AS `3루타`). 날짜는 toString(...)으로.
- 이닝은 소수 나눗셈으로 (s.outs / 3.0). 정수끼리 나누면 115⅔이 115가 된다.
- 마지막에 LIMIT 20 이하.
- 답할 수 없는 질문이면 cypher를 null로.

[출력] {{"cypher": 문자열|null, "explain": "어떻게 찾았는지 사람이 읽는 한 줄 (예: 2025 시즌 · 정규시즌 · 홈런 많은 순 5명)"}}"""
