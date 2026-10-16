# 핸드오프 — BASEON 분석 · statscene-neo4j 비교 · 백엔드/배포 검토

> **2026-10-16 갱신:** 팀 TRD v1.0이 아래 「결정 대기」 1~4를 정했다 — FastAPI · 규정타석 50% · 재생 버튼은 홈런만 · Docker Compose.
> TRD 분석과 그에 맞춘 통합 설계는 `docs/설계.md`에 있다. 같은 날 D1~D8도 확정했다(설계.md 14장). 다음 세션은 설계.md 12장 일정의 7~8주차 작업부터 이어간다.

> 작성 2026-10-14. 코드·문서 정독과 CSV 집계로 확인한 내용이다. Neo4j·서버는 실행하지 않았다(코드상 문제는 읽어서 찾은 것).
> 다음 세션은 이 파일부터 읽고 「결정 대기」와 「다음 할 일」에서 이어간다.

## 1. 현재 상태 요약

- **BASEON** (이 폴더): 팀 Notion 스키마(`docs/스키마.md`)를 FastAPI + Neo4j로 구현한 프로토타입. 2025 정규시즌만 적재.
  API 17개, 영상 수집→매칭→검수 흐름, 데모 화면(`backend/demo/index.html`)까지 동작.
- **statscene-neo4j** (`../statscene-neo4j`): SPEC·DEC 기반 원 설계를 PostgreSQL → Neo4j로 옮긴 Spring Boot 실험 복제본(DEC-036).
  2024~2026.7.26 적재, 회귀 기준·테스트가 단단함. API는 3개(검색·상세·백분위), 영상(F-08·F-13)은 설계만.
- 원본 `kbo_pbp.parquet`는 BASEON 폴더에 없다. statscene-neo4j의 `data/raw/kbo_pbp/kbo_pbp_<시즌>.parquet`(리비전 `6afc8af`)를 쓸 수 있다.

## 2. BASEON 데이터 현황 (CSV 집계)

| 항목 | 값 |
| --- | --- |
| 재생목록 영상 | 1,658개 (2025.1.21~11.16, 전부 임베드 가능) |
| 후보 있는 영상 / 자동 연결 영상 | 1,009 / 774 (전체의 47%) |
| 자동 연결 타석 | 933 (홈런 515 · 안타 242 · 2루타 128 · 3루타 35 …) |
| 애매함 (1·2등 점수 차 20 미만) | 117 |
| 연결 못 한 영상 649 | 타자 이름 없음 162 · KBO 경기 아님 152 · 기타(시구·수비) 123 · 투수 122 · 제목 형식 다름 87 · 경기 없음 3 |
| 선수 프로필 | 847명, 등번호 빈칸 327, 동명이인 75 |

## 3. BASEON에서 찾은 문제

| 우선 | 위치 | 문제 |
| --- | --- | --- |
| 높음 | `etl/08_load_videos.py` | MERGE만 해서 07을 다시 돌리면 예전 CANDIDATE·pending MATCHED_TO가 남는다. 재실행 전 pending/auto 정리 단계 필요 |
| 높음 | `backend/app/routers/review.py` 8·9번 | 인증 없음. 공개 서버에선 누구나 승인·반려 가능. reviewer도 본문 문자열 |
| 높음 | 운영 | 검수 결과(MATCHED_TO 상태) 백업 수단 없음. `00_reset_db.py` 한 번이면 소실. Community는 온라인 백업 불가 → JSON 내보내기 cron 필요 |
| 중간 | `etl/05_load_profile.py:34` | `int(float(등번호))`로 `00` 3명이 `0`이 됨 (CSV에 `00` 3건 · `0` 5건 확인). 문자열로 저장해야 함 |
| 중간 | `review.py` Q_MOVE_TO | 옮김 대상의 기존 반려 연결을 승인으로 바꿀 때 `moved_to`를 안 지움. auto 연결이면 정확도 통계에 승인으로 잡힘 |
| 낮음 | `etl/prepare.py:336` | 선발 판정에 `groupby().first()` — 의도는 `.head(1)` (현재 결과는 같음) |
| 낮음 | `review.py` 7번 | 영상 전체를 불러와 파이썬에서 거름. 여러 시즌이면 느려짐 |
| ~~낮음~~ | `backend/app/main.py` | ~~CORS가 `localhost:3000` 고정~~ → 10-16 `CORS_ORIGINS` 환경변수로 고침 |
| ~~낮음~~ | `backend/requirements.txt` | ~~버전 고정 없음~~ → 10-16 고정, `etl/requirements.txt` 신설 |
| 문서 | 여러 곳 | backend/README "position 항상 null"(05가 채움), etl/README "영상은 나중에"(06~08 있음), 스키마.md에 `duration_sec`·`reasons`·`moved_to` 누락, docstring의 "data 폴더" 옛 경로 |

## 4. statscene-neo4j와의 차이 (같은 선수인데 숫자가 달라지는 곳)

