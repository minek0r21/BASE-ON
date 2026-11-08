"use client";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기: next/image 최적화 서버가 없다 */
import { useState } from "react";
import { logoSmallUrl, logoUrl, photoUrl, team as teamOf } from "@/lib/teams";

/** 선수 얼굴 (원형). 사진은 4배로 키운 376×472(scripts/upscale_media.py)라 72px까지 깨지지 않는다 — 없으면 이름 첫 글자 + 구단 연한 색 */
export function PlayerAvatar({ id, name, team, size = 40 }: { id: string; name: string; team?: string | null; size?: number }) {
  const [failed, setFailed] = useState(false);
  const t = teamOf(team);
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-line bg-surface-2"
      style={{ width: size, height: size, background: failed ? t?.soft : undefined }}
    >
      {failed ? (
        <span className="font-bold" style={{ fontSize: size * 0.4, color: t?.text ?? "var(--fg-2)" }} aria-hidden>
          {name.slice(0, 1)}
        </span>
      ) : (
        <img src={photoUrl(id)} alt="" className="h-full w-full object-cover object-top" onError={() => setFailed(true)} loading="lazy" />
      )}
    </span>
  );
}

/** 구단 엠블럼. 없으면 팀 이름 글자 */
export function TeamLogo({ team, height = 16 }: { team: string | null | undefined; height?: number }) {
  const [step, setStep] = useState(height <= 32 ? 0 : 1); // 작은 파일 → 원본 → 글자
  const url = step === 0 ? logoSmallUrl(team) : step === 1 ? logoUrl(team) : null;
  if (!url) {
    return team ? (
      <span className="text-[11px] font-bold" style={{ color: teamOf(team)?.text }}>
        {team}
      </span>
    ) : null;
  }
  return <img src={url} alt={team ?? ""} style={{ height }} className="w-auto shrink-0" onError={() => setStep(step + 1)} />;
}

/** 재생 ▶ 삼각형 — 잉크 바탕 버튼 안에 쓴다 */
export function PlayGlyph({ size = 8 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 10 10" aria-hidden className="shrink-0">
      <path d="M1.5 0.8 9 5 1.5 9.2Z" fill="currentColor" />
    </svg>
  );
}

/** 초 → 「2:43」 */
export const mmss = (sec: number | null | undefined) => {
  if (sec == null || sec < 0) return "";
  const s = Math.round(sec);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
