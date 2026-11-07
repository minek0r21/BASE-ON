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


# 하이라이트 장면 (11): 같은 경기 김도영 3회 홈런 · 5회 2루타 · 7회 삼진
SC = [dict(PA, pa_id="h", events="home_run", outs=1, pitcher="박세웅"),
      dict(PA, pa_id="d", events="double", hr_seq=None, inning=5, outs=0, pitcher="박세웅", away_post=2, home_post=5),
      dict(PA, pa_id="k", events="strikeout", hr_seq=None, inning=7, outs=2, pitcher="김원중", away_post=3, home_post=5)]


def sc(kind, **k):
    return {"kind": kind, "batter": "김도영", "evidence": ["caption"], **k}


def test_compare_scene_kind_must_match():
    assert R.compare_scene(sc("strikeout", inning=5), SC[1]) is None
    assert R.compare_scene(sc("out", inning=5), SC[1]) is None
    # 안타끼리는 후보가 되고 1·2·3루타 차이는 근거로 센다
    assert R.compare_scene(sc("single", inning=5), SC[1]) == ("conflict", ["이닝"], ["종류"])
    assert R.compare_scene(sc("double", inning=5), SC[1]) == ("strong", ["종류", "이닝"], [])
    # 아웃 수는 판정에 쓰지 않는다 (자주 하나 적게 읽음)
    assert R.compare_scene(sc("double", inning=5, outs=2), SC[1]) == ("strong", ["종류", "이닝"], [])


def test_compare_scene_home_run_uses_hr_rules():
    assert R.compare_scene(sc("home_run", season_hr_no=20, inning=3), SC[0]) == ("strong", ["n호", "이닝"], [])
    assert R.compare_scene(sc("home_run", inning=3, pitcher="세웅"), SC[0]) == ("strong", ["이닝", "투수"], [])
    assert R.compare_scene(sc("home_run", inning=3), SC[0])[0] == "weak"  # 근거 1개는 weak (11은 2개부터 strong)


def test_assign_scenes():
    items = [sc("home_run", season_hr_no=20, inning=3, time="1:00"), sc("double", inning=5, outs=0, time="3:00"),
             sc("strikeout", inning=7, pitcher="김원중", time="5:00"), sc("out", time="6:00"),
             sc("strikeout", inning=8, time="7:00"), {"kind": "single", "batter": "최형우", "time": "8:00"}]
    got, state = R.assign_scenes(items, SC, 600)
    assert {p: g["strength"] for p, g in got.items()} == {"h": "strong", "d": "strong", "k": "strong"}
    assert [state[i] for i in range(6)] == ["matched", "matched", "matched", "skipped", "conflict", "unmatched"]
    # 시각이 타석 순서와 거꾸로면 weak
    items[0]["time"] = "4:00"
    got, _ = R.assign_scenes(items, SC, 600)
    assert got["h"]["strength"] == got["d"]["strength"] == "weak"



def test_broken_scene():
    ok = {"batter": "김도영", "team": "KIA", "time": "5:11", "score_after": {"away_team": "LG", "home_team": "KIA"}}
    assert not R.broken(ok)
    assert R.broken({**ok, "score_after": {"away_team": "LG", "home_team": "두산" * 30}})
    assert R.broken({**ok, "pitcher": "선발투수정보김택연박신지이병헌최지강이영하김명신"})
    assert R.SCENE_ITEM["team"]["enum"] == R.TEAMS


def test_scene_time_numbers_or_string():
    assert R.scene_time({"time_min": 5, "time_sec": 11}) == 311
    assert R.scene_time({"time": "5:11"}) == 311
    assert R.scene_time({"time_min": 5, "time_sec": 75}) is None
    assert list(R.SCENE_ITEM)[-2:] == ["time_min", "time_sec"]  # 시각은 맨 끝 (scene-blind-1)


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
