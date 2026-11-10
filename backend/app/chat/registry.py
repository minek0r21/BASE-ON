"""
챗봇 메뉴 등록부 — 메뉴 하나에 필요한 것을 한 곳에 둔다. 프롬프트의 메뉴 · 조건 칸 · 예시, 실행, 답 문장이 모두 여기서 나온다.
메뉴를 더할 때는 Menu 하나를 MENUS에 넣는다 (프롬프트 · service를 따로 고치지 않는다).
학습 순환(learn/)이 승인한 메뉴도 여기로 들어온다 — 사람 승인 + 전체 재채점(grade --gate)을 통과한 것만.

  prompt   [메뉴]에 들어갈 설명 (여러 줄 가능, 첫 줄 앞에 「- id: 」가 붙는다)
  slots    [cond]에 들어갈 이 메뉴의 칸 설명
  examples (질문, 해석) — {this_year} · {last_year}는 프롬프트를 만들 때 채운다
  season   시즌이 없을 때: "ask" 되묻기(전체 포함) · "ask_one" 되묻기(한 시즌만, 되묻지 않은 경우 최근 시즌) · None 상관없음
  run      (선수 ids, cond) → 결과 dict.  text  (결과, cond, 기준일) → 답 문장
"""
from dataclasses import dataclass, field
from typing import Callable

from .. import db
from ..errors import ApiError
from . import answers


@dataclass(frozen=True)
class Menu:
    id: str
    prompt: str
    slots: str
    run: Callable[[dict, dict], dict]
    text: Callable[[dict, dict, str | None], str]
    season: str | None = None
    examples: list = field(default_factory=list)


def pick(cond: dict, keys: list[str]) -> dict:
    return {k: cond[k] for k in keys if cond.get(k) not in (None, "", [])}


def latest_team(player_id: str, season: int | None = None) -> str | None:
    r = db.run("""MATCH (:Player {player_id: $id})-[f:PLAYS_FOR]->(t:Team) WHERE $season IS NULL OR f.season = $season
                  RETURN t.name AS team ORDER BY f.season DESC, f.last_date DESC LIMIT 1""", id=player_id, season=season)
    return r[0]["team"] if r else None


# ------------------------------------------------------------------ pa: 타석 찾기
PA_KEYS = ["results", "season", "date_from", "date_to", "stadium", "bat_team", "pit_team", "home_away", "inning_from", "inning_to",
           "inning_half", "situations", "bases", "outs", "balls", "strikes", "pitch_names", "speed_min", "speed_max", "video_only"]


def run_pa(ids: dict, cond: dict) -> dict:
    from ..routers import chat as api
    body = pick(cond, PA_KEYS)
    body.update({k: v for k, v in (("batter_id", ids.get("batter")), ("pitcher_id", ids.get("pitcher"))) if v})
    return api.search_pa(api.PASearch(**body))


# ------------------------------------------------------------------ games: 경기 찾기
GAME_KEYS = ["team", "opponent", "season", "date_from", "date_to", "home_away", "result"]


def run_games(ids: dict, cond: dict) -> dict:
    from ..routers import chat as api
    body = pick(cond, GAME_KEYS)
    if not body.get("team"):  # 팀을 말하지 않았으면 선발 · 같이 뛴 선수의 그 시즌(없으면 최근) 팀으로
        who = ids.get("starter") or (ids.get("players") or [None])[0]
        if who:
            body["team"] = latest_team(who, body.get("season"))
    if not body.get("team"):
        raise ApiError(400, "NEED_TEAM", "어느 팀 기준인지 함께 말씀해 주세요. 예: KIA가 …")
    body.update({k: v for k, v in (("starter_id", ids.get("starter")), ("opp_starter_id", ids.get("opp_starter")),
                                   ("player_ids", ids.get("players"))) if v})
    return api.search_games(api.GameSearch(**body))


# ------------------------------------------------------------------ stats: 한 선수 시즌 기록
def run_stats(ids: dict, cond: dict) -> dict:
    from ..routers import chat as api
    if not ids.get("player"):
        raise ApiError(400, "NEED_PLAYER", "어느 선수의 기록인지 말씀해 주세요.")
    return api.season_stats(player_id=ids["player"], season=int(cond["season"]))


MENUS: dict[str, Menu] = {m.id: m for m in [
    Menu(
        id="pa",
        prompt="타석 찾기 (누가 · 누구에게 · 언제 · 어디서 · 어떤 결과를 냈는지, 그 장면 영상)",
        slots="results(목록) season date_from date_to(YYYY-MM-DD) stadium bat_team pit_team home_away(home|away, 타자 팀 기준)\n"
              "  inning_from inning_to inning_half(초|말) situations(목록) bases outs balls strikes pitch_names(목록) speed_min speed_max video_only",
        run=run_pa, text=lambda r, c, d: answers.pa_text(r, c), season="ask",
        examples=[
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
        ]),
    Menu(
        id="games",
        prompt="경기 찾기 (팀 기준 경기 목록 · 승패 · 승률, 선발 투수 · 같이 뛴 선수 조건)",
        slots="team opponent season date_from date_to home_away result(승|패|무)",
        run=run_games, text=lambda r, c, d: answers.games_text(r, c), season="ask",
        examples=[
            ("기아가 올러 선발일 때 엘지 상대로 승률 어때?",
             {"menu": "games", "people": {"starter": "올러"}, "cond": {"team": "KIA", "opponent": "LG"}, "year_given": False}),
            ("2025년에 김도영이랑 나성범이 같이 뛴 날 이긴 날 있어?",
             {"menu": "games", "people": {"players": ["김도영", "나성범"]}, "cond": {"team": "KIA", "season": 2025, "result": "승"}, "year_given": True}),
            ("LG 작년 성적 어때", {"menu": "games", "people": {}, "cond": {"team": "LG", "season": "{last_year}"}, "year_given": True}),
            ("2025년 7월 4일 한화 경기 몇 대 몇이었어",
             {"menu": "games", "people": {}, "cond": {"team": "한화", "date_from": "2025-07-04", "date_to": "2025-07-04"}, "year_given": True}),
        ]),
    Menu(
        id="stats",
        prompt="한 선수의 한 시즌 기록 (타율 · 홈런 · OPS · 삼진 · WHIP …)\n"
               "  \"김도영 홈런\"처럼 결과 이름만 말하면 pa(장면 목록). \"홈런 몇 개야\" · \"타율 몇이야\" · \"시즌 기록\"처럼 시즌 숫자를 물을 때만 stats",
        slots="season metrics(물어본 지표 목록. \"시즌 기록\"처럼 지표를 안 말하면 넣지 않는다)",
        run=run_stats, text=lambda r, c, d: answers.stats_text(r, c.get("metrics"), d), season="ask_one",
        examples=[
            ("김도영 올해 타율 몇이야",
             {"menu": "stats", "people": {"player": "김도영"}, "cond": {"season": "{this_year}", "metrics": ["타율"]}, "year_given": True}),
            ("원태인 2025 시즌 기록", {"menu": "stats", "people": {"player": "원태인"}, "cond": {"season": 2025}, "year_given": True}),
            ("원태인 작년 평균자책점이랑 삼진",
             {"menu": "stats", "people": {"player": "원태인"}, "cond": {"season": "{last_year}", "metrics": ["평균자책점", "삼진"]}, "year_given": True}),
        ]),
]}
