"""
09. 장면 없는 홈런의 「제안 시각」을 Gemini로 찾는다 (docs/장면.md 11-5) — 관리자 「수동 표시」가 이 제안을 채운 채 연다

    docker compose run --rm etl etl/09_suggest_times.py --season 2026 --videos 10 --no-load   # 시험: 파일에만
    docker compose run --rm etl etl/09_suggest_times.py --season 2026 --videos 30             # 판독 + DB에 제안 저장
    docker compose run --rm etl etl/09_suggest_times.py --season 2026 --load-only             # 받아 둔 응답으로 제안만 다시 저장

- 대상: 수동 표시 큐(API 11-2)와 같은 조건(정규시즌 홈런 · 확정 장면 없음 · 「영상에 없음」 아님). 장면 없는 홈런이 많은 경기부터
- 묻는 법: 홈런 목록을 주지 않고 「이 하이라이트의 홈런을 모두」 적게 한 뒤(유도 질문 방지), 코드가 그 경기 기록과 대조한다
- 대조: 타자 이름 + 다른 근거(시즌 n호 · 이닝 · 홈런 뒤 점수). 이름 + 근거 1개 이상이 맞고 어긋난 것 없음 = strong,
  이름만 = weak, 근거가 하나라도 어긋나면 버린다. 같은 경기 홈런 시각이 타석 순서와 거꾸로면 weak로 내린다
- 저장: (PlateAppearance)-[:SUGGESTED]->(VideoLink). 화면용 쿼리는 MATCHED_TO만 읽으므로 사용자 화면에 나가지 않는다.
  확정은 사람이 수동 표시 화면에서 미리 보고 한다 (NFR-07)
- 무료 등급: YouTube 영상 입력이 하루 8시간까지라 --hours(기본 7.5)만큼 쓰면 멈춘다. 쓴 양은 videos/gemini/usage.json (미국 태평양 날짜)
- 응답 원본은 videos/gemini/hl/<영상>.json에 남기고, 있으면 다시 부르지 않는다 (멈췄다 다시 돌려도 이어서 한다)
"""
import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import get_driver, run
from gemini import Judge, mmss, parsed

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "videos" / "gemini"
USAGE = OUT / "usage.json"
PROMPT_V = "hr-blind-1"
CONFIRMED = ["auto_confirmed", "approved"]
LEAD, TAIL = 8, 12  # 찍힌 시각은 타격 직후 → 시작 = t − 8초, 끝 = t + 12초 (장면.md 11-2)

S = lambda **p: {"type": "OBJECT", "properties": p}  # noqa: E731
STR, INT = {"type": "STRING", "nullable": True}, {"type": "INTEGER", "nullable": True}
SCHEMA = S(home_runs={"type": "ARRAY", "items": S(
    batter=STR, evidence={"type": "ARRAY", "items": {"type": "STRING"}}, team=STR, season_hr_no=INT,
    inning=INT, half=STR, score_after={**S(away_team=STR, away=INT, home_team=STR, home=INT), "nullable": True},
    pitcher=STR, time=STR)})
PROMPT = """이 영상은 KBO(한국 프로야구) 경기 하이라이트입니다. 영상에 나오는 홈런 장면을 빠짐없이 모두 찾아 주세요.
화면(중계 점수판, 자막 그래픽, 유니폼 이름·등번호)과 음성(중계 해설)에서 실제로 보이거나 들린 것만 적고, 보이지 않으면 null로 두세요.
제목이나 상식으로 추측하지 마세요. 같은 홈런의 다시 보기(리플레이)는 한 번만 적으세요.
홈런마다:
- batter: 홈런 친 타자 이름 (한글)
- evidence: 이름을 어디서 확인했는지 목록 (scoreboard, caption, commentary, jersey 중)
- team: 타자 팀
- season_hr_no: 화면이나 해설에 나온 「시즌 N호」
- inning, half: 이닝 숫자와 초/말
- score_after: 홈런 직후 점수판 점수 {away_team, away, home_team, home}
- pitcher: 상대 투수 이름
- time: 타자가 공을 친 순간의 영상 시각, 「분:초」 문자열 (예: 5:11)"""

