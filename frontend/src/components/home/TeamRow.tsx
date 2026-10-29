import { TeamLogo } from "@/components/ui/Media";
import type { Standing } from "@/lib/api";
import { SectionHead } from "./common";

/** 「팀으로 찾기」 — 순위대로 10칸 한 줄. 누르면 06 팀 화면 (옮기기 전이라 지금은 표시만) */
export default function TeamRow({ teams, sub }: { teams?: Standing[]; sub: string }) {
  return (
    <section>
      <SectionHead title="팀으로 찾기" sub={sub} />
      <ul className="grid grid-cols-5 gap-3 lg:grid-cols-10">
        {(teams ?? []).map((t) => (
          <li key={t.team_id} className="flex flex-col items-center gap-1.5 rounded-2xl border border-line bg-surface pt-3.5 pb-3" title={`${t.w}승 ${t.l}패 ${t.d}무 · 승률 ${t.pct.toFixed(3)}`}>
            <TeamLogo team={t.team} height={30} />
            <span className="text-[13px] font-bold">{t.team}</span>
            <span className="text-[11px] font-medium text-fg-2">{t.rank}위</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
