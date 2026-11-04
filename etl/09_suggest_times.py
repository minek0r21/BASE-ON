"""
09. 장면 없는 홈런의 「제안 시각」을 Gemini로 찾는다 (docs/장면.md 11-5) — 관리자 「수동 표시」가 이 제안을 채운 채 연다

    docker compose run --rm etl etl/09_suggest_times.py --season 2026 --videos 10 --no-load   # 시험: 파일에만
    docker compose run --rm etl etl/09_suggest_times.py --season 2026 --videos 30 --usd 3     # 판독 + DB에 제안 저장
    docker compose run --rm etl etl/09_suggest_times.py --season 2026 --load-only             # 받아 둔 응답으로 제안만 다시 저장

- 대상: 수동 표시 큐(API 11-2)와 같은 조건(정규시즌 홈런 · 확정 장면 없음 · 「영상에 없음」 아님). 장면 없는 홈런이 많은 경기부터
- 묻는 법: 홈런 목록을 주지 않고 「이 하이라이트의 홈런을 모두」 적게 한 뒤(유도 질문 방지), 코드가 그 경기 기록과 대조한다
- 대조(reading.py): 타자 이름 + 다른 근거(시즌 n호 · 이닝 · 홈런 뒤 점수). 이름 + 근거 1개 이상이 맞고 어긋난 것 없음 = strong,
  이름만 = weak, 근거가 하나라도 어긋나면 버린다. 같은 경기 홈런 시각이 타석 순서와 거꾸로면 weak로 내린다
- 저장: (PlateAppearance)-[:SUGGESTED]->(VideoLink). 화면용 쿼리는 MATCHED_TO만 읽으므로 사용자 화면에 나가지 않는다.
  확정은 사람이 수동 표시 화면에서 미리 보고 한다 (NFR-07)
- 비용: 11-04부터 유료(선불). --usd(기본 3)만큼 쓰면 멈춘다. 쓴 돈은 videos/gemini/spend.jsonl (gemini.py)
- 응답 원본은 videos/gemini/hl/hl_<영상>.<프롬프트 버전>.json에 남기고, 있으면 다시 부르지 않는다 (멈췄다 다시 돌려도 이어서 한다)
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from common import get_driver, run
from gemini import Judge, OverBudget, parsed, spent_total
from reading import HR_ITEM, RULES, S, STR, assign

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "videos" / "gemini"
PROMPT_V = "hr-blind-1"
CONFIRMED = ["auto_confirmed", "approved"]
LEAD, TAIL = 8, 12  # 찍힌 시각은 타격 직후 → 시작 = t − 8초, 끝 = t + 12초 (장면.md 11-2)

SCHEMA = S(home_runs={"type": "ARRAY", "items": S(**HR_ITEM, time=STR)})
PROMPT = ("이 영상은 KBO(한국 프로야구) 경기 하이라이트입니다. 영상에 나오는 홈런 장면을 빠짐없이 모두 찾아 주세요.\n" + RULES
          + "\n- time: 타자가 공을 친 순간의 영상 시각, 「분:초」 문자열 (예: 5:11)")

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


# ------------------------------------------------------------------ 실행
def main():
    ap = argparse.ArgumentParser(description="장면 없는 홈런의 제안 시각 (Gemini)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--videos", type=int, default=10, help="이번에 새로 판독할 하이라이트 수")
    ap.add_argument("--usd", type=float, default=3.0, help="이번 실행에서 쓸 돈 상한(달러) — 하이라이트 하나 약 $0.07")
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
          f"지금까지 쓴 돈 ${spent_total():.2f} · 이번 상한 ${a.usd:.2f}")

    judge = None if a.load_only else Judge(OUT / "hl", sleep=6.0, usd=a.usd)
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
            key = f"hl_{hl['video_id']}.{PROMPT_V}"
            cache = OUT / "hl" / f"{key}.json"
            if not cache.exists():
                if a.load_only:
                    break
                if new >= a.videos:
                    stop = True
                    break
                try:
                    res = judge.ask(key, hl["video_id"], PROMPT, SCHEMA)
                except OverBudget as e:
                    print(e, "— 다시 돌리면 이어서 한다")
                    stop = True
                    break
                if res.get("status") != 200:
                    print("  ", hl["video_id"], "판독 실패", res.get("status"), str(res.get("body"))[:120])
                    continue
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
    print(f"장면 없는 홈런 제안: 강함 {stats['strong']} · 약함 {stats['weak']} · 영상에 없음 후보 {stats['absent']}"
          + (f" · 이번에 쓴 돈 ${judge.spent:.2f}" if judge else ""))
    if not a.no_load and rows:
        run(driver, Q_SAVE, rows=rows)
        print(f"DB에 제안 {len(rows)}개 저장 (SUGGESTED)")
    driver.close()


if __name__ == "__main__":
    main()
