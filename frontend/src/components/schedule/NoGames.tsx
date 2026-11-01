import { Empty } from "@/components/ui/Chip";
import { addDays, longDate, weekdayOf } from "@/lib/dates";
import { md } from "@/lib/format";

const short = (iso: string) => `${md(iso)} (${weekdayOf(iso)})`;
const monthDay = (iso: string) => longDate(iso).replace(/ \(.\)$/, "");

/**
 * 일정(08) · 장면(10) 공통 — 고른 날에 경기가 없을 때 (09 「경기가 없는 날」 · 「기록이 아직 들어오지 않은 날」)
 * 쉬는 기간이 이틀 이상이면 그 기간을 말하고, 앞뒤 경기일(API-14 prev_date · next_date)로 넘어갈 버튼을 둔다
 */
export default function NoGames({ date, asOf, prev, next, onPick }: {
  date: string; asOf: string | null; prev: string | null; next: string | null; onPick: (d: string) => void;
}) {
  if (asOf && date > asOf) {
    return (
      <Empty
        text={`${monthDay(date)} 기록은 아직 없어요`}
        sub={`경기 기록은 공개 데이터(허깅페이스 kbo_playbyplay)를 써요. 지금은 ${monthDay(asOf)}까지 있어요.`}
        action={{ label: `마지막 경기일 ${short(asOf)} 보기`, onClick: () => onPick(asOf) }}
      />
    );
  }
  const from = prev && addDays(prev, 1);
  const to = next && addDays(next, -1);
  const span = from && to && from < to
    ? `${monthDay(from)}부터 ${from.slice(5, 7) === to.slice(5, 7) ? `${Number(to.slice(8, 10))}일` : monthDay(to)}까지 경기가 없는 기간이에요.`
    : undefined;
  return (
    <Empty
      text={`${longDate(date)}에는 경기가 없어요`}
      sub={span}
      actions={[
        ...(prev ? [{ label: `‹ ${short(prev)} 경기`, onClick: () => onPick(prev) }] : []),
        ...(next ? [{ label: `${short(next)} 경기 ›`, onClick: () => onPick(next) }] : []),
      ]}
    />
  );
}
