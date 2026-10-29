/** 날짜 문자열(YYYY-MM-DD) 계산 — 시간대 영향을 받지 않게 UTC 정오로 다룬다 */
const toDate = (iso: string) => new Date(`${iso}T12:00:00Z`);
const toIso = (d: Date) => d.toISOString().slice(0, 10);

export const addDays = (iso: string, n: number) => {
  const d = toDate(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return toIso(d);
};

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
export const weekdayOf = (iso: string) => WEEK[toDate(iso).getUTCDay()];

/** 그 날짜가 들어 있는 주(월~일) 7일과 「7월 4주」 — 주는 목요일이 속한 달로 센다 */
export function weekOf(iso: string) {
  const dow = (toDate(iso).getUTCDay() + 6) % 7; // 월 0 … 일 6
  const monday = addDays(iso, -dow);
  const days = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  const thu = toDate(days[3]);
  return { days, start: days[0], end: days[6], label: `${thu.getUTCMonth() + 1}월 ${Math.ceil(thu.getUTCDate() / 7)}주` };
}

/** 「2026-07-26」 → 「7월 26일 (일)」 */
export const longDate = (iso: string) => `${Number(iso.slice(5, 7))}월 ${Number(iso.slice(8, 10))}일 (${weekdayOf(iso)})`;
