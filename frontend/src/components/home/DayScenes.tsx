"use client";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기: 썸네일 핫링크(설계 8-2) */
import Link from "next/link";
import { useEffect, useState } from "react";
import { playerHref } from "@/components/SearchBox";
import ScenePlayer, { thumbnailUrl } from "@/components/ScenePlayer";
import { PlayGlyph, PlayerAvatar, mmss } from "@/components/ui/Media";
import type { Clip, Day, DayGame, DayScene } from "@/lib/api";
import { useReducedMotion } from "@/lib/motion";
import { team as teamOf } from "@/lib/teams";
import { clipLength, sceneSub, sceneTitle } from "./common";

type Pick = { scene: DayScene; game: DayGame };

/**
 * 큰 장면 고르기 — 응원팀이 있으면 그 팀 선수 장면, 없으면 그날 홈런 중 시즌 몇 호가 큰 순. 최대 3개를 큰 자리에서 넘긴다(featured, 첫 번째가 main).
 * (시안은 응원팀 경기의 대표 장면. 기준은 아직 팀 결정 전 — 디자인_2.0_구현 8장)
 * 옆 목록은 main 경기를 뺀 나머지 경기마다 한 장면씩(등판 장면 먼저, 없으면 홈런) 최대 4개. 같은 장면을 두 번 넣지 않는다
 */
export function pickScenes(day: Day, myTeam: string | null): { main: Pick | null; featured: Pick[]; others: Pick[] } {
  const all: Pick[] = day.games.flatMap((game) => game.scenes.map((scene) => ({ scene, game })));
  const bySeq = (ps: Pick[]) => ps.filter((p) => p.scene.kind === "home_run").sort((a, b) => (b.scene.hrSeq ?? 0) - (a.scene.hrSeq ?? 0));
  const mine = myTeam ? all.filter((p) => p.scene.team === myTeam) : [];
  const pool = mine.length ? [...bySeq(mine), ...mine.filter((p) => p.scene.kind !== "home_run")] : [...bySeq(all), ...all.filter((p) => p.scene.kind !== "home_run")];
  const featured = pool.slice(0, 3);
  const main = featured[0] ?? null;
  const used = new Set(featured.map((p) => p.scene.clip.videoId));
  const order = (p: Pick) => (p.scene.kind === "outing" ? (p.scene.role === "선발" ? 0 : 2) : 1); // 선발 등판 → 홈런 → 구원
  const others = day.games
    .filter((g) => g.game_pk !== main?.game.game_pk)
    .flatMap((g) => { const scene = g.scenes.find((x) => !used.has(x.clip.videoId)); return scene ? [{ scene, game: g }] : []; })
    .sort((a, b) => order(a) - order(b))
    .slice(0, 4);
  return { main, featured, others };
}

const ROTATE_MS = 5000;

/** 큰 자리 미리보기 넘김 (HANDOFF 모션 후보 「히어로 미리보기」) — 5초마다 크로스페이드, 마우스를 올리거나 재생 중이면 멈춤. 움직임 줄이기면 넘기지 않는다 */
function useRotation(n: number, paused: boolean) {
  const reduce = useReducedMotion();
  const [i, setI] = useState(0);
  useEffect(() => {
    if (paused || reduce || n < 2) return;
    const t = setInterval(() => setI((x) => (x + 1) % n), ROTATE_MS);
    return () => clearInterval(t);
  }, [n, paused, reduce]);
  return [n ? i % n : 0, setI] as const;
}

/** 지금 재생 중인 영상 — 큰 장면 자리에서 바로 재생한다 (별도 창 없음, 10-29 사용자) */
export type Playing = { clip: Clip; title: string; sub?: string };

