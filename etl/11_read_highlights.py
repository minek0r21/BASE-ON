"""
11. 경기 하이라이트에서 주목 장면(홈런 · 안타 · 삼진)을 시각과 함께 한 번에 읽는다 (docs/장면.md 11-7)

    docker compose run --rm etl etl/11_read_highlights.py --season 2026 --videos 10 --usd 1.5   # 시험: 보고서만
    docker compose run --rm etl etl/11_read_highlights.py --season 2026 --videos 0              # 받아 둔 응답으로 보고서만 다시

- 왜: 선수별 클립은 「멀티 홈런」 · 「백투백」처럼 장면이 섞여 클립 하나가 여러 타석에 0초부터 걸린다(11-6 충돌 22개).
  경기 하이라이트는 경기마다 하나로 정해지고, 장면마다 시작 초를 붙이면 「15초 안에 그 타격」 기준이 저절로 맞는다
- 대상: 그 시즌 정규시즌 경기의 1등 하이라이트(rank 1). 홈런 전용 프롬프트(09, hr-blind-1)로 이미 읽은 영상부터 →
  같은 영상에서 홈런을 옛 판독과 견줘 「한 번에 다 읽어도 홈런이 줄지 않는지」를 본다
- 대조: reading.assign_scenes — 타자 이름 + 종류가 맞아야 후보, 근거 2개↑ 일치 · 어긋남 없음 = strong. 판정은 코드가 한다
- 아직 DB에 쓰지 않는다. 시험 결과(보고서)를 보고 저장 방식(SUGGESTED → MATCHED_TO)과 측정(NFR-07)을 정한다
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
from reading import EVENTS, HITS, SCENE_ITEM, SCENE_RULES, S, assign, assign_scenes

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "videos" / "gemini"
PROMPT_V = "scene-blind-2"  # 1은 time 칸을 맨 앞에 둬서 10개 중 8개가 무너짐 (장면.md 11-7)
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
       p.name AS pitcher, pa.inning AS inning, pa.outs_when_up AS outs, pa.hr_seq AS hr_seq, pa.at_bat_number AS ab,
       pa.post_home_score AS home_post, pa.post_away_score AS away_post
ORDER BY gpk, ab
"""


def scenes_of(path: Path) -> list[dict] | None:
    return (parsed(json.load(open(path, encoding="utf-8"))) or {}).get("scenes")


def group(kind: str | None) -> str:
    return "hit" if kind in HITS else kind or "?"


def main():
    ap = argparse.ArgumentParser(description="하이라이트 주목 장면 판독 (Gemini)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--videos", type=int, default=10, help="이번에 새로 판독할 하이라이트 수")
    ap.add_argument("--usd", type=float, default=1.5, help="이번 실행에서 쓸 돈 상한(달러)")
    a = ap.parse_args()

    driver = get_driver()
    hls = run(driver, Q_HIGHLIGHTS, season=a.season, confirmed=CONFIRMED)
    cache = lambda vid, v=PROMPT_V: OUT / "hl" / f"hl_{vid}.{v}.json"  # noqa: E731
    # 이미 읽은 것 → 옛 판독이 있는 것 → 나머지, 같은 묶음 안에서는 영상 ID 해시 순 (실행마다 같은 순서)
    hls.sort(key=lambda h: (not cache(h["video_id"]).exists(), not cache(h["video_id"], OLD_V).exists(),
                            hashlib.sha1(h["video_id"].encode()).hexdigest()))
    # 중간에 멈춘 응답은 같은 영상을 한 번 더 묻는다 (키 끝 .r1). 다시 물은 것도 이번 --videos 수에 든다
    short = [h for h in hls if cache(h["video_id"]).exists() and not cache(h["video_id"], PROMPT_V + ".r1").exists()
             and (h["dur"] or 0) > LONG and len(scenes_of(cache(h["video_id"])) or []) < MIN_SCENES]
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
    driver.close()

    rec, read, matched, states, hr_cmp, videos, spot = Counter(), Counter(), Counter(), Counter(), Counter(), [], []
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


if __name__ == "__main__":
    main()
