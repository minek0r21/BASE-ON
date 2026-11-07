# BASE:ON

KBO 입문 팬을 위한 기록 해석 · 장면 연결 서비스다. 타석 기록을 Neo4j 그래프 DB에 넣어 타자 · 투수의 능력을 리그 안 위치(백분위)로 풀어 주고, 그 기록에 KBO · 구단 공식 YouTube 영상의 장면을 이어 보여 준다.
**2024 · 2025 · 2026(7월 26일까지) 정규시즌**이 들어 있다. 비상업 수업 프로젝트다.

| 화면 | 주소 | 내용 |
| --- | --- | --- |
| 홈 | `/` | 선수 찾기 · 응원팀 경기, 그날 장면, 능력 카드, 지금 가장 잘하는 선수, 팀 순위 |
| 선수 | `/players/?id=<선수코드>` | 타자 · 투수 요약, 능력 5개(백분위), 장면 · 등판, 경기 기록(등판 상세), 시즌 기록, 맞대결 |
| 선수 목록 · 능력별 순위 | `/rankings/` | 팀별 선수, 능력마다 리그 순위(팀으로 거르기) |
| 선수 비교 | `/compare/?ids=&as=` | 2~3명 능력 · 기록 · 장면 비교 (타자끼리 · 투수끼리) |
| 경기 상세 | `/games/?id=<경기번호>` | 경기 하이라이트 · 장면 재생, 이닝별 점수, 박스스코어 |
| 팀 | `/teams/?team=` | 순위(펼치면 주마다 순위 변동 그래프) · 최근 경기 · 최근 장면 · 타자 · 선발 투수 |
| 일정 · 장면 | `/schedule/` · `/scenes/` | 날짜별 경기 · 그날 장면 |
| 장면 검수 (관리자) | `/admin/review/` | 자동 확정되지 못한 연결을 승인 · 반려 (공개 화면에 링크 없음, 검수자 토큰 필요) |

데스크톱(1440px) 기준으로 만들었고, 모바일 화면은 다음 단계다.

- 백엔드: FastAPI (Python 3.11)
- DB: Neo4j
- 화면: `frontend/` — Next.js 16 · React 19 · Tailwind CSS 4 · TanStack Query 5 (정적 내보내기)
- 서버: Docker Compose + Caddy (HTTPS · 비밀번호)

## 데이터 출처 · 이용

