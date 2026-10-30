"use client";

import { useQuery } from "@tanstack/react-query";
import { getGameDays, qk, type GameDayCount } from "@/lib/api";
import { addDays, weekOf, weekdayOf } from "@/lib/dates";
import { md } from "@/lib/format";

/**
 * 한 주 띠 (08 일정 158:2099 · 10 장면 182:2066 위쪽) — 월~일 7칸, 고른 날은 잉크 바탕.
 * 칸 아래 줄은 화면마다 다르다(일정: 「5경기 · 홈런 15」, 장면: 「5경기 · 장면 14」) → caption으로 받는다
 */
export default function WeekStrip({ date, onPick, caption }: {
  date: string;
  onPick: (date: string) => void;
  caption: (d: GameDayCount) => string;
}) {
  const week = weekOf(date);
  const q = useQuery({ queryKey: qk.gameDays(week.start), queryFn: ({ signal }) => getGameDays(week.start, week.end, signal) });
  const byDate = new Map((q.data?.days ?? []).map((d) => [d.date, d]));
  const first = q.data?.first_date, last = q.data?.last_date;
  // 앞뒤 주 화살표는 같은 요일로 옮긴다. 데이터 첫 주 · 마지막 주 밖으로는 막는다
  const canPrev = !first || week.start > first;
  const canNext = !last || week.end < last;

  return (
    <div className="flex items-stretch gap-2 rounded-[20px] border border-line bg-surface p-2">
      <div className="flex w-[104px] shrink-0 flex-col justify-center pl-3">
        <p className="text-[15px] font-bold">{week.label}</p>
        <p className="text-[11px] text-muted">
          {md(week.start)} ~ {md(week.end)}
        </p>
      </div>
      <Arrow dir="prev" disabled={!canPrev} onClick={() => onPick(addDays(date, -7))} />
      <ul className="grid flex-1 grid-cols-7 gap-1">
        {week.days.map((d) => {
          const c = byDate.get(d);
          const on = d === date;
          return (
            <li key={d}>
              <button
                onClick={() => onPick(d)}
                disabled={!c}
                aria-pressed={on}
                className="flex h-full w-full flex-col items-center justify-center rounded-2xl py-2.5 transition-colors duration-[120ms] enabled:hover:bg-surface-2 disabled:text-muted aria-pressed:bg-night aria-pressed:text-white aria-pressed:hover:bg-night"
              >
                <span className="flex items-baseline gap-1">
                  <span className="font-display text-[26px] leading-none font-extrabold">{Number(d.slice(8))}</span>
                  <span className="text-xs">{weekdayOf(d)}</span>
                </span>
                <span className={`mt-1 text-[11px] ${on ? "text-white/70" : "text-muted"}`}>{c ? caption(c) : "경기 없음"}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <Arrow dir="next" disabled={!canNext} onClick={() => onPick(addDays(date, 7))} />
    </div>
  );
}

function Arrow({ dir, disabled, onClick }: { dir: "prev" | "next"; disabled: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={dir === "prev" ? "앞 주" : "다음 주"}
      className="my-auto flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line text-fg-2 enabled:hover:bg-surface-2 disabled:opacity-30"
    >
      {dir === "prev" ? "‹" : "›"}
    </button>
  );
}
