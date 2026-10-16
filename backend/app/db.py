"""
Neo4j 연결.
- 서버가 켜질 때 드라이버를 한 번 만들고, 꺼질 때 닫는다 (main.py의 lifespan).
- 라우터는 run()으로 Cypher를 실행한다. 값은 항상 파라미터($id 등)로 넘긴다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

# backend/app/db.py 기준 두 단계 위 = data 폴더의 .env (적재 코드와 같은 파일)
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")  # 이미 있는 환경변수는 덮어쓰지 않음 (나중에 Docker에서 편함)

DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
_driver = None


def connect():  # 서버 켤 때 Neo4j 연결
    global _driver
    _driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )
    _driver.verify_connectivity()  # Neo4j가 꺼져 있으면 서버 시작 때 바로 오류


def close():  # 서버 끌 때 연결 닫기
    if _driver is not None:
        _driver.close()


def run(query: str, **params) -> list[dict]:  # Cypher 실행 → 결과를 dict 목록으로
    """읽기 쿼리 한 번 실행 → dict 목록."""
    records, _, _ = _driver.execute_query(query, params, database_=DATABASE)
    return [r.data() for r in records]
