# BASE:ON 프로토타입

KBO 타석 기록을 Neo4j 그래프 DB에 넣고, 타자·투수 지표(백분위)와 하이라이트 영상 장면을 이어서 보여주는 서비스의 프로토타입이에요.
**2024 · 2025 · 2026(7월 26일까지) 정규시즌**이 들어 있어요.

- 백엔드: FastAPI (Python)
- DB: Neo4j
- 화면: `frontend/` (Next.js 정적 내보내기). `backend/demo/index.html`은 예전 확인용 데모

## 폴더 구조

```
BASEON/
├─ README.md                      이 파일
├─ .env.example                   DB 접속·데이터 경로·CORS 양식. .env로 복사해서 값을 채운다
├─ player_profile_view_cp949.csv  선수 프로필 (포지션·등번호·생년월일·투타). 05가 읽는다
├─ shared/                        backend·etl 공통 계산 규칙 (pip install -e shared)
├─ scripts/
│   ├─ get_data.py                원본 기록(parquet)을 리비전 고정으로 받기 → data/kbo_pbp/
│   ├─ reload_all.sh              DB 전체 다시 적재 (00 → 01 → 02 → 05 → 03 → 07 → 08)
│   └─ deploy.py                  서버에 코드·화면·DB 올리기 (docs/배포.md)
├─ data/                          원본 기록 (저장소에 올리지 않음)
├─ docs/
│   ├─ 설계.md                    TRD 기준 통합 설계와 팀 결정 (14장 D1~)
│   ├─ 스키마.md                  Neo4j 노드·관계·속성 설명
│   ├─ 투수.md                    투수 5지표 · 선발/불펜 · 실점 귀속 (D12)
│   ├─ 장면.md                    영상 장면 연결 구조 · 자동 확정 규칙 · 검수 (S1~S15)
│   ├─ 포스트시즌.md              포스트시즌 설계 (팀 저장소에서는 데이터가 없어 꺼져 있음)
│   └─ 배포.md                    서버 배포 (Caddy · HTTPS · 비밀번호)
├─ etl/                           원본 데이터 → Neo4j 적재 코드 (자세한 건 etl/README.md)
│   ├─ prepare.py                 parquet 읽기·정제·계산 (DB 안 씀)
│   ├─ 00 ~ 03                    DB 초기화 → 팀·선수·경기·타석·등판 → 시즌 기록·백분위 → 확인
│   ├─ 04 · 05                    정제 규칙 건수 세기 · 선수 프로필 추가
│   ├─ 06 ~ 08                    YouTube 영상 목록 → 경기·타석·등판 매칭 → DB에 연결
│   └─ tests/                     계산 규칙 단위 시험
├─ videos/                        영상 목록 (yt_inventory.json은 git 제외 — etl/README.md)
├─ backend/                       API 서버 (자세한 건 backend/README.md)
│   ├─ app/main.py                서버 시작, /demo 화면
│   └─ app/routers/               players · games · outings · matchup · league · admin(검수) · report · meta · postseason
├─ frontend/                      화면 (자세한 건 frontend/README.md)
└─ deploy/                        서버용 docker-compose · Caddyfile · 서버 준비 스크립트
```

## 실행 방법 — Docker (권장)

Docker Desktop이 켜져 있어야 한다. 모든 명령은 이 폴더(BASEON)에서 실행한다.

```bash
cp .env.example .env               # NEO4J_PASSWORD(8자 이상)를 채운다
python scripts/get_data.py         # 원본 기록 2024~2026 → data/kbo_pbp/ (다른 곳에 있으면 .env의 KBO_PBP_HOST_DIR)
docker compose up -d               # neo4j + api 켜기

# 처음 한 번: 세 시즌 적재 (Git Bash). 영상 목록 videos/yt_inventory.json이 있어야 한다 — etl/README.md
bash scripts/reload_all.sh
```

`reload_all.sh`는 아래를 차례로 돈다. 하나씩 돌리려면:

```bash
docker compose run --rm etl etl/00_reset_db.py --yes
docker compose run --rm etl etl/01_load_core.py               # --season을 빼면 세 시즌 모두
docker compose run --rm etl etl/02_load_season_stats.py
docker compose run --rm etl etl/05_load_profile.py
docker compose run --rm etl etl/03_check.py
# 시즌마다 (2024 · 2025 · 2026)
docker compose run --rm etl etl/07_match_videos.py --season 2025 --step game   --videos videos/yt_inventory.json
docker compose run --rm etl etl/07_match_videos.py --season 2025 --step pa     --videos videos/yt_inventory.json
docker compose run --rm etl etl/07_match_videos.py --season 2025 --step outing --videos videos/yt_inventory.json
docker compose run --rm etl etl/08_load_videos.py --season 2025
```

- **00은 사람이 한 검수(승인·반려)까지 지운다.** 검수를 시작한 뒤에는 00 없이 07·08만 다시 돌린다.
- API 문서 http://localhost:8000/docs · Neo4j 화면 http://localhost:17474 · 예전 데모 http://localhost:8000/demo
- `backend/` 코드를 고치면 API가 알아서 다시 켜진다
- 끄기 `docker compose down` (DB는 볼륨에 남는다). DB까지 지우기 `docker compose down -v`

### 화면 (frontend)

```bash
cd frontend
npm install
npm run dev                        # http://localhost:3000 (API는 localhost:8000)
```

- 선수 화면 `/players/?id=<선수 ID>`, 장면 검수 `/admin/review/` (공개 화면에 링크 없음)
- 검수 API는 `.env`에 `ADMIN_TOKENS`(이름:토큰)를 넣으면 토큰을 요구한다. 비우면 로컬에서는 열려 있다

## 실행 방법 — 직접 설치

### 1. 준비
- Python 3.10 이상, Neo4j (Neo4j Desktop 등), Node.js 20 이상(화면)
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
python etl/01_load_core.py
python etl/02_load_season_stats.py
python etl/05_load_profile.py
# 시즌마다 (2024 · 2025 · 2026)
python etl/07_match_videos.py --season 2025 --step game   --videos videos/yt_inventory.json
python etl/07_match_videos.py --season 2025 --step pa     --videos videos/yt_inventory.json
python etl/07_match_videos.py --season 2025 --step outing --videos videos/yt_inventory.json
python etl/08_load_videos.py --season 2025
```

### 3. 서버 켜기
```bash
cd backend
uvicorn app.main:app --reload
```
- http://localhost:8000/docs : API 목록, 바로 호출해 볼 수 있음

## 시험

```bash
python etl/tests/test_rules.py     # 계산 규칙 단위 시험 (Docker: docker compose run --rm etl etl/tests/test_rules.py)
```

## 데이터 출처
- 타석 기록: Hugging Face slothman3878/kbo_playbyplay (CC BY 4.0, 리비전 고정 — 2026은 7월 26일까지)
- 영상: KBO · 구단 공식 YouTube 채널 (정보만 저장, 재생은 임베드)
