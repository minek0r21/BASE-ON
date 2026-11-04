"""
10. 자동 확정 클립이 정말 그 타석인지 Gemini로 확인한다 (docs/장면.md 11-6) — NFR-07 오매칭 측정에서 사람이 어디를 볼지 고른다

    docker compose run --rm etl etl/10_check_clips.py --limit 10 --no-load      # 시험: 10개만 판독, 파일에만
    docker compose run --rm etl etl/10_check_clips.py --usd 6                    # 표본 300개 판독 + DB에 저장
    docker compose run --rm etl etl/10_check_clips.py --pending --usd 2          # 검수 대기 홈런 클립도
    docker compose run --rm etl etl/10_check_clips.py --load-only                # 받아 둔 응답으로 판정만 다시

- 표본(NFR-07): 그 시즌 정규시즌 홈런의 자동 확정 장면 연결을 (pa_id|video_id) 해시 순으로 세운 앞 300개.
  관리자 「NFR-07 표본」(admin.py nfr07_sample)과 같은 규칙이다. 사람이 맞음 · 틀림을 눌러 상태가 바뀐 연결(reviewed_from)도 표본에 남는다
- 묻는 법: 09와 같다. 타석 정보를 주지 않고 「이 클립의 홈런을 모두」 적게 한 뒤, 코드가 연결된 타석과 대조한다(reading.verdict)
- 판정: match2 · match1 · name_only · conflict · other · none. 사람은 match2가 아닌 것 전부 + match2 앞 20개를 본다
- 대조군: 같은 클립 판독을 같은 타자의 다른 홈런 타석(가까운 n호)과 대조한다. 틀린 연결을 conflict로 잡는지 본다 (Gemini를 다시 부르지 않는다)
- 저장: (PlateAppearance)-[:CHECKED]->(VideoLink). 사용자 화면은 읽지 않는다 (관리자만 — test_api 경계 시험)
- 응답 원본은 videos/gemini/clip/clip_<영상>.<프롬프트 버전>.json, 요약은 videos/gemini/check_<시즌>_<시각>.json
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from common import get_driver, run
from gemini import Judge, OverBudget, parsed, spent_total
from reading import HR_ITEM, RULES, S, verdict

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "videos" / "gemini"
PROMPT_V = "clip-blind-1"
SAMPLE, SPOT = 300, 20  # NFR-07 표본 수 · 근거 2개↑ 쪽에서 사람이 보는 수 (장면.md 11-6)
TOK_PER_SEC, USD_PER_CLIP_OUT = 100, 0.006  # 비용 어림: 낮은 해상도 1초 ≈ 100토큰, 출력 약 1.5천 토큰

SCHEMA = S(home_runs={"type": "ARRAY", "items": S(**HR_ITEM)})
PROMPT = ("이 영상은 KBO(한국 프로야구) 경기 장면 클립입니다. 영상에 나오는 홈런 장면을 모두 찾아 주세요. "
          "홈런이 없으면 빈 목록으로 두세요.\n" + RULES)

PA_FIELDS = """pa.pa_id AS pa_id, b.player_id AS batter_id, b.name AS batter, pa.inning AS inning, pa.hr_seq AS hr_seq,
       pa.post_home_score AS home_post, pa.post_away_score AS away_post, home.name AS home, away.name AS away"""
Q_LINKS = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance {season: $season, events: 'home_run', game_type: 'regular'})-[m:MATCHED_TO]->(v:VideoLink)
WHERE coalesce(m.precision, 'scene') = 'scene' AND coalesce(v.playable, true)
  AND CASE $role WHEN 'sample' THEN m.status = 'auto_confirmed' OR m.reviewed_from = 'auto_confirmed'
                 ELSE m.status = 'pending' END
MATCH (pa)-[:PART_OF]->(g:Game)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
RETURN v.video_id AS video_id, v.duration_sec AS dur, toString(pa.date) AS date, """ + PA_FIELDS
# 대조군 후보: 같은 타자의 그 시즌 다른 홈런 (그 영상에 연결된 타석은 뺀다 — 연타석 클립이면 진짜로 같이 나온다)
Q_OTHERS = """
UNWIND $batters AS bid
MATCH (b:Player {player_id: bid})-[:BATTED_IN]->(pa:PlateAppearance {season: $season, events: 'home_run', game_type: 'regular'})
MATCH (pa)-[:PART_OF]->(g:Game)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
RETURN [(pa)-[:MATCHED_TO|CANDIDATE]->(x:VideoLink) | x.video_id] AS videos, """ + PA_FIELDS
Q_SAVE = """
UNWIND $rows AS r
MATCH (pa:PlateAppearance {pa_id: r.pa_id}), (v:VideoLink {video_id: r.video_id})
MERGE (pa)-[c:CHECKED]->(v)
SET c.scene = 'hr', c.role = r.role, c.verdict = r.verdict, c.checks = r.checks, c.conflicts = r.conflicts,
    c.read_batter = r.read_batter, c.read_hr_no = r.read_hr_no, c.read_inning = r.read_inning, c.read_score = r.read_score,
    c.evidence = r.evidence, c.model = r.model, c.prompt_v = r.prompt_v, c.at = datetime()
"""


