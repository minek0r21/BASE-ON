import Link from "next/link";
import { TeamLogo } from "@/components/ui/Media";
import type { Standing } from "@/lib/api";
import { teamHref } from "@/lib/teams";
import { SectionHead } from "./common";

/** 「팀으로 찾기」 — 순위대로 10칸 한 줄. 누르면 06 팀 화면 */
export default function TeamRow({ teams, sub }: { teams?: Standing[]; sub: string }) {
  return (
    <section>
      <SectionHead title="팀으로 찾기" sub={sub} />
      <ul className="grid grid-cols-5 gap-3 lg:grid-cols-10">
        {(teams ?? []).map((t) => (
          <li key={t.team_id}>
            <Link href={teamHref(t.team)} className="flex flex-col items-center rounded-2xl border border-line bg-surface pt-5 pb-3.5 transition-colors duration-[120ms] hover:bg-surface-2" title={`${t.w}승 ${t.l}패 ${t.d}무 · 승률 ${t.pct.toFixed(3)}`}>
              <span className="flex h-14 items-center"><TeamLogo team={t.team} height={52} /></span>
              <span className="mt-2.5 text-sm font-bold">{t.team}</span>
              <span className="mt-0.5 text-xs font-medium text-fg-2">{t.rank}위</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
