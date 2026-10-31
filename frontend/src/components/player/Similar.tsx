"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type { Playing } from "@/components/home/DayScenes";
import { SectionHead } from "@/components/home/common";
import InlinePlayer from "@/components/InlinePlayer";
import { playerHref } from "@/components/SearchBox";
import { PlayGlyph, PlayerAvatar, TeamLogo } from "@/components/ui/Media";
import { getSimilar, qk } from "@/lib/api";
import { josa } from "@/lib/abilities";
import { axisCopy } from "@/lib/axes";
import { md, rate3 } from "@/lib/format";
import type { Role } from "./Hero";

/** 「파워가 비슷한 타자」 (Figma 138:519 아래 · 139:1371) — API-31: 가장 강한 능력 순위에서 바로 위 선수 먼저 4명. ▶는 카드 아래에서 재생 */
export default function Similar({ id, season, role, asOf }: { id: string; season: number; role: Role; asOf: string | null }) {
  const q = useQuery({ queryKey: qk.similar(id, season, role), queryFn: ({ signal }) => getSimilar(id, season, role, signal) });
  const [playing, setPlaying] = useState<(Playing & { id: string }) | null>(null);
  const d = q.data;
  if (!d || !d.players.length) return null;
  const copy = axisCopy(d.axis);
  return (
    <section className="mt-14">
      <SectionHead
        title={`${josa(d.label, "이", "가")} 비슷한 ${role === "pitcher" ? "투수" : "타자"}`}
        sub={[copy && `${copy.metric} 상위`, `${season} 정규시즌${role === "pitcher" ? " 선발" : ""}`, asOf && `${md(asOf)} 기준`].filter(Boolean).join(" · ")}
      />
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {d.players.map((x) => (
          <li key={x.player_id} className="flex items-center gap-3 rounded-3xl border border-line bg-surface p-4">
            <Link href={playerHref(x.player_id)} className="group flex min-w-0 flex-1 items-center gap-3">
              <PlayerAvatar id={x.player_id} name={x.name} team={x.team} size={56} />
              <span className="min-w-0">
                <span className="flex items-center gap-1.5 text-[17px] font-bold group-hover:underline">
                  <span className="truncate">{x.name}</span> <TeamLogo team={x.team} height={14} />
                </span>
                <span className="mt-1 block truncate text-[13px] font-bold">{d.label} {x.rank}위 · {copy?.fmt(x.value) ?? "–"}</span>
                <span className="mt-0.5 block truncate text-xs text-fg-2">
                  {role === "pitcher" ? `WHIP ${x.whip?.toFixed(2) ?? "–"} · 삼진 ${x.so ?? "–"}` : `OPS ${rate3(x.ops)} · ${x.hr ?? 0}홈런`}
                </span>
              </span>
            </Link>
            {x.clip && (
              <button
                onClick={() => setPlaying(playing?.id === x.player_id ? null : { id: x.player_id, clip: x.clip!, title: x.sceneTitle ?? x.name })}
                aria-expanded={playing?.id === x.player_id}
                aria-label={`${x.sceneTitle ?? x.name} 재생`}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-2 hover:bg-accent hover:text-white aria-expanded:bg-accent aria-expanded:text-white"
              >
                <PlayGlyph size={11} />
              </button>
            )}
          </li>
        ))}
      </ul>
      {playing && <InlinePlayer playing={playing} onClose={() => setPlaying(null)} className="mt-5" />}
    </section>
  );
}
