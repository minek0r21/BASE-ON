"use client";

import { useQuery } from "@tanstack/react-query";
import { getGameDays, qk, type GameDayCount } from "@/lib/api";
import { addDays, weekOf, weekdayOf } from "@/lib/dates";
import { md } from "@/lib/format";

/**
 * 한 주 띠 (08 일정 158:2099 · 10 장면 182:2066 위쪽) — 월~일 7칸, 고른 날은 잉크 바탕.
 * 칸 아래 줄은 화면마다 다르다(일정: 「5경기 · 홈런 15」, 장면: 「5경기 · 장면 14」) → caption으로 받는다
 */
export default function WeekStrip({ date, onPick, caption, short }: {
  date: string;
  onPick: (date: string) => void;
  caption: (d: GameDayCount) => string;
  /** 모바일 칸 아래 글자 — 칸이 좁아 한 낱말만 */
  short: (d: GameDayCount) => string;
}) {
  const week = weekOf(date);
  const q = useQuery({ queryKey: qk.gameDays(week.start), queryFn: ({ signal }) => getGameDays(week.start, week.end, signal) });
  const byDate = new Map((q.data?.days ?? []).map((d) => [d.date, d]));
  const first = q.data?.first_date, last = q.data?.last_date;
  // 앞뒤 주 화살표는 같은 요일로 옮긴다. 데이터 첫 주 · 마지막 주 밖으로는 막는다
  const canPrev = !first || week.start > first;
  const canNext = !last || week.end < last;

  return (
    <div className="rounded-2xl border border-line bg-surface p-2 md:flex md:items-stretch md:gap-2 md:rounded-[20px]">
      {/* 모바일: 화살표 · 주 이름 줄을 위에 두고 아래 7칸이 폭 전체를 나눠 가진다 */}
      <div className="flex items-center justify-between md:hidden">
        <Arrow dir="prev" disabled={!canPrev} onClick={() => onPick(addDays(date, -7))} />
        <div className="text-center">
          <p className="text-sm font-bold">{week.label}</p>
          <p className="text-xs text-fg-2">{md(week.start)} ~ {md(week.end)}</p>
        </div>
        <Arrow dir="next" disabled={!canNext} onClick={() => onPick(addDays(date, 7))} />
      </div>
      <div className="hidden w-[104px] shrink-0 flex-col justify-center pl-3 md:flex">
        <p className="text-[15px] font-bold">{week.label}</p>
        <p className="text-[11px] text-muted">
          {md(week.start)} ~ {md(week.end)}
        </p>
      </div>
      <span className="hidden md:contents"><Arrow dir="prev" disabled={!canPrev} onClick={() => onPick(addDays(date, -7))} /></span>
      <ul className="mt-1 grid flex-1 grid-cols-7 gap-0.5 md:mt-0 md:gap-1">
        {week.days.map((d) => {
          const c = byDate.get(d);
          const on = d === date;
          return (
            <li key={d}>
              <button
                onClick={() => onPick(d)}
                disabled={!c}
                aria-pressed={on}
                className="flex h-full w-full flex-col items-center justify-center rounded-[10px] py-1.5 md:rounded-2xl md:py-2.5 transition-colors duration-[120ms] enabled:hover:bg-surface-2 disabled:text-muted aria-pressed:bg-night aria-pressed:text-white aria-pressed:hover:bg-night"
              >
                <span className="flex flex-col-reverse items-center gap-0.5 md:flex-row md:items-baseline md:gap-1">
                  <span className="font-display text-xl leading-none font-extrabold md:text-[26px]">{Number(d.slice(8))}</span>
                  <span className="text-xs">{weekdayOf(d)}</span>
                </span>
                <span className={`mt-0.5 text-xs md:hidden ${on ? "font-bold text-white" : "text-fg-2"}`}>{c ? short(c) : "없음"}</span>
                <span className={`mt-1 hidden text-[11px] md:block ${on ? "text-white/70" : "text-muted"}`}>{c ? caption(c) : "경기 없음"}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <span className="hidden md:contents"><Arrow dir="next" disabled={!canNext} onClick={() => onPick(addDays(date, 7))} /></span>
    </div>
  );
}

function Arrow({ dir, disabled, onClick }: { dir: "prev" | "next"; disabled: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={dir === "prev" ? "앞 주" : "다음 주"}
      className="my-auto flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-xl font-bold enabled:hover:bg-surface-2 disabled:opacity-30 md:h-8 md:w-8 md:border md:border-line md:text-base md:font-normal md:text-fg-2"
    >
      {dir === "prev" ? "‹" : "›"}
    </button>
  );
}
