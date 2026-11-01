"use client";

import { useEffect, useLayoutEffect, useRef, useState, type ComponentProps } from "react";

type Box = { left: number; width: number; top: number; height: number };

/**
 * 전환(타자 · 투수) · 탭의 선택 표시가 미끄러져 옮겨 간다 (HANDOFF 모션 후보, 11-01).
 * 그룹 안에서 선택된 요소(aria-pressed · aria-current)의 자리를 재서 표시 하나가 따라간다.
 * line이면 밑줄(가로 위치 · 너비만), 아니면 알약 바탕(세로까지). 버튼은 표시 위로 올라오게 relative
 */
export default function Slide({ line = false, mark, className = "", children, ...rest }: ComponentProps<"div"> & { line?: boolean; mark: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<Box | null>(null);
  const [ready, setReady] = useState(false); // 처음 자리는 움직이지 않고 바로 놓는다

  useLayoutEffect(() => {
    const g = ref.current;
    if (!g) return;
    const measure = () => {
      const el = g.querySelector<HTMLElement>('[aria-pressed="true"], [aria-current="page"]');
      setBox(el ? { left: el.offsetLeft, width: el.offsetWidth, top: el.offsetTop, height: el.offsetHeight } : null);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(g);
    const mo = new MutationObserver(measure);
    mo.observe(g, { subtree: true, childList: true, attributes: true, attributeFilter: ["aria-pressed", "aria-current"] });
    return () => { ro.disconnect(); mo.disconnect(); };
  }, []);
  useEffect(() => {
    if (!box || ready) return;
    const r = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(r);
  }, [box, ready]);

  return (
    <div ref={ref} className={`relative ${className}`} {...rest}>
      {box && (
        <span
          aria-hidden
          className={`pointer-events-none absolute ${ready ? "transition-[left,width,top,height] duration-200 ease-out" : ""} ${mark}`}
          style={line ? { left: box.left, width: box.width } : box}
        />
      )}
      {children}
    </div>
  );
}
