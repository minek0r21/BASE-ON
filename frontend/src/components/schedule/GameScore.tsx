import { TeamLogo } from "@/components/ui/Media";
import type { DayGame } from "@/lib/api";

/** 모바일 경기 머리 (M08 · M10): 왼쪽 원정 · 가운데 점수 · 오른쪽 홈. 팀 칸이 남는 폭을 나눠 가져 점수가 늘 가운데 온다 */
export default function GameScore({ game: g }: { game: DayGame }) {
  const side = (win: boolean) => `truncate text-[15px] ${win ? "font-bold" : "font-medium text-fg-2"}`;
  return (
    <span className="grid w-full grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2">
      <span className="flex min-w-0 items-center gap-2">
        <TeamLogo team={g.away.team} height={18} /><span className={side(g.away.result !== "L")}>{g.away.team}</span>
      </span>
      <span className="font-display text-2xl leading-none font-extrabold">{g.away.score} : {g.home.score}</span>
      <span className="flex min-w-0 items-center justify-end gap-2">
        <span className={side(g.home.result !== "L")}>{g.home.team}</span><TeamLogo team={g.home.team} height={18} />
      </span>
    </span>
  );
}
