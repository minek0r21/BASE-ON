"""
관리자 검수 API — 연결 대상 셋(경기·타석·등판) 공통. 설계: docs/장면.md 7장, 설계.md 6-4·8-4
  GET   /admin/review/queue?target_kind=&reason=&season=&limit=&offset=   검수 대기 연결 (연결 하나 = 한 줄)
  PATCH /admin/review/{target_kind}/{target_id}/videos/{video_id}         승인 · 반려 · 구간 고쳐 승인(retime)
  GET   /admin/review/stats                                               대상별·상태별 개수, 자동 연결 정확도

인증 (설계 6-4): 환경변수 ADMIN_TOKENS="이름1:토큰1,이름2:토큰2"가 있으면 Authorization: Bearer <토큰>이 필요하고
검수자 이름은 토큰으로 정한다. 없으면(로컬 개발) 인증 없이 본문의 reviewer를 쓴다.
"""
import hashlib
import os
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field

from ..db import run
from ..errors import ApiError
from ..videocheck import apply_verdict, check_videos

router = APIRouter(tags=["관리자 검수"])

TargetKind = Literal["game", "pa", "outing"]
TARGETS = {"game": ("Game", "game_pk"), "pa": ("PlateAppearance", "pa_id"), "outing": ("Outing", "outing_id")}


def _tokens() -> dict[str, str]:
    raw = os.getenv("ADMIN_TOKENS", "")
    return {tok.strip(): name.strip() for name, _, tok in (p.partition(":") for p in raw.split(",")) if tok.strip()}


def require_admin(authorization: str | None = Header(None)) -> str | None:
    """토큰이 설정돼 있으면 검사하고 검수자 이름을 돌려준다. 설정이 없으면 None (로컬 개발)"""
    tokens = _tokens()
    if not tokens:
        return None
    given = (authorization or "").removeprefix("Bearer ").strip()
    for tok, name in tokens.items():
        if secrets.compare_digest(given, tok):
            return name
    raise ApiError(401, "UNAUTHORIZED", "관리자 토큰이 필요합니다")


# ------------------------------------------------------------------ 검수 대기 목록
# 대상마다 「누구의 언제 무슨 기록인지」 요약. 라벨은 TARGETS 표에서만 온다 (사용자 입력 아님)
Q_QUEUE = {
    "game": """
MATCH (g:Game)-[m:MATCHED_TO]->(v:VideoLink)
WHERE m.status = $status AND ($season IS NULL OR g.season = $season) AND ($reason IS NULL OR m.review_reason = $reason)
MATCH (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
RETURN 'game' AS target_kind, g.game_pk AS target_id, toString(g.date) AS date,
       away.name + ' vs ' + home.name + CASE WHEN g.dh_no > 0 THEN ' (DH' + toString(g.dh_no) + ')' ELSE '' END AS summary,
       m {.status, .origin, .scene_type, .precision, .start_sec, .end_sec, .score, .reasons, .review_reason, .tags} AS m,
       v {.video_id, .title, .channel, .kind, .duration_sec} AS v,
       COUNT { (g)-[:MATCHED_TO|CANDIDATE]->(c:VideoLink) WHERE c <> v AND coalesce(c.playable, true) } AS alt
""",
    "pa": """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance)-[m:MATCHED_TO]->(v:VideoLink)
WHERE m.status = $status AND ($season IS NULL OR pa.season = $season) AND ($reason IS NULL OR m.review_reason = $reason)
RETURN 'pa' AS target_kind, pa.pa_id AS target_id, toString(pa.date) AS date,
       b.name + ' · ' + toString(pa.inning) + '회' + pa.inning_half + ' ' + pa.events
         + CASE WHEN pa.hr_seq IS NULL THEN '' ELSE ' (' + toString(pa.hr_seq) + '호)' END AS summary,
       m {.status, .origin, .scene_type, .precision, .start_sec, .end_sec, .score, .reasons, .review_reason, .tags} AS m,
       v {.video_id, .title, .channel, .kind, .duration_sec} AS v,
       COUNT { (pa)-[:CANDIDATE]->(c:VideoLink) WHERE c <> v AND coalesce(c.playable, true) } AS alt
""",
    "outing": """
MATCH (p:Player)-[:PITCHED_GAME]->(o:Outing)-[m:MATCHED_TO]->(v:VideoLink)
WHERE m.status = $status AND ($season IS NULL OR o.season = $season) AND ($reason IS NULL OR m.review_reason = $reason)
RETURN 'outing' AS target_kind, o.outing_id AS target_id, o.date AS date,
       p.name + ' · ' + CASE WHEN o.starter THEN '선발 ' ELSE '구원 ' END
         + toString(o.outs / 3) + CASE o.outs % 3 WHEN 1 THEN '⅓' WHEN 2 THEN '⅔' ELSE '' END + '이닝 '
         + toString(o.so) + 'K ' + toString(o.r) + '실점' AS summary,
       m {.status, .origin, .scene_type, .precision, .start_sec, .end_sec, .score, .reasons, .review_reason, .tags} AS m,
       v {.video_id, .title, .channel, .kind, .duration_sec} AS v,
       COUNT { (o)-[:CANDIDATE]->(c:VideoLink) WHERE c <> v AND coalesce(c.playable, true) } AS alt
""",
}


