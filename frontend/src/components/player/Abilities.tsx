"use client";

import Link from "next/link";
import { SectionHead } from "@/components/home/common";
import Help from "@/components/ui/Help";
import type { AxisKey, PitchAxisKey, PlayerSummary } from "@/lib/api";
import { barOpacity, josa, verdict } from "@/lib/abilities";
import { GROUP_RULE, axisCopy, rankingsHref } from "@/lib/axes";
import { AXIS_HELP, GROUP_HELP, PITCH_AXIS_HELP, STAT_HELP } from "@/lib/constants";
import { md } from "@/lib/format";
import { leaguePosition } from "@/lib/position";
import type { Role } from "./Hero";

type Cell = { key: AxisKey | PitchAxisKey; label: string; value: number | null; percentile: number | null; rank: number | null; note?: string | null };

/**
 * 03 · 03b 「리그 타자 103명 중 김도영은」 (Figma 139:1157) — 능력 5칸: 상위 · 하위 % 큰 글씨(상위 20%면 구단 글자색), 구단 색 막대(농도 3단계),
 * 판정 한 줄, 「n명 중 m위」 + 원 수치. 백분위가 가장 높은 칸에 「가장 강한 점」. 「?」는 눌러서 여는 말풍선.
 * 섹션 제목(기준 · 「다른 타자와 비교」) + 5칸 한 상자 — 06 팀 화면 표와 같은 틀
 */
export default function Abilities({ p, role, asOf }: { p: PlayerSummary; role: Role; asOf: string | null }) {
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
  const more = (
    <Link href={rankingsHref(role, best)} className="text-sm font-bold text-brand-text hover:underline">
      다른 {role === "pitcher" ? "투수" : "타자"}와 비교 ›
    </Link>
  );
  const cell = (c: Cell) => (
    <AbilityCell c={c} n={n} who={role === "pitcher" ? `${pi?.roleLabel ?? ""} ` : ""} name={p.name} best={c.key === best} />
  );

  if (!qualified) {
    const msg = role === "pitcher" ? pi?.notQualifiedMessage : p.notQualifiedMessage;
    return (
      <section className="rounded-3xl border border-line bg-surface px-6 py-5">
        <h2 className="text-[17px] font-bold">{who}와 비교</h2>
        <p className="mt-2 text-sm text-fg-2">{msg ?? "리그 비교 대상이 아니에요"} · {criteria}</p>
      </section>
    );
  }

  return (
    <section>
      <SectionHead title={title} sub={sub} right={more} />
      <ul className="grid grid-cols-2 gap-y-5 rounded-3xl border border-line bg-surface px-6 py-5 md:grid-cols-5 md:divide-x md:divide-line">
        {cells.map((c) => <li key={c.key} className="min-w-0 md:px-5 md:first:pl-0 md:last:pr-0">{cell(c)}</li>)}
      </ul>
    </section>
  );
}

function AbilityCell({ c, n, who, name, best }: { c: Cell; n: number; who: string; name: string; best: boolean }) {
  const copy = axisCopy(c.key);
  const value = copy?.fmt(c.value) ?? "–";
  const pos = c.percentile != null && c.rank != null ? leaguePosition(c.percentile, c.rank, n) : null;
  const strong = c.percentile != null && barOpacity(c.percentile) === 1; // 상위 20% 안이면 큰 숫자 · 판정도 구단 색
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[15px] font-bold">
          {c.label}
          <Help title={`${c.label} · ${copy?.title ?? ""}`} body={`${helpOf(c.key)} ${josa(name, "은", "는")} ${value}예요.`} />
        </span>
        {best && <span className="rounded bg-accent px-1.5 py-0.5 text-[11px] font-bold text-white">가장 강한 점</span>}
      </div>
      {pos ? (
        <>
          <p className="mt-2 flex items-baseline gap-1.5">
            <span className="text-[15px] font-medium text-fg-2">{pos.side}</span>
            <span className={`font-display text-[46px] leading-none font-extrabold ${strong ? "text-(--team-text)" : ""}`}>{pos.pct}%</span>
          </p>
          <span className="mt-2.5 block h-1.5 overflow-hidden rounded-full bg-surface-3">
            <span className="block h-full rounded-full bg-(--team)" style={{ width: `${c.percentile}%`, opacity: barOpacity(c.percentile!) }} />
          </span>
          <p className={`mt-2.5 text-[15px] font-bold ${strong ? "text-(--team-text)" : ""}`}>{verdict(c.key, c.percentile!)}</p>
          <p className="mt-1 text-[13px] leading-5 text-fg-2">
            {who}{n}명 중 {c.rank}위<br />
            {copy?.metric} {value}
          </p>
        </>
      ) : (
        <p className="mt-3 text-[13px] text-fg-2">계산하지 않아요{c.note ? ` (${c.note})` : ""}</p>
      )}
    </div>
  );
}

const helpOf = (k: AxisKey | PitchAxisKey) =>
  k === "consistency" ? `${AXIS_HELP.consistency} OPS = ${STAT_HELP.ops.split(". ")[0]}.`
    : (AXIS_HELP as Record<string, string>)[k] ?? (PITCH_AXIS_HELP as Record<string, string>)[k];
