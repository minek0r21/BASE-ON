"""
판독 대조 규칙 (docs/장면.md 11-6) — Gemini가 영상에서 읽은 것(제목 없이 화면 · 해설만)을 경기 기록과 맞춘다. 09 · 10이 같이 쓴다
- 판정은 Gemini가 아니라 이 코드가 한다. Gemini는 본 것을 적기만 한다
- 홈런(scene = hr): 타자 이름 필수 + 근거(시즌 n호 · 이닝 · 홈런 뒤 점수). 초·말은 판정에 쓰지 않는다(11-2: 33/35로 가장 자주 틀림)
- 하이라이트 장면(11, scene-blind-2): 홈런 · 안타(1·2·3루타) · 삼진을 한 번에 읽는다. 타자 이름 + 종류(홈런 · 안타 · 삼진)가 맞아야 후보,
  근거는 n호(홈런) · 이닝 · 플레이 뒤 점수 · 투수 · 안타 종류. 아웃 수는 읽게만 하고 판정에 안 쓴다(11-05 시험: 4번에 1번 틀림, 초·말과 같은 처리). 근거 2개↑ 일치 · 어긋남 없음 = strong (장면.md 11-7)
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


# ------------------------------------------------------------------ 하이라이트 장면 (11, 장면.md 11-7)
# 읽는 종류 → 기록 events. 홈런 · 안타 · 삼진만 읽는다 (scene-blind-1에서 볼넷 · 아웃까지 다 적게 했더니 응답이 무너졌다, 장면.md 11-7)
KINDS = ["home_run", "single", "double", "triple", "strikeout"]
EVENTS = {k: k for k in KINDS}
HITS = {"single", "double", "triple"}
# 칸 순서가 곧 응답 순서다 — time을 맨 앞에 두면 그 칸에 생각을 늘어놓는다(scene-blind-1). 09처럼 이름 먼저 · time 맨 끝
SCENE_ITEM = dict(batter=STR, evidence=EVIDENCE, team=STR, kind={"type": "STRING", "enum": KINDS, "nullable": True},
                  season_hr_no=INT, inning=INT, half=STR, outs=INT, score_after=SCORE, pitcher=STR, time=STR)
SCENE_RULES = """화면(중계 점수판, 자막 그래픽, 유니폼 이름·등번호)과 음성(중계 해설)에서 실제로 보이거나 들린 것만 적고, 보이지 않으면 null로 두세요.
제목이나 상식으로 추측하지 마세요. 같은 플레이의 다시 보기(리플레이)는 한 번만 적으세요. 영상에 나오는 순서대로 적으세요.
홈런 · 안타 · 삼진 장면만 적고, 그 밖의 결과(볼넷, 땅볼·뜬공 아웃, 호수비 등)는 적지 마세요.
장면마다 (모든 칸은 짧은 값만, 설명 문장 금지):
- batter: 타자 이름 (한글)
- evidence: 타자 이름을 어디서 확인했는지 목록 (scoreboard, caption, commentary, jersey 중)
- team: 타자 팀
- kind: home_run(홈런) · single(1루타) · double(2루타) · triple(3루타) · strikeout(삼진)
- season_hr_no: 홈런일 때 화면이나 해설에 나온 「시즌 N호」
- inning, half: 이닝 숫자와 초/말
- outs: 공을 던지기 전 점수판의 아웃 수 (0~2)
- score_after: 플레이 직후 점수판 점수 {away_team, away, home_team, home}
- pitcher: 상대 투수 이름
- time: 타자가 공을 친 순간(삼진은 마지막 공을 던진 순간)의 영상 시각, 「분:초」 문자열만 (예: 5:11)"""


def compare_scene(h: dict, pa: dict) -> tuple[str, list[str], list[str]] | None:
    """읽은 장면 하나 vs 기록 타석 하나 → ('strong' | 'weak' | 'conflict', 맞은 근거, 어긋난 근거) · 이름이나 종류가 다르면 None
    pa: batter · pitcher · events · hr_seq · inning · home · away · home_post · away_post
    안타끼리는 같은 종류로 보고 1·2·3루타 차이는 근거(「종류」)로 센다 — 중계 화면만으로 갈리기 쉬워서"""
    kind, ev = h.get("kind"), pa["events"]
    if kind not in EVENTS or not (EVENTS[kind] == ev or (kind in HITS and ev in HITS)):
        return None
    if not name_hit(h.get("batter"), pa["batter"]):
        return None
    if ev == "home_run":
        c = compare(h, pa)
        ok, bad = list(c[1]), list(c[2])
    else:
        ok, bad = [], []
        if kind in HITS:
            (ok if kind == ev else bad).append("종류")
        if h.get("inning") is not None:
            (ok if h["inning"] == pa["inning"] else bad).append("이닝")
        sa = h.get("score_after") or {}
        if sa.get("away") is not None and sa.get("home") is not None:
            both = {(sa["away"], sa["home"]), (sa["home"], sa["away"])}
            if sa.get("away_team") and pa["home"] in sa["away_team"]:
                both = {(sa["home"], sa["away"])}
            (ok if (pa["away_post"], pa["home_post"]) in both else bad).append("점수")
    if h.get("pitcher") and pa.get("pitcher"):
        (ok if name_hit(h["pitcher"], pa["pitcher"]) else bad).append("투수")
    if bad:
        return "conflict", ok, bad
    return ("strong" if len(ok) >= 2 else "weak"), ok, bad


def assign_scenes(items: list[dict], pas: list[dict], dur: float | None) -> tuple[dict, dict]:
    """하이라이트 한 개: 기록 타석마다 읽은 장면 하나(겹치지 않게, 근거 많은 쪽부터)
    pas는 타석 순서(at_bat_number)대로. 시각이 타석 순서와 거꾸로인 짝은 둘 다 weak
    돌려줌: {pa_id: 제안}, 판독 장면별 상태 {i: 'matched' | 'conflict' | 'unmatched' | 'skipped' | 'no_time'}"""
    pairs, state = [], {}
    for i, h in enumerate(items):
        t = mmss(h.get("time"))
        if h.get("kind") not in EVENTS:
            state[i] = "skipped"
            continue
        if t is None or t < 0 or (dur and t >= dur):
            state[i] = "no_time"
            continue
        state[i] = "unmatched"
        for pa in pas:
            c = compare_scene(h, pa)
            if c is None:
                continue
            if c[0] == "conflict":
                state[i] = "conflict" if state[i] == "unmatched" else state[i]
                continue
            state[i] = "candidate"
            pairs.append((c[0] == "strong", len(c[1]), i, pa["pa_id"], t, c[1], h))
    pairs.sort(key=lambda x: (x[0], x[1]), reverse=True)
    out = {}
    for strong, _, i, pid, t, ok, h in pairs:
        if state[i] == "matched" or pid in out:
            continue
        state[i] = "matched"
        out[pid] = {"t_sec": t, "strength": "strong" if strong else "weak", "checks": ok, "kind": h.get("kind"),
                    "evidence": h.get("evidence") or [], "i": i}
    order = [pa["pa_id"] for pa in pas if pa["pa_id"] in out]
    for a, b in zip(order, order[1:]):
        if out[a]["t_sec"] > out[b]["t_sec"]:
            out[a]["strength"] = out[b]["strength"] = "weak"
    for i, s in state.items():
        if s == "candidate":  # 후보는 있었는데 다른 장면에 밀림 (같은 타석을 두 번 읽음 등)
            state[i] = "unmatched"
    return out, state
