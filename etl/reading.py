"""
판독 대조 규칙 (docs/장면.md 11-6) — Gemini가 영상에서 읽은 것(제목 없이 화면 · 해설만)을 경기 기록과 맞춘다. 09 · 10이 같이 쓴다
- 판정은 Gemini가 아니라 이 코드가 한다. Gemini는 본 것을 적기만 한다
- 홈런(scene = hr): 타자 이름 필수 + 근거(시즌 n호 · 이닝 · 홈런 뒤 점수). 초·말은 판정에 쓰지 않는다(11-2: 33/35로 가장 자주 틀림)
- 안타 · 등판은 같은 틀에 종류만 늘린다 (다음 단계 — 표본 50개로 먼저 잰다)
"""
from gemini import mmss

S = lambda **p: {"type": "OBJECT", "properties": p}  # noqa: E731
STR, INT = {"type": "STRING", "nullable": True}, {"type": "INTEGER", "nullable": True}
SCORE = {**S(away_team=STR, away=INT, home_team=STR, home=INT), "nullable": True}
EVIDENCE = {"type": "ARRAY", "items": {"type": "STRING"}}

# 홈런 판독 칸 — 하이라이트(09)는 time까지, 클립(10)은 time 없이
HR_ITEM = dict(batter=STR, evidence=EVIDENCE, team=STR, season_hr_no=INT, inning=INT, half=STR, score_after=SCORE, pitcher=STR)
RULES = """화면(중계 점수판, 자막 그래픽, 유니폼 이름·등번호)과 음성(중계 해설)에서 실제로 보이거나 들린 것만 적고, 보이지 않으면 null로 두세요.
제목이나 상식으로 추측하지 마세요. 같은 홈런의 다시 보기(리플레이)는 한 번만 적으세요.
홈런마다:
- batter: 홈런 친 타자 이름 (한글)
- evidence: 이름을 어디서 확인했는지 목록 (scoreboard, caption, commentary, jersey 중)
- team: 타자 팀
- season_hr_no: 화면이나 해설에 나온 「시즌 N호」
- inning, half: 이닝 숫자와 초/말
- score_after: 홈런 직후 점수판 점수 {away_team, away, home_team, home}
- pitcher: 상대 투수 이름"""


def given(name: str) -> str:
    return name[1:] if len(name) == 3 else name


def name_hit(said: str | None, real: str) -> bool:
    """세 글자 이름은 성을 뺀 두 글자로도 맞춘다 (해설이 「도영이」처럼 부른다)"""
    return bool(said) and (real in said or said in real or given(real) in said)


def compare(h: dict, pa: dict) -> tuple[str, list[str], list[str]] | None:
    """읽은 홈런 하나 vs 기록 홈런 하나 → ('strong' | 'weak' | 'conflict', 맞은 근거, 어긋난 근거) · 이름이 다르면 None
    pa: batter · hr_seq · inning · home · away · home_post · away_post"""
    if not name_hit(h.get("batter"), pa["batter"]):
        return None
    ok, bad = [], []
    if h.get("season_hr_no") is not None:
        (ok if h["season_hr_no"] == pa["hr_seq"] else bad).append("n호")
    if h.get("inning") is not None:
        (ok if h["inning"] == pa["inning"] else bad).append("이닝")
    sa = h.get("score_after") or {}
    if sa.get("away") is not None and sa.get("home") is not None:
        # 중계사마다 원정 · 홈 순서가 달라 두 순서 모두 허용 (팀 이름이 있으면 그걸로 맞춤, 장면.md 11-2)
        both = {(sa["away"], sa["home"]), (sa["home"], sa["away"])}
        if sa.get("away_team") and pa["home"] in sa["away_team"]:
            both = {(sa["home"], sa["away"])}
        (ok if (pa["away_post"], pa["home_post"]) in both else bad).append("점수")
    if bad:
        return "conflict", ok, bad
    return ("strong" if ok else "weak"), ok, bad


def assign(hrs: list[dict], pas: list[dict], dur: float | None) -> tuple[dict, int]:
    """하이라이트(09): 기록 홈런마다 읽은 홈런 하나(겹치지 않게). 돌려줌: {pa_id: 제안}, 기록과 안 맞는 판독 홈런 수(지어냈을 수 있음)"""
    pairs = []
    for i, h in enumerate(hrs):
        t = mmss(h.get("time"))
        if t is None or t < 0 or (dur and t >= dur):
            continue
        for pa in pas:
            c = compare(h, pa)
            if c and c[0] != "conflict":
                pairs.append((c[0] == "strong", len(c[1]), i, pa["pa_id"], t, c[1], h))
    pairs.sort(key=lambda x: (x[0], x[1]), reverse=True)
    used_h, out = set(), {}
    for strong, _, i, pid, t, ok, h in pairs:
        if i in used_h or pid in out:
            continue
        used_h.add(i)
        out[pid] = {"t_sec": t, "strength": "strong" if strong else "weak", "checks": ok, "evidence": h.get("evidence") or []}
    # 같은 경기 안에서 시각이 타석 순서와 거꾸로면 둘 다 weak
    order = [pa["pa_id"] for pa in pas if pa["pa_id"] in out]
    for a, b in zip(order, order[1:]):
        if out[a]["t_sec"] > out[b]["t_sec"]:
            out[a]["strength"] = out[b]["strength"] = "weak"
    named = {i for i, h in enumerate(hrs) if any(name_hit(h.get("batter"), pa["batter"]) for pa in pas)}
    return out, len(hrs) - len(named | used_h)


# 클립 확인(10) 판정 — 사람이 보는 순서도 이 순서 (위험한 것부터)
VERDICTS = ["conflict", "other", "none", "name_only", "match1", "match2"]


def verdict(hrs: list[dict] | None, pa: dict) -> dict:
    """클립(10): 연결된 타석 하나 vs 클립에서 읽은 홈런들(연타석이면 여럿) → 판정 하나
    match2 이름 + 근거 2개↑ · match1 근거 1개 · name_only 이름만 · conflict 이름은 맞는데 근거 어긋남 ·
    other 다른 타자 홈런만 · none 홈런을 못 읽음(판독 실패 포함)"""
    if not hrs:
        return {"verdict": "none", "checks": [], "conflicts": [], "read": None}
    best = None
    for h in hrs:
        c = compare(h, pa)
        if c is None:
            continue
        rank = (c[0] != "conflict", len(c[1]))  # 충돌 없는 쪽 → 근거 많은 쪽
        if best is None or rank > best[0]:
            best = (rank, c, h)
    if best is None:
        return {"verdict": "other", "checks": [], "conflicts": [], "read": hrs[0]}
    _, (kind, ok, bad), h = best
    v = "conflict" if kind == "conflict" else "match2" if len(ok) >= 2 else "match1" if ok else "name_only"
    return {"verdict": v, "checks": ok, "conflicts": bad, "read": h}
