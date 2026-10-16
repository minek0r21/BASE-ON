"""
영상·장면 검수 API
   5. GET   /plate-appearances/{pa_id}/video                       기록 탭: 이 타석의 승인된 영상
   7. GET   /video-links?status=&sort=&limit=&offset=              장면 검수: 영상 목록 (연결·후보 포함)
   8. PATCH /video-links/{video_id}/plate-appearances/{pa_id}      장면 검수: 승인 / 반려 / 다른 타석으로 옮김
   9. POST  /video-links/{video_id}/plate-appearances/{pa_id}      장면 검수: 영상-타석 새 연결 (직접 연결)
  10. GET   /video-links/stats                                     장면 검수: 자동 연결 정확도

연결 상태 (MATCHED_TO.status)
  pending  자동 매칭(08)이 만든 연결, 검수 전
  approved 승인. 화면(2·3·4·5번 API)에는 이것만 나온다
  rejected 반려. 옮김(move)으로 반려된 연결에는 moved_to(옮긴 타석)가 남는다
"""
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ..db import run
from ..errors import ApiError
from ..events import events_ko

router = APIRouter(tags=["영상·검수"])


def _summary(inning, half, events, runs) -> str:  # 타석 한 줄 요약: "3회말 2루타, 2득점"
    s = f"{inning}회{half} {events_ko(events)}"
    return s + (f", {runs}득점" if runs else "")


# ------------------------------------------------------------------ 5. 타석의 영상
Q_PA_VIDEOS = """
MATCH (pa:PlateAppearance {pa_id: $pa})
OPTIONAL MATCH (pa)-[m:MATCHED_TO {status: 'approved'}]->(v:VideoLink)
WITH pa, m, v ORDER BY v.published_at
RETURN pa.pa_id AS pa_id,
       collect(v {.video_id, .title, .duration_sec,
                  start_sec: coalesce(m.start_sec, 0), end_sec: m.end_sec}) AS videos
"""


@router.get("/plate-appearances/{pa_id}/video", summary="5. 타석의 영상 (승인된 것만)")
def get_pa_video(pa_id: str):  # API 5: 기록 탭 '영상보기'
    rows = run(Q_PA_VIDEOS, pa=pa_id)
    if not rows:
        raise ApiError(404, "PA_NOT_FOUND", "타석을 찾을 수 없습니다")
    return rows[0]  # {"pa_id": ..., "videos": [...]}  영상이 없으면 빈 목록


# ------------------------------------------------------------------ 7. 검수 목록
# 영상마다 연결(MATCHED_TO) 전부를 모은다. 후보(CANDIDATE)는 따로 불러 붙인다
Q_VIDEO_LINKS = """
MATCH (v:VideoLink)
OPTIONAL MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance)-[m:MATCHED_TO]->(v)
RETURN v {.video_id, .title, .duration_sec, game_date: toString(v.game_date)} AS v,
       collect(CASE WHEN m IS NULL THEN null ELSE {
           pa_id: pa.pa_id, batter: b.name, inning: pa.inning, inning_half: pa.inning_half,
           events: pa.events, runs: pa.runs_scored,
           status: m.status, origin: m.origin, score: m.score, reasons: m.reasons,
           reviewer: m.reviewer, reviewed_at: toString(m.reviewed_at), moved_to: m.moved_to
       } END) AS links
"""

Q_CANDIDATES = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance)-[c:CANDIDATE]->(v:VideoLink)
WHERE v.video_id IN $ids
RETURN v.video_id AS video_id, b.name AS batter, c.rank AS rank, c.score AS score, c.reasons AS reasons,
       pa.pa_id AS pa_id, pa.inning AS inning, pa.inning_half AS inning_half,
       pa.events AS events, pa.runs_scored AS runs
