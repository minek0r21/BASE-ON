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
- http://localhost:8000/docs → 각 API의 "Try it out"으로 바로 호출해 볼 수 있다.
- http://localhost:8000/demo → 예전 확인용 화면 (HTML 한 장). 실제 화면은 `frontend/`
  - 데모의 장면 검수 탭은 타석 연결만, 자동 확정 연결은 보여 주지 않는다. 검수는 `frontend/`의 `/admin/review/`(아래 관리자 검수 API)

## 확정 장면
연결(`MATCHED_TO`)의 상태가 `auto_confirmed`(자동 확정) 또는 `approved`(승인)이면 **확정**이고, 화면의 ▶·장면 수·최근 홈런 장면은 확정만 쓴다(설계 D1).
`pending`(검수 대기)·`rejected`(반려)는 화면에 나오지 않는다. 연결 구조와 자동 확정 규칙은 팀 문서 「장면.md」.

## 관리자 토큰
`.env`에 `ADMIN_TOKENS=이름1:토큰1,이름2:토큰2`가 있으면 `/admin/…`과 예전 검수 쓰기(8 · 9)가 `Authorization: Bearer <토큰>`을 요구하고, 검수자 이름은 토큰으로 정한다. 재생 불가 신고(12)는 누구나 쓴다.
비워 두면(로컬 개발) 토큰 없이 열린다. 서버에서는 Caddy가 `/admin`·`/api/v1/admin`을 404로 막는다(팀 문서 「배포.md」).

## 파일
| 파일 | 하는 일 |
| --- | --- |
| `app/main.py` | 서버 시작, CORS, 라우터 등록, /demo 화면 |
| `demo/index.html` | 예전 확인용 화면 (HTML 한 장) |
| `app/db.py` | Neo4j 연결 (프로젝트 맨 위 .env 사용) |
| `app/errors.py` | 오류 응답 형식 `{"error": {"code", "message"}}` |
| `app/events.py` | events → 한글 (events_ko). 본문은 `shared/baseon_rules/events.py` |
| `app/utils.py` | 요일, 타율, 승패 같은 작은 도우미 |
| `app/scenes.py` | 장면 연결 공통 — 확정이고 재생 가능한 연결 고르기 (여러 라우터가 같이 씀) |
| `app/videocheck.py` | YouTube videos.list로 재생 가능 판정 (API-12 · 재확인) |
| `app/postseason.py` | 포스트시즌 꼬리표 · 홈런 표기 · 기간 (포스트시즌 경기가 없으면 기간 아님) |
| `app/routers/players.py` | 1 검색(초성 · 옛 이름), 2 선수 정보(타자 · 투수), 3 출전 경기, 11 비교, 19 시즌 기록, 27 요즘 타격감 |
| `app/routers/games.py` | 4 경기별 타석, 14 날짜별 경기 일정, 15 최근 홈런 |
| `app/routers/matchup.py` | 6 맞대결, 17 상대한 투수(또는 타자) 목록 |
| `app/routers/league.py` | 13 팀 순위, 16 타자 순위표, 18 지표별 상위 타자, 26 투수 목록, 28 순위 변동 |
| `app/routers/outings.py` | 23 투수 등판 목록, 24 등판 장면 |
| `app/routers/review.py` | 5 타석 장면, 7~10 예전 검수(타석만, 데모가 씀) |
| `app/routers/admin.py` | 관리자 검수 (경기 · 타석 · 등판 공통) |
| `app/routers/report.py` | 12 재생 불가 신고, 재확인 |
| `app/routers/postseason.py` | 25 포스트시즌 코너 |
| `app/routers/meta.py` | 20 기록 기준일 |

## API 목록
모든 주소 앞에 `/api/v1`. 번호는 설계 문서의 API 번호.

**선수 · 경기 · 리그**

