"""
BASE:ON 백엔드 시작 파일.
실행:  uvicorn app.main:app --reload   (backend 폴더에서)
문서:  http://localhost:8000/docs
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import db, errors
from .routers import games, league, matchup, players, review


@asynccontextmanager
async def lifespan(app: FastAPI):  # 서버 켜질 때·꺼질 때 할 일 (DB 연결/해제)
    db.connect()   # 서버 켤 때 Neo4j 연결
    yield
    db.close()     # 서버 끌 때 연결 닫기


app = FastAPI(title="BASE:ON API", version="0.1.0", lifespan=lifespan)

# 프론트에서 호출할 수 있게 허용. 주소는 .env의 CORS_ORIGINS (쉼표로 여러 개, 기본 Next.js 개발 서버)
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

errors.register(app)

PREFIX = "/api/v1"
for r in (players.router, games.router, matchup.router, league.router, review.router):
    app.include_router(r, prefix=PREFIX)


@app.get(f"{PREFIX}/health", tags=["상태"], summary="서버·DB 연결 확인")
def health():  # 서버·DB가 살아 있는지 확인
    db.run("RETURN 1 AS ok")
    return {"status": "ok"}


# 확인용 화면 (디자인 없음). 실제 프론트는 Next.js로 따로 만든다
DEMO_PAGE = Path(__file__).resolve().parents[1] / "demo" / "index.html"


@app.get("/demo", include_in_schema=False)
def demo():  # localhost:8000/demo 에서 API를 화면으로 확인
    return FileResponse(DEMO_PAGE, headers={"Cache-Control": "no-store"})  # 고친 화면이 바로 보이게 캐시 안 함
