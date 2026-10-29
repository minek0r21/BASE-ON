"""
타자·투수 시즌 기록과 백분위, 투수 등판(Outing)을 계산해서 적재한다.
    python etl/02_load_season_stats.py
    python etl/02_load_season_stats.py --season 2025  # 2025시즌만

01_load_core.py로 선수 노드를 먼저 넣은 뒤 실행한다.
새 경기가 들어오면 이 스크립트만 다시 돌리면 값이 덮어써진다.
"""
import argparse
import time

from common import get_driver, load_rows
from prepare import (BATTER_POST_PROPS, PITCHER_POST_PROPS, batter_rows, build_batter_post_stats, build_batter_stats,
                     build_games, build_outings, build_pa, build_pitcher_post_stats, build_pitcher_stats, build_plays_for,
                     filter_season, outing_rows, pitcher_rows, post_rows, read_pitches)

Q_BATTER = """
UNWIND $rows AS r
MATCH (p:Player {player_id: r.player_id})
MERGE (s:BatterSeasonStat {stat_id: r.stat_id})
SET s += r.props
MERGE (p)-[:HAS_STAT]->(s)
"""

Q_PITCHER = """
UNWIND $rows AS r
MATCH (p:Player {player_id: r.player_id})
MERGE (s:PitcherSeasonStat {stat_id: r.stat_id})
SET s += r.props
MERGE (p)-[:HAS_PITCHING_STAT]->(s)
"""

# 포스트시즌 기록 (docs/포스트시즌.md 5장, PS1): 정규시즌 기록과 따로, 백분위 없음
Q_BATTER_POST = """
UNWIND $rows AS r
MATCH (p:Player {player_id: r.player_id})
MERGE (s:BatterPostseasonStat {stat_id: r.stat_id})
SET s += r.props
MERGE (p)-[:HAS_POST_STAT]->(s)
"""
Q_PITCHER_POST = """
UNWIND $rows AS r
MATCH (p:Player {player_id: r.player_id})
MERGE (s:PitcherPostseasonStat {stat_id: r.stat_id})
SET s += r.props
MERGE (p)-[:HAS_POST_PITCHING_STAT]->(s)
"""
# 등판 (docs/장면.md 3-5): (Player)-[:PITCHED_GAME]->(Outing)-[:PART_OF]->(Game)
Q_OUTING = """
UNWIND $rows AS r
MATCH (p:Player {player_id: r.player_id}), (g:Game {game_pk: r.game_pk})
MERGE (o:Outing {outing_id: r.outing_id})
SET o += r.props
MERGE (p)-[:PITCHED_GAME]->(o)
MERGE (o)-[:PART_OF]->(g)
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, help="이 시즌만 적재 (예: 2025)")
    args = ap.parse_args()

    start = time.time()
    print("1) parquet 읽고 시즌 기록 계산하는 중…")
    df = read_pitches()
    if args.season:
        df = filter_season(df, args.season)
    games = build_games(df)
    pa = build_pa(df, games)
    batters = build_batter_stats(pa, games, build_plays_for(pa))
    pitchers = build_pitcher_stats(df, pa)
    outings = build_outings(df, pa)
    bat_post, pit_post = build_batter_post_stats(pa), build_pitcher_post_stats(df, pa)
    q = batters[batters["qualified"]].groupby("season").size().to_dict()
    print(f"   타자 시즌 기록 {len(batters):,} · 투수 시즌 기록 {len(pitchers):,} · 등판 {len(outings):,}")
    print(f"   시즌별 백분위 대상 타자: {q}")
    print(f"   포스트시즌 기록: 타자 {len(bat_post):,} · 투수 {len(pit_post):,} · 포스트시즌 등판 {int(outings['game_type'].eq('postseason').sum()):,}")

    print("2) Neo4j에 적재하는 중…")
    driver = get_driver()
    load_rows(driver, Q_BATTER, batter_rows(batters), "타자 시즌 기록")
    load_rows(driver, Q_PITCHER, pitcher_rows(pitchers), "투수 시즌 기록")
    load_rows(driver, Q_OUTING, outing_rows(outings), "등판")
    load_rows(driver, Q_BATTER_POST, post_rows(bat_post, BATTER_POST_PROPS), "타자 포스트시즌 기록")
    load_rows(driver, Q_PITCHER_POST, post_rows(pit_post, PITCHER_POST_PROPS), "투수 포스트시즌 기록")
    driver.close()
    print(f"끝. 총 {time.time() - start:.1f}초")


if __name__ == "__main__":
    main()
