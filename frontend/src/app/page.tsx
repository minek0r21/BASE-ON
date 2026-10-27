"use client";

import { useState } from "react";
import SearchBox from "@/components/SearchBox";
import ScenePlayer from "@/components/ScenePlayer";
import PostseasonCorner from "@/components/home/PostseasonCorner";
import RecentHomeRuns from "@/components/home/RecentHomeRuns";
import type { Clip } from "@/lib/api";

// BO-MA-01 메인 (임시 — 메인 디자인은 Figma에서 정하는 중). 포스트시즌 코너(기간 중에만) → 최근 홈런 장면 (PS6 · PS7).
// 추천 선수 · 팀 순위 · 경기 일정(API 16 · 18 · 13 · 14)은 메인 디자인이 정해지면
export default function Home() {
  const [playing, setPlaying] = useState<{ clip: Clip; label: string } | null>(null);
  const onPlay = (clip: Clip, label: string) => setPlaying({ clip, label });

  return (
    <div className="space-y-10">
      <section className="mx-auto max-w-xl pt-12 text-center">
        <h1 className="text-3xl font-extrabold tracking-tight">
          BASE<span className="text-accent">:</span>ON
        </h1>
        <p className="mt-2 text-muted">KBO 타자의 기록과 장면을 한 번에</p>
        <div className="mt-8 text-left">
          <SearchBox large autoFocus />
        </div>
      </section>

      {playing && (
        <div className="sticky top-16 z-10">
          <ScenePlayer clip={playing.clip} label={playing.label} onClose={() => setPlaying(null)} />
        </div>
      )}

      <PostseasonCorner onPlay={onPlay} />
      <RecentHomeRuns onPlay={onPlay} />
    </div>
  );
}
