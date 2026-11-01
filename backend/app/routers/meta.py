"""
상태 API — 설계 9장 공통
  20. GET /meta   기록 기준일 · 포스트시즌 기간인가 (메뉴줄 「7.26 기준」 · 메인 코너)
  데이터는 HF 고정본을 손으로 적재해 서버에 올린다 — 자동 갱신은 없다
"""
from fastapi import APIRouter

from ..db import run
from ..postseason import period

router = APIRouter(tags=["상태"])

Q_META = """
OPTIONAL MATCH (g:Game)
RETURN toString(max(g.date)) AS data_as_of, max(g.season) AS season
"""


@router.get("/meta", summary="20. 기록 기준일")
def get_meta():
    r = run(Q_META)[0]
    return {
        "data_as_of": r["data_as_of"],          # DB에 있는 마지막 경기일
        "season": r["season"],
        "postseason_active": period(r["season"])["active"] if r["season"] else False,
    }
