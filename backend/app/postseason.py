"""포스트시즌 공통 — 꼬리표 · 홈런 표기 · 기간. 설계: docs/포스트시즌.md (PS3 · PS5 · PS6)"""
from datetime import date, datetime, timedelta, timezone

from .db import run

STAGE_SHORT = {"WC": "WC", "SPO": "준PO", "PO": "PO", "KS": "KS"}  # 꼬리표 「준PO 2차전」
STAGE_NAME = {"WC": "와일드카드 결정전", "SPO": "준플레이오프", "PO": "플레이오프", "KS": "한국시리즈"}
STAGE_ORDER = ["WC", "SPO", "PO", "KS"]
KS_WINS = 4          # 한국시리즈 7전 4선승 → 4승이면 끝
AFTER_KS_DAYS = 14   # 기간 끝 = 한국시리즈 끝나고 14일 (PS6)
KST = timezone(timedelta(hours=9))


def stage_label(stage: str | None, series_game_no: int | None) -> str | None:
    """「준PO 2차전」. 정규시즌이면 None"""
    if not stage:
        return None
    short = STAGE_SHORT.get(stage, stage)
    return f"{short} {series_game_no}차전" if series_game_no else short


def hr_label(season: int, game_type: str | None, hr_seq: int | None, post_hr_seq: int | None) -> str | None:
    """「시즌 45호」 / 「2026 포스트시즌 2호」 (PS5). 홈런이 아니면 None"""
    if game_type == "postseason":
        return f"{season} 포스트시즌 {post_hr_seq}호" if post_hr_seq else None
    return f"시즌 {hr_seq}호" if hr_seq else None


def game_tag(row: dict) -> dict:
    """경기 꼬리표 칸 — row에 game_type · stage · series_game_no가 있어야 한다"""
    gt = row.get("game_type") or "regular"
    return {"game_type": gt, "stage": row.get("stage"), "series_game_no": row.get("series_game_no"),
            "stage_label": stage_label(row.get("stage"), row.get("series_game_no"))}


Q_PERIOD = """
MATCH (g:Game {season: $season, game_type: 'regular'})
WITH max(g.date) AS last_regular
OPTIONAL MATCH (k:Game {season: $season, stage: 'KS'})-[:HOME]->(h:Team), (k)-[:AWAY]->(a:Team)
WITH last_regular, k,
     CASE WHEN k.home_final > k.away_final THEN h.team_id WHEN k.away_final > k.home_final THEN a.team_id END AS winner
RETURN toString(last_regular) AS last_regular, toString(max(k.date)) AS ks_last, collect(winner) AS ks_winners
"""


def today_kst() -> date:
    return datetime.now(KST).date()


def period(season: int) -> dict:
    """포스트시즌 기간 (PS6): 정규시즌 마지막 경기 다음 날 ~ 한국시리즈 끝나고 14일.
    한국시리즈가 아직 안 끝났으면 end = None(열려 있음). active = 오늘이 기간 안인가"""
    r = run(Q_PERIOD, season=season)
    if not r or not r[0]["last_regular"]:
        return {"start": None, "end": None, "active": False}
    r = r[0]
    start = date.fromisoformat(r["last_regular"]) + timedelta(days=1)
    wins: dict = {}
    for w in r["ks_winners"]:
        wins[w] = wins.get(w, 0) + 1
    ks_done = r["ks_last"] and max(wins.values(), default=0) >= KS_WINS
    end = date.fromisoformat(r["ks_last"]) + timedelta(days=AFTER_KS_DAYS) if ks_done else None
    today = today_kst()
    return {"start": start.isoformat(), "end": end.isoformat() if end else None,
            "active": start <= today and (end is None or today <= end)}