Q_GAMES = """
MATCH (pa:PlateAppearance {season: $season, events: 'home_run', game_type: 'regular'})-[:PART_OF]->(g:Game)
WHERE NOT coalesce(pa.no_video, false)
  AND NOT EXISTS { (pa)-[m:MATCHED_TO]->() WHERE m.status IN $confirmed AND coalesce(m.precision, 'scene') = 'scene' }
RETURN g.game_pk AS game_pk, count(pa) AS missing, toString(max(pa.date)) AS date
ORDER BY missing DESC, date DESC
"""
Q_GAME_HRS = """
UNWIND $games AS gpk
MATCH (g:Game {game_pk: gpk})-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance {events: 'home_run'})-[:PART_OF]->(g)
RETURN gpk AS game_pk, home.name AS home, away.name AS away, pa.pa_id AS pa_id, b.name AS batter,
       pa.inning AS inning, pa.inning_half AS half, pa.hr_seq AS hr_seq, pa.at_bat_number AS ab,
       pa.post_home_score AS home_post, pa.post_away_score AS away_post,
       NOT coalesce(pa.no_video, false)
         AND NOT EXISTS { (pa)-[m:MATCHED_TO]->() WHERE m.status IN $confirmed AND coalesce(m.precision, 'scene') = 'scene' } AS missing
ORDER BY gpk, ab
"""
# 화면(API-14 · 11-2)은 rank 1등 하이라이트 하나만 쓰지만, 여기서는 그 영상에 없는 홈런을 다음 하이라이트에서 다시 찾는다
Q_HIGHLIGHTS = """
UNWIND $games AS gpk
MATCH (g:Game {game_pk: gpk})-[h:MATCHED_TO]->(v:VideoLink)
WHERE h.status IN $confirmed AND coalesce(v.playable, true)
RETURN gpk AS game_pk, v.video_id AS video_id, v.duration_sec AS dur, h.rank AS rank
ORDER BY gpk, h.rank
"""
Q_SAVE = """
UNWIND $rows AS r
MATCH (pa:PlateAppearance {pa_id: r.pa_id}), (v:VideoLink {video_id: r.video_id})
MERGE (pa)-[s:SUGGESTED]->(v)
SET s.found = r.found, s.t_sec = r.t_sec, s.start_sec = r.start_sec, s.end_sec = r.end_sec, s.strength = r.strength,
    s.checks = r.checks, s.evidence = r.evidence, s.model = r.model, s.prompt_v = r.prompt_v, s.at = datetime()
"""


# ------------------------------------------------------------------ 무료 등급 하루 8시간
def pt_today() -> str:
    """무료 한도 하루 = 미국 태평양 날짜 (gemini.next_reset와 같은 서머타임 규칙)"""
    now = datetime.now(timezone.utc)
    y = now.year
    dst_start = datetime(y, 3, 8 + (6 - datetime(y, 3, 8).weekday()) % 7, 10, tzinfo=timezone.utc)
    dst_end = datetime(y, 11, 1 + (6 - datetime(y, 11, 1).weekday()) % 7, 9, tzinfo=timezone.utc)
    return (now + timedelta(hours=-7 if dst_start <= now < dst_end else -8)).strftime("%Y-%m-%d")


def used_sec() -> float:
    return json.load(open(USAGE, encoding="utf-8")).get(pt_today(), 0) if USAGE.exists() else 0


def add_used(sec: float):
    d = json.load(open(USAGE, encoding="utf-8")) if USAGE.exists() else {}
    d[pt_today()] = d.get(pt_today(), 0) + sec
    json.dump(d, open(USAGE, "w", encoding="utf-8"), indent=1)


# ------------------------------------------------------------------ 대조
def given(name: str) -> str:
    return name[1:] if len(name) == 3 else name


def name_hit(said: str | None, real: str) -> bool:
    return bool(said) and (real in said or said in real or given(real) in said)


