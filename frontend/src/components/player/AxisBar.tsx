import type { ReactNode } from "react";

/** 백분위 막대 한 줄 — 타자·투수 요약이 같이 쓴다 (FR-02-02·FR-10, 투수.md P9: 「상위 N%」·등수가 앞, 원 수치는 작게) */
export default function AxisBar({
  label,
  help,
  valueText,
  percentile,
  topPct,
  rankText,
  note,
  action,
}: {
  /** 지표 이름 옆에 놓을 것 (축 장면 ▶, docs/장면.md 6장). 없으면 아무것도 그리지 않는다 */
  action?: ReactNode;
  label: string;
  help: string;
  valueText: string;
  percentile: number | null;
  topPct: number | null;
  /** 예: 「103명 중 6위」 · 「선발 45명 중 1위」 */
  rankText: string | null;
  /** 설명 대신 보일 문구 (예: 「계산 불가(월별 타석 부족)」) */
  note?: string | null;
}) {
  return (
    <li>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="flex items-center gap-2">
          <span className="font-semibold" title={help}>
            {label}
          </span>
          {action}
        </span>
        <span className="tabular-nums">
          <span className="text-muted">{valueText}</span>
          {percentile != null && (
            <>
              <span className="ml-3 font-bold">상위 {topPct}%</span>
              {rankText && <span className="ml-2 text-xs text-muted">{rankText}</span>}
            </>
          )}
        </span>
      </div>
      <div
        className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-bar-track"
        role="meter"
        aria-label={`${label} 백분위`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percentile ?? undefined}
      >
        {percentile != null && <div className="h-full rounded-full bg-bar" style={{ width: `${percentile}%` }} />}
      </div>
      <p className="mt-1 text-xs text-muted">{note ?? help}</p>
    </li>
  );
}
