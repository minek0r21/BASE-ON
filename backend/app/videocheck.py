"""
영상 재생 가능 판정 — 신고(API-12)·주기 재확인·검수 승인이 같이 쓴다. 설계: 설계.md 8-3
YouTube videos.list?part=status (영상 50개까지 쿼터 1). 키(YOUTUBE_API_KEY)가 없거나 오류면 판정 보류(unknown).
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .db import run

CONFIRMED = ["auto_confirmed", "approved"]
YT = "https://www.googleapis.com/youtube/v3/videos"


def check_videos(video_ids: list[str]) -> dict[str, str]:
    """영상마다 'ok' · 'unplayable' · 'unknown'(키 없음·API 오류 — 판정 보류)"""
    key = os.getenv("YOUTUBE_API_KEY")
    if not key or not video_ids:
        return {v: "unknown" for v in video_ids}
    out = {}
    for i in range(0, len(video_ids), 50):
        ids = video_ids[i:i + 50]
        url = YT + "?" + urllib.parse.urlencode({"part": "status", "id": ",".join(ids), "key": key})
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                items = {it["id"]: it["status"] for it in json.load(r).get("items", [])}
        except (urllib.error.URLError, TimeoutError, ValueError):
            out.update({v: "unknown" for v in ids})
            continue
        for v in ids:
            s = items.get(v)
            out[v] = "unplayable" if s is None or not s.get("embeddable", True) or s.get("privacyStatus") == "private" else "ok"
    return out


Q_MARK_CHECKED = "MATCH (v:VideoLink {video_id: $v}) SET v.checked_at = datetime(), v.check_result = $verdict"
Q_UNPLAYABLE = """
MATCH (v:VideoLink {video_id: $v}) SET v.playable = false
WITH v
OPTIONAL MATCH (t)-[m:MATCHED_TO]->(v) WHERE m.status IN $confirmed
SET m.prev_status = m.status, m.status = 'pending', m.review_reason = 'unplayable',
    m.reviewer = 'system', m.reviewed_at = datetime()
RETURN count(m) AS links
"""
Q_PLAYABLE_AGAIN = "MATCH (v:VideoLink {video_id: $v}) WHERE v.playable = false SET v.playable = true RETURN count(v) AS n"


def apply_verdict(video_id: str, verdict: str) -> int:
    """판정을 DB에 반영. 재생 불가로 바꾼 확정 연결 수를 돌려준다"""
    if verdict == "unknown":
        return 0
    run(Q_MARK_CHECKED, v=video_id, verdict=verdict)
    if verdict == "unplayable":
        return run(Q_UNPLAYABLE, v=video_id, confirmed=CONFIRMED)[0]["links"]
    run(Q_PLAYABLE_AGAIN, v=video_id)
    return 0