| # | 주소 | 화면 |
| --- | --- | --- |
| 1 | GET /players?q=&role= | 검색. 초성(ㄱㄷㅇ · 김ㄷㅇ), 개명 선수 옛 이름, 많이 뛴 선수 먼저 |
| 2 | GET /players/{id}?season= | 선수 요약. 타자 5축 백분위 · 최근 홈런 · 축 장면, 투수면 `pitching`(5지표 · 선발/불펜) |
| 3 | GET /players/{id}/games?season=&month= | 경기 기록 탭 (타자) |
| 4 | GET /games/{game_pk}/plate-appearances?player= | 경기 요약 + 이 선수 타석 |
| 6 | GET /matchup?batter=&pitcher=&season= | 맞대결 (1:1) |
| 11 | GET /players/compare?ids=&season= | 비교 탭 (2~3명) |
| 13 | GET /standings?season= | 팀 순위 |
| 14 | GET /games?date= | 날짜별 경기 일정 · 점수판 · 그날 장면(홈런 `scene`, 등판 `pitcher_scenes`, `scene_counts`) |
| 15 | GET /home-runs?season=&limit=&video_only= | 최근 홈런 장면 (기본: 확정 장면이 있는 홈런만) |
| 16 | GET /batters?season=&team=&sort=&qualified=&limit= | 타자 순위표 (`scene_count`: 확정 장면 수) |
| 17 | GET /players/{id}/matchups?season=&min_pa=&as= | 맞대결 탭 목록 (`as=pitcher`면 이 투수가 상대한 타자) |
| 18 | GET /leaders?season=&limit= | 지표별 상위 타자 |
| 19 | GET /players/{id}/seasons | 시즌 기록 탭 (타격 · 투구) |
| 20 | GET /meta | 기록 기준일 |
| 23 | GET /players/{id}/outings?season=&month= | 경기 기록 탭 (투수 등판) |
| 25 | GET /postseason?season= | 메인 포스트시즌 코너 (포스트시즌 기록이 있을 때만) |
| 26 | GET /pitchers?season=&team=&role=&qualified=&sort=&limit= | 투수 목록 (기본 이닝 순) · 능력별 순위(`sort`=지표 5개 · whip 등, 백분위 · 등수 · 장면 수 · 지표 장면 · 비교 대상 평균) |
| 27 | GET /players/{id}/form?season= | 요즘 타격감 (최근 20경기 OPS) |
| 28 | GET /standings/history?season= | 달마다 순위 |
| 29 | GET /pitchers/leaders?season=&role=&limit= | 투수 지표 5개별 상위 n명 (메인 능력 카드 「투수」, 기본 선발) |
| 30 | GET /outings/{outing_id}/plate-appearances | 등판 상세: 등판 요약 + 이닝별 상대 타자(결과 · 범례 분류 · 투구 수 · 볼카운트 · 주자 · 아웃) |
| 31 | GET /players/{id}/similar?season=&as=&limit= | 비슷한 선수: 가장 강한 지표 순위에서 바로 위 선수 먼저, 모자라면 아래 (카드 대표 장면 포함) |
| 32 | GET /players/{id}/pitching-form?season= | 요즘 투구감: 등판마다 최근 10등판 WHIP, 시즌 · 비교 대상 평균, 판정(.15 기준), 최근 10등판 기간 |

**장면 · 검수**

| # | 주소 | 화면 |
| --- | --- | --- |
| 5 | GET /plate-appearances/{pa_id}/video | 타석 장면 (확정만) |
| 24 | GET /outings/{outing_id}/video | 등판 장면 (확정만) |
| 12 | POST /video-links/{video_id}/report | 재생 불가 신고 (누구나, 항상 202) |
| 7 | GET /video-links?status=&sort=&limit=&offset= | 예전 검수 목록 (타석만, 데모) |
| 8 | PATCH /video-links/{video_id}/plate-appearances/{pa_id} | 예전 검수 저장: approve / reject / move (토큰) |
| 9 | POST /video-links/{video_id}/plate-appearances/{pa_id} | 예전 직접 연결 (토큰) |
| 10 | GET /video-links/stats | 자동 연결 정확도 |
| 7' | GET /admin/review/queue?target_kind=&reason=&season=&status= | 검수 대기 · 자동 확정 표본 (경기 · 타석 · 등판) |
| 8' | PATCH /admin/review/{target_kind}/{target_id}/videos/{video_id} | 승인 · 반려 · 구간 고쳐 승인 · 옮김 |
| | GET /admin/review/{…}/move-candidates | 옮길 후보 |
| 8-3 | POST /admin/review/{…}/swap | 영상이 사라졌을 때 교체 후보로 |
| 10' | GET /admin/review/stats | 대상별 · 상태별 개수, 자동 연결 정확도 |
| 11-2 | GET /admin/review/missing-hr?season= | 장면 없는 홈런 · 홈런 장면 목표(NFR-06) |
| 12-2 | POST /admin/review/manual | 재생 시각으로 장면 표시 |
| 12-3 | POST /admin/review/no-video | 이 홈런은 영상에 없음 |
| 12' | POST /admin/videos/recheck?limit= | 확정 영상 재생 가능 다시 확인 |

포지션 · 등번호 · 생년월일 · 투타는 `etl/05_load_profile.py`가 넣는다. 05를 안 돌렸으면 null이다.

## 확인용 주소
- http://localhost:8000/api/v1/health
- http://localhost:8000/api/v1/players?q=김도영 · `?q=ㄱㄷㅇ` · `?q=김&role=pitcher`
- http://localhost:8000/api/v1/players/{player_id}?season=2024       (검색 결과의 player_id. 시즌은 2024~2026)
- http://localhost:8000/api/v1/players/없는ID            → 404 PLAYER_NOT_FOUND
- http://localhost:8000/api/v1/players/{player_id}/games
- http://localhost:8000/api/v1/players/{투수 player_id}/outings
- http://localhost:8000/api/v1/standings
- http://localhost:8000/api/v1/games
- http://localhost:8000/api/v1/home-runs
- http://localhost:8000/api/v1/batters?sort=power&limit=3
- http://localhost:8000/api/v1/batters?team=KIA&qualified=false&sort=pa
- http://localhost:8000/api/v1/pitchers?season=2025
- http://localhost:8000/api/v1/players/{player_id}/matchups
- http://localhost:8000/api/v1/leaders
- http://localhost:8000/api/v1/players/{player_id}/seasons
- http://localhost:8000/api/v1/admin/review/stats
