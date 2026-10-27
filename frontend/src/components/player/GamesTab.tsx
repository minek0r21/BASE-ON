"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getGamePas, getPaClip, getPlayerGames, qk, type Clip, type GameRow } from "@/lib/api";
import ScenePlayer from "@/components/ScenePlayer";
import StageTag from "@/components/StageTag";

const RESULT_KO = { W: "승", L: "패", D: "무" } as const;
const mdOf = (iso: string) => `${Number(iso.slice(5, 7))}.${Number(iso.slice(8, 10))}`;

type Playing = { clip: Clip; label: string };

// BO-PB-02 경기 기록 (FR-03). 기본층: 경기마다 「이 경기 하이라이트」, 보너스층: 확정 장면이 있는 타석의 ▶ (docs/장면.md 6장)
export default function GamesTab({
  playerId,
  playerName,
  season,
  month,
  onChange,
}: {
  playerId: string;
  playerName: string;
  season: number | null;
  month: number | null;
  onChange: (season: number | null, month: number | null) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [playing, setPlaying] = useState<Playing | null>(null);

  const q = useQuery({
    queryKey: qk.games(playerId, season, month),
    queryFn: ({ signal }) => getPlayerGames(playerId, season, month, signal),
    placeholderData: keepPreviousData,
  });

  if (q.isPending) return <p className="text-muted">불러오는 중…</p>;
  if (q.isError) return <p className="text-muted">경기 기록을 불러오지 못했습니다.</p>;
  const d = q.data;
  if (!d.season) return <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">타석 기록이 없습니다.</p>;

  return (
    <div className="space-y-4">
      {playing && (
        <div className="sticky top-16 z-10">
          <ScenePlayer clip={playing.clip} label={playing.label} onClose={() => setPlaying(null)} />
        </div>
      )}

      {/* 시즌·월 */}
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm">
          <span className="sr-only">시즌</span>
          <select
            value={d.season}
            onChange={(e) => onChange(Number(e.target.value), null)}
            className="rounded-lg border border-line bg-surface px-2 py-1.5"
          >
            {d.seasons.map((s) => (
              <option key={s} value={s}>
                {s} 시즌
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap gap-1" role="group" aria-label="월">
          {d.months.map((m) => (
            <button
              key={m}
              onClick={() => onChange(d.season, m)}
              aria-pressed={m === d.month}
              className={`rounded-full border px-3 py-1 text-sm ${
                m === d.month ? "border-fg bg-fg text-bg" : "border-line bg-surface text-muted hover:text-fg"
              }`}
            >
              {m}월
            </button>
          ))}
        </div>
      </div>

      {/* 경기 목록 */}
      <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
        {d.games.map((g) => (
          <GameItem
            key={g.gamePk}
            g={g}
            playerId={playerId}
            open={open === g.gamePk}
            onToggle={() => setOpen(open === g.gamePk ? null : g.gamePk)}
            onPlay={(clip, label) => setPlaying({ clip, label })}
            playerName={playerName}
          />
        ))}
      </ul>
    </div>
  );
}

function GameItem({
  g,
  playerId,
  playerName,
  open,
  onToggle,
  onPlay,
}: {
  g: GameRow;
  playerId: string;
  playerName: string;
  open: boolean;
  onToggle: () => void;
  onPlay: (clip: Clip, label: string) => void;
}) {
  const line = `${g.line.ab}타수 ${g.line.h}안타${g.line.hr ? ` ${g.line.hr}홈런` : ""}`;
  return (
    <li>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm">
        <button onClick={onToggle} aria-expanded={open} className="flex min-w-0 flex-1 items-center gap-3 text-left">
          <span className="w-16 shrink-0 tabular-nums text-muted">
            {mdOf(g.date)} ({g.weekday})
          </span>
          <StageTag label={g.stageLabel} />
          <span className="shrink-0 font-semibold">
            {g.home ? "vs" : "@"} {g.opponent}
          </span>
          <span className={`shrink-0 tabular-nums ${g.result === "W" ? "text-fg" : "text-muted"}`}>
            {RESULT_KO[g.result]} {g.score.team}:{g.score.opponent}
          </span>
          <span className="min-w-0 truncate text-muted">{line}</span>
        </button>
        {g.playerVideo && (
          <button
            onClick={() => onPlay(g.playerVideo!, `${playerName} · ${mdOf(g.date)} ${g.home ? "vs" : "@"} ${g.opponent} · ${g.playerVideo!.title}`)}
            className="shrink-0 rounded-lg border border-accent px-2.5 py-1 text-xs font-semibold hover:bg-bg"
          >
            ▶ {playerName} 영상
          </button>
        )}
        {g.highlight && (
          <button
            onClick={() => onPlay(g.highlight!, `${mdOf(g.date)} ${g.home ? "vs" : "@"} ${g.opponent}${g.stageLabel ? ` ${g.stageLabel}` : ""} · 경기 하이라이트`)}
            className="shrink-0 rounded-lg border border-line px-2.5 py-1 text-xs font-semibold hover:bg-bg"
          >
            이 경기 하이라이트
          </button>
        )}
      </div>
      {open && <GamePas gamePk={g.gamePk} playerId={playerId} playerName={playerName} date={g.date} onPlay={onPlay} />}
    </li>
  );
}

function GamePas({
  gamePk,
  playerId,
  playerName,
  date,
  onPlay,
}: {
  gamePk: string;
  playerId: string;
  playerName: string;
  date: string;
  onPlay: (clip: Clip, label: string) => void;
}) {
  const q = useQuery({ queryKey: qk.gamePas(gamePk, playerId), queryFn: ({ signal }) => getGamePas(gamePk, playerId, signal) });
  if (q.isPending) return <p className="px-4 pb-3 text-sm text-muted">불러오는 중…</p>;
  if (q.isError) return <p className="px-4 pb-3 text-sm text-muted">타석을 불러오지 못했습니다.</p>;

  const playPa = async (paId: string, label: string) => {
    const clip = await getPaClip(paId);
    if (clip) onPlay(clip, label);
  };

  return (
    <ol className="space-y-1 bg-bg px-4 py-3 text-sm">
      {q.data.pas.map((p) => {
        const label = `${playerName} · ${mdOf(date)} ${p.inning}회${p.inning_half} ${p.events_ko}`;
        return (
          <li key={p.pa_id} className="flex items-center gap-3">
            <span className="w-14 shrink-0 tabular-nums text-muted">
              {p.inning}회{p.inning_half}
            </span>
            <span className={`shrink-0 ${p.post_hr_seq ? "" : "w-20"} ${p.events === "home_run" ? "font-bold" : ""}`}>
              {p.events_ko}
              {p.post_hr_seq ? ` (포스트시즌 ${p.post_hr_seq}호)` : p.hr_seq ? ` (${p.hr_seq}호)` : ""}
            </span>
            <span className="min-w-0 flex-1 truncate text-muted">투수 {p.pitcher.name}</span>
            {p.has_video && (
              <button
                onClick={() => playPa(p.pa_id, label)}
                className="shrink-0 rounded-full bg-accent px-2.5 py-0.5 text-xs font-bold text-black"
                aria-label={`${label} 장면 재생`}
              >
                ▶
              </button>
            )}
          </li>
        );
      })}
    </ol>
  );
}
