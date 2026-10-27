"""
상태 API — 설계 9장 공통
  20. GET /meta   기록 기준일 · 마지막 자동 갱신 · 포스트시즌 기간인가 (메뉴줄 「10.20 기준」 · 검수 화면 · 메인 코너)
  자동 갱신 칸(updated_at …)은 (:Meta {key: 'update'})가 있을 때만 찬다. 팀 저장소에는 자동 갱신이 아직 없어 null
"""
import json

from fastapi import APIRouter

from ..db import run
from ..postseason import period

router = APIRouter(tags=["상태"])

Q_META = """
OPTIONAL MATCH (g:Game)
WITH max(g.date) AS last_date, max(g.season) AS season
OPTIONAL MATCH (m:Meta {key: 'update'})
RETURN toString(last_date) AS data_as_of, season, m {.*} AS m
"""


@router.get("/meta", summary="20. 기록 기준일 · 마지막 갱신")
def get_meta():
    r = run(Q_META)[0]
    m = r["m"] or {}
    warnings = m.get("warnings")
    return {
        "data_as_of": r["data_as_of"],          # DB에 있는 마지막 경기일
        "season": r["season"],
        "updated_at": m.get("updated_at"),      # 마지막 자동 갱신. 한 번도 안 돌았으면 null
        "last_status": m.get("last_status"),    # ok · partial(일부 경기 · 영상 건너뜀) · failed
        "failed_step": m.get("failed_step") if m.get("last_status") == "failed" else None,
        "new_games": m.get("new_games"),
        "new_scenes": m.get("new_scenes"),
        "warnings": json.loads(warnings) if isinstance(warnings, str) else (warnings or []),
        "postseason_active": period(r["season"])["active"] if r["season"] else False,
    }
