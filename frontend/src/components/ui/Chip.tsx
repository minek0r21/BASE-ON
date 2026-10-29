import type { ReactNode } from "react";

/** 거르기 칩 — 고르면 잉크 바탕 (05 지표 · 10 장면 종류 · 08 팀) */
export function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={on}
      className="flex h-9 items-center gap-1.5 rounded-full border border-line bg-surface px-4 text-[13px] font-medium transition-colors duration-[120ms] hover:bg-surface-2 aria-pressed:border-accent aria-pressed:bg-accent aria-pressed:font-bold aria-pressed:text-white"
    >
      {children}
    </button>
  );
}

/** 빈 상태 · 불러오기 실패 칸 (09 예외 상태) */
export function Empty({ text, action }: { text: string; action?: { label: string; onClick: () => void } }) {
  return (
    <div className="mt-8 flex flex-col items-center gap-4 rounded-3xl border border-line bg-surface py-16 text-sm text-fg-2">
      {text}
      {action && (
        <button onClick={action.onClick} className="rounded-xl bg-surface-2 px-4 py-2 font-bold text-fg hover:bg-surface-3">
          {action.label}
        </button>
      )}
    </div>
  );
}
