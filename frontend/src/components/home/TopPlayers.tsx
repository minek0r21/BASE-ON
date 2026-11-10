"use client";

import Link from "next/link";
import { useState } from "react";
import { playerHref } from "@/components/SearchBox";
import { PlayGlyph, PlayerAvatar, TeamLogo } from "@/components/ui/Media";
import Seg from "@/components/ui/Seg";
import type { TopBatter, TopPitcher } from "@/lib/api";
import { rate3 } from "@/lib/format";
import { SectionHead } from "./common";

type Row = { id: string; name: string; team: string | null; meta: string; value: string; bar: number; extra: string; scenes: number };

/** 「지금 가장 잘하는 선수」 — 타자 OPS · 선발 WHIP 상위 5명. 막대는 1위 대비 길이(WHIP는 낮을수록 길다) */
export default function TopPlayers({ batters, pitchers, sub }: { batters?: TopBatter[]; pitchers?: TopPitcher[]; sub: string }) {
  const [role, setRole] = useState<"batter" | "pitcher">("batter"); // 모바일은 하나씩, 데스크톱은 둘 다
  const maxOps = Math.max(...(batters ?? []).map((b) => b.ops ?? 0), 0.001);
  const minWhip = Math.min(...(pitchers ?? []).map((p) => p.whip ?? 99), 99);
  const bRows: Row[] = (batters ?? []).map((b) => ({
    id: b.player_id, name: b.name, team: b.team,
    meta: [b.team, b.position, b.back_number != null && `#${b.back_number}`].filter(Boolean).join(" · "),
    value: rate3(b.ops), bar: (b.ops ?? 0) / maxOps, extra: `${b.hr ?? 0}홈런`, scenes: b.scene_count,
  }));
  const pRows: Row[] = (pitchers ?? []).map((p) => ({
    id: p.player_id, name: p.name, team: p.team,
    meta: [p.team, "선발", p.back_number != null && `#${p.back_number}`].filter(Boolean).join(" · "),
    value: p.whip?.toFixed(2) ?? "–", bar: p.whip ? minWhip / p.whip : 0, extra: `${p.so ?? 0}삼진`, scenes: p.scene_count,
  }));

  return (
    <section>
      <SectionHead title="지금 가장 잘하는 선수" sub={sub} />
      <Seg className="mb-2 md:hidden" label="타자 · 투수" value={role} onChange={setRole}
           items={[{ key: "batter", label: "타자 · OPS" }, { key: "pitcher", label: "투수 · WHIP" }]} />
      <div className="grid gap-2 rounded-2xl border border-line bg-surface p-1 md:rounded-3xl md:p-2 lg:grid-cols-2">
        <Column title="타자" note="OPS · 출루율 + 장타율 · 높을수록 좋아요" rows={bRows} className={role === "batter" ? "" : "hidden md:block"} />
        <Column title="투수" note="WHIP · 이닝마다 내보낸 주자 · 낮을수록 좋아요" rows={pRows} className={role === "pitcher" ? "" : "hidden md:block"} />
      </div>
    </section>
  );
}

function Column({ title, note, rows, className }: { title: string; note: string; rows: Row[]; className: string }) {
  return (
    <div className={className}>
      <p className="hidden px-3 pt-2 pb-1 text-[13px] font-bold md:block">
        {title} <span className="ml-1 text-[11px] font-normal text-muted">{note}</span>
      </p>
      <ol>
        {rows.map((r, i) => (
          <li key={r.id}>
            <Link
              href={playerHref(r.id)}
              className={`grid grid-cols-[22px_44px_minmax(0,1fr)_auto] items-center gap-2.5 rounded-2xl px-2.5 py-2.5 md:grid-cols-[28px_48px_1fr_120px_56px_auto] md:gap-3 md:px-3 transition-colors duration-[120ms] hover:bg-surface-2 ${i === 0 ? "bg-surface-2" : ""}`}
            >
              <span className="font-display text-[28px] leading-none font-extrabold">{i + 1}</span>
              <PlayerAvatar id={r.id} name={r.name} team={r.team} size={48} />
              <span className="min-w-0">
                <span className="flex min-w-0 items-center gap-1.5 text-[15px] font-bold">
                  <span className="truncate">{r.name}</span> <TeamLogo team={r.team} height={14} />
                </span>
                <span className="block truncate text-xs text-fg-2 md:text-[11px] md:text-muted">{r.meta}</span>
              </span>
              <span>
                <span className="block text-right font-num text-xl font-bold">{r.value}</span>
                <span className="mt-1 flex items-center justify-end gap-1 text-xs font-medium text-fg-2 md:hidden"><PlayGlyph size={7} /> 장면 {r.scenes}</span>
                <span className="mt-1 hidden h-1 overflow-hidden rounded-full bg-surface-3 md:block">
                  <span className={`block h-full rounded-full ${i === 0 ? "bg-fg" : "bg-brand"}`} style={{ width: `${Math.round(r.bar * 100)}%` }} />
                </span>
              </span>
              <span className="hidden text-right text-xs text-fg-2 md:block">{r.extra}</span>
              <span className="hidden h-7 items-center gap-1 rounded-full bg-accent px-2.5 text-[11px] font-bold text-white md:flex">
                <PlayGlyph size={7} /> 장면 {r.scenes}
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}
