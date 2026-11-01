# frontend — BASE:ON 화면 (Next.js)

Next.js 16 · TypeScript · Tailwind CSS 4 · TanStack Query 5. **정적 내보내기**(`output: "export"`, 설계 9장·T11)라 서버에 Node 프로세스가 없다. 데이터는 전부 브라우저에서 FastAPI를 불러 받는다.

## 실행

```bash
docker compose up -d        # 저장소 맨 위에서. neo4j + api(:8000)
python scripts/sync_media.py   # 저장소 맨 위에서. 선수 사진 · 엠블럼 → frontend/public/media/ (git 제외)
cd frontend
npm install
npm run dev                 # http://localhost:3000
npm run build               # out/ 생성 (Caddy가 그대로 서빙)
```

- 선수 사진(`photos/`) · 구단 엠블럼(`logos/`)은 저장소에 넣지 않는다(팀 문서 「데이터_이용.md」). `sync_media.py`가 복사한 `public/media/`가 빌드에 같이 들어간다. 파일이 없으면 화면은 이름 첫 글자 · 팀 이름 글자로 대신 그린다.
- 원본이 작아(사진 94×118 · 엠블럼 64×41, KBO 공식 사이트 최대 크기) 고해상도 화면에서 깨진다 → `python scripts/upscale_media.py --esrgan <realesrgan-ncnn-vulkan.exe>`로 4배 폴더(`photos_x4/` · `logos_x4/`)를 만들면 `sync_media.py`가 그쪽을 먼저 쓴다. 사진은 「AI 30% + 원본 확대 · 선명화 70%」(AI만 쓰면 피부가 그림처럼 매끈해짐), 엠블럼은 AI 4배 그대로. 그래픽카드로 842장 몇 분.

- 개발 서버는 `.env.development`의 `NEXT_PUBLIC_API_BASE`(`http://localhost:8000/api/v1`)를 직접 부른다. API 쪽 `.env`의 `CORS_ORIGINS`에 `http://localhost:3000`이 있어야 한다(기본값).
- 배포 빌드는 같은 도메인의 `/api/v1`을 부른다.

## 주소

정적 내보내기에서는 `/players/[id]` 같은 동적 경로가 빌드 때 id를 전부 알아야 해서, 화면마다 쿼리 주소를 쓴다. 쿼리를 읽는 화면은 `<Suspense>` 안에 둔다.

| 화면 | 주소 |
| --- | --- |
| 홈 | `/` |
| 선수 | `/players/?id=<선수코드>&season=&tab=&view=&month=&outing=` — `tab` = `scenes` · `games` · `seasons` · `matchup`(생략하면 개요), `view` = `batter` · `pitcher`(타자 · 투수를 다 한 시즌), `outing` = 투수 경기 기록의 등판 상세 |
| 선수 목록 (팀별) | `/rankings/?team=` |
| 능력별 순위 | `/rankings/?role=batter·pitcher&axis=&team=` (`role` · `axis`가 있으면 이 탭) |
| 선수 비교 | `/compare/?ids=<코드,코드,코드>&as=batter·pitcher` (최대 3명) |
| 경기 상세 | `/games/?id=<경기번호>` |
| 팀 | `/teams/?team=` (생략하면 응원팀, 없으면 1위 팀) |
| 일정 · 장면 | `/schedule/?date=` · `/scenes/?date=` (생략하면 마지막 경기일) |
| 장면 검수 (공개 화면에 링크 없음, 서버에서는 막힘) | `/admin/review/` |

## 구조

