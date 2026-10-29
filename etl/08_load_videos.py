"""
08. 영상과 연결(매칭 결과)을 DB에 넣기. 설계: docs/장면.md 3·4장

07이 만든 그 시즌의 videos_<시즌>_<단계>.csv · links_<시즌>_<단계>.csv 를 전부 Neo4j에 넣는다.
연결 대상 종류와 상관없이 같은 방식이다.
  (VideoLink)                                   영상 노드 (kind · channel · …)
  (<대상>)-[:CANDIDATE {score, rank, reasons}]->(VideoLink)      후보
  (<대상>)-[:MATCHED_TO {status, origin, scene_type, precision, start_sec, end_sec, …}]->(VideoLink)  연결
  <대상> = Game(경기) · PlateAppearance(타석) · Outing(등판)   — scenes.TARGETS

실행 (01·02 다음)
  docker compose run --rm etl etl/08_load_videos.py --season 2025

다시 실행해도 안전하다 (설계 7-2)
- 시작할 때 그 시즌 대상의 CANDIDATE 전부와, 자동(origin auto)이면서 pending·auto_confirmed인 MATCHED_TO만 지운다
- 사람이 승인·반려·직접 연결한 것은 남고, 07이 같은 쌍을 다시 내도 MERGE가 만나 아무것도 바꾸지 않는다
"""
import argparse

from common import get_driver, load_rows, run, to_records
from scenes import TARGETS, VIDEO_COLUMNS, read_season

Q_VIDEO = """
UNWIND $rows AS r
MERGE (v:VideoLink {video_id: r.video_id})
SET v.title = r.title, v.channel = r.channel, v.kind = r.kind,
    v.game_date = CASE WHEN r.game_date IS NULL THEN null ELSE date(r.game_date) END,
    v.published_at = datetime(r.published_at), v.duration_sec = r.duration_sec,
    v.embeddable = r.embeddable, v.source = null,
    // 임베드가 막힌 영상은 처음부터 재생 불가. 신고(API-12)로 정해진 false는 다시 적재해도 남긴다
    v.playable = CASE WHEN r.embeddable = false THEN false ELSE coalesce(v.playable, true) END
"""

# 그 시즌 대상의 자동 생성물만 지운다. 라벨은 TARGETS 표에서만 온다 (사용자 입력 아님)
Q_CLEAN = """
MATCH (t:{label} {{season: $season}})-[c:CANDIDATE]->(:VideoLink) DELETE c
"""
Q_CLEAN_AUTO = """
MATCH (t:{label} {{season: $season}})-[m:MATCHED_TO]->(:VideoLink)
WHERE m.origin STARTS WITH 'auto' AND m.status IN ['pending', 'auto_confirmed']
  AND coalesce(m.review_reason, '') <> 'unplayable'   // 재생 불가로 검수에 보낸 것은 남긴다 (API-12)
DELETE m
"""

Q_CANDIDATE = """
UNWIND $rows AS r
MATCH (t:{label} {{{key}: r.target_id}}), (v:VideoLink {{video_id: r.video_id}})
MERGE (t)-[c:CANDIDATE]->(v)
SET c.score = r.score, c.rank = r.rank, c.reasons = r.reasons
"""

Q_MATCHED = """
UNWIND $rows AS r
MATCH (t:{label} {{{key}: r.target_id}}), (v:VideoLink {{video_id: r.video_id}})
MERGE (t)-[m:MATCHED_TO]->(v)
ON CREATE SET m.status = r.status, m.origin = r.origin, m.scene_type = r.scene_type, m.precision = r.precision,
              m.start_sec = r.start_sec, m.end_sec = r.end_sec, m.score = r.score, m.rank = r.rank,
              m.reasons = r.reasons, m.review_reason = r.review_reason,
              m.tags = CASE WHEN r.tags IS NULL THEN [] ELSE split(r.tags, '+') END
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2025)
    args = ap.parse_args()

    videos, links, steps = read_season(args.season)
    for c in ("start_sec", "end_sec", "rank"):
        links[c] = links[c].astype("Int64")
    print(f"단계 {steps} · 영상 {len(videos)}개 · 연결 파일 {len(links)}줄 "
          f"({links.groupby(['target_kind', 'rel']).size().to_dict()})")

    driver = get_driver()
    load_rows(driver, Q_VIDEO, to_records(videos[VIDEO_COLUMNS]), "영상")
    for kind, (label, key) in TARGETS.items():
        sub = links[links["target_kind"] == kind]
        run(driver, Q_CLEAN.format(label=label), season=args.season)
        run(driver, Q_CLEAN_AUTO.format(label=label), season=args.season)
        if sub.empty:
            continue
        cand = sub[sub["rel"] == "candidate"][["target_id", "video_id", "score", "rank", "reasons"]]
        matched = sub[sub["rel"] == "matched"].drop(columns=["rel", "target_kind"])
        load_rows(driver, Q_CANDIDATE.format(label=label, key=key), to_records(cand), f"{kind} 후보 CANDIDATE")
        load_rows(driver, Q_MATCHED.format(label=label, key=key), to_records(matched), f"{kind} 연결 MATCHED_TO")
        missing = run(driver, f"""
            UNWIND $ids AS id
            OPTIONAL MATCH (t:{label} {{{key}: id}}) WITH id, t WHERE t IS NULL
            RETURN count(id) AS n""", ids=list(sub["target_id"].unique()))[0]["n"]
        print(f"  DB에 없는 {kind} 대상 (0이어야 정상, 01을 같은 시즌으로 넣었는지 확인): {missing}")

    print(run(driver, """
        MATCH (t)-[m:MATCHED_TO]->(:VideoLink)
        RETURN labels(t)[0] AS 대상, m.status AS 상태, m.origin AS 출처, count(*) AS 개수
        ORDER BY 대상, 상태, 출처"""))
    driver.close()


if __name__ == "__main__":
    main()
