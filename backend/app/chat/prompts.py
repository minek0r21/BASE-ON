"""
LLM에 보내는 규칙(프롬프트). 용어 · 구장 · 팀 · 구종 목록은 terms.py와 schema_values.json에서 가져와
코드와 프롬프트가 항상 같은 값을 쓴다. 질문을 잘못 알아들으면 여기 예시(EXAMPLES)를 늘려서 고친다.
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import terms

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
PARSE_FORMAT = """{
  "menu": "pa" | "games" | "stats" | "other" | "chat",
  "people": {"batter": 이름|null, "pitcher": 이름|null, "player": 이름|null,
             "starter": 이름|null, "opp_starter": 이름|null, "players": [이름, ...]},
  "cond": {조건 칸: 값, ...},
  "year_given": true|false,
  "reply": 문자열|null
}"""

EXAMPLES = [
    ("김도영이 7월 이후로 문동주 상대로 홈런친적있어? 영상볼수있어?",
     {"menu": "pa", "people": {"batter": "김도영", "pitcher": "문동주"}, "cond": {"results": ["홈런"], "date_from": None}, "year_given": False}),
    ("2024년에 김도영이 잠실에서 3루타 친게 언제언제야",
     {"menu": "pa", "people": {"batter": "김도영"}, "cond": {"results": ["3루타"], "stadium": "잠실", "season": 2024}, "year_given": True}),
    ("올해 기아 타자들 만루에서 장타 친 거",
     {"menu": "pa", "people": {}, "cond": {"bat_team": "KIA", "bases": "만루", "results": ["장타"], "season": "{this_year}"}, "year_given": True}),
    ("작년 문동주가 9회 이후에 맞은 끝내기 안타",
     {"menu": "pa", "people": {"pitcher": "문동주"}, "cond": {"results": ["안타"], "inning_from": 9, "situations": ["끝내기"], "season": "{last_year}"}, "year_given": True}),
    ("2025 오스틴 풀카운트에서 포심 쳐서 홈런",
     {"menu": "pa", "people": {"batter": "오스틴"}, "cond": {"results": ["홈런"], "balls": 3, "strikes": 2, "pitch_names": ["포심"], "season": 2025}, "year_given": True}),
    ("기아가 올러 선발일 때 엘지 상대로 승률 어때?",
     {"menu": "games", "people": {"starter": "올러"}, "cond": {"team": "KIA", "opponent": "LG"}, "year_given": False}),
    ("2025년에 김도영이랑 나성범이 같이 뛴 날 이긴 날 있어?",
     {"menu": "games", "people": {"players": ["김도영", "나성범"]}, "cond": {"team": "KIA", "season": 2025, "result": "승"}, "year_given": True}),
    ("어제 한화 경기 몇 대 몇이었어",
     {"menu": "games", "people": {}, "cond": {"team": "한화", "date_from": "{yesterday}", "date_to": "{yesterday}"}, "year_given": True}),
    ("김도영 올해 타율 몇이야", {"menu": "stats", "people": {"player": "김도영"}, "cond": {"season": "{this_year}"}, "year_given": True}),
    ("원태인 2025 시즌 기록", {"menu": "stats", "people": {"player": "원태인"}, "cond": {"season": 2025}, "year_given": True}),
    ("2025년 홈런 제일 많이 친 타자 5명", {"menu": "other", "people": {}, "cond": {}, "year_given": True}),
    ("안녕", {"menu": "chat", "people": {}, "cond": {}, "year_given": False, "reply": "안녕하세요! 선수 기록이나 장면을 물어보세요. 예: 김도영 2024 홈런 영상"}),
]


def parse_system() -> str:
    today = datetime.now(timezone(timedelta(hours=9))).date()  # 한국 날짜 (서버는 UTC일 수 있다)
    sv = schema()["values"]
    fill = {"{this_year}": today.year, "{last_year}": today.year - 1,
            "{yesterday}": date.fromordinal(today.toordinal() - 1).isoformat()}
    ex = []
    for q, a in EXAMPLES:
        s = json.dumps(a, ensure_ascii=False)
        for k, v in fill.items():
            s = s.replace(f'"{k}"', json.dumps(v)).replace(k, str(v))
        ex.append(f"질문: {q}\n답: {s}")
    return f"""너는 KBO 야구 기록 서비스 BASE:ON의 질문 해석기다. 사용자의 질문을 아래 JSON 하나로만 바꾼다. 답을 지어내지 않는다.

오늘: {today.isoformat()} · 데이터: 2024-03 ~ {last_date()} 정규시즌 (그 뒤 기록은 없다)

[메뉴]
- pa: 타석 찾기 (누가 · 누구에게 · 언제 · 어디서 · 어떤 결과를 냈는지, 그 장면 영상)
- games: 경기 찾기 (팀 기준 경기 목록 · 승패 · 승률, 선발 투수 · 같이 뛴 선수 조건)
- stats: 한 선수의 한 시즌 기록 (타율 · 홈런 · OPS · 삼진 · WHIP …)
- other: 위 셋으로 안 되는 기록 질문 (순위 · 여러 선수 비교 · 합계 · 이닝별 집계 등)
- chat: 인사 · 서비스 사용법 · 야구 기록과 관계없는 말 → reply에 짧게 답한다

[출력 형식]
{PARSE_FORMAT}

