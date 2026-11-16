"""
학습 순환 단계. 작업 파일은 backend/chat_logs/learn/<run>/ (git 제외)에만 쓴다. 서버 · 등록부는 건드리지 않는다.

  generate    값(params)을 먼저 고르고 AI가 질문 문장으로 바꾼다           → items.jsonl
  understand  질문 이해(서버와 같은 프롬프트)가 정답 값을 냈는지 (①)
  candidates  같은 질문에 Cypher 후보 3개 (기본 · 타석에서 세기 · 온도 높여 다르게), 읽기 전용 실행
  check       서로 일치 · 규칙 · 정답(사이트 API) 대조 → 판정 두 개
                verdict  정답 대조까지 한 판정 (🟢 green · 🟡 yellow · 🔴 red)
                blind    정답 대조 없이 일치 · 규칙만 본 판정 — API 없는 묶음에서 쓸 수 있는 건 이것뿐.
                         blind가 통과인데 정답과 틀리면 false_green (순환을 얼마나 믿을지의 숫자)
  review      사람이 볼 목록 (review.md · review.csv의 승인 칸)
  promote     승인(O)된 질문을 채점 질문(tests/chat_questions.csv)으로
"""
import csv
import json
import random
import re
from datetime import datetime
from pathlib import Path

import neo4j

from .. import llm, prompts
from ..service import LOG, as_of, guard, run_read
from .families import FAMILIES, Family

ROOT = LOG.parent / "learn"
CSV = Path(__file__).resolve().parents[3] / "tests" / "chat_questions.csv"
CALLS = {"n": 0}  # 이번 실행의 AI 호출 수 (비용 어림용)


def call_json(system: str, user: str, temperature: float = 0) -> dict:
    CALLS["n"] += 1
    return llm.complete_json(system, user, temperature=temperature)


def save(run: Path, items: list[dict]):
    run.mkdir(parents=True, exist_ok=True)
    with (run / "items.jsonl").open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False, default=str) + "\n")


