"""
08. 영상과 매칭 결과를 DB에 넣기

07에서 만든 매칭 결과(CSV)를 Neo4j에 넣는다.
  (VideoLink)                                영상 노드
  (PlateAppearance)-[:CANDIDATE]->(VideoLink)   후보 (타자마다 상위 3개)  score, rank, reasons
  (PlateAppearance)-[:MATCHED_TO]->(VideoLink)  자동 연결 (검수 대기)     status, origin, score, reasons

실행 (data 폴더에서, 01 다음)
  python etl/08_load_videos.py --season 2025 --videos videos/playlist_PLMtML65ksOv0.csv

다시 실행해도 안전하다
- 영상·후보는 같은 값으로 덮어쓴다
- 이미 검수한 연결(승인·거절, 직접 연결)은 건드리지 않는다. 대기 중인 자동 연결만 점수를 갱신한다
"""
import argparse

import pandas as pd

from common import ROOT, get_driver, load_rows, run, to_records

Q_VIDEO = """
UNWIND $rows AS r
MERGE (v:VideoLink {video_id: r.video_id})
SET v.title = r.title,
    v.game_date = date(r.game_date),
    v.published_at = datetime(r.published_at),
    v.duration_sec = r.duration_sec,
    v.source = 'clip'
"""

Q_CANDIDATE = """
UNWIND $rows AS r
MATCH (pa:PlateAppearance {pa_id: r.pa_id}), (v:VideoLink {video_id: r.video_id})
MERGE (pa)-[c:CANDIDATE]->(v)
SET c.score = r.score, c.rank = r.rank, c.reasons = r.reasons
"""

Q_MATCHED = """
UNWIND $rows AS r
MATCH (pa:PlateAppearance {pa_id: r.pa_id}), (v:VideoLink {video_id: r.video_id})
MERGE (pa)-[m:MATCHED_TO]->(v)
ON CREATE SET m.status = 'pending', m.origin = 'auto', m.score = r.score, m.reasons = r.reasons
ON MATCH SET m.score = CASE WHEN m.status = 'pending' AND m.origin = 'auto' THEN r.score ELSE m.score END,
             m.reasons = CASE WHEN m.status = 'pending' AND m.origin = 'auto' THEN r.reasons ELSE m.reasons END
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--videos", default="videos/playlist_PLMtML65ksOv0.csv")
    args = ap.parse_args()

    videos = pd.read_csv(ROOT / args.videos, dtype={"video_id": str}, encoding="utf-8-sig")
    match = pd.read_csv(ROOT / f"videos/match_{args.season}.csv", dtype={"video_id": str}, encoding="utf-8-sig")

    # 후보가 하나라도 있는 영상만 넣는다 (시구·국가대표 경기 등은 제외)
    v = videos[videos["video_id"].isin(set(match["video_id"]))].copy()
    game_date = match.drop_duplicates("video_id").set_index("video_id")["game_pk"].str[:8]
    v["game_date"] = v["video_id"].map(game_date).map(lambda d: f"{d[:4]}-{d[4:6]}-{d[6:]}")
    v["duration_sec"] = v["duration_sec"].astype(int)

    cand = match[["pa_id", "video_id", "score", "rank", "reasons"]]
    auto = match[match["matched"]][["pa_id", "video_id", "score", "reasons"]]
    print(f"영상 {len(v)}개, 후보 {len(cand)}개, 자동 연결 {len(auto)}개")

    driver = get_driver()
    load_rows(driver, Q_VIDEO, to_records(v[["video_id", "title", "game_date", "published_at", "duration_sec"]]), "영상")
    load_rows(driver, Q_CANDIDATE, to_records(cand), "후보 CANDIDATE")
    load_rows(driver, Q_MATCHED, to_records(auto), "자동 연결 MATCHED_TO")

    print(run(driver, """
        MATCH ()-[m:MATCHED_TO]->() RETURN m.status AS 상태, m.origin AS 출처, count(*) AS 개수
        ORDER BY 상태, 출처"""))
    missing = run(driver, """
        UNWIND $ids AS id
        OPTIONAL MATCH (pa:PlateAppearance {pa_id: id}) WITH id, pa WHERE pa IS NULL
        RETURN count(id) AS n""", ids=list(cand["pa_id"].unique()))[0]["n"]
    print(f"DB에 없는 타석 (0이어야 정상, 01을 같은 시즌으로 넣었는지 확인): {missing}")
    driver.close()


if __name__ == "__main__":
    main()
