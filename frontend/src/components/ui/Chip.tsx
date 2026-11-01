import Link from "next/link";
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

type EmptyAction = { label: string; onClick?: () => void; href?: string };

/**
 * 빈 상태 · 불러오기 실패 칸 (09 예외 상태, Figma 168:1934) — 원칙: 숨기지 않고, 이유를 말하고, 다른 길을 준다.
 * sub(이유 한 줄)나 버튼이 있으면 text는 굵은 제목. 버튼은 onClick 또는 href(다른 화면으로)
 */
export function Empty({ text, sub, action, actions }: { text: string; sub?: ReactNode; action?: EmptyAction; actions?: EmptyAction[] }) {
  const list = actions ?? (action ? [action] : []);
  const cls = "rounded-xl bg-surface-2 px-4 py-2 font-bold text-fg hover:bg-surface-3";
  return (
    <div className="mt-8 flex flex-col items-center gap-4 rounded-3xl border border-line bg-surface px-6 py-16 text-center text-sm text-fg-2">
      {sub || list.length > 0 ? (
        <div>
          <p className="text-base font-bold text-fg">{text}</p>
          {sub && <p className="mt-1.5">{sub}</p>}
        </div>
      ) : text}
      {list.length > 0 && (
        <div className="flex flex-wrap justify-center gap-2">
          {list.map((a) => a.href
            ? <Link key={a.label} href={a.href} className={cls}>{a.label}</Link>
            : <button key={a.label} onClick={a.onClick} className={cls}>{a.label}</button>)}
        </div>
      )}
    </div>
  );
}

/** 불러오기 실패 한 줄 — 실패한 구역만 바꾸고 나머지는 그대로 (09 「기록을 불러오지 못했을 때」) */
export function Retry({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-3xl border border-line bg-surface px-6 py-5 text-sm">
      <span className="text-fg-2">{text}</span>
      <button onClick={onRetry} className="rounded-xl bg-surface-2 px-4 py-2 font-bold hover:bg-surface-3">
        다시 시도
      </button>
    </div>
  );
}