def load(run: Path) -> list[dict]:
    return [json.loads(x) for x in (run / "items.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


# ------------------------------------------------------------------ generate
GEN_SYSTEM = """너는 KBO 야구 입문 팬이다. 주어진 설명마다 채팅창에 칠 법한 질문 한 문장을 만든다.
- 짧게, 말투는 섞어서 (반말 · 존댓말 · 줄임말). 팀은 가끔 별칭으로 (기아 · 엘지 · 쓱 · 롯데 자이언츠).
- 시즌은 다양하게 (2025년 · 25시즌 · 작년 · 올해). 오늘은 {today}이라 올해 = {y0}, 작년 = {y1}, 재작년 = {y2} — 이 셋 말고는 연도를 숫자로 쓴다.
- 설명에 없는 조건은 넣지 않는다. 설명 순서대로 같은 개수를 만든다.
출력: {{"questions": ["...", "..."]}}"""


def generate(fam: Family, n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    params = [fam.sample(rng) for _ in range(n)]
    today = datetime.now().date()
    descs = "\n".join(f"{i + 1}. {fam.describe(p)}" for i, p in enumerate(params))
    sys_text = GEN_SYSTEM.format(today=today.isoformat(), y0=today.year, y1=today.year - 1, y2=today.year - 2)
    out = call_json(sys_text, descs, temperature=0.9).get("questions") or []
    if len(out) != n:
        raise llm.LLMError(f"질문 {n}개를 달라고 했는데 {len(out)}개가 왔어요")
    return [{"id": f"{fam.id}-{seed}-{i}", "family": fam.id, "source": "synthetic", "params": p, "question": q}
            for i, (p, q) in enumerate(zip(params, out))]


# ------------------------------------------------------------------ understand (①)
def understand(it: dict, fam: Family, day: str | None):
    parsed = call_json(prompts.parse_system(day), json.dumps({"question": it["question"], "previous": None}, ensure_ascii=False))
    want = fam.expect(it["params"])
    cond = parsed.get("cond") or {}
    diff = [] if parsed.get("menu") == want["menu"] else [f"menu {parsed.get('menu')} (기대 {want['menu']})"]
    diff += [f"{k} {cond.get(k)} (기대 {v})" for k, v in want["cond"].items() if str(cond.get(k)) != str(v)]
    it.update(parsed=parsed, understood=not diff, understand_diff=diff)


# ------------------------------------------------------------------ candidates
VARIANTS = [
    ("기본", "", 0.0),
    ("타석에서 세기", "\n[이번 작성 방식] 개수 기록이면 시즌 기록 노드(BatterSeasonStat · PitcherSeasonStat) 대신 타석(PlateAppearance)에서 직접 센다. "
                  "비율 기록이면 이 지시는 무시한다.", 0.0),
    ("다르게", "", 0.8),
]


def candidates(it: dict):
    out = []
    for name, extra, temp in VARIANTS:
        c = {"variant": name}
        try:
            got = call_json(prompts.cypher_system({}) + extra, it["question"], temperature=temp)
            c["cypher"] = got.get("cypher")
            if c["cypher"]:
                cols, rows = run_read(guard(c["cypher"]))
                c.update(columns=cols, rows=rows)
        except (ValueError, llm.LLMError, neo4j.exceptions.Neo4jError) as e:
            c["error"] = str(e)[:300]
        out.append(c)
    it["candidates"] = out


# ------------------------------------------------------------------ check
def plays_for_without_season(cy: str) -> bool:
    """PLAYS_FOR 관계를 시즌으로 거르지 않았나 — 변수 없이 쓰거나, 변수.season 조건이 없으면"""
    for m in re.finditer(r"\[\s*(\w*)\s*:\s*PLAYS_FOR\s*(\{[^}]*\})?", cy, re.I):
        var, props = m.group(1), m.group(2) or ""
        if "season" in props:
            continue
        if not var or not re.search(rf"\b{var}\.season\b", cy):
            return True
    return False


RED_RULES = [  # 순환에서 실제로 나온 조용한 오류 (11-10: 236 vs 78 · 같은 선수 두 줄). (검사, 이유)
    (re.compile(r"on_[123]b\s+IS\s+(NOT\s+)?NULL", re.I).search, "주자 칸을 IS NULL로 비교 (true/false 칸)"),
    (plays_for_without_season, "소속 팀(PLAYS_FOR)을 시즌 없이 씀 (같은 선수가 여러 줄)"),
    (re.compile(r"outs\s*\)?\s*/\s*3(?![.\d])", re.I).search, "이닝을 정수 나눗셈 (115⅔ → 115)"),
]
WARN_RULES = [
    (re.compile(r"\bname\s*[:=]\s*['\"]", re.I).search, "이름으로 찾음 (동명이인)"),
]


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def same_rows(a: list, b: list) -> bool:
    """두 후보의 같은 줄이 같은 답인가 — 열 순서 · 덧붙인 열(팀 이름 등)이 달라도, 글자 하나 · 숫자 하나가 겹치면 같다"""
    sa, sb = {str(v) for v in a if isinstance(v, str)}, {str(v) for v in b if isinstance(v, str)}
    na, nb = {round(float(v), 3) for v in a if is_num(v)}, {round(float(v), 3) for v in b if is_num(v)}
    return bool(sa & sb) and bool(na & nb)


def tol(v) -> float:
    """정답 값의 자릿수만큼 허용 (사이트는 WHIP을 두 자리, 타율을 세 자리로 반올림해 준다)"""
    if not isinstance(v, float):
        return 0
    s = repr(v)
    return 0.5 * 10 ** -(len(s.split(".")[1]) if "." in s else 0) + 1e-9


def oracle_ok(c: dict, ora: dict, k: int) -> tuple[bool, str]:
    rows, want = c.get("rows") or [], ora["rows"][:k]
    if len(rows) < len(want):
        return False, f"줄 {len(rows)}개 (정답 {len(want)}개)"
    for i, w in enumerate(want):  # 같은 자리의 값이 같은가 (공동 순위는 순서가 달라도 값은 같다)
        nums = [float(v) for v in rows[i] if is_num(v)]
        ok_vals = [float(w["value"])] + ([w["value"] / 3] if ora.get("key") == "outs" else [])  # 이닝은 아웃 수 · 이닝 둘 다 맞음
        if not any(abs(x - v) <= max(tol(w["value"]), 0.05 if v != float(w["value"]) else 0) for x in nums for v in ok_vals):
            return False, f"{i + 1}번째 값 {nums} (정답 {w['value']})"
    last = want[-1]["rank"] if want else 0  # 경계에 걸친 공동 순위를 빼고 이름이 다 있는가
    names = {w["name"] for w in want if w["rank"] < last} if any(w["rank"] < last for w in want) else {want[0]["name"]} if want else set()
    got = {str(v) for r in rows[:k] for v in r if isinstance(v, str)}
    miss = names - got
    return (not miss), (f"없는 선수 {sorted(miss)}" if miss else "")


def check(it: dict, fam: Family):
    cands = it["candidates"]
    k = it["params"].get("top") or 1
    red = sorted({msg for c in cands for hit, msg in RED_RULES if c.get("cypher") and hit(c["cypher"])})
    warn = sorted({msg for c in cands for hit, msg in WARN_RULES if c.get("cypher") and hit(c["cypher"])})
    ran = [c for c in cands if c.get("rows")]
    first = ran[0]["rows"][:k] if ran else []
    agree = len(ran) == len(cands) and all(
        len(c["rows"]) >= len(first) and all(same_rows(x, y) for x, y in zip(first, c["rows"][:k])) for c in ran[1:])
    it.update(red=red, warn=warn, agree=agree)
    blind_ok = agree and not red
    it["blind"] = "pass" if blind_ok else "fail"
    if fam.oracle:
        ora = fam.oracle(it["params"])
        it["oracle"] = ora["rows"][:max(k, 1)]
        per = [oracle_ok(c, ora, max(k, 1)) if "rows" in c else (False, c.get("error", "실행 안 됨")) for c in cands]
        for c, (ok, why) in zip(cands, per):
            c.update(oracle_ok=ok, oracle_why=why)
        all_ok = all(ok for ok, _ in per)
        it["verdict"] = "green" if all_ok and not red else "red"
        it["false_green"] = blind_ok and not all_ok
    else:
        it["verdict"] = "yellow" if blind_ok else "red"
        it["false_green"] = None


# ------------------------------------------------------------------ review
MARK = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def review(run: Path, items: list[dict]):
    lines = [f"# 검토 목록 — {run.name}", "", "승인은 review.csv의 「승인」 칸에 O. 🟢도 한 번은 눈으로 본다.", ""]
    for it in items:
        lines += [f"## {MARK.get(it.get('verdict'), '?')} {it['question']}",
                  f"- 정답 값: `{json.dumps(it['params'], ensure_ascii=False)}` · 질문 이해 {'맞음' if it.get('understood') else '틀림 ' + '; '.join(it.get('understand_diff', []))}",
                  f"- 일치 {'O' if it.get('agree') else 'X'} · blind {it.get('blind')} · false_green {it.get('false_green')}"
                  + (f" · 🔴 {', '.join(it['red'])}" if it.get("red") else "") + (f" · 주의 {', '.join(it['warn'])}" if it.get("warn") else "")]
        if it.get("oracle"):
            lines.append("- 정답(사이트): " + " · ".join(f"{o['rank']}. {o['name']}({o['team']}) {o['value']}" for o in it["oracle"]))
        for c in it.get("candidates", []):
            head = f"  - [{c['variant']}] " + ("정답 일치" if c.get("oracle_ok") else f"정답과 다름: {c.get('oracle_why', '')}" if "oracle_ok" in c else "")
            lines.append(head + (f" — 오류 {c['error']}" if c.get("error") else f" — 첫 줄 {c.get('rows', [[]])[:1]}"))
            if c.get("cypher"):
                lines += ["    ```cypher", *("    " + x for x in c["cypher"].splitlines()), "    ```"]
        lines.append("")
    (run / "review.md").write_text("\n".join(lines), encoding="utf-8")
    with (run / "review.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "질문", "판정", "blind", "false_green", "질문이해", "정답값", "승인"])
        for it in items:
            w.writerow([it["id"], it["question"], it.get("verdict"), it.get("blind"), it.get("false_green"), "O" if it.get("understood") else "X",
                        json.dumps(it["params"], ensure_ascii=False), ""])


# ------------------------------------------------------------------ promote
def promote(run: Path) -> int:
    """승인된 질문 → 채점 질문. 정답 숫자는 사이트 API(oracle)에서 온 것만 적는다"""
    ok = {r["id"] for r in csv.DictReader((run / "review.csv").open(encoding="utf-8-sig")) if r["승인"].strip().upper() in ("O", "Y", "1")}
    have = {r["질문"] for r in csv.DictReader(CSV.open(encoding="utf-8-sig"))}
    rows = []
    for it in load(run):
        if it["id"] not in ok or it["question"] in have:
            continue
        fam = FAMILIES[it["family"]]
        want = fam.expect(it["params"])
        cond = "; ".join(f"{k}={v}" for k, v in want["cond"].items())
        ora = it.get("oracle") or []
        firsts = [o for o in ora if o["rank"] == 1]
        val = f"{want['menu']}.rows.0.value={firsts[0]['value']}" if firsts and want["menu"] == "rank" else ""
        name = f"; rank.rows.0.name={firsts[0]['name']}" if len(firsts) == 1 and want["menu"] == "rank" else ""
        rows.append([it["question"], want["menu"], cond, "", "", (val + name).lstrip("; "), "", f"학습 순환 {run.name} ({it['source']})"])
    if rows:
        with CSV.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f, lineterminator="\n").writerows(rows)
    return len(rows)


# ------------------------------------------------------------------ collect (서버 · 로컬 기록 → 갈래)
BUCKET = {
    "other_off": "②③ 메뉴 밖 — API가 있으면 API 메뉴, 없으면 Cypher 틀 후보",
    "zero_rows": "① 0건 — 잘못 알아들었는지 확인",
    "BAD_CONDITION": "① 조건 못 알아들음 — 프롬프트 · terms 확인",
    "player_not_found": "① 선수 못 찾음 — 별명 · 이름 확인",
    "after_as_of": "④ 기준일 뒤 — 고정 답",
    "talk_record_like": "⑤ talk 답에 기록 숫자 — 질문 이해가 기록 메뉴로 보내야 했는지",
    "llm_error": "AI 오류",
}


def collect() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if not LOG.exists():
        return out
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            x = json.loads(line)
        except ValueError:
            continue
        out.setdefault(x.get("reason", "?"), []).append(x)
    return out


def new_run(fam: str) -> Path:
    return ROOT / f"{datetime.now():%Y%m%d_%H%M%S}_{fam}"


def as_of_now() -> str | None:
    return as_of()