```
src/
├─ app/
│   ├─ page.tsx                홈 (장면이 주인공)
│   ├─ players/                선수 화면 — PlayerView(머리 · 시즌 기록 · 능력 · 탭)
│   ├─ rankings/               선수 목록 — TeamRoster(팀별 선수) · RankingsView(능력별 순위) · PlayersHead · TeamPicker
│   ├─ compare/                선수 비교
│   ├─ games/                  경기 상세 (위쪽 플레이어 하나가 무대, 다음 장면 자동 재생)
│   ├─ teams/                  팀 — TeamHead(팀 색 머리 · 순위 띠) · TeamView
│   ├─ schedule/ · scenes/     일정 · 장면 (위쪽 한 주 띠)
│   ├─ admin/review/           장면 검수
│   ├─ layout.tsx · providers.tsx  글꼴 · 내비 · 푸터 · TanStack Query
│   └─ globals.css             색 토큰(연회색 기본) · 글꼴 이름 · 포커스 테두리 · 모션
├─ components/
│   ├─ layout/                 Nav · Footer(출처 고지)
│   ├─ home/                   Hero · ScoreStrip · DayScenes(그날 장면) · AbilityCards · TopPlayers · TeamRow · PostseasonCorner · common
│   ├─ player/                 Hero · Abilities(능력 5칸) · SceneList(장면 · 등판) · GamesTab · OutingsTab(등판 상세) · SeasonsTab
│   │                          MatchupTab · Forecast(맞대결 예상) · SideCards(요즘 타격감 · 시즌별 기록) · Similar(비슷한 선수)
│   ├─ schedule/               WeekStrip(한 주 띠) · NoGames(경기 없는 날)
│   ├─ ui/                     Chip · Empty · Retry(빈 상태 · 실패) · Help(「?」 말풍선) · Media(선수 얼굴 · 엠블럼 · ▶)
│   │                          ShareButton · Slide(전환 · 탭 선택 표시)
│   ├─ ScenePlayer.tsx         장면 재생 (YouTube IFrame)
│   ├─ InlinePlayer.tsx        그 자리에서 재생하는 어두운 칸
│   ├─ SearchBox.tsx           선수 검색 (초성 · 옛 이름)
│   └─ StageTag.tsx            포스트시즌 꼬리표
└─ lib/
    ├─ api.ts                  API 호출 · 응답 타입 · 변환 (이 파일 하나)
    ├─ axes.ts · abilities.ts  능력 축 문구 · 판정 한 줄 · 순위 주소
    ├─ constants.ts            지표 설명
    ├─ position.ts             리그 안 위치 「상위 N% / 하위 M%」 규칙
    ├─ teams.ts                구단 표: 이름 · 엠블럼 코드 · 색 3개(띠 · 글자 · 연한 배경)
    ├─ local.ts                이 브라우저에만 저장: 응원팀 · 최근 본 선수
    ├─ motion.ts               모션 공용(움직임 줄이기 · 처음 보일 때 · 진행도)
    └─ format.ts · dates.ts    .309 · 18.9% · 115⅔ · 날짜 표기
```

`lib/api.ts`는 `Raw*` 타입(지금 백엔드 응답)을 `to*()` 함수로 화면용 타입으로 바꾼다. 백엔드 응답이 바뀌면 `Raw*` 타입과 변환 함수만 고친다.

## 장면 재생

`ScenePlayer`는 썸네일을 먼저 그리고 누를 때 YouTube IFrame 플레이어를 붙인다(`bare`면 누른 자리에서 바로 재생). 구간은 `startSeconds`·`endSeconds`로 주고, 재생 중 250ms마다 종료 지점을 넘었는지 보고 멈춘다. 다른 장면으로 바꾸면 같은 플레이어에서 `loadVideoById`만 부른다. 구간 끝에 닿으면 `onEnded`로 알리고, 경기 상세는 4초 카운트다운 뒤 다음 장면을 이어 재생한다(움직임 줄이기면 버튼만). 재생할 수 없는 영상(비공개 · 삭제)은 안내를 띄우고 재생 불가 신고(API-12)를 보낸다. 어떤 버튼에 어떤 영상이 붙는지는 팀 문서 「장면.md」 6장.

## 모션

모든 모션은 OS 「움직임 줄이기」 설정에서 꺼진다. CSS 모션은 `globals.css`의 규칙이, JS로 움직이는 것(막대 숫자 · 큰 장면 넘김 · 자동 재생)은 `lib/motion.ts`의 `useReducedMotion`이 막는다.