@router.get("/admin/review/queue", summary="7'. 검수 대기 연결 / 자동 확정 표본 (경기·타석·등판)")
def review_queue(
    target_kind: TargetKind | None = Query(None, description="game 경기 / pa 타석 / outing 등판. 생략하면 전체"),
    reason: str | None = Query(None, description="검수 이유 (ambiguous · no_title_date · claim_mismatch · neutral …)"),
    season: int | None = Query(None),
    status: Literal["pending", "auto_confirmed"] = Query(
        "pending", description="pending 검수 대기 / auto_confirmed 자동 확정 표본 확인 (NFR-07: 무작위 표본에서 오매칭 세기)"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _reviewer: str | None = Depends(require_admin),
):
    rows = []
    for kind in ([target_kind] if target_kind else list(TARGETS)):
        rows += run(Q_QUEUE[kind], season=season, reason=reason, status=status)
    if status == "auto_confirmed":
        # 표본: 고정된 무작위 순서 (같은 표본을 여러 번에 나눠 확인할 수 있게, 연결 ID의 해시 순)
        rows.sort(key=lambda r: hashlib.sha1(f"{r['target_id']}|{r['v']['video_id']}".encode()).hexdigest())
    else:
        rows.sort(key=lambda r: (r["date"] or "", r["target_id"]), reverse=True)  # 최근 경기부터
    counts: dict = {}
    for r in rows:
        k = (r["target_kind"], r["m"]["review_reason"] or "-")
        counts[k] = counts.get(k, 0) + 1
    return {
        "total": len(rows), "limit": limit, "offset": offset,
        "counts": [{"target_kind": k, "reason": r, "n": n} for (k, r), n in sorted(counts.items())],
        "items": [
            {"target_kind": r["target_kind"], "target_id": r["target_id"], "date": r["date"], "summary": r["summary"],
             "video": r["v"], "alt": r["alt"], **r["m"]}
            for r in rows[offset:offset + limit]
        ],
    }


# ------------------------------------------------------------------ 검수 저장
class ReviewAction(BaseModel):
    action: Literal["approve", "reject", "retime", "move"] = Field(
        description="approve 승인 / reject 반려 / retime 구간 고쳐 승인 / move 같은 종류의 다른 대상으로 옮김")
    reviewer: str | None = Field(None, description="검수자 이름 (토큰 인증을 쓰면 무시하고 토큰의 이름)")
    start_sec: int | None = Field(None, ge=0, description="retime: 새 시작 초")
    end_sec: int | None = Field(None, ge=1, description="retime: 새 종료 초")
    to_target_id: str | None = Field(None, description="move: 옮길 대상 ID (같은 종류 — 타석이면 pa_id)")


# 옮김: 원래 연결은 반려 + moved_to, 옮길 대상에는 원래 연결의 장면 종류·정밀도·구간을 그대로 승인 연결로 (origin manual).
# 08을 다시 돌려도 둘 다 남는다 (08은 자동 연결 중 pending·auto_confirmed만 지운다)
Q_MOVE = """
MATCH (:{label} {{{key}: $t}})-[src:MATCHED_TO]->(v:VideoLink {{video_id: $v}}), (dst:{label} {{{key}: $to}})
MERGE (dst)-[m:MATCHED_TO]->(v)
ON CREATE SET m.origin = 'manual', m.scene_type = src.scene_type, m.precision = src.precision,
              m.start_sec = src.start_sec, m.end_sec = src.end_sec, m.tags = coalesce(src.tags, []), m.rank = src.rank,
              m.reasons = '옮김 ← ' + $t
SET m.status = 'approved', m.reviewer = $reviewer, m.reviewed_at = datetime(),
    src.status = 'rejected', src.moved_to = $to, src.reviewer = $reviewer, src.reviewed_at = datetime()
"""


@router.patch("/admin/review/{target_kind}/{target_id}/videos/{video_id}", summary="8'. 검수 저장 (경기·타석·등판)")
def review_save(target_kind: TargetKind, target_id: str, video_id: str, body: ReviewAction,
                token_reviewer: str | None = Depends(require_admin)):
    label, key = TARGETS[target_kind]
    reviewer = token_reviewer or body.reviewer
    if not reviewer:
        raise ApiError(400, "INVALID_PARAM", "검수자 이름이 필요합니다")
    found = run(f"MATCH (:{label} {{{key}: $t}})-[m:MATCHED_TO]->(v:VideoLink {{video_id: $v}}) "
                "RETURN m.status AS status, v.duration_sec AS duration, coalesce(v.playable, true) AS playable",
                t=target_id, v=video_id)
    if not found:
        raise ApiError(404, "LINK_NOT_FOUND", "이 대상과 영상의 연결이 없습니다")
    if body.action != "reject" and not found[0]["playable"]:
        # 「영상 소실」 연결 승인: 지금 다시 확인해서 재생되면 playable을 되돌리고 승인, 아니면 막는다 (설계 8-3)
        verdict = check_videos([video_id])[video_id]
        if verdict != "ok":
            raise ApiError(409, "VIDEO_UNPLAYABLE", "영상이 아직 재생되지 않습니다 (삭제·비공개·임베드 막힘). 반려하거나 나중에 다시 승인하세요"
                           if verdict == "unplayable" else "지금 영상 상태를 확인할 수 없습니다 (YouTube 키·API 오류)")
        apply_verdict(video_id, verdict)
    params = {"t": target_id, "v": video_id, "reviewer": reviewer}
    if body.action == "move":
        to = body.to_target_id
        if not to or to == target_id:
            raise ApiError(400, "INVALID_PARAM", "move에는 지금 대상과 다른 to_target_id가 필요합니다")
        if not run(f"MATCH (x:{label} {{{key}: $to}}) RETURN 1 AS ok", to=to):
            raise ApiError(404, "TARGET_NOT_FOUND", "옮길 대상을 찾을 수 없습니다")
        run(Q_MOVE.format(label=label, key=key), to=to, **params)
        moved = run(f"MATCH (:{label} {{{key}: $to}})-[m:MATCHED_TO]->(:VideoLink {{video_id: $v}}) "
                    "RETURN m {.status, .precision, .start_sec, .end_sec, .reviewer, reviewed_at: toString(m.reviewed_at)} AS m",
                    to=to, v=video_id)[0]["m"]
        return {"target_kind": target_kind, "target_id": target_id, "video_id": video_id, "status": "rejected",
                "moved_to": {"target_id": to, **moved}}
    if body.action == "retime":
        dur = found[0]["duration"]
        if body.start_sec is None or body.end_sec is None or body.end_sec <= body.start_sec \
                or (dur and body.end_sec > dur):
            raise ApiError(400, "INVALID_PARAM", "retime에는 0 ≤ start_sec < end_sec ≤ 영상 길이가 필요합니다")
        # 구간을 사람이 고쳤으면 그 장면 정밀도로 본다 (설계 7-4: 검수에서 맞으면 scene)
        q = (f"MATCH (:{label} {{{key}: $t}})-[m:MATCHED_TO]->(:VideoLink {{video_id: $v}}) "
             "SET m.status = 'approved', m.start_sec = $s, m.end_sec = $e, "
             "m.precision = CASE WHEN m.precision = 'game' THEN 'game' ELSE 'scene' END, "
             "m.reviewer = $reviewer, m.reviewed_at = datetime()")
        run(q, s=body.start_sec, e=body.end_sec, **params)
    else:
        status = "approved" if body.action == "approve" else "rejected"
        run(f"MATCH (:{label} {{{key}: $t}})-[m:MATCHED_TO]->(:VideoLink {{video_id: $v}}) "
            "SET m.status = $status, m.reviewer = $reviewer, m.reviewed_at = datetime()", status=status, **params)
    after = run(f"MATCH (:{label} {{{key}: $t}})-[m:MATCHED_TO]->(:VideoLink {{video_id: $v}}) "
                "RETURN m {.status, .precision, .start_sec, .end_sec, .reviewer, reviewed_at: toString(m.reviewed_at)} AS m",
                t=target_id, v=video_id)[0]["m"]
    return {"target_kind": target_kind, "target_id": target_id, "video_id": video_id, **after}


# ------------------------------------------------------------------ 옮길 후보
# 타석: 같은 경기의 그 타자 다른 타석 + 그 영상의 매칭 후보(CANDIDATE, 다른 타자 포함)
# 등판: 같은 투수의 앞뒤 7일 등판 + 같은 경기의 다른 투수 / 경기: 같은 날 다른 경기(더블헤더)
Q_CAND = {
    "pa": """
MATCH (b:Player)-[:BATTED_IN]->(src:PlateAppearance {pa_id: $t})-[:PART_OF]->(g:Game)
CALL (b, g, src) {
  MATCH (b)-[:BATTED_IN]->(x:PlateAppearance)-[:PART_OF]->(g) WHERE x <> src RETURN x, '같은 경기 다른 타석' AS why
  UNION
  MATCH (x:PlateAppearance)-[c:CANDIDATE]->(:VideoLink {video_id: $v}) WHERE x <> src RETURN x, '영상 매칭 후보' AS why
}
WITH DISTINCT x, collect(why)[0] AS why
MATCH (xb:Player)-[:BATTED_IN]->(x), (pit:Player)-[:PITCHED_IN]->(x)
RETURN x.pa_id AS target_id, toString(x.date) AS date, why,
       xb.name + ' · ' + toString(x.inning) + '회' + x.inning_half + ' ' + x.events
         + CASE WHEN x.hr_seq IS NULL THEN '' ELSE ' (' + toString(x.hr_seq) + '호)' END + ' · 투수 ' + pit.name AS summary
ORDER BY why, x.date, x.at_bat_number
""",
    "outing": """
MATCH (p:Player)-[:PITCHED_GAME]->(src:Outing {outing_id: $t})-[:PART_OF]->(g:Game)
CALL (p, g, src) {
  MATCH (p)-[:PITCHED_GAME]->(x:Outing) WHERE x <> src AND abs(duration.inDays(date(x.date), date(src.date)).days) <= 7
  RETURN x, '같은 투수 앞뒤 7일' AS why
  UNION
  MATCH (x:Outing)-[:PART_OF]->(g) WHERE x <> src RETURN x, '같은 경기 다른 투수' AS why
}
MATCH (xp:Player)-[:PITCHED_GAME]->(x)
RETURN x.outing_id AS target_id, x.date AS date, why,
       xp.name + ' · ' + CASE WHEN x.starter THEN '선발 ' ELSE '구원 ' END
         + toString(x.outs / 3) + CASE x.outs % 3 WHEN 1 THEN '⅓' WHEN 2 THEN '⅔' ELSE '' END + '이닝 '
         + toString(x.so) + 'K ' + toString(x.r) + '실점' AS summary
ORDER BY why, x.date
""",
    "game": """
MATCH (src:Game {game_pk: $t})
MATCH (x:Game) WHERE x <> src AND x.date = src.date
MATCH (x)-[:HOME]->(home:Team), (x)-[:AWAY]->(away:Team)
RETURN x.game_pk AS target_id, toString(x.date) AS date, '같은 날 다른 경기' AS why,
       away.name + ' vs ' + home.name + CASE WHEN x.dh_no > 0 THEN ' (DH' + toString(x.dh_no) + ')' ELSE '' END AS summary
ORDER BY summary
""",
}


@router.get("/admin/review/{target_kind}/{target_id}/videos/{video_id}/move-candidates", summary="8''. 옮길 후보")
def move_candidates(target_kind: TargetKind, target_id: str, video_id: str, _reviewer: str | None = Depends(require_admin)):
    return {"candidates": run(Q_CAND[target_kind], t=target_id, v=video_id)}


# ------------------------------------------------------------------ 통계
Q_STATS = """
MATCH (t)-[m:MATCHED_TO]->(:VideoLink)
RETURN labels(t)[0] AS label, m.status AS status, m.origin AS origin, count(*) AS n
"""
LABEL_KIND = {label: kind for kind, (label, _) in TARGETS.items()}
# Gemini 제안 정확도: 제안을 보고 표시한 장면에서 사람이 시작 시각을 몇 초 옮겼나 (장면.md 11-5)
Q_GEMINI_SHIFT = """
MATCH (:PlateAppearance)-[m:MATCHED_TO {origin: 'gemini_manual'}]->(:VideoLink)
WITH abs(m.start_sec - m.suggested_sec) AS d
RETURN count(*) AS n, avg(d) AS avg_shift, sum(CASE WHEN d <= 5 THEN 1 ELSE 0 END) AS within5
"""


@router.get("/admin/review/stats", summary="10'. 검수 통계 (대상별·상태별)")
def review_stats(_reviewer: str | None = Depends(require_admin)):
    by: dict = {}
    for r in run(Q_STATS):
        kind = LABEL_KIND.get(r["label"])
        if not kind:
            continue
        d = by.setdefault(kind, {"pending": 0, "auto_confirmed": 0, "approved": 0, "rejected": 0, "manual": 0,
                                 "auto_reviewed_ok": 0, "auto_reviewed_ng": 0})
        d[r["status"]] = d.get(r["status"], 0) + r["n"]
        if r["origin"] in ("manual", "gemini_manual"):  # gemini_manual = Gemini 제안을 사람이 보고 표시
            d["manual"] += r["n"]
            if r["origin"] == "gemini_manual":
                d["gemini_manual"] = d.get("gemini_manual", 0) + r["n"]
        elif r["status"] == "approved":
            d["auto_reviewed_ok"] += r["n"]
        elif r["status"] == "rejected":
            d["auto_reviewed_ng"] += r["n"]
    for d in by.values():  # 정확도 = 자동 연결 중 검수에서 승인된 비율 (검수한 것만)
        done = d["auto_reviewed_ok"] + d["auto_reviewed_ng"]
        d["accuracy"] = round(d["auto_reviewed_ok"] / done, 3) if done else None
    g = run(Q_GEMINI_SHIFT)[0]
    if g["n"]:
        by.setdefault("pa", {})["gemini"] = {"marked": g["n"], "avg_shift": round(g["avg_shift"], 1), "within5": g["within5"]}
    return by


# ------------------------------------------------------------------ 수동 표시 (시안 검수 「수동 표시」 큐)
# 정규시즌 홈런 중 장면(scene) 연결이 없고 「영상에 없음」으로 표시하지 않은 것. 경기 하이라이트를 틀어 그 순간을 표시한다
Q_MISSING_HR = """
MATCH (b:Player)-[:BATTED_IN]->(pa:PlateAppearance {season: $season, events: 'home_run', game_type: 'regular'})-[:PART_OF]->(g:Game)
WHERE NOT coalesce(pa.no_video, false)
  AND NOT EXISTS { (pa)-[m:MATCHED_TO]->() WHERE m.status IN ['auto_confirmed', 'approved'] AND coalesce(m.precision, 'scene') = 'scene' }
MATCH (pit:Player)-[:PITCHED_IN]->(pa), (g)-[:HOME]->(home:Team), (g)-[:AWAY]->(away:Team)
// Gemini 제안 시각 (etl/09_suggest_times.py, 장면.md 11-5) — 찾음 · 강함부터 하나. 사용자 화면은 SUGGESTED를 읽지 않는다
CALL (pa) {
  OPTIONAL MATCH (pa)-[s:SUGGESTED]->(sv:VideoLink)
  RETURN s, sv ORDER BY s.found DESC, CASE s.strength WHEN 'strong' THEN 0 ELSE 1 END LIMIT 1
}
RETURN pa.pa_id AS pa_id, toString(pa.date) AS date, g.game_pk AS game_pk, b.name AS batter, pit.name AS pitcher,
       pa.inning AS inning, pa.inning_half AS half, pa.hr_seq AS hr_seq, pa.runs_scored AS runs,
       pa.on_1b AS on_1b, pa.on_2b AS on_2b, pa.on_3b AS on_3b, pa.outs_when_up AS outs,
       pa.final_balls AS balls, pa.final_strikes AS strikes, away.name + ' vs ' + home.name AS game,
       EXISTS { (pa)-[x:MATCHED_TO {status: 'pending'}]->() } AS has_pending,
       CASE WHEN s IS NULL THEN null ELSE {
         video_id: sv.video_id, title: sv.title, channel: sv.channel, duration_sec: sv.duration_sec,
         found: s.found, t_sec: s.t_sec, start_sec: s.start_sec, end_sec: s.end_sec,
         strength: s.strength, checks: s.checks, evidence: s.evidence, model: s.model } END AS suggestion
// 제안이 강한 것 → 약한 것 → 제안 없음 → 「영상에 없음」 후보 순, 그 안에서는 최근 경기부터
ORDER BY CASE WHEN s IS NULL THEN 2 WHEN NOT s.found THEN 3 WHEN s.strength = 'strong' THEN 0 ELSE 1 END,
         pa.date DESC, pa.at_bat_number DESC
"""
Q_HR_GOAL = """
MATCH (pa:PlateAppearance {season: $season, events: 'home_run', game_type: 'regular'})
RETURN count(pa) AS total,
       count(CASE WHEN EXISTS { (pa)-[m:MATCHED_TO]->() WHERE m.status IN ['auto_confirmed', 'approved'] AND coalesce(m.precision, 'scene') = 'scene' } THEN 1 END) AS done
"""
HR_GOAL = 0.70  # NFR-06


@router.get("/admin/review/missing-hr", summary="11-2. 장면 없는 홈런 (수동 표시 큐) · 홈런 장면 목표")
def missing_hr(season: int = Query(..., description="시즌"), limit: int = Query(50, ge=1, le=500),
               _reviewer: str | None = Depends(require_admin)):
    from ..scenes import game_highlights
    rows = run(Q_MISSING_HR, season=season)
    goal = run(Q_HR_GOAL, season=season)[0]
    items = rows[:limit]
    hl = game_highlights(list({r["game_pk"] for r in items}))
    return {"season": season, "goal": {**goal, "target": round(goal["total"] * HR_GOAL), "rate": HR_GOAL},
            "total": len(rows), "items": [{**r, "highlight": hl.get(r["game_pk"])} for r in items]}


class ManualMark(BaseModel):
    pa_id: str
    video_id: str
    start_sec: int = Field(ge=0)
    end_sec: int | None = Field(None, ge=1, description="생략하면 시작 + 20초 (영상 길이를 넘지 않게)")
    reviewer: str | None = None
    suggested_sec: int | None = Field(None, ge=0, description="Gemini 제안 시작 초를 보고 표시했으면 그 값 (제안 정확도 측정)")


@router.post("/admin/review/manual", summary="12-2. 재생 시각으로 장면 표시 (수동 연결)")
def manual_mark(body: ManualMark, token_reviewer: str | None = Depends(require_admin)):
    reviewer = token_reviewer or body.reviewer
    if not reviewer:
        raise ApiError(400, "INVALID_PARAM", "검수자 이름이 필요합니다")
    v = run("MATCH (v:VideoLink {video_id: $v}) RETURN v.duration_sec AS d", v=body.video_id)
    if not v:
        raise ApiError(404, "VIDEO_NOT_FOUND", "영상을 찾을 수 없습니다")
    dur = v[0]["d"] or 10 ** 6
    end = min(body.end_sec or body.start_sec + 20, dur)
    if end <= body.start_sec:
        raise ApiError(400, "INVALID_PARAM", "시작 시각이 영상 길이를 넘습니다")
    r = run("""
MATCH (pa:PlateAppearance {pa_id: $pa}), (v:VideoLink {video_id: $v})
MERGE (pa)-[m:MATCHED_TO]->(v)
SET m.status = 'approved', m.origin = $origin, m.suggested_sec = $sug, m.precision = 'scene', m.start_sec = $s, m.end_sec = $e,
    m.scene_type = CASE pa.events WHEN 'home_run' THEN 'home_run' ELSE 'hit' END, m.rank = 0, m.tags = coalesce(m.tags, []),
    m.reasons = '수동 표시', m.reviewer = $reviewer, m.reviewed_at = datetime()
RETURN m {.status, .start_sec, .end_sec} AS m""", pa=body.pa_id, v=body.video_id, s=body.start_sec, e=end, reviewer=reviewer,
            origin="gemini_manual" if body.suggested_sec is not None else "manual", sug=body.suggested_sec)
    if not r:
        raise ApiError(404, "TARGET_NOT_FOUND", "타석을 찾을 수 없습니다")
    return {"pa_id": body.pa_id, "video_id": body.video_id, **r[0]["m"]}


class NoVideo(BaseModel):
    pa_id: str
    reviewer: str | None = None


@router.post("/admin/review/no-video", summary="12-3. 이 홈런은 영상에 없음")
def no_video(body: NoVideo, token_reviewer: str | None = Depends(require_admin)):
    reviewer = token_reviewer or body.reviewer
    if not reviewer:
        raise ApiError(400, "INVALID_PARAM", "검수자 이름이 필요합니다")
    r = run("MATCH (pa:PlateAppearance {pa_id: $pa}) SET pa.no_video = true, pa.no_video_by = $reviewer, "
            "pa.no_video_at = datetime() RETURN pa.pa_id AS id", pa=body.pa_id, reviewer=reviewer)
    if not r:
        raise ApiError(404, "TARGET_NOT_FOUND", "타석을 찾을 수 없습니다")
    return {"pa_id": body.pa_id, "no_video": True}


class Swap(BaseModel):
    reviewer: str | None = None


@router.post("/admin/review/{target_kind}/{target_id}/videos/{video_id}/swap", summary="8-3. 교체 후보로 바꾸기 (영상 소실)")
def swap(target_kind: TargetKind, target_id: str, video_id: str, body: Swap, token_reviewer: str | None = Depends(require_admin)):
    """이 연결은 반려하고, 같은 대상의 다른 후보(재생 가능, 점수 높은 것) 하나를 승인 연결로"""
    label, key = TARGETS[target_kind]
    reviewer = token_reviewer or body.reviewer
    if not reviewer:
        raise ApiError(400, "INVALID_PARAM", "검수자 이름이 필요합니다")
    r = run(f"""
MATCH (t:{label} {{{key}: $t}})-[src:MATCHED_TO]->(old:VideoLink {{video_id: $v}})
MATCH (t)-[c:MATCHED_TO|CANDIDATE]->(nv:VideoLink) WHERE nv <> old AND coalesce(nv.playable, true)
WITH t, src, nv, c ORDER BY CASE type(c) WHEN 'MATCHED_TO' THEN 0 ELSE 1 END, coalesce(c.score, 0) DESC
LIMIT 1
MERGE (t)-[m:MATCHED_TO]->(nv)
ON CREATE SET m.origin = 'manual', m.scene_type = src.scene_type, m.precision = src.precision, m.start_sec = 0,
              m.end_sec = nv.duration_sec, m.tags = coalesce(src.tags, []), m.rank = src.rank, m.reasons = '교체 ← ' + $v
SET m.status = 'approved', m.reviewer = $reviewer, m.reviewed_at = datetime(),
    src.status = 'rejected', src.replaced_by = nv.video_id, src.reviewer = $reviewer, src.reviewed_at = datetime()
RETURN nv.video_id AS video_id, nv.title AS title""", t=target_id, v=video_id, reviewer=reviewer)
    if not r:
        raise ApiError(404, "NO_CANDIDATE", "바꿀 후보 영상이 없습니다")
    return {"target_kind": target_kind, "target_id": target_id, "replaced": video_id, **r[0]}
