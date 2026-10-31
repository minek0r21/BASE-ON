import type { AxisKey, PitchAxisKey } from "./api";
import { team } from "./teams";

/** 투수 지표 설명 — 입문 팬용 쉬운 말 (docs/투수.md 8장, P9) */
export const PITCH_AXIS_HELP: Record<PitchAxisKey, string> = {
  strikeout: "상대한 타자를 삼진으로 잡는 비율이에요.",
  control: "볼넷·몸에 맞는 공을 적게 주는 능력이에요.",
  chase: "볼에도 방망이가 나오게 만드는 능력이에요. 스트라이크 존 밖 공에 타자가 휘두른 비율로 계산해요.",
  hit_prevention: "안타를 적게 맞는 능력이에요. 수비와 운도 영향을 줍니다.",
  power_prevention: "2루타·3루타·홈런 같은 큰 타구를 적게 맞는 능력이에요. 수비와 운도 영향을 줍니다.",
};

/** 지표 설명 (FR-02-04) — 「?」 말풍선 문장 (Figma 218:2115 확정 10-30, 디자인_2.0_구현 6장). 약어를 앞에 두지 않는다 */
export const AXIS_HELP: Record<AxisKey, string> = {
  contact: "삼진을 얼마나 적게 당하는지예요. 타석 중 삼진 비율로 계산해요. 낮을수록 막대가 길어요.",
  hit: "안타를 얼마나 잘 치는지예요. 타율(안타 ÷ 타수)로 계산해요.",
  power: "장타를 얼마나 치는지예요. 순수 장타력(장타율 − 타율)으로 계산해요. 2루타 · 3루타 · 홈런이 많을수록 커요.",
  eye: "공을 얼마나 잘 골라내는지예요. 타석 중 볼넷 비율로 계산해요.",
  consistency: "달마다 OPS가 얼마나 오르내렸는지예요(월별 OPS 표준편차). 작을수록 꾸준해요. 20타석 이상인 달이 3개 미만이면 계산하지 않아요.",
};

/** 비교 대상 기준 「?」 (etl/prepare.py QUALIFY_RATE · QUALIFY_SHARE · PITCHER_QUALIFY와 같은 값) */
export const GROUP_HELP = {
  batter: "규정타석은 팀 경기 수 × 3.1타석이에요. 그 절반 이상 타석에 선 타자끼리 비교해요.",
  pitcher: "규정이닝은 팀 경기 수 × 1이닝이에요. 선발은 그 절반 이상, 구원은 5분의 1 이상 던진 투수끼리 비교해요.",
} as const;

/** 기록 머리글 설명 (OPS · WHIP) */
export const STAT_HELP = {
  ops: "출루율 + 장타율. 얼마나 자주 나가고 얼마나 멀리 치는지를 한 숫자로 본 타격 점수예요. 1.000을 넘으면 리그 최상위권이에요.",
  whip: "이닝마다 내보낸 주자 수예요((볼넷 + 안타) ÷ 이닝). 낮을수록 좋아요.",
};

/** 구단 대표 색 (띠 · 막대). 표 전체는 lib/teams.ts */
export const teamColor = (name: string | null | undefined) => team(name)?.band ?? "#66676d";
