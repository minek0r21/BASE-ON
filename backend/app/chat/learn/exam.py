"""
시험지 만들기 — 실제 사용자처럼 「어렵게」 말한 질문 + 코드가 계산한 정답 → 채점 CSV (grade --file 로 채점).
학습 순환(steps.py)과 같은 방식: 값(params)을 먼저 고르고 AI는 문장만 만든다. 정답 숫자는 사이트 API로 계산한다.

  dev   보고 고쳐도 되는 시험지 (틀린 질문을 보고 프롬프트 · 코드를 고친다)
  hold  따로 떼어 둔 시험지 — 점수만 본다. 틀린 질문을 보고 프롬프트에 예시로 넣지 않는다 (외워서 오르는 점수 거르기)

    docker compose exec api python -m app.chat.learn exam --name dev --n 12 --seed 1
    docker compose exec api python -m app.chat.grade --file tests/chat_exam_dev.csv
"""
import csv
import random
from datetime import datetime
from pathlib import Path

from .. import terms
from ..service import find_player
from .families import rank_describe, rank_expect, rank_sample
from .steps import call_json

TESTS = Path(__file__).resolve().parents[3] / "tests"
SEASONS = [2024, 2025, 2026]
TEAMS = sorted(set(terms.TEAMS.values()))
HOME = {"잠실": "LG", "고척": "키움", "문학": "SSG", "사직": "롯데", "대구": "삼성", "광주": "KIA", "대전": "한화", "수원": "KT", "창원": "NC"}

# 어렵게 말하기 — 질문마다 하나. 「연도 빼기」는 값에서 시즌을 지우고 되묻기 → 시즌 고르기로 채점한다
STYLES = {
    "오타": "글자 하나를 잘못 친다 (이름 · 낱말 중 한 군데, 자판에서 옆 글자나 받침 빠짐). 띄어쓰기도 대충",
    "줄임": "최대한 짧게, 조사 · 물음표 없이 낱말만 (예: 「도영 24 홈런 몇개」)",
    "이름만": "선수는 성을 빼고 이름만 (도영이 · 현민이처럼), 팀은 별칭 (기아 · 엘지 · 쓱 · 한화 이글스)",
    "돌려 말하기": "지표 이름을 그대로 쓰지 않고 풀어서 (홈런 → 담장 넘긴 거, 삼진 → 삼진 먹은 거 / 투수면 삼진 잡은 거, 1위 → 제일 잘한)",
    "수다": "앞뒤에 상관없는 말을 붙인다 (「어제 친구랑 얘기하다 궁금해서 그런데」 · 「ㅋㅋ」), 반말",
    "연도 빼기": "연도 · 시즌을 말하지 않는다",
}
GEN_SYSTEM = """너는 KBO 야구 입문 팬이다. 주어진 설명마다 채팅창에 칠 법한 질문 한 문장을 만든다.
- 설명 끝의 [말투]를 꼭 따른다. 오늘은 {today}이라 올해 = {y0}, 작년 = {y1}, 재작년 = {y2}.
- 설명에 있는 조건(선수 · 팀 · 시즌 · 지표 · 몇 명)은 빠짐없이, 설명에 없는 조건은 넣지 않는다. 설명 순서대로 같은 개수를 만든다.
- 풀어 말해도 뜻은 그 지표 그대로여야 한다 (출루율 ≠ 타율처럼 다른 지표로 읽힐 말 금지). 「시즌 기록」은 숫자 하나를, 「장면」은 그 타석들을 묻는 말로.
출력: {{"questions": ["...", "..."]}}"""


def unique(name: str, role: str) -> bool:
    """이름으로 한 명만 나오는 선수만 쓴다 (동명이인 되묻기는 따로 시험)"""
    return len(find_player(name, role)) == 1


def some_player(rng: random.Random, season: int, side: str) -> dict:
    from ...routers.league import get_batters, get_pitchers
    rows = (get_batters(season=season, team=None, sort="pa", qualified=True, limit=500)["batters"] if side == "batter" else
            get_pitchers(season=season, team=None, role="starter", qualified=True, sort="outs", limit=1000)["pitchers"])
    rng.shuffle(rows)
    return next(r for r in rows if unique(r["name"], side))


