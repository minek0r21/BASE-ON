"use client";

import { useQuery } from "@tanstack/react-query";
import { TeamLogo } from "@/components/ui/Media";
import { getStandings, qk } from "@/lib/api";
import { TEAM_NAMES, team as teamOf } from "@/lib/teams";

/** 팀 순서 = 순위순 (순위를 못 받으면 구단 표 순서) */
export function useTeamOrder(): string[] {
  const standings = useQuery({ queryKey: qk.standings(), queryFn: ({ signal }) => getStandings(signal) });
  return standings.data?.teams.map((t) => t.team).filter((t) => teamOf(t)) ?? TEAM_NAMES;
}

/** 팀 로고 줄 — 선수 탭 「팀별 선수」 · 「능력별 순위」가 같이 쓴다. withAll이면 맨 앞 「전체」(value null) */
export default function TeamPicker({ value, onPick, withAll = false }: { value: string | null; onPick: (team: string | null) => void; withAll?: boolean }) {
  const order = useTeamOrder();
  const btn = "flex h-11 items-center gap-2 rounded-full border border-line bg-surface text-sm font-medium hover:bg-surface-2 aria-pressed:border-2 aria-pressed:font-bold";
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="팀">
      {withAll && (
        <button onClick={() => onPick(null)} aria-pressed={value == null} className={`${btn} px-5 aria-pressed:border-fg`}>전체</button>
      )}
      {order.map((x) => (
        <button key={x} onClick={() => onPick(x)} aria-pressed={x === value} style={x === value ? { borderColor: teamOf(x)!.band } : undefined} className={`${btn} pr-4 pl-3`}>
          <TeamLogo team={x} height={22} /> {x}
        </button>
      ))}
    </div>
  );
}
