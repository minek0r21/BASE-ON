"""
LLM에 보내는 규칙(프롬프트). 용어 · 구장 · 팀 · 구종 목록은 terms.py와 schema_values.json에서 가져와
코드와 프롬프트가 항상 같은 값을 쓴다. 질문을 잘못 알아들으면 여기 예시(EXAMPLES)를 늘려서 고친다.
"""
import json
from datetime import datetime, timedelta, timezone
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

# 출력 모양을 Gemini responseJsonSchema로 고정해 봤더니(11-10, 채점 27개) 15개만 맞았다 — 작은 모델이 안 물은 칸을
# 엉뚱한 값으로 채웠다(result=승 · balls=0). 고정 없이는 25~26개. 그래서 값 목록은 아래 규칙 글로만 주고, 모르는 값은 조회 쪽(terms.py)이 거른다

EXAMPLES = [
    ("김도영이 7월 이후로 문동주 상대로 홈런친적있어? 영상볼수있어?",
     {"menu": "pa", "people": {"batter": "김도영", "pitcher": "문동주"}, "cond": {"results": ["홈런"]}, "year_given": False}),
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
    ("LG 작년 성적 어때", {"menu": "games", "people": {}, "cond": {"team": "LG", "season": "{last_year}"}, "year_given": True}),
    ("2025년 7월 4일 한화 경기 몇 대 몇이었어",
     {"menu": "games", "people": {}, "cond": {"team": "한화", "date_from": "2025-07-04", "date_to": "2025-07-04"}, "year_given": True}),
    ("김도영 올해 타율 몇이야",
     {"menu": "stats", "people": {"player": "김도영"}, "cond": {"season": "{this_year}", "metrics": ["타율"]}, "year_given": True}),
    ("원태인 2025 시즌 기록", {"menu": "stats", "people": {"player": "원태인"}, "cond": {"season": 2025}, "year_given": True}),
    ("원태인 작년 평균자책점이랑 삼진",
     {"menu": "stats", "people": {"player": "원태인"}, "cond": {"season": "{last_year}", "metrics": ["평균자책점", "삼진"]}, "year_given": True}),
    ("작년에 KIA 투수 상대로 3루타 친 타자 누구누구야",
     {"menu": "pa", "people": {}, "cond": {"pit_team": "KIA", "results": ["3루타"], "season": "{last_year}"}, "year_given": True}),
    ("김도영 문동주 상대 전적",
     {"menu": "pa", "people": {"batter": "김도영", "pitcher": "문동주"}, "cond": {}, "year_given": True}),
    ("작년에 양현종이 선발로 나온 경기에서 KIA가 친 홈런",
     {"menu": "pa", "people": {"starter": "양현종"}, "cond": {"bat_team": "KIA", "results": ["홈런"], "season": "{last_year}"}, "year_given": True}),
    ("올해 김도영이랑 나성범이 같이 뛴 날 나성범이 친 홈런",
     {"menu": "pa", "people": {"batter": "나성범", "players": ["김도영", "나성범"]}, "cond": {"results": ["홈런"], "season": "{this_year}"}, "year_given": True}),
    ("2024년 김도영이 홈런 친 날 KIA 승률",
     {"menu": "games", "people": {"batter": "김도영"}, "cond": {"team": "KIA", "season": 2024, "batter_results": ["홈런"]}, "year_given": True}),
    ("2025년 홈런 제일 많이 친 타자 5명", {"menu": "other", "people": {}, "cond": {}, "year_given": True}),
    ("안녕", {"menu": "chat", "people": {}, "cond": {}, "year_given": False, "reply": "안녕하세요! 선수 기록이나 장면을 물어보세요. 예: 김도영 2024 홈런 영상"}),
]