# ------------------------------------------------------------------ 묶음: (params, 설명, 채점 줄) — 정답은 여기서 계산
def ex_rank(rng):
    p = rank_sample(rng)
    want = rank_expect(p)
    from ..registry import run_rank
    top = run_rank({}, p)["rank"]["rows"][0]
    cond = "; ".join(f"{k}={v}" for k, v in want["cond"].items() if k != "season")
    return p, rank_describe(p), {"기대메뉴": "rank", "기대조건": cond, "기대값": f"rank.rows.0.name={top['name']}; rank.rows.0.value={top['value']}"}


COUNTS = {"홈런", "안타", "2루타", "3루타", "볼넷", "삼진", "몸에 맞는 공"}


def ex_stats(rng):
    from ...routers.chat import season_stats
    season, side = rng.choice(SEASONS), rng.choice(["batter", "batter", "pitcher"])
    who = some_player(rng, season, side)
    table, part = (terms.BAT_METRICS, "batting") if side == "batter" else (terms.PIT_METRICS, "pitching")
    metric = rng.choice([m for m in table if m not in ("타석", "타수", "경기")])
    stat = season_stats(player_id=who["player_id"], season=season)[part]
    p = {"player": who["name"], "season": season, "metric": metric, "side": side}
    if side == "batter" and metric in COUNTS:  # 개수는 pa(장면 목록)로 답해도 숫자가 같다 → 어느 쪽이든 그 숫자가 답에 있으면 맞음
        n = stat[table[metric]]
        return p, f"{who['name']}({who['team']} 타자) {season} 시즌 {metric} 몇 개인지", {
            "기대메뉴": "stats|pa", "기대조건": "", "기대값": f"text~{n}개"}
    desc = f"{who['name']}({who['team']} {'타자' if side == 'batter' else '투수'}) {season} 시즌 기록 중 {metric}이 얼마인지 (숫자 하나)"
    return p, desc, {"기대메뉴": "stats", "기대조건": f"metrics={metric}",
                     "기대값": f"name={who['name']}; {part}.{table[metric]}={stat[table[metric]]}"}


def ex_pa(rng):
    from ...routers.chat import PASearch, search_pa
    for _ in range(10):
        season = rng.choice(SEASONS)
        who = some_player(rng, season, "batter")
        p = {"batter": who["name"], "season": season, "result": rng.choice(["홈런", "2루타", "안타", "삼진", "볼넷", "장타"])}
        extra = rng.choice([None, "bases", "stadium", "inning"])
        if extra == "bases":
            p["bases"] = rng.choice(["득점권", "만루", "주자 없음"])
        elif extra == "stadium":
            p["stadium"] = rng.choice(list(HOME))
        elif extra == "inning":
            p["inning_from"] = rng.choice([7, 8, 9])
        body = {"batter_id": who["player_id"], "results": [p["result"]], "season": season,
                **{k: p[k] for k in ("bases", "stadium", "inning_from") if k in p}}
        total = search_pa(PASearch(**body))["total"]
        if total:
            break
    bits = [f"{who['name']}({who['team']} 타자)", f"{season} 시즌", f"{p['result']} 친 장면" if p["result"] not in ("삼진", "볼넷") else f"{p['result']} 당한 타석"]
    bits += [f"{p['bases']} 상황" if "bases" in p else "", f"{p['stadium']} 구장에서" if "stadium" in p else "",
             f"{p['inning_from']}회 이후" if "inning_from" in p else ""]
    return p, " · ".join(b for b in bits if b) + " 장면 (그 타석들 · 영상)", {"기대메뉴": "pa", "기대조건": f"results={p['result']}",
                                                                   "기대개수": str(total), "기대값": f"conditions~{who['name']}"}


def ex_games(rng):
    from ...routers.chat import GameSearch, search_games
    season, team = rng.choice(SEASONS), rng.choice(TEAMS)
    p = {"team": team, "season": season}
    if rng.random() < 0.5:
        p["opponent"] = rng.choice([t for t in TEAMS if t != team])
    if rng.random() < 0.3:
        p["home_away"] = rng.choice(["home", "away"])
    r = search_games(GameSearch(**p))
    bits = [f"{team} 팀", f"{season} 시즌", f"{p['opponent']} 상대" if "opponent" in p else "",
            {"home": "홈 경기", "away": "원정 경기"}.get(p.get("home_away"), ""), "몇 승 몇 패인지 (성적 · 승률)"]
    return p, " · ".join(b for b in bits if b), {"기대메뉴": "games", "기대조건": f"team={team}",
                                                  "기대개수": str(r["total"]), "기대값": f"record.win={r['record']['win']}"}


