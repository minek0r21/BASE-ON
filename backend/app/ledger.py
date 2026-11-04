"""
사람 판정 장부 (docs/장면.md 11-6) — 검수 화면에서 사람이 한 판정을 한 줄씩 남기고, DB를 다시 만든 뒤 그대로 다시 적용한다.
지금까지는 사람 판정이 DB에만 있어서 00 · 01부터 다시 적재하면 사라졌다 (08은 자동 연결만 지우므로 08만 돌리면 남는다).

    docker compose exec api python -m app.ledger export   # 지금 DB의 사람 판정을 장부로 (처음 한 번 — 장부가 비어 있을 때만)
    docker compose exec api python -m app.ledger replay   # 장부를 순서대로 다시 적용 (여러 번 돌려도 같다)

- 한 줄 = 판정 직후 그 연결의 상태 그대로(스냅숏). 다시 적용은 「그 상태로 맞추기」라 순서대로 덮어쓰면 된다
- 파일: 환경변수 REVIEW_LEDGER (로컬 docker-compose.yml이 data/review/decisions.jsonl을 연결, git 제외).
  없으면(서버) 남기지 않는다 — 검수는 PC에서 하고 deploy.py db로 서버에 올린다
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .db import run

TARGETS = {"game": ("Game", "game_pk"), "pa": ("PlateAppearance", "pa_id"), "outing": ("Outing", "outing_id")}
LINK_KEYS = ["status", "origin", "scene_type", "precision", "start_sec", "end_sec", "rank", "tags", "reasons",
             "review_reason", "reviewed_from", "moved_to", "replaced_by", "suggested_sec", "reviewer"]
Q_LINK = "MATCH (:{label} {{{key}: $t}})-[m:MATCHED_TO]->(:VideoLink {{video_id: $v}}) RETURN properties(m) AS m"


def path() -> Path | None:
    p = os.environ.get("REVIEW_LEDGER")
    return Path(p) if p else None


def _append(rows: list[dict]):
    p = path()
    if not p or not rows:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_links(action: str, links: list[tuple[str, str, str]]):
    """판정 뒤 (target_kind, target_id, video_id) 연결들의 상태를 그대로 남긴다"""
    if not path():
        return
    rows = []
    for kind, t, v in links:
        label, key = TARGETS[kind]
        found = run(Q_LINK.format(label=label, key=key), t=t, v=v)
        if found:
            m = dict(found[0]["m"])
            rows.append({"at": _now(), "action": action, "target_kind": kind, "target_id": t, "video_id": v,
                         "link": {k: m.get(k) for k in LINK_KEYS}})
    _append(rows)


def record_no_video(pa_id: str, reviewer: str):
    _append([{"at": _now(), "action": "no_video", "target_kind": "pa", "target_id": pa_id, "reviewer": reviewer}])


# ------------------------------------------------------------------ 다시 적용 · 내보내기
def _apply(r: dict) -> bool:
    if r["action"] == "no_video":
        return bool(run("MATCH (pa:PlateAppearance {pa_id: $t}) SET pa.no_video = true, pa.no_video_by = $by, "
                        "pa.no_video_at = datetime($at) RETURN 1 AS ok", t=r["target_id"], by=r.get("reviewer"), at=r["at"]))
    label, key = TARGETS[r["target_kind"]]
    # SET m += map: 값이 null인 칸은 지운다 → 판정 직후 상태와 똑같아진다
    return bool(run(f"MATCH (t:{label} {{{key}: $t}}), (v:VideoLink {{video_id: $v}}) MERGE (t)-[m:MATCHED_TO]->(v) "
                    "SET m += $link, m.reviewed_at = datetime($at) RETURN 1 AS ok",
                    t=r["target_id"], v=r["video_id"], link=r["link"], at=r["at"]))


def replay() -> tuple[int, int]:
    p = path()
    if not p or not p.exists():
        sys.exit("장부가 없다 (REVIEW_LEDGER)")
    done = missing = 0
    with open(p, encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
        if line.strip():
            if _apply(json.loads(line)):
                done += 1
            else:
                missing += 1  # 대상이나 영상이 DB에 없음 (데이터를 다른 범위로 적재했을 때)
    return done, missing


Q_EXPORT = """
MATCH (t)-[m:MATCHED_TO]->(v:VideoLink) WHERE m.reviewer IS NOT NULL
RETURN labels(t)[0] AS label, CASE WHEN t:PlateAppearance THEN t.pa_id WHEN t:Outing THEN t.outing_id ELSE t.game_pk END AS t,
       v.video_id AS v,
       toString(m.reviewed_at) AS at, properties(m) AS m
"""


def export() -> int:
    p = path()
    if not p:
        sys.exit("REVIEW_LEDGER가 없다")
    if p.exists() and p.stat().st_size:
        sys.exit(f"장부가 이미 있다 ({p}) — 내보내기는 처음 한 번만")
    kinds = {label: kind for kind, (label, _) in TARGETS.items()}
    rows = [{"at": r["at"], "action": "export", "target_kind": kinds[r["label"]], "target_id": r["t"], "video_id": r["v"],
             "link": {k: dict(r["m"]).get(k) for k in LINK_KEYS}} for r in run(Q_EXPORT) if r["label"] in kinds]
    rows += [{"at": r["at"], "action": "no_video", "target_kind": "pa", "target_id": r["t"], "reviewer": r["by"]}
             for r in run("MATCH (pa:PlateAppearance) WHERE pa.no_video RETURN pa.pa_id AS t, pa.no_video_by AS by, "
                          "toString(pa.no_video_at) AS at")]
    _append(sorted(rows, key=lambda r: r["at"] or ""))
    return len(rows)


if __name__ == "__main__":
    from . import db

    db.connect()
    try:
        cmd = sys.argv[1] if len(sys.argv) > 1 else ""
        if cmd == "export":
            print(f"사람 판정 {export()}줄을 장부에 남김 → {path()}")
        elif cmd == "replay":
            done, missing = replay()
            print(f"다시 적용 {done}줄 · 대상 없음 {missing}줄")
        else:
            sys.exit(__doc__)
    finally:
        db.close()
