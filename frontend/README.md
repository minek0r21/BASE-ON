# frontend — BASE:ON 화면 (Next.js)

Next.js 16 · TypeScript · Tailwind CSS 4 · TanStack Query 5. **정적 내보내기**(`output: "export"`, 설계 9장·T11)라 서버에 Node 프로세스가 없다. 데이터는 전부 브라우저에서 FastAPI를 불러 받는다.

## 실행

```bash
docker compose up -d        # 저장소 맨 위에서. neo4j + api(:8000)
cd frontend
npm install
npm run dev                 # http://localhost:3000
npm run build               # out/ 생성 (Caddy가 그대로 서빙)
```

- 개발 서버는 `.env.development`의 `NEXT_PUBLIC_API_BASE`(`http://localhost:8000/api/v1`)를 직접 부른다. API 쪽 `.env`의 `CORS_ORIGINS`에 `http://localhost:3000`이 있어야 한다(기본값).
- 배포 빌드는 같은 도메인의 `/api/v1`을 부른다.

## 주소

| 화면 | 주소 |
| --- | --- |
| 메인·검색 | `/` |
| 장면 검수 (공개 화면에 링크 없음, 설계 8-4) | `/admin/review/` |
| 선수 (탭은 `tab=games·seasons·compare·matchup`, 생략하면 요약) | `/players/?id=<선수코드>&season=&tab=&month=&view=&with=` |

정적 내보내기에서는 `/players/[id]` 같은 동적 경로가 빌드 때 id를 전부 알아야 해서, 선수 화면은 쿼리 주소를 쓴다. 쿼리를 읽는 화면은 `<Suspense>` 안에 둔다.

## 구조

```
src/
├─ lib/api.ts          API 호출·응답 타입·변환 (이 파일 하나)
├─ lib/constants.ts    지표 설명(FR-02-04)·구단 색(SEC-06)
├─ lib/format.ts       .309 · 18.9% 같은 표기
├─ app/layout.tsx      메뉴줄(검색)·푸터(출처 고지, NFR-02)
├─ app/page.tsx        메인
├─ app/players/        선수 화면 (탭)
└─ components/         SearchBox(BO-CM-01) · ScenePlayer(장면 재생, 설계 8-2)
                       player/Summary(BO-PB-01 타자 요약) · player/PitcherSummary(BO-PP-01 투수 요약)
                       player/GamesTab(타석 경기 기록) · player/OutingsTab(투수 등판 기록) · player/CompareTab(BO-PB-04 비교)
                       SceneButton(정밀도별 장면 버튼) · player/AxisBar(백분위 막대)
```

`lib/api.ts`는 `Raw*` 타입(지금 백엔드 응답)을 `to*()` 함수로 화면용 타입으로 바꾼다. 화면용 타입은 설계 6-3(API-02 `axes` 배열·`data_as_of`) 기준이라, 백엔드 응답이 바뀌면 `Raw*` 타입과 변환 함수만 고친다. 백엔드에 `response_model`이 생기면 `Raw*`는 `openapi-typescript` 생성 타입으로 바꾼다.

## 장면 재생

`ScenePlayer`는 썸네일을 먼저 그리고 누를 때 YouTube IFrame 플레이어를 붙인다(자동재생 없음). 구간은 `startSeconds`·`endSeconds`로 주고, 재생 중 250ms마다 종료 지점을 넘었는지 보고 멈춘다(FR-04-02). 다른 장면으로 바꾸면 같은 플레이어에서 `loadVideoById`만 부른다. 어떤 버튼에 어떤 영상이 붙는지는 `docs/장면.md` 6장.
