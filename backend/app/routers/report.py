"""
재생 불가 신고 (API-12). 설계: 설계.md 8-3, docs/장면.md 7장
  POST /video-links/{video_id}/report      누구나. 항상 202 — 응답으로 판정을 알려 주지 않는다
  POST /admin/videos/recheck?limit=50      관리자. 확정 연결이 있는 영상을 오래 확인 안 한 순으로 다시 확인 (주기 재확인)

판정 (YouTube videos.list?part=status, 영상 50개까지 쿼터 1)
- 영상이 없음(삭제·비공개) 또는 embeddable = false → 재생 불가
  → VideoLink.playable = false, 그 영상의 확정 연결 전부 status 'pending' · review_reason 'unplayable'
    (원래 상태는 prev_status, reviewer 'system') → 검수 「영상 소실」. 같은 대상의 다음 순위 연결이 있으면 화면은 그것을 쓴다
- 정상 → 연결은 그대로 (사용자 쪽 일시 오류). 예전에 재생 불가였다면 playable만 true로 되돌리고 연결 승인은 검수에서
- 키가 없거나 API 오류 → 아무것도 바꾸지 않는다
같은 영상은 24시간 안에 다시 확인하지 않는다(VideoLink.checked_at). 신고는 IP마다 1분에 10번까지(프로세스 안 카운터).
"""
import time
from collections import defaultdict, deque

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse

from ..db import run
from ..videocheck import CONFIRMED, apply_verdict, check_videos
from .admin import require_admin

router = APIRouter(tags=["영상·검수"])

RATE = 10          # IP마다 1분에 신고 몇 번까지
_hits: dict[str, deque] = defaultdict(deque)


Q_RECENT = """
MATCH (v:VideoLink {video_id: $v})
RETURN v.checked_at IS NOT NULL AND v.checked_at > datetime() - duration('PT24H') AS recent
"""


def _check_one(video_id: str):
    apply_verdict(video_id, check_videos([video_id])[video_id])


def _limited(ip: str) -> bool:
    now, q = time.monotonic(), _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE:
        return True
    q.append(now)
    return False


@router.post("/video-links/{video_id}/report", status_code=202, summary="12. 재생 불가 신고")
def report_unplayable(video_id: str, request: Request, background: BackgroundTasks):
    # 판정은 응답 뒤에 한다. 없는 영상·24시간 안에 확인한 영상·신고가 잦은 IP도 똑같이 202
    ip = request.client.host if request.client else "-"
    if not _limited(ip):
        found = run(Q_RECENT, v=video_id)
        if found and not found[0]["recent"]:
            background.add_task(_check_one, video_id)
    return JSONResponse({"status": "accepted"}, status_code=202)


Q_STALE = """
MATCH (:Game|PlateAppearance|Outing)-[m:MATCHED_TO]->(v:VideoLink) WHERE m.status IN $confirmed
WITH DISTINCT v ORDER BY coalesce(v.checked_at, datetime('1970-01-01T00:00:00Z'))
RETURN v.video_id AS video_id LIMIT $limit
"""


@router.post("/admin/videos/recheck", summary="12'. 확정 영상 재생 가능 다시 확인 (주기 재확인)")
def recheck(limit: int = Query(50, ge=1, le=500), _reviewer: str | None = Depends(require_admin)):
    ids = [r["video_id"] for r in run(Q_STALE, confirmed=CONFIRMED, limit=limit)]
    verdicts = check_videos(ids)
    moved = sum(apply_verdict(v, verdict) for v, verdict in verdicts.items())
    counts = defaultdict(int)
    for verdict in verdicts.values():
        counts[verdict] += 1
    return {"checked": len(ids), "ok": counts["ok"], "unplayable": counts["unplayable"], "unknown": counts["unknown"],
            "links_to_review": moved}
