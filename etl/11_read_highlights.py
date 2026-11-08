"""
11. 경기 하이라이트에서 주목 장면(홈런 · 안타 · 삼진)을 시각과 함께 한 번에 읽는다 (docs/장면.md 11-7)

    docker compose run --rm etl etl/11_read_highlights.py --season 2026 --videos 10 --usd 1.5   # 시험: 보고서만
    docker compose run --rm etl etl/11_read_highlights.py --season 2026 --videos 0              # 받아 둔 응답으로 보고서만 다시
    docker compose run --rm etl etl/11_read_highlights.py --season 2026 --videos 0 --load       # 받아 둔 응답으로 장면 연결 저장
    docker compose run --rm etl etl/11_read_highlights.py --season 2026 --videos 0 --sample     # NFR-07 표본 300 뽑아 고정 (한 번만)

- 왜: 선수별 클립은 「멀티 홈런」 · 「백투백」처럼 장면이 섞여 클립 하나가 여러 타석에 0초부터 걸린다(11-6 충돌 22개).
  경기 하이라이트는 경기마다 하나로 정해지고, 장면마다 시작 초를 붙이면 「15초 안에 그 타격」 기준이 저절로 맞는다
- 대상: 그 시즌 정규시즌 경기의 1등 하이라이트(rank 1). 홈런 전용 프롬프트(09, hr-blind-1)로 이미 읽은 영상부터 →
  같은 영상에서 홈런을 옛 판독과 견줘 「한 번에 다 읽어도 홈런이 줄지 않는지」를 본다
- 대조: reading.assign_scenes — 타자 이름 + 종류가 맞아야 후보, 근거 2개↑ 일치 · 어긋남 없음 = strong. 판정은 코드가 한다
- 저장(--load, 11-05 사용자 승인: strong = 자동 확정, 장면.md 11-7):
    홈런 · 안타 strong → (타석)-[:MATCHED_TO {origin: 'highlight', precision: 'scene', rank: 0}]->(하이라이트), 시작 = 친 순간 − 8초
      rank 0 = 클립(rank 1~)보다 먼저 재생 (클립은 0초부터라 15초 기준을 못 지킬 수 있다). 홈런 weak → 검수 대기(highlight_weak)
    삼진 strong → 그 투수 등판의 장면 하나(가장 이른 삼진, tags strikeout, 등판 클립 뒤 · 이닝 챕터 앞). 타자 화면엔 삼진을 안 그린다(S8)
    멀티 홈런 클립(한 클립이 같은 타자 홈런 2개↑에 자동 확정) → 하이라이트 장면이 생긴 타석은 superseded, 없으면 검수 대기(multi_scene_clip)
    사람이 판정한 연결(reviewed_at)은 건드리지 않는다. origin이 auto로 시작하지 않아 08을 다시 돌려도 지워지지 않는다
    (08을 다시 돌리면 멀티 홈런 클립이 자동 확정으로 돌아오므로 11 --load도 다시)
- 표본(--sample): 홈런마다 화면에 나가는 연결(scenes.Q_PA_SCENES와 같은 순서) 중 자동 확정인 것을 (pa_id|video_id) 해시 순 300개 →
  m.nfr07 = 'v2'로 고정. 사람이 전부 본다(판독이 확정을 정했으니 Gemini 확인은 자기 채점이 된다). 이미 있으면 다시 뽑지 않는다
- 비용: 하이라이트 하나 약 $0.08~0.10(평균 15분). --usd만큼 쓰면 멈춘다. 쓴 돈은 videos/gemini/spend.jsonl
- 응답 원본은 videos/gemini/hl/hl_<영상>.<프롬프트 버전>.json (있으면 다시 부르지 않는다)
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from common import get_driver, run
from gemini import Judge, OverBudget, parsed, spent_total
from reading import EVENTS, HITS, SCENE_ITEM, SCENE_RULES, S, assign, assign_scenes, broken

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "videos" / "gemini"
PROMPT_V = "scene-blind-3"  # 1: time 칸을 맨 앞에 둬서 무너짐 · 2: 점수판 없이 이닝 · 점수를 짐작해 채움 → 3 (장면.md 11-7)
# 11-06: 팀 칸은 구단 enum, 시각은 분 · 초 숫자 두 칸으로. 무너진 응답만 이 스키마로 다시 묻고 .r1에 둔다
OLD_V = "hr-blind-1"  # 09의 홈런 전용 판독 — 같은 영상이면 홈런끼리 견준다
CONFIRMED = ["auto_confirmed", "approved"]
LEAD, TAIL = 8, 12  # 시작 = 친 순간 − 8초, 끝 = + 12초 (09와 같음)
USD_PER_VIDEO = 0.10  # 실행 전 어림 (입력 약 8.4만 토큰 + 장면이 늘어난 출력)
SPOT = 15  # 사람이 눌러 볼 안타 · 삼진 장면 수
MIN_SCENES, LONG = 8, 600  # 10분 넘는 하이라이트에 장면이 8개 미만이면 중간에 멈춘 응답 → 한 번 다시 묻는다 (11-05: 10개 중 1개, 1개 적고 멈춤)

MAX_TOKENS = 16000  # 생각 포함. 정상 응답은 6천 안팎
SCHEMA = S(scenes={"type": "ARRAY", "items": {**S(**SCENE_ITEM), "propertyOrdering": list(SCENE_ITEM)}})
PROMPT = ("이 영상은 KBO(한국 프로야구) 경기 하이라이트입니다. 영상에 나오는 홈런 · 안타 · 삼진 장면을 빠짐없이 모두 찾아 주세요.\n"
          + SCENE_RULES)

Q_HIGHLIGHTS = """
MATCH (g:Game {season: $season})-[h:MATCHED_TO]->(v:VideoLink)
WHERE coalesce(g.game_type, 'regular') = 'regular' AND h.status IN $confirmed AND coalesce(h.rank, 1) = 1
  AND coalesce(v.playable, true)
