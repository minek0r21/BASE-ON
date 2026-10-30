"use client";

import type { Playing } from "@/components/home/DayScenes";
import ScenePlayer from "@/components/ScenePlayer";

/** 화면 안 그 자리에서 바로 재생하는 어두운 칸 (별도 창 없음, 10-29 사용자) — 10 장면 · 06 팀 · 08 일정 */
export default function InlinePlayer({ playing, onClose, className = "" }: { playing: Playing; onClose: () => void; className?: string }) {
  return (
    <div className={`rounded-3xl bg-night p-5 text-white ${className}`}>
      <div className="mx-auto aspect-video w-full max-w-[760px] overflow-hidden rounded-2xl">
        <ScenePlayer bare clip={playing.clip} label={playing.title} />
      </div>
      <div className="mx-auto mt-3 flex max-w-[760px] items-center justify-between gap-4">
        <p>
          <span className="text-[17px] font-bold">{playing.title}</span>
          {playing.sub && <span className="ml-2 text-[13px] text-[#a1a1a8]">{playing.sub}</span>}
        </p>
        <button onClick={onClose} className="shrink-0 text-[13px] font-bold text-[#d3d4d8] hover:underline">닫기</button>
      </div>
    </div>
  );
}
