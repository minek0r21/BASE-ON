import { pct1, rate3 } from "./format";

/**
 * 능력 지표 문구 — 메인 능력 카드(Figma 113:519 · 136:1569)와 05 능력별 순위(142:805)가 같이 쓴다.
 * 이름은 사람 말, 부제는 기준 지표. chip = 05 지표 칩 이름
 */
export type Role = "batter" | "pitcher";
export type AxisCopy = { chip: string; title: string; sub: string; metric: string; fmt: (v: number | null) => string };

export const AXES: Record<Role, { key: string; copy: AxisCopy }[]> = {
  batter: [
    { key: "contact", copy: { chip: "삼진 회피", title: "삼진을 잘 안 당하는 타자", sub: "삼진 비율 · 낮을수록 좋아요", metric: "삼진 비율", fmt: pct1 } },
    { key: "hit", copy: { chip: "안타 생산", title: "안타를 잘 치는 타자", sub: "안타를 친 비율 (타율)", metric: "타율", fmt: rate3 } },
    { key: "power", copy: { chip: "파워", title: "멀리 치는 타자", sub: "장타를 얼마나 치나 · 순수 장타력", metric: "순수 장타력", fmt: rate3 } },
    { key: "eye", copy: { chip: "선구안", title: "공을 잘 고르는 타자", sub: "볼넷 비율", metric: "볼넷 비율", fmt: pct1 } },
    { key: "consistency", copy: { chip: "꾸준함", title: "기복이 적은 타자", sub: "달마다 OPS(출루율 + 장타율) 차이 · 작을수록 좋아요", metric: "달마다 OPS 차이", fmt: rate3 } },
  ],
  pitcher: [
    { key: "strikeout", copy: { chip: "탈삼진", title: "삼진을 잘 잡는 투수", sub: "삼진 비율 · 높을수록 좋아요", metric: "삼진 비율", fmt: pct1 } },
    { key: "control", copy: { chip: "제구", title: "볼넷을 잘 안 주는 투수", sub: "볼넷·몸에 맞는 공 비율 · 낮을수록 좋아요", metric: "볼넷·사구 비율", fmt: pct1 } },
    { key: "chase", copy: { chip: "유인", title: "유인구로 속이는 투수", sub: "존 밖 공에 스윙한 비율", metric: "존 밖 스윙 비율", fmt: pct1 } },
    { key: "hit_prevention", copy: { chip: "안타 억제", title: "안타를 잘 안 맞는 투수", sub: "피안타율 · 낮을수록 좋아요", metric: "피안타율", fmt: rate3 } },
    { key: "power_prevention", copy: { chip: "장타 억제", title: "장타를 잘 안 맞는 투수", sub: "피순수장타력 · 낮을수록 좋아요", metric: "피순수장타력", fmt: rate3 } },
  ],
};

export const axisCopy = (key: string): AxisCopy | undefined =>
  [...AXES.batter, ...AXES.pitcher].find((a) => a.key === key)?.copy;

/** 비교 대상 기준 (etl/prepare.py: 타자 규정타석 50% · 선발 규정이닝 50%) */
export const GROUP_RULE: Record<Role, string> = { batter: "규정타석 50% 이상 타자", pitcher: "규정이닝 50% 이상 선발" };

export const rankingsHref = (role: Role, axis?: string) =>
  `/rankings/?${new URLSearchParams({ role, ...(axis ? { axis } : {}) })}`;
