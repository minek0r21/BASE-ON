"use client";

import { useEffect, useRef, useState } from "react";

/** 「?」 — 눌러서 열고, 바깥을 누르거나 Esc로 닫는다. inline이면 글줄 안에 끼우는 작은 크기 (능력 칸 · 선수 화면 · 능력별 순위) */
export default function Help({ title, body, inline = false, below = false }: { title: string; body: string; inline?: boolean; below?: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  return (
    <span ref={ref} className={`relative ${inline ? "inline-block align-middle" : ""}`}>
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label={`${title} 설명`}
        className="flex h-[18px] w-[18px] items-center justify-center rounded-full border border-fg-2 text-[11px] font-bold text-fg-2 aria-expanded:border-fg aria-expanded:bg-fg aria-expanded:text-bg"
      >
        ?
      </button>
      {open && (
        <span role="tooltip" className={`absolute ${below ? "top-full mt-2 origin-top" : "bottom-full mb-2 origin-bottom"} left-1/2 z-20 block w-[282px] -translate-x-1/2 animate-pop rounded-xl bg-night px-4 py-3.5 text-left font-normal text-white shadow-lg`}>
          <span className="block text-[13px] font-bold">{title}</span>
          <span className="mt-1.5 block text-xs leading-[18px] font-normal text-[#d3d4d8]">{body}</span>
        </span>
      )}
    </span>
  );
}