export default function DayScenes({ day, myTeam, playing, onPlay }: {
  day: Day;
  myTeam: string | null;
  playing: Playing | null;
  onPlay: (p: Playing) => void;
}) {
  const { featured, others } = pickScenes(day, myTeam);
  const [hover, setHover] = useState(false);
  const [shown, setShown] = useRotation(featured.length, hover || !!playing);
  const main = featured[shown] ?? null;
  const isMain = !!main && (!playing || playing.clip.videoId === main.scene.clip.videoId);
  const c = day.scene_counts;
  const [, mm, dd] = day.date.split("-").map(Number);
  const wk = ["일", "월", "화", "수", "목", "금", "토"][new Date(`${day.date}T00:00:00`).getDay()];

  return (
    <section id="day-scenes" className="scroll-mt-20 rounded-[28px] bg-night px-6 pt-8 pb-9 text-white sm:px-9" aria-label="그날 장면">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[26px] font-bold">
            {mm}월 {dd}일 ({wk}) 장면
          </h2>
          <p className="mt-1.5 text-[13px] text-[#a1a1a8]">
            홈런 {c.home_runs}개 중 장면 {c.home_run_scenes}개 · 투수 장면 {c.pitcher_scenes}개 · 영상이 있는 장면만
          </p>
        </div>
        <Link href={`/scenes/?date=${day.date}`} className="text-sm font-bold text-white hover:underline">
          장면 전체 보기 ›
        </Link>
      </div>

      {!main && !playing ? (
        <p className="py-10 text-center text-sm text-[#a1a1a8]">이날 확정된 장면이 아직 없어요</p>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[680px_1fr]">
          <div>
            {playing ? (
              <div className="aspect-video w-full animate-grow overflow-hidden rounded-2xl">
                <ScenePlayer bare clip={playing.clip} label={playing.title} />
              </div>
            ) : (
              main && (
                <button
                  onClick={() => onPlay({ clip: main.scene.clip, title: sceneTitle(main.scene), sub: sceneSub(main.scene, main.game) })}
                  onMouseEnter={() => setHover(true)}
                  onMouseLeave={() => setHover(false)}
                  onFocus={() => setHover(true)}
                  onBlur={() => setHover(false)}
                  className="group relative block aspect-video w-full overflow-hidden rounded-2xl"
                  aria-label={`${sceneTitle(main.scene)} 재생`}
                >
                  {featured.map((f, k) => (
                    <img key={f.scene.clip.videoId} src={thumbnailUrl(f.scene.clip.videoId)} alt=""
                         className={`absolute inset-0 h-full w-full object-cover transition-[opacity,scale] duration-500 group-hover:scale-[1.02] ${k === shown ? "opacity-100" : "opacity-0"}`} />
                  ))}
                  <span className="absolute bottom-4 left-4 flex h-12 w-12 items-center justify-center rounded-full bg-accent text-white">
                    <PlayGlyph size={16} />
                  </span>
                  <span className="absolute top-3 right-3 rounded-md bg-black/70 px-1.5 py-0.5 font-num text-[11px] font-semibold">
                    {mmss(clipLength(main.scene.clip))}
                  </span>
                </button>
              )
            )}
            {!playing && featured.length > 1 && (
              <div className="mt-3 flex gap-1.5" role="group" aria-label="큰 장면 고르기">
                {featured.map((f, k) => (
                  <button key={f.scene.clip.videoId} onClick={() => setShown(k)} aria-pressed={k === shown} aria-label={sceneTitle(f.scene)}
                          className="h-1.5 w-6 rounded-full bg-white/25 transition-colors duration-300 aria-pressed:bg-white" />
                ))}
              </div>
            )}
            <p className="mt-4 text-[22px] font-bold">{playing ? playing.title : main && sceneTitle(main.scene)}</p>
            <p className="mt-1 text-[13px] text-[#a1a1a8]">{playing ? playing.sub : main && sceneSub(main.scene, main.game)}</p>
            {main && isMain && (
            <div className="mt-3 flex items-center gap-2.5">
              <PlayerAvatar id={main.scene.player.player_id} name={main.scene.player.name} team={main.scene.team} size={44} />
              <span className="text-[13px] font-medium text-[#d3d4d8]">
                {main.scene.player.name} · {teamOf(main.scene.team)?.full ?? main.scene.team}
              </span>
              <Link href={playerHref(main.scene.player.player_id)} className="text-[13px] font-bold text-[#8fb0ff] hover:underline">
                선수 보기 ›
              </Link>
            </div>
            )}
          </div>

          <ul className="divide-y divide-[#2c2c30]">
            {[...(main && !isMain ? [main] : []), ...others].map(({ scene, game }) => (
              <li key={`${game.game_pk}-${scene.clip.videoId}`}>
                <button
                  onClick={() => onPlay({ clip: scene.clip, title: sceneTitle(scene), sub: sceneSub(scene, game) })}
                  aria-current={playing?.clip.videoId === scene.clip.videoId ? "true" : undefined}
                  className="group flex w-full items-center gap-4 py-3 text-left aria-[current=true]:opacity-50"
                >
                  <span className="relative aspect-video w-44 shrink-0 overflow-hidden rounded-[10px]">
                    <img src={thumbnailUrl(scene.clip.videoId)} alt="" className="h-full w-full object-cover" />
                    <span className="absolute bottom-2 left-2 flex items-center gap-1 rounded-md bg-black/75 px-1.5 py-0.5 font-num text-[11px] font-semibold">
                      <PlayGlyph size={7} /> {mmss(clipLength(scene.clip))}
                    </span>
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[15px] font-bold group-hover:underline">{sceneTitle(scene)}</span>
                    <span className="mt-1 block text-xs text-[#a1a1a8]">{sceneSub(scene, game)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