def sample_order(rows: list[dict]) -> list[dict]:
    """표본 순서 = (pa_id|video_id) 해시 순 (admin.py와 같은 규칙)"""
    return sorted(rows, key=lambda r: hashlib.sha1(f"{r['pa_id']}|{r['video_id']}".encode()).hexdigest())


def control_for(link: dict, others: list[dict]) -> dict | None:
    """같은 타자의 다른 홈런 중 n호가 가장 가까운 것 (그 영상에 연결된 타석은 뺀다)"""
    cands = [o for o in others if o["batter_id"] == link["batter_id"] and o["pa_id"] != link["pa_id"]
             and link["video_id"] not in o["videos"] and o["hr_seq"] is not None and link["hr_seq"] is not None]
    return min(cands, key=lambda o: (abs(o["hr_seq"] - link["hr_seq"]), o["hr_seq"]), default=None)


def score_text(h: dict | None) -> str | None:
    sa = (h or {}).get("score_after") or {}
    if sa.get("away") is None or sa.get("home") is None:
        return None
    return f"{sa.get('away_team') or '원정'} {sa['away']} : {sa['home']} {sa.get('home_team') or '홈'}"


def main():
    ap = argparse.ArgumentParser(description="자동 확정 클립 확인 판독 (Gemini, NFR-07 표본)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--pending", action="store_true", help="표본 대신 검수 대기 홈런 클립을 판독")
    ap.add_argument("--limit", type=int, default=SAMPLE, help="이번에 새로 판독할 클립 수")
    ap.add_argument("--usd", type=float, default=6.0, help="이번 실행에서 쓸 돈 상한(달러) — 클립 하나 약 $0.015")
    ap.add_argument("--no-load", action="store_true", help="파일에만 남기고 DB에 저장하지 않는다 (시험)")
    ap.add_argument("--load-only", action="store_true", help="새로 부르지 않고 받아 둔 응답으로 판정만 다시 저장")
    a = ap.parse_args()
    role = "pending" if a.pending else "sample"

    driver = get_driver()
    links = run(driver, Q_LINKS, season=a.season, role=role)
    links = sample_order(links)[:SAMPLE] if role == "sample" else sorted(links, key=lambda r: r["date"], reverse=True)
    cache = lambda vid: OUT / "clip" / f"clip_{vid}.{PROMPT_V}.json"  # noqa: E731
    todo = list(dict.fromkeys(r["video_id"] for r in links if not cache(r["video_id"]).exists()))
    dur = {r["video_id"]: r["dur"] or 120 for r in links}
    est = sum(dur[v] * TOK_PER_SEC / 1e6 * 0.75 + USD_PER_CLIP_OUT for v in todo[:a.limit])
    print(f"{a.season} {'검수 대기' if a.pending else 'NFR-07 표본'} 연결 {len(links)}개 · 새로 판독할 클립 {len(todo)}개 "
          f"(이번 {min(len(todo), a.limit)}개, 어림 ${est:.2f}) · 지금까지 쓴 돈 ${spent_total():.2f} · 이번 상한 ${a.usd:.2f}")

    judge = None
    if not a.load_only and todo and a.limit > 0:
        judge = Judge(OUT / "clip", sleep=2.0, usd=a.usd)
        for i, vid in enumerate(todo[:a.limit], 1):
            try:
                res = judge.ask(f"clip_{vid}.{PROMPT_V}", vid, PROMPT, SCHEMA)
            except OverBudget as e:
                print(e, "— 다시 돌리면 이어서 한다")
                break
            if res.get("status") != 200:
                print("  ", vid, "판독 실패", res.get("status"), str(res.get("body"))[:120])
            if i % 20 == 0:
                print(f"   {i}개 판독 · 이번에 쓴 돈 ${judge.spent:.2f}", flush=True)

    rows, ctl = [], Counter()
    others = run(driver, Q_OTHERS, season=a.season, batters=list({r["batter_id"] for r in links})) if role == "sample" else []
    for r in links:
        p = cache(r["video_id"])
        if not p.exists():
            continue
        res = json.load(open(p, encoding="utf-8"))
        hrs = (parsed(res) or {}).get("home_runs")
        v = verdict(hrs, r)
        h = v["read"] or {}
        rows.append({"pa_id": r["pa_id"], "video_id": r["video_id"], "role": role, "verdict": v["verdict"],
                     "checks": "·".join(v["checks"]), "conflicts": "·".join(v["conflicts"]),
                     "read_batter": h.get("batter"), "read_hr_no": h.get("season_hr_no"), "read_inning": h.get("inning"),
                     "read_score": score_text(h), "evidence": ",".join(h.get("evidence") or []),
                     "model": res.get("model"), "prompt_v": PROMPT_V})
        if role == "sample":
            c = control_for(r, others)
            ctl[verdict(hrs, c)["verdict"] if c else "no_control"] += 1

    got = Counter(r["verdict"] for r in rows)
    print(f"판정 {len(rows)}개: " + " · ".join(f"{k} {got[k]}" for k in ["match2", "match1", "name_only", "conflict", "other", "none"]))
    if role == "sample":
        m2 = [r for r in sample_order(rows) if r["verdict"] == "match2"]
        print(f"사람이 볼 것: match2가 아닌 것 {len(rows) - len(m2)}개 + match2 앞 {min(SPOT, len(m2))}개")
        # 대조군: 틀린 연결(같은 타자 다른 홈런)이면 conflict가 나와야 한다. match1 · match2 = 놓침
        print("대조군(같은 타자 다른 홈런): 잡음(conflict) {} · 놓침(match1·2) {} · 판단 못 함(name_only) {} · 기타 {}".format(
            ctl["conflict"], ctl["match1"] + ctl["match2"], ctl["name_only"],
            sum(ctl.values()) - ctl["conflict"] - ctl["match1"] - ctl["match2"] - ctl["name_only"]))
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    json.dump({"season": a.season, "role": role, "prompt_v": PROMPT_V, "verdicts": got, "controls": ctl,
               "spent_usd": round(judge.spent, 4) if judge else 0, "rows": rows},
              open(OUT / f"check_{a.season}_{role}_{stamp}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if judge:
        print(f"이번에 쓴 돈 ${judge.spent:.2f} · 지금까지 ${spent_total():.2f}")
    if not a.no_load and rows:
        run(driver, Q_SAVE, rows=rows)
        print(f"DB에 판정 {len(rows)}개 저장 (CHECKED)")
    driver.close()


if __name__ == "__main__":
    main()
