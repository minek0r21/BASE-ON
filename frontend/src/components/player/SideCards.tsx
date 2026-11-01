"use client";

import { useQuery } from "@tanstack/react-query";
import { getForm, qk, type Form, type PlayerSeasons, type PlayerSummary } from "@/lib/api";
import { innings, md, rate3 } from "@/lib/format";
import Help from "@/components/ui/Help";
import type { Role } from "./Hero";

const card = "rounded-3xl border border-line bg-surface p-6";

type Stat = { label: string; value: string; rank: { text: string; n?: number } | null; help?: string };

/** 시즌 기록 5칸 — 원 수치 + 「리그 n위」 */
function seasonStats(p: PlayerSummary, role: Role, seasons: PlayerSeasons | undefined, asOf: string | null): { title: string; sub: string; items: Stat[] } | null {
  const at = asOf ? `${md(asOf)} 기준` : null;
  if (role === "pitcher") {
    const pi = p.pitching;
    if (!pi) return null;
    const r = pi.statRanks;
    const rk = (k: keyof NonNullable<typeof r>) => (r?.[k] ? { text: `${pi.roleLabel} ${r[k]}위`, n: r[k]! } : null);
    const bb = pi.bb + pi.hbp;
    return {
      title: `${p.season} 시즌 기록`,
      sub: [`${pi.g}경기${pi.gs === pi.g ? " 선발" : ""}`, at, r && pi.groupSize && `순위는 ${pi.roleLabel} ${pi.groupSize}명 중`].filter(Boolean).join(" · "),
      items: [
        { label: "이닝", value: innings(pi.outs), rank: rk("outs"), help: "이닝은 「회」예요. 아웃 3개가 1이닝이라, ⅓은 아웃 1개 · ⅔는 아웃 2개를 더 잡았다는 뜻이에요." },
        { label: "탈삼진", value: String(pi.so), rank: rk("so") },
        { label: "WHIP", value: pi.whip?.toFixed(2) ?? "–", rank: rk("whip") },
        { label: "피안타율", value: rate3(pi.avg), rank: rk("avg") },
        { label: "볼넷 · 몸에 맞는 공", value: String(bb), rank: pi.outs ? { text: `9이닝당 ${((bb * 27) / pi.outs).toFixed(1)}` } : null },
      ],
    };
  }
  const st = p.stats;
  if (!st) return null;
  const r = p.statRanks;
  const rk = (k: keyof NonNullable<typeof r>) => (r?.[k] ? { text: `리그 ${r[k]}위`, n: r[k]! } : null);
  const games = seasons?.batting.find((s) => s.season === p.season)?.games;
  return {
    title: `${p.season} 시즌 기록`,
    sub: [games != null && `${games}경기 ${st.pa}타석`, at, r && p.groupSize && `순위는 타자 ${p.groupSize}명 중`].filter(Boolean).join(" · "),
    items: [
      { label: "홈런", value: String(st.hr), rank: rk("hr") },
      { label: "장타율", value: rate3(st.slg), rank: rk("slg") },
      { label: "OPS", value: rate3(st.ops), rank: rk("ops") },
      { label: "출루율", value: rate3(st.obp), rank: rk("obp") },
      { label: "타율", value: rate3(st.avg), rank: rk("avg") },
    ],
  };
}

/** 3위 안이면 큰 숫자를 구단 글자색 (데이터에만 구단 색, 10-31 사용자) */
const valueTone = (s: Stat) => (s.rank?.n != null && s.rank.n <= 3 ? "text-(--team-text)" : "");

