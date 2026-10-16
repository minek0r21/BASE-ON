"""
적재가 잘 됐는지 숫자로 확인한다.
    python etl/03_check.py
"""
from common import get_driver, run

CHECKS = [
    ("노드 수", "MATCH (n) RETURN labels(n)[0] AS 종류, count(*) AS 개수 ORDER BY 종류"),
    ("관계 수", "MATCH ()-[r]->() RETURN type(r) AS 종류, count(*) AS 개수 ORDER BY 종류"),
    ("관계가 빠진 타석 (0이어야 정상)", """
        MATCH (pa:PlateAppearance)
        WHERE NOT EXISTS { (pa)<-[:BATTED_IN]-() } OR NOT EXISTS { (pa)<-[:PITCHED_IN]-() }
           OR NOT EXISTS { (pa)-[:PART_OF]->() }
        RETURN count(pa) AS 개수"""),
    ("김도영 시즌 기록", """
        MATCH (p:Player {player_id: '52605'})-[:HAS_STAT]->(s)
        RETURN s.season AS 시즌, s.pa AS 타석, s.avg AS 타율, s.hr AS 홈런, s.ops AS OPS,
               s.qualified AS 백분위대상, s.pct_hit AS 안타생산, s.pct_power AS 파워
        ORDER BY 시즌"""),
    ("김도영 최근 홈런 3개", """
        MATCH (:Player {player_id: '52605'})-[:BATTED_IN]->(pa:PlateAppearance {events: 'home_run'})
              <-[:PITCHED_IN]-(pit:Player)
        RETURN pa.date AS 날짜, pa.inning AS 이닝, pa.inning_half AS 초말,
               pa.hr_seq AS 시즌몇호, pa.runs_scored AS 점수, pit.name AS 투수
        ORDER BY pa.date DESC, pa.at_bat_number DESC LIMIT 3"""),
]


def main():
    driver = get_driver()
    for title, q in CHECKS:
        print(f"\n[{title}]")
        rows = run(driver, q)
        if not rows:
            print("  (결과 없음)")
        for r in rows:
            print("  " + " | ".join(f"{k}: {v}" for k, v in r.items()))
    driver.close()


if __name__ == "__main__":
    main()
