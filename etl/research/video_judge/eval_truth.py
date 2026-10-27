# 시험 표본의 정답표: 표본 영상마다 연결 후보 타석 + 그 경기 홈런 전부
# 실행: MSYS_NO_PATHCONV=1 docker compose run --rm -T etl /srv/etl/research/video_judge/eval_truth.py
import json, sys
sys.path.insert(0, "/srv/etl")
from common import get_driver, run

HERE = "/srv/etl/research/video_judge/"
sample = json.load(open(HERE + "sample.json", encoding="utf-8"))
d = get_driver()
Q_LINKS = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance)-[m:MATCHED_TO]->(v:VideoLink {video_id: $v})
MATCH (pa)-[:PART_OF]->(g:Game)
RETURN pa.pa_id AS pa_id, g.game_pk AS game_pk, m.status AS status, m.review_reason AS reason, m.precision AS precision
"""
Q_GAME_HR = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance)-[:PART_OF]->(g:Game {game_pk: $g})
WHERE pa.events = 'home_run'
MATCH (g)-[:HOME]->(h:Team), (g)-[:AWAY]->(a:Team)
RETURN pa.pa_id AS pa_id, b.name AS batter, pa.hr_seq AS hr_seq, toString(pa.date) AS date, pa.inning AS inning,
       pa.inning_half AS half, pa.outs_when_up AS outs, a.name AS away, h.name AS home,
       pa.away_score AS away_pre, pa.home_score AS home_pre, pa.post_away_score AS away_post, pa.post_home_score AS home_post
ORDER BY pa.inning, pa.inning_half DESC
"""
out = []
for s in sample:
    links = run(d, Q_LINKS, v=s["video_id"])
    games = sorted({l["game_pk"] for l in links} | ({s["game_pk"]} if s.get("game_pk") else set()))
    hrs = [h for g in games for h in run(d, Q_GAME_HR, g=g)]
    out.append({**s, "links": links, "game_hrs": hrs})
json.dump(out, open(HERE + "_eval_truth.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "videos;", sum(len(o["game_hrs"]) for o in out), "HR rows")
