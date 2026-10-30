"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Wrap, clipLength } from "@/components/home/common";
import type { Playing } from "@/components/home/DayScenes";
import InlinePlayer from "@/components/InlinePlayer";
import WeekStrip from "@/components/schedule/WeekStrip";
import { Chip, Empty } from "@/components/ui/Chip";
import { PlayGlyph, TeamLogo, mmss } from "@/components/ui/Media";
import { getDay, getMeta, qk, type DayGame, type DayHomeRun } from "@/lib/api";
import { longDate } from "@/lib/dates";
import { md } from "@/lib/format";
import { useMyTeam } from "@/lib/local";
import { team as teamOf, type Team } from "@/lib/teams";

/**
 * 08 일정 (Figma 158:2099) — 한 주 띠(API-34) → 고른 날의 경기 카드(API-14): 점수 · 이닝별 점수판 · 그 경기 홈런 칩.
 * 장면 있는 홈런 칩은 잉크 바탕이고 누르면 그 카드 안에서 바로 재생한다 (별도 창 없음). 영상 없는 홈런은 연한 칩
 * 경기장 이름은 데이터에 없어 넣지 않는다. 「경기 기록 ›」(04 경기 상세)은 화면을 옮긴 뒤 연결한다
 */
export default function ScheduleView() {
  const params = useSearchParams();
  const router = useRouter();
  const [myTeam] = useMyTeam();
  const meta = useQuery({ queryKey: qk.meta(), queryFn: ({ signal }) => getMeta(signal) });
  const asOf = meta.data?.data_as_of ?? null;
  const date = params.get("date") ?? asOf;
  const day = useQuery({ queryKey: qk.day(date), queryFn: ({ signal }) => getDay(date, signal), enabled: !!date });
  const [onlyMine, setOnlyMine] = useState(false);
  const [playing, setPlaying] = useState<(Playing & { gamePk: string }) | null>(null);
  const pick = (d: string) => {
    setPlaying(null);
    router.replace(`/schedule/?date=${d}`, { scroll: false });
  };

  const games = day.data?.games ?? [];
  const mine = (g: DayGame) => !!myTeam && (g.away.team === myTeam || g.home.team === myTeam);
  const shown = games.filter((g) => !onlyMine || mine(g)).sort((a, b) => Number(mine(b)) - Number(mine(a)));
  const c = day.data?.scene_counts;
  const future = !!(date && asOf && date > asOf);

  return (
    <Wrap className="pt-10 pb-24">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[40px] font-extrabold tracking-tight">일정</h1>
          <p className="mt-1.5 text-sm text-fg-2">
            {[meta.data?.season && `${meta.data.season} 정규시즌`, asOf && `${md(asOf)} 기준`].filter(Boolean).join(" · ")}
          </p>
        </div>
        {myTeam && (
          <div className="flex items-center gap-2" role="group" aria-label="팀">
            <span className="text-xs text-muted">팀</span>
            <Chip on={!onlyMine} onClick={() => setOnlyMine(false)}>전체</Chip>
            <Chip on={onlyMine} onClick={() => setOnlyMine(true)}>
              <TeamLogo team={myTeam} height={14} /> 응원팀만
            </Chip>
          </div>
        )}
      </div>

      {date && (
        <div className="mt-7">
          <WeekStrip date={date} onPick={pick} caption={(d) => `${d.games}경기 · 홈런 ${d.home_runs}`} />
        </div>
      )}

      {future ? (
        <Empty text="공개 데이터에 아직 없는 날짜예요" action={asOf ? { label: "마지막 경기일 보기", onClick: () => pick(asOf) } : undefined} />
      ) : day.isError ? (
        <Empty text="경기 결과를 불러오지 못했어요" action={{ label: "다시 시도", onClick: () => day.refetch() }} />
      ) : !day.data ? (
        <div className="mt-8 h-[600px] animate-pulse rounded-3xl bg-surface-2" />
      ) : games.length === 0 ? (
        <Empty text="이날은 경기가 없어요" />
      ) : (
        <>
          <div className="mt-9 flex flex-wrap items-end justify-between gap-3">
            <h2 className="text-2xl font-bold">
              {longDate(day.data.date)} · {games.length}경기
            </h2>
            {c && (
              <p className="flex items-center gap-2 text-xs text-fg-2">
                <span className="flex h-6 items-center gap-1 rounded-full bg-accent px-2.5 font-bold text-white"><PlayGlyph size={6} /> 장면 있는 홈런</span>
                <span className="flex h-6 items-center rounded-full bg-surface-2 px-2.5 font-medium">영상 없음</span>
                홈런 {c.home_runs}개 중 장면 {c.home_run_scenes}개
              </p>
            )}
          </div>
          {onlyMine && shown.length === 0 ? (
            <Empty text={`이날은 ${myTeam} 경기가 없어요`} />
          ) : (
            <ul className="mt-5 space-y-4">
              {shown.map((g) => (
                <GameCard
                  key={g.game_pk}
                  game={g}
                  mine={mine(g) ? teamOf(myTeam) : null}
                  playing={playing?.gamePk === g.game_pk ? playing : null}
                  onPlay={(p) => setPlaying(p && { ...p, gamePk: g.game_pk })}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </Wrap>
  );
}

const hrText = (h: DayHomeRun) => `${h.name}${h.hrSeq ? ` ${h.hrSeq}호` : ""} · ${h.inning}회${h.inningHalf}`;

function GameCard({ game: g, mine, playing, onPlay }: {
  game: DayGame;
  mine: Team | null;
  playing: Playing | null;
  onPlay: (p: Playing | null) => void;
}) {
  const extra = (g.innings ?? 9) > 9 ? `연장 ${g.innings}회` : null;
  const draw = g.away.result === "D" ? "무승부" : null;
  return (
    <li
      className="grid items-center gap-6 rounded-3xl border border-line bg-surface p-6 lg:grid-cols-[220px_auto_1fr]"
      style={mine ? { borderColor: mine.band, borderWidth: 2 } : undefined} // 응원팀 경기는 팀 색 테두리
    >
      <div>
        <p className="flex items-center gap-1.5 text-xs text-fg-2">
          {["종료", extra, draw, g.stage_label].filter(Boolean).join(" · ")}
          {mine && <span className="rounded-md bg-brand-soft px-1.5 py-0.5 text-[11px] font-bold text-brand-text">응원팀</span>}
        </p>
        <div className="mt-3 space-y-2">
          {([[g.away, "원정"], [g.home, "홈"]] as const).map(([t, side]) => (
            <p key={side} className="flex items-center gap-2.5">
              <TeamLogo team={t.team} height={22} />
              <span className={`flex-1 text-[15px] ${t.result === "W" ? "font-bold" : "font-medium text-fg-2"}`}>{t.team}</span>
              <span className="text-[11px] text-muted">{side}</span>
              <span className={`w-8 text-right font-display text-[28px] leading-none font-extrabold ${t.result === "W" ? "" : "text-muted"}`}>{t.score}</span>
            </p>
          ))}
        </div>
      </div>

      <LineScore game={g} />

      <div className="min-w-0">
        <p className="text-xs text-fg-2">{g.homeRuns.length ? `이 경기 홈런 ${g.homeRuns.length}개` : "이 경기 홈런 없음"}</p>
        {g.homeRuns.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {g.homeRuns.map((h, i) => (
              <li key={`${h.player_id}-${i}`}>
                {h.clip ? (
                  <button
                    onClick={() => onPlay({ clip: h.clip!, title: `${h.name}${h.hrSeq ? ` ${h.hrSeq}호` : ""} 홈런`, sub: `${h.inning}회${h.inningHalf}` })}
                    aria-current={playing?.title.startsWith(`${h.name}${h.hrSeq ? ` ${h.hrSeq}호` : ""} 홈런`) ? "true" : undefined}
                    className="flex h-7 items-center gap-1 rounded-full bg-accent px-2.5 text-xs font-bold text-white hover:opacity-90 aria-[current=true]:bg-brand"
                  >
                    <PlayGlyph size={6} /> {hrText(h)}
                  </button>
                ) : (
                  <span className="flex h-7 items-center rounded-full bg-surface-2 px-2.5 text-xs font-medium text-fg-2" title="영상 없음">
                    {hrText(h)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {g.highlight && (
          <button
            onClick={() => onPlay({ clip: g.highlight!, title: `${g.away.team} ${g.away.score} : ${g.home.score} ${g.home.team} 경기 하이라이트`, sub: "처음부터" })}
            className="mt-3 flex h-8 items-center gap-1.5 rounded-full bg-surface-2 px-3.5 text-xs font-bold hover:bg-surface-3"
          >
            <PlayGlyph size={7} /> 이 경기 하이라이트 {mmss(clipLength(g.highlight))}
          </button>
        )}
      </div>

      {playing && <InlinePlayer playing={playing} onClose={() => onPlay(null)} className="lg:col-span-3" />}
    </li>
  );
}

/** 이닝별 점수판 — 9회(연장이면 그만큼) + 점수 · 안타. 안 한 반 이닝은 「–」 */
function LineScore({ game: g }: { game: DayGame }) {
  const n = g.line.away.length;
  const cell = "w-6 text-center";
  return (
    <div className="overflow-x-auto rounded-2xl bg-surface-2 px-4 py-3">
      <table className="font-num text-xs">
        <thead>
          <tr className="text-muted">
            <th className="w-10" />
            {Array.from({ length: n }, (_, i) => <th key={i} className={`${cell} font-medium`}>{i + 1}</th>)}
            <th className="w-9 text-center font-medium">점수</th>
            <th className="w-9 text-center font-medium">안타</th>
          </tr>
        </thead>
        <tbody>
          {([["away", g.away], ["home", g.home]] as const).map(([side, t]) => (
            <tr key={side} className="h-7">
              <td className="text-left font-bold">{t.team}</td>
              {g.line[side].map((r, i) => (
                <td key={i} className={`${cell} ${r ? "font-bold" : "text-fg-2"}`}>{r ?? "–"}</td>
              ))}
              <td className="text-center font-display text-base font-extrabold">{t.score}</td>
              <td className="text-center font-bold">{side === "away" ? g.line.away_h : g.line.home_h}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