RETURN g.game_pk AS game_pk, v.video_id AS video_id, v.duration_sec AS dur, v.title AS title
"""
Q_PAS = """
UNWIND $games AS gpk
MATCH (g:Game {game_pk: gpk})-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance)-[:PART_OF]->(g)
WHERE pa.events IN $events
OPTIONAL MATCH (p:Player)-[:PITCHED_IN]->(pa)
RETURN gpk AS game_pk, home.name AS home, away.name AS away, pa.pa_id AS pa_id, pa.events AS events, b.name AS batter,
       p.name AS pitcher, p.player_id AS pitcher_id, pa.inning AS inning, pa.outs_when_up AS outs, pa.hr_seq AS hr_seq,
       pa.at_bat_number AS ab, pa.post_home_score AS home_post, pa.post_away_score AS away_post
ORDER BY gpk, ab
"""
# --load: 지난번에 넣은 하이라이트 장면 중 사람이 안 본 것은 지우고 다시 넣는다 (프롬프트 · 규칙이 바뀌어도 같은 결과)
Q_CLEAR = """
MATCH (t:PlateAppearance|Outing {season: $season})-[m:MATCHED_TO {origin: 'highlight'}]->(:VideoLink)
WHERE m.reviewed_at IS NULL
DELETE m
"""
Q_SAVE = """
UNWIND $rows AS r
MATCH (t:{label} {{{key}: r.target_id}}), (v:VideoLink {{video_id: r.video_id}})
MERGE (t)-[m:MATCHED_TO]->(v)
WITH m, r WHERE m.reviewed_at IS NULL AND NOT coalesce(m.status, '') IN ['approved', 'rejected']  // 사람 판정 · 수동 표시는 그대로
SET m.status = r.status, m.origin = 'highlight', m.scene_type = r.scene_type, m.precision = 'scene', m.rank = r.rank,
    m.start_sec = r.start_sec, m.end_sec = r.end_sec, m.t_sec = r.t_sec, m.tags = r.tags, m.score = null,
    m.reasons = r.reasons, m.review_reason = r.review_reason, m.prompt_v = r.prompt_v, m.model = r.model, m.loaded_at = datetime()
