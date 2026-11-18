"""
챗봇 순수 함수 테스트 (DB · AI 없이): 답 문장 · 호출 제한 · 질문 해석 출력 모양.
    docker compose exec api python -m unittest tests.test_chat_units -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "backend", ROOT / "shared"):  # PC에서 바로 돌릴 때
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.chat import answers, prompts, terms  # noqa: E402
from app.chat.limits import Limiter  # noqa: E402

AS_OF = "2026-07-26"


class Answers(unittest.TestCase):
    def test_pa_count_and_videos(self):
        r = {"total": 38, "shown": 10, "rows": [{"video": {"video_id": "x"}}] * 7 + [{"video": None}] * 3}
        self.assertEqual(answers.pa_text(r, {"results": ["홈런"]}), "홈런 38개예요.\n최근 10개 · 영상 7개")

    def test_pa_zero_uses_right_particle(self):
        self.assertEqual(answers.pa_text({"total": 0, "shown": 0}, {"results": ["홈런"]}), "조건에 맞는 홈런이 없어요.")
        self.assertEqual(answers.pa_text({"total": 0, "shown": 0}, {"results": ["2루타"]}), "조건에 맞는 2루타가 없어요.")
        self.assertEqual(answers.pa_text({"total": 0, "shown": 0}, {}), "조건에 맞는 타석이 없어요.")

    def test_pa_matchup_summary(self):  # 결과를 안 정한 맞대결 → 타석 · 타수 · 안타 요약
        r = {"total": 12, "shown": 10, "rows": [], "summary": {"pa": 12, "ab": 10, "h": 3, "hr": 1, "bb": 1, "so": 4}}
        self.assertEqual(answers.pa_text(r, {}), "12타석 10타수 3안타 (타율 .300) · 홈런 1 · 삼진 4 · 볼넷 1\n최근 10개")

    def test_pa_who(self):  # 타자를 안 정한 질문 → 많이 친 타자 이름
        r = {"total": 12, "shown": 10, "rows": [],
             "by_batter": {"top": [{"name": "오스틴", "n": 3}, {"name": "김도영", "n": 2}], "people": 9}}
        self.assertEqual(answers.pa_text(r, {"results": ["홈런"]}), "홈런 12개예요.\n오스틴 3개 · 김도영 2개 등 9명\n최근 10개")

    def test_pa_few_rows_say_when(self):
        r = {"total": 1, "shown": 1, "rows": [{"date": "2024-06-23", "inning": 5, "inning_half": "초", "batter": "김도영",
                                              "pitcher": "최원준", "result": "3루타", "video": None}]}
        self.assertEqual(answers.pa_text(r, {"results": ["3루타"]}), "3루타 1개예요.\n2024년 6월 23일 5회초 · 김도영 · 투수 최원준 · 3루타")

    def test_asks_who(self):
        self.assertTrue(answers.asks_who("2024년에 류현진 상대로 홈런 친 타자 누구누구야"))
        self.assertTrue(answers.asks_who("2025년 기아 타자들 만루에서 장타"))
        self.assertFalse(answers.asks_who("2024년 고척에서 키움 투수들이 포크볼로 잡은 삼진"))

    def test_games_one_game_says_score(self):
        r = {"total": 1, "record": {"win": 1, "loss": 0, "draw": 0, "win_pct": 1.0},
             "rows": [{"date": "2025-05-04", "team": "LG", "team_score": 12, "opp_score": 4, "opponent": "두산", "result": "승"}]}
        self.assertEqual(answers.games_text(r, {}), "2025년 5월 4일 LG 12:4 두산 · 승")

    def test_games_few_list_each(self):
        rows = [{"date": "2024-08-13", "team": "한화", "team_score": 2, "opp_score": 3, "opponent": "LG", "result": "패"},
                {"date": "2024-05-02", "team": "한화", "team_score": 1, "opp_score": 5, "opponent": "LG", "result": "패"}]
        self.assertEqual(answers.games_text({"total": 2, "rows": rows}, {"result": "패"}),
                         "진 경기는 2경기예요.\n2024년 8월 13일 한화 2:3 LG · 패\n2024년 5월 2일 한화 1:5 LG · 패")

    def test_gocheok_dome(self):
        self.assertEqual(terms.stadium_teams("고척돔"), ["키움"])

    def test_games_record(self):
        r = {"total": 9, "record": {"win": 5, "loss": 4, "draw": 0, "win_pct": 0.556}}
        self.assertEqual(answers.games_text(r, {}), "5승 4패 · 승률 .556")
        self.assertEqual(answers.games_text({"total": 3}, {"result": "승"}), "이긴 경기는 3경기예요.")

    def test_stats_metrics_from_result_only(self):
        r = {"name": "김도영", "season": 2025, "batting": {"avg": 0.3091, "hr": 7, "pa": 122, "qualified": False}, "pitching": None}
        self.assertEqual(answers.stats_text(r, ["타율", "홈런"], AS_OF), "김도영 2025 시즌 타율 .309 · 홈런 7개\n규정 타석 미달 (122타석)")

    def test_stats_missing_metric_says_not_stored(self):
        r = {"name": "원태인", "season": 2025, "batting": None, "pitching": {"so": 108, "outs": 499, "whip": 1.1062}}
        text = answers.stats_text(r, ["평균자책점", "삼진", "이닝"], AS_OF)
        self.assertIn("삼진 108개", text)
        self.assertIn("이닝 166⅓이닝", text)
        self.assertIn("평균자책점은 BASE:ON에 없는 기록이에요.", text)

    def test_current_season_label(self):
        self.assertEqual(answers.season_label(2026, AS_OF), "2026 시즌(7월 26일까지)")
        self.assertEqual(answers.season_label(2025, AS_OF), "2025 시즌")

    def test_after_as_of(self):
        self.assertTrue(answers.after_as_of({"date_from": "2026-08-01"}, AS_OF))
        self.assertTrue(answers.after_as_of({"season": 2027}, AS_OF))
        self.assertFalse(answers.after_as_of({"date_from": "2026-07-26"}, AS_OF))
        self.assertFalse(answers.after_as_of({"season": 2026}, AS_OF))


class Limits(unittest.TestCase):
    def test_per_minute_then_recovers(self):
        now = [1_800_000_000.0]
        lim = Limiter(per_min=2, per_day=10, daily_cap=100, clock=lambda: now[0])
        self.assertIsNone(lim.check("a"))
        self.assertIsNone(lim.check("a"))
        self.assertEqual(lim.check("a"), "minute")
        self.assertIsNone(lim.check("b"))  # 다른 IP는 따로
        now[0] += 61
        self.assertIsNone(lim.check("a"))

    def test_daily_cap_is_shared(self):
        lim = Limiter(per_min=10, per_day=10, daily_cap=3, clock=lambda: 1_800_000_000.0)
        for ip in ("a", "b", "c"):
            self.assertIsNone(lim.check(ip))
        self.assertEqual(lim.check("d"), "cap")

    def test_per_day(self):
        now = [1_800_000_000.0]
        lim = Limiter(per_min=100, per_day=2, daily_cap=100, clock=lambda: now[0])
        lim.check("a"); lim.check("a")
        self.assertEqual(lim.check("a"), "day")
        now[0] += 86_400  # 다음 날
        self.assertIsNone(lim.check("a"))


class Json(unittest.TestCase):
    def test_parse_json(self):
        from app.chat.llm import parse_json
        self.assertEqual(parse_json('```json\n{"menu": "pa"}\n```'), {"menu": "pa"})
        self.assertEqual(parse_json('답: {"menu": "pa"} 끝'), {"menu": "pa"})
        self.assertIsNone(parse_json('{"people": {"batter": "\\ucc\\uc2a4"}}'))  # 잘린 글자 코드 → 다시 묻는다


class Prompt(unittest.TestCase):
    def test_prompt_has_no_real_yesterday(self):  # 기준일 뒤 날짜 예시는 0건이 나와서 뺐다
        self.assertNotIn("어제 한화", prompts.parse_system(AS_OF))
        self.assertIn(AS_OF, prompts.parse_system(AS_OF))

    def test_metrics_in_prompt(self):  # 없는 지표(평균자책점)도 이름으로 받아야 「없는 기록」이라고 답한다
        s = prompts.parse_system(AS_OF)
        for m in terms.MISSING_METRICS + ["타율", "WHIP"]:
            self.assertIn(m, s)


if __name__ == "__main__":
    unittest.main()
