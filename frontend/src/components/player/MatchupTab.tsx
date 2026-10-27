"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getMatchup, getMatchups, getPaClip, qk, type Clip, type VsPitcher } from "@/lib/api";
import { md, rate3 } from "@/lib/format";
import ScenePlayer from "@/components/ScenePlayer";
import StageTag from "@/components/StageTag";

// BO-PB-05 맞대결 (API-17 상대한 투수 → API-06 타석 목록). 10타석 미만은 성적보다 타석별 결과로 보여 준다 (시안 v9)
const MIN_PA = 10;

export default function MatchupTab({ playerId, playerName, season }: { playerId: string; playerName: string; season: number | null }) {
  const [scope, setScope] = useState<"all" | "season">("all");
  const [picked, setPicked] = useState<VsPitcher | null>(null);
  const [filter, setFilter] = useState("");
  const [playing, setPlaying] = useState<{ clip: Clip; label: string } | null>(null);
  const s = scope === "season" ? season : null;

  const list = useQuery({ queryKey: qk.matchups(playerId, s, 1), queryFn: ({ signal }) => getMatchups(playerId, s, 1, signal) });
  const detail = useQuery({
    queryKey: qk.matchup(playerId, picked?.player_id ?? "", s),
    queryFn: ({ signal }) => getMatchup(playerId, picked!.player_id, s, signal),
    enabled: picked != null,
  });

  if (list.isPending) return <p className="text-muted">불러오는 중…</p>;
  if (list.isError) return <p className="text-muted">맞대결 기록을 불러오지 못했습니다.</p>;

  const all = list.data.pitchers;
  const many = all.filter((p) => p.pa >= MIN_PA);
  const few = all.filter((p) => p.pa < MIN_PA);
  const f = filter.trim();
  const shown = f ? all.filter((p) => p.name.includes(f)) : many;

  const play = async (paId: string, label: string) => {
    const clip = await getPaClip(paId);
    if (clip) setPlaying({ clip, label });
  };

  return (
    <div className="space-y-5">
      {playing && (
        <div className="sticky top-16 z-10">
          <ScenePlayer clip={playing.clip} label={playing.label} onClose={() => setPlaying(null)} />
        </div>
      )}
      <section className="rounded-xl border border-line bg-surface p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="flex gap-1" role="group" aria-label="기간">
            {([["all", "2024~2026 누적"], ["season", `${season ?? ""} 시즌`]] as const).map(([k, l]) => (
              <button key={k} onClick={() => { setScope(k); setPicked(null); }} aria-pressed={scope === k}
                className={`rounded-full border px-3 py-1 text-sm ${scope === k ? "border-fg bg-fg text-bg" : "border-line text-muted hover:text-fg"}`}>
                {l}
              </button>
            ))}
          </div>
          <span className="text-sm text-muted">{MIN_PA}타석 이상 상대한 투수 {many.length}명 · 그 밖 {few.length}명</span>
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="상대 투수 이름"
            className="ml-auto w-44 rounded-lg border border-line bg-bg px-3 py-1.5 text-sm" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm tabular-nums">
            <thead className="text-xs text-muted">
              <tr className="border-b border-line">
                {["투수", "팀", "타석", "타수", "안타", "홈런", "볼넷", "삼진", "타율"].map((h, i) => (
                  <th key={h} className={`py-2 font-semibold ${i < 2 ? "pr-3 text-left" : "pl-2 text-right"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((p) => (
                <tr key={p.player_id} onClick={() => setPicked(p)} aria-selected={picked?.player_id === p.player_id}
                  className={`cursor-pointer border-b border-line last:border-0 hover:bg-bg ${picked?.player_id === p.player_id ? "bg-bg" : ""}`}>
                  <td className="py-2 pr-3 font-bold">{p.name}</td>
                  <td className="py-2 pr-3">{p.team ?? "–"}</td>
                  <td className="py-2 pl-2 text-right font-bold">{p.pa}</td>
                  {[p.ab, p.h, p.hr, p.bb, p.so].map((v, i) => <td key={i} className="py-2 pl-2 text-right">{v}</td>)}
                  <td className="py-2 pl-2 text-right">{p.pa < MIN_PA ? "–" : rate3(p.avg)}</td>
                </tr>
              ))}
              {shown.length === 0 && (
                <tr><td colSpan={9} className="py-6 text-center text-muted">{f ? "그 이름의 상대 투수가 없어요." : `${MIN_PA}타석 이상 상대한 투수가 없어요.`}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {picked && (
        <section className="rounded-xl border border-line bg-surface p-5">
          <h2 className="font-bold">{picked.name} ({picked.team ?? "–"}) 상대 — {picked.pa}타석</h2>
          {picked.pa < MIN_PA && (
            <p className="mt-1 text-sm text-muted">표본이 적어 성적으로 판단하기 어려워요. {MIN_PA}타석 전까지는 타석별 결과만 보세요.</p>
          )}
          {detail.isPending ? (
            <p className="mt-3 text-sm text-muted">불러오는 중…</p>
          ) : detail.isError ? (
            <p className="mt-3 text-sm text-muted">타석을 불러오지 못했습니다.</p>
          ) : (
            <ol className="mt-3 space-y-1 text-sm">
              {detail.data.plate_appearances.map((pa) => {
                const label = `${playerName} vs ${picked.name} · ${pa.date.slice(0, 4)}.${md(pa.date)} ${pa.inning}회${pa.inning_half} ${pa.events_ko}`;
                return (
                  <li key={pa.pa_id} className="flex items-center gap-3">
                    <span className="w-24 shrink-0 tabular-nums text-muted">{pa.date.slice(0, 4)}.{md(pa.date)}</span>
                    <span className="w-14 shrink-0 tabular-nums text-muted">{pa.inning}회{pa.inning_half}</span>
                    <StageTag label={pa.stage_label} />
                    <span className={`flex-1 ${pa.events === "home_run" ? "font-bold" : ""}`}>{pa.events_ko}</span>
                    {pa.has_video && (
                      <button onClick={() => play(pa.pa_id, label)} aria-label={`${label} 장면 재생`}
                        className="shrink-0 rounded-full bg-accent px-2.5 py-0.5 text-xs font-bold text-black">▶</button>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </section>
      )}
    </div>
  );
}
