"use client";

import Link from "next/link";
import { useRef } from "react";
import { SectionHead } from "@/components/home/common";
import Help from "@/components/ui/Help";
import type { AxisKey, PitchAxisKey, PlayerSummary } from "@/lib/api";
import { barOpacity, isTop20, josa, verdict } from "@/lib/abilities";
import { GROUP_RULE, axisCopy, rankingsHref } from "@/lib/axes";
import { AXIS_HELP, GROUP_HELP, PITCH_AXIS_HELP, STAT_HELP } from "@/lib/constants";
import { innings, md } from "@/lib/format";
import { useProgress, useSeen } from "@/lib/motion";
import { leaguePosition } from "@/lib/position";
import type { Role } from "./Hero";

type Cell = { key: AxisKey | PitchAxisKey; label: string; value: number | null; percentile: number | null; rank: number | null; note?: string | null };

/**
 * 03 · 03b 「리그 타자 103명 중 김도영은」 (Figma 139:1157) — 능력 5칸: 상위 · 하위 % 큰 글씨(상위 20%면 구단 글자색), 구단 색 막대(농도 3단계),
 * 판정 한 줄, 「n명 중 m위」 + 원 수치. 백분위가 가장 높은 칸에 「가장 강한 점」. 「?」는 눌러서 여는 말풍선.
 * 섹션 제목(기준 · 「다른 타자와 비교」) + 5칸 한 상자 — 06 팀 화면 표와 같은 틀
 */
/** onCompare가 있으면(휴대폰 개요) 「다른 ~와 비교 ›」가 비교 화면을 연다 — 머리의 「비교하기」 줄을 없앤 자리 (M03 · 11-08) */
export default function Abilities({ p, role, asOf, onCompare }: { p: PlayerSummary; role: Role; asOf: string | null; onCompare?: () => void }) {
  const box = useRef<HTMLUListElement>(null);
  const seen = useSeen(box); // 처음 보일 때 막대를 0에서 채운다 (600ms, 칸마다 60ms 간격)
  const pi = p.pitching;
  const qualified = role === "pitcher" ? !!pi?.qualified : p.qualified;
  const n = (role === "pitcher" ? pi?.groupSize : p.groupSize) ?? 0;
  const who = role === "pitcher" ? `리그 ${pi?.roleLabel ?? ""} 투수` : "리그 타자";
  const cells: Cell[] = role === "pitcher"
    ? (pi?.axes ?? []).map((a) => ({ key: a.key, label: a.label, value: a.value, percentile: a.percentile, rank: a.rank }))
    : p.axes.map((a) => ({ key: a.key, label: a.label, value: a.value, percentile: a.percentile, rank: a.rank, note: a.unavailable }));
  const best = cells.filter((c) => c.percentile != null).sort((a, b) => b.percentile! - a.percentile!)[0]?.key;
  const criteria = [p.season && `${p.season} 정규시즌`, asOf && `${md(asOf)} 기준`,
    role === "pitcher" ? `규정이닝 ${pi?.role === "reliever" ? "20%" : "50%"} 이상 ${pi?.roleLabel ?? "선발"}과 비교` : `${GROUP_RULE.batter}와 비교`].filter(Boolean).join(" · ");
  const sub = <>{criteria} <Help title={role === "pitcher" ? "규정이닝" : "규정타석"} body={GROUP_HELP[role]} inline /></>;
  const title = `${who} ${n}명 중 ${josa(p.name, "은", "는")}`;
  const moreText = <>다른 {role === "pitcher" ? "투수" : "타자"}와 비교 ›</>;
  const more = onCompare ? (
    <button type="button" onClick={onCompare} className="text-sm font-bold text-brand-text hover:underline max-md:-my-3 max-md:py-3">{moreText}</button>
  ) : (
    <Link href={rankingsHref(role, best)} className="text-sm font-bold text-brand-text hover:underline max-md:-my-3 max-md:py-3">{moreText}</Link>
  );
  const cell = (c: Cell, i: number) => (
    <AbilityCell c={c} n={n} who={role === "pitcher" ? `${pi?.roleLabel ?? ""} ` : ""} name={p.name} best={c.key === best} run={seen} delay={i * 60} />
  );

  // 비교 대상 밖: 이유(몇 타석 · 이닝 모자란지)를 말하고 막대 대신 실제 수치만 (09 「리그 비교 대상이 아닐 때」)
  if (!qualified) {
    const shown = cells.filter((c) => c.value != null);
    return (
      <section className="rounded-3xl border border-line bg-surface px-6 py-5">
        <h2 className="text-[17px] font-bold">{who}와 비교</h2>
        <div className="mt-3 flex gap-3 rounded-2xl border border-line bg-bg px-4 py-3.5">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-3 text-[11px] font-bold text-fg-2" aria-hidden>i</span>
          <div className="text-sm">
            <p className="font-bold">리그 비교 대상이 아니에요</p>
            <p className="mt-1 text-fg-2">{shortOf(p, role)}</p>
          </div>
        </div>
        {shown.length > 0 && (
          <dl className="mt-5 flex flex-wrap gap-x-12 gap-y-4">
            {shown.map((c) => {
              const copy = axisCopy(c.key);
              return (
                <div key={c.key}>
                  <dt className="text-xs text-fg-2">{copy?.metric ?? c.label}</dt>
                  <dd className="mt-1 font-display text-[28px] leading-none font-extrabold">{copy?.fmt(c.value) ?? "–"}</dd>
                </div>
              );
            })}
          </dl>
        )}
        <p className="mt-4 text-xs text-muted">{sub}</p>
      </section>
    );
  }

  return (
    <section>
      <SectionHead title={title} sub={sub} right={more} />
      <ul ref={box} className="grid divide-y divide-line rounded-2xl border border-line bg-surface px-4 py-1 md:grid-cols-5 md:gap-y-5 md:divide-x md:divide-y-0 md:rounded-3xl md:px-6 md:py-5">
        {cells.map((c, i) => <li key={c.key} className="min-w-0 py-3 md:px-5 md:py-0 md:first:pl-0 md:last:pr-0">{cell(c, i)}</li>)}
      </ul>
    </section>
  );
}

