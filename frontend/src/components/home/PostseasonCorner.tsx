"use client";

import { useQuery } from "@tanstack/react-query";
import { getPostseason, qk, type Clip, type PostSeries } from "@/lib/api";
import { thumbnailUrl } from "@/components/ScenePlayer";
import { md } from "@/lib/format";
import StageTag from "@/components/StageTag";

// 메인 「포스트시즌 코너」 (API-25, docs/포스트시즌.md PS6): 기간 중에만 「최근 홈런 장면」 위에. 시리즈 결과 + 명장면
function SeriesCard({ s, onPlay }: { s: PostSeries; onPlay: (clip: Clip, label: string) => void }) {
  const [a, b] = s.teams;
  const result = s.winner
    ? `${s.winner} ${s.wins[s.winner]}승${Object.entries(s.wins).filter(([t]) => t !== s.winner).map(([, w]) => ` ${w}패`).join("")}`
    : `${a} ${s.wins[a] ?? 0} : ${s.wins[b] ?? 0} ${b}`;
  return (
    <article className="rounded-xl border border-line bg-surface p-4">
      <header className="mb-3 flex items-baseline justify-between gap-2">
        <h3 className="font-bold">{s.name}</h3>
        <p className="text-sm tabular-nums">
          {s.winner ? <span className="font-bold">{result}</span> : <span className="text-muted">진행 중 · {result}</span>}
        </p>
      </header>

      {s.scenes.length > 0 && (
        <ul className="mb-3 grid gap-2 sm:grid-cols-3">
          {s.scenes.map((c) => (
            <li key={c.label}>
              <button onClick={() => onPlay(c.clip, c.label)} className="group block w-full text-left" aria-label={`${c.label} 재생`}>
                <div className="relative aspect-video overflow-hidden rounded-lg bg-bg">
                  {/* eslint-disable-next-line @next/next/no-img-element -- 정적 내보내기: next/image 최적화 없음, 썸네일 핫링크(설계 8-2) */}
                  <img src={thumbnailUrl(c.clip.videoId)} alt="" className="h-full w-full object-cover transition group-hover:scale-[1.02]" />
                  <span className="absolute bottom-1.5 left-1.5 rounded-full bg-accent px-2 py-0.5 text-xs font-bold text-black">
                    {c.clip.precision === "scene" ? "▶" : "▶ 이닝"}
                  </span>
                </div>
                <p className="mt-1 line-clamp-2 text-xs leading-snug">{c.label}</p>
              </button>
            </li>
          ))}
        </ul>
      )}

      <ol className="divide-y divide-line text-sm">
        {s.games.map((g) => (
          <li key={g.gamePk} className="flex items-center gap-3 py-1.5">
            <StageTag label={g.stageLabel} />
            <span className="w-10 shrink-0 tabular-nums text-muted">{md(g.date)}</span>
            <span className="flex-1 tabular-nums">
              {g.away.team} {g.away.score} : {g.home.score} {g.home.team}
            </span>
            {g.highlight && (
              <button onClick={() => onPlay(g.highlight!, `${g.stageLabel} ${g.away.team} vs ${g.home.team} · 경기 하이라이트`)}
                className="shrink-0 rounded-lg border border-line px-2 py-0.5 text-xs font-semibold hover:bg-bg">
                하이라이트
              </button>
            )}
          </li>
        ))}
      </ol>
    </article>
  );
}

export default function PostseasonCorner({ onPlay }: { onPlay: (clip: Clip, label: string) => void }) {
  const q = useQuery({ queryKey: qk.postseason(), queryFn: ({ signal }) => getPostseason(signal) });
  if (!q.data?.period.active || q.data.series.length === 0) return null; // 기간 밖이면 그리지 않는다 (PS6)
  const d = q.data;
  return (
    <section aria-labelledby="ps-title" className="space-y-3">
      <h2 id="ps-title" className="text-lg font-extrabold">{d.season} 포스트시즌</h2>
      {[...d.series].reverse().map((s) => <SeriesCard key={s.stage} s={s} onPlay={onPlay} />)}
    </section>
  );
}
