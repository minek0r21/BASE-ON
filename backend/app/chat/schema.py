"""
DB에 실제로 들어 있는 값을 뽑아 schema_values.json으로 저장한다 (LLM 프롬프트 · Cypher 직접 방식용, 챗봇 2단계).
    docker compose exec api python -m app.chat.schema
"""
import json
from pathlib import Path

from .. import db

OUT = Path(__file__).with_name("schema_values.json")
Q = {
    "events": "MATCH (pa:PlateAppearance) RETURN pa.events AS v, count(*) AS n ORDER BY n DESC",
    "situation": "MATCH (pa:PlateAppearance) RETURN pa.situation AS v, count(*) AS n ORDER BY n DESC",
    "last_pitch_name": "MATCH (pa:PlateAppearance) WHERE pa.last_pitch_name IS NOT NULL RETURN pa.last_pitch_name AS v, count(*) AS n ORDER BY n DESC",
    "game_type": "MATCH (g:Game) RETURN g.game_type AS v, count(*) AS n",
    "stage": "MATCH (g:Game) WHERE g.stage IS NOT NULL RETURN g.stage AS v, count(*) AS n",
    "teams": "MATCH (t:Team) RETURN t.team_id + ' ' + t.name AS v, 1 AS n",
    "seasons": "MATCH (pa:PlateAppearance) RETURN pa.season AS v, count(*) AS n ORDER BY v",
    "last_date": "MATCH (g:Game) RETURN toString(max(g.date)) AS v, 1 AS n",
    "speed_range": "MATCH (pa:PlateAppearance) RETURN toString(min(pa.last_pitch_speed)) + '~' + toString(max(pa.last_pitch_speed)) AS v, 1 AS n",
}
PROPS = {
    "PlateAppearance": "MATCH (x:PlateAppearance) WITH x LIMIT 1 RETURN keys(x) AS k",
    "Game": "MATCH (x:Game) WITH x LIMIT 1 RETURN keys(x) AS k",
    "Outing": "MATCH (x:Outing) WITH x LIMIT 1 RETURN keys(x) AS k",
    "Player": "MATCH (x:Player) WITH x LIMIT 1 RETURN keys(x) AS k",
    "BatterSeasonStat": "MATCH (x:BatterSeasonStat) WITH x LIMIT 1 RETURN keys(x) AS k",
    "PitcherSeasonStat": "MATCH (x:PitcherSeasonStat) WITH x LIMIT 1 RETURN keys(x) AS k",
    "VideoLink": "MATCH (x:VideoLink) WITH x LIMIT 1 RETURN keys(x) AS k",
}
RELS = "MATCH (a)-[r]->(b) RETURN DISTINCT labels(a)[0] AS a, type(r) AS r, labels(b)[0] AS b"

if __name__ == "__main__":
    db.connect()
    out = {"values": {k: {str(r["v"]): r["n"] for r in db.run(q)} for k, q in Q.items()},
           "properties": {k: sorted(db.run(q)[0]["k"]) if db.run(q) else [] for k, q in PROPS.items()},
           "relations": [f"({r['a']})-[:{r['r']}]->({r['b']})" for r in db.run(RELS)]}
    db.close()
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {OUT} · events {len(out['values']['events'])}종 · 구종 {len(out['values']['last_pitch_name'])}종 · 관계 {len(out['relations'])}개")
