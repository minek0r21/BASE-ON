import type { AxisKey, PitchAxisKey } from "./api";

/** 투수 지표 설명 — 입문 팬용 쉬운 말 (docs/투수.md 8장, P9) */
export const PITCH_AXIS_HELP: Record<PitchAxisKey, string> = {
  strikeout: "상대한 타자를 삼진으로 잡는 비율이에요.",
  control: "볼넷·몸에 맞는 공을 적게 주는 능력이에요.",
  chase: "볼에도 방망이가 나오게 만드는 능력이에요. 스트라이크 존 밖 공에 타자가 휘두른 비율로 계산해요.",
  hit_prevention: "안타를 적게 맞는 능력이에요. 수비와 운도 영향을 줍니다.",
  power_prevention: "2루타·3루타·홈런 같은 큰 타구를 적게 맞는 능력이에요. 수비와 운도 영향을 줍니다.",
};

/** 지표 설명 (FR-02-04). 바뀌지 않는 글이라 프론트 상수로 둔다 (설계 6-3) */
export const AXIS_HELP: Record<AxisKey, string> = {
  contact: "타석당 삼진 비율(K%)이 낮을수록 높습니다.",
  hit: "타율(AVG). 타수 대비 안타를 얼마나 만드는지입니다.",
  power: "순장타율(ISO = 장타율 − 타율). 장타를 얼마나 치는지입니다.",
  eye: "타석당 볼넷 비율(BB%). 공을 얼마나 잘 골라내는지입니다.",
  consistency: "월별 OPS의 표준편차가 작을수록 높습니다. 20타석 이상인 달이 3개 이상이어야 계산합니다.",
};

/** 구단 색 — 선수 사진·로고 대신 쓴다 (SEC-06). 키는 API의 팀 이름 */
export const TEAM_COLORS: Record<string, string> = {
  KIA: "#EA0029",
  삼성: "#074CA1",
  LG: "#C30452",
  두산: "#131230",
  KT: "#231F20",
  SSG: "#CE0E2D",
  롯데: "#041E42",
  한화: "#FC4E00",
  NC: "#315288",
  키움: "#820024",
};

export const teamColor = (team: string | null | undefined) => (team && TEAM_COLORS[team]) || "#64748b";
