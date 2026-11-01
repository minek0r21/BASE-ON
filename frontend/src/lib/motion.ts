"use client";

import { useEffect, useState, useSyncExternalStore, type RefObject } from "react";

/** 모션 공용 (HANDOFF 모션 후보, 11-01). CSS 모션은 globals.css가 「움직임 줄이기」에서 끄고, JS로 움직이는 것은 이 값을 본다 */
const QUERY = "(prefers-reduced-motion: reduce)";
export function useReducedMotion() {
  return useSyncExternalStore(
    (cb) => { const m = window.matchMedia(QUERY); m.addEventListener("change", cb); return () => m.removeEventListener("change", cb); },
    () => window.matchMedia(QUERY).matches,
    () => false,
  );
}

/** 요소가 처음 화면에 들어왔는가 (한 번 true가 되면 그대로) */
export function useSeen(ref: RefObject<Element | null>, threshold = 0.3) {
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } }, { threshold });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, seen, threshold]);
  return seen;
}

/** 0 → 1로 가는 진행도 (ease-out). start가 true가 된 뒤 delay만큼 기다렸다가 ms 동안. 움직임 줄이기면 바로 1 */
export function useProgress(start: boolean, ms = 600, delay = 0) {
  const reduce = useReducedMotion();
  const [t, setT] = useState(0);
  useEffect(() => {
    if (!start || reduce) return;
    let raf = 0;
    const t0 = performance.now() + delay;
    const step = (now: number) => {
      const x = Math.min(1, Math.max(0, (now - t0) / ms));
      setT(1 - (1 - x) ** 3);
      if (x < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [start, reduce, ms, delay]);
  return reduce ? 1 : t;
}
