// 펼치기 표시 (글자 「⌄」는 글꼴에 따라 「v」처럼 보여서 선으로 그린다)
export function ChevronDown({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden className={`shrink-0 text-fg-2 ${className}`}>
      <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
