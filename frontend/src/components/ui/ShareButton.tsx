"use client";

import { useState } from "react";

/** 머리 버튼 — 06 팀 · 03 선수 · 04 경기 머리가 같은 크기로 쓴다 */
export const BTN = "h-10 rounded-full border border-line bg-surface px-4 text-sm font-bold hover:bg-surface-2";

/** 공유 — 지금 주소를 클립보드에 복사 (03 선수 머리 · 04 경기 상세) */
export default function ShareButton({ icon = false, className = "" }: { icon?: boolean; className?: string }) {
  const [done, setDone] = useState(false);
  const share = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setDone(true);
      setTimeout(() => setDone(false), 1600);
    } catch { /* 클립보드 권한이 없으면 조용히 넘긴다 */ }
  };
  if (icon) return (
    // 휴대폰 위 막대 (M03 · 11-08): 44px 아이콘, 복사되면 체크 표시
    <button type="button" onClick={share} aria-label={done ? "링크 복사됨" : "링크 복사"} className={`flex h-11 w-11 items-center justify-center ${className}`}>
      <svg viewBox="0 0 24 24" className="h-[22px] w-[22px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        {done ? <path d="m5 12.5 4.5 4.5L19 7.5" /> : <path d="M12 15V3m0 0L7.5 7.5M12 3l4.5 4.5M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7" />}
      </svg>
      <span className="sr-only" aria-live="polite">{done ? "링크 복사됨" : ""}</span>
    </button>
  );
  return (
    <button onClick={share} className={BTN} aria-live="polite">
      {done ? "링크 복사됨" : "공유"}
    </button>
  );
}
