"""
선수 상세 API 응답 시간 (NFR-01: p95 500ms 이하). 표준 라이브러리만 쓴다.

    python scripts/perf_check.py                                  # PC 개발 API (http://127.0.0.1:8000 — Windows에서 localhost는 IPv6를 먼저 찾아 느려진다)
    python scripts/perf_check.py --base http://localhost:8000 --rounds 2

배포 서버는 비밀번호 뒤라, 서버 안 API 컨테이너에서 같은 스크립트를 돌린다(Caddy · 네트워크 제외, API + DB 시간):
    ssh <서버> "cd /opt/baseon/app/deploy && docker compose exec -T api python - --base http://localhost:8000" < scripts/perf_check.py

그 시즌 출전 선수 전원(팀마다 타자 · 투수 목록)을 무작위 순서로 /players/{id}를 한 번씩 부른다.
첫 회는 DB 캐시가 차는 중이라 --rounds 2면 두 번째 회만 따로도 보여 준다.
"""
import argparse
import json
import random
import statistics
import time
import urllib.request

TEAMS = ["KIA", "삼성", "LG", "두산", "KT", "SSG", "롯데", "한화", "NC", "키움"]


def get(base: str, path: str):
    t = time.perf_counter()
    with urllib.request.urlopen(base + "/api/v1" + path, timeout=30) as r:
        body = r.read()
        status = r.status
    return status, (time.perf_counter() - t) * 1000, body


def players(base: str) -> list[str]:
    ids = set()
    for t in TEAMS:
        q = urllib.parse.quote(t)
        for path in (f"/batters?team={q}&qualified=false&limit=500", f"/pitchers?team={q}&qualified=false&limit=1000"):
            data = json.loads(get(base, path)[2])
            ids |= {p["player_id"] for p in data.get("batters", data.get("pitchers", []))}
    return sorted(ids)


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def report(title: str, ms: list[float], errors: int):
    print(f"{title}: {len(ms)}번 · 오류 {errors} · 평균 {statistics.mean(ms):.0f}ms · p50 {pct(ms, 50):.0f}ms · "
          f"p95 {pct(ms, 95):.0f}ms · p99 {pct(ms, 99):.0f}ms · 최대 {max(ms):.0f}ms")


def main():
    import sys
    import urllib.parse  # noqa: F401 — players()에서 쓴다
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 한글이 깨지지 않게
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--seed", type=int, default=20261101)
    ap.add_argument("--limit-ms", type=float, default=500, help="통과 기준 p95 (NFR-01)")
    a = ap.parse_args()

    ids = players(a.base)
    meta = json.loads(get(a.base, "/meta")[2])
    print(f"대상: {a.base} · 기준일 {meta.get('data_as_of')} · 선수 {len(ids)}명 · {a.rounds}회")
    rnd = random.Random(a.seed)
    all_ms, last_ms, errors = [], [], 0
    for k in range(a.rounds):
        order = ids[:]
        rnd.shuffle(order)
        ms = []
        for pid in order:
            try:
                status, t, _ = get(a.base, f"/players/{pid}")
                ms.append(t)
                errors += status != 200
            except Exception:
                errors += 1
        report(f"  {k + 1}회", ms, 0)
        all_ms += ms
        last_ms = ms
    report("전체", all_ms, errors)
    p95 = pct(last_ms, 95)
    print(f"판정 (마지막 회 p95 {p95:.0f}ms ≤ {a.limit_ms:.0f}ms, 오류 0): {'통과' if p95 <= a.limit_ms and not errors else '실패'}")
    raise SystemExit(0 if p95 <= a.limit_ms and not errors else 1)


if __name__ == "__main__":
    main()
