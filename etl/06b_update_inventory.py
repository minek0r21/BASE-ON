"""
06b. 영상 목록(videos/yt_inventory.json)에 새 업로드만 덧붙인다. 공식 YouTube Data API만 쓴다 (영상 파일은 받지 않는다).

처음 목록은 statscene-neo4j/tools/verify/yt_inventory.py가 2024-03-01부터 전부 받은 것이다.
이 스크립트는 목록의 마지막 게시일 3일 전부터 채널 12개의 업로드를 받아, 같은 영상은 새 정보로 바꾸고 새 영상은 더한다.
2026 재생목록(크보모먼트 · H/L) 소속도 새로 읽는다. 쓰기 전에 원래 파일을 yt_inventory.<날짜>.bak.json으로 남긴다.

    python etl/06b_update_inventory.py            # 호스트에서 (키: .env의 YOUTUBE_API_KEY)
    python etl/06b_update_inventory.py --dry-run  # 받을 개수만

쿼터: 채널마다 업로드 목록 50개당 1 + 영상 정보 50개당 1 + 재생목록 50개당 1 (보통 수십 단위, 하루 한도 10,000)
"""
import argparse
import json
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INV = ROOT / "videos" / "yt_inventory.json"
API = "https://www.googleapis.com/youtube/v3/"
CHANNELS = {  # statscene-neo4j/tools/verify/channels.json 과 같다
    "KBO": "UCoVz66yWHzVsXAFG8WhJK9g", "KIA": "UCKp8knO8a6tSI1oaLjfd9XA", "삼성": "UCMWAku3a3h65QpLm63Jf2pw",
    "LG": "UCL6QZZxb-HR4hCh_eFAnQWA", "두산": "UCsebzRfMhwYfjeBIxNX1brg", "KT": "UCvScyjGkBUx2CJDMNAi9Twg",
    "SSG": "UCt8iRtgjVqm5rJHNl1TUojg", "롯데": "UCAZQZdSY5_YrziMPqXi-Zfw", "한화": "UCdq4Ji3772xudYRUatdzRrg",
    "NC": "UC8_FRgynMX8wlGsU6Jh3zKg", "키움": "UC_MA8-XEaVmvyayPzG66IKg", "티빙": "UC8JtQf77wqhVpOQ8Cze8JjA",
}
PLAYLISTS = {"2026 크보모먼트": "PLTX4PhrvOayA", "2026 H/L": "PLuY-NTS_5Ipz7qggSm4O0aTp4RQjNCLCl"}  # 제목 형식 판정용
OVERLAP = timedelta(days=3)  # 늦게 처리된 업로드·바뀐 제목을 다시 잡으려고 겹쳐 받는다


def key() -> str:
    for line in open(ROOT / ".env", encoding="utf-8"):
        k, _, v = line.strip().partition("=")
        if k == "YOUTUBE_API_KEY" and v:
            return v
    raise SystemExit("YOUTUBE_API_KEY가 .env에 없습니다")


def call(k: str, endpoint: str, **params) -> dict:
    params["key"] = k
    try:
        with urllib.request.urlopen(API + endpoint + "?" + urllib.parse.urlencode(params), timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"YouTube API 오류 {e.code} ({endpoint}): {e.read().decode('utf-8', 'replace')[:300]}")


def uploads_since(k: str, channel_id: str, cutoff: datetime) -> list[str]:
    ch = call(k, "channels", part="contentDetails", id=channel_id)["items"][0]
    playlist, ids, token = ch["contentDetails"]["relatedPlaylists"]["uploads"], [], None
    while True:
        res = call(k, "playlistItems", part="contentDetails", playlistId=playlist, maxResults=50, **({"pageToken": token} if token else {}))
        stop = False
        for it in res.get("items", []):
            pub = it["contentDetails"].get("videoPublishedAt")
            if not pub:
                continue  # 비공개·삭제
            if datetime.fromisoformat(pub.replace("Z", "+00:00")) < cutoff:
                stop = True
                continue
            ids.append(it["contentDetails"]["videoId"])
        token = res.get("nextPageToken")
        if stop or not token:
            return ids


def playlist_ids(k: str, pid: str) -> list[str]:
    ids, token = [], None
    while True:
        res = call(k, "playlistItems", part="contentDetails", playlistId=pid, maxResults=50, **({"pageToken": token} if token else {}))
        ids += [i["contentDetails"]["videoId"] for i in res.get("items", [])]
        token = res.get("nextPageToken")
        if not token:
            return ids


def duration_sec(d: str | None) -> int | None:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return None
    days, h, mi, s = (int(x or 0) for x in m.groups())
    return days * 86400 + h * 3600 + mi * 60 + s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    k = key()
    inv = json.load(open(INV, encoding="utf-8"))
    last = max(datetime.fromisoformat(v["published"].replace("Z", "+00:00")) for v in inv)
    cutoff = last - OVERLAP
    print(f"지금 목록 {len(inv)}개, 마지막 게시 {last:%Y-%m-%d} → {cutoff:%Y-%m-%d}부터 받는다")
    found = {label: uploads_since(k, cid, cutoff) for label, cid in CHANNELS.items()}
    print({label: len(ids) for label, ids in found.items()})
    if args.dry_run:
        return
    membership: dict[str, list[str]] = {}
    for name, pid in PLAYLISTS.items():
        for vid in playlist_ids(k, pid):
            membership.setdefault(vid, []).append(name)
    by_id = {v["id"]: v for v in inv}
    added = updated = 0
    for label, ids in found.items():
        for i in range(0, len(ids), 50):
            for x in call(k, "videos", part="snippet,contentDetails,status", id=",".join(ids[i:i + 50])).get("items", []):
                sn, cd, st = x["snippet"], x["contentDetails"], x.get("status", {})
                old = by_id.get(x["id"])
                row = {"id": x["id"], "channel": label, "title": sn["title"], "description": (sn.get("description") or "")[:2000],
                       "published": sn["publishedAt"], "sec": duration_sec(cd.get("duration")),
                       "embeddable": st.get("embeddable"), "privacy": st.get("privacyStatus"),
                       "playlists": sorted(set((old or {}).get("playlists", [])) | set(membership.get(x["id"], [])))}
                added += old is None
                updated += old is not None
                by_id[x["id"]] = row
    for vid, names in membership.items():  # 예전 영상의 2026 재생목록 소속도 맞춘다
        if vid in by_id:
            by_id[vid]["playlists"] = sorted(set(by_id[vid].get("playlists", [])) | set(names))
    backup = INV.with_name(f"yt_inventory.{datetime.now():%Y%m%d}.bak.json")
    if not backup.exists():
        shutil.copy2(INV, backup)
    out = sorted(by_id.values(), key=lambda v: v["published"])
    json.dump(out, open(INV, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"새 영상 {added} · 다시 받은 영상 {updated} → {len(out)}개, 마지막 게시 {out[-1]['published'][:10]} (백업 {backup.name})")


if __name__ == "__main__":
    main()
