"""
적재가 잘 됐는지 숫자로 확인한다.
    python etl/03_check.py                     # 노드 · 관계 수, 빠진 관계, 한 선수 기록
    python etl/03_check.py --sample 100        # + 원천 대조 (NFR-05): DB 타석 무작위 100건을 원본 parquet과 한 칸씩 비교
    python etl/03_check.py --sample 100 --seed 7

원천 대조는 prepare.py(적재 가공)를 거치지 않고 원본 parquet을 직접 읽어 비교한다 — 적재 가공의 실수도 잡게.
타석 하나 = 원본에서 그 경기 · 그 타석 번호의 투구 줄들. 마지막 공 줄이 타석 결과다.
불일치가 하나라도 있으면 종료 코드 1.
"""
import argparse
import random

import pandas as pd

from common import KBO_PBP_DIR, get_driver, run

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

# ---------------------------------------------------------------- 원천 대조 (NFR-05)
Q_ALL_PA = "MATCH (pa:PlateAppearance) RETURN pa.pa_id AS id ORDER BY id"
Q_SAMPLE = """
UNWIND $ids AS id
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance {pa_id: id})<-[:PITCHED_IN]-(p:Player)
MATCH (pa)-[:PART_OF]->(g:Game)-[:HOME]->(h:Team), (g)-[:AWAY]->(a:Team)
RETURN id, pa.game_pk AS game_pk, pa.at_bat_number AS at_bat_number, toString(pa.date) AS date,
       pa.inning AS inning, pa.inning_half AS inning_half, pa.events AS events, pa.runs_scored AS runs_scored,
       pa.final_balls AS balls, pa.final_strikes AS strikes, pa.pitch_count AS pitch_count,
       pa.post_home_score AS post_home_score, pa.post_away_score AS post_away_score,
       pa.on_1b AS on_1b, pa.on_2b AS on_2b, pa.on_3b AS on_3b,
       b.player_id AS batter, p.player_id AS pitcher, h.team_id AS home_team, a.team_id AS away_team
"""
RAW_COLS = ["game_pk", "game_date", "home_team", "away_team", "inning", "inning_topbot", "at_bat_number",
            "pitch_number", "batter", "pitcher", "balls", "strikes", "post_home_score", "post_away_score",
            "on_1b", "on_2b", "on_3b", "events", "runs_scored"]


def read_raw(game_pks: set[str]) -> pd.DataFrame:
    """그 경기들의 원본 투구 줄 (정규 · 포스트시즌 파일 모두)"""
    frames = []
    for path in sorted(KBO_PBP_DIR.glob("kbo_pbp_*.parquet")):
        df = pd.read_parquet(path, columns=RAW_COLS)
        df["game_pk"] = df["game_pk"].astype("string").str.strip()
        frames.append(df[df["game_pk"].isin(game_pks)])
    return pd.concat(frames, ignore_index=True).sort_values(["game_pk", "at_bat_number", "pitch_number"])


def norm(v):
    """비교용: 빈 문자열 · None · NaN은 같게, 숫자는 int로"""
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
        return None
    if isinstance(v, str):
        v = v.strip()
        return v or None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def check_sample(driver, n: int, seed: int) -> int:
    ids = [r["id"] for r in run(driver, Q_ALL_PA)]
    picked = random.Random(seed).sample(ids, min(n, len(ids)))
    db = {r["id"]: r for r in run(driver, Q_SAMPLE, ids=picked)}
    raw = read_raw({db[i]["game_pk"] for i in picked if i in db})
    groups = {k: g for k, g in raw.groupby(["game_pk", "at_bat_number"])}

    bad, fields = [], 0
    for i in picked:
        d = db.get(i)
        if d is None:
            bad.append((i, "DB", "선수 · 경기 관계가 빠짐", None))
            continue
        g = groups.get((d["game_pk"], d["at_bat_number"]))
        if g is None:
            bad.append((i, "원본", "원본에 이 타석이 없음", None))
            continue
        last = g.iloc[-1]
        expect = {
            "date": str(last["game_date"])[:10],
            "home_team": last["home_team"], "away_team": last["away_team"],
            "inning": last["inning"], "inning_half": "초" if last["inning_topbot"] == "top" else "말",
            "batter": last["batter"], "pitcher": last["pitcher"],
            "events": last["events"], "runs_scored": last["runs_scored"],
            "balls": last["balls"], "strikes": last["strikes"], "pitch_count": len(g),
            "post_home_score": last["post_home_score"], "post_away_score": last["post_away_score"],
            "on_1b": norm(last["on_1b"]) is not None, "on_2b": norm(last["on_2b"]) is not None,
            "on_3b": norm(last["on_3b"]) is not None,
        }
        for k, want in expect.items():
            fields += 1
            got = d[k]
            if norm(got) != norm(want):
                bad.append((i, k, got, want))

    print(f"\n[원천 대조 (NFR-05)] 시드 {seed} · 타석 {len(picked)}건 · 항목 {fields}개 비교 (원본: {KBO_PBP_DIR})")
    rows = len({b[0] for b in bad})
    print(f"  불일치 타석 {rows}건 · 불일치 항목 {len(bad)}개 → {'통과' if not bad else '실패'}")
    for i, k, got, want in bad[:20]:
        print(f"  {i} · {k}: DB {got!r} ≠ 원본 {want!r}")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0, help="원천 대조할 타석 수 (NFR-05는 100)")
    ap.add_argument("--seed", type=int, default=20261101, help="무작위 표본 시드 (같은 시드 = 같은 표본)")
    a = ap.parse_args()

    driver = get_driver()
    for title, q in CHECKS:
        print(f"\n[{title}]")
        rows = run(driver, q)
        if not rows:
            print("  (결과 없음)")
        for r in rows:
            print("  " + " | ".join(f"{k}: {v}" for k, v in r.items()))
    code = check_sample(driver, a.sample, a.seed) if a.sample else 0
    driver.close()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
