"""
코드로 다시 확인하기 — AI 해석(parsed)을 질문 글자와 대조해 고친다. AI 호출 없음.
어려운 시험지(learn exam, 11-16)에서 틀린 것의 대부분이 AI가 「글자에 있는 것」을 잘못 옮긴 경우였다:
  · 연도: 질문에 연도가 없는데 올해를 넣음 (되묻기가 사라짐) · 「24」를 다른 해로
  · 팀: 선수 옆에 쓴 팀(그 선수 소속)을 상대 팀 칸에 넣음 → 0개
  · 메뉴: 「8회 이후」 · 「득점권」 같은 장면 조건이 있는데 시즌 기록(stats)으로 → 조건이 사라진 숫자
연도 · 팀 이름처럼 글자로 확실히 뽑히는 것은 코드를 믿는다.
"""
import re

from . import terms

# 연도 말 → 올해 기준 몇 해 전
REL_YEAR = [(r"재작년|지지난\s*(?:해|시즌)", 2), (r"작년|지난\s*(?:해|시즌)|전년", 1),
            (r"올해|올\s*시즌|이번\s*시즌|금년|올해\s*시즌", 0)]
RECENT = re.compile(r"요즘|요새|최근|현재|지금|이번\s*년")
# 「24」 · 「2024」 · 「24년」 · 「24시즌」. 뒤에 회 · 명 · 개 · 월 …이 붙으면 연도가 아니다
YEAR = re.compile(r"(?<![\d.\-/])(20\d{2}|\d{2})"
                  r"(?=$|\s|[?!,~]|년|시즌|에|엔|때|도|부터|까지|이랑|랑|은|는|[A-Za-z])"   # 「38홈런」 · 「10명」은 연도가 아니다
                  r"(?!\s+(?:회|명|개|위|번|승|패|이닝|경기|월|일|점|살|아웃)(?![가-힣]))")  # 「10 명」은 아니고 「2025 승패」는 연도


def years_in(message: str, this_year: int) -> tuple[set[int], bool]:
    """질문 글자에 있는 시즌들, 「요즘」 같은 말이 있는가"""
    ys = set()
    for pat, back in REL_YEAR:  # 재작년 먼저 지운다 (안에 「작년」이 있다)
        if re.search(pat, message):
            ys.add(this_year - back)
            message = re.sub(pat, " ", message)
    for m in YEAR.finditer(message):
        v = int(m.group(1))
        v = v if v >= 2000 else 2000 + v
        if 2015 <= v <= this_year + 1:
            ys.add(v)
    return ys, bool(RECENT.search(message))


def fix_season(parsed: dict, message: str, day: str | None, follow_up: bool) -> list[str]:
    """시즌 칸을 질문 글자에 맞춘다. 고친 것 목록을 돌려준다 (로그 · 채점용)"""
    cond = parsed.setdefault("cond", {}) or {}
    parsed["cond"] = cond
    if cond.get("date_from") or cond.get("date_to") or parsed.get("menu") in (None, "chat", "talk", "other"):
        return []
    this = int(day[:4]) if day else 2026
    ys, recent = years_in(message, this)
    got = cond.get("season")
    try:
        got = int(got) if got not in (None, "", []) else None
    except (TypeError, ValueError):
        got = None
    if len(ys) == 1:
        y = next(iter(ys))
        if got != y:
            cond["season"] = y
            parsed["year_given"] = True
            return [f"season {got}→{y}"]
        return []
    if not ys and got is not None and not follow_up:
        if recent:
            if got != this:
                cond["season"] = this
                return [f"season {got}→{this} (요즘)"]
            return []
        cond.pop("season", None)  # 질문에 연도가 없다 → 메뉴 규칙대로 되묻는다
        parsed["year_given"] = False
        return [f"season {got}→없음"]
    return []


AGG = re.compile(r"통산|커리어|월별|달마다|이닝별|회별|팀별|구장별|상대\s*팀별|요일|합계|평균\s*몇|추이|변화")


def other_to_stats(parsed: dict, message: str) -> list[str]:
    """「전민재 자이언츠 3루타 몇개야」 — 연도가 없어 통산으로 읽고 other(못 답함)로 보낸 경우 → stats (시즌은 되묻는다).
    통산 · 월별 · 이닝별처럼 정말 메뉴 밖인 말이 있으면 그대로"""
    if parsed.get("menu") != "other" or AGG.search(message):
        return []
    people, cond = parsed.get("people") or {}, parsed.get("cond") or {}
    who = people.get("player") or people.get("batter") or people.get("pitcher")
    asked = [m for m in (cond.get("metrics") or []) + (cond.get("results") or []) if m in terms.METRICS]
    if not who or not asked or any(people.get(k) for k in ("players", "starter", "opp_starter")):
        return []
    if any(cond.get(k) for k in ("bases", "situations", "inning_from", "stadium", "pit_team", "date_from")):
        return []
    parsed.update(menu="stats", people={"player": who}, cond={k: v for k, v in cond.items() if k == "season"} | {"metrics": asked})
    if "season" not in parsed["cond"]:
        parsed["year_given"] = False
    return ["other→stats"]


