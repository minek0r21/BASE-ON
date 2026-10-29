/**
 * 구단 표 — 이름 · 엠블럼 파일 · 색 3개 (Figma 「팀 색 표」 179:2012, 팀 문서 「디자인_2.0_구현.md」 3-1).
 * 키는 API의 팀 이름. 색 출처: 위키백과 「틀:야구 주요 색」
 *   band: 위쪽 띠 · 막대 · 첫 배지   text: 흰 바탕 글자(대비 4.5:1 이상)   soft: 연한 배경   home: 홈 구장(06 「홈 광주」)
 */
export type Team = { name: string; full: string; code: string; band: string; text: string; soft: string; home: string };

export const TEAMS: Record<string, Team> = {
  KIA: { name: "KIA", full: "KIA 타이거즈", code: "HT", band: "#EA0029", text: "#C60023", soft: "#FCE0E5", home: "광주" },
  삼성: { name: "삼성", full: "삼성 라이온즈", code: "SS", band: "#074CA1", text: "#074CA1", soft: "#E1EAF4", home: "대구" },
  KT: { name: "KT", full: "KT 위즈", code: "KT", band: "#000000", text: "#000000", soft: "#E0E0E0", home: "수원" },
  LG: { name: "LG", full: "LG 트윈스", code: "LG", band: "#C40037", text: "#C40037", soft: "#F8E0E7", home: "잠실" },
  두산: { name: "두산", full: "두산 베어스", code: "OB", band: "#1A1748", text: "#1A1748", soft: "#E4E3E9", home: "잠실" },
  한화: { name: "한화", full: "한화 이글스", code: "HH", band: "#FC4E00", text: "#B53800", soft: "#FFEAE0", home: "대전" },
  NC: { name: "NC", full: "NC 다이노스", code: "NC", band: "#315288", text: "#315288", soft: "#E6EAF1", home: "창원" },
  롯데: { name: "롯데", full: "롯데 자이언츠", code: "LT", band: "#041E42", text: "#041E42", soft: "#E1E4E8", home: "사직" },
  SSG: { name: "SSG", full: "SSG 랜더스", code: "SK", band: "#CE0E2D", text: "#CE0E2D", soft: "#F9E2E6", home: "문학" },
  키움: { name: "키움", full: "키움 히어로즈", code: "WO", band: "#570514", text: "#570514", soft: "#EBE1E3", home: "고척" },
};

export const TEAM_NAMES = Object.keys(TEAMS);
export const team = (name: string | null | undefined): Team | null => (name && TEAMS[name]) || null;

/** 사진 · 엠블럼은 저장소에 넣지 않는다 — scripts/sync_media.py가 frontend/public/media/로 복사한다 */
export const logoUrl = (name: string | null | undefined) => {
  const t = team(name);
  return t ? `/media/logos/${t.code}.png` : null;
};
export const photoUrl = (playerId: string) => `/media/photos/${playerId}.jpg`;

/** 06 팀 화면 주소 */
export const teamHref = (name: string) => `/teams/?${new URLSearchParams({ team: name })}`;

/** 「두산과」 · 「KT와」 — 읽는 소리 끝에 받침이 있으면 과 (KIA 기아 · KT 케이티 · NC 엔씨 · SSG 에스에스지는 받침 없음) */
export const withGwa = (name: string) => `${name}${["삼성", "두산", "키움"].includes(name) ? "과" : "와"}`;
