"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const TIP_W = 282;

/** 「?」 — 눌러서 열고, 바깥을 누르거나 Esc로 닫는다. inline이면 글줄 안에 끼우는 작은 크기 (능력 칸 · 선수 화면 · 능력별 순위)
 *  데스크톱 말풍선은 body에 띄운다 — 가로로 미는 표(overflow) 안에서도 잘리지 않게. 스크롤하면 닫는다 */
export default function Help({ title, body, inline = false, below = false }: { title: string; body: string; inline?: boolean; below?: boolean }) {
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState<{ x: number; y: number } | null>(null);
  const ref = useRef<HTMLSpanElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const tip = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node) && !tip.current?.contains(e.target as Node)) setOpen(false);
    };
    const shut = () => setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    window.addEventListener("scroll", shut, true);
    window.addEventListener("resize", shut);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
      window.removeEventListener("scroll", shut, true);
      window.removeEventListener("resize", shut);
    };
  }, [open]);
  const toggle = () => {
    const r = btn.current?.getBoundingClientRect();
    if (r) {
      const x = Math.min(Math.max(r.left + r.width / 2 - TIP_W / 2, 8), window.innerWidth - TIP_W - 8);
      setAt({ x, y: below ? r.bottom + 8 : r.top - 8 });
    }
    setOpen(!open);
  };
  return (
    <span ref={ref} className={`relative ${inline ? "inline-block align-middle" : ""}`}>
      <button
        ref={btn}
        onClick={toggle}
        aria-expanded={open}
        aria-label={`${title} 설명`}
        className="flex h-[18px] w-[18px] items-center justify-center rounded-full border border-fg-2 text-[11px] font-bold text-fg-2 aria-expanded:border-fg aria-expanded:bg-fg aria-expanded:text-bg"
      >
        ?
      </button>
      {open && createPortal(
        <div className="fixed inset-0 z-50 md:hidden">
          <button aria-label="닫기" onClick={() => setOpen(false)} className="absolute inset-0 bg-black/45" />
          <div role="dialog" aria-label={title} className="absolute inset-x-0 bottom-0 rounded-t-[20px] bg-raised px-5 pt-2.5 pb-[calc(1.5rem+env(safe-area-inset-bottom))] text-left text-fg">
            <div className="mx-auto h-1 w-10 rounded-full bg-line-strong" aria-hidden />
            <p className="mt-3 text-lg font-bold">{title}</p>
            <p className="mt-2 text-[15px] leading-[23px] font-normal text-fg-2">{body}</p>
            <button onClick={() => setOpen(false)} className="mt-3 h-11 w-full rounded-xl bg-fg text-[13px] font-bold text-white">닫기</button>
          </div>
        </div>,
        document.body,
      )}
      {open && at && createPortal(
        <span ref={tip} role="tooltip" style={{ left: at.x, top: at.y, width: TIP_W }}
              className={`fixed hidden md:block ${below ? "origin-top" : "-translate-y-full origin-bottom"} z-50 animate-pop rounded-xl bg-night px-4 py-3.5 text-left font-normal text-white shadow-lg`}>
          <span className="block text-[13px] font-bold">{title}</span>
          <span className="mt-1.5 block text-xs leading-[18px] font-normal text-[#d3d4d8]">{body}</span>
        </span>,
        document.body,
      )}
    </span>
  );
}
