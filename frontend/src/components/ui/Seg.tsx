"use client";

/** 모바일 전환 칸 (Figma 모바일 시안의 segment) — 칸은 남는 폭을 똑같이 나눠 가져서 폭이 달라도 구성이 같다. 가로로 밀지 않는다 */
export default function Seg<T extends string | number>({ items, value, onChange, label, small = false, className = "" }: {
  items: { key: T; label: string }[];
  value: T;
  onChange: (key: T) => void;
  label: string;
  small?: boolean;
  className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={`flex h-11 gap-0.5 rounded-xl bg-surface-3 p-1 ${className}`}>
      {items.map((x) => (
        <button
          key={x.key}
          onClick={() => onChange(x.key)}
          aria-pressed={x.key === value}
          className={`min-w-0 flex-1 truncate rounded-[9px] font-medium text-fg-2 aria-pressed:bg-surface aria-pressed:font-bold aria-pressed:text-fg ${small ? "text-xs" : "text-[13px]"}`}
        >
          {x.label}
        </button>
      ))}
    </div>
  );
}