RETURN count(*) AS n
"""
# 등판 삼진 장면 순서: 등판 장면 클립(scene) 바로 뒤, 이닝 챕터(inning) 앞. 07은 등판마다 scene → inning 순으로 rank 1, 2, …를 매기므로
# (그 등판 scene 클립의 가장 큰 rank) + 0.5 (클립이 없으면 0.5). 11-05 확인: scene과 inning이 같이 있는 289개 모두 scene rank가 작다
Q_K_RANK = """
MATCH (o:Outing {season: $season})-[k:MATCHED_TO {origin: 'highlight'}]->()
WHERE k.reviewed_at IS NULL
OPTIONAL MATCH (o)-[c:MATCHED_TO]->() WHERE c.precision = 'scene' AND c.origin <> 'highlight' AND c.status IN ['auto_confirmed', 'approved']
WITH k, max(c.rank) AS top
SET k.rank = coalesce(top, 0) + 0.5
"""
# 멀티 홈런 클립: 같은 영상이 같은 타자의 홈런 2개↑에 자동 확정(사람이 안 본 것) → 내림 (장면.md 11-6 · 11-7)
Q_MULTI = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance {season: $season, events: 'home_run', game_type: 'regular'})-[m:MATCHED_TO]->(v:VideoLink)
WHERE m.origin STARTS WITH 'auto' AND coalesce(m.precision, 'scene') = 'scene' AND m.reviewed_at IS NULL
  AND (m.status = 'auto_confirmed' OR m.demoted_from = 'auto_confirmed')
WITH b, v, collect({pa: pa, m: m}) AS xs WHERE size(xs) > 1
UNWIND xs AS x
WITH x.pa AS pa, x.m AS m
WITH m, EXISTS { (pa)-[h:MATCHED_TO {origin: 'highlight'}]->() WHERE h.status IN ['auto_confirmed', 'approved'] } AS covered
SET m.demoted_from = 'auto_confirmed', m.status = CASE WHEN covered THEN 'superseded' ELSE 'pending' END,
    m.review_reason = CASE WHEN covered THEN m.review_reason ELSE 'multi_scene_clip' END
RETURN covered, count(*) AS n
"""
# NFR-07 표본: 홈런마다 화면에 나가는 연결 = 확정 · 재생 가능 · 장면 정밀도 중 rank, 올린 날 순 첫째 (backend/app/scenes.py Q_PA_SCENES)
Q_SHOWN = """
MATCH (pa:PlateAppearance {season: $season, events: 'home_run', game_type: 'regular'})
CALL (pa) {
  MATCH (pa)-[m:MATCHED_TO]->(v:VideoLink)
  WHERE m.status IN ['auto_confirmed', 'approved'] AND coalesce(m.precision, 'scene') <> 'game' AND coalesce(v.playable, true)
  RETURN v, m ORDER BY m.rank, v.published_at LIMIT 1
}
RETURN pa.pa_id AS pa_id, v.video_id AS video_id, m.status AS status, m.origin AS origin
"""
Q_MARK = """
UNWIND $rows AS r
MATCH (:PlateAppearance {pa_id: r.pa_id})-[m:MATCHED_TO]->(:VideoLink {video_id: r.video_id})
SET m.nfr07 = 'v2', m.nfr07_i = r.i
"""
NFR07_N = 300


def scenes_of(path: Path, keep_broken: bool = False) -> list[dict] | None:
    items = (parsed(json.load(open(path, encoding="utf-8"))) or {}).get("scenes")
    return items if items is None or keep_broken else [h for h in items if not broken(h)]


def needs_retry(path: Path, dur: float | None) -> bool:
    """못 읽은 응답 · 칸이 무너진 장면이 있는 응답 · 10분 넘는데 장면이 8개 미만(중간에 멈춤)"""
    items = scenes_of(path, keep_broken=True)
    if items is None or any(broken(h) for h in items):
        return True
    return (dur or 0) > LONG and len(items) < MIN_SCENES