VIDEO_ONLY = re.compile(r"영상\s*(?:이\s*)?(?:있는|나오는|붙은|딸린)|영상만|영상\s*있는\s*것만")


def norm(word: str, names: list[str]) -> str | None:
    """「평균구속」 · 「ops」 → 「평균 구속」 · 「OPS」 (띄어쓰기 · 대소문자만 다른 지표 이름)"""
    key = re.sub(r"\s", "", str(word)).lower()
    return next((n for n in names if re.sub(r"\s", "", n).lower() == key), None)


def fix_cond(parsed: dict, message: str) -> list[str]:
    """지표 이름 맞추기 · 영상 거르기는 「영상 있는 것만」이라고 할 때만"""
    cond, out = parsed.get("cond") or {}, []
    if isinstance(cond.get("metrics"), list):
        fixed = [norm(m, terms.METRICS) or m for m in cond["metrics"]]
        if fixed != cond["metrics"]:
            out.append(f"metrics {cond['metrics']}→{fixed}")
            cond["metrics"] = fixed
    if cond.get("rank_metric") and cond["rank_metric"] not in terms.RANK_METRICS:
        n = norm(cond["rank_metric"], terms.RANK_METRICS)
        if n:
            out.append(f"rank_metric {cond['rank_metric']}→{n}")
            cond["rank_metric"] = n
    if cond.get("video_only") and not VIDEO_ONLY.search(message):  # 「장면 영상」은 영상도 같이 보여 달라는 말 → 거르면 「없어요」로 잘못 나간다
        cond.pop("video_only")
        out.append("video_only→없음")
    return out


# 장면 조건 — 이게 있으면 시즌 기록(stats)으로는 답할 수 없다
SCENE = re.compile(r"\d+\s*회|득점권|만루|주자|끝내기|역전|동점|풀카운트|\d\s*아웃|투아웃|원아웃|노아웃|\d\s*-\s*\d\s*카운트|"
                   r"구장|홈\s*경기|원정|상대로|상대\s|에게|한테|직구|포심|슬라이더|커브|체인지업|포크|"
                   + "|".join(map(re.escape, terms.STADIUMS)))


def needs_pa(parsed: dict, message: str) -> bool:
    return parsed.get("menu") == "stats" and bool(SCENE.search(message))


STAT_CUE = re.compile(r"몇|얼마|기록|개수|율|성적|시즌\s*숫자|총|합계|어때|어떻|잘\s*(?:했|쳐|던)")


def result_only(parsed: dict, message: str) -> list[str]:
    """「최주환 26시즌 장타」처럼 결과 이름만 말했는데 stats(장타율)로 읽은 경우 → pa (등록부 규칙: 결과 이름만이면 장면 목록).
    지표 이름이 글자 그대로 있거나 「몇 개 · 얼마 · 기록」이 있으면 그대로 둔다"""
    if parsed.get("menu") != "stats" or STAT_CUE.search(message):
        return []
    bare = message.replace(" ", "")
    if any(m.replace(" ", "") in bare for m in (parsed.get("cond") or {}).get("metrics") or []):
        return []
    words = [w for w in sorted(terms.EVENT_GROUPS, key=len, reverse=True) if w.replace(" ", "") in bare]
    if not words:
        return []
    who = (parsed.get("people") or {}).get("player")
    parsed["menu"] = "pa"
    parsed["people"] = {"batter": who} if who else {}
    parsed["cond"] = {k: v for k, v in (parsed.get("cond") or {}).items() if k == "season"} | {"results": [words[0]]}
    return [f"stats→pa (결과 이름 「{words[0]}」만)"]


def team_near(message: str, name: str) -> str | None:
    """이름 바로 앞 · 뒤에 붙은 팀 (「기아 성범이랑 쓱 지훈이」 → 지훈 = SSG). 팀이 둘 나오는 비교 질문에서 사람마다"""
    i = message.replace(" ", "").find(name.replace(" ", ""))
    if i < 0:
        return None
    bare = message.replace(" ", "")
    before, after = bare[max(0, i - 6):i], bare[i + len(name.replace(' ', '')):][:8]
    for text, pick in ((before, -1), (after, 0)):
        hits = [(m.start(), terms.TEAMS[a]) for a in terms.TEAMS for m in re.finditer(re.escape(a), text, re.I)]
        if hits:
            return sorted(hits)[pick][1]
    return None


def teams_in(message: str) -> list[str]:
    """질문에 나온 팀 (별칭 포함, 긴 별칭 먼저)"""
    found, text = [], message
    for alias in sorted(terms.TEAMS, key=len, reverse=True):
        if re.search(r"(?<![A-Za-z])" + re.escape(alias) + r"(?![A-Za-z])", text, re.I):
            t = terms.TEAMS[alias]
            if t not in found:
                found.append(t)
            text = re.sub(re.escape(alias), " ", text, flags=re.I)
    return found