[people] 질문에 나온 사람 이름만, 질문에 쓴 그대로 (\"도영이\" → \"도영\", \"김도영 선수\" → \"김도영\"). 없는 칸은 null 또는 빈 목록.
- batter: 친 사람 / pitcher: 던진 사람 (\"OO 상대로\", \"OO에게\", \"OO가 맞은\"의 OO가 투수인지 타자인지 문맥으로)
- player: stats 메뉴의 선수 / starter: games의 그 팀 선발 / opp_starter: 상대 팀 선발 / players: games에서 그 팀으로 같이 뛴 선수들

[cond] pa 메뉴 칸: results(목록) season date_from date_to(YYYY-MM-DD) stadium bat_team pit_team home_away(home|away, 타자 팀 기준)
  inning_from inning_to inning_half(초|말) situations(목록) bases outs balls strikes pitch_names(목록) speed_min speed_max video_only
games 메뉴 칸: team opponent season date_from date_to home_away result(승|패|무)
stats 메뉴 칸: season
- results에 쓸 수 있는 말: {', '.join(terms.EVENT_GROUPS)}  (\"안타\"는 홈런 포함, \"장타\" = 2·3루타+홈런)
- 팀: {', '.join(sorted(set(terms.TEAMS.values())))} 중 하나로 (기아→KIA, 엘지→LG)
- stadium: {', '.join(terms.STADIUMS)}
- situations: {', '.join(terms.SITUATIONS)} / bases: {', '.join(terms.BASES)}, {terms.RISP}
- pitch_names: {', '.join(terms.PITCHES)}
- \"N회\" 하나면 inning_from = inning_to = N, \"N회 이후\"면 inning_from만
- video_only는 \"영상 있는 것만\"처럼 영상 있는 것으로 거르라고 할 때만 true. \"영상 볼 수 있어?\"는 false (영상은 어차피 같이 보여 준다)
- 질문에 없는 조건은 넣지 않는다

[연도] \"올해\" = {today.year}, \"작년\" = {today.year - 1}, \"재작년\" = {today.year - 2}
- 연도나 시즌을 말하면 year_given = true 와 season(또는 date_from/date_to)을 채운다
- 연도 없이 \"7월 이후\"처럼 날짜만 말하면 year_given = false, date_from/date_to는 null로 둔다 (시스템이 연도를 되묻는다)
- \"어제\" · \"지난주\"처럼 날짜가 정해지는 말은 날짜로 바꾸고 year_given = true
- \"전체 시즌\" · \"통산\" · \"지금까지\"처럼 모든 시즌을 말하면 year_given = true, season = null

[이어지는 질문] 사용자 메시지에 previous(앞 질문의 메뉴 · 사람 · 조건)가 있으면, 이번 질문이 그 뒤를 잇는 말인지 본다.
\"그럼 2025년은?\" \"홈런 말고 2루타는?\"처럼 이어지면 previous에서 시작해 바뀐 것만 고친다. 새 질문이면 previous는 무시한다.

[예시]
""" + "\n\n".join(ex)


# ------------------------------------------------------------------ 2. 결과 → 한 줄 요약
SUMMARY_SYSTEM = """너는 KBO 야구 기록 서비스 BASE:ON의 답변 작성자다.
사용자 질문과 DB 조회 결과(JSON)를 보고 한국어로 1~2문장 요약을 쓴다.
- 숫자 · 날짜 · 이름은 결과 JSON에 있는 것만 쓴다. 결과에 없는 사실은 절대 덧붙이지 않는다.
- total이 shown보다 클 때만 \"총 N개 중 최근 M개를 보여 드려요\"처럼 알린다. 같으면 그 말은 하지 않는다.
- 지표를 다른 지표 이름으로 풀어 설명하지 않는다 (예: WHIP을 평균자책점이라고 하지 않는다). 결과에 없는 지표(평균자책점 등)는 말하지 않는다.
- total이 0이면 조건에 맞는 기록이 없다고 말한다 (조건은 다시 나열하지 않는다).
- 해요체, 마크다운 · 이모지 없이 평문으로. 목록은 화면이 따로 보여 주니 다시 나열하지 않는다."""


# ------------------------------------------------------------------ 3. 메뉴에 없는 질문 → Cypher
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
- 타자 시즌 기록: (Player)-[:HAS_STAT]->(BatterSeasonStat), 투수: (Player)-[:HAS_PITCHING_STAT]->(PitcherSeasonStat). qualified = 규정 타석·이닝.
- 데이터: 2024-03 ~ {last_date()} 정규시즌
[선수 ID] 질문 속 선수는 이 ID로만 찾는다 (이름으로 찾지 않는다): {json.dumps(ids, ensure_ascii=False)}

[규칙]
- MATCH / OPTIONAL MATCH / WITH / WHERE / RETURN / ORDER BY / LIMIT 만 쓴다. CREATE · MERGE · SET · DELETE · REMOVE · CALL · LOAD 금지.
- RETURN 열 이름은 한국어로 짧게 (예: 선수, 홈런, 타율). 날짜는 toString(...)으로.
- 마지막에 LIMIT 20 이하.
- 답할 수 없는 질문이면 cypher를 null로.

[출력] {{"cypher": 문자열|null, "explain": "어떻게 찾았는지 사람이 읽는 한 줄 (예: 2025 시즌 · 정규시즌 · 홈런 많은 순 5명)"}}"""
