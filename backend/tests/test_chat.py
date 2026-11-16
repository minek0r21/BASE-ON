"""
챗봇 조회 API 테스트 (1단계). 켜져 있는 API에 실제로 요청한다.
    docker compose exec api python -m unittest tests.test_chat -v
"""
import json
import os
import unittest
import urllib.error
import urllib.parse
import urllib.request

BASE = os.getenv("BASEON_API", "http://127.0.0.1:8000").rstrip("/") + "/api/v1"


def req(method, path, body=None, query=None):
    url = BASE + path + (f"?{urllib.parse.urlencode(query)}" if query else "")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=60) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def pid(name, role=None):
    s, d = req("GET", "/chat/players", query={"name": name, **({"role": role} if role else {})})
    assert s == 200 and d["candidates"], (name, d)
    return d["candidates"][0]["player_id"]


def up() -> bool:
    """켜져 있는 API에 챗봇 라우터가 있나 (CI에는 DB · API가 없어서 건너뛴다)"""
    try:
        return req("GET", "/chat/status")[0] == 200
    except (OSError, ValueError):
        return False


@unittest.skipUnless(up(), f"챗봇 API가 꺼져 있다 ({BASE})")
class ChatSearch(unittest.TestCase):
    def test_players_many(self):  # 성 없이 → 여러 명
        s, d = req("GET", "/chat/players", query={"name": "민혁"})
        self.assertEqual(s, 200)
        self.assertEqual(d["status"], "many")

    def test_kim_doyoung_hr_vs_moon(self):  # 김도영이 문동주 상대로 친 홈런
        s, d = req("POST", "/chat/search/pa", {"batter_id": pid("김도영", "batter"), "pitcher_id": pid("문동주", "pitcher"),
                                                "results": ["홈런"], "game_type": "all"})
        self.assertEqual(s, 200, d)
        self.assertTrue(all(r["events"] == "home_run" for r in d["rows"]))
        print("\n 김도영 vs 문동주 홈런:", d["total"], [(r["date"], r["inning"], r["inning_half"], bool(r["video"])) for r in d["rows"]])

    def test_kim_doyoung_triple_jamsil(self):  # 김도영 잠실 3루타
        s, d = req("POST", "/chat/search/pa", {"batter_id": pid("김도영", "batter"), "results": ["3루타"], "stadium": "잠실"})
        self.assertEqual(s, 200, d)
        self.assertTrue(all(r["home"] in ("LG", "두산") and r["events"] == "triple" for r in d["rows"]))
        print("\n 김도영 잠실 3루타:", d["total"], [r["date"] for r in d["rows"]], d["conditions"])

    def test_long_hits_bases_loaded(self):  # 만루 장타
        s, d = req("POST", "/chat/search/pa", {"bat_team": "기아", "results": ["장타"], "bases": "만루", "season": 2025})
        self.assertEqual(s, 200, d)
        self.assertTrue(all(r["on_1b"] and r["on_2b"] and r["on_3b"] for r in d["rows"]))

    def test_bad_term(self):
        s, d = req("POST", "/chat/search/pa", {"bat_team": "KIA", "results": ["안타비슷한거"]})
        self.assertEqual(s, 400)

    def test_games_starter_vs_lg(self):  # KIA가 올러 선발일 때 LG 상대
        s, d = req("POST", "/chat/search/games", {"team": "기아", "opponent": "LG", "starter_id": pid("올러", "pitcher"), "game_type": "all"})
        self.assertEqual(s, 200, d)
        print("\n KIA 올러 선발 vs LG:", d["record"], [(r["date"], r["team_score"], r["opp_score"], r["result"]) for r in d["rows"]])

    def test_games_together(self):  # 두 선수가 같이 뛴 날
        s, d = req("POST", "/chat/search/games", {"team": "KIA", "player_ids": [pid("김도영", "batter"), pid("나성범", "batter")], "result": "승", "season": 2025})
        self.assertEqual(s, 200, d)
        self.assertTrue(all(r["result"] == "승" for r in d["rows"]))
        print("\n 김도영·나성범 같이 뛴 2025 KIA:", d["record"], d["total"])

    def test_hr_2024_nonzero(self):  # 김도영 2024 홈런은 있어야 한다 (0이면 DB 적재나 조회문 문제)
        s, d = req("POST", "/chat/search/pa", {"batter_id": pid("김도영", "batter"), "results": ["홈런"], "season": 2024})
        self.assertEqual(s, 200, d)
        self.assertGreater(d["total"], 0, d)
        print("\n 김도영 2024 홈런:", d["total"], "개, 영상 있는 것", sum(bool(r["video"]) for r in d["rows"]), "/", d["shown"])

    def test_kia_2025_games_nonzero(self):  # KIA 2025 정규시즌은 144경기 안팎
        s, d = req("POST", "/chat/search/games", {"team": "KIA", "season": 2025})
        self.assertEqual(s, 200, d)
        self.assertGreater(d["total"], 100, d)
        print("\n KIA 2025:", d["record"], d["total"], "경기")

    def test_pitcher_stats(self):  # 투수 시즌 기록 (HAS_PITCHING_STAT)
        s, d = req("GET", "/chat/stats", query={"player_id": pid("원태인", "pitcher"), "season": 2025})
        self.assertEqual(s, 200, d)
        self.assertIsNotNone(d["pitching"], d)

    def test_pitch_alias(self):  # 「포심」은 DB의 「직구」로
        s, d = req("POST", "/chat/search/pa", {"batter_id": pid("김도영", "batter"), "results": ["홈런"], "season": 2024, "pitch_names": ["포심"]})
        self.assertEqual(s, 200, d)
        self.assertTrue(all(r["pitch"] == "직구" for r in d["rows"]))
        print("\n 김도영 2024 직구 홈런:", d["total"])

    def test_status(self):  # 화면이 💬 버튼을 그릴지 · 기준일
        s, d = req("GET", "/chat/status")
        self.assertEqual(s, 200, d)
        self.assertIsInstance(d["enabled"], bool)
        self.assertRegex(d["as_of"], r"^\d{4}-\d{2}-\d{2}$")

    def test_default_regular_season_is_shown(self):  # 기본값(정규시즌)도 🔍 줄에 나온다
        s, d = req("POST", "/chat/search/pa", {"batter_id": pid("레이예스", "batter"), "bases": "득점권", "outs": 2, "season": 2025})
        self.assertEqual(s, 200, d)
        self.assertIn("정규시즌", d["conditions"])
        self.assertEqual(d["total"], 78)  # pa.on_2b IS NOT NULL로 세면 236 — 주자 칸은 true/false라 값으로 비교해야 한다

    def test_stats(self):
        s, d = req("GET", "/chat/stats", query={"player_id": pid("김도영", "batter"), "season": 2025})
        self.assertEqual(s, 200, d)
        self.assertIsNotNone(d["batting"])


if __name__ == "__main__":
    unittest.main()
