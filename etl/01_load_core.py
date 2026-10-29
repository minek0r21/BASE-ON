"""
1단계 기본 데이터를 적재한다: 팀, 선수, 경기, 타석과 그 관계.
    python etl/01_load_core.py              # 전체 (약 2,630경기, 20만 타석)
    python etl/01_load_core.py --sample 30  # 빠른 시험: 최근 30경기만
    python etl/01_load_core.py --season 2025  # 2025시즌만

먼저 00_reset_db.py로 DB를 비우고 제약조건을 만든 뒤 실행한다.
MERGE를 쓰기 때문에 다시 실행해도 노드가 중복으로 생기지 않는다.
"""
import argparse
import time

from common import get_driver, load_rows, to_records
from prepare import (filter_season, build_games, build_pa, build_players, build_plays_for, build_teams,
                     pa_rows, read_pitches, sample_games)

Q_TEAM = """
UNWIND $rows AS r
MERGE (t:Team {team_id: r.team_id})
SET t.name = r.name
"""

Q_PLAYER = """
UNWIND $rows AS r
MERGE (p:Player {player_id: r.player_id})
SET p.name = r.name
"""

Q_GAME = """
UNWIND $rows AS r
MERGE (g:Game {game_pk: r.game_pk})
SET g.date = date(r.date), g.season = r.season, g.dh_no = r.dh_no,
    g.home_final = r.home_final, g.away_final = r.away_final, g.innings = r.innings,
    g.game_type = r.game_type, g.stage = r.stage, g.series_game_no = r.series_game_no  // 포스트시즌 (docs/포스트시즌.md 4장)
WITH g, r
MATCH (h:Team {team_id: r.home_team})
MATCH (a:Team {team_id: r.away_team})
MERGE (g)-[:HOME]->(h)
MERGE (g)-[:AWAY]->(a)
"""

Q_PA = """
UNWIND $rows AS r
MERGE (pa:PlateAppearance {pa_id: r.pa_id})
SET pa += r.props, pa.date = date(r.date)
WITH pa, r
MATCH (b:Player {player_id: r.batter})
MATCH (p:Player {player_id: r.pitcher})
MATCH (g:Game {game_pk: r.game_pk})
MERGE (b)-[:BATTED_IN]->(pa)
MERGE (p)-[:PITCHED_IN]->(pa)
MERGE (pa)-[:PART_OF]->(g)
"""

Q_PLAYS_FOR = """
UNWIND $rows AS r
MATCH (p:Player {player_id: r.player_id})
MATCH (t:Team {team_id: r.team_id})
MERGE (p)-[f:PLAYS_FOR {season: r.season}]->(t)
SET f.games = r.games, f.first_date = date(r.first_date), f.last_date = date(r.last_date)
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, help="최근 N경기만 적재 (시험용)")
    ap.add_argument("--season", type=int, help="이 시즌만 적재 (예: 2025)")
    args = ap.parse_args()

    start = time.time()
    print("1) parquet 읽고 가공하는 중…")
    df = read_pitches()
    if args.season:
        df = filter_season(df, args.season)
    if args.sample:
        df = sample_games(df, args.sample)
    games = build_games(df)
    teams = build_teams(games)
    pa = build_pa(df, games)
    players = build_players(df, pa)
    plays_for = build_plays_for(pa)
    print(f"   경기 {len(games):,} (포스트시즌 {int(games['game_type'].eq('postseason').sum())}) · 타석 {len(pa):,} · "
          f"선수 {len(players):,} ({time.time() - start:.1f}초)")

    print("2) Neo4j에 적재하는 중…")
    driver = get_driver()
    load_rows(driver, Q_TEAM, to_records(teams), "팀")
    load_rows(driver, Q_PLAYER, to_records(players), "선수")
    load_rows(driver, Q_GAME, to_records(games[
        ["game_pk", "date", "season", "dh_no", "home_final", "away_final", "innings", "home_team", "away_team",
         "game_type", "stage", "series_game_no"]
    ]), "경기")
    load_rows(driver, Q_PA, pa_rows(pa), "타석")
    load_rows(driver, Q_PLAYS_FOR, to_records(plays_for), "소속(PLAYS_FOR)")
    driver.close()
    print(f"끝. 총 {time.time() - start:.1f}초")


if __name__ == "__main__":
    main()
