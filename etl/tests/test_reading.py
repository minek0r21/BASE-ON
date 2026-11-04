"""
판독 대조 규칙 단위 시험 (reading.py, 장면.md 11-6) — Gemini를 부르지 않는다.
실행: docker compose run --rm etl etl/tests/test_reading.py   (pytest가 있으면 pytest로도 돈다)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reading as R  # noqa: E402

# 김도영 20호 · 3회말 · 홈런 뒤 롯데 2 : 4 KIA (원정 롯데, 홈 KIA)
PA = {"pa_id": "p1", "batter": "김도영", "hr_seq": 20, "inning": 3, "home": "KIA", "away": "롯데", "home_post": 4, "away_post": 2}


def hr(**k):
    return {"batter": "김도영", "evidence": ["commentary"], **k}


def test_name():
    assert R.name_hit("도영", "김도영") and R.name_hit("김도영 선수", "김도영")
    assert not R.name_hit("김선빈", "김도영") and not R.name_hit(None, "김도영")


def test_compare_strong_weak_conflict():
    assert R.compare(hr(season_hr_no=20, inning=3), PA) == ("strong", ["n호", "이닝"], [])
    assert R.compare(hr(), PA) == ("weak", [], [])
    assert R.compare(hr(season_hr_no=19, inning=3), PA) == ("conflict", ["이닝"], ["n호"])
    assert R.compare({"batter": "김선빈", "season_hr_no": 20}, PA) is None


def test_half_is_not_used():
    # 11-2: 초·말은 가장 자주 틀려 판정에 쓰지 않는다 — 초·말만 다르면 충돌이 아니다
    assert R.compare(hr(inning=3, half="초"), PA)[0] == "strong"


def test_score_either_order():
    assert R.compare(hr(score_after={"away": 2, "home": 4}), PA)[1] == ["점수"]
    assert R.compare(hr(score_after={"away": 4, "home": 2}), PA)[1] == ["점수"]  # 원정 · 홈을 뒤바꿔 적은 경우
    # 팀 이름이 있으면 그 순서로만: 「KIA 2 : 4 롯데」는 KIA가 2점 → 기록(KIA 4)과 어긋남
    assert R.compare(hr(score_after={"away_team": "KIA", "away": 2, "home_team": "롯데", "home": 4}), PA)[0] == "conflict"


def test_verdict():
    assert R.verdict(None, PA)["verdict"] == "none"
    assert R.verdict([], PA)["verdict"] == "none"
    assert R.verdict([{"batter": "최형우"}], PA)["verdict"] == "other"
    assert R.verdict([hr()], PA)["verdict"] == "name_only"
    assert R.verdict([hr(inning=3)], PA)["verdict"] == "match1"
    assert R.verdict([hr(season_hr_no=20, score_after={"away": 2, "home": 4})], PA)["verdict"] == "match2"
    v = R.verdict([hr(season_hr_no=19)], PA)
    assert v["verdict"] == "conflict" and v["conflicts"] == ["n호"]


def test_verdict_multi_hr_clip_picks_matching_one():
    # 연타석 클립: 19호(1회)와 20호(3회)가 같이 나오면 20호 타석에는 맞는 쪽으로 판정
    hrs = [hr(season_hr_no=19, inning=1), hr(season_hr_no=20, inning=3)]
    assert R.verdict(hrs, PA)["verdict"] == "match2"


def test_assign_order_check():
    pas = [dict(PA, pa_id="a", hr_seq=19, inning=1), dict(PA, pa_id="b", hr_seq=20, inning=3)]
    hrs = [hr(season_hr_no=19, time="5:00"), hr(season_hr_no=20, time="1:00")]  # 시각이 타석 순서와 거꾸로
    got, invented = R.assign(hrs, pas, 600)
    assert got["a"]["strength"] == got["b"]["strength"] == "weak" and invented == 0


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
