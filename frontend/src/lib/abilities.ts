import type { AxisKey, PitchAxisKey } from "./api";

/**
 * 선수 화면 능력 칸 판정 한 줄 (디자인_2.0_구현 6장 「막대 아래 판정」, Figma 138:519 · 139:1125).
 * 상위 25% 이내 = 강함 · 26~40% = 「~편」 · 41~60% = 「중간이에요」 · 그 밖 = 약한 쪽 「~편」
 */
const PHRASES: Record<AxisKey | PitchAxisKey, [strong: string, good: string, weak: string]> = {
  contact: ["삼진을 잘 안 당해요", "삼진이 적은 편", "삼진이 많은 편"],
  hit: ["안타를 잘 쳐요", "안타가 많은 편", "안타가 적은 편"],
  power: ["멀리 쳐요", "장타가 많은 편", "장타가 적은 편"],
  eye: ["공을 잘 골라요", "볼넷이 많은 편", "볼넷이 적은 편"],
  consistency: ["기복이 적어요", "꾸준한 편", "기복이 있는 편"],
  strikeout: ["삼진을 잘 잡아요", "삼진이 많은 편", "삼진이 적은 편"],
  control: ["볼넷을 잘 안 줘요", "볼넷이 적은 편", "볼넷이 많은 편"],
  chase: ["볼로 타자를 잘 속여요", "볼로 속이는 편", "볼로 잘 못 속이는 편"],
  hit_prevention: ["안타를 잘 안 맞아요", "안타를 덜 맞는 편", "안타를 많이 맞는 편"],
  power_prevention: ["장타를 잘 안 맞아요", "장타를 덜 맞는 편", "장타를 많이 맞는 편"],
};

export function verdict(key: AxisKey | PitchAxisKey, percentile: number): string {
  const top = 100 - percentile;
  const [strong, good, weak] = PHRASES[key];
  if (top <= 25) return strong;
  if (top <= 40) return good;
  if (top <= 60) return "중간이에요";
  return weak;
}

/** 상위 20% 이내 — 막대를 진하게 · 숫자와 판정을 강조하는 기준 (선수 상세 · 팀별 선수 · 능력별 순위 공통) */
export const isTop20 = (percentile: number) => 100 - percentile <= 20;
/** 막대 농도: 상위 20% 이내 진하게 · 50% 이내 중간 · 그 밖 연하게 */
export const barOpacity = (percentile: number) => (isTop20(percentile) ? 1 : 100 - percentile <= 50 ? 0.6 : 0.3);

/** 받침 있으면 a, 없으면 b — 「김도영은」 · 「네일은」 · 「오스틴은」 */
export function josa(word: string, a: string, b: string) {
  const c = word.charCodeAt(word.length - 1);
  if (c < 0xac00 || c > 0xd7a3) return `${word}${b}`;
  return `${word}${(c - 0xac00) % 28 ? a : b}`;
}
