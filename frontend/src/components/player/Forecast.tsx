"use client";

import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { PlayerAvatar, TeamLogo } from "@/components/ui/Media";
import { ApiError, getForecast, qk, searchPlayers, type Forecast, type ForecastKey } from "@/lib/api";
import { rate3 } from "@/lib/format";
import type { Role } from "./Hero";

const ROWS: [ForecastKey, string][] = [
  ["single", "1루타"], ["xbh", "2·3루타"], ["home_run", "홈런"], ["bb", "볼넷 · 몸에 맞는 공"], ["so", "삼진"], ["out", "아웃"],
];
const PITCHER_WIN = new Set<ForecastKey>(["so", "out"]); // 투수 쪽 결과는 회색 막대 (강조는 타자 쪽 결과만)
const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

/**
 * 맞대결 예상 (API-37) — 왼쪽 우세 · 예상 타율 · OPS · 지난 맞대결, 오른쪽 타석당 결과 6갈래 막대(리그 같은 좌우 평균은 세로 눈금).
 * 막대는 이 맞대결 하나만 구단 색, 리그는 회색 눈금 (dataviz: 한 계열 강조 + 회색 기준).
 * side = 지금 화면의 선수 쪽. 구단 색은 그 선수에게 좋은 쪽에만 (타자 화면: 안타 쪽 막대 · 높은 예상 타율, 투수 화면: 삼진 · 아웃 막대 · 낮은 예상 타율)
 */
