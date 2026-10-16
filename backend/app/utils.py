"""여러 라우터가 같이 쓰는 작은 도우미."""
from datetime import date

WEEKDAYS = "월화수목금토일"


def weekday_ko(iso: str) -> str:  # "2025-08-28" → "목"
    return WEEKDAYS[date.fromisoformat(iso).weekday()]


def avg(h: int, ab: int):  # 타율. 타수가 0이면 None
    return round(h / ab, 3) if ab else None


def batter_is_home(inning_half: str) -> bool:  # 말 공격 = 홈팀 타자
    return inning_half == "말"


def result_of(team_score: int, opp_score: int) -> str:  # 승 W / 패 L / 무 D
    if team_score > opp_score:
        return "W"
    if team_score < opp_score:
        return "L"
    return "D"
