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
        names = lambda q: {p["name"] for p in self.ok("/players", {"q": q})["players"]}  # noqa: E731
        self.assertTrue({"이주형", "이진하", "이정현", "윤정현"} <= names("ㅇㅈㅎ"))  # 상한 없음: 겹치는 초성도 모두
        self.assertIn("코엔 윈", names("ㅋㅇㅇ"))  # 이름의 띄어쓰기는 빼고 맞춘다
        self.assertIn("코엔 윈", names("코엔윈"))
        # 동명이인 · 옛 이름 표시 (FR-01-04): 같은 이름이면 same_name + 출생 연도 · 등번호, 옛 이름으로도 찾는다
        twins = [p for p in self.ok("/players", {"q": "박준영"})["players"] if p["name"] == "박준영"]
        self.assertGreaterEqual(len(twins), 2)
        self.assertTrue(all(p["same_name"] for p in twins))
        self.assertEqual(len({(p["team"], p["position"], p["bats_throws"], p["birth_year"], p["back_number"]) for p in twins}), len(twins))
        hit = self.ok("/players", {"q": "김윤수"})["players"]
        self.assertTrue(any(p["name"] == "김무신" and "김윤수" in p["former_names"] for p in hit))
        self.assertTrue(all(p["name"] not in p["former_names"] for p in self.ok("/players", {"q": "김민수"})["players"]))

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

    def test_standings_history(self):
        h = self.ok("/standings/history", {"season": 2026})
        pts = h["points"]
        self.assertGreater(len(pts), 10)  # 주마다 — 2026은 3월 말 ~ 7.26
        self.assertEqual(pts[-1]["date"], "2026-07-26")
        self.assertTrue(all(len(p["ranks"]) == 10 for p in pts))
        last = {t["team"]: t["rank"] for t in self.ok("/standings", {"season": 2026})["teams"]}
        self.assertEqual(pts[-1]["ranks"], last)  # 마지막 점 = 지금 순위표
        self.error(404, "SEASON_NOT_FOUND", "/standings/history", {"season": 2019})

    # ---------------------------------------------------------------- 지운 주소 (11-01 정리)
    def test_removed_routes(self):
        for path in ("/video-links", "/video-links/stats", "/outings/x/video"):
            self.assertEqual(call("GET", path)[0], 404, path)


class SuggestionBoundaryTest(unittest.TestCase):
    """Gemini 판독(제안 SUGGESTED · 확인 CHECKED)은 관리자 검수만 읽는다 — 사람 판정 전에는 사용자 화면에 나가지 않는다 (장면.md 11-5 · 11-6)"""

    def test_public_code_never_reads_gemini(self):
        import re
        from pathlib import Path
        app = Path(__file__).resolve().parents[1] / "app"
        for rel in ("SUGGESTED", "CHECKED"):  # Cypher 관계 표기 「:CHECKED」만 (Q_MARK_CHECKED 같은 이름은 아니다)
            hits = [str(f.relative_to(app)) for f in app.rglob("*.py")
                    if f.name != "admin.py" and re.search(rf"[:|]\s*{rel}\b", f.read_text(encoding="utf-8"))]
            self.assertEqual(hits, [], rel)


class LedgerTest(unittest.TestCase):
    """사람 판정 장부: 스냅숏을 남기고 다시 적용하면 같은 상태 (DB 없이 — run을 바꿔 끼운다)"""

    def test_record_and_replay(self):
        try:
            from app import ledger
        except ImportError:  # PC에서 backend 패키지 없이 돌릴 때
            self.skipTest("app 패키지 없음 — API 컨테이너 안에서 돌린다")
        import tempfile
        from pathlib import Path
        calls = []

        def fake_run(q, **p):
            calls.append((q, p))
            if "RETURN properties(m)" in q:
                return [{"m": {"status": "approved", "origin": "manual", "start_sec": 30, "end_sec": 50, "reviewer": "민",
                               "reviewed_at": object()}}]  # reviewed_at(날짜 객체)은 장부에 넣지 않는다
            return [{"ok": 1}]

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "decisions.jsonl"
            old_run, old_env = ledger.run, os.environ.get("REVIEW_LEDGER")
            ledger.run, os.environ["REVIEW_LEDGER"] = fake_run, str(p)
            try:
                ledger.record_links("manual", [("pa", "pa1", "vid1")])
                ledger.record_no_video("pa2", "민")
                rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
                self.assertEqual([r["action"] for r in rows], ["manual", "no_video"])
                self.assertEqual(rows[0]["link"]["start_sec"], 30)
                self.assertNotIn("reviewed_at", rows[0]["link"])
                calls.clear()
                self.assertEqual(ledger.replay(), (2, 0))
                self.assertIn("SET m += $link", calls[0][0])
                self.assertEqual(calls[0][1]["link"]["status"], "approved")
            finally:
                ledger.run = old_run
                if old_env is None:
                    os.environ.pop("REVIEW_LEDGER", None)
                else:
                    os.environ["REVIEW_LEDGER"] = old_env


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
        # 화면은 X-Admin-Token — Authorization은 서버 사이트 비밀번호(Basic)가 쓴다
        self.assertEqual(self.require_admin("Basic dXNlcjpwdw==", "secret-1"), "성준")
        for bad in (None, "", "Bearer wrong", "secret-3"):
            with self.assertRaises(self.ApiError) as e:
                self.require_admin(bad)
            self.assertEqual(e.exception.status, 401)

    def test_no_tokens_is_open(self):  # 로컬 개발: 설정이 없으면 열려 있다 (서버에서는 Caddy가 /admin을 막는다)
        os.environ["ADMIN_TOKENS"] = ""
        self.assertIsNone(self.require_admin(None))


class RecheckTest(unittest.TestCase):
    """틀림 다시 보기 — 시작 초를 고쳐 살린 장면도 측정에서는 틀림, 다시 볼 목록에서 처음 누른 사람 것은 뺀다"""

    def setUp(self):
        try:
            from app.routers.admin import _to_recheck, is_wrong
        except ImportError as e:
            self.skipTest(f"백엔드 패키지를 불러올 수 없다 ({e}) — API 컨테이너에서 돌린다")
        self.is_wrong, self.to_recheck = is_wrong, _to_recheck

    def test_is_wrong(self):
        self.assertTrue(self.is_wrong({"status": "rejected"}))
        self.assertTrue(self.is_wrong({"status": "rejected", "recheck": "confirmed"}))
        self.assertTrue(self.is_wrong({"status": "approved", "recheck": "retimed"}))  # 화면엔 살렸지만 자동 연결은 틀렸다
        self.assertFalse(self.is_wrong({"status": "approved", "recheck": "mistake"}))  # 처음 판정이 잘못
        self.assertFalse(self.is_wrong({"status": "approved"}))

    def test_queue(self):
        def row(reviewer, **m):
            return {"m": {"reviewed_from": "auto_confirmed", "moved_to": None, "recheck": None, "reviewer": reviewer, **m}}
        rows = [row("성준"), row("세라"), row("세라", recheck="retimed"), row("세라", moved_to="x"), row("세라", reviewed_from="pending")]
        todo, mine = self.to_recheck(rows, "성준")
        self.assertEqual((len(todo), mine), (1, 1))  # 세라의 틀림 하나만 — 다시 본 것 · 옮김 · 검수 대기 반려는 빠진다
        self.assertEqual(todo[0]["m"]["reviewer"], "세라")


if __name__ == "__main__":
    unittest.main()