def half_of(s: str | None) -> str | None:
    s = (s or "").strip().lower()
    return {"t": "초", "b": "말", "초": "초", "말": "말"}.get(s[:1]) if s else None


def compare(h: dict, pa: dict) -> tuple[str, list[str]] | None:
    """판독 홈런 하나 vs 기록 홈런 하나 → ('strong' | 'weak' | 'conflict', 맞은 근거) · 이름이 다르면 None"""
    if not name_hit(h.get("batter"), pa["batter"]):
        return None
    ok, bad = [], []
    if h.get("season_hr_no") is not None:
        (ok if h["season_hr_no"] == pa["hr_seq"] else bad).append("n호")
    if h.get("inning") is not None:
        half = half_of(h.get("half"))
        (ok if h["inning"] == pa["inning"] and (half is None or half == pa["half"]) else bad).append("이닝")
    sa = h.get("score_after") or {}
    if sa.get("away") is not None and sa.get("home") is not None:
        # 중계사마다 원정 · 홈 순서가 달라 두 순서 모두 허용 (팀 이름이 있으면 그걸로 맞춤, 장면.md 11-2)
        both = {(sa["away"], sa["home"]), (sa["home"], sa["away"])}
        if sa.get("away_team") and pa["home"] in sa["away_team"]:
            both = {(sa["home"], sa["away"])}
        (ok if (pa["away_post"], pa["home_post"]) in both else bad).append("점수")
    if bad:
        return "conflict", ok
    return ("strong" if ok else "weak"), ok


def assign(hrs: list[dict], pas: list[dict], dur: float | None) -> tuple[dict, int]:
    """기록 홈런마다 판독 홈런 하나(겹치지 않게). 돌려줌: {pa_id: 제안}, 기록과 안 맞는 판독 홈런 수(지어냈을 수 있음)"""
    pairs = []
    for i, h in enumerate(hrs):
        t = mmss(h.get("time"))
        if t is None or t < 0 or (dur and t >= dur):
            continue
        for pa in pas:
            c = compare(h, pa)
            if c and c[0] != "conflict":
                pairs.append((c[0] == "strong", len(c[1]), i, pa["pa_id"], t, c[1], h))
    pairs.sort(key=lambda x: (x[0], x[1]), reverse=True)
    used_h, out = set(), {}
    for strong, _, i, pid, t, ok, h in pairs:
        if i in used_h or pid in out:
            continue
        used_h.add(i)
        out[pid] = {"t_sec": t, "strength": "strong" if strong else "weak", "checks": ok, "evidence": h.get("evidence") or []}
    # 같은 경기 안에서 시각이 타석 순서와 거꾸로면 둘 다 weak
    order = [pa["pa_id"] for pa in pas if pa["pa_id"] in out]
    for a, b in zip(order, order[1:]):
        if out[a]["t_sec"] > out[b]["t_sec"]:
            out[a]["strength"] = out[b]["strength"] = "weak"
    named = {i for i, h in enumerate(hrs) if any(name_hit(h.get("batter"), pa["batter"]) for pa in pas)}
    return out, len(hrs) - len(named | used_h)


