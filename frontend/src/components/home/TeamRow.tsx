"use client";

import Link from "next/link";
import { TeamLogo } from "@/components/ui/Media";
import type { Standing } from "@/lib/api";
import { useMyTeam } from "@/lib/local";
import { team as teamOf, teamHref } from "@/lib/teams";
import { SectionHead } from "./common";

/** 「팀으로 찾기」 — 순위대로 10칸 한 줄. 누르면 06 팀 화면 */
export default function TeamRow({ teams, sub }: { teams?: Standing[]; sub: string }) {
  const [myTeam] = useMyTeam();
  return (
    <section>
      <SectionHead title="팀으로 찾기" sub={sub} />
      <ul className="grid grid-cols-2 gap-2 md:grid-cols-5 md:gap-3 lg:grid-cols-10">
        {(teams ?? []).map((t) => (
          <li key={t.team_id}>
            <Link href={teamHref(t.team)} style={t.team === myTeam ? { borderColor: teamOf(t.team)?.band } : undefined} className="flex h-16 items-center gap-1.5 rounded-2xl border border-line bg-surface px-3 transition-colors duration-[120ms] hover:bg-surface-2 md:h-auto md:flex-col md:gap-0 md:px-0 md:pt-5 md:pb-3.5" title={`${t.w}승 ${t.l}패 ${t.d}무 · 승률 ${t.pct.toFixed(3)}`}>
              <span className="w-5 text-center font-display text-[22px] leading-none font-extrabold md:hidden">{t.rank}</span>
              <span className="flex items-center md:hidden"><TeamLogo team={t.team} height={18} /></span>
              <span className="hidden h-14 items-center md:flex"><TeamLogo team={t.team} height={52} /></span>
              <span className="min-w-0 md:contents">
                <span className="block text-sm font-bold md:mt-2.5">{t.team}</span>
                <span className="block text-xs whitespace-nowrap text-fg-2 md:hidden">{t.w}승 {t.l}패</span>
              </span>
              <span className="mt-0.5 hidden text-xs font-medium text-fg-2 md:block">{t.rank}위</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
