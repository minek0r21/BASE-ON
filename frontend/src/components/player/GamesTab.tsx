"use client";

import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import type { Playing } from "@/components/home/DayScenes";
import { SectionHead, gameHref } from "@/components/home/common";
import InlinePlayer from "@/components/InlinePlayer";
import StageTag from "@/components/StageTag";
import { Chip, Empty } from "@/components/ui/Chip";
import { PlayGlyph, TeamLogo } from "@/components/ui/Media";
import { getGamePas, getPaClip, getPlayerGames, qk, type GameRow } from "@/lib/api";
import { md, rate3 } from "@/lib/format";

const RESULT_KO = { W: "승", L: "패", D: "무" } as const;

export type Now = (Playing & { key: string }) | null;

/**
 * BO-PB-02 경기 기록 (FR-03) — 섹션 제목(그 달 경기 수 · 타율 · 홈런) + 월 칩, 경기 줄. 시즌은 탭 줄 오른쪽 선택 하나로 (10-31 사용자).
 * 기본층: 경기마다 「하이라이트」, 보너스층: 확정 장면이 있는 타석의 ▶ (docs/장면.md 6장). 재생은 그 줄 바로 아래
 */
export default function GamesTab({ playerId, playerName, season, month, onChange }: {
  playerId: string;
  playerName: string;
  season: number | null;
  month: number | null;
  onChange: (season: number | null, month: number | null) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [now, setNow] = useState<Now>(null);
  const q = useQuery({
    queryKey: qk.games(playerId, season, month),
    queryFn: ({ signal }) => getPlayerGames(playerId, season, month, signal),
    placeholderData: keepPreviousData,
  });

  if (q.isPending) return <div className="h-[520px] animate-pulse rounded-3xl bg-surface-2" />;
  if (q.isError) return <Empty text="경기 기록을 불러오지 못했어요" action={{ label: "다시 시도", onClick: () => q.refetch() }} />;
  const d = q.data;
  if (!d.season) return <Empty text="타석 기록이 없어요" />;

  const sum = d.games.reduce((a, g) => ({ ab: a.ab + g.line.ab, h: a.h + g.line.h, hr: a.hr + g.line.hr }), { ab: 0, h: 0, hr: 0 });
  const sub = [`${d.season} 시즌 ${d.month}월 ${d.games.length}경기`, `${sum.ab}타수 ${sum.h}안타`, sum.ab && `타율 ${rate3(sum.h / sum.ab)}`, `홈런 ${sum.hr}`, "최신순"]
    .filter(Boolean).join(" · ");

  return (
    <section className="animate-appear">
      <SectionHead title="경기 기록" sub={sub} right={<MonthChips months={d.months} month={d.month} onPick={(m) => { setNow(null); onChange(d.season, m); }} />} />
      <GameList>
        {d.games.map((g) => {
          const key = g.gamePk;
          const where = `${md(g.date)} ${g.opponent}전`;
          return (
            <li key={key}>
              <GameLine
                date={`${md(g.date)} (${g.weekday})`} opponent={g.opponent} home={g.home} stage={g.stageLabel} result={g.result} score={g.score}
                line={<>{g.line.ab}타수 {g.line.h}안타{g.line.hr > 0 && <b className="ml-1 font-bold text-(--team-text)">{g.line.hr}홈런</b>}</>}
                open={open === key} onToggle={() => setOpen(open === key ? null : key)} toggleLabel="타석"
              >
                {g.playerVideo && (
                  <PlayButton on={now?.key === `${key}-me`} onClick={() => setNow(now?.key === `${key}-me` ? null : { key: `${key}-me`, clip: g.playerVideo!, title: `${playerName} 영상`, sub: where })}>
                    선수 영상
                  </PlayButton>
                )}
                <Link href={gameHref(g.gamePk)} className="flex h-8 items-center rounded-full px-2 text-xs font-bold text-brand-text hover:underline">경기 상세 ›</Link>
                {g.highlight && (
                  <PlayButton on={now?.key === `${key}-hl`} onClick={() => setNow(now?.key === `${key}-hl` ? null : { key: `${key}-hl`, clip: g.highlight!, title: `${where} 하이라이트`, sub: g.stageLabel ?? undefined })}>
                    하이라이트
                  </PlayButton>
                )}
              </GameLine>
              {open === key && <GamePas gamePk={g.gamePk} playerId={playerId} playerName={playerName} g={g} now={now} onPlay={setNow} />}
              {now?.key.startsWith(`${key}-`) && <InlinePlayer playing={now} onClose={() => setNow(null)} className="mx-3 mb-3" />}
            </li>
          );
        })}
      </GameList>
    </section>
  );
}

/** 이 경기 타석 — 홈런은 굵게 + 시즌 몇 호, 확정 장면이 있으면 ▶ */
function GamePas({ gamePk, playerId, playerName, g, now, onPlay }: {
  gamePk: string; playerId: string; playerName: string; g: GameRow; now: Now; onPlay: (p: Now) => void;
}) {
  const q = useQuery({ queryKey: qk.gamePas(gamePk, playerId), queryFn: ({ signal }) => getGamePas(gamePk, playerId, signal) });
  if (q.isPending) return <p className="mx-3 mb-3 rounded-2xl bg-surface-2 px-4 py-3 text-[13px] text-fg-2">불러오는 중…</p>;
  if (q.isError) return <p className="mx-3 mb-3 rounded-2xl bg-surface-2 px-4 py-3 text-[13px] text-fg-2">타석을 불러오지 못했어요</p>;

  const play = async (paId: string, title: string) => {
    const key = `${gamePk}-pa-${paId}`;
    if (now?.key === key) return onPlay(null);
    const clip = await getPaClip(paId);
    if (clip) onPlay({ key, clip, title, sub: `${md(g.date)} ${g.opponent}전` });
  };

  return (
    <ol className="mx-3 mb-3 divide-y divide-line rounded-2xl bg-surface-2 px-4">
      {q.data.pas.map((p) => {
        const hr = p.events === "home_run";
        const seq = p.post_hr_seq ? `포스트시즌 ${p.post_hr_seq}호` : p.hr_seq ? `시즌 ${p.hr_seq}호` : null;
        return (
          <li key={p.pa_id} className="flex h-11 items-center gap-4 text-[13px]">
            <span className="w-14 shrink-0 font-num text-fg-2">{p.inning}회{p.inning_half}</span>
            <span className={`w-36 shrink-0 truncate ${hr ? "font-bold text-(--team-text)" : "font-medium"}`}>
              {p.events_ko}{hr && seq && <span className="ml-1.5 text-xs">{seq}</span>}
            </span>
            <span className="min-w-0 flex-1 truncate text-fg-2">vs {p.pitcher.name}</span>
            {p.has_video && (
              <button
                onClick={() => play(p.pa_id, `${playerName} ${p.inning}회${p.inning_half} ${p.events_ko}`)}
                aria-expanded={now?.key === `${gamePk}-pa-${p.pa_id}`}
                aria-label={`${p.inning}회${p.inning_half} ${p.events_ko} 장면 재생`}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-white"
              >
                <PlayGlyph size={9} />
              </button>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/* ---- 경기 기록 · 등판 기록이 같이 쓰는 조각 ---- */

export function MonthChips({ months, month, onPick }: { months: number[]; month: number | null; onPick: (m: number) => void }) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="월">
      {months.map((m) => <Chip key={m} on={m === month} onClick={() => onPick(m)}>{m}월</Chip>)}
    </div>
  );
}

export function GameList({ children }: { children: ReactNode }) {
  return <ul className="divide-y divide-line overflow-hidden rounded-3xl border border-line bg-surface">{children}</ul>;
}

/** 경기 한 줄 — 날짜 · 상대(로고 + 홈/원정) · 결과 · 점수 · 내 기록, 오른쪽 재생 버튼. 가운데를 누르면 아래로 펼친다.
 *  홈 · 원정은 「vs · @」 대신 글자로 (06 팀 「최근 경기」와 같은 표기, 10-31 사용자) */
export function GameLine({ date, opponent, home, stage, result, score, line, role, open, onToggle, toggleLabel, children }: {
  date: string; opponent: string; home: boolean; stage: string | null; result: "W" | "L" | "D"; score: { team: number; opponent: number };
  line: ReactNode; role?: string; open?: boolean; onToggle?: () => void; toggleLabel?: string; children?: ReactNode;
}) {
  const body = (
    <>
      <span className="w-[72px] shrink-0 font-num text-[13px] text-fg-2">{date}</span>
      <span className="flex w-[120px] shrink-0 items-center gap-2">
        <TeamLogo team={opponent} height={18} />
        <span className="truncate text-[15px] font-bold">{opponent}</span>
        <span className="shrink-0 text-xs text-fg-2">{home ? "홈" : "원정"}</span>
      </span>
      <StageTag label={stage} />
      {role && <span className="shrink-0 text-xs text-fg-2">{role}</span>}
      <span className="flex w-[84px] shrink-0 items-center gap-2">
        <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${result === "W" ? "bg-(--team) text-white" : "bg-surface-2 text-fg-2"}`}>{RESULT_KO[result]}</span>
        <span className="font-num text-sm font-semibold">{score.team}:{score.opponent}</span>
      </span>
      <span className="min-w-0 flex-1 truncate text-sm">{line}</span>
    </>
  );
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3">
      {onToggle ? (
        <button onClick={onToggle} aria-expanded={open} className="group flex min-w-0 flex-1 items-center gap-4 text-left">
          {body}
          <span className="shrink-0 text-xs font-bold text-fg-2 group-hover:text-fg">{toggleLabel} {open ? "▴" : "▾"}</span>
        </button>
      ) : (
        <div className="flex min-w-0 flex-1 items-center gap-4">{body}</div>
      )}
      {children && <div className="flex shrink-0 gap-2">{children}</div>}
    </div>
  );
}

export function PlayButton({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      aria-expanded={on}
      className="flex h-8 items-center gap-1.5 rounded-full border border-line bg-surface px-3 text-xs font-bold hover:border-accent hover:bg-accent hover:text-white aria-expanded:border-accent aria-expanded:bg-accent aria-expanded:text-white"
    >
      <PlayGlyph size={7} /> {children}
    </button>
  );
}
