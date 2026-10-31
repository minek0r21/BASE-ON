"use client";

import { useState } from "react";

/** 머리 버튼 — 06 팀 · 03 선수 · 04 경기 머리가 같은 크기로 쓴다 */
export const BTN = "h-10 rounded-full border border-line bg-surface px-4 text-sm font-bold hover:bg-surface-2";

/** 공유 — 지금 주소를 클립보드에 복사 (03 선수 머리 · 04 경기 상세) */
export default function ShareButton() {
  const [done, setDone] = useState(false);
  const share = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setDone(true);
      setTimeout(() => setDone(false), 1600);
    } catch { /* 클립보드 권한이 없으면 조용히 넘긴다 */ }
  };
  return (
    <button onClick={share} className={BTN} aria-live="polite">
      {done ? "링크 복사됨" : "공유"}
    </button>
  );
}
