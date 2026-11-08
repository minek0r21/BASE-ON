"use client";

import type { Playing } from "@/components/home/DayScenes";
import ScenePlayer from "@/components/ScenePlayer";

/** 화면 안 그 자리에서 바로 재생하는 어두운 칸 (별도 창 없음, 10-29 사용자) — 10 장면 · 06 팀 · 08 일정. 열릴 때 누른 자리에서 커지며 나타난다 */
export default function InlinePlayer({ playing, onClose, className = "" }: { playing: Playing; onClose: () => void; className?: string }) {
  return (
    <div className={`origin-top animate-grow rounded-2xl bg-night p-3 text-white md:rounded-3xl md:p-5 ${className}`}>
      <div className="mx-auto aspect-video w-full max-w-[760px] overflow-hidden rounded-xl md:rounded-2xl">
        <ScenePlayer bare clip={playing.clip} label={playing.title} />
      </div>
      <div className="mx-auto mt-3 flex max-w-[760px] items-center justify-between gap-4">
        <p>
          <span className="block text-sm font-bold md:inline md:text-[17px]">{playing.title}</span>
          {playing.sub && <span className="text-xs text-[#a1a1a8] md:ml-2 md:text-[13px]">{playing.sub}</span>}
        </p>
        <button onClick={onClose} className="h-11 shrink-0 text-[13px] font-bold text-[#d3d4d8] hover:underline md:h-auto">닫기</button>
      </div>
    </div>
  );
}
