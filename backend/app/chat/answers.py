"""
챗봇 답 문장 — 조회 결과의 숫자로 코드가 채운다 (AI는 답 문장을 쓰지 않는다).
틀린 숫자가 나올 수 없고, AI 호출이 질문당 1번(질문 이해)으로 끝난다.
문구 기준: 사실 · 기준만 짧게, 줄임말 풀기 (OPS · WHIP은 그대로). DB · AI를 부르지 않는 순수 함수만 둔다.
"""
from . import terms

COUNT_UNIT = {"hr": "개", "h": "개", "so": "개", "bb": "개", "b2": "개", "b3": "개", "hbp": "개", "pitches": "개",
              "g": "경기", "gs": "경기", "r": "점"}
RATE3 = {"avg", "obp", "slg", "ops", "iso"}
PCT1 = {"k_pct", "bb_pct"}
WIN_WORD = {"승": "이긴", "패": "진", "무": "비긴"}


def has_batchim(word: str) -> bool:
    """마지막 글자에 받침이 있나 (한글이 아니면 숫자 · 영문 읽는 소리로 대충)"""
    if not word:
        return False
    c = word[-1]
    if "가" <= c <= "힣":
        return (ord(c) - 0xAC00) % 28 != 0
    return c in "013678LMNlmn"  # 영(0) 일 삼 육 칠 팔, 엘 엠 엔


def josa(word: str, with_batchim: str, without: str) -> str:
    return word + (with_batchim if has_batchim(word) else without)


def rate3(v: float) -> str:
    return f"{v:.3f}".replace("0.", ".", 1) if 0 <= v < 1 else f"{v:.3f}"


def innings(outs: int) -> str:
    return f"{outs // 3}{['', '⅓', '⅔'][outs % 3]}"


def fmt(key: str, v) -> str:
    if key in RATE3:
        return rate3(v)
    if key in PCT1:
        return f"{v * 100:.1f}%"
    if key == "whip":
        return f"{v:.2f}"
    if key == "outs":
        return f"{innings(int(v))}이닝"
    if key == "avg_velo":
        return f"{v:.1f}km"
    return f"{v:g}{COUNT_UNIT.get(key, '')}" if isinstance(v, (int, float)) else str(v)


def season_label(season: int | None, as_of: str | None) -> str:
    """현재 시즌은 기준일까지라고 붙인다: 2026 시즌(7월 26일까지)"""
    if not season:
        return "전체 시즌"
    if as_of and season == int(as_of[:4]):
        return f"{season} 시즌({int(as_of[5:7])}월 {int(as_of[8:10])}일까지)"
    return f"{season} 시즌"


def as_of_ko(as_of: str) -> str:
    return f"{int(as_of[:4])}년 {int(as_of[5:7])}월 {int(as_of[8:10])}일"


def after_as_of(cond: dict, as_of: str | None) -> bool:
    """기준일 뒤만 묻는 질문 (조회하지 않고 바로 답한다)"""
    if not as_of:
        return False
    season = cond.get("season")
    if isinstance(season, int) and season > int(as_of[:4]):
        return True
    return bool(cond.get("date_from")) and str(cond["date_from"]) > as_of


def pa_text(result: dict, cond: dict) -> str:
    total, shown = result.get("total") or 0, result.get("shown") or 0
    res = cond.get("results") or []
    noun = res[0] if len(res) == 1 else "타석"
    if total == 0:
        return f"조건에 맞는 {josa(noun, '이', '가')} 없어요."
    lines = [f"{noun} {total}개예요."]
    videos = sum(1 for r in result.get("rows") or [] if r.get("video"))
    tail = [f"최근 {shown}개"] if total > shown else []
    if videos:
        tail.append(f"영상 {videos}개")
    if tail:
        lines.append(" · ".join(tail))
    return "\n".join(lines)


def games_text(result: dict, cond: dict) -> str:
    total = result.get("total") or 0
    if total == 0:
        return "조건에 맞는 경기가 없어요."
    if cond.get("result") in WIN_WORD:
        return f"{WIN_WORD[cond['result']]} 경기는 {total}경기예요."
    rec = result.get("record") or {}
    w, l, d = rec.get("win", 0), rec.get("loss", 0), rec.get("draw", 0)
    line = f"{w}승 {l}패" + (f" {d}무" if d else "")
    if rec.get("win_pct") is not None:
        line += f" · 승률 {rate3(rec['win_pct'])}"
    return line


def pick_stat(metric: str, batting: dict | None, pitching: dict | None) -> tuple[str, object] | None:
    """지표 이름 → (저장 칸, 값). 타자 · 투수 둘 다 있는 이름(삼진 · 볼넷)은 기록이 있는 쪽"""
    for table, stat in ((terms.BAT_METRICS, batting), (terms.PIT_METRICS, pitching)):
        if stat and metric in table and stat.get(table[metric]) is not None:
            return table[metric], stat[table[metric]]
    return None


def stats_text(result: dict, metrics: list[str] | None, as_of: str | None) -> str:
    name, label = result.get("name") or "", season_label(result.get("season"), as_of)
    batting, pitching = result.get("batting"), result.get("pitching")
    metrics = [m for m in dict.fromkeys(metrics or []) if m in terms.METRICS]
    if not metrics:
        return f"{name} {label} 기록이에요."
    parts, missing, none = [], [], []
    for m in metrics:
        if m in terms.MISSING_METRICS:
            missing.append(m); continue
        got = pick_stat(m, batting, pitching)
        if got:
            parts.append(f"{m} {fmt(*got)}")
        else:
            none.append(m)
    lines = []
    if parts:
        lines.append(f"{name} {label} " + " · ".join(parts))
        rate_asked = any(terms.BAT_METRICS.get(m) in RATE3 | PCT1 for m in metrics)
        if rate_asked and batting and batting.get("qualified") is False:
            lines.append(f"규정 타석 미달 ({batting.get('pa')}타석)")
    if none:
        lines.append(f"{name} {label} {' · '.join(none)} 기록은 없어요.")
    if missing:
        lines.append(f"{josa(' · '.join(missing), '은', '는')} BASE:ON에 없는 기록이에요.")
    return "\n".join(lines)


def other_text(result: dict) -> str:
    return f"자동 조회 {result.get('total', 0)}줄 (참고용 · 로컬 전용)"


def text_for(menu: str, result: dict, cond: dict, as_of: str | None) -> str:
    if menu == "pa":
        return pa_text(result, cond)
    if menu == "games":
        return games_text(result, cond)
    if menu == "stats":
        return stats_text(result, cond.get("metrics"), as_of)
    return other_text(result)
