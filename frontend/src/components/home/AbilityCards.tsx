"use client";

import Link from "next/link";
import { useState } from "react";
import { playerHref } from "@/components/SearchBox";
import { PlayerAvatar, TeamLogo } from "@/components/ui/Media";
import Slide from "@/components/ui/Slide";
import type { LeaderCard, Leaders } from "@/lib/api";
import { axisCopy, rankingsHref } from "@/lib/axes";
import { SectionHead } from "./common";


export default function AbilityCards({ batters, pitchers, asOf }: { batters?: Leaders; pitchers?: Leaders; asOf: string | null }) {
  const [role, setRole] = useState<"batter" | "pitcher">("batter");
  const data = role === "batter" ? batters : pitchers;
  const season = batters?.season ?? pitchers?.season;
  const sub = [
    season && `${season} 정규시즌`,
    asOf && `${asOf} 기준`,
    "능력별 1~3위",
    batters && pitchers && `타자 ${batters.groupSize}명 / 선발 투수 ${pitchers.groupSize}명 중`,
  ].filter(Boolean).join(" · ");

  return (
    <section>
      <SectionHead
        title="어떤 선수를 찾고 있나요?"
        sub={sub}
        right={
          <Slide mark="rounded-full bg-surface-3" className="flex rounded-full border border-line bg-surface p-1" role="group" aria-label="타자 · 투수">
            {(["batter", "pitcher"] as const).map((r) => (
              <button
                key={r}
                onClick={() => setRole(r)}
                aria-pressed={role === r}
                className="relative h-[30px] rounded-full px-5 text-[13px] font-medium text-fg-2 transition-colors duration-[120ms] aria-pressed:font-bold aria-pressed:text-fg"
              >
                {r === "batter" ? "타자" : "투수"}
              </button>
            ))}
          </Slide>
        }
      />
      {!data ? (
        <div className="h-[360px] animate-pulse rounded-3xl bg-surface-2" />
      ) : (
        <ul className="animate-appear grid gap-5 sm:grid-cols-2 lg:grid-cols-5">
          {data.cards.map((c) => (
            <Card key={c.key} card={c} role={role} />
          ))}
        </ul>
      )}
    </section>
  );
}

function Card({ card, role }: { card: LeaderCard; role: "batter" | "pitcher" }) {
  const def = axisCopy(card.key);
  const [first, ...rest] = card.players;
  if (!def || !first) return null;
  return (
    <li className="flex flex-col rounded-3xl border border-line bg-surface px-5 py-[22px]">
      <h3 className="text-lg leading-snug font-bold break-keep">
        <Link href={rankingsHref(role, card.key)} className="hover:underline">{def.title}</Link>
      </h3>
      <p className="mt-1.5 text-xs text-muted">{def.sub}</p>
      <Link href={playerHref(first.player_id)} className="group mt-5 block">
        <span className="flex items-center gap-2.5">
          <PlayerAvatar id={first.player_id} name={first.name} team={first.team} size={72} />
          <span className="min-w-0">
            <span className="flex items-center gap-1.5 text-[17px] font-bold group-hover:underline">
              {first.name} <TeamLogo team={first.team} height={16} />
            </span>
            <span className="font-num text-xs font-bold">
              {first.rank}위
            </span>
          </span>
        </span>
        {/* 메인 카드는 1~3위만 보여 줘 「상위 1%」가 다섯 장 모두 같아진다 → 원 수치를 크게 (10-29 결정 (나)).
            「상위 N%」 강조는 선수 화면 · 05 능력별 순위에서 */}
        <span className="mt-2 block font-display text-[52px] leading-none font-extrabold">{def.fmt(first.value)}</span>
      </Link>
      <hr className="my-4 border-line" />
      <ol className="space-y-2.5">
        {rest.map((p) => (
          <li key={p.player_id}>
            <Link href={playerHref(p.player_id)} className="flex items-center gap-2.5 hover:underline">
              <span className="w-2.5 font-num text-[13px] font-bold text-muted">{p.rank}</span>
              <PlayerAvatar id={p.player_id} name={p.name} team={p.team} size={36} />
              <span className="min-w-0 flex-1 truncate text-sm font-medium">{p.name}</span>
              <span className="font-num text-sm font-semibold text-fg-2">{def.fmt(p.value)}</span>
            </Link>
          </li>
        ))}
      </ol>
      <Link href={rankingsHref(role, card.key)} className="mt-auto pt-4 text-[13px] font-bold text-brand-text hover:underline">
        순위 전체 ›
      </Link>
    </li>
  );
}
