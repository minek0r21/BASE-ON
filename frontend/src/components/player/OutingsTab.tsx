"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getPlayerOutings, qk, type Clip } from "@/lib/api";
import { md, outingLine } from "@/lib/format";
import ScenePlayer from "@/components/ScenePlayer";
import StageTag from "@/components/StageTag";
import SceneButton from "@/components/SceneButton";

const RESULT_KO = { W: "승", L: "패", D: "무" } as const;

// 투수 경기 기록 (API-23). 기본층: 등판마다 「이 경기 하이라이트」, 보너스층: 확정 등판 장면 (docs/장면.md 6장)
export default function OutingsTab({
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
  const [playing, setPlaying] = useState<{ clip: Clip; label: string } | null>(null);
  const q = useQuery({
    queryKey: qk.outings(playerId, season, month),
    queryFn: ({ signal }) => getPlayerOutings(playerId, season, month, signal),
    placeholderData: keepPreviousData,
  });

  if (q.isPending) return <p className="text-muted">불러오는 중…</p>;
  if (q.isError) return <p className="text-muted">등판 기록을 불러오지 못했습니다.</p>;
  const d = q.data;
  if (!d.season) return <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">등판 기록이 없습니다.</p>;

  return (
    <div className="space-y-4">
      {playing && (
        <div className="sticky top-16 z-10">
          <ScenePlayer clip={playing.clip} label={playing.label} onClose={() => setPlaying(null)} />
        </div>
      )}

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

      <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
        {d.outings.map((o) => {
          const where = `${md(o.date)} ${o.home ? "vs" : "@"} ${o.opponent}`;
          const line = outingLine(o.line);
          return (
            <li key={o.outingId} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm">
              <span className="w-16 shrink-0 tabular-nums text-muted">
                {md(o.date)} ({o.weekday})
              </span>
              <StageTag label={o.stage_label} />
              <span className="shrink-0 font-semibold">
                {o.home ? "vs" : "@"} {o.opponent}
              </span>
              <span className="shrink-0 text-xs text-muted">{o.role}</span>
              <span className={`shrink-0 tabular-nums ${o.result === "W" ? "text-fg" : "text-muted"}`}>
                {RESULT_KO[o.result]} {o.score.team}:{o.score.opponent}
              </span>
              <span className="min-w-0 flex-1 truncate tabular-nums">{line}</span>
              {o.scene && (
                <SceneButton
                  clip={o.scene}
                  label={`${playerName} ${where} 등판 장면`}
                  onPlay={() => setPlaying({ clip: o.scene!, label: `${playerName} · ${where} · ${line}` })}
                />
              )}
              {o.highlight && (
                <SceneButton
                  clip={o.highlight}
                  label={`${where} 경기 하이라이트`}
                  onPlay={() => setPlaying({ clip: o.highlight!, label: `${where} · 경기 하이라이트` })}
                />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