/** 시즌 기록 가로 띠 (Figma 138:676 · 139:1281) — 06 팀 「2026 순위」 띠처럼 5칸 한 줄 */
export function SeasonStrip({ p, role, seasons, asOf }: { p: PlayerSummary; role: Role; seasons?: PlayerSeasons; asOf: string | null }) {
  const d = seasonStats(p, role, seasons, asOf);
  if (!d) return null;
  return (
    <section>
      <p className="mb-2.5 flex flex-wrap items-baseline gap-2 text-sm font-bold">
        {d.title} <span className="text-xs font-medium text-muted">{d.sub}</span>
      </p>
      <ul className="grid grid-cols-2 gap-1.5 sm:grid-cols-5">
        {d.items.map((s) => (
          <li key={s.label} className="rounded-2xl border border-line bg-surface px-4 py-3.5">
            <span className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1 text-[13px] font-bold"><span className="truncate">{s.label}</span>{s.help && <Help title={s.label} body={s.help} inline />}</span>
              {s.rank && <span className="shrink-0 text-[11px] font-bold text-fg-2">{s.rank.text}</span>}
            </span>
            <span className={`mt-2 block font-display text-[30px] leading-none font-extrabold ${valueTone(s)}`}>{s.value}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function CardHead({ title, sub }: { title: string; sub?: string }) {
  return (
    <div>
      <h3 className="text-xl font-bold">{title}</h3>
      {sub && <p className="mt-1 text-xs text-fg-2">{sub}</p>}
    </div>
  );
}

/** 요즘 타격감(최근 20경기 OPS) · 투구감(최근 10등판 WHIP) — 큰 숫자 + 판정 + 흐름 선 (Figma 138:720 · 139:1325) */
export function FormCard({ id, season, role }: { id: string; season: number; role: Role }) {
  const q = useQuery({ queryKey: qk.form(id, season, role), queryFn: ({ signal }) => getForm(id, season, role, signal) });
  const f = q.data;
  if (q.isError || (f && f.points.length < 2)) return null;
  const bat = role === "batter";
  const fmt = (v: number | null) => (v == null ? "–" : bat ? rate3(v) : v.toFixed(2));
  return (
    <section className={`${card} flex flex-col`}>
      {!f ? (
        <div className="h-[210px] animate-pulse rounded-2xl bg-surface-2" />
      ) : (
        <div className="flex flex-1 animate-appear flex-col">
          <CardHead
            title={bat ? "요즘 타격감" : "요즘 투구감"}
            sub={[`최근 ${f.window}${bat ? "경기 OPS" : "경기 WHIP"} 흐름`, f.range ? `${md(f.range[0])} ~ ${md(f.range[1])}` : `${md(f.points[0].date)} ~ ${md(f.points.at(-1)!.date)}`, !bat && "낮을수록 좋아요"]
              .filter(Boolean).join(" · ")}
          />
          <p className="mt-3 flex items-end gap-3">
            <span className={`font-display text-[48px] leading-none font-extrabold ${f.verdict === "up" ? "text-(--team-text)" : ""}`}>{fmt(f.recent)}</span>
            {f.verdict && (
              <span className="mb-1 rounded-full bg-surface-2 px-2.5 py-1 text-xs font-bold">
                {{ up: "시즌보다 좋아요", flat: "시즌과 비슷해요", down: bat ? "시즌보다 주춤해요" : "시즌보다 주자를 많이 내보내요" }[f.verdict]}
              </span>
            )}
          </p>
          <div className="mt-auto">
            <Spark f={f} />
            <p className="mt-2 flex justify-between text-[11px] text-fg-2">
              <span className="font-num">{md(f.points[0].date)}</span>
              <span>- - 시즌 {bat ? "OPS" : "WHIP"} {fmt(f.season)}{f.league != null && ` · 리그 평균 ${fmt(f.league)}`}</span>
              <span className="font-num">{md(f.points.at(-1)!.date)}</span>
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

function Spark({ f }: { f: Form }) {
  const W = 358, H = 96, pad = 6;
  const vals = f.points.map((p) => p.value).concat(f.season ?? []);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const x = (i: number) => (i / (f.points.length - 1)) * W;
  const y = (v: number) => pad + (1 - (v - lo) / (hi - lo || 1)) * (H - pad * 2);
  const line = f.points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");
  const last = f.points.at(-1)!;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-4 h-20 w-full overflow-visible" preserveAspectRatio="none" role="img"
         aria-label={`${f.points.length}경기 흐름, 마지막 ${last.value}`}>
      <path d={`${line} L${W} ${H} L0 ${H} Z`} className="fill-(--team-soft)" />
      {f.season != null && <line x1={0} x2={W} y1={y(f.season)} y2={y(f.season)} className="stroke-fg-2" strokeDasharray="4 4" strokeWidth={1} vectorEffect="non-scaling-stroke" />}
      <path d={line} fill="none" className="stroke-(--team)" strokeWidth={2.5} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      <circle cx={x(f.points.length - 1)} cy={y(last.value)} r={4.5} className="fill-(--team) stroke-surface" strokeWidth={2} />
    </svg>
  );
}

/** 시즌별 기록 — 최근 3시즌 (Figma 138:739 · 139:1344). 지금 보는 시즌 줄은 굵게. 전체는 「시즌 기록」 탭 */
export function SeasonsCard({ role, seasons, current }: { role: Role; seasons?: PlayerSeasons; current: number | null }) {
  if (!seasons) return null;
  const rows = role === "pitcher"
    ? seasons.pitching.slice(0, 3).map((s) => [s.season, s.g, innings(s.outs as number), s.so, (s.whip as number | null)?.toFixed(2) ?? "–"])
    : seasons.batting.slice(0, 3).map((s) => [s.season, s.games, rate3(s.avg), s.hr, rate3(s.ops)]);
  if (!rows.length) return null;
  const head = role === "pitcher" ? ["시즌", "경기", "이닝", "탈삼진", "WHIP"] : ["시즌", "경기", "타율", "홈런", "OPS"];
  return (
    <section className={card}>
      <CardHead title="시즌별 기록" />
      <table className="mt-3 w-full text-left">
        <thead>
          <tr className="text-xs text-fg-2">{head.map((h) => <th key={h} className="pb-1 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-line font-num text-[15px]">
          {rows.map((r) => (
            <tr key={String(r[0])} className={`h-11 ${r[0] === current ? "font-bold" : "text-fg-2"}`}>
              {r.map((v, i) => <td key={i} className={i === 0 ? "font-bold text-fg" : ""}>{String(v ?? "–")}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
