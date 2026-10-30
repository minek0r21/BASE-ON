"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import AbilityCards from "@/components/home/AbilityCards";
import DayScenes, { type Playing } from "@/components/home/DayScenes";
import Hero from "@/components/home/Hero";
import PostseasonCorner from "@/components/home/PostseasonCorner";
import ScoreStrip from "@/components/home/ScoreStrip";
import TeamRow from "@/components/home/TeamRow";
import TopPlayers from "@/components/home/TopPlayers";
import { Wrap } from "@/components/home/common";
import { getDay, getLeaders, getMeta, getStandings, getTopBatters, getTopPitchers, qk, type Clip } from "@/lib/api";
import { md } from "@/lib/format";
import { useMyTeam } from "@/lib/local";

/**
 * 01 홈 — 장면이 주인공 (Figma 113:519, 팀 피드백 1차로 바뀐 구조 · 디자인_2.0_구현 7장)
 * ① 히어로: 검색 + 최근 본 선수 / 응원팀 경기  ② 점수 한 줄  ③ 그날 장면(가장 큰 요소)  ④ 능력 카드  ⑤ 지금 가장 잘하는 선수  ⑥ 팀 10칸
 * 날짜는 기록 기준일(마지막 경기일). 같은 장면을 한 화면에 두 번 넣지 않는다
 */
export default function Home() {
  // 장면은 「그날 장면」 카드의 큰 장면 자리에서 바로 재생한다 (별도 창 없음). 다른 곳에서 누르면 그 자리로 스크롤
  const [playing, setPlaying] = useState<Playing | null>(null);
  const play = (p: Playing) => {
    setPlaying(p);
    document.getElementById("day-scenes")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const onPlay = (clip: Clip, title: string) => play({ clip, title, sub: clip.precision === "game" ? "경기 하이라이트 · 처음부터" : undefined });
  const [myTeam] = useMyTeam();

  const meta = useQuery({ queryKey: qk.meta(), queryFn: ({ signal }) => getMeta(signal) });
  const day = useQuery({ queryKey: qk.day(null), queryFn: ({ signal }) => getDay(null, signal) });
  const bLeaders = useQuery({ queryKey: qk.leaders("batter"), queryFn: ({ signal }) => getLeaders("batter", signal) });
  const pLeaders = useQuery({ queryKey: qk.leaders("pitcher"), queryFn: ({ signal }) => getLeaders("pitcher", signal) });
  const topB = useQuery({ queryKey: qk.topBatters(), queryFn: ({ signal }) => getTopBatters(signal) });
  const topP = useQuery({ queryKey: qk.topPitchers(), queryFn: ({ signal }) => getTopPitchers(signal) });
  const standings = useQuery({ queryKey: qk.standings(), queryFn: ({ signal }) => getStandings(signal) });

  const asOf = meta.data?.data_as_of ?? null;
  const asOfMd = asOf ? md(asOf) : null;
  const season = meta.data?.season;
  // 첫 방문 추천 선수 = 지금 잘하는 선수 (타자 OPS 2명 + 선발 WHIP 2명)
  const recommended = [
    ...(topB.data?.batters ?? []).slice(0, 2).map((b) => ({ id: b.player_id, name: b.name, team: b.team })),
    ...(topP.data?.pitchers ?? []).slice(0, 2).map((p) => ({ id: p.player_id, name: p.name, team: p.team })),
  ];

  return (
    <>
      <Hero day={day.data} recommended={recommended} onPlay={onPlay} />

      <Wrap className="space-y-[72px] pt-8">
        <PostseasonCorner onPlay={onPlay} />

        <div className="space-y-6">
          {day.isError ? (
            <Retry label="경기 결과" onRetry={() => day.refetch()} />
          ) : day.data ? (
            <>
              <ScoreStrip day={day.data} isLast={day.data.date === asOf} />
              <DayScenes day={day.data} myTeam={myTeam} playing={playing} onPlay={play} />
            </>
          ) : (
            <div className="h-[560px] animate-pulse rounded-[28px] bg-surface-2" />
          )}
        </div>

        {bLeaders.isError && pLeaders.isError ? (
          <Retry label="능력 카드" onRetry={() => { bLeaders.refetch(); pLeaders.refetch(); }} />
        ) : (
          <AbilityCards batters={bLeaders.data} pitchers={pLeaders.data} asOf={asOfMd} />
        )}

        <TopPlayers
          batters={topB.data?.batters}
          pitchers={topP.data?.pitchers}
          sub={[season && `${season} 정규시즌`, asOfMd && `${asOfMd} 기준`, "타자는 규정타석 50% 이상, 투수는 규정이닝 50% 이상 선발"].filter(Boolean).join(" · ")}
        />

        <TeamRow teams={standings.data?.teams} sub={[season && `${season} 정규시즌 순위`, asOfMd && `${asOfMd} 기준`].filter(Boolean).join(" · ")} />
      </Wrap>
    </>
  );
}

/** 불러오기 실패 — 실패한 구역만 다시 시도 (09 ⑧) */
function Retry({ label, onRetry }: { label: string; onRetry: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-3xl border border-line bg-surface px-6 py-5 text-sm">
      <span className="text-fg-2">{label}을(를) 불러오지 못했어요</span>
      <button onClick={onRetry} className="rounded-xl bg-surface-2 px-4 py-2 font-bold hover:bg-surface-3">
        다시 시도
      </button>
    </div>
  );
}
