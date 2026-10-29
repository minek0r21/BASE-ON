"use client";

import Link from "next/link";
import { useState } from "react";
import { playerHref } from "@/components/SearchBox";
import { PlayerAvatar, TeamLogo } from "@/components/ui/Media";
import type { LeaderCard, Leaders } from "@/lib/api";
import { pct1, rate3 } from "@/lib/format";
import { SectionHead } from "./common";

// 능력 카드 문구 (Figma 113:519 · 136:1569). 이름은 사람 말, 부제는 기준 지표
const CARD: Record<string, { title: string; sub: string; fmt: (v: number | null) => string }> = {
  contact: { title: "삼진을 잘 안 당하는 타자", sub: "삼진 비율 · 낮을수록 좋아요", fmt: pct1 },
  hit: { title: "안타를 잘 치는 타자", sub: "안타를 친 비율 (타율)", fmt: rate3 },
  power: { title: "멀리 치는 타자", sub: "장타를 얼마나 치나 · 순수 장타력", fmt: rate3 },
  eye: { title: "공을 잘 고르는 타자", sub: "볼넷 비율", fmt: pct1 },
  consistency: { title: "기복이 적은 타자", sub: "달마다 OPS(출루율 + 장타율) 차이 · 작을수록 좋아요", fmt: rate3 },
  strikeout: { title: "삼진을 잘 잡는 투수", sub: "삼진 비율 · 높을수록 좋아요", fmt: pct1 },
  control: { title: "볼넷을 잘 안 주는 투수", sub: "볼넷·몸에 맞는 공 비율 · 낮을수록 좋아요", fmt: pct1 },
  chase: { title: "유인구로 속이는 투수", sub: "존 밖 공에 스윙한 비율", fmt: pct1 },
  hit_prevention: { title: "안타를 잘 안 맞는 투수", sub: "피안타율 · 낮을수록 좋아요", fmt: rate3 },
  power_prevention: { title: "장타를 잘 안 맞는 투수", sub: "피순수장타력 · 낮을수록 좋아요", fmt: rate3 },
};

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
          <div className="flex rounded-full border border-line bg-surface p-1" role="group" aria-label="타자 · 투수">
            {(["batter", "pitcher"] as const).map((r) => (
              <button
                key={r}
                onClick={() => setRole(r)}
                aria-pressed={role === r}
                className="h-[30px] rounded-full px-5 text-[13px] font-medium text-fg-2 transition-colors duration-[120ms] aria-pressed:bg-surface-3 aria-pressed:font-bold aria-pressed:text-fg"
              >
                {r === "batter" ? "타자" : "투수"}
              </button>
            ))}
          </div>
        }
      />
      {!data ? (
        <div className="h-[360px] animate-pulse rounded-3xl bg-surface-2" />
      ) : (
        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-5">
          {data.cards.map((c) => (
            <Card key={c.key} card={c} />
          ))}
        </ul>
      )}
    </section>
  );
}

function Card({ card }: { card: LeaderCard }) {
  const def = CARD[card.key];
  const [first, ...rest] = card.players;
  if (!def || !first) return null;
  return (
    <li className="flex flex-col rounded-3xl border border-line bg-surface px-5 py-[22px]">
      <h3 className="text-lg leading-snug font-bold break-keep">{def.title}</h3>
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
    </li>
  );
}
