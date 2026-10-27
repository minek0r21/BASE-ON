"use client";

import { useState } from "react";
import type { Clip, PlayerSummary, StatKey } from "@/lib/api";
import AxisBar from "./AxisBar";
import { AXIS_HELP } from "@/lib/constants";
import { formatStat, md } from "@/lib/format";
import ScenePlayer, { thumbnailUrl } from "@/components/ScenePlayer";
import SceneButton from "@/components/SceneButton";

const STAT_ROW: { key: StatKey; label: string }[] = [
  { key: "pa", label: "타석" },
  { key: "avg", label: "타율" },
  { key: "obp", label: "출루율" },
  { key: "slg", label: "장타율" },
  { key: "ops", label: "OPS" },
  { key: "hr", label: "홈런" },
];

// BO-PB-01 타자 요약 (FR-02). 축 옆 ▶ = 그 시즌 최근 확정 장면: 파워 = 홈런, 안타생산 = 안타, 선구안 = 볼넷 (docs/장면.md 6장)
export default function Summary({ p }: { p: PlayerSummary }) {
  const [playing, setPlaying] = useState<{ clip: Clip; label: string } | null>(null);

  if (!p.isBatter) {
    return (
      <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">
        {p.season} 시즌 타자 기록이 없습니다.
      </p>
    );
  }

  const scene = p.recentScene;
  const sceneLabel = scene ? `${p.name} · ${md(scene.date)} ${scene.opponent}전 시즌 ${scene.hrSeq}호 홈런` : "";
  const play = () => scene && setPlaying({ clip: scene.clip, label: sceneLabel });

  return (
    <div className="space-y-5">
      {playing && (
        <div className="sticky top-16 z-10">
          <ScenePlayer clip={playing.clip} label={playing.label} onClose={() => setPlaying(null)} />
        </div>
      )}

      <div className="grid gap-5 md:grid-cols-[1fr_18rem]">
        <div className="space-y-5">
          {/* 시즌 기록 */}
          <section className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-6">
            {STAT_ROW.map((s) => (
              <div key={s.key} className="bg-surface px-3 py-3 text-center">
                <div className="text-xs text-muted">{s.label}</div>
                <div className="mt-0.5 text-lg font-bold tabular-nums">{formatStat(s.key, p.stats?.[s.key])}</div>
              </div>
            ))}
          </section>

          {/* 5지표 백분위 */}
          <section className="rounded-xl border border-line bg-surface p-5">
            <header className="mb-4 flex items-baseline justify-between gap-2">
              <h2 className="font-bold">리그 백분위</h2>
              <span className="text-xs text-muted">
                {p.qualified ? `${p.season} 비교 대상 ${p.groupSize}명` : p.notQualifiedMessage}
                {p.dataAsOf && ` · ${p.dataAsOf} 기준`}
              </span>
            </header>
            <ul className="space-y-4">
              {p.axes.map((a) => (
                <AxisBar
                  key={a.key}
                  label={a.label}
                  help={AXIS_HELP[a.key]}
                  valueText={formatStat(a.metric, a.value)}
                  percentile={a.percentile}
                  topPct={a.topPct}
                  rankText={a.rank != null && p.groupSize != null ? `${p.groupSize}명 중 ${a.rank}위` : null}
                  note={p.qualified && a.unavailable ? `계산 불가(${a.unavailable})` : null}
                  action={
                    a.key === "power" && scene ? (
                      <SceneButton clip={scene.clip} label={`${p.name} 홈런 장면`} onPlay={play} />
                    ) : a.scene ? (
                      <SceneButton clip={a.scene.clip} label={a.scene.label} onPlay={() => setPlaying(a.scene)} />
                    ) : null
                  }
                />
              ))}
            </ul>
          </section>
        </div>

        {/* 최근 홈런·장면 */}
        <aside className="space-y-3 rounded-xl border border-line bg-surface p-5 text-sm">
          <h2 className="font-bold">최근 홈런</h2>
          {p.lastHr ? (
            <p>
              <span className="font-semibold">시즌 {p.lastHr.hr_seq}호</span>
              <br />
              <span className="text-muted">
                {p.lastHr.date} · {p.lastHr.opponent}전 · 투수 {p.lastHr.pitcher.name}
                {p.lastHr.runs > 1 && ` · ${p.lastHr.runs}점`}
              </span>
            </p>
          ) : (
            <p className="text-muted">이 시즌 홈런이 없습니다.</p>
          )}
          {scene && (
            <button onClick={play} className="block w-full overflow-hidden rounded-lg border border-line text-left hover:bg-bg">
              {/* eslint-disable-next-line @next/next/no-img-element -- 정적 내보내기: 썸네일 핫링크(설계 8-2) */}
              <img src={thumbnailUrl(scene.clip.videoId)} alt="" className="aspect-video w-full object-cover" />
              <span className="block px-3 py-2">
                <span className="font-semibold">▶ {md(scene.date)} 시즌 {scene.hrSeq}호</span>
                <span className="text-muted"> · {scene.opponent}전</span>
                {scene.clip.precision === "inning" && <span className="ml-1 text-xs text-muted">(그 이닝부터)</span>}
              </span>
            </button>
          )}
        </aside>
      </div>
    </div>
  );
}
