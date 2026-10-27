# BASE:ON 적재 스크립트 (etl)

parquet를 새 스키마(스키마 탭 확정본)대로 Neo4j에 넣는다. 1단계 범위만 들어 있다: 팀, 선수, 경기, 타석, 타자·투수 시즌 기록과 그 관계. 영상과 구종 세부 유형은 나중에 따로 추가한다.

## 파일

| 파일 | 하는 일 |
| --- | --- |
| `common.py` | .env 읽기(원본 폴더 `KBO_PBP_DIR` 포함), Neo4j 연결, 배치 적재 도우미 |
| `prepare.py` | parquet → 노드·관계 모양으로 가공 (DB 안 씀). 직접 실행하면 가공 결과 요약만 출력 |
| `00_reset_db.py` | DB 전체 삭제 + 제약조건 11개·인덱스 5개 생성 (`--yes`: 확인 문구 없이). 사람이 한 검수도 지워진다 |
| `01_load_core.py` | 팀, 선수, 경기, 타석, 소속(PLAYS_FOR) 적재 |
| `02_load_season_stats.py` | 타자·투수 시즌 기록과 백분위 계산·적재 |
| `03_check.py` | 적재 결과 확인 (개수, 김도영 기록) |
| `04_count_rules.py` | 정제 규칙에 걸리는 건수를 시즌별로 세기 (DB 안 씀) |
| `05_load_profile.py` | 선수 프로필 CSV로 포지션·등번호·생년월일·투타를 Player에 추가 |
| `06_fetch_videos.py` | YouTube API로 영상 정보(제목·올린 시각·길이)를 받아 `videos/`에 CSV로 저장 (DB 안 씀) |
| `06b_update_inventory.py` | 영상 목록 `videos/yt_inventory.json`에 새 업로드만 덧붙이기 (채널 12개, YouTube API 키 필요) |
| `07_match_videos.py` | 영상 분류 + 매칭. `--step game` 경기 하이라이트 → 경기(`match_game.py`), `--step pa` 장면 클립·챕터 홈런 줄 → 타석(`match_pa.py`), `--step outing` 등판 클립·챕터 투수 줄 → 등판(`match_outing.py`). 결과 `videos/links_<시즌>_<단계>.csv` (DB 안 씀) |
| `08_load_videos.py` | VideoLink 노드, CANDIDATE·MATCHED_TO(검수 대기) 관계 적재. 이미 검수한 연결은 안 건드림 |
| `scenes.py` | 07의 영상 분류 · 제목 읽기 공통 (경기 · 타석 · 등판) |
| `tests/test_rules.py` | 계산 규칙 단위 시험 (백분위 · 꾸준함 · 실점 귀속 · 유인 · 안타 장면). `python etl/tests/test_rules.py` |
| `research/video_judge/` | Gemini 영상 판독 시험 코드 (보류, `docs/장면.md` 11장). 적재에는 쓰지 않는다 |

## 실행 순서 (PowerShell, 프로젝트 맨 위 폴더에서)

```powershell
cd BASEON   # 프로젝트 맨 위 폴더 (.env가 있는 곳. 원본은 data/kbo_pbp/ — scripts/get_data.py)
venv\Scripts\activate

python etl\prepare.py                 # 0. 가공만 해 보기 (DB 안 건드림)
python etl\00_reset_db.py             # 1. DB 비우기 (DELETE 입력)
python etl\01_load_core.py --sample 30   # 2-1. 30경기로 먼저 시험
python etl\03_check.py                # 확인
python etl\00_reset_db.py             # 시험 데이터 지우기
python etl\01_load_core.py            # 2-2. 전체 적재
python etl\02_load_season_stats.py    # 3. 시즌 기록
python etl\03_check.py                # 4. 확인
```

Neo4j Desktop에서 DB가 켜져 있어야 한다. 다른 DB 이름을 쓰면 `.env`에 `NEO4J_DATABASE=이름`을 추가한다.

### 2025시즌만 넣기 (프로토타입)

```bash
python etl/00_reset_db.py
python etl/01_load_core.py --season 2025
python etl/02_load_season_stats.py --season 2025
python etl/03_check.py
```

01과 02에 같은 시즌을 줘야 한다.

### 선수 프로필과 영상 연결 (01 다음)

```bash
python etl/05_load_profile.py                                 # 선수 프로필 (player_profile_view_cp949.csv)
python etl/06_fetch_videos.py --playlist PLMtML65ksOv0        # 2025 크보모먼트 영상 정보 (YOUTUBE_API_KEY 필요)
python etl/07_match_videos.py --season 2025 --step game   --videos videos/yt_inventory.json
python etl/07_match_videos.py --season 2025 --step pa     --videos videos/yt_inventory.json
python etl/07_match_videos.py --season 2025 --step outing --videos videos/yt_inventory.json
                                                              # 영상 분류 + 매칭 → videos/links_2025.csv · videos_2025.csv
python etl/08_load_videos.py --season 2025                    # 매칭 결과를 DB에 넣기 (경기·타석·등판 공통)
```

`videos/` 폴더에 06 결과가 이미 있으면 06은 건너뛰어도 된다 (YouTube 키 없이 07·08만 돌리면 됨).
07 결과 파일(`links_*`·`videos_*`·`unmatched_*`)은 git에 올리지 않는다 — 07을 돌릴 때마다 다시 만든다.
구조·규칙은 `docs/장면.md`.

**영상 목록 `videos/yt_inventory.json`** (약 21MB, git 제외): KBO · 10개 구단 · 티빙 채널의 2024-03 이후 업로드 34,000개.
처음 목록은 담당자(ETL 영상 담당)에게 파일로 받아 `videos/`에 둔다 — 처음부터 다시 받는 스크립트는 저장소에 없다.
그 뒤에는 `python etl/06b_update_inventory.py`로 새 업로드만 덧붙인다(`.env`의 `YOUTUBE_API_KEY`).
파일이 없으면 07은 `--videos videos/playlist_PLMtML65ksOv0.csv`(2025 크보모먼트 재생목록)로 `--step pa`만 돌릴 수 있다.

## 가공 규칙

- 타석은 `(game_pk, at_bat_number)`로 묶고 마지막 공 줄에서 결과·상황을 가져온다. 결과가 빈 타석은 제외한다.
- 사용 시즌: 2024~2026.7.26 (2023 제외, `prepare.py`의 SEASONS). 기본은 세 시즌 모두 적재.
- 정규시즌만 집계한다. `kbo_pbp_<시즌>_post.parquet`(포스트시즌)가 있으면 경기·타석에는 넣되 시즌 기록·백분위에서는 뺀다 (`docs/포스트시즌.md`, 팀 저장소에는 이 파일을 받는 길이 없다).
- 백분위 대상: 규정타석(타석이 가장 많은 팀의 경기 수 × 3.1)의 50% 이상. 같은 시즌 대상 타자끼리 비교한다.
- 백분위 = 나보다 나쁜 선수 수 ÷ n × 100 반올림 (설계 D3). 1위도 100이 되지 않는다.
- 꾸준함: 3월→4월 · 10월→9월을 합친 뒤 20타석 이상인 달의 월별 OPS 모표준편차, 그런 달이 3개 미만이면 null (설계 D3).
- 투수: 아웃 · 실점은 주자별 책임 투수에게 귀속한다 (`charge_runs`, `docs/투수.md` 10장). 5지표 · 선발/불펜 구분은 `docs/투수.md`.
- PLAYS_FOR에는 season 말고도 games, first_date, last_date가 들어간다. 시즌 중 트레이드된 선수의 최근 팀을 가리기 위해서다.
