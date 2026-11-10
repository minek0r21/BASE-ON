"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

// 맨 위로 (11-08 모바일 비교: 네이버 스포츠처럼 긴 화면에서 한 번에 올라가기).
// 두 화면 넘게 내려가면 보인다. 휴대폰은 아래 탭 위에, 탭이 없는 경기 상세는 안전 영역 위에 놓는다
export default function ToTop() {
  const path = usePathname();
  const [show, setShow] = useState(false);
  useEffect(() => {
    const on = () => setShow(window.scrollY > window.innerHeight * 2);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, [path]);
  const noTab = path.startsWith("/games");
  const up = () => {
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: still ? "auto" : "smooth" });
  };
  return (
    <button
      type="button"
      onClick={up}
      aria-label="맨 위로"
      tabIndex={show ? 0 : -1}
      aria-hidden={!show}
      className={`fixed right-4 z-20 flex h-11 w-11 items-center justify-center rounded-full border border-line bg-raised text-fg shadow-md transition-opacity duration-200 md:right-8 md:bottom-8 md:h-12 md:w-12 ${
        noTab ? "bottom-[calc(16px+env(safe-area-inset-bottom))]" : "bottom-[calc(3.5rem+1px+12px+env(safe-area-inset-bottom))]"
      } ${show ? "opacity-100" : "pointer-events-none opacity-0"}`}
    >
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M12 19V5m0 0-6 6m6-6 6 6" />
      </svg>
    </button>
  );
}
