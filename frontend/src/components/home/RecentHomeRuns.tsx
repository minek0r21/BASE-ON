"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getPaClip, getRecentHomeRuns, qk, type Clip } from "@/lib/api";
import { thumbnailUrl } from "@/components/ScenePlayer";
import { md } from "@/lib/format";
import StageTag from "@/components/StageTag";

const LIMIT = 9;

// 메인 「최근 홈런 장면」 (API-15): 확정 장면이 있는 홈런 최신순. 포스트시즌 기간이면 포스트시즌 홈런도 꼬리표와 함께 (PS7)
export default function RecentHomeRuns({ onPlay }: { onPlay: (clip: Clip, label: string) => void }) {
  const q = useQuery({ queryKey: qk.recentHrs(LIMIT), queryFn: ({ signal }) => getRecentHomeRuns(LIMIT, signal) });
  if (q.isPending) return <p className="text-muted">불러오는 중…</p>;
  if (q.isError || q.data.home_runs.length === 0) return null;

  const play = async (paId: string, label: string) => {
    const clip = await getPaClip(paId);
    if (clip) onPlay(clip, label);
  };

  return (
    <section aria-labelledby="hr-title" className="space-y-3">
      <h2 id="hr-title" className="text-lg font-extrabold">최근 홈런 장면</h2>
      <ul className="grid gap-3 sm:grid-cols-3">
        {q.data.home_runs.map((h) => {
          const label = `${h.batter.name} · ${md(h.date)} vs ${h.opponent} ${h.inning}회${h.inning_half}${h.hr_label ? ` ${h.hr_label}` : ""}`;
          return (
            <li key={h.pa_id} className="rounded-xl border border-line bg-surface p-2">
              <button onClick={() => play(h.pa_id, label)} disabled={!h.video} className="group block w-full text-left" aria-label={`${label} 재생`}>
                <div className="relative aspect-video overflow-hidden rounded-lg bg-bg">
                  {h.video && (
                    // eslint-disable-next-line @next/next/no-img-element -- 정적 내보내기: next/image 최적화 없음, 썸네일 핫링크(설계 8-2)
                    <img src={thumbnailUrl(h.video.video_id)} alt="" className="h-full w-full object-cover transition group-hover:scale-[1.02]" />
                  )}
                  <span className="absolute bottom-1.5 left-1.5 rounded-full bg-accent px-2 py-0.5 text-xs font-bold text-black">▶</span>
                  {h.stage_label && <span className="absolute left-1.5 top-1.5"><StageTag label={h.stage_label} /></span>}
                </div>
              </button>
              <div className="mt-1.5 px-1 text-sm">
                <Link href={`/players/?id=${h.batter.player_id}`} className="font-bold hover:underline">{h.batter.name}</Link>
                <span className="ml-1.5 text-xs text-muted">{h.batter.team}</span>
                <p className="text-xs text-muted">
                  {md(h.date)} vs {h.opponent} · {h.inning}회{h.inning_half} · {h.hr_label}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