| 구분 | 내용 |
| --- | --- |
| 데이터 출처 (경기 기록) | Hugging Face [slothman3878/kbo_playbyplay](https://huggingface.co/datasets/slothman3878/kbo_playbyplay) — CC BY 4.0 |
| 원천 정보 제공처 | NAVER Sports 문자중계 — 데이터셋 제작자가 수집한 원천. 데이터셋에는 원문 해설 텍스트가 아닌 구조화된 경기 기록만 들어 있다 |
| 선수 프로필 일부 | 위키백과 (CC BY-SA 4.0) · 팀이 직접 입력 |
| 영상 | KBO · 구단 공식 YouTube 채널 — 영상 정보만 저장하고, 재생은 임베드 (영상을 내려받지 않는다) |
| 선수 사진 · 구단 엠블럼 | KBO 공식 사이트 — 서비스에는 쓰지만 저장소에는 넣지 않는다 |

이용 원칙 (원천이 NAVER Sports라 이용 · 재배포 권한에 주의하라는 검토 의견을 따른다):

- **학술 · 수업용 고정본만 쓴다.** 데이터셋을 리비전 `6afc8af044e3bba5f326b688e8cb41d7ff7065ec`로 고정해서 받는다(`scripts/get_data.py`, 파일별 SHA-256 확인). 2026 시즌은 7월 26일 경기까지이고, 그 뒤로 갱신하지 않는다(자동 갱신 없음).
- **원문 문자중계 텍스트는 확보하거나 공개하지 않는다.** NAVER Sports에서 직접 수집하지 않고 위 데이터셋만 쓴다.
- **원본 데이터를 GitHub나 논문 · 보고서 부록에 다시 올리지 않는다.** 저장소에는 코드와 받는 법만 둔다(아래 표).
- 발표 · 보고서 · 논문에는 통계 · 지표 · 예측 결과 · 모델 성능 같은 **파생 결과만** 싣는다.
- KBO · NAVER · 각 구단과 관계없는 비공식 · 비상업 프로젝트다.

### 저장소에 있는 것 · 없는 것

| 있음 | 없음 (git 제외 — 각자 받거나 만든다) |
| --- | --- |
| 소스 코드 (`backend/` · `frontend/` · `etl/` · `shared/`) | 원본 경기 기록 parquet (`data/kbo_pbp/` — `scripts/get_data.py`로 받기) |
| 전처리 · 계산 코드 (`etl/prepare.py`, 계산 규칙 `shared/baseon_rules/`) | Neo4j DB · DB 덤프 (`data/deploy/`) |
| 데이터 출처 · 받는 법 (이 문서, `scripts/get_data.py`) | 영상 목록 전체 `videos/yt_inventory.json` · 매칭 결과 `videos/links_*.csv` (받는 법은 `etl/README.md`) |
| `player_profile_view_cp949.csv` — 선수 프로필(포지션 · 등번호 · 생년월일 · 투타, 위키백과 · 직접 입력) | 선수 사진 `photos/` · 구단 엠블럼 `logos/` |
| `videos/playlist_*.csv` — YouTube 공개 영상 정보(제목 · 길이 · 게시일) | 설계 · 기획 문서 `docs/` |
| `etl/research/video_judge/sample.json` — 시험용 영상 40개의 제목 · 채널 | `.env` (비밀번호 · 키) |

### 서비스 공개 범위

- 지금 서버는 **비밀번호로 잠겨 있어** 팀원만 본다(`ACCESS=private`). 외부에 공개하기 전에 아래 범위를 확인한다.
- 화면에 보이는 것: 시즌 집계 기록 · 백분위 · 순위, 타석 결과 요약(「4회말 솔로 홈런」), 경기 박스스코어 · 이닝별 점수, 공식 채널 영상 임베드
- 보이지 않는 것: 문자중계 원문, 원본 파일 내려받기
- 공개 전 확인할 것: API(`/api/v1`)가 타석 단위 기록을 그대로 돌려주는 범위를 그대로 둘지

### 데이터 없이 실행하기

- `.env.example`을 `.env`로 복사한 뒤 `docker compose up -d`만 하면 API와 DB가 뜬다(적재용 etl 컨테이너는 따로 실행할 때만 켜진다).
- 화면(`frontend/`)도 켜진다. DB가 비어 있으면 기록이 나오지 않는다.
- 계산 규칙 단위 시험(`etl/tests/test_rules.py`)은 데이터 없이 돈다.
- 데이터를 넣으려면 `python scripts/get_data.py`로 받은 뒤 `bash scripts/reload_all.sh`.

## 장면 연결 (기록 ↔ 영상)

기록 한 줄(타석 · 등판 · 경기)에 KBO · 구단 공식 YouTube 영상의 **그 장면**을 잇는다. 근거는 두 가지다.

| 층 | 무엇으로 | 코드 |
| --- | --- | --- |
| ① 어느 경기 · 어느 영상인가 | 영상 **제목 · 설명란 글자**를 경기 기록과 맞춘다 (날짜 · 팀 · 선수 · n호 · n회 · 타점) | `etl/07_match_videos.py` → `08` |
| ② 영상 안 어느 장면 · 몇 초인가 | Gemini가 **제목 없이 화면 · 해설만** 보고 장면을 적고, 코드가 경기 기록과 대조한다 | `etl/11_read_highlights.py` (규칙 `etl/reading.py`) |

**① 제목 규칙** (`07`)
- 경기 하이라이트 → 경기 (모든 경기의 기본층), 홈런 · 안타 클립 → 타석, 투수 클립 → 등판, 설명란 챕터 줄(「5회말 ○○○ 2타점 적시타」) → 그 이닝 구간
- 제목의 주장이 기록과 모두 맞고 후보가 하나일 때만 **자동 확정**, 아니면 **검수 대기**(관리자 검수 화면). 화면에는 확정된 연결만 나온다.

**② 하이라이트 판독** (`11`) — 장면 연결의 기본
- 선수별 클립은 「멀티 홈런」 · 「백투백」처럼 장면이 섞여, 클립 하나가 여러 타석에 **0초부터** 걸리는 문제가 있었다(2026 홈런 클립 48개 · 연결 100개). 그래서 경기마다 하나인 **경기 하이라이트 + 장면 시작 초**를 기본으로 바꿨다.
- Gemini에는 YouTube 주소와 질문만 보낸다. 영상 파일을 내려받거나 올리지 않는다. 화면은 1초에 1장(낮은 해상도), 해설 음성과 함께 읽는다. 영상 제목과 그 경기 기록은 주지 않는다(유도 질문 방지).
- Gemini는 **본 것을 적기만** 한다. 장면마다 홈런 · 안타 · 삼진의 타자 · 투수 · 종류 · 시즌 n호 · 이닝 · 점수 · 친 순간 시각을 적는다. 이닝과 점수는 점수판에서 본 것만, 안 보이면 비운다.
- **판정은 코드가 한다.** 이름과 종류가 맞아야 후보가 된다. 그다음 근거(n호 · 이닝 · 점수 · 투수 · 안타 종류) **2개 이상이 맞고 어긋난 것이 없으면 자동 확정**한다. 장면 순서가 타석 순서와 거꾸로면 낮춘다. 자주 틀리는 초 · 말과 아웃 수는 판정에 쓰지 않는다.
- 재생 구간은 친 순간 8초 전부터 12초 뒤까지다. 하이라이트 장면은 클립보다 먼저 재생한다.
  - 홈런 · 안타 → 타석에 붙인다.
  - 삼진 → 그 투수의 등판 장면으로 붙인다.
  - 근거가 약한 홈런 → 검수 대기로 간다.
  - 멀티 홈런 클립 → 자동 확정에서 내린다.
  - 사람이 판정한 연결은 건드리지 않는다.
- 하이라이트에 없는 장면은 ①의 클립(장면이 하나뿐인 것)이나 관리자 「수동 표시」로 메운다.

**사람이 하는 일 · 측정**
- 오매칭 측정(NFR-07)은 홈런마다 **화면에 실제로 나가는 자동 확정 연결**에서 300개를 고정해(`11 --sample`) 사람이 전부 본다. 기준은 「시작 15초 안에 그 타자의 그 홈런이 보이는가」다. 확정을 Gemini 판독이 정했으므로 Gemini로 다시 확인하지 않는다(자기 채점). 300개 중 틀림 0개면 95% 상한이 0.99%다.
- 관리자 검수 화면(`/admin/review/`): 검수 대기 승인 · 반려, 「NFR-07 표본」(장면부터 자동 재생, J 맞음 · K 틀림), 장면 없는 홈런 「수동 표시」. 사람 판정은 장부(`data/review/decisions.jsonl`)에 남아 DB를 다시 적재해도 되살린다(`docker compose exec api python -m app.ledger replay`).

**공통 규칙**
- 정밀도: 바로 그 장면(하이라이트 장면 · 클립) > 그 이닝부터(챕터) > 경기 하이라이트 처음부터
- 선수에게는 그 선수가 잘한 장면만 붙인다(타자 화면에 삼진, 투수 화면에 피홈런을 그리지 않는다).
- Gemini 호출은 유료다. 응답은 `videos/gemini/`에 캐시해 같은 영상을 다시 부르지 않는다. 실행마다 달러 상한(`--usd`)을 두고, 쓴 돈은 `videos/gemini/spend.jsonl`에 남긴다.

## 폴더 구조

```
BASEON/
├─ README.md                      이 파일
├─ .env.example                   DB 접속 · 데이터 경로 · CORS · 키 양식. .env로 복사해서 값을 채운다
├─ player_profile_view_cp949.csv  선수 프로필. 05가 읽는다
├─ shared/                        backend · etl 공통 계산 규칙 (pip install -e shared)
├─ scripts/
│   ├─ get_data.py                원본 기록(parquet)을 리비전 고정으로 받기 → data/kbo_pbp/
│   ├─ reload_all.sh              DB 전체 다시 적재 (00 → 01 → 02 → 05 → 03 → 07 → 08)
│   ├─ sync_media.py              선수 사진 · 엠블럼 → frontend/public/media/
│   ├─ upscale_media.py           사진 · 엠블럼 4배 확대본 만들기 (선택)
│   ├─ perf_check.py              선수 상세 API 응답 시간 측정 (NFR-01)
│   └─ deploy.py                  서버에 코드 · 화면 · DB 올리기
├─ data/                          원본 기록 · DB 덤프 (git 제외)
├─ photos/ · logos/               선수 사진 · 구단 엠블럼 (git 제외)
├─ docs/                          설계 · 기획 문서 (git 제외)
├─ etl/                           원본 데이터 → Neo4j 적재 (자세한 건 etl/README.md)
│   ├─ prepare.py                 parquet 읽기 · 정제 · 계산 (DB 안 씀)
│   ├─ 00 ~ 03                    DB 초기화 → 팀 · 선수 · 경기 · 타석 · 등판 → 시즌 기록 · 백분위 → 확인
│   ├─ 04 · 05                    정제 규칙 건수 세기 · 선수 프로필 추가
│   ├─ 06 · 06b                   YouTube 영상 목록 받기 · 새 업로드 덧붙이기
│   ├─ 07 · 08                    영상 매칭(scenes.py 분류, match_game · match_pa · match_outing) → DB에 연결
│   ├─ gemini.py · reading.py     Gemini 호출기(캐시 · 비용 상한) · 판독 대조 규칙
│   ├─ 09 · 10 · 11               Gemini 판독: 장면 없는 홈런 제안 시각 · 클립 확인 · 하이라이트 장면(장면 연결의 기본)
│   ├─ research/video_judge/      Gemini 영상 판독 첫 시험 코드
│   └─ tests/                     계산 규칙 · 판독 대조 규칙 단위 시험
├─ videos/                        영상 목록 · 매칭 결과 (대부분 git 제외 — etl/README.md)
├─ backend/                       API 서버 (자세한 건 backend/README.md)
│   ├─ app/main.py                서버 시작, 라우터 등록
│   ├─ tests/                     API 테스트 (unittest)
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

그다음 하이라이트 판독(2026, Gemini 키 `GEMINI_API_KEY` 필요 · 유료):

```bash
docker compose run --rm etl etl/11_read_highlights.py --season 2026 --videos 10 --usd 1.5   # 판독 (캐시 · 상한, 다시 돌리면 이어서)
docker compose run --rm etl etl/11_read_highlights.py --season 2026 --videos 0 --load       # 받아 둔 판독으로 장면 연결 저장
docker compose run --rm etl etl/11_read_highlights.py --season 2026 --videos 0 --sample     # NFR-07 표본 300 고정 (한 번만)
```

- **00은 사람이 한 검수(승인 · 반려)까지 지운다.** 검수를 시작한 뒤에는 00 없이 07 · 08만 다시 돌린다(지웠다면 장부로 되살린다).
- 07 · 08을 다시 돌리면 멀티 홈런 클립이 자동 확정으로 돌아오므로 `11 --videos 0 --load`도 다시 돌린다(Gemini는 다시 부르지 않는다).
- API 문서 http://localhost:8000/docs · Neo4j 화면 http://localhost:17474
- `backend/` 코드를 고치면 API가 알아서 다시 켜진다
- 끄기 `docker compose down` (DB는 볼륨에 남는다). DB까지 지우기 `docker compose down -v`

### 화면 (frontend)

```bash
python scripts/sync_media.py       # 선수 사진 · 엠블럼 → frontend/public/media/ (photos/ · logos/가 있을 때. 없으면 이름 첫 글자로 그린다)
cd frontend
npm install
npm run dev                        # http://localhost:3000
```

- 개발 서버는 `frontend/.env.development`의 API 주소(`http://localhost:8000/api/v1`)를 부른다. 배포 빌드는 같은 도메인의 `/api/v1`을 부른다.
- 검수 API는 `.env`에 `ADMIN_TOKENS`(이름:토큰)를 넣으면 토큰을 요구한다. 비우면 로컬에서는 열려 있다.

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

## 서버 배포

서버는 **보여 주기와 검수만** 한다. 데이터 적재 · 매칭은 PC에서 하고, 서버에는 커밋된 코드 · 빌드한 화면 · PC DB 덤프만 올린다(`scripts/deploy.py`, 표준 라이브러리와 ssh · scp만 씀).

```bash
python scripts/deploy.py setup     # 처음 한 번: 스왑 · Docker · /opt/baseon (deploy/server_setup.sh)
python scripts/deploy.py code      # 화면 빌드 → 커밋된 코드(git archive HEAD) + 화면 올리기 → 빌드 · 재시작
python scripts/deploy.py db        # PC Neo4j를 1분쯤 멈추고 덤프 → 서버 DB를 통째로 바꾼다
python scripts/deploy.py status    # 컨테이너 · 메모리 · 디스크 · /meta
python scripts/deploy.py reviews   # 서버에서 한 판정을 PC 장부 · DB로 가져오기 (db 전에)
python scripts/deploy.py code --local <폴더>   # 서버 대신 PC 폴더에 똑같이 띄워 시험 (http://localhost:8080)
```

- PC `.env`에 `DEPLOY_HOST`(ubuntu@서버) · `DEPLOY_KEY`(SSH 키 경로)를 넣는다. 서버의 `deploy/.env`(도메인 · 비밀번호 · 관리자 토큰, `deploy/.env.example` 참고)는 서버에만 있다.
- 커밋하지 않은 변경은 올라가지 않는다. 사진 · 엠블럼을 바꿨으면 `code` 전에 `sync_media.py`.
- 검수는 서버에서도 한다(팀이 같이). 서버 판정은 서버 장부(`reviewdata` 볼륨)에 남고, `python scripts/deploy.py reviews`가 PC 장부에 없는 줄만 가져와 PC DB에 다시 적용한다. 서버 DB는 `db`를 할 때마다 PC 덤프로 바뀌므로, 안 가져온 서버 판정이 있으면 `db`는 멈춘다.
- 검수자는 사람마다 토큰을 받는다(서버 `deploy/.env`의 `ADMIN_TOKENS=이름:토큰,…`). 판정의 검수자 이름은 토큰으로 정해진다. NFR-07 표본은 「나눠 보기」로 사람 수만큼 나눠 본다.
- 기본은 비밀번호 잠금(`ACCESS=private`). 서버 컨테이너는 재부팅해도 다시 뜬다(`restart: unless-stopped`).

## 시험

```bash
python etl/tests/test_rules.py                       # 계산 규칙 단위 시험 (DB 없이. Docker: docker compose run --rm etl etl/tests/test_rules.py)
python etl/tests/test_reading.py                     # 판독 대조 규칙 단위 시험 (DB · Gemini 없이)
docker compose exec api python -m unittest discover -s tests -v    # API 테스트 (켜진 API · DB 대상, backend/tests)
docker compose run --rm etl etl/03_check.py --sample 100            # 원천 대조: DB 타석 무작위 100건을 원본 parquet과 비교 (NFR-05)
python scripts/perf_check.py                         # 선수 상세 API 응답 시간 p95 (NFR-01). 서버는 스크립트 머리말 참고
cd frontend && npm run lint && npx tsc --noEmit      # 화면 lint · 타입 검사
```

GitHub Actions(`.github/workflows/ci.yml`)가 PR · main 푸시마다 DB 없이 되는 검사(화면 lint · 타입 · 빌드, 계산 규칙 · 판독 대조 규칙, 관리자 토큰 검사)를 돌린다.
