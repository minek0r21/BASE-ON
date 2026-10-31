import type { StatKey } from "./api";

/** .309 처럼 앞의 0을 뺀 소수 셋째 자리 (야구 표기) */
export const rate3 = (v: number | null | undefined) =>
  v == null ? "–" : v.toFixed(3).replace(/^(-?)0\./, "$1.");

/** 0.189 → 18.9% */
export const pct1 = (v: number | null | undefined) => (v == null ? "–" : `${(v * 100).toFixed(1)}%`);

/** "2025-05-25" → "5.25" */
export const md = (iso: string) => `${Number(iso.slice(5, 7))}.${Number(iso.slice(8, 10))}`;

/** 등판 한 줄: 「6이닝 8K 무실점」 (장면을 제목 대신 우리 기록으로 표기, docs/장면.md 6장) */
export const outingLine = (l: { outs: number; so: number; r: number }) =>
  `${innings(l.outs)}이닝 · 삼진 ${l.so} · ${l.r === 0 ? "무실점" : `${l.r}실점`}`; // K 약자 대신 글자로 (11-01 사용자)

/** 아웃 수 → 이닝 표기: 542 → 180⅔ */
export const innings = (outs: number | null | undefined) =>
  outs == null ? "–" : `${Math.floor(outs / 3)}${["", "⅓", "⅔"][outs % 3]}`;

/** 투수 지표 원 수치 (API-02 pitching.axes[].metric) */
export function formatPitchMetric(metric: string, v: number | null | undefined) {
  if (metric === "k_pct" || metric === "bbhbp_pct" || metric === "chase_pct") return pct1(v);
  return rate3(v); // avg_against · iso_against
}

export function formatStat(key: StatKey, v: number | null | undefined) {
  if (key === "k_pct" || key === "bb_pct") return pct1(v);
  if (key === "pa" || key === "ab" || key === "h" || key === "hr") return v == null ? "–" : String(v);
  return rate3(v);
}
