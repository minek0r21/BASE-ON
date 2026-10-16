"""
DB를 완전히 비우고 새 스키마의 제약조건·인덱스를 만든다.
    python etl/00_reset_db.py         # 확인 문구(DELETE)를 물어본다
    python etl/00_reset_db.py --yes   # 묻지 않고 지운다 (docker compose run처럼 입력할 수 없을 때)

주의: Neo4j에 있는 모든 노드와 관계가 지워진다.
"""
import argparse

from common import get_driver, run

CONSTRAINTS = [
    "CREATE CONSTRAINT player_id IF NOT EXISTS FOR (n:Player) REQUIRE n.player_id IS UNIQUE",
    "CREATE CONSTRAINT team_id IF NOT EXISTS FOR (n:Team) REQUIRE n.team_id IS UNIQUE",
    "CREATE CONSTRAINT game_pk IF NOT EXISTS FOR (n:Game) REQUIRE n.game_pk IS UNIQUE",
    "CREATE CONSTRAINT pa_id IF NOT EXISTS FOR (n:PlateAppearance) REQUIRE n.pa_id IS UNIQUE",
    "CREATE CONSTRAINT stat_id IF NOT EXISTS FOR (n:BatterSeasonStat) REQUIRE n.stat_id IS UNIQUE",
    "CREATE CONSTRAINT pitching_stat_id IF NOT EXISTS FOR (n:PitcherSeasonStat) REQUIRE n.stat_id IS UNIQUE",
    "CREATE CONSTRAINT video_id IF NOT EXISTS FOR (n:VideoLink) REQUIRE n.video_id IS UNIQUE",
    "CREATE CONSTRAINT archetype_id IF NOT EXISTS FOR (n:PitchArchetype) REQUIRE n.archetype_id IS UNIQUE",
]
INDEXES = [
    "CREATE TEXT INDEX player_name IF NOT EXISTS FOR (n:Player) ON (n.name)",
    "CREATE INDEX pa_season IF NOT EXISTS FOR (n:PlateAppearance) ON (n.season)",
    "CREATE INDEX pa_date IF NOT EXISTS FOR (n:PlateAppearance) ON (n.date)",
    "CREATE INDEX batter_stat_season IF NOT EXISTS FOR (n:BatterSeasonStat) ON (n.season)",
    "CREATE INDEX matched_status IF NOT EXISTS FOR ()-[r:MATCHED_TO]-() ON (r.status)",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="확인 문구를 묻지 않고 지운다")
    args = ap.parse_args()

    driver = get_driver()
    count = run(driver, "MATCH (n) RETURN count(n) AS c")[0]["c"]
    print(f"지금 DB에 노드 {count:,}개가 있습니다.")
    if not args.yes and input("모두 지우려면 DELETE 를 입력하세요: ").strip() != "DELETE":
        print("취소했습니다.")
        return

    # 1) 노드·관계 삭제 (한 번에 지우면 메모리가 부족할 수 있어 1만 개씩)
    deleted = 0
    while True:
        c = run(driver, "MATCH (n) WITH n LIMIT 10000 DETACH DELETE n RETURN count(*) AS c")[0]["c"]
        if c == 0:
            break
        deleted += c
        print(f"  삭제: {deleted:,}", end="\r")
    print(f"  삭제 완료: {deleted:,}개          ")

    # 2) 기존 제약조건·인덱스 삭제
    for r in run(driver, "SHOW CONSTRAINTS YIELD name"):
        run(driver, f"DROP CONSTRAINT `{r['name']}` IF EXISTS")
    for r in run(driver, "SHOW INDEXES YIELD name, type, owningConstraint "
                         "WHERE owningConstraint IS NULL AND type <> 'LOOKUP' RETURN name"):
        run(driver, f"DROP INDEX `{r['name']}` IF EXISTS")
    print("  기존 제약조건·인덱스 삭제 완료")

    # 3) 새 스키마의 제약조건·인덱스 생성
    for q in CONSTRAINTS + INDEXES:
        run(driver, q)
    run(driver, "CALL db.awaitIndexes(300)")
    print(f"  제약조건 {len(CONSTRAINTS)}개, 인덱스 {len(INDEXES)}개 생성 완료")
    driver.close()


if __name__ == "__main__":
    main()
