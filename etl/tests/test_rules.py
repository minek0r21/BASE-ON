"""
계산 규칙 단위 시험 — 백분위 식·꾸준함(D3)·실점 귀속(책임 주자).
실행: docker compose run --rm etl etl/tests/test_rules.py   (pytest가 있으면 pytest로도 돈다)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare as P  # noqa: E402


# ---------------------------------------------------------------- 백분위
def test_percentile_top_is_not_100():
    pct = P._percentile(pd.Series([0.1, 0.2, 0.2, 0.3, np.nan]), True)
    assert pct.tolist()[:4] == [0, 25, 25, 75]  # 1위 = 나보다 나쁜 3명 ÷ 4명
    assert np.isnan(pct.iloc[4])


def test_percentile_reverse_and_rounding():
    assert P._percentile(pd.Series([0.1, 0.2, 0.3]), False).tolist() == [67, 33, 0]  # 낮을수록 좋음
    assert P._percentile(pd.Series(range(8)), True).iloc[1] == 13  # 12.5 → 13 (사사오입)


# ---------------------------------------------------------------- 꾸준함 (D3)
def _month_pas(player, month, n, events="single"):
    return [{"player_id": player, "season": 2026, "date": f"2026-{month:02d}-15", "events": events}] * n


def test_consistency_merges_march_and_october():
    # 3월 8 + 4월 15 = 23타석 → 4월로 한 달, 9월 12 + 10월 10 = 22타석 → 9월로 한 달. 합치지 않으면 20타석 달이 5월 하나뿐
    rows = (_month_pas("A", 3, 8) + _month_pas("A", 4, 15) + _month_pas("A", 5, 20, "strikeout")
            + _month_pas("A", 9, 12) + _month_pas("A", 10, 10))
    sd = P._ops_sd(pd.DataFrame(rows)).set_index("player_id")["ops_sd"]
    assert round(sd["A"], 6) == round(float(np.std([2.0, 0.0, 2.0])), 6)  # 모표준편차 (ddof=0)


def test_consistency_needs_three_months_of_20_pa():
    rows = _month_pas("B", 4, 20) + _month_pas("B", 5, 20) + _month_pas("B", 6, 19)  # 6월은 19타석 → 2개월뿐
    assert np.isnan(P._ops_sd(pd.DataFrame(rows)).set_index("player_id")["ops_sd"]["B"])


# ---------------------------------------------------------------- 실점 귀속
def _pa(ab, pitcher, batter, pre=(None, None, None), post=(None, None, None), runs=0):
    """pre/post = (1루, 2루, 3루) 주자"""
    return {"game_pk": "G", "inning": 7, "inning_topbot": "top", "at_bat_number": ab,
            "pitcher": pitcher, "batter": batter, "runs_scored": runs,
            "on_1b": pre[0], "on_2b": pre[1], "on_3b": pre[2],
            "post_on_1b": post[0], "post_on_2b": post[1], "post_on_3b": post[2]}


def _charged(rows):
    c = P.charge_runs(pd.DataFrame(rows))
    return c.groupby("pitcher")["runs"].sum().to_dict()


def test_inherited_runner_scores_on_sac_fly():
    # A가 만루를 만들고 내려감 → B가 희생플라이 → 3루 주자 득점은 A 몫 (홍민기 2025-07-25 사례)
    rows = [
        _pa(1, "A", "r3", post=(None, None, "r3")),
        _pa(2, "A", "r2", pre=(None, None, "r3"), post=(None, "r2", "r3")),
        _pa(3, "A", "r1", pre=(None, "r2", "r3"), post=("r1", "r2", "r3")),
        _pa(4, "B", "x", pre=("r1", "r2", "r3"), post=(None, "r1", "r2"), runs=1),
    ]
    assert _charged(rows) == {"A": 1}


def test_home_run_splits_by_responsibility():
    # 1루 주자는 A가, 타자는 B가 상대 → 투런 홈런 = A 1 · B 1
    rows = [
        _pa(1, "A", "r1", post=("r1", None, None)),
        _pa(2, "B", "hr", pre=("r1", None, None), runs=2),
    ]
    assert _charged(rows) == {"A": 1, "B": 1}


def test_pinch_runner_inherits():
    # A가 내보낸 r1이 대주자 p1로 바뀜 → p1 득점도 A 몫
    rows = [
        _pa(1, "A", "r1", post=("r1", None, None)),
        _pa(2, "B", "x", pre=("p1", None, None), post=(None, None, None), runs=1),
    ]
    assert _charged(rows) == {"A": 1}


def test_runs_without_departing_runner_go_to_pitcher():
    # 원천이 득점만 있고 주자 이동이 맞지 않는 경우 → 지금 투수
    assert _charged([_pa(1, "A", "x", post=("x", None, None), runs=1)]) == {"A": 1}


# ---------------------------------------------------------------- 유인(체이스율)
def _pitch(ab, n, x, z, result, events=None, top=3.4, bot=1.6):
    return {"game_pk": "G", "game_date": "2025-05-01", "at_bat_number": ab, "pitch_number": n, "pitcher": "A",
            "plate_x": x, "plate_z": z, "sz_top": top, "sz_bot": bot, "pitch_result": result, "events": events}


def test_chase_counts_zone_edge_and_bunts():
    rows = [
        _pitch(1, 1, 0.80, 2.5, "S"),            # 존 반폭+공 반지름(0.829) 안 → 존 안, 세지 않음
        _pitch(1, 2, 0.90, 2.5, "S"),            # 존 밖 + 헛스윙 → 존 밖 1 · 스윙 1
        _pitch(1, 3, 0.00, 1.40, "B"),           # 아래로 존 밖 + 볼 → 존 밖 2
        _pitch(1, 4, 1.20, 2.5, "V", "strikeout"),  # 번트 헛스윙 → 빼기
        _pitch(2, 1, 1.20, 2.5, "H", "sac_bunt"),   # 희생번트 타석의 마지막 공 → 빼기
        _pitch(3, 1, None, None, "B"),           # 위치 없음 → 빼기
        _pitch(4, 1, 1.00, 2.5, "F", None),      # 결과 없이 끝난 타석의 공도 센다 → 존 밖 3 · 스윙 2
    ]
    c = P.chase_counts(pd.DataFrame(rows)).iloc[0]
    assert (c["o_pitches"], c["o_swings"]) == (3, 2)


# ---------------------------------------------------------------- 안타 장면 자동 확정 (장면.md 5-2, 2차)
def _hit(pa_id, events, runs, situation="없음", inning=5, half="말"):
    return {"pa_id": pa_id, "events": events, "runs_scored": runs, "situation": situation,
            "inning": inning, "inning_half": half}


def test_hit_claim_unique_and_multi():
    import match_pa as M
    pool = pd.DataFrame([_hit("a", "single", 0, inning=1), _hit("b", "double", 2, "역전", 5), _hit("c", "single", 1, inning=8)])
    b, c = pool.iloc[1], pool.iloc[2]
    seg = "박찬호의 역전 2타점 적시타"
    assert M.hit_reason(b, pool, seg, seg) is None                      # 주장을 다 만족하는 타석은 b 하나
    assert M.hit_reason(c, pool, seg, seg) == "claim_mismatch"          # c는 1타점·역전 아님
    assert M.hit_reason(b, pool, "박찬호의 적시타", "") == "multi_hit"   # 적시타는 b·c 둘 → 사람이
    assert M.hit_reason(b, pool, "박찬호 3안타 맹타", "") == "multi_hit"  # 여러 타석 요약 영상


def test_hit_claim_comeback_and_rbi_list():
    import match_pa as M
    q = pd.Series(_hit("x", "single", 2, "리드"))
    assert M.fits_claim(q, "hit", "문성주의 역전 적시타", "")               # 동점 → 앞서감(리드)도 제목은 「역전」
    assert not M.fits_claim(q, "hit", "문성주의 동점 적시타", "")
    assert M.fits_claim(q, "hit", "류지혁의 6타점 경기! 쐐기 2타점 적시타", "")  # n타점이 여럿이면 하나라도 맞으면
    assert not M.fits_claim(pd.Series(_hit("y", "single", 0)), "hit", "적시타", "")  # 적시타인데 득점 없음


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except AssertionError as e:
            failed += 1
            print("FAIL", name, e)
    print(f"{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(1 if failed else 0)
