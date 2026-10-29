/**
 * 리그 안 위치 문구 — 상위 · 하위 규칙 (10-29 결정, 디자인_2.0_구현 6장)
 *   백분위 p(나보다 나쁜 선수 수 ÷ n × 100), 상위 N = 100 − p
 *   N ≤ 50 → 「상위 N%」, 그 밖 → 「하위 M%」, M = (n − 등수 + 1) ÷ n × 100
 *   어느 쪽이든 「n명 중 m위」를 함께 쓴다
 */
export function leaguePosition(percentile: number, rank: number, n: number) {
  const top = Math.max(1, Math.round(100 - percentile));
  if (top <= 50) return { side: "상위" as const, pct: top, label: `상위 ${top}% · ${n}명 중 ${rank}위` };
  const bottom = Math.max(1, Math.round(((n - rank + 1) / n) * 100));
  return { side: "하위" as const, pct: bottom, label: `하위 ${bottom}% · ${n}명 중 ${rank}위` };
}