function ForecastBody({ f, side }: { f: Forecast; side: Role }) {
  const max = Math.max(...ROWS.flatMap(([k]) => [f.probs[k], f.league.probs[k]]));
  const lower = f.expected.avg != null && f.league.avg != null && f.expected.avg < f.league.avg;
  const better = f.expected.avg != null && f.league.avg != null && (side === "batter" ? !lower && f.expected.avg !== f.league.avg : lower);
  const mine = (k: ForecastKey) => (side === "batter") !== PITCHER_WIN.has(k);
  const edge = f.edge === "batter" ? `${f.batter.name} 우세` : f.edge === "pitcher" ? `${f.pitcher.name} 우세` : "팽팽";
  const lg = f.platoon ? `리그 ${f.platoon} 평균` : "리그 평균";
  return (
    <div className="grid gap-6 md:grid-cols-[220px_minmax(0,1fr)]">
      <div>
        <span className={`inline-block rounded-md px-2 py-0.5 text-xs font-bold ${f.edge === side ? "bg-(--team) text-white" : "bg-surface-3 text-fg"}`}>{edge}</span>
        <p className="mt-3 text-xs font-bold text-fg-2">예상 타율</p>
        <p className={`font-display text-[44px] leading-none font-extrabold ${better ? "text-(--team-text)" : ""}`}>{rate3(f.expected.avg)}</p>
        <p className="mt-2 text-[13px] text-fg-2">OPS <b className="font-num text-fg">{rate3(f.expected.ops)}</b> · 리그 {rate3(f.league.ops)}</p>
        <p className="mt-1 text-[13px] text-fg-2">
          지난 맞대결 {f.h2h.pa ? <>{f.h2h.pa}타석 {f.h2h.h}안타 · 타율 <b className="font-num text-fg">{rate3(f.h2h.avg)}</b></> : "없음"}
        </p>
      </div>
      <div>
        <ul className="space-y-1.5" aria-label="타석당 결과 예상">
          {ROWS.map(([k, label]) => (
            <li key={k} className="grid grid-cols-[112px_minmax(0,1fr)_52px] items-center gap-3" title={`${label} · 이 맞대결 ${pct(f.probs[k])} · ${lg} ${pct(f.league.probs[k])}`}>
              <span className="text-[13px] font-medium">{label}</span>
              <span className="relative h-2.5 rounded-full bg-surface-3">
                <span className={`absolute inset-y-0 left-0 rounded-full ${mine(k) ? "bg-(--team)" : "bg-fg-2/45"}`} style={{ width: `${(f.probs[k] / max) * 100}%` }} />
                <span className="absolute -top-1 -bottom-1 w-0.5 rounded-full bg-fg" style={{ left: `calc(${(f.league.probs[k] / max) * 100}% - 1px)` }} aria-hidden />
              </span>
              <span className="text-right font-num text-[13px] font-bold">{pct(f.probs[k])}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-2">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-full bg-(--team)" aria-hidden /> 이 맞대결 예상(타석당)</span>
          <span className="flex items-center gap-1.5"><span className="h-3.5 w-0.5 rounded-full bg-fg" aria-hidden /> {lg}</span>
        </p>
      </div>
    </div>
  );
}

/** 「2026 시즌 기록 · 우타 vs 우투 · 직접 맞대결 21타석 반영」 */
function basisText(f: Forecast) {
  return [`${f.season} 시즌 기록`, f.platoon, f.basis.h2h_pa ? `직접 맞대결 ${f.basis.h2h_pa}타석 ${Math.round(f.basis.h2h_weight * 100)}% 반영` : "직접 맞대결 없음", "타자 · 투수 기록을 리그 평균과 비교해 계산"]
    .filter(Boolean).join(" · ");
}

function useForecast(batter: string, pitcher: string | null, season: number) {
  return useQuery({
    queryKey: qk.forecast(batter, pitcher ?? "", season),
    queryFn: ({ signal }) => getForecast(batter, pitcher!, season, signal),
    enabled: !!pitcher,
    retry: false,
  });
}

function Body({ q, side }: { q: ReturnType<typeof useForecast>; side: Role }) {
  if (q.isError) return <p className="py-6 text-[13px] text-fg-2">{q.error instanceof ApiError ? q.error.message : "예상을 불러오지 못했어요"}</p>;
  if (!q.data) return <div className="h-[184px] animate-pulse rounded-2xl bg-surface-2" />;
  return <ForecastBody f={q.data} side={side} />;
}

function Head({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 className="text-[17px] font-bold">{title}</h3>
        {sub && <p className="mt-1 text-xs text-fg-2">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

/** 펼친 줄 안 — 「다음 맞대결 예상」 */
export function NextTime({ batter, pitcher, season, side }: { batter: string; pitcher: string; season: number; side: Role }) {
  const q = useForecast(batter, pitcher, season);
  return (
    <div className="rounded-2xl bg-surface p-5">
      <Head title="다음 맞대결 예상" sub={q.data ? basisText(q.data) : undefined} />
      <Body q={q} side={side} />
    </div>
  );
}

type Pick = { id: string; name: string; team: string | null };

/** 표 위 「○○ 상대 예상」 — 상대 쪽(타자 화면이면 투수, 투수 화면이면 타자) 누구나 이름으로 골라 예상. 처음엔 가장 많이 상대한 선수 */
export function ForecastPicker({ player, side, season, initial }: { player: string; side: Role; season: number; initial: Pick | null }) {
  const [pick, setPick] = useState<Pick | null>(initial);
  const [text, setText] = useState("");
  const other: Role = side === "batter" ? "pitcher" : "batter";
  const who = other === "pitcher" ? "투수" : "타자";
  const q = useForecast(side === "batter" ? player : pick?.id ?? "", side === "batter" ? pick?.id ?? null : pick ? player : null, season);
  const t = text.trim();
  const hits = useQuery({
    queryKey: qk.searchRole(t, other),
    queryFn: ({ signal }) => searchPlayers(t, signal, other),
    enabled: t.length > 0,
  });

  const picker = (
    <div className="relative">
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder={`${who} 이름 · 초성`} aria-label={`예상할 ${who} 이름`}
             className="h-9 w-48 rounded-full border border-line bg-surface px-4 text-[13px]" />
      {t && (
        <ul className="absolute right-0 z-20 mt-1.5 max-h-72 w-64 overflow-y-auto rounded-2xl border border-line bg-surface py-1.5 shadow-lg">
          {(hits.data ?? []).slice(0, 8).map((h) => (
            <li key={h.player_id}>
              <button onClick={() => { setPick({ id: h.player_id, name: h.name, team: h.team }); setText(""); }}
                      className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm hover:bg-surface-2">
                <PlayerAvatar id={h.player_id} name={h.name} team={h.team} size={28} />
                <span className="font-bold">{h.name}</span>
                <span className="flex items-center gap-1 text-xs text-fg-2"><TeamLogo team={h.team} height={12} /> {h.team ?? "–"} · {h.bats_throws ?? "투타 정보 없음"}</span>
              </button>
            </li>
          ))}
          {hits.data?.length === 0 && <li className="px-3 py-2 text-[13px] text-fg-2">그 이름의 {who}가 없어요</li>}
        </ul>
      )}
    </div>
  );

  return (
    <section className="mb-8 rounded-3xl border border-line bg-surface p-6">
      <Head
        title={pick ? `${pick.name} 상대 예상` : `상대 ${who} 예상`}
        sub={q.data ? basisText(q.data) : `${season} 시즌 기록 기준 예상`}
        right={picker}
      />
      {pick ? <Body q={q} side={side} /> : <p className="py-6 text-[13px] text-fg-2">{who}를 고르면 예상이 나와요</p>}
    </section>
  );
}
