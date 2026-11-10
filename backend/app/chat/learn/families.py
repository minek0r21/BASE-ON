"""
질문 묶음(family) — 「무엇을 묻는지 + 바뀌는 값」. 학습 순환은 값을 먼저 고르고(sample) AI가 그 값을 질문 문장으로 바꾼다.
그래서 만든 질문마다 정답 값(params)을 알고 있다 → 질문 이해가 맞았는지(①) · 후보 Cypher가 맞았는지를 잴 수 있다.

  sample(rng)        정답 값 하나 (dict)
  expect(params)     그 값이면 질문 이해가 내야 할 메뉴 · 칸 (채점 기대조건과 같은 모양)
  oracle(params)     정답 결과 — 사이트 API로 계산 (없으면 None: API 없는 묶음은 사람이 본다)
  describe(params)   AI에게 「이런 질문을 만들어」라고 줄 설명
"""
import random
from dataclasses import dataclass
from typing import Callable

from .. import terms


@dataclass(frozen=True)
class Family:
    id: str
    title: str
    sample: Callable[[random.Random], dict]
    expect: Callable[[dict], dict]
    describe: Callable[[dict], str]
    oracle: Callable[[dict], dict] | None = None


# ------------------------------------------------------------------ rank: 시즌 순위 (정답 = 사이트 순위 API → registry.run_rank)
SEASONS = [2024, 2025, 2026]
TEAMS = sorted(set(terms.TEAMS.values()))


def rank_sample(rng: random.Random) -> dict:
    metric = rng.choice(terms.RANK_METRICS)
    side = None
    if metric in terms.RANK_BAT and metric in terms.RANK_PIT:
        side = rng.choice(["batter", "pitcher"])
    p = {"rank_metric": metric, "season": rng.choice(SEASONS)}
    if side:
        p["rank_side"] = side
    if rng.random() < 0.3:
        p["team"] = rng.choice(TEAMS)
    if rng.random() < 0.4:
        p["top"] = rng.choice([3, 5, 10])
    return p


def rank_expect(p: dict) -> dict:
    cond = {k: p[k] for k in ("rank_metric", "season", "team", "top") if k in p}
    if p.get("rank_side") == "pitcher":
        cond["rank_side"] = "pitcher"
    return {"menu": "rank", "cond": cond}


def rank_describe(p: dict) -> str:
    who = "투수" if p.get("rank_side") == "pitcher" or (p["rank_metric"] in terms.RANK_PIT and p["rank_metric"] not in terms.RANK_BAT) else "타자"
    parts = [f"{p['season']} 시즌", f"{who} {p['rank_metric']} 순위"]
    if p.get("team"):
        parts.append(f"{p['team']} 팀 안에서")
    parts.append(f"상위 {p['top']}명" if p.get("top") else "1위가 누구인지")
    return " · ".join(parts)


def rank_oracle(p: dict) -> dict:
    from ..registry import run_rank
    r = run_rank({}, {k: v for k, v in p.items()})
    return {"key": r["rank"]["key"], "rows": r["rank"]["rows"]}


FAMILIES: dict[str, Family] = {f.id: f for f in [
    Family(id="rank", title="시즌 순위", sample=rank_sample, expect=rank_expect, describe=rank_describe, oracle=rank_oracle),
]}
