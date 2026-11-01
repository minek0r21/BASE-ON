"""
API 테스트 — 표준 라이브러리 unittest만 쓴다 (pytest로 돌려도 된다).
켜져 있는 API에 실제로 요청을 보낸다. 데이터는 HF 고정본(2024~2026, 7.26까지)을 적재한 DB 기준.

    docker compose exec api python -m unittest discover -s tests -v      # API 컨테이너 안에서 (권장)
    BASEON_API=http://127.0.0.1:8000 python -m unittest discover -s backend/tests -v   # PC에서

API가 꺼져 있으면 통합 테스트는 건너뛴다. 관리자 토큰 검사는 API 없이 함수만 시험한다(fastapi가 있을 때).
"""
import json
import os
import unittest
import urllib.error
import urllib.parse
import urllib.request

BASE = os.getenv("BASEON_API", "http://127.0.0.1:8000").rstrip("/")


def call(method: str, path: str, query: dict | None = None):
    url = f"{BASE}/api/v1{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, None


def up() -> bool:
    try:
        return call("GET", "/health")[0] == 200
    except OSError:
        return False


@unittest.skipUnless(up(), f"API가 꺼져 있다 ({BASE})")
class ApiTest(unittest.TestCase):
    def ok(self, path, query=None):
        status, body = call("GET", path, query)
        self.assertEqual(status, 200, f"{path} {query} → {status} {body}")
        return body

    def error(self, status, code, path, query=None, method="GET"):
        got, body = call(method, path, query)
        self.assertEqual(got, status, f"{path} → {got} {body}")
        self.assertEqual(body["error"]["code"], code)  # 오류 응답 형식 {"error": {"code", "message"}}
        self.assertTrue(body["error"]["message"])

    # ---------------------------------------------------------------- 상태
    def test_meta(self):
        m = self.ok("/meta")
        self.assertEqual(set(m), {"data_as_of", "season", "postseason_active"})
        self.assertEqual(m["data_as_of"], "2026-07-26")  # 고정본 마지막 경기일 (NFR-04)
        self.assertEqual(m["season"], 2026)

    # ---------------------------------------------------------------- 검색 (API-01)
    def test_search(self):
        ids = lambda q: [p["player_id"] for p in self.ok("/players", {"q": q})["players"]]  # noqa: E731
        self.assertIn("52605", ids("김도영"))
        self.assertIn("52605", ids("ㄱㄷㅇ"))  # 초성
        self.assertEqual(ids("이종범"), [])     # 2024~2026 기록 없음 → 빈 목록 (오류 아님)

    # ---------------------------------------------------------------- 선수 (API-02)
    def test_batter_summary(self):
        p = self.ok("/players/52605")
        self.assertEqual(p["name"], "김도영")
        self.assertTrue(p["qualified"])
        self.assertEqual(len(p["percentiles"]), 5)
        self.assertIsNone(p["qualify_pa"])  # 비교 대상이면 기준 없음

    def test_not_qualified_has_threshold(self):
        p = self.ok("/players/56613")  # 아데를린: 130타석, 규정타석 50%(149) 미달
        self.assertFalse(p["qualified"])
        self.assertGreater(p["qualify_pa"], p["stats"]["pa"])

    def test_pitcher_summary(self):
        p = self.ok("/players/54640")  # 네일 (선발)
        self.assertEqual(p["pitching"]["role"], "starter")
        self.assertEqual(len(p["pitching"]["axes"]), 5)

    def test_player_errors(self):
        self.error(404, "PLAYER_NOT_FOUND", "/players/zzz")
        self.error(404, "SEASON_NOT_FOUND", "/players/56613", {"season": 2024})

    # ---------------------------------------------------------------- 비교 (API-11)
    def test_compare(self):
        c = self.ok("/players/compare", {"ids": "52605,56613"})
        self.assertEqual([x["player_id"] for x in c["players"]], ["52605", "56613"])
        # 투수 비교에 타자가 앞에 있어도 비교는 한다 (기록 있는 선수 기준 시즌)
        c = self.ok("/players/compare", {"ids": "52605,54640", "as": "pitcher"})
        self.assertFalse(c["players"][0]["has_stats"])
        self.assertTrue(c["players"][1]["has_stats"])

    def test_compare_errors(self):
        self.error(400, "COMPARE_COUNT", "/players/compare", {"ids": "52605"})
        self.error(400, "COMPARE_COUNT", "/players/compare", {"ids": "52605,56613,54640,61102"})
        self.error(404, "PLAYER_NOT_FOUND", "/players/compare", {"ids": "52605,zzz"})

    # ---------------------------------------------------------------- 경기 (API-14 · 38 · 05)
    def test_day(self):
        d = self.ok("/games", {"date": "2026-07-26"})
        self.assertEqual(len(d["games"]), 5)
        rest = self.ok("/games", {"date": "2026-07-14"})  # 쉬는 날: 경기 0 + 앞뒤 경기일
        self.assertEqual(rest["games"], [])
        self.assertEqual((rest["prev_date"], rest["next_date"]), ("2026-07-09", "2026-07-16"))

    def test_box_and_pa_video(self):
        box = self.ok("/games/20260726WOHT02026/box")
        self.assertTrue(box["home"]["batters"] and box["away"]["pitchers"])
        self.error(404, "GAME_NOT_FOUND", "/games/zzz/box")
        v = self.ok("/plate-appearances/20260726WOHT02026_22/video")  # 김웅빈 7호 — 확정 장면
        self.assertTrue(v["videos"])
        self.assertTrue({"video_id", "start_sec", "end_sec", "precision"} <= set(v["videos"][0]))
        self.error(404, "PA_NOT_FOUND", "/plate-appearances/zzz/video")

    # ---------------------------------------------------------------- 지운 주소 (11-01 정리)
    def test_removed_routes(self):
        for path in ("/video-links", "/video-links/stats", "/standings/history?season=2026", "/outings/x/video"):
            self.assertEqual(call("GET", path)[0], 404, path)


class AdminTokenTest(unittest.TestCase):
    """관리자 토큰 검사 (SEC-01) — ADMIN_TOKENS가 있으면 토큰이 맞아야 하고, 검수자 이름은 토큰으로 정한다"""

    def setUp(self):
        try:
            from app.errors import ApiError
            from app.routers.admin import require_admin
        except ImportError as e:
            self.skipTest(f"백엔드 패키지를 불러올 수 없다 ({e}) — API 컨테이너에서 돌린다")
        self.ApiError, self.require_admin = ApiError, require_admin
        self.saved = os.environ.get("ADMIN_TOKENS")

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("ADMIN_TOKENS", None)
        else:
            os.environ["ADMIN_TOKENS"] = self.saved

    def test_token(self):
        os.environ["ADMIN_TOKENS"] = "성준:secret-1,세라:secret-2"
        self.assertEqual(self.require_admin("Bearer secret-2"), "세라")
        for bad in (None, "", "Bearer wrong", "secret-3"):
            with self.assertRaises(self.ApiError) as e:
                self.require_admin(bad)
            self.assertEqual(e.exception.status, 401)

    def test_no_tokens_is_open(self):  # 로컬 개발: 설정이 없으면 열려 있다 (서버에서는 Caddy가 /admin을 막는다)
        os.environ["ADMIN_TOKENS"] = ""
        self.assertIsNone(self.require_admin(None))


if __name__ == "__main__":
    unittest.main()
