"use client";

import { useState } from "react";
import type { Clip, PitchingSummary, PitchScene } from "@/lib/api";
import { PITCH_AXIS_HELP } from "@/lib/constants";
import { formatPitchMetric, innings, md, outingLine, rate3 } from "@/lib/format";
import ScenePlayer, { thumbnailUrl } from "@/components/ScenePlayer";
import SceneButton from "@/components/SceneButton";
import AxisBar from "./AxisBar";

// 축 ▶에 붙는 쉬운 말 (docs/장면.md 5장: 축 이름을 풀어 쓴다)
const AXIS_SCENE_LABEL: Partial<Record<string, string>> = {
  strikeout: "삼진을 잡는 장면",
  hit_prevention: "안타를 막아 내는 장면",
  control: "볼넷 없이 막는 장면",
};

// BO-PP-01 투수 요약 (docs/투수.md 8장). 5지표는 A안, 비교 대상은 선발·불펜 따로
export default function PitcherSummary({ p, season, name }: { p: PitchingSummary; season: number | null; name: string }) {
  const [playing, setPlaying] = useState<{ clip: Clip; label: string } | null>(null);
  const sceneLabel = (s: PitchScene) => `${name} · ${md(s.date)} · ${outingLine(s.line)}`;

  const cells = [
    { label: "등판 (선발)", value: `${p.g} (${p.gs})` },
    { label: "이닝", value: innings(p.outs) },
    { label: "탈삼진", value: String(p.so) },
    { label: "볼넷", value: String(p.bb) },
    { label: "피안타율", value: rate3(p.avg) },
    { label: "WHIP", value: p.whip == null ? "–" : p.whip.toFixed(2) },
  ];

  return (
    <div className="space-y-5">
      {playing && (
        <div className="sticky top-16 z-10">
          <ScenePlayer clip={playing.clip} label={playing.label} onClose={() => setPlaying(null)} />
        </div>
      )}

      {/* 직구 구속은 막대가 아니라 숫자로 (P8) */}
      {p.avgVelo != null && (
        <p className="text-sm">
          <span className="font-semibold">직구 평균 {p.avgVelo.toFixed(1)}km/h</span>
          {p.leagueAvgVelo != null && <span className="text-muted"> (비교 대상 평균 {p.leagueAvgVelo.toFixed(1)}km/h)</span>}
        </p>
      )}

      <section className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-6">
        {cells.map((c) => (
          <div key={c.label} className="bg-surface px-3 py-3 text-center">
            <div className="text-xs text-muted">{c.label}</div>
            <div className="mt-0.5 text-lg font-bold tabular-nums">{c.value}</div>
          </div>
        ))}
      </section>

      <div className="grid gap-5 md:grid-cols-[1fr_18rem]">
        <section className="rounded-xl border border-line bg-surface p-5">
          <header className="mb-4 flex items-baseline justify-between gap-2">
            <h2 className="font-bold">리그 백분위</h2>
            <span className="text-xs text-muted">
              {p.qualified ? `${season} ${p.roleLabel} 비교 대상 ${p.groupSize}명` : p.notQualifiedMessage}
            </span>
          </header>
          <ul className="space-y-4">
            {p.axes.map((a) => (
              <AxisBar
                key={a.key}
                label={a.label}
                help={PITCH_AXIS_HELP[a.key]}
                valueText={formatPitchMetric(a.metric, a.value)}
                percentile={a.percentile}
                topPct={a.topPct}
                rankText={a.rank != null && p.groupSize != null ? `${p.roleLabel} ${p.groupSize}명 중 ${a.rank}위` : null}
                action={
                  a.scene && (
                    <SceneButton
                      clip={a.scene.clip}
                      label={`${name} ${AXIS_SCENE_LABEL[a.key] ?? a.label}`}
                      onPlay={() => setPlaying({ clip: a.scene!.clip, label: `${sceneLabel(a.scene!)} · ${AXIS_SCENE_LABEL[a.key] ?? ""}` })}
                    />
                  )
                }
              />
            ))}
          </ul>
        </section>

        {/* 최근 장면 — 제목 대신 우리 기록으로 표기 */}
        <aside className="space-y-3 rounded-xl border border-line bg-surface p-5 text-sm">
          <h2 className="font-bold">최근 장면</h2>
          {p.recentScene ? (
            <button
              onClick={() => setPlaying({ clip: p.recentScene!.clip, label: sceneLabel(p.recentScene!) })}
              className="block w-full overflow-hidden rounded-lg border border-line text-left hover:bg-bg"
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- 정적 내보내기: 썸네일 핫링크(설계 8-2) */}
              <img src={thumbnailUrl(p.recentScene.clip.videoId)} alt="" className="aspect-video w-full object-cover" />
              <span className="block px-3 py-2">
                <span className="font-semibold">{md(p.recentScene.date)}</span>
                <span className="text-muted"> · {outingLine(p.recentScene.line)}</span>
                {p.recentScene.clip.precision === "inning" && <span className="ml-1 text-xs text-muted">(그 이닝부터)</span>}
              </span>
            </button>
          ) : (
            <p className="text-muted">이 시즌 연결된 장면이 아직 없어요. 경기 기록 탭에서 경기 하이라이트를 볼 수 있어요.</p>
          )}
        </aside>
      </div>

      <p className="text-xs text-muted">
        평균자책점·승패는 원천 기록에 자책점·결정 투수 구분이 없어 제공하지 않습니다.
      </p>
    </div>
  );
}
