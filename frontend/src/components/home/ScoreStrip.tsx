import Link from "next/link";
import { Fragment } from "react";
import { TeamLogo } from "@/components/ui/Media";
import type { Day } from "@/lib/api";
import { md } from "@/lib/format";
import { weekday } from "./common";

/** 점수 한 줄 (메인 a): 그날 경기 점수만. 「일정 전체 ›」는 08 일정의 같은 날짜로 */
export default function ScoreStrip({ day, isLast }: { day: Day; isLast: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-y-3 rounded-[20px] border border-line bg-surface px-6 py-4">
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
              <li className="flex items-center gap-2 px-2 font-num text-sm font-bold">
                <TeamLogo team={g.away.team} height={20} />
                <span>
                  {g.away.team} {g.away.score} : {g.home.score} {g.home.team}
                </span>
                <TeamLogo team={g.home.team} height={20} />
                {g.stage_label && <span className="text-[11px] font-medium text-muted">{g.stage_label}</span>}
              </li>
            </Fragment>
          ))}
        </ul>
      )}
      <Link href={`/schedule/?date=${day.date}`} className="shrink-0 text-sm font-medium text-fg-2 hover:underline">
        일정 전체 ›
      </Link>
    </div>
  );
}