def parse_system(as_of: str | None = None) -> str:
    today = datetime.now(timezone(timedelta(hours=9))).date()  # 한국 날짜 (서버는 UTC일 수 있다)
    fill = {"{this_year}": today.year, "{last_year}": today.year - 1}
    ex = []
    for q, a in EXAMPLES:
        s = json.dumps(a, ensure_ascii=False)
        for k, v in fill.items():
            s = s.replace(f'"{k}"', json.dumps(v)).replace(k, str(v))
        ex.append(f"질문: {q}\n답: {s}")
    return f"""너는 KBO 야구 기록 서비스 BASE:ON의 질문 해석기다. 사용자의 질문을 아래 JSON 하나로만 바꾼다. 답을 지어내지 않는다.

오늘: {today.isoformat()} · 데이터: 2024-03 ~ {as_of or last_date()} 정규시즌 (그 뒤 기록은 없다. 그 뒤 날짜를 물어도 날짜는 그대로 옮긴다 — 시스템이 안내한다)

[메뉴]
- pa: 타석 찾기 (누가 · 누구에게 · 언제 · 어디서 · 어떤 결과를 냈는지, 그 장면 영상)
- games: 경기 찾기 (팀 기준 경기 목록 · 승패 · 승률, 선발 투수 · 같이 뛴 선수 조건)
- stats: 한 선수의 한 시즌 기록 (타율 · 홈런 · OPS · 삼진 · WHIP …)
  \"김도영 홈런\"처럼 결과 이름만 말하면 pa(장면 목록). \"홈런 몇 개야\" · \"타율 몇이야\" · \"시즌 기록\"처럼 시즌 숫자를 물을 때만 stats
- other: 위 셋으로 안 되는 기록 질문 (순위 · 여러 선수 비교 · 합계 · 이닝별 집계 등)
  \"~친 타자 누구야\" · \"~맞은 투수 누구\"처럼 조건에 맞는 타석의 사람을 묻는 건 other가 아니라 pa (목록에 이름이 나온다)
  \"A랑 B 맞대결 · 상대 전적\"(타자와 투수)은 other가 아니라 pa (batter A · pitcher B). 연도를 안 말하면 전체 시즌으로 보고 year_given = true
- chat: 인사 · 서비스 사용법 · 야구 기록과 관계없는 말 → reply에 짧게 답한다

[출력 형식]
{PARSE_FORMAT}

[people] 질문에 나온 사람 이름만, 질문에 쓴 그대로 (\"도영이\" → \"도영\", \"김도영 선수\" → \"김도영\"). 없는 칸은 null 또는 빈 목록.
- batter: 친 사람 / pitcher: 던진 사람 (\"OO 상대로\", \"OO에게\", \"OO가 맞은\"의 OO가 투수인지 타자인지 문맥으로)
- player: stats 메뉴의 선수 / starter: games의 그 팀 선발 / opp_starter: 상대 팀 선발 / players: 같이 뛴 선수들
- pa에서도 경기 조건을 쓸 수 있다: \"OO가 선발로 나온 경기에서\"의 OO는 starter, \"OO랑 OO가 같이 뛴 날\"은 players (그 경기의 타석 중에서 찾는다)
- games에서 \"OO가 홈런 친 날\" · \"OO가 나온 날\"의 OO는 batter, 그 결과는 cond.batter_results (\"나온 날\"이면 넣지 않는다)

[cond] pa 메뉴 칸: results(목록) season date_from date_to(YYYY-MM-DD) stadium bat_team pit_team home_away(home|away, 타자 팀 기준)
  inning_from inning_to inning_half(초|말) situations(목록) bases outs balls strikes pitch_names(목록) speed_min speed_max video_only
games 메뉴 칸: team opponent season date_from date_to home_away result(승|패|무) batter_results(목록, people.batter가 낸 결과)
stats 메뉴 칸: season metrics(물어본 지표 목록. \"시즌 기록\"처럼 지표를 안 말하면 넣지 않는다)
- metrics에 쓸 수 있는 말: {', '.join(terms.METRICS)}  (\"방어율\" = 평균자책점, \"K\" = 삼진, \"홈런 맞은 거\" = 피홈런)
- results에 쓸 수 있는 말: {', '.join(terms.EVENT_GROUPS)}  (\"안타\"는 홈런 포함, \"장타\" = 2·3루타+홈런)
- 팀: {', '.join(sorted(set(terms.TEAMS.values())))} 중 하나로 (기아→KIA, 엘지→LG)
- stadium: {', '.join(terms.STADIUMS)}
- situations: {', '.join(terms.SITUATIONS)} / bases: {', '.join(terms.BASES)}, {terms.RISP}
- pitch_names: {', '.join(terms.PITCHES)}
- \"N회\" 하나면 inning_from = inning_to = N, \"N회 이후\"면 inning_from만
- 구속은 \"N km 넘는\" · \"N km 이상\" 모두 speed_min = N (정수 그대로, 155.1처럼 바꾸지 않는다). \"N km 이하 · 안 되는\"은 speed_max = N
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
""" + "\n\n".join(ex)


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
- 타자 시즌 기록: (Player)-[:HAS_STAT]->(BatterSeasonStat), 투수: (Player)-[:HAS_PITCHING_STAT]->(PitcherSeasonStat). qualified = 규정 타석·이닝.
- 데이터: 2024-03 ~ {last_date()} 정규시즌
[선수 ID] 질문 속 선수는 이 ID로만 찾는다 (이름으로 찾지 않는다): {json.dumps(ids, ensure_ascii=False)}

[규칙]
- MATCH / OPTIONAL MATCH / WITH / WHERE / RETURN / ORDER BY / LIMIT 만 쓴다. CREATE · MERGE · SET · DELETE · REMOVE · CALL · LOAD 금지.
- RETURN 열 이름은 한국어로 짧게 (예: 선수, 홈런, 타율). 날짜는 toString(...)으로.
- 마지막에 LIMIT 20 이하.
- 답할 수 없는 질문이면 cypher를 null로.

[출력] {{"cypher": 문자열|null, "explain": "어떻게 찾았는지 사람이 읽는 한 줄 (예: 2025 시즌 · 정규시즌 · 홈런 많은 순 5명)"}}"""