| 항목 | BASEON | statscene-neo4j |
| --- | --- | --- |
| 교체 타석 귀속 | 마지막 공의 타자·투수 | 공식 규칙 DEC-026 (볼넷 → 이전 투수, 2스트라이크 후 대타 삼진 → 이전 타자). 약 18타석 차이 |
| 백분위 모집단 | 규정타석 50% 이상 (2025: 223타석) | 시즌 타석 상위 100명 (+동률) — DEC-038. "규정타석" 표현 금지 |
| 백분위 식 | (평균순위−1)/(n−1)×100 | 나보다 나쁜 수/n×100 반올림 |
| 꾸준함 | 30타석 이상 달, 3개월 이상 | 20타석 이상 달, 3월→4월·10월→9월 합침 |
| 등번호 | 정수 | 문자열 (0·00 구분) |
| 개명 | 최근 이름만 | `formerNames`·초성 검색·`:HomeRun.batterName` (DEC-035) |
| 타석 결과 분류 | Python 코드(prepare.py·events.py에 중복) | `:EventType` 노드 15개 |
| 맞대결 | 매번 집계 | 파생 간선 `FACED` |
| 영상 | VideoLink + CANDIDATE/MATCHED_TO, 모든 결과 대상, 크보모먼트 2025만 | Video + Clip(precision·startSec/endSec) + Report, **홈런만**, 공식 채널 12개 약 34,000개 실측 |
| 검증 | `03_check.py` | dry-run 회귀 기준·SHA-256 스냅샷·테스트 8개 |

- statscene 실측(V-04): 크보모먼트 제목 형식이 9월부터 `내용 | A vs B | M.D |`로 바뀜. BASEON `RE_TEAMS`는 `[A vs B]`만 읽는다 — 2025 재생목록에서 실제 영향 건수는 미확인.
- 문서 수치 불일치: 팀 스키마 사본은 대타 교체 35건·누락 39경기, BASEON 스키마.md는 51건·52경기. 집계 범위 차이로 보이나 미확인.

**합칠 때:** 데이터 정확성(귀속·EventType·스냅샷 고정·회귀 기준·개명·등번호 문자열·사람 데이터 보호)은 statscene에서,
화면·장면 연결(API 13~19 응답 모양·07 점수 규칙·검수 흐름·데모)은 BASEON에서 가져온다.

## 5. 백엔드·배포 검토 결론

- **Spring은 대체 가능.** 과목 요건(`statscene-neo4j/docs/00_CONTEXT.md`)에 백엔드 지정 없음(Git·Jira/Trello·Lint·리뷰·UML만).
  막는 것은 팀 결정 DEC-022와 CLAUDE.md 절대 제약 3번뿐. DEC-022 스스로 FastAPI를 원래 기본값이라 적었고, 기각 이유는 "구현자가 Java에 익숙"이었다.
  Neo4j로 바뀐 뒤엔 FastAPI면 JVM이 하나(Neo4j)만 남는다. 단 DEC-022의 되돌릴 조건이 "7주차 이후 변경 없음"이고 지금이 7주차.
- **선택 기준:** 팀 공동 작업·6주 내 완성 우선 → FastAPI(코드 이미 17개, 누구나 수정). Spring 포트폴리오·자문 친숙도 우선 → Spring(API 14개 재작성 필요).
- **Docker는 필수 아님, 팀 공유엔 가장 적합.** Neo4j·Python 버전 통일, 명령 하나 실행, Windows 7474 포트(Hyper-V 예약) 문제 한 번에 해결, 개발=배포 환경.
  대안: 서버 직접 설치(apt + systemd) / 관리형(AuraDB Free + PaaS — 2025만이면 한도 안으로 추정, 한도·휴면 정책은 확인 필요).
- **Docker가 안 풀어 주는 것 = 데이터 공유.** parquet은 리비전 고정 다운로드 스크립트, 적재 DB는 한 사람이 만든 dump를 공유, 검수는 공용 서버 한 곳에서만.
- **서버 구성안 (t3.small 2GB):** Caddy(HTTPS) → FastAPI(uvicorn 1~2 워커) → Neo4j(힙 512MB + 캐시 256MB). 합계 약 1.6~1.8GB(추정) — 스왑 1~2GB 필수, 부족하면 t3.medium.
- **배포 전 필수:** ① 검수 API 인증 ② 검수 결과 JSON 백업 cron ③ 7687·7474 비공개(내부망/127.0.0.1) ④ CORS 환경변수화.
  그 밖에: ETL은 서버에서 돌리지 말고 로컬 적재 후 dump/load(2GB에서 pandas OOM 위험, 00은 `input()` 대화형), Neo4j healthcheck 후 API 시작, 배포 도메인에서 YouTube 임베드 재확인(오류 153).

## 6. 결정 대기 (팀이 정할 것)

1. 백엔드: FastAPI 유지 vs Spring — FastAPI면 DEC-022 대체 결정 + SPEC·CLAUDE.md 제약 3 수정
2. 백분위 기준: 규정타석 50% vs 타석 상위 100명
3. 영상 연결 대상: 홈런만 vs 안타 등 포함
4. 배포 방식: Docker Compose(추천) vs 직접 설치 vs 관리형

## 7. 다음 할 일 (제안)

- [ ] Docker 구성: `docker-compose.yml`(neo4j + api, 배포용 caddy) · `backend/Dockerfile` · `etl/Dockerfile`(`docker compose run --rm etl …`) · `scripts/`(데이터 받기·dump/load·검수 백업) · README 실행 절차
- [ ] 검수 API 인증 추가 (관리자 토큰 `Depends`)
- [ ] 07·08 재실행 시 예전 후보·pending 정리
- [ ] 등번호 문자열 저장, `moved_to` 정리 버그 수정
- [ ] (FastAPI로 정하면) DEC-022 대체 결정 초안
