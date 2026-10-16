# BASE:ON 백엔드 (FastAPI)

## 처음 한 번
```bash
python -m venv venv && source venv/bin/activate   # Windows PowerShell: venv\Scripts\activate
pip install -r backend/requirements.txt -e shared   # BASEON 폴더에서. shared = 공통 계산 규칙
cd backend
```
화면 주소가 `localhost:3000`이 아니면 `.env`의 `CORS_ORIGINS`에 넣는다 (쉼표로 여러 개).

## 실행
Neo4j DB를 먼저 켠다. 접속 정보는 프로젝트 맨 위의 `.env`에서 읽는다 (`.env.example` 참고).
```bash   # backend 폴더에서
uvicorn app.main:app --reload       # --reload: 코드를 고치면 서버가 알아서 다시 켜짐
```
브라우저에서
- http://localhost:8000/demo → 확인용 화면 (메인·팀·타자 상세·장면 검수). 화면 시안 v9 모양에 실제 API 데이터를 넣은 것
- http://localhost:8000/docs → 각 API의 "Try it out"으로 바로 호출해 볼 수 있다.

## 파일
| 파일 | 하는 일 |
| --- | --- |
| `app/main.py` | 서버 시작, CORS, 라우터 등록, /demo 화면 |
| `demo/index.html` | 확인용 화면 (HTML 한 장, 실제 프론트는 Next.js로 따로) |
| `app/db.py` | Neo4j 연결 (프로젝트 맨 위 .env 사용) |
| `app/errors.py` | 오류 응답 형식 `{"error": {"code", "message"}}` |
| `app/events.py` | events → 한글 (events_ko). 본문은 `shared/baseon_rules/events.py` |
| `app/utils.py` | 요일, 타율, 승패 같은 작은 도우미 |
| `app/routers/players.py` | 1 검색, 2 선수 정보, 3 출전 경기, 19 시즌 기록 |
| `app/routers/games.py` | 4 경기별 타석, 14 날짜별 경기 일정, 15 최근 홈런 |
| `app/routers/matchup.py` | 6 맞대결, 17 상대한 투수 목록 |
| `app/routers/league.py` | 13 팀 순위, 16 타자 순위표, 18 지표별 상위 타자 |
| `app/routers/review.py` | 5 타석 영상, 7 검수 목록, 8 승인·반려·옮김, 9 직접 연결, 10 정확도 |

## API 목록 (13~19는 시안 v9 화면용으로 추가)
| # | 주소 | 화면 |
| --- | --- | --- |
| 1 | GET /players?q=&role= | 검색 |
| 2 | GET /players/{id}?season= | 타자 상세 카드·요약 (last_hr_video: 영상 있는 최근 홈런) |
| 3 | GET /players/{id}/games?season=&month= | 경기 기록 탭 왼쪽 |
| 4 | GET /games/{game_pk}/plate-appearances?player= | 경기 기록 탭 오른쪽 |
| 5 | GET /plate-appearances/{pa_id}/video | 타석 영상보기 (승인된 영상만) |
| 6 | GET /matchup?batter=&pitcher=&season= | 맞대결 (1:1) |
| 7 | GET /video-links?status=&sort=&limit=&offset= | 장면 검수 목록 (연결·후보) |
| 8 | PATCH /video-links/{video_id}/plate-appearances/{pa_id} | 검수 저장: approve / reject / move |
| 9 | POST /video-links/{video_id}/plate-appearances/{pa_id} | 영상-타석 직접 연결 |
| 10 | GET /video-links/stats | 자동 연결 정확도 |
| 13 | GET /standings?season= | 메인 팀 순위 |
| 14 | GET /games?date= | 메인 경기 일정 |
| 15 | GET /home-runs?season=&limit=&video_only= | 메인 최근 홈런 장면 (기본: 승인된 영상 있는 홈런만, 주자·볼카운트 포함) |
| 16 | GET /batters?season=&team=&sort=&qualified=&limit= | 메인 OPS 상위 타자, 팀 선수 전원·그 밖의 타자 (scene_count: 승인된 장면 수) |
| 17 | GET /players/{id}/matchups?season=&min_pa= | 맞대결 탭 투수 목록 |
| 18 | GET /leaders?season=&limit= | 메인 '이런 타자는 어때요?' 지표별 TOP 3 |
| 19 | GET /players/{id}/seasons | 시즌 기록 탭 |

포지션(`position`)은 데이터가 없어서 지금은 항상 null이에요. 수집하면 값만 채워요.

## 확인용 주소
- http://localhost:8000/api/v1/health
- http://localhost:8000/api/v1/players?q=김도영
- http://localhost:8000/api/v1/players?q=김&role=pitcher
- http://localhost:8000/api/v1/players/{player_id}       (검색 결과의 player_id)
- http://localhost:8000/api/v1/players/{player_id}?season=2024  → 404 SEASON_NOT_FOUND (2025만 적재됨)
- http://localhost:8000/api/v1/players/없는ID            → 404 PLAYER_NOT_FOUND
- http://localhost:8000/api/v1/players/{player_id}/games
- http://localhost:8000/api/v1/standings
- http://localhost:8000/api/v1/games
- http://localhost:8000/api/v1/home-runs
- http://localhost:8000/api/v1/batters?sort=power&limit=3
- http://localhost:8000/api/v1/batters?team=KIA&qualified=false&sort=pa
- http://localhost:8000/api/v1/players/{player_id}/matchups
- http://localhost:8000/api/v1/leaders
- http://localhost:8000/api/v1/players/{player_id}/seasons
