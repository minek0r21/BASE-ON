import Link from "next/link";
import { Fragment } from "react";
import { TeamLogo } from "@/components/ui/Media";
import type { Day } from "@/lib/api";
import { md } from "@/lib/format";
import { gameHref, weekday } from "./common";

/** 모바일 M01: 세로 5줄. 왼쪽 원정 · 가운데 점수 · 오른쪽 홈 — 팀 칸이 남는 폭을 나눠 가져 점수가 늘 가운데 온다 */
function MobileGames({ day, isLast }: { day: Day; isLast: boolean }) {
  const [, mm, dd] = day.date.split("-").map(Number);
  const sub = [isLast && "마지막 경기일", `${day.games.length}경기`, day.games.length > 0 && "누르면 경기 상세"].filter(Boolean).join(" · ");
  return (
    <section className="md:hidden">
      <div className="mb-2 flex items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-black tracking-tight">{mm}월 {dd}일 ({weekday(day.date)}) 경기</h2>
          <p className="mt-1 text-xs text-fg-2">{sub}</p>
        </div>
        <Link href={`/schedule/?date=${day.date}`} className="shrink-0 text-[13px] font-bold text-brand-text max-md:-my-3 max-md:py-3">일정 ›</Link>
      </div>
      {day.games.length > 0 && (
        <ul className="divide-y divide-line rounded-2xl border border-line bg-surface px-3.5">
          {day.games.map((g) => {
            const aWin = g.away.score > g.home.score, hWin = g.home.score > g.away.score;
            return (
              <li key={g.game_pk}>
                <Link href={gameHref(g.game_pk)} className="grid h-12 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_14px] items-center gap-2">
                  <span className={`flex min-w-0 items-center gap-2 text-[15px] ${aWin ? "font-bold" : "font-medium text-fg-2"}`}>
                    <TeamLogo team={g.away.team} height={18} /><span className="truncate">{g.away.team}</span>
                  </span>
                  <span className="font-display text-xl font-extrabold">
                    <span className={hWin ? "text-muted" : ""}>{g.away.score}</span> <span className="text-muted">:</span> <span className={aWin ? "text-muted" : ""}>{g.home.score}</span>
                  </span>
                  <span className={`flex min-w-0 items-center justify-end gap-2 text-[15px] ${hWin ? "font-bold" : "font-medium text-fg-2"}`}>
                    <span className="truncate">{g.home.team}</span><TeamLogo team={g.home.team} height={18} />
                  </span>
                  <span className="text-lg leading-none text-fg-2" aria-hidden>›</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {day.games.length === 0 && <p className="rounded-2xl bg-surface px-4 py-5 text-sm text-fg-2">이날은 경기가 없어요</p>}
    </section>
  );
}

/** 점수 한 줄 (메인 a): 그날 경기 점수만. 「일정 전체 ›」는 08 일정의 같은 날짜로 */
export default function ScoreStrip({ day, isLast }: { day: Day; isLast: boolean }) {
  return (
    <>
    <MobileGames day={day} isLast={isLast} />
    <div className="hidden flex-wrap items-center gap-y-3 rounded-[20px] border border-line bg-surface px-6 py-4 md:flex">
      <div className="shrink-0">
        <p className="text-[15px] font-bold">
          {md(day.date)} ({weekday(day.date)})
        </p>
        {isLast && <p className="text-xs text-fg-2">마지막 경기일</p>}
      </div>
      {day.games.length === 0 ? (
        <p className="flex-1 px-5 text-sm text-fg-2">이날은 경기가 없어요</p>
      ) : (
        <ul className="flex flex-1 flex-wrap items-center justify-between gap-y-2 px-5">
          {day.games.map((g, i) => (
            <Fragment key={g.game_pk}>
              {i > 0 && <li className="hidden h-5 w-px bg-line-strong lg:block" aria-hidden />}
              <li>
                <Link href={gameHref(g.game_pk)} className="flex items-center gap-2 rounded-lg px-2 py-1 font-num text-sm font-bold hover:bg-surface-2">
                  <TeamLogo team={g.away.team} height={20} />
                  <span>
                    {g.away.team} {g.away.score} : {g.home.score} {g.home.team}
                  </span>
                  <TeamLogo team={g.home.team} height={20} />
                  {g.stage_label && <span className="text-[11px] font-medium text-muted">{g.stage_label}</span>}
                </Link>
              </li>
            </Fragment>
          ))}
        </ul>
      )}
      <Link href={`/schedule/?date=${day.date}`} className="shrink-0 text-sm font-medium text-fg-2 hover:underline">
        일정 전체 ›
      </Link>
    </div>
    </>
  );
}
