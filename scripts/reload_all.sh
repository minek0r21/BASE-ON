#!/usr/bin/env bash
# DB를 처음부터 다시 적재한다 (README 「데이터 적재」). 원본 기록·영상 목록을 바꾼 뒤에 쓴다. Git Bash에서 실행.
#   bash scripts/reload_all.sh            # 00 → 01 → 02 → 05 → 03 → 07(시즌 × 단계) → 08(시즌)
#   SEASONS="2026" bash scripts/reload_all.sh   # 07·08만 그 시즌 (00~05는 항상 전체)
# 원본 기록 위치는 .env의 KBO_PBP_HOST_DIR (docker-compose가 /data/kbo_pbp로 붙인다).
# 사람이 승인·반려한 연결도 00에서 지워진다 — 검수를 시작한 뒤에는 00 대신 07·08만 다시 돌린다.
set -euo pipefail
cd "$(dirname "$0")/.."
run() { MSYS_NO_PATHCONV=1 docker compose run --rm -T etl "$@" 2>&1 | grep -v "^ Container " ; }
SEASONS="${SEASONS:-2024 2025 2026}"

echo "== 00 DB 비우기"; run etl/00_reset_db.py --yes
echo "== 01 경기·타석";  run etl/01_load_core.py
echo "== 02 시즌 기록";  run etl/02_load_season_stats.py
echo "== 05 선수 프로필"; run etl/05_load_profile.py
echo "== 03 회귀 확인";  run etl/03_check.py
for s in $SEASONS; do
  for step in game pa outing; do
    echo "== 07 $s $step"; run etl/07_match_videos.py --season "$s" --step "$step" --videos videos/yt_inventory.json | grep -E "자동 확정|검수 이유|저장" || true
  done
  echo "== 08 $s"; run etl/08_load_videos.py --season "$s" | grep -E "DB에 없는|^\[" || true
done
echo "== 끝"