# ------------------------------------------------------------------ 실행
def main():
    ap = argparse.ArgumentParser(description="장면 없는 홈런의 제안 시각 (Gemini, 무료 등급)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--videos", type=int, default=10, help="이번에 새로 판독할 하이라이트 수")
    ap.add_argument("--hours", type=float, default=7.5, help="오늘(미국 태평양 날짜) 쓸 영상 길이 상한 — 무료 등급은 8시간")
    ap.add_argument("--no-load", action="store_true", help="파일에만 남기고 DB에 제안을 저장하지 않는다 (시험)")
    ap.add_argument("--load-only", action="store_true", help="새로 부르지 않고 받아 둔 응답으로 제안만 저장")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    driver = get_driver()
    games = run(driver, Q_GAMES, season=a.season, confirmed=CONFIRMED)
    gpks = [g["game_pk"] for g in games]
    hrs_by, hl_by = {}, {}
    for r in run(driver, Q_GAME_HRS, games=gpks, confirmed=CONFIRMED):
        hrs_by.setdefault(r["game_pk"], []).append(r)
    for r in run(driver, Q_HIGHLIGHTS, games=gpks, confirmed=CONFIRMED):
        hl_by.setdefault(r["game_pk"], []).append(r)
    print(f"{a.season} 장면 없는 홈런 {sum(g['missing'] for g in games)}개 · 경기 {len(games)}개 · "
          f"오늘 쓴 영상 {used_sec() / 3600:.1f}시간 / {a.hours}시간")

    judge = None if a.load_only else Judge(OUT / "hl", sleep=6.0)
    rows, stats, new = [], {"videos": 0, "record_hrs": 0, "found": 0, "invented": 0, "strong": 0, "weak": 0, "absent": 0}, 0
    stop = False
    for g in games:
        if stop:
            break
        pas = hrs_by.get(g["game_pk"], [])
        left = {pa["pa_id"] for pa in pas if pa["missing"]}
        found_any, tried = {}, []
        for hl in hl_by.get(g["game_pk"], []):
            if not left - set(found_any):
                break
            cache = OUT / "hl" / f"hl_{hl['video_id']}.json"
            if not cache.exists():
                if a.load_only:
                    break
                if new >= a.videos:
                    stop = True
                    break
                if used_sec() + (hl["dur"] or 900) > a.hours * 3600:
                    print(f"오늘 무료 한도({a.hours}시간)에 닿아 멈춤 — 내일(미국 태평양 자정 뒤) 다시 돌리면 이어서 한다")
                    stop = True
                    break
                res = judge.ask(f"hl_{hl['video_id']}", hl["video_id"], PROMPT, SCHEMA)
                if res.get("status") != 200:
                    print("  ", hl["video_id"], "판독 실패", res.get("status"), str(res.get("body"))[:120])
                    continue
                add_used(hl["dur"] or 0)
                new += 1
            res = json.load(open(cache, encoding="utf-8"))
            hrs = (parsed(res) or {}).get("home_runs") or []
            got, invented = assign(hrs, pas, hl["dur"])
            tried.append(hl)
            stats["videos"] += 1
            stats["record_hrs"] += len(pas)
            stats["found"] += len(got)
            stats["invented"] += invented
            for pid, s in got.items():
                if pid in left and pid not in found_any:
                    found_any[pid] = s
                    t = s["t_sec"]
                    rows.append({"pa_id": pid, "video_id": hl["video_id"], "found": True, "t_sec": t,
                                 "start_sec": int(max(0, t - LEAD)), "end_sec": int(min(hl["dur"] or t + TAIL, t + TAIL)),
                                 "strength": s["strength"], "checks": "·".join(s["checks"]),
                                 "evidence": ",".join(s["evidence"]), "model": res.get("model"), "prompt_v": PROMPT_V})
                    stats[s["strength"]] += 1
        # 이 경기 하이라이트를 다 봤는데도 못 찾은 홈런 = 「영상에 없음」 후보 (사람이 확인)
        if tried and len(tried) == len(hl_by.get(g["game_pk"], [])):
            for pid in left - set(found_any):
                rows.append({"pa_id": pid, "video_id": tried[0]["video_id"], "found": False, "t_sec": None, "start_sec": None,
                             "end_sec": None, "strength": None, "checks": "", "evidence": "", "model": None, "prompt_v": PROMPT_V})
                stats["absent"] += 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    with open(OUT / f"suggest_{a.season}_{stamp}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"판독한 하이라이트 {stats['videos']}개(새로 {new}개) · 그 경기 기록 홈런 {stats['record_hrs']}개 중 찾음 {stats['found']}개 · "
          f"기록과 안 맞는 판독 {stats['invented']}개")
    print(f"장면 없는 홈런 제안: 강함 {stats['strong']} · 약함 {stats['weak']} · 영상에 없음 후보 {stats['absent']}")
    if not a.no_load and rows:
        run(driver, Q_SAVE, rows=rows)
        print(f"DB에 제안 {len(rows)}개 저장 (SUGGESTED)")
    driver.close()


if __name__ == "__main__":
    main()
