"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type PointerEvent } from "react";
import { Retry } from "@/components/ui/Chip";
import { TeamLogo } from "@/components/ui/Media";
import { getStandingsHistory, qk } from "@/lib/api";
import { md } from "@/lib/format";
import { teamHref, type Team } from "@/lib/teams";

const ROWS = 10;
const y = (rank: number) => ((rank - 1) / (ROWS - 1)) * 100;

/**
 * 06 팀 「순위 변동 보기」(API-28) — 주마다 마지막 경기일 순위를 선 10개로. 이 팀 선만 팀 색, 나머지는 회색.
 * 선 양 끝에 팀 이름표(왼쪽 = 첫 점 순위, 공동 순위는 「KIA·롯데·키움」처럼 묶음), 이 팀 점에는 순위 숫자 (11-02 사용자: 10팀 그대로 + 이름표).
 * 다른 팀 선 · 이름표에 올리면 그 팀 선이 진해진다. 그래프 위를 움직이면 그 주 순위를 위 줄에 보여 준다
 */
export default function RankFlow({ name, t, season }: { name: string; t: Team; season: number }) {
  const q = useQuery({ queryKey: qk.standingsHistory(season), queryFn: ({ signal }) => getStandingsHistory(season, signal) });
  const [hot, setHot] = useState<string | null>(null);
  const [at, setAt] = useState<number | null>(null);

  if (q.isError) return <div className="mt-4"><Retry text="순위 변동을 불러오지 못했어요" onRetry={() => q.refetch()} /></div>;
  const pts = q.data?.points;
  if (!pts) return <div className="mt-4 h-[392px] animate-pulse rounded-3xl bg-surface-2" />;
  if (pts.length < 2) return null;

  const n = pts.length;
  const x = (i: number) => (i / (n - 1)) * 100;
  const last = pts[n - 1];
  const order = Object.keys(last.ranks).sort((a, b) => last.ranks[a] - last.ranks[b]);
  const mine = pts.map((p) => p.ranks[name]);
  const line = (team: string) => pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(2)} ${y(p.ranks[team]).toFixed(2)}`).join(" ");
  const months = pts.map((p, i) => ({ i, m: Number(p.date.slice(5, 7)) })).filter((p, k, a) => (!k || p.m !== a[k - 1].m) && p.i < n - 1);
  const shown = pts[at ?? n - 1];
  const starts = [...new Set(order.map((k) => pts[0].ranks[k]))].sort((a, b) => a - b)
    .map((r) => [r, order.filter((k) => pts[0].ranks[k] === r)] as const);
  const tone = (k: string) => (k === name ? "font-bold" : hot === k ? "font-bold text-fg" : "text-fg-2");

  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    setAt(Math.round(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * (n - 1)));
  };

  return (
    <section className="mt-4 animate-appear rounded-3xl border border-line bg-surface p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-lg font-extrabold">
            {md(pts[0].date)} {mine[0]}위 <span className="text-muted" aria-hidden>→</span> {md(last.date)} <span style={{ color: t.text }}>{mine[n - 1]}위</span>
          </p>
          <p className="mt-1 text-xs text-fg-2">
            {season} 정규시즌 · 주마다 마지막 경기일 순위 · 최고 {Math.min(...mine)}위 · 최저 {Math.max(...mine)}위
          </p>
        </div>
        <p className="font-num text-sm" aria-live="polite">
          <span className="text-fg-2">{md(shown.date)}</span>
          <b className="ml-2" style={{ color: t.text }}>{name} {shown.ranks[name]}위</b>
          {hot && hot !== name && <b className="ml-2">{hot} {shown.ranks[hot]}위</b>}
        </p>
      </div>

      <div className="mt-6 flex gap-2">
        {/* 왼쪽 순위 눈금 */}
        <ol className="relative w-5 shrink-0 text-right font-num text-[11px] text-muted" aria-hidden>
          {Array.from({ length: ROWS }, (_, k) => (
            <li key={k} className="absolute right-0 -translate-y-1/2" style={{ top: `${y(k + 1)}%` }}>{k + 1}</li>
          ))}
        </ol>

        {/* 왼쪽 이름표 = 첫 점 순위. 공동 순위는 한 줄로 묶어 선과 높이를 맞춘다 */}
        <ul className="relative hidden w-[88px] shrink-0 sm:block">
          {starts.map(([r, teams]) => (
            <li key={r} className="absolute right-3 -translate-y-1/2 truncate text-right text-[11px] leading-none" style={{ top: `${y(r)}%`, maxWidth: 76 }}>
              {teams.map((k, j) => (
                <span key={k}>
                  {j > 0 && <span className="text-muted">·</span>}
                  <span onPointerEnter={() => setHot(k)} onPointerLeave={() => setHot(null)} className={tone(k)} style={k === name ? { color: t.text } : undefined}>{k}</span>
                </span>
              ))}
            </li>
          ))}
        </ul>

        <div className="relative h-[280px] flex-1" onPointerMove={onMove} onPointerLeave={() => { setAt(null); setHot(null); }}>
          {/* 5위 아래 = 포스트시즌 경계 */}
          <div className="absolute inset-x-0 border-t border-dashed border-line-strong" style={{ top: `${(y(5) + y(6)) / 2}%` }} aria-hidden />
          {at != null && <div className="absolute inset-y-0 border-l border-line-strong" style={{ left: `${x(at)}%` }} aria-hidden />}
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible" role="img"
               aria-label={`${name} 순위 변동: ${md(pts[0].date)} ${mine[0]}위에서 ${md(last.date)} ${mine[n - 1]}위`}>
            {order.filter((k) => k !== name).map((k) => (
              <g key={k} onPointerEnter={() => setHot(k)}>
                <path d={line(k)} fill="none" stroke="transparent" strokeWidth={14} vectorEffect="non-scaling-stroke" />
                <path d={line(k)} fill="none" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke"
                      className={`transition-[stroke,stroke-width,opacity] duration-150 ${hot === k ? "stroke-fg" : "stroke-line-strong opacity-60"}`}
                      strokeWidth={hot === k ? 2.5 : 1.5} />
              </g>
            ))}
            <path d={line(name)} fill="none" stroke={t.band} strokeWidth={3.5} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          </svg>
          {/* 이 팀 점 + 순위 숫자 (svg를 늘려 그리므로 점은 HTML로). 좁은 화면은 숫자 없이 작은 점 */}
          {mine.map((r, i) => (
            <span key={i} aria-hidden
                  className={`absolute flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-surface font-num text-[10px] leading-none font-bold text-white ${i === (at ?? -1) ? "h-3.5 w-3.5 sm:h-[24px] sm:w-[24px] sm:text-[12px]" : "h-2 w-2 sm:h-[20px] sm:w-[20px]"}`}
                  style={{ left: `${x(i)}%`, top: `${y(r)}%`, background: t.band }}>
              <span className="hidden sm:inline">{r}</span>
            </span>
          ))}
          {hot && hot !== name && at != null && (
            <span aria-hidden className="absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-fg"
                  style={{ left: `${x(at)}%`, top: `${y(shown.ranks[hot])}%` }} />
          )}
        </div>

        {/* 오른쪽 이름표 = 마지막 순위 순서 (공동 순위면 한 칸씩 내려 겹치지 않게) */}
        <ul className="relative w-8 shrink-0 sm:w-[84px]">
          {order.map((k, i) => (
            <li key={k} className="absolute left-0 -translate-y-1/2 sm:left-3" style={{ top: `${y(i + 1)}%` }}>
              <Link href={teamHref(k)} onPointerEnter={() => setHot(k)} onPointerLeave={() => setHot(null)} title={`${k} ${last.ranks[k]}위`}
                    className={`flex h-6 items-center gap-1.5 rounded-md pr-1 text-xs leading-none transition-opacity duration-150 hover:underline ${hot && hot !== k && k !== name ? "opacity-40" : ""}`}>
                <span className="flex w-6 justify-center"><TeamLogo team={k} height={16} /></span>
                <span className={`hidden sm:inline ${tone(k)}`} style={k === name ? { color: t.text } : undefined}>{k}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>

      {/* 아래 달 눈금 · 마지막 날 */}
      <div className="mt-3 flex gap-2 font-num text-[11px] text-muted" aria-hidden>
        <span className="w-5 shrink-0" />
        <span className="hidden w-[88px] shrink-0 sm:block" />
        <div className="relative h-4 flex-1">
          {months.map(({ i, m }) => (
            <span key={i} className="absolute -translate-x-1/2" style={{ left: `${x(i)}%` }}>{m}월</span>
          ))}
          <span className="absolute right-0 translate-x-1/2 font-bold text-fg-2">{md(last.date)}</span>
        </div>
        <span className="w-8 shrink-0 sm:w-[84px]" />
      </div>
      <p className="mt-3 flex items-center gap-2 text-[11px] text-muted">
        <span className="w-6 border-t border-dashed border-line-strong" aria-hidden /> 5위까지 포스트시즌
      </p>
    </section>
  );
}
