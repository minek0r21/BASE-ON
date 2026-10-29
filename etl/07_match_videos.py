"""
07. 영상 ↔ 기록 매칭 (DB 안 건드림). 설계: docs/장면.md 4·5장

영상 목록을 읽어 분류하고(07a, scenes.classify), 영상마다 어느 기록의 장면인지 정한다.
결과는 CSV로만 저장한다. 눈으로 확인한 뒤 08_load_videos.py로 DB에 넣는다.

단계별 규칙은 모듈에 있다
  game   match_game.py   경기 하이라이트·챕터 영상 → 경기 (기본층)
  pa     match_pa.py     장면 클립·챕터 홈런 줄 → 타석 (홈런 자동 확정 7조건)
  outing match_outing.py 등판 클립·챕터 투수 줄 → 등판

실행
  docker compose run --rm etl etl/07_match_videos.py --season 2025 --step game   --videos videos/yt_inventory.json
  docker compose run --rm etl etl/07_match_videos.py --season 2025 --step pa     --videos videos/yt_inventory.json
  docker compose run --rm etl etl/07_match_videos.py --season 2025 --step outing --videos videos/yt_inventory.json
결과 (git 제외, 단계마다 한 벌)
  videos/links_2025_<단계>.csv      연결·후보 한 줄씩 (scenes.LINK_COLUMNS: rel·target_kind·target_id·video_id·…)
  videos/videos_2025_<단계>.csv     적재할 영상 (연결·후보가 하나라도 있는 영상)
  videos/unmatched_2025_<단계>.csv  연결 못 한 영상과 이유
"""
import argparse
from pathlib import Path

from match_game import match_game
from match_outing import match_outing
from match_pa import match_pa
from scenes import STEPS, VIDEO_COLUMNS, VIDEOS_DIR, load_videos, videos_path, write_links


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--step", choices=STEPS, default="pa",
                    help="pa: 장면 클립 → 타석 · game: 경기 하이라이트 → 경기 · outing: 등판 클립·챕터 → 등판")
    ap.add_argument("--videos", help="영상 목록. 생략하면 videos/yt_inventory.json, 없을 때만 2025 크보모먼트 재생목록 CSV")
    args = ap.parse_args()

    # 기본 입력을 재생목록 CSV로 두면 --videos 없이 돌렸을 때 작은 입력으로 links_<시즌>_<단계>.csv를 덮어쓰고,
    # 08이 그 결과로 자동 연결을 바꿔 장면이 크게 줄어든다(2025 타석 자동 확정 2,578 → 887로 확인). 그래서 영상 목록이 먼저다
    inventory = VIDEOS_DIR / "yt_inventory.json"
    if not args.videos:
        args.videos = inventory if inventory.exists() else VIDEOS_DIR / "playlist_PLMtML65ksOv0.csv"
    if inventory.exists() and Path(args.videos).resolve() != inventory.resolve():
        print(f"주의: 영상 목록({inventory.name})이 있는데 {Path(args.videos).name}로 매칭합니다. "
              "이 결과를 08로 넣으면 영상 목록 기준 자동 연결이 이 결과로 바뀝니다.")

    videos = load_videos(args.videos)
    print(f"입력 {Path(args.videos).name}: 영상 {len(videos)}개 (종류 {videos['kind'].value_counts().to_dict()})")
    step = {"pa": match_pa, "game": match_game, "outing": match_outing}[args.step]
    links, miss, game_date = step(videos, args.season)

    write_links(links, args.season, args.step)
    vids = videos[videos["video_id"].isin(set(game_date))].copy()
    vids["game_date"] = vids["video_id"].map(game_date)
    vids[VIDEO_COLUMNS].to_csv(videos_path(args.season, args.step), index=False, encoding="utf-8-sig")
    miss.to_csv(VIDEOS_DIR / f"unmatched_{args.season}_{args.step}.csv", index=False, encoding="utf-8-sig")
    print(f"\n저장: videos/links_{args.season}_{args.step}.csv · videos_{args.season}_{args.step}.csv"
          f" · unmatched_{args.season}_{args.step}.csv")


if __name__ == "__main__":
    main()
