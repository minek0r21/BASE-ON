import type { ReactNode } from "react";
import type { DayGame, DayScene } from "@/lib/api";
import { outingLine } from "@/lib/format";

/** 메인 화면 폭 (Figma 1440 화면의 본문 1200) */
export function Wrap({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`mx-auto w-full max-w-[1200px] px-4 xl:px-0 ${className}`}>{children}</div>;
}

/** 섹션 제목 — 기준 · 수치만 (AI 말투 부제 금지, 디자인_2.0_구현 6장) */
export function SectionHead({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">{title}</h2>
        {sub && <p className="mt-2 text-[13px] text-fg-2">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
/** 「2026-07-26」 → 「일」 */
export const weekday = (iso: string) => WEEK[new Date(`${iso}T00:00:00`).getDay()];

/** 「키움 8 : 3 KIA」 (원정 먼저) */
export const scoreText = (g: DayGame) => `${g.away.team} ${g.away.score} : ${g.home.score} ${g.home.team}`;

const HR_RUNS = ["", "솔로", "투런", "스리런", "만루"];

/** 장면 제목 — 우리 기록으로 만든다 (장면.md · 코드 outingLine). 「리그 첫 30홈런」 같은 말은 시안 예시라 쓰지 않는다 */
export function sceneTitle(s: DayScene) {
  if (s.kind === "outing") return `${s.player.name} ${s.line ? outingLine(s.line) : ""}`.trim();
  return `${s.player.name} ${s.hrSeq ? `${s.hrSeq}호 · ` : ""}${HR_RUNS[s.runs ?? 0] ?? ""} 홈런`.replace("  ", " ");
}

export function sceneSub(s: DayScene, g: DayGame) {
  if (s.kind === "outing") return `${scoreText(g)} · ${s.role} 등판`;
  return `${scoreText(g)} · ${s.inning}회${s.inningHalf}`;
}

export const clipLength = (c: { startSec: number; endSec: number | null; durationSec: number | null }) =>
  c.endSec != null ? c.endSec - c.startSec : c.durationSec;