def group(kind: str | None) -> str:
    return "hit" if kind in HITS else kind or "?"


def main():
    ap = argparse.ArgumentParser(description="하이라이트 주목 장면 판독 (Gemini)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--videos", type=int, default=10, help="이번에 새로 판독할 하이라이트 수")
    ap.add_argument("--usd", type=float, default=1.5, help="이번 실행에서 쓸 돈 상한(달러)")
    ap.add_argument("--only", nargs="*", help="이 영상 ID만 (프롬프트를 고친 뒤 같은 영상으로 견줄 때)")
    ap.add_argument("--load", action="store_true", help="판독 결과로 장면 연결 저장 (홈런 · 안타 → 타석, 삼진 → 등판)")
    ap.add_argument("--sample", action="store_true", help="NFR-07 표본 300 뽑아 고정 (이미 있으면 그대로)")
    a = ap.parse_args()

    driver = get_driver()
    hls = run(driver, Q_HIGHLIGHTS, season=a.season, confirmed=CONFIRMED)
    if a.only:
        hls = [h for h in hls if h["video_id"] in a.only]
    cache = lambda vid, v=PROMPT_V: OUT / "hl" / f"hl_{vid}.{v}.json"  # noqa: E731
    # 이미 읽은 것 → 옛 판독이 있는 것 → 나머지, 같은 묶음 안에서는 영상 ID 해시 순 (실행마다 같은 순서)
    hls.sort(key=lambda h: (not cache(h["video_id"]).exists(), not cache(h["video_id"], OLD_V).exists(),
                            hashlib.sha1(h["video_id"].encode()).hexdigest()))
    # 무너지거나 중간에 멈춘 응답은 같은 영상을 한 번 더 묻는다 (키 끝 .r1). 다시 물은 것도 이번 --videos 수에 든다
    short = [h for h in hls if cache(h["video_id"]).exists() and not cache(h["video_id"], PROMPT_V + ".r1").exists()
             and needs_retry(cache(h["video_id"]), h["dur"])]
    todo = (short + [h for h in hls if not cache(h["video_id"]).exists()])[:a.videos]
    print(f"{a.season} 하이라이트 {len(hls)}개 · 읽어 둔 것 {sum(cache(h['video_id']).exists() for h in hls)}개 · "
          f"옛 홈런 판독 있는 것 {sum(cache(h['video_id'], OLD_V).exists() for h in hls)}개 · 다시 물을 것 {len(short)}개 · 이번에 새로 {len(todo)}개(어림 ${len(todo) * USD_PER_VIDEO:.2f}) · 상한 ${a.usd:.2f} · 지금까지 ${spent_total():.2f}")

    judge = Judge(OUT / "hl", sleep=6.0, usd=a.usd) if todo else None
    for h in todo:
        v = PROMPT_V + (".r1" if cache(h["video_id"]).exists() else "")
        try:
            res = judge.ask(f"hl_{h['video_id']}.{v}", h["video_id"], PROMPT, SCHEMA, max_tokens=MAX_TOKENS)
        except OverBudget as e:
            print(e, "— 다시 돌리면 이어서 한다")
            break
        if res.get("status") != 200:
            print("  ", h["video_id"], "판독 실패", res.get("status"), str(res.get("body"))[:120])

    done = [h for h in hls if cache(h["video_id"]).exists()]
    pas_by = {}
    for r in run(driver, Q_PAS, games=[h["game_pk"] for h in done], events=list(set(EVENTS.values()))):
        pas_by.setdefault(r["game_pk"], []).append(r)

    rec, read, matched, states, hr_cmp, videos, spot = Counter(), Counter(), Counter(), Counter(), Counter(), [], []
    pa_rows, k_rows = [], {}
    for h in done:
        # 다시 물은 응답이 있으면 장면이 더 많은 쪽
        path = max((c for c in (cache(h["video_id"]), cache(h["video_id"], PROMPT_V + ".r1")) if c.exists()),
                   key=lambda c: len(scenes_of(c) or []))
        res = json.load(open(path, encoding="utf-8"))
        items = scenes_of(path)
        if items is None:
            print("  ", h["video_id"], "응답을 읽지 못함")
            continue
        pas = pas_by.get(h["game_pk"], [])
        got, state = assign_scenes(items, pas, h["dur"])
        by_pa = {pa["pa_id"]: pa for pa in pas}
        for pa in pas:
            rec[group(pa["events"])] += 1
        for i, it in enumerate(items):
            read[group(it.get("kind"))] += 1
            states[(group(it.get("kind")), state[i])] += 1
        for pid, s in got.items():
            matched[(group(by_pa[pid]["events"]), s["strength"])] += 1
            pa = by_pa[pid]
            row = {"video_id": h["video_id"], "t_sec": s["t_sec"], "start_sec": int(max(0, s["t_sec"] - LEAD)),
                   "end_sec": int(min(h["dur"] or s["t_sec"] + TAIL, s["t_sec"] + TAIL)), "tags": [],
                   "reasons": "하이라이트 판독 " + "·".join(["이름", "종류"] + s["checks"]), "review_reason": None,
                   "prompt_v": PROMPT_V, "model": res.get("model")}
            if pa["events"] == "strikeout":
                if s["strength"] == "strong" and pa["pitcher_id"]:
                    oid = f"{h['game_pk']}_{pa['pitcher_id']}"
                    if oid not in k_rows or s["t_sec"] < k_rows[oid]["t_sec"]:  # 그 등판의 가장 이른 삼진
                        k_rows[oid] = {**row, "target_id": oid, "status": "auto_confirmed", "scene_type": "outing",
                                       "rank": None, "tags": ["strikeout"]}  # rank는 Q_K_RANK
            elif s["strength"] == "strong" or pa["events"] == "home_run":
                pa_rows.append({**row, "target_id": pid, "rank": 0,
                                "scene_type": "home_run" if pa["events"] == "home_run" else "hit",
                                "status": "auto_confirmed" if s["strength"] == "strong" else "pending",
                                "review_reason": None if s["strength"] == "strong" else "highlight_weak"})
        # 홈런: 같은 영상의 옛 판독(홈런 전용)과 견준다
        old = cache(h["video_id"], OLD_V)
        hr_pas = [pa for pa in pas if pa["events"] == "home_run"]
        diffs = []
        if old.exists():
            old_got, _ = assign((parsed(json.load(open(old, encoding="utf-8"))) or {}).get("home_runs") or [], hr_pas, h["dur"])
            for pa in hr_pas:
                o, n = old_got.get(pa["pa_id"]), got.get(pa["pa_id"])
                hr_cmp[("옛 strong" if o and o["strength"] == "strong" else "옛 weak" if o else "옛 못 찾음",
                        "새 strong" if n and n["strength"] == "strong" else "새 weak" if n else "새 못 찾음")] += 1
                if o and n:
                    diffs.append(abs(o["t_sec"] - n["t_sec"]))
        videos.append({"video_id": h["video_id"], "game_pk": h["game_pk"], "title": h["title"], "dur": h["dur"],
                       "model": res.get("model"), "read": len(items), "record": len(pas), "matched": len(got),
                       "hr_time_diffs": diffs,
                       "links": [{"pa_id": pid, "events": by_pa[pid]["events"], "batter": by_pa[pid]["batter"],
                                  "inning": by_pa[pid]["inning"], **s, "start_sec": int(max(0, s["t_sec"] - LEAD))}
                                 for pid, s in got.items()],
                       "unmatched": [items[i] for i, st in state.items() if st in ("unmatched", "conflict")]})
        for v in videos[-1]["links"]:
            if v["events"] != "home_run" and v["strength"] == "strong":
                spot.append({"key": hashlib.sha1(f"{v['pa_id']}|{h['video_id']}".encode()).hexdigest(),
                             "url": f"https://youtu.be/{h['video_id']}?t={v['start_sec']}",
                             "what": f"{v['batter']} {v['inning']}회 {v['events']}"})

    spot = sorted(spot, key=lambda s: s["key"])[:SPOT]
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    report = {"season": a.season, "prompt_v": PROMPT_V, "videos": len(videos), "spent_usd": round(judge.spent, 4) if judge else 0,
              "record": dict(rec), "read": dict(read), "matched": {f"{k[0]} {k[1]}": n for k, n in matched.items()},
              "read_state": {f"{k[0]} {k[1]}": n for k, n in sorted(states.items())},
              "hr_vs_old": {f"{k[0]} → {k[1]}": n for k, n in sorted(hr_cmp.items())}, "spot": spot, "detail": videos}
    path = OUT / f"scenes_{a.season}_{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"하이라이트 {len(videos)}개 · 그 경기 기록(홈런 · 안타 · 삼진) {dict(rec)} · 판독 장면 {dict(read)}")
    for g in ("home_run", "hit", "strikeout"):
        print(f"  {g}: 연결 strong {matched[(g, 'strong')]} · weak {matched[(g, 'weak')]} · "
              f"근거 충돌만 {states[(g, 'conflict')]} · 기록에 없음 {states[(g, 'unmatched')]} · 시각 없음 {states[(g, 'no_time')]}")
    if hr_cmp:
        print("  홈런 옛 판독 대비:", ", ".join(f"{k[0]} → {k[1]} {n}" for k, n in sorted(hr_cmp.items())))
        d = [x for v in videos for x in v["hr_time_diffs"]]
        print(f"  홈런 시각 차이(옛 ↔ 새): {len(d)}개 중 3초 이내 {sum(x <= 3 for x in d)} · 최대 {max(d, default=0):.0f}초")
    print(f"사람이 눌러 볼 장면 {len(spot)}개 → {path.name} 의 spot" + (f" · 이번에 쓴 돈 ${judge.spent:.2f}" if judge else ""))

    if a.load:
        run(driver, Q_CLEAR, season=a.season)
        n_pa = run(driver, Q_SAVE.format(label="PlateAppearance", key="pa_id"), rows=pa_rows)[0]["n"]
        n_k = run(driver, Q_SAVE.format(label="Outing", key="outing_id"), rows=list(k_rows.values()))[0]["n"]
        run(driver, Q_K_RANK, season=a.season)
        st = Counter((r["scene_type"], r["status"]) for r in pa_rows)
        print(f"저장: 타석 {n_pa}개 ({', '.join(f'{k[0]} {k[1]} {n}' for k, n in sorted(st.items()))}) · "
              f"등판 삼진 장면 {n_k}개 (사람이 판정한 연결은 건드리지 않음)")
        for r in run(driver, Q_MULTI, season=a.season):
            print(f"  멀티 홈런 클립 연결 {r['n']}개 → " + ("superseded (하이라이트 장면이 대신)" if r["covered"] else "검수 대기 (multi_scene_clip)"))
    if a.sample:
        have = run(driver, "MATCH (pa:PlateAppearance {season: $season})-[m:MATCHED_TO {nfr07: 'v2'}]->() RETURN count(m) AS n",
                   season=a.season)[0]["n"]
        if have:
            print(f"NFR-07 표본이 이미 {have}개 있어 다시 뽑지 않는다")
        else:
            shown = [r for r in run(driver, Q_SHOWN, season=a.season) if r["video_id"] and r["status"] == "auto_confirmed"]
            shown.sort(key=lambda r: hashlib.sha1(f"{r['pa_id']}|{r['video_id']}".encode()).hexdigest())
            pick = [{"pa_id": r["pa_id"], "video_id": r["video_id"], "i": i} for i, r in enumerate(shown[:NFR07_N])]
            run(driver, Q_MARK, rows=pick)
            print(f"NFR-07 표본 {len(pick)}개 고정 (화면에 나가는 자동 확정 홈런 연결 {len(shown)}개 중 · "
                  f"출처 {dict(Counter(r['origin'] for r in shown[:NFR07_N]))})")
    driver.close()


if __name__ == "__main__":
    main()
