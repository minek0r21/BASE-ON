"""타석 결과(events) 분류. 적재(etl/prepare.py)와 API(backend)가 이 파일 하나를 같이 쓴다.
한 곳만 고치면 화면마다 타율이 달라지므로 값 목록을 다른 파일에 따로 적지 않는다."""

EVENTS_KO = {  # 화면 2 탭 '결과 표시 규칙'
    "single": "안타",
    "double": "2루타",
    "triple": "3루타",
    "home_run": "홈런",
    "walk": "볼넷",
    "hit_by_pitch": "몸에 맞는 공",
    "strikeout": "삼진",
    "field_out": "아웃",
    "double_play": "병살",
    "triple_play": "삼중살",
    "fielders_choice": "야수선택",
    "field_error": "실책 출루",
    "sac_fly": "희생플라이",
    "sac_bunt": "희생번트",
    "catcher_interference": "타격방해",  # 규칙 표에는 없어서 추가
}

HITS = {"single", "double", "triple", "home_run"}
# 타수에서 빼는 결과: 볼넷, 사구, 희생플라이, 희생번트, 타격방해
NOT_AB = {"walk", "hit_by_pitch", "sac_fly", "sac_bunt", "catcher_interference"}


def events_ko(events: str | None) -> str | None:  # 영어 결과 → 한글 (예: home_run → 홈런)
    """표에 없는 값은 원문을 그대로 돌려준다 (빈칸보다 낫다)."""
    if events is None:
        return None
    return EVENTS_KO.get(events, events)


def batting_line(events_list: list[str]) -> dict:  # 결과 목록 → 타석·타수·안타·홈런·볼넷·삼진
    return {
        "pa": len(events_list),
        "ab": sum(e not in NOT_AB for e in events_list),
        "h": sum(e in HITS for e in events_list),
        "hr": events_list.count("home_run"),
        "bb": events_list.count("walk"),
        "so": events_list.count("strikeout"),
    }
