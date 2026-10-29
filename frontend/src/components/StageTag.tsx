// 포스트시즌 경기 꼬리표 「준PO 2차전」 (docs/포스트시즌.md PS3). 노랑(accent)은 ▶ 확정 장면 전용이라 반전 색을 쓴다
export default function StageTag({ label }: { label: string | null | undefined }) {
  if (!label) return null;
  return (
    <span className="shrink-0 rounded bg-fg px-1.5 py-0.5 text-[11px] font-bold leading-none text-bg">{label}</span>
  );
}
