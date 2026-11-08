"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Wrap, clipLength, gameHref } from "@/components/home/common";
import type { Playing } from "@/components/home/DayScenes";
import InlinePlayer from "@/components/InlinePlayer";
import GameScore from "@/components/schedule/GameScore";
import NoGames from "@/components/schedule/NoGames";
import WeekStrip from "@/components/schedule/WeekStrip";
import { Chip, Empty } from "@/components/ui/Chip";
import { PlayGlyph, TeamLogo, mmss } from "@/components/ui/Media";
import Seg from "@/components/ui/Seg";
import { getDay, getMeta, qk, type DayGame, type DayHomeRun } from "@/lib/api";
import { longDate } from "@/lib/dates";
import { md } from "@/lib/format";
import { useMyTeam } from "@/lib/local";
import { team as teamOf, type Team } from "@/lib/teams";
import { ChevronDown } from "@/components/ui/Chevron";

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
    <Wrap className="pt-3 pb-6 md:pt-10 md:pb-24">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-black tracking-tight md:text-[40px] md:font-extrabold">일정</h1>
          <p className="mt-1 text-xs text-fg-2 md:mt-1.5 md:text-sm">
            {[meta.data?.season && `${meta.data.season} 정규시즌`, asOf && `${md(asOf)} 기준`].filter(Boolean).join(" · ")}
          </p>
        </div>
        {myTeam && (
          <div className="hidden items-center gap-2 md:flex" role="group" aria-label="팀">
            <span className="text-xs text-muted">팀</span>
            <Chip on={!onlyMine} onClick={() => setOnlyMine(false)}>전체</Chip>
            <Chip on={onlyMine} onClick={() => setOnlyMine(true)}>
              <TeamLogo team={myTeam} height={14} /> 응원팀만
            </Chip>
          </div>
        )}
      </div>

      {myTeam && (
        <Seg className="mt-3 md:hidden" label="팀" value={onlyMine ? "mine" : "all"} onChange={(v) => setOnlyMine(v === "mine")}
             items={[{ key: "all", label: "전체" }, { key: "mine", label: `${myTeam} 경기만` }]} />
      )}

      {date && (
        <div className="mt-2 md:mt-7">
          <WeekStrip date={date} onPick={pick} caption={(d) => `${d.games}경기 · 홈런 ${d.home_runs}`} short={(d) => `${d.games}경기`} />
        </div>
      )}

      {date && (future || day.data?.games.length === 0) ? (
        <NoGames date={date} asOf={asOf} prev={day.data?.prev_date ?? null} next={day.data?.next_date ?? null} onPick={pick} />
      ) : day.isError || (!date && meta.isError) ? (
        <Empty text="경기 결과를 불러오지 못했어요" sub="잠시 뒤 다시 시도해 주세요."
               action={{ label: "다시 시도", onClick: () => (date ? day.refetch() : meta.refetch()) }} />
      ) : !day.data ? (
        <div className="mt-8 h-[600px] animate-pulse rounded-3xl bg-surface-2" />
      ) : (
        <div className="animate-appear">
          <div className="mt-5 flex flex-wrap items-end justify-between gap-x-3 gap-y-1 md:mt-9">
            <h2 className="text-xl font-black md:text-2xl md:font-bold">
              {longDate(day.data.date)} · {games.length}경기
            </h2>
            {c && (
              <p className="flex items-center gap-2 text-xs text-fg-2">
                <span className="hidden h-6 items-center gap-1 rounded-full bg-accent px-2.5 font-bold text-white md:flex"><PlayGlyph size={6} /> 장면 있는 홈런</span>
                <span className="hidden h-6 items-center rounded-full bg-surface-2 px-2.5 font-medium md:flex">영상 없음</span>
                홈런 {c.home_runs}개 중 장면 {c.home_run_scenes}개
              </p>
            )}
          </div>
          {onlyMine && shown.length === 0 ? (
            <Empty text={`이날은 ${myTeam} 경기가 없어요`} />
          ) : (
            <ul className="mt-2 space-y-2 md:mt-5 md:space-y-4">
              {shown.map((g, i) => (
                <GameCard
                  key={g.game_pk}
                  game={g}
                  first={i < 2}
                  mine={mine(g) ? teamOf(myTeam) : null}
                  playing={playing?.gamePk === g.game_pk ? playing : null}
                  onPlay={(p) => setPlaying(p && { ...p, gamePk: g.game_pk })}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </Wrap>
  );
}

const hrText = (h: DayHomeRun) => `${h.name}${h.hrSeq ? ` ${h.hrSeq}호` : ""} · ${h.inning}회${h.inningHalf}`;

function GameCard({ game: g, first, mine, playing, onPlay }: {
  game: DayGame;
  /** 모바일은 위 두 경기만 펼쳐 둔다 (M08). 나머지는 누르면 펼침 */
  first: boolean;
  mine: Team | null;
  playing: Playing | null;
  onPlay: (p: Playing | null) => void;
}) {
  const [opened, setOpened] = useState(false);
  const open = first || opened || !!mine || !!playing;
  const fold = open ? "" : "hidden md:block";
  const extra = (g.innings ?? 9) > 9 ? `연장 ${g.innings}회` : null;
  const draw = g.away.result === "D" ? "무승부" : null;
  return (
    <li
      className="grid items-center gap-2.5 rounded-2xl border border-line bg-surface p-3.5 md:gap-6 md:rounded-3xl md:p-6 lg:grid-cols-[220px_auto_1fr]"
      style={mine ? { borderColor: mine.band, borderWidth: 2 } : undefined} // 응원팀 경기는 팀 색 테두리
    >
      {!open && (
        <button onClick={() => setOpened(true)} aria-expanded={false} className="flex w-full items-center gap-2 text-left md:hidden">
          <span className="min-w-0 flex-1">
            <GameScore game={g} />
            <span className="mt-1 block text-center text-xs text-fg-2">
              {["종료", extra, draw].filter(Boolean).join(" · ")} · {g.homeRuns.length ? `이 경기 홈런 ${g.homeRuns.length}개` : "이 경기 홈런 없음"}
            </span>
          </span>
          <ChevronDown />
        </button>
      )}
      <div className={fold}>
        <p className="flex items-center gap-1.5 text-xs text-fg-2">
          {["종료", extra, draw, g.stage_label].filter(Boolean).join(" · ")}
          {mine && <span className="rounded-md bg-brand-soft px-1.5 py-0.5 text-[11px] font-bold text-brand-text">응원팀</span>}
        </p>
        <div className="mt-3 hidden space-y-2 md:block">
          {([[g.away, "원정"], [g.home, "홈"]] as const).map(([t, side]) => (
            <p key={side} className="flex items-center gap-2.5">
              <TeamLogo team={t.team} height={22} />
              <span className={`flex-1 text-[15px] ${t.result === "W" ? "font-bold" : "font-medium text-fg-2"}`}>{t.team}</span>
              <span className="text-[11px] text-muted">{side}</span>
              <span className={`w-8 text-right font-display text-[28px] leading-none font-extrabold ${t.result === "W" ? "" : "text-muted"}`}>{t.score}</span>
            </p>
          ))}
        </div>
        <Link href={gameHref(g.game_pk)} className="mt-3 hidden text-xs font-bold text-brand-text hover:underline md:inline-block">경기 상세 ›</Link>
      </div>

      <div className={`min-w-0 ${fold}`}><LineScore game={g} /></div>

      <div className={`min-w-0 ${fold}`}>
        <p className="text-xs font-bold text-fg-2 md:font-normal">{g.homeRuns.length ? `이 경기 홈런 ${g.homeRuns.length}개` : "이 경기 홈런 없음"}</p>
        {g.homeRuns.length > 0 && (
          <ul className="mt-2 divide-y divide-line overflow-hidden rounded-xl bg-surface-2 md:flex md:flex-wrap md:gap-1.5 md:divide-y-0 md:overflow-visible md:rounded-none md:bg-transparent">
            {g.homeRuns.map((h, i) => (
              <li key={`${h.player_id}-${i}`}>
                {h.clip ? (
                  <button
                    onClick={() => onPlay({ clip: h.clip!, title: `${h.name}${h.hrSeq ? ` ${h.hrSeq}호` : ""} 홈런`, sub: `${h.inning}회${h.inningHalf}` })}
                    aria-current={playing?.title.startsWith(`${h.name}${h.hrSeq ? ` ${h.hrSeq}호` : ""} 홈런`) ? "true" : undefined}
                    className="flex h-11 w-full items-center gap-2 px-3.5 text-left text-[13px] font-bold hover:bg-surface-3 aria-[current=true]:bg-brand aria-[current=true]:text-white md:h-7 md:w-auto md:gap-1 md:rounded-full md:bg-accent md:px-2.5 md:text-xs md:text-white md:hover:bg-accent md:hover:opacity-90"
                  >
                    <PlayGlyph size={6} /> {hrText(h)}
                  </button>
                ) : (
                  <span className="flex h-11 items-center px-3.5 text-[13px] font-medium text-fg-2 md:h-7 md:rounded-full md:bg-surface-2 md:px-2.5 md:text-xs" title="영상 없음">
                    {hrText(h)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-2.5 grid grid-cols-2 gap-1.5 md:mt-3 md:block">
          {g.highlight && (
            <button
              onClick={() => onPlay({ clip: g.highlight!, title: `${g.away.team} ${g.away.score} : ${g.home.score} ${g.home.team} 경기 하이라이트`, sub: "처음부터" })}
              className="flex h-11 items-center justify-center gap-1.5 rounded-xl bg-accent text-[13px] font-bold text-white hover:bg-surface-3 md:h-8 md:rounded-full md:bg-surface-2 md:px-3.5 md:text-xs md:text-fg"
            >
              <PlayGlyph size={7} /> <span className="md:hidden">하이라이트</span><span className="hidden md:inline">이 경기 하이라이트</span> {mmss(clipLength(g.highlight))}
            </button>
          )}
          <Link href={gameHref(g.game_pk)} className="flex h-11 items-center justify-center rounded-xl bg-surface-2 text-[13px] font-bold md:hidden">경기 기록 ›</Link>
        </div>
      </div>

      {playing && <InlinePlayer playing={playing} onClose={() => onPlay(null)} className="lg:col-span-3" />}
    </li>
  );
}

/** 이닝별 점수판 — 9회(연장이면 그만큼) + 점수 · 안타. 안 한 반 이닝은 「–」 */
function LineScore({ game: g }: { game: DayGame }) {
  const n = g.line.away.length;
  const cell = "text-center md:w-6";
  return (
    <div className="overflow-x-auto rounded-xl bg-surface-2 px-2.5 py-2 md:rounded-2xl md:px-4 md:py-3">
      {/* 모바일은 표가 폭을 다 쓰고 이닝 칸이 남는 폭을 나눠 가진다 — 연장 11회도 옆으로 밀지 않는다 */}
      <table className="w-full table-fixed font-num text-xs md:w-auto md:table-auto">
        <thead>
          <tr className="text-muted">
            <th className="w-10" />
            {Array.from({ length: n }, (_, i) => <th key={i} className={`${cell} font-medium`}>{i + 1}</th>)}
            <th className="w-7 text-center font-medium md:w-9">점수</th>
            <th className="w-7 text-center font-medium md:w-9">안타</th>
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