function AbilityCell({ c, n, who, name, best, run, delay }: { c: Cell; n: number; who: string; name: string; best: boolean; run: boolean; delay: number }) {
  const t = useProgress(run, 600, delay);
  const copy = axisCopy(c.key);
  const value = copy?.fmt(c.value) ?? "–";
  const pos = c.percentile != null && c.rank != null ? leaguePosition(c.percentile, c.rank, n) : null;
  const strong = c.percentile != null && isTop20(c.percentile); // 상위 20% 안이면 큰 숫자 · 판정도 구단 색
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 md:block">
      <div className="flex items-center gap-2 md:justify-between">
        <span className="flex items-center gap-1.5 text-[15px] font-bold">
          {c.label}
          <Help title={`${c.label} · ${copy?.title ?? ""}`} body={`${helpOf(c.key)} ${josa(name, "은", "는")} ${value}예요.`} />
        </span>
        {best && <span className="rounded bg-brand px-1.5 py-0.5 text-xs font-bold text-white md:bg-accent md:text-[11px]">가장 강한 점</span>}
      </div>
      {pos ? (
        <>
          <p className="col-start-2 row-span-2 row-start-1 flex items-baseline gap-1 md:mt-2 md:gap-1.5">
            <span className="text-[13px] font-medium text-fg-2 md:text-[15px]">{pos.side}</span>
            <span className={`font-display text-[34px] leading-none md:text-[46px] font-extrabold tabular-nums ${strong ? "text-(--team-text)" : ""}`}>{Math.round(pos.pct * t)}%</span>
          </p>
          <span className="col-span-2 mt-1.5 block h-1.5 overflow-hidden rounded-full bg-surface-3 md:mt-2.5">
            <span className="block h-full rounded-full bg-(--team)" style={{ width: `${c.percentile! * t}%`, opacity: barOpacity(c.percentile!) }} />
          </span>
          <p className={`col-start-1 row-start-2 text-[13px] font-bold md:mt-2.5 md:text-[15px] ${strong ? "text-(--team-text)" : ""}`}>{verdict(c.key, c.percentile!)}</p>
          <p className="col-span-2 mt-1 text-xs leading-5 text-fg-2 md:text-[13px]">
            {who}{n}명 중 {c.rank}위<span className="md:hidden"> · </span><br className="hidden md:block" />
            {copy?.metric} {value}
          </p>
        </>
      ) : (
        <p className="mt-3 text-[13px] text-fg-2">계산하지 않아요{c.note ? ` (${c.note})` : ""}</p>
      )}
    </div>
  );
}

/** 「규정타석의 50%(149타석)에 19타석 모자라요. 지금 130타석이라 순위 대신 실제 수치만 보여 드려요.」 — 기준을 모르면 앞 문장 없이 */
function shortOf(p: PlayerSummary, role: Role) {
  const tail = "순위 대신 실제 수치만 보여 드려요.";
  if (role === "pitcher") {
    const pi = p.pitching;
    if (!pi?.qualifyOuts) return `이닝이 모자라 ${tail}`;
    const share = pi.role === "reliever" ? "20%" : "50%";
    return `규정이닝의 ${share}(${innings(pi.qualifyOuts)}이닝)에 ${innings(Math.max(pi.qualifyOuts - pi.outs, 0))}이닝 모자라요. 지금 ${innings(pi.outs)}이닝이라 ${tail}`;
  }
  const pa = p.stats?.pa ?? 0;
  if (!p.qualifyPa) return `타석이 모자라 ${tail}`;
  return `규정타석의 50%(${p.qualifyPa}타석)에 ${Math.max(p.qualifyPa - pa, 0)}타석 모자라요. 지금 ${pa}타석이라 ${tail}`;
}

const helpOf = (k: AxisKey | PitchAxisKey) =>
  k === "consistency" ? `${AXIS_HELP.consistency} OPS = ${STAT_HELP.ops.split(". ")[0]}.`
    : (AXIS_HELP as Record<string, string>)[k] ?? (PITCH_AXIS_HELP as Record<string, string>)[k];
