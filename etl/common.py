"""
공통 설정: .env 읽기, Neo4j 연결, 배치 적재 도우미.
다른 스크립트들이 import 해서 쓴다. 직접 실행하는 파일이 아니다.
"""
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# etl 폴더의 한 단계 위 = data 폴더
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# 원본 기록(시즌별 parquet) 폴더. 상대 경로는 BASEON 폴더 기준 (scripts/get_data.py가 받는 곳이 기본값)
KBO_PBP_DIR = Path(os.getenv("KBO_PBP_DIR", "data/kbo_pbp"))
if not KBO_PBP_DIR.is_absolute():
    KBO_PBP_DIR = ROOT / KBO_PBP_DIR
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
BATCH = 5000


def get_driver():
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )
    driver.verify_connectivity()  # Neo4j가 꺼져 있으면 여기서 바로 오류
    return driver


def run(driver, query, **params):
    """Cypher 한 번 실행하고 결과를 dict 목록으로 돌려준다."""
    with driver.session(database=DATABASE) as session:
        return session.run(query, **params).data()


def load_rows(driver, query, rows, label, batch=BATCH):
    """rows(dict 목록)를 batch개씩 끊어서 UNWIND 쿼리로 넣는다."""
    total = len(rows)
    start = time.time()
    for i in range(0, total, batch):
        with driver.session(database=DATABASE) as session:
            session.run(query, rows=rows[i : i + batch]).consume()
        print(f"  {label}: {min(i + batch, total):,}/{total:,}", end="\r")
    print(f"  {label}: {total:,}개 완료 ({time.time() - start:.1f}초)     ")


def to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame을 Neo4j에 넘길 수 있는 dict 목록으로 바꾼다. NaN은 None(null)."""
    obj = df.astype(object)
    return obj.where(obj.notna(), None).to_dict("records")
