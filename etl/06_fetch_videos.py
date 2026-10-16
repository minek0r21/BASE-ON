"""
06. YouTube 영상 정보 모으기 (DB 안 건드림)

KBO 공식 채널(@KBO1982)에 올라온 영상의 정보만 받아서 파일로 저장한다.
영상 파일은 받지 않는다. video_id만 있으면 화면에서 YouTube 플레이어로 재생할 수 있다.

흐름
  1) 채널 핸들(@KBO1982) → 채널의 "업로드 목록" id 알아내기   (요청 1번)
  2) 업로드 목록을 50개씩 넘기며 제목·올린 시각 받기           (50개당 요청 1번)
     최신 영상부터 오므로, SINCE 날짜보다 오래된 영상이 나오면 멈춘다
  3) 영상 50개씩 길이·임베드 허용 여부 받기                    (50개당 요청 1번)
  4) data/videos/kbo1982_videos.csv 로 저장

실행 (data 폴더에서)
  python etl/06_fetch_videos.py               # 2024-03-01 이후 영상 전부
  python etl/06_fetch_videos.py --pages 2     # 시험: 최신 100개만
  python etl/06_fetch_videos.py --playlist PLxxxx   # 채널 전체 대신 재생목록 하나만 (예: 크보모먼트)

필요: data/.env 에 YOUTUBE_API_KEY=발급받은키
"""
import argparse
import csv
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent  # data 폴더
load_dotenv(ROOT / ".env")

API = "https://www.googleapis.com/youtube/v3/"
HANDLE = "KBO1982"           # 채널 주소 youtube.com/@KBO1982 의 @ 뒤
SINCE = "2024-03-01"         # 이 날짜 이후에 올라온 영상만 (2024~2026 시즌)
OUT = ROOT / "videos" / "kbo1982_videos.csv"  # --playlist면 videos/playlist_<id>.csv


def call(endpoint: str, **params) -> dict:  # YouTube API 한 번 호출 → JSON(dict)
    params["key"] = os.environ["YOUTUBE_API_KEY"]
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:  # 키 오류, 한도 초과 등은 구글이 이유를 JSON으로 알려줌
        raise SystemExit(f"YouTube API 오류 {e.code}: {e.read().decode('utf-8')[:500]}")


def uploads_playlist(handle: str) -> tuple[str, str]:  # 채널 핸들 → (채널 이름, 업로드 목록 id)
    data = call("channels", part="snippet,contentDetails", forHandle=handle)
    if not data.get("items"):
        raise SystemExit(f"채널을 못 찾음: @{handle}")
    ch = data["items"][0]
    return ch["snippet"]["title"], ch["contentDetails"]["relatedPlaylists"]["uploads"]


def list_uploads(playlist_id: str, since: str, max_pages: int | None, stop_when_old: bool = True) -> list[dict]:  # 업로드 목록 넘기며 모으기
    rows, token, page = [], None, 0
    while True:
        params = {"part": "snippet,contentDetails", "playlistId": playlist_id, "maxResults": 50}
        if token:
            params["pageToken"] = token
        data = call("playlistItems", **params)
        page += 1
        old = 0
        for it in data["items"]:
            published = it["contentDetails"].get("videoPublishedAt") or it["snippet"]["publishedAt"]
            if published[:10] < since:
                old += 1
                continue
            rows.append({
                "video_id": it["contentDetails"]["videoId"],
                "title": it["snippet"]["title"],
                "published_at": published,
            })
        print(f"  {page}쪽: 누적 {len(rows)}개")
        token = data.get("nextPageToken")
        # 한 쪽이 전부 SINCE 이전이면 그 뒤는 더 오래된 영상이라 멈춘다
        if not token or (stop_when_old and old == len(data["items"])) or (max_pages and page >= max_pages):
            return rows


def iso_seconds(d: str) -> int:  # "PT1M5S" → 65
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    dd, h, mi, s = (int(x or 0) for x in m.groups())
    return ((dd * 24 + h) * 60 + mi) * 60 + s


def add_details(rows: list[dict]) -> None:  # 50개씩 길이·임베드 허용 여부 붙이기
    by_id = {r["video_id"]: r for r in rows}
    ids = list(by_id)
    for i in range(0, len(ids), 50):
        data = call("videos", part="contentDetails,status", id=",".join(ids[i:i + 50]))
        for it in data["items"]:
            r = by_id[it["id"]]
            r["duration_sec"] = iso_seconds(it["contentDetails"].get("duration"))
            r["embeddable"] = it["status"].get("embeddable", False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, help="시험용: 최신 N쪽(50개씩)만")
    ap.add_argument("--since", default=SINCE, help="이 날짜 이후 영상만 (기본 2024-03-01)")
    ap.add_argument("--playlist", help="재생목록 id (주소의 list= 뒤). 없으면 채널 업로드 전체")
    args = ap.parse_args()

    if args.playlist:  # 재생목록은 최신순이 아닐 수 있어서 날짜로 멈추지 않고 끝까지 받는다
        playlist = args.playlist
        print(f"재생목록: {playlist}")
    else:
        name, playlist = uploads_playlist(HANDLE)
        print(f"채널: {name} (@{HANDLE})")
    rows = list_uploads(playlist, args.since, args.pages, stop_when_old=not args.playlist)
    rows.sort(key=lambda r: r["published_at"], reverse=True)  # 최신순
    add_details(rows)

    out = ROOT / "videos" / f"playlist_{args.playlist}.csv" if args.playlist else OUT
    out.parent.mkdir(exist_ok=True)
    cols = ["video_id", "published_at", "duration_sec", "embeddable", "title"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: 엑셀에서 한글 안 깨짐
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"\n저장: {out.relative_to(ROOT)} ({len(rows)}개)")
    print(f"임베드 불가: {sum(not r.get('embeddable') for r in rows)}개")
    print("\n최신 제목 20개:")
    for r in rows[:20]:
        print(f"  {r['published_at'][:10]}  {r.get('duration_sec', 0):>5}초  {r['title']}")


if __name__ == "__main__":
    main()
