# 2차 시험 표본과 정답표 — 안타 검수 대기 20 · 투수 클립 검수 대기 20 · 챕터 구간 5 (docs/장면.md 11-4)
# 실행: MSYS_NO_PATHCONV=1 docker compose run --rm -T etl /srv/etl/research/video_judge/pilot2_truth.py
import hashlib
import json
import sys

sys.path.insert(0, "/srv/etl")
from common import get_driver, run

HERE = "/srv/etl/research/video_judge/"
d = get_driver()
h = lambda s: hashlib.sha1(s.encode()).hexdigest()  # noqa: E731  고정된 무작위 순서

# A. 안타 검수 대기 (클립): 어느 안타인지 모름(multi_hit) · 주장 불일치(claim_mismatch)
Q_HIT = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance)-[m:MATCHED_TO {status: 'pending'}]->(v:VideoLink)
WHERE m.scene_type = 'hit' AND m.precision = 'scene' AND m.review_reason = $reason AND pa.season IN [2025, 2026]
MATCH (pa)-[:PART_OF]->(g:Game)
RETURN v.video_id AS video_id, v.title AS title, v.duration_sec AS sec, pa.pa_id AS linked, b.player_id AS batter,
       b.name AS name, g.game_pk AS game_pk
"""
Q_POOL = """
MATCH (:Player {player_id: $batter})-[:BATTED_IN]->(pa:PlateAppearance)-[:PART_OF]->(g:Game {game_pk: $g})
MATCH (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
RETURN pa.pa_id AS pa_id, pa.inning AS inning, pa.inning_half AS half, pa.events AS events, pa.runs_scored AS runs,
       pa.situation AS situation, away.name AS away, home.name AS home,
       pa.post_away_score AS away_post, pa.post_home_score AS home_post
ORDER BY pa.at_bat_number
"""
hits = []
for reason in ("multi_hit", "claim_mismatch"):
    rows = sorted(run(d, Q_HIT, reason=reason), key=lambda r: h(r["video_id"] + r["linked"]))[:10]
    for r in rows:
        hits.append({**r, "group": "hit:" + reason, "pool": run(d, Q_POOL, batter=r["batter"], g=r["game_pk"])})

# B. 투수 클립 검수 대기: 후보 등판 여럿(ambiguous) · 주장 없음(no_claim). 영상 하나 = 한 줄, 후보 등판 전부
Q_PIT = """
MATCH (p:Player)-[:PITCHED_GAME]->(o:Outing)-[m:MATCHED_TO {status: 'pending'}]->(v:VideoLink)
WHERE m.precision = 'scene' AND m.review_reason = $reason AND o.season IN [2025, 2026]
MATCH (o)-[:PART_OF]->(g:Game), (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
WITH v, collect({outing_id: o.outing_id, pitcher: p.name, date: o.date, team: CASE WHEN home.team_id = o.team_id THEN home.name ELSE away.name END,
                 opponent: CASE WHEN home.team_id = o.team_id THEN away.name ELSE home.name END, starter: o.starter,
                 outs: o.outs, so: o.so, r: o.r, h: o.h, bb: o.bb}) AS cands
RETURN v.video_id AS video_id, v.title AS title, v.duration_sec AS sec, cands
"""
pits = []
for reason in ("ambiguous", "no_claim"):
    rows = sorted(run(d, Q_PIT, reason=reason), key=lambda r: h(r["video_id"]))[:10]
    pits += [{**r, "group": "pitch:" + reason} for r in rows]

# C. 챕터 구간: 무실점이지만 안타를 맞은 이닝(neutral) — 구간만 잘라 보낸다
Q_SEG = """
MATCH (p:Player)-[:PITCHED_GAME]->(o:Outing)-[m:MATCHED_TO {status: 'pending', review_reason: 'neutral'}]->(v:VideoLink)
WHERE o.season = 2026
MATCH (o)-[:PART_OF]->(g:Game)
WITH p, o, m, v, g, toInteger(split(split(m.reasons, '+')[1], '회')[0]) AS inn
MATCH (p)-[:PITCHED_IN]->(pa:PlateAppearance {inning: inn})-[:PART_OF]->(g)
WITH p, o, m, v, inn, collect(pa.events) AS evs
RETURN v.video_id AS video_id, v.title AS title, m.start_sec AS start, m.end_sec AS end, o.outing_id AS outing_id,
       p.name AS pitcher, inn AS inning, evs
"""
segs = sorted(run(d, Q_SEG), key=lambda r: h(r["video_id"] + r["outing_id"]))[:5]
segs = [{**r, "group": "segment"} for r in segs]

out = hits + pits + segs
json.dump(out, open(HERE + "pilot2_truth.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print({g: sum(1 for x in out if x["group"] == g) for g in sorted({x["group"] for x in out})})