ORDER BY video_id, batter, rank
"""


def _video_status(links: list[dict]) -> str:  # 영상 하나의 상태: 대기가 하나라도 있으면 pending
    statuses = {l["status"] for l in links}
    for s in ("pending", "approved", "rejected"):
        if s in statuses:
            return s
    return "unmatched"


def _score_gap(cands: list[dict]) -> int | None:  # 타자마다 1등−2등 점수 차 중 가장 작은 값 (작을수록 애매)
    gaps = []
    for batter in {c["batter"] for c in cands}:
        scores = [c["score"] for c in cands if c["batter"] == batter]
        if len(scores) >= 2:
            gaps.append(scores[0] - scores[1])
    return min(gaps) if gaps else None


@router.get("/video-links", summary="7. 장면 검수 목록")
def list_video_links(  # API 7: 장면 검수 화면
    status: Literal["pending", "approved", "rejected", "unmatched"] | None = Query(
        None, description="pending 대기 / approved 승인 / rejected 반려 / unmatched 연결 없음. 생략하면 전체"),
    sort: Literal["date", "ambiguity"] = Query("date", description="date 최근 경기부터 / ambiguity 애매한 것부터"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    videos = []
    for r in run(Q_VIDEO_LINKS):
        v, links = r["v"], r["links"]
        v["status"] = _video_status(links)
        v["links"] = links
        videos.append(v)
    if status:
        videos = [v for v in videos if v["status"] == status]

    # 애매함 정렬에 점수 차가 필요해서 후보는 걸러진 영상 전부에 대해 한 번에 부른다
    cands: dict[str, list] = {}
    for c in run(Q_CANDIDATES, ids=[v["video_id"] for v in videos]):
        cands.setdefault(c["video_id"], []).append(c)
    for v in videos:
        v["score_gap"] = _score_gap(cands.get(v["video_id"], []))

    if sort == "ambiguity":  # 점수 차 작은 것부터, 점수 차가 없는(후보 1개) 영상은 뒤로
        videos.sort(key=lambda v: (v["score_gap"] is None, v["score_gap"] or 0, v["game_date"] or ""))
    else:
        videos.sort(key=lambda v: v["game_date"] or "", reverse=True)

    page = videos[offset:offset + limit]
    return {
        "total": len(videos),
        "limit": limit,
        "offset": offset,
        "video_links": [
            {
                "video_id": v["video_id"],
                "title": v["title"],
                "game_date": v["game_date"],
                "duration_sec": v["duration_sec"],
                "status": v["status"],
                # 한 영상에 타자가 여럿이면 연결도 여럿 (예: "문성주 2타점과 김현수 스리런")
                "matched": [
                    {
                        "pa_id": l["pa_id"], "batter": l["batter"],
                        "summary": _summary(l["inning"], l["inning_half"], l["events"], l["runs"]),
                        "status": l["status"], "origin": l["origin"], "score": l["score"],
                        "reasons": l["reasons"], "reviewer": l["reviewer"], "reviewed_at": l["reviewed_at"],
                        "moved_to": l["moved_to"],
                    }
                    for l in v["links"]
                ],
                "candidates": [
                    {
                        "batter": c["batter"], "rank": c["rank"], "pa_id": c["pa_id"], "score": c["score"],
                        "reasons": c["reasons"],
                        "summary": _summary(c["inning"], c["inning_half"], c["events"], c["runs"]),
                    }
                    for c in cands.get(v["video_id"], [])
                ],
                "score_gap": v["score_gap"],
            }
            for v in page
        ],
    }


# ------------------------------------------------------------------ 8. 검수 저장
class ReviewBody(BaseModel):
    action: Literal["approve", "reject", "move"] = Field(description="approve 승인 / reject 반려 / move 다른 타석으로 옮김")
    reviewer: str = Field(min_length=1, description="검수자 이름")
    to_pa_id: str | None = Field(None, description="move일 때 옮길 타석 ID")


Q_LINK = """
MATCH (pa:PlateAppearance {pa_id: $pa})-[m:MATCHED_TO]->(v:VideoLink {video_id: $video})
RETURN m.status AS status
"""

Q_SET_STATUS = """
MATCH (:PlateAppearance {pa_id: $pa})-[m:MATCHED_TO]->(:VideoLink {video_id: $video})
SET m.status = $status, m.reviewer = $reviewer, m.reviewed_at = datetime(), m.moved_to = $moved_to
"""

# 옮길 타석에 연결이 이미 있으면(같은 영상의 다른 타자 연결 등) 승인으로 바꾸고, 없으면 직접 연결로 새로 만든다
Q_MOVE_TO = """
MATCH (pa:PlateAppearance {pa_id: $pa}), (v:VideoLink {video_id: $video})
MERGE (pa)-[m:MATCHED_TO]->(v)
ON CREATE SET m.origin = 'manual'
SET m.status = 'approved', m.reviewer = $reviewer, m.reviewed_at = datetime()
"""

Q_LINKS_OF = """
MATCH (pa:PlateAppearance)-[m:MATCHED_TO]->(v:VideoLink {video_id: $video})
WHERE pa.pa_id IN $pas
RETURN pa.pa_id AS pa_id, m.status AS status, m.origin AS origin, m.score AS score,
       m.reviewer AS reviewer, toString(m.reviewed_at) AS reviewed_at, m.moved_to AS moved_to
