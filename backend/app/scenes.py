"""장면(영상) 연결 공통 — 여러 라우터가 같이 쓴다. 설계: docs/장면.md

확정 = auto_confirmed(자동 확정) 또는 approved(승인) (설계 D1). 화면에는 확정이고 재생 가능한 연결만 나온다.
"""
from .db import run

CONFIRMED = ["auto_confirmed", "approved"]
# 장면으로 보여 주는 타석 = 잘한 것만 (홈런 · 안타 · 볼넷 · 몸에 맞는 공, 장면.md S8). API-36 목록과 API-16 장면 수가 같이 쓴다
GOOD_EVENTS = ["home_run", "single", "double", "triple", "walk", "hit_by_pitch"]

# 경기마다 기본층 「이 경기 하이라이트」 = 확정·재생 가능한 연결 중 rank가 가장 앞선 것 (KBO 공식 > 티빙 > 구단)
Q_GAME_HIGHLIGHTS = """
UNWIND $games AS gpk
MATCH (g:Game {game_pk: gpk})
CALL (g) {
  MATCH (g)-[h:MATCHED_TO]->(v:VideoLink)
  WHERE h.status IN $confirmed AND coalesce(v.playable, true)
  RETURN v, h ORDER BY h.rank LIMIT 1
}
RETURN gpk AS game_pk, v.video_id AS video_id, v.title AS title, v.channel AS channel,
       v.duration_sec AS duration_sec, h.start_sec AS start_sec, h.end_sec AS end_sec
"""


# 등판마다 보너스층 장면 = 확정·재생 가능한 연결 중 rank가 가장 앞선 것 (자동 확정 > 클립 > 챕터, 07 match_outing)
Q_OUTING_SCENES = """
UNWIND $outings AS oid
MATCH (o:Outing {outing_id: oid})
CALL (o) {
  MATCH (o)-[m:MATCHED_TO]->(v:VideoLink)
  WHERE m.status IN $confirmed AND coalesce(v.playable, true)
  RETURN v, m ORDER BY m.rank LIMIT 1
}
RETURN oid AS outing_id, v.video_id AS video_id, v.title AS title, v.duration_sec AS duration_sec,
       m.start_sec AS start_sec, m.end_sec AS end_sec, m.precision AS precision, m.scene_type AS scene_type,
       coalesce(m.tags, []) AS tags
"""


# 타석(홈런 등) 장면 = 확정·재생 가능한 연결 중 rank가 가장 앞선 것. 경기 단위 영상은 타석 장면이 아니다 (API-05와 같은 기준)
Q_PA_SCENES = """
UNWIND $pas AS pid
MATCH (pa:PlateAppearance {pa_id: pid})
CALL (pa) {
  MATCH (pa)-[m:MATCHED_TO]->(v:VideoLink)
  WHERE m.status IN $confirmed AND coalesce(m.precision, 'scene') <> 'game' AND coalesce(v.playable, true)
  RETURN v, m ORDER BY m.rank, v.published_at LIMIT 1
}
RETURN pid AS pa_id, v.video_id AS video_id, v.title AS title, v.duration_sec AS duration_sec,
       m.start_sec AS start_sec, m.end_sec AS end_sec, coalesce(m.precision, 'scene') AS precision,
       m.scene_type AS scene_type, coalesce(m.tags, []) AS tags
"""


def scene_of(r: dict) -> dict:
    return {
        "video_id": r["video_id"], "title": r["title"], "duration_sec": r["duration_sec"],
        "start_sec": r["start_sec"] or 0, "end_sec": r["end_sec"], "precision": r["precision"],
        "scene_type": r["scene_type"], "tags": r["tags"],
    }


def outing_scenes(outing_ids: list[str]) -> dict[str, dict]:
    """등판 ID 목록 → {등판 ID: 장면}. 확정 장면이 없는 등판은 빠진다."""
    if not outing_ids:
        return {}
    return {r["outing_id"]: scene_of(r) for r in run(Q_OUTING_SCENES, outings=list(outing_ids), confirmed=CONFIRMED)}


def pa_scenes(pa_ids: list[str]) -> dict[str, dict]:
    """타석 ID 목록 → {타석 ID: 장면}. 확정 장면이 없는 타석은 빠진다."""
    if not pa_ids:
        return {}
    return {r["pa_id"]: scene_of(r) for r in run(Q_PA_SCENES, pas=list(pa_ids), confirmed=CONFIRMED)}


def game_highlights(game_pks: list[str]) -> dict[str, dict]:
    """경기 ID 목록 → {경기 ID: 하이라이트}. 하이라이트가 없는 경기는 빠진다."""
    if not game_pks:
        return {}
    return {
        r["game_pk"]: {
            "video_id": r["video_id"], "title": r["title"], "channel": r["channel"],
            "duration_sec": r["duration_sec"], "start_sec": r["start_sec"] or 0, "end_sec": r["end_sec"],
            "precision": "game",
        }
        for r in run(Q_GAME_HIGHLIGHTS, games=list(game_pks), confirmed=CONFIRMED)
    }
