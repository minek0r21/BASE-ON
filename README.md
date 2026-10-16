# BASE:ON 프로토타입

KBO 타석 기록을 Neo4j 그래프 DB에 넣고, 타자 지표(백분위)와 하이라이트 영상 장면을 이어서 보여주는 서비스의 프로토타입이에요.
지금은 **2025 정규시즌**만 들어 있어요.

- 백엔드: FastAPI (Python)
- DB: Neo4j
- 화면: `backend/demo/index.html` (확인용 데모. 실제 프론트는 Next.js로 따로 만들 예정)

## 폴더 구조

```
BASEON/
├─ README.md                      이 파일
├─ .env.example                   DB 접속·데이터 경로·CORS 양식. .env로 복사해서 값을 채운다
├─ player_profile_view_cp949.csv  선수 프로필 (포지션·등번호·생년월일·투타). 05가 읽는다
├─ shared/                        backend·etl 공통 계산 규칙 (pip install -e shared)
├─ scripts/
│   └─ get_data.py                원본 기록(parquet)을 리비전 고정으로 받기 → data/kbo_pbp/
├─ data/                          원본 기록 (저장소에 올리지 않음)
├─ docs/
│   ├─ 설계.md                    TRD 기준 통합 설계와 팀 결정
│   └─ 스키마.md                  Neo4j 노드·관계·속성 설명
├─ etl/                           원본 데이터 → Neo4j 적재 코드 (자세한 건 etl/README.md)
│   ├─ prepare.py                 parquet 읽기·정제·계산 (DB 안 씀)
│   ├─ 00 ~ 03                    DB 초기화 → 팀·선수·경기·타석 → 시즌 기록·백분위 → 확인
│   ├─ 04                         정제 규칙 건수 세기
│   ├─ 05                         선수 프로필 추가
│   └─ 06 ~ 08                    YouTube 영상 수집 → 제목·타석 매칭 → DB에 연결
├─ videos/                        06·07 결과 (영상 목록, 매칭 후보, 연결 못 한 영상)
└─ backend/                       API 서버 (자세한 건 backend/README.md)
    ├─ app/main.py                서버 시작, /demo 화면
    ├─ app/routers/               API 19개 중 17개 (players, games, matchup, league, review)
    └─ demo/index.html            확인용 화면 (메인·팀·타자 상세·장면 검수)
```

## 실행 방법 — Docker (권장)

Docker Desktop이 켜져 있어야 한다. 모든 명령은 이 폴더(BASEON)에서 실행한다.

```bash
cp .env.example .env               # NEO4J_PASSWORD(8자 이상)를 채운다
python scripts/get_data.py         # 원본 기록 → data/kbo_pbp/ (다른 곳에 있으면 .env의 KBO_PBP_HOST_DIR)
docker compose up -d               # neo4j + api 켜기

# 처음 한 번: 2025 시즌 적재 (약 1분)
docker compose run --rm etl etl/00_reset_db.py --yes
docker compose run --rm etl etl/01_load_core.py --season 2025
docker compose run --rm etl etl/02_load_season_stats.py --season 2025
docker compose run --rm etl etl/05_load_profile.py
docker compose run --rm etl etl/08_load_videos.py --season 2025
docker compose run --rm etl etl/03_check.py
```

- 확인 화면 http://localhost:8000/demo · API 문서 http://localhost:8000/docs · Neo4j 화면 http://localhost:17474
- `backend/` 코드를 고치면 API가 알아서 다시 켜진다
- 끄기 `docker compose down` (DB는 볼륨에 남는다). DB까지 지우기 `docker compose down -v`

## 실행 방법 — 직접 설치

### 1. 준비
- Python 3.10 이상, Neo4j (Neo4j Desktop 등)
- `.env.example`을 `.env`로 복사하고 Neo4j 비밀번호를 넣는다

```bash
python -m venv venv
source venv/bin/activate        # Windows PowerShell: venv\Scripts\activate
pip install -r backend/requirements.txt -r etl/requirements.txt -e shared
python scripts/get_data.py      # 원본 기록 2024~2026 → data/kbo_pbp/ (SHA-256 확인)
```

### 2. DB에 데이터 넣기
이 폴더(BASEON)에서 순서대로 실행한다. 원본 경로는 `.env`의 `KBO_PBP_DIR`(기본 `data/kbo_pbp`).
```bash
python etl/00_reset_db.py
python etl/01_load_core.py --season 2025
python etl/02_load_season_stats.py --season 2025
python etl/05_load_profile.py
python etl/07_match_videos.py --season 2025
python etl/08_load_videos.py --season 2025
```

### 3. 서버 켜기
```bash
cd backend
uvicorn app.main:app --reload
```
- http://localhost:8000/demo : 확인용 화면
- http://localhost:8000/docs : API 목록, 바로 호출해 볼 수 있음

## 데이터 출처
- 타석 기록: Hugging Face slothman3878/kbo_playbyplay (CC BY 4.0)
- 영상: KBO 공식 YouTube 채널 (정보만 저장, 재생은 임베드)
