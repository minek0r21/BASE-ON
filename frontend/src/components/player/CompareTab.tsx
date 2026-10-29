"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getCompare, qk, type ComparePlayer } from "@/lib/api";
import { AXIS_HELP } from "@/lib/constants";
import { formatStat } from "@/lib/format";
import SearchBox from "@/components/SearchBox";

const MAX = 3;
const COLORS = ["bg-s1", "bg-s2", "bg-s3"]; // 선수 순서대로 고정 (색은 선수를 따른다)
const DOTS = ["text-s1", "text-s2", "text-s3"];
const STAT_ROW = [
  { key: "pa", label: "타석" }, { key: "avg", label: "타율" }, { key: "obp", label: "출루율" },
  { key: "slg", label: "장타율" }, { key: "ops", label: "OPS" }, { key: "hr", label: "홈런" },
] as const;

// BO-PB-04 비교 (FR-06, API-11). 지금 선수 + 검색으로 1~2명. 대상 밖 선수는 원 수치만
export default function CompareTab({
  playerId,
  season,
  withIds,
  onChange,
}: {
  playerId: string;
  season: number | null;
  withIds: string[];
  onChange: (withIds: string[]) => void;
}) {
  const ids = [playerId, ...withIds.filter((i) => i !== playerId)].slice(0, MAX);
  const q = useQuery({
    queryKey: qk.compare(ids, season),
    queryFn: ({ signal }) => getCompare(ids, season, signal),
    enabled: ids.length >= 2,
    placeholderData: keepPreviousData,
  });

  const add = (id: string) => {
    if (!ids.includes(id) && ids.length < MAX) onChange([...withIds, id]);
  };
  const remove = (id: string) => onChange(withIds.filter((i) => i !== id));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <div className="w-full sm:w-72">
          <SearchBox
            onSelect={(p) => add(p.player_id)}
            placeholder={ids.length >= MAX ? `${MAX}명까지 비교할 수 있어요` : "비교할 타자 추가"}
            disabled={ids.length >= MAX}
          />
        </div>
        {q.data?.players.slice(1).map((p, i) => (
          <button
            key={p.player_id}
            onClick={() => remove(p.player_id)}
            className="flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-sm hover:bg-bg"
            aria-label={`${p.name} 빼기`}
          >
            <span className={DOTS[i + 1]}>●</span>
            {p.name} <span className="text-muted">✕</span>
          </button>
        ))}
      </div>

      {ids.length < 2 ? (
        <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">
          비교할 타자를 검색해서 추가해 주세요. 최대 {MAX}명까지 나란히 볼 수 있어요.
        </p>
      ) : q.isPending ? (
        <p className="text-muted">불러오는 중…</p>
      ) : q.isError ? (
        <p className="text-muted">비교를 불러오지 못했습니다.</p>
      ) : (
        <Compare players={q.data.players} season={q.data.season} groupSize={q.data.group_size} />
      )}
    </div>
  );
}

function Compare({ players, season, groupSize }: { players: ComparePlayer[]; season: number; groupSize: number }) {
  return (
    <>
      {/* 범례: 선수 색 + 대상 밖 안내 */}
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {players.map((p, i) => (
          <span key={p.player_id} className="flex items-center gap-1.5">
            <span className={`inline-block h-2.5 w-2.5 rounded-full ${COLORS[i]}`} />
            <span className="font-semibold">{p.name}</span>
            <span className="text-muted">{[p.team, p.message].filter(Boolean).join(" · ")}</span>
          </span>
        ))}
      </div>

      <section className="rounded-xl border border-line bg-surface p-5">
        <header className="mb-4 flex items-baseline justify-between gap-2">
          <h2 className="font-bold">리그 백분위 비교</h2>
          <span className="text-xs text-muted">{season} 비교 대상 {groupSize}명</span>
        </header>
        <ul className="space-y-5">
          {players[0].axes.map((axis, ai) => (
            <li key={axis.key}>
              <div className="text-sm font-semibold" title={AXIS_HELP[axis.key]}>
                {axis.label}
              </div>
              <div className="mt-1.5 space-y-1.5">
                {players.map((p, pi) => {
                  const a = p.axes[ai];
                  return (
                    <div key={p.player_id} className="grid grid-cols-[4.5rem_1fr_7.5rem] items-center gap-2 text-xs sm:grid-cols-[6rem_1fr_9rem]">
                      <span className="truncate text-muted">{p.name}</span>
                      <div className="h-2.5 overflow-hidden rounded-full bg-bar-track" role="meter" aria-label={`${p.name} ${axis.label} 백분위`}
                        aria-valuemin={0} aria-valuemax={100} aria-valuenow={a.percentile ?? undefined}>
                        {a.percentile != null && <div className={`h-full rounded-full ${COLORS[pi]}`} style={{ width: `${a.percentile}%` }} />}
                      </div>
                      <span className="text-right tabular-nums">
                        {a.percentile != null ? <span className="font-bold">상위 {100 - a.percentile}%</span> : <span className="text-muted">–</span>}
                        <span className="ml-1.5 text-muted">{formatStat(a.metric, a.value)}</span>
                      </span>
                    </div>
                  );
                })}
              </div>
              <p className="mt-1 text-xs text-muted">{AXIS_HELP[axis.key]}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* 원 수치 표 */}
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th className="px-3 py-2 text-left font-medium">선수</th>
              {STAT_ROW.map((s) => (
                <th key={s.key} className="px-3 py-2 text-right font-medium">{s.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {players.map((p, i) => (
              <tr key={p.player_id} className="border-b border-line last:border-0">
                <td className="px-3 py-2 font-semibold">
                  <span className={`mr-1.5 ${DOTS[i]}`}>●</span>
                  {p.name}
                </td>
                {STAT_ROW.map((s) => (
                  <td key={s.key} className="px-3 py-2 text-right tabular-nums">{formatStat(s.key, p.stats?.[s.key])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
