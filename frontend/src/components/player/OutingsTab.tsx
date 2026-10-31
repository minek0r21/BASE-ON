"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { SectionHead } from "@/components/home/common";
import InlinePlayer from "@/components/InlinePlayer";
import { Empty } from "@/components/ui/Chip";
import { getPlayerOutings, qk } from "@/lib/api";
import { innings, md, outingLine } from "@/lib/format";
import { GameLine, GameList, MonthChips, PlayButton, type Now } from "./GamesTab";

/**
 * 투수 경기 기록 (API-23) — 경기 기록 탭과 같은 줄 모양. 섹션 제목에 그 달 등판 · 이닝 · 탈삼진 · 실점, 무실점 등판은 구단 글자색.
 * 기본층: 등판마다 「하이라이트」, 보너스층: 확정 등판 장면 (docs/장면.md 6장). 재생은 그 줄 바로 아래
 */
export default function OutingsTab({ playerId, playerName, season, month, onChange }: {
  playerId: string;
  playerName: string;
  season: number | null;
  month: number | null;
  onChange: (season: number | null, month: number | null) => void;
}) {
  const [now, setNow] = useState<Now>(null);
  const q = useQuery({
    queryKey: qk.outings(playerId, season, month),
    queryFn: ({ signal }) => getPlayerOutings(playerId, season, month, signal),
    placeholderData: keepPreviousData,
  });

  if (q.isPending) return <div className="h-[420px] animate-pulse rounded-3xl bg-surface-2" />;
  if (q.isError) return <Empty text="등판 기록을 불러오지 못했어요" action={{ label: "다시 시도", onClick: () => q.refetch() }} />;
  const d = q.data;
  if (!d.season) return <Empty text="등판 기록이 없어요" />;

  const sum = d.outings.reduce((a, o) => ({ outs: a.outs + o.line.outs, so: a.so + o.line.so, r: a.r + o.line.r }), { outs: 0, so: 0, r: 0 });
  const sub = [`${d.season} 시즌 ${d.month}월 ${d.outings.length}경기`, `${innings(sum.outs)}이닝`, `탈삼진 ${sum.so}`, `실점 ${sum.r}`, "최신순"].join(" · ");

  return (
    <section>
      <SectionHead title="경기 기록" sub={sub} right={<MonthChips months={d.months} month={d.month} onPick={(m) => { setNow(null); onChange(d.season, m); }} />} />
      <GameList>
        {d.outings.map((o) => {
          const key = o.outingId;
          const where = `${md(o.date)} ${o.opponent}전`;
          const line = outingLine(o.line);
          const toggle = (k: string, p: Now) => setNow(now?.key === k ? null : p);
          return (
            <li key={key}>
              <GameLine
                date={`${md(o.date)} (${o.weekday})`} opponent={o.opponent} home={o.home} stage={o.stage_label} result={o.result} score={o.score} role={o.role}
                line={<span className={o.line.r === 0 ? "font-bold text-(--team-text)" : ""}>{line}</span>}
              >
                {o.scene && (
                  <PlayButton on={now?.key === `${key}-sc`} onClick={() => toggle(`${key}-sc`, { key: `${key}-sc`, clip: o.scene!, title: `${playerName} 등판 장면`, sub: `${where} · ${line}` })}>
                    등판 장면
                  </PlayButton>
                )}
                {o.highlight && (
                  <PlayButton on={now?.key === `${key}-hl`} onClick={() => toggle(`${key}-hl`, { key: `${key}-hl`, clip: o.highlight!, title: `${where} 하이라이트`, sub: o.stage_label ?? undefined })}>
                    하이라이트
                  </PlayButton>
                )}
              </GameLine>
              {now?.key.startsWith(`${key}-`) && <InlinePlayer playing={now} onClose={() => setNow(null)} className="mx-3 mb-3" />}
            </li>
          );
        })}
      </GameList>
    </section>
  );
}
