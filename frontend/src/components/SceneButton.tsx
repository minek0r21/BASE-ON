import type { Clip } from "@/lib/api";

/**
 * 장면 버튼 — 정밀도마다 모양이 다르다 (설계 8-1, docs/장면.md 1장)
 *   scene  바로 그 장면      → 노란 ▶
 *   inning 그 이닝부터       → 테두리 버튼
 *   game   경기 요약 처음부터 → 「이 경기 하이라이트」 글자 버튼
 */
export default function SceneButton({ clip, label, onPlay }: { clip: Clip; label: string; onPlay: () => void }) {
  if (clip.precision === "scene") {
    return (
      <button
        onClick={onPlay}
        aria-label={`${label} 재생`}
        className="shrink-0 rounded-full bg-accent px-2.5 py-0.5 text-xs font-bold text-black hover:brightness-95"
      >
        ▶
      </button>
    );
  }
  if (clip.precision === "inning") {
    return (
      <button
        onClick={onPlay}
        aria-label={`${label} 재생 (그 이닝부터)`}
        className="shrink-0 rounded-full border border-accent px-2.5 py-0.5 text-xs font-bold hover:bg-bg"
      >
        ▶ 이닝
      </button>
    );
  }
  return (
    <button onClick={onPlay} className="shrink-0 rounded-lg border border-line px-2.5 py-1 text-xs font-semibold hover:bg-bg">
      이 경기 하이라이트
    </button>
  );
}