"""

Q_PA_EXISTS = "MATCH (pa:PlateAppearance {pa_id: $pa}) RETURN pa.pa_id AS pa_id"
Q_VIDEO_EXISTS = "MATCH (v:VideoLink {video_id: $video}) RETURN v.video_id AS video_id"


@router.patch("/video-links/{video_id}/plate-appearances/{pa_id}", summary="8. 검수 저장 (승인·반려·옮김)")
def review_link(video_id: str, pa_id: str, body: ReviewBody):  # API 8
    if not run(Q_LINK, pa=pa_id, video=video_id):
        raise ApiError(404, "LINK_NOT_FOUND", "이 영상과 타석의 연결이 없습니다")

    if body.action == "move":
        if not body.to_pa_id:
            raise ApiError(400, "INVALID_PARAM", "move에는 to_pa_id가 필요합니다")
        if body.to_pa_id == pa_id:
            raise ApiError(400, "INVALID_PARAM", "같은 타석으로는 옮길 수 없습니다")
        if not run(Q_PA_EXISTS, pa=body.to_pa_id):
            raise ApiError(404, "PA_NOT_FOUND", "옮길 타석을 찾을 수 없습니다")
        run(Q_SET_STATUS, pa=pa_id, video=video_id, status="rejected",
            reviewer=body.reviewer, moved_to=body.to_pa_id)
        run(Q_MOVE_TO, pa=body.to_pa_id, video=video_id, reviewer=body.reviewer)
        changed = [pa_id, body.to_pa_id]
    else:
        status = "approved" if body.action == "approve" else "rejected"
        run(Q_SET_STATUS, pa=pa_id, video=video_id, status=status, reviewer=body.reviewer, moved_to=None)
        changed = [pa_id]

    return {"video_id": video_id, "links": run(Q_LINKS_OF, video=video_id, pas=changed)}


# ------------------------------------------------------------------ 9. 직접 연결
class LinkBody(BaseModel):
    reviewer: str = Field(min_length=1, description="검수자 이름")


Q_CREATE_LINK = """
MATCH (pa:PlateAppearance {pa_id: $pa}), (v:VideoLink {video_id: $video})
CREATE (pa)-[:MATCHED_TO {status: 'approved', origin: 'manual', reviewer: $reviewer, reviewed_at: datetime()}]->(v)
"""


@router.post("/video-links/{video_id}/plate-appearances/{pa_id}", status_code=201,
             summary="9. 영상-타석 직접 연결")
def create_link(video_id: str, pa_id: str, body: LinkBody):  # API 9
    if not run(Q_VIDEO_EXISTS, video=video_id):
        raise ApiError(404, "VIDEO_NOT_FOUND", "영상을 찾을 수 없습니다")
    if not run(Q_PA_EXISTS, pa=pa_id):
        raise ApiError(404, "PA_NOT_FOUND", "타석을 찾을 수 없습니다")
    if run(Q_LINK, pa=pa_id, video=video_id):
        raise ApiError(409, "LINK_EXISTS", "이미 연결되어 있습니다. 상태 변경은 8번을 쓰세요")
    run(Q_CREATE_LINK, pa=pa_id, video=video_id, reviewer=body.reviewer)
    return {"video_id": video_id, "links": run(Q_LINKS_OF, video=video_id, pas=[pa_id])}


# ------------------------------------------------------------------ 10. 정확도
Q_STATS = """
MATCH (v:VideoLink)
OPTIONAL MATCH ()-[m:MATCHED_TO]->(v)
WITH v, collect(m) AS ms
RETURN count(v) AS videos,
       sum(CASE WHEN size(ms) = 0 THEN 1 ELSE 0 END) AS unmatched,
       sum(size([m IN ms WHERE m.origin = 'auto' AND m.status = 'pending'])) AS pending,
       sum(size([m IN ms WHERE m.origin = 'auto' AND m.status = 'approved'])) AS approved,
       sum(size([m IN ms WHERE m.origin = 'auto' AND m.status = 'rejected' AND m.moved_to IS NOT NULL])) AS moved,
       sum(size([m IN ms WHERE m.origin = 'auto' AND m.status = 'rejected' AND m.moved_to IS NULL])) AS rejected,
       sum(size([m IN ms WHERE m.origin = 'manual'])) AS manual
"""


@router.get("/video-links/stats", summary="10. 자동 연결 정확도")
def video_link_stats():  # API 10
    s = run(Q_STATS)[0]
    reviewed = s["approved"] + s["moved"] + s["rejected"]
    # 정확도 = 승인 ÷ (승인 + 옮김 + 반려). 자동 연결(origin auto)만 센다. 검수한 게 없으면 null
    s["accuracy"] = round(s["approved"] / reviewed, 3) if reviewed else None
    return s