TALK = ["OPS가 무슨 뜻인지", "WHIP이 뭔지", "인필드 플라이 규칙", "보크가 뭔지", "낫아웃(스트라이크 아웃 낫아웃)", "규정타석이 뭔지",
        "희생플라이는 타수에 들어가는지", "더블헤더가 뭔지", "지명타자 제도", "콜드게임", "피치클락", "홀드가 무슨 기록인지",
        "볼카운트 읽는 법", "야구장 처음 갈 때 응원석 고르는 법", "FA 제도", "타격 방해"]


def ex_talk(rng):
    t = rng.choice(TALK)
    return {"topic": t}, f"{t} (선수 · 시즌 기록이 아니라 규칙 · 용어 · 입문 질문)", {"기대메뉴": "talk", "기대조건": "", "기대값": "tag~일반 설명"}


EXAMS = {"rank": ex_rank, "stats": ex_stats, "pa": ex_pa, "games": ex_games, "talk": ex_talk}
NO_YEAR_OK = {"rank", "stats", "pa", "games"}  # 시즌을 빼면 되묻기가 나와야 하는 묶음


def valid(q: str, p: dict, style: str) -> bool:
    """만든 질문이 정답 값과 맞는가 — 한 번에 여러 개를 만들면 AI가 이름을 다른 줄과 섞는다 (11-16 dev2: 김현수 → 「현민」)"""
    from ..checks import teams_in, years_in
    bare = q.replace(" ", "")
    who = p.get("player") or p.get("batter")
    if who:
        grams = {who[i:i + 2] for i in range(len(who) - 1)}
        if not any(g in bare for g in grams):
            return False
    for k in ("team",):
        if p.get(k) and p[k] not in teams_in(q):
            return False
    if "season" in p:
        ys = years_in(q, datetime.now().year)[0]
        if ys != (set() if style == "연도 빼기" else {p["season"]}):
            return False
    return True


def ask_batch(sys_text: str, items: list) -> list[str]:
    got = call_json(sys_text, "\n".join(f"{i + 1}. {d} [말투: {s} — {STYLES[s]}]" for i, (d, s, _, _) in enumerate(items)),
                    temperature=0.9).get("questions") or []
    return got if len(got) == len(items) else [""] * len(items)


def make(name: str, n: int, seed: int) -> Path:
    rng = random.Random(seed)
    today = datetime.now().date()
    sys_text = GEN_SYSTEM.format(today=today.isoformat(), y0=today.year, y1=today.year - 1, y2=today.year - 2)
    style_names = list(STYLES)
    out = []
    for fam, fn in EXAMS.items():
        items = []
        for i in range(n):
            p, desc, row = fn(rng)
            style = style_names[i % len(style_names)]
            if style == "연도 빼기" and fam not in NO_YEAR_OK:
                style = "수다"
            if style == "연도 빼기":
                desc = desc.replace(f"{p['season']} 시즌", "").replace(" ·  · ", " · ")
                row["시즌선택"] = str(p["season"])  # 되물으면 이 시즌을 고른다 (채점이 대신 누른다)
            elif "season" in p:
                row["기대조건"] = "; ".join(filter(None, [row["기대조건"], f"season={p['season']}"]))
            items.append((desc, style, row, p))
        got = []
        for i in range(0, n, 6):  # 여섯 개씩 (길면 줄이 섞인다)
            got += ask_batch(sys_text, items[i:i + 6])
        bad = [i for i, q in enumerate(got) if not valid(q, items[i][3], items[i][1])]
        for i in bad:  # 틀린 줄은 하나씩 다시 (그래도 틀리면 버린다)
            got[i] = ask_batch(sys_text, [items[i]])[0]
        kept = 0
        for q, (desc, style, row, p) in zip(got, items):
            if not valid(q, p, style):
                continue
            kept += 1
            out.append({"질문": q.strip(), "기대메뉴": row["기대메뉴"], "기대조건": row.get("기대조건", ""),
                        "시즌선택": row.get("시즌선택", ""), "기대개수": row.get("기대개수", ""), "기대값": row.get("기대값", ""),
                        "앞질문": "", "메모": f"{fam} · {style} · {desc}"})
        print(f"{fam}: {kept}/{n}개 (다시 만든 것 {len(bad)})")
    f = TESTS / f"chat_exam_{name}.csv"
    with f.open("w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)
    return f
