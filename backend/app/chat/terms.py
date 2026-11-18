"""챗봇이 쓰는 야구 용어 약속 · 구장 · 팀 이름. 조회 API와 질문 해석(LLM)이 이 파일 하나를 같이 쓴다."""
from baseon_rules.events import EVENTS_KO, HITS

# 결과 묶음 — 야구 기록 기준 (안타에 홈런 포함)
EVENT_GROUPS = {
    "안타": sorted(HITS),
    "단타": ["single"], "1루타": ["single"],
    "2루타": ["double"], "3루타": ["triple"],
    "홈런": ["home_run"],
    "장타": ["double", "triple", "home_run"],
    "출루": sorted(HITS | {"walk", "hit_by_pitch"}),
    "볼넷": ["walk"], "사구": ["hit_by_pitch"], "몸에 맞는 공": ["hit_by_pitch"], "사사구": ["walk", "hit_by_pitch"],
    "삼진": ["strikeout"],
    "아웃": ["field_out", "double_play", "triple_play", "fielders_choice", "strikeout", "sac_fly", "sac_bunt"],
    "병살": ["double_play"],
    "희생플라이": ["sac_fly"], "희생번트": ["sac_bunt"], "희생타": ["sac_fly", "sac_bunt"],
    "실책": ["field_error"],
}

# 구장 → 그 구장을 홈으로 쓰는 팀 (제2구장은 따지지 않는다)
STADIUMS = {
    "잠실": ["LG", "두산"],
    "고척": ["키움"], "고척돔": ["키움"], "고척스카이돔": ["키움"], "스카이돔": ["키움"],
    "문학": ["SSG"], "인천": ["SSG"], "랜더스필드": ["SSG"],
    "사직": ["롯데"], "부산": ["롯데"],
    "대구": ["삼성"], "라팍": ["삼성"], "라이온즈파크": ["삼성"],
    "광주": ["KIA"], "챔필": ["KIA"], "챔피언스필드": ["KIA"],
    "대전": ["한화"], "한밭": ["한화"], "이글스파크": ["한화"], "볼파크": ["한화"],
    "수원": ["KT"], "위즈파크": ["KT"],
    "창원": ["NC"], "NC파크": ["NC"],
}

# 팀 별칭 → DB의 팀 이름 (Team.name)
TEAMS = {
    "KIA": "KIA", "기아": "KIA", "타이거즈": "KIA",
    "LG": "LG", "엘지": "LG", "트윈스": "LG",
    "두산": "두산", "베어스": "두산",
    "삼성": "삼성", "라이온즈": "삼성",
    "롯데": "롯데", "자이언츠": "롯데",
    "SSG": "SSG", "랜더스": "SSG",
    "한화": "한화", "이글스": "한화",
    "키움": "키움", "히어로즈": "키움",
    "KT": "KT", "kt": "KT", "위즈": "KT",
    "NC": "NC", "엔씨": "NC", "다이노스": "NC",
}

# 상황 (타석 전후 점수로 적재 때 계산된 값)
SITUATIONS = ["끝내기", "역전", "동점", "리드"]

# 주자 상황 → (1루, 2루, 3루) 조건. None은 상관없음
BASES = {
    "주자 없음": (False, False, False),
    "1루": (True, False, False),
    "2루": (False, True, False),
    "3루": (False, False, True),
    "1,2루": (True, True, False),
    "1,3루": (True, False, True),
    "2,3루": (False, True, True),
    "만루": (True, True, True),
}
RISP = "득점권"  # 2루나 3루에 주자

# 구종 (마지막 공) → DB 값 (last_pitch_name). DB 값: 직구 슬라이더 체인지업 포크 커브 투심 커터 스위퍼 너클볼 슬러브
PITCHES = {
    "직구": "직구", "포심": "직구", "포심패스트볼": "직구", "패스트볼": "직구", "속구": "직구",
    "슬라이더": "슬라이더", "체인지업": "체인지업",
    "포크": "포크", "포크볼": "포크", "스플리터": "포크", "스플리트": "포크",
    "커브": "커브", "커브볼": "커브",
    "투심": "투심", "싱커": "투심", "투심패스트볼": "투심",
    "커터": "커터", "컷패스트볼": "커터",
    "스위퍼": "스위퍼", "너클볼": "너클볼", "너클": "너클볼", "슬러브": "슬러브",
}


def pitches_of(names: list[str] | None) -> list[str] | None:
    """「포심」·「스플리터」 → DB 구종 이름 목록. 모르는 말이면 ValueError"""
    if not names:
        return None
    out = []
    for n in names:
        k = n.strip().replace(" ", "")
        if k not in PITCHES:
            raise ValueError(f"모르는 구종: {n}")
        out.append(PITCHES[k])
    return sorted(set(out))


def events_of(terms: list[str] | None) -> list[str] | None:
    """「장타」·「홈런」·「double」 → events 값 목록. 모르는 말이면 ValueError"""
    if not terms:
        return None
    out: set[str] = set()
    for t in terms:
        t = t.strip()
        if t in EVENT_GROUPS:
            out |= set(EVENT_GROUPS[t])
        elif t in EVENTS_KO:
            out.add(t)
        else:
            raise ValueError(f"모르는 결과: {t}")
    return sorted(out)


def team_of(name: str | None) -> str | None:
    if not name:
        return None
    t = TEAMS.get(name.strip()) or TEAMS.get(name.strip().upper())
    if not t:
        raise ValueError(f"모르는 팀: {name}")
    return t


def stadium_teams(name: str | None) -> list[str] | None:
    if not name:
        return None
    key = name.strip().replace("야구장", "").replace("구장", "").strip()
    if key not in STADIUMS:
        raise ValueError(f"모르는 구장: {name}")
    return STADIUMS[key]


# 시즌 기록에서 물을 수 있는 지표 → 저장 칸 (BatterSeasonStat · PitcherSeasonStat). 답 문장은 answers.py가 이 이름으로 쓴다
BAT_METRICS = {
    "타율": "avg", "홈런": "hr", "안타": "h", "OPS": "ops", "출루율": "obp", "장타율": "slg", "순수 장타력": "iso",
    "타석": "pa", "타수": "ab", "삼진": "so", "볼넷": "bb", "2루타": "b2", "3루타": "b3", "몸에 맞는 공": "hbp",
    "삼진 비율": "k_pct", "볼넷 비율": "bb_pct",
}
PIT_METRICS = {
    "경기": "g", "선발": "gs", "이닝": "outs", "WHIP": "whip", "삼진": "so", "볼넷": "bb", "피홈런": "hr", "피안타": "h",
    "피안타율": "avg", "실점": "r", "투구 수": "pitches", "평균 구속": "avg_velo", "삼진 비율": "k_pct",
}
# DB에 없는 지표 — 물으면 「없는 기록」이라고 답한다 (지어내지 않게 질문 해석에서 이름으로 받는다)
MISSING_METRICS = ["평균자책점", "승", "패", "세이브", "홀드", "타점", "득점", "도루", "자책점", "WAR"]
METRICS = list(dict.fromkeys([*BAT_METRICS, *PIT_METRICS, *MISSING_METRICS]))
