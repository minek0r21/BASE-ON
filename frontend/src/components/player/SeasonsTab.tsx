"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { getPitcherOutings, getPlayerScenes, getPlayerSeasons, qk } from "@/lib/api";
import { innings, rate3 } from "@/lib/format";
import { SectionHead } from "@/components/home/common";
import StageTag from "@/components/StageTag";
import { Empty } from "@/components/ui/Chip";
import { PlayGlyph, TeamLogo } from "@/components/ui/Media";
import type { Role } from "./Hero";

// BO-PB-03 시즌 기록 (API-19). 타자 표 + 투수 표(투구 기록이 있으면). 숫자 머리에는 쉬운 설명(title). 프로필은 머리에 있어 뺐다 (10-31 사용자)
// 칸마다 정규시즌 중 가장 좋은 값은 구단 글자색(best: high 클수록 · low 작을수록 좋음), 줄 끝 「▶ n」은 그 시즌 장면 · 등판 탭으로 (10-31 사용자)
type Col<T> = { key: string; label: string; help?: string; value: (r: T) => string; strong?: boolean; best?: "high" | "low" };
type Bat = Record<string, unknown> & { season: number; teams: string[]; games: number };
type Pit = Record<string, unknown> & { season: number; teams: string[]; role_label: string };

const n = (v: unknown) => (v == null ? "–" : String(v));
const r3 = (v: unknown) => rate3(typeof v === "number" ? v : null);

const BAT: Col<Bat>[] = [
  { key: "games", label: "경기", value: (r) => n(r.games) },
  { key: "pa", label: "타석", value: (r) => n(r.pa) },
  { key: "ab", label: "타수", help: "타석에서 볼넷·사구·희생타를 뺀 수", value: (r) => n(r.ab) },
  { key: "h", label: "안타", value: (r) => n(r.h), best: "high" },
  { key: "b2", label: "2루타", value: (r) => n(r.b2), best: "high" },
  { key: "b3", label: "3루타", value: (r) => n(r.b3), best: "high" },
  { key: "hr", label: "홈런", value: (r) => n(r.hr), best: "high" },
  { key: "bb", label: "볼넷", value: (r) => n(r.bb), best: "high" },
  { key: "hbp", label: "사구", help: "몸에 맞는 공", value: (r) => n(r.hbp) },
  { key: "so", label: "삼진", value: (r) => n(r.so) },
  { key: "avg", label: "타율", value: (r) => r3(r.avg), best: "high" },
  { key: "obp", label: "출루율", help: "타석에서 살아 나간 비율", value: (r) => r3(r.obp), best: "high" },
  { key: "slg", label: "장타율", help: "타수당 루타 수 — 장타를 많이 칠수록 높다", value: (r) => r3(r.slg), best: "high" },
  { key: "ops", label: "OPS", help: "출루율 + 장타율, 타격 종합 점수", value: (r) => r3(r.ops), strong: true, best: "high" },
];

const PIT: Col<Pit>[] = [
  { key: "role", label: "역할", value: (r) => r.role_label },
  { key: "g", label: "등판", value: (r) => n(r.g) },
  { key: "gs", label: "선발", value: (r) => n(r.gs) },
  { key: "outs", label: "이닝", help: "아웃 3개 = 1이닝", value: (r) => innings(typeof r.outs === "number" ? r.outs : null), strong: true, best: "high" },
  { key: "tbf", label: "상대 타자", value: (r) => n(r.tbf) },
  { key: "h", label: "피안타", value: (r) => n(r.h) },
  { key: "hr", label: "피홈런", value: (r) => n(r.hr) },
  { key: "bb", label: "볼넷", value: (r) => n(r.bb) },
  { key: "hbp", label: "사구", value: (r) => n(r.hbp) },
  { key: "so", label: "탈삼진", value: (r) => n(r.so), best: "high" },
  { key: "r", label: "실점", value: (r) => n(r.r) },
  { key: "avg", label: "피안타율", help: "맞은 안타 비율 · 낮을수록 좋아요", value: (r) => r3(r.avg), best: "low" },
  { key: "whip", label: "WHIP", help: "1이닝에 내보낸 주자(안타 + 볼넷) · 낮을수록 좋아요", value: (r) => (typeof r.whip === "number" ? r.whip.toFixed(2) : "–"), best: "low" },
];

// 포스트시즌 줄 (PS3): 그 시즌 줄 바로 아래 「포스트시즌」. 팀 · 역할 칸이 없고 백분위도 없다
type Post = Record<string, unknown> & { season: number };

const num = (r: object, k: string) => { const v = (r as Record<string, unknown>)[k]; return typeof v === "number" ? v : null; };

function Table<T extends { season: number; teams: string[] }>({ title, rows, cols, post = [], unit, scenes, onScenes }: {
  title: string; rows: T[]; cols: Col<T>[]; post?: Post[];
  /** 줄 끝 칸 머리 (장면 · 등판) */ unit: string; scenes: Map<number, number>; onScenes: (season: number) => void;
}) {
  const postOf = new Map(post.map((p) => [p.season, p]));
  // 칸마다 가장 좋은 값 — 정규시즌이 2시즌 이상일 때만
  const best = new Map<string, number>();
  if (new Set(rows.map((r) => r.season)).size > 1) {
    for (const c of cols) {
      const vs = rows.map((r) => num(r, c.key)).filter((v): v is number => v != null);
      if (c.best && vs.length) best.set(c.key, c.best === "high" ? Math.max(...vs) : Math.min(...vs));
    }
  }
  const tone = (r: object, c: Col<T>) => (best.has(c.key) && num(r, c.key) === best.get(c.key) ? "font-bold text-(--team-text)" : c.strong ? "font-bold" : "");
  const shownScene = new Set<number>(); // 투수는 한 시즌에 역할 줄이 여럿일 수 있어 첫 줄에만
  return (
    <section>
      <SectionHead title={title} sub={tableSub(rows, post)} />
      <div className="overflow-x-auto rounded-3xl border border-line bg-surface px-6 py-2">
        <table className="w-full min-w-[720px] font-num text-sm">
          <thead className="text-xs text-fg-2">
            <tr className="border-b border-line">
              <th className="py-3 pr-3 text-left font-semibold">시즌</th>
              <th className="py-3 pr-3 text-left font-semibold">팀</th>
              {cols.map((c) => (
                <th key={c.key} title={c.help} className={`py-3 pl-2 text-right font-semibold ${c.help ? "cursor-help underline decoration-dotted" : ""}`}>
                  {c.label}
                </th>
              ))}
              <th className="py-3 pl-4 text-right font-semibold">{unit}</th>
            </tr>
          </thead>
          <tbody>
            {[...rows].sort((a, b) => b.season - a.season).flatMap((r) => {
              const p = postOf.get(r.season);
              return [
                <tr key={`${r.season}-${cols[0].value(r)}`} className="border-b border-line last:border-0">
                  <td className="py-3 pr-3 font-bold">{r.season}</td>
                  <td className="py-3 pr-3"><span className="flex items-center gap-1.5">{r.teams.map((t) => <TeamLogo key={t} team={t} height={14} />)} {r.teams.join(" · ")}</span></td>
                  {cols.map((c) => (
                    <td key={c.key} className={`py-3 pl-2 text-right ${tone(r, c)}`}>{c.value(r)}</td>
                  ))}
                  <td className="py-3 pl-4">
                    {!shownScene.has(r.season) && shownScene.add(r.season) && scenes.get(r.season) ? (
                      <button onClick={() => onScenes(r.season)} aria-label={`${r.season} 시즌 ${unit} ${scenes.get(r.season)}개 보기`}
                              className="ml-auto flex h-7 items-center gap-1 rounded-full bg-accent px-2.5 text-[11px] font-bold text-white hover:brightness-95">
                        <PlayGlyph size={7} /> {scenes.get(r.season)}
                      </button>
                    ) : null}
                  </td>
                </tr>,
                p && (
                  <tr key={`${r.season}-post`} className="border-b border-line bg-surface-2 last:border-0">
                    <td className="py-3 pr-3 text-muted">└</td>
                    <td className="py-3 pr-3"><StageTag label={`${r.season} 포스트시즌`} /></td>
                    {cols.map((c) => (
                      <td key={c.key} className={`py-3 pl-2 text-right ${c.strong ? "font-bold" : ""}`}>
                        {c.key === "role" ? "–" : c.value(p as unknown as T)}
                      </td>
                    ))}
                    <td />
                  </tr>
                ),
              ];
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** 「2024~2026 정규시즌 3시즌 · 포스트시즌은 그 시즌 아래 줄」 */
function tableSub(rows: { season: number }[], post: Post[]) {
  const ss = rows.map((r) => r.season);
  const span = ss.length ? `${Math.min(...ss)}~${Math.max(...ss)} 정규시즌 ${new Set(ss).size}시즌` : "";
  return [span, new Set(ss).size > 1 && "구단 색 숫자는 시즌 최고 기록", post.length > 0 && "포스트시즌은 그 시즌 아래 줄", "최신순"].filter(Boolean).join(" · ");
}

/** 시즌마다 장면(타자) · 등판(투수) 수 — 장면 · 등판 탭과 같은 캐시라 탭으로 넘어가면 바로 뜬다 */
function useSceneCounts(id: string, seasons: number[], role: Role) {
  const qs = useQueries({
    queries: seasons.map((s) => ({
      queryKey: qk.playerScenes(id, s, role),
      queryFn: ({ signal }: { signal: AbortSignal }) => (role === "pitcher" ? getPitcherOutings(id, s, signal) : getPlayerScenes(id, s, signal)),
    })),
  });
  return new Map(seasons.flatMap((s, i) => {
    const d = qs[i].data;
    if (!d) return [];
    return [[s, "outings" in d ? d.counts.outings : d.counts.scenes] as const];
  }));
}

export default function SeasonsTab({ playerId, onScenes }: { playerId: string; onScenes: (season: number, role: Role) => void }) {
  const q = useQuery({ queryKey: qk.seasons(playerId), queryFn: ({ signal }) => getPlayerSeasons(playerId, signal) });
  const batScenes = useSceneCounts(playerId, [...new Set(q.data?.batting.map((r) => r.season) ?? [])], "batter");
  const pitScenes = useSceneCounts(playerId, [...new Set(q.data?.pitching.map((r) => r.season) ?? [])], "pitcher");
  if (q.isPending) return <div className="h-[260px] animate-pulse rounded-3xl bg-surface-2" />;
  if (q.isError) return <Empty text="시즌 기록을 불러오지 못했어요" action={{ label: "다시 시도", onClick: () => q.refetch() }} />;
  const { batting, pitching, postBatting, postPitching } = q.data;

  return (
    <div className="animate-appear space-y-14">
      {batting.length > 0 && (
        <Table title="타격 기록" rows={batting as Bat[]} cols={BAT} post={postBatting} unit="장면" scenes={batScenes} onScenes={(s) => onScenes(s, "batter")} />
      )}
      {pitching.length > 0 && (
        <Table title="투구 기록" rows={pitching as Pit[]} cols={PIT} post={postPitching} unit="등판" scenes={pitScenes} onScenes={(s) => onScenes(s, "pitcher")} />
      )}
      {batting.length === 0 && pitching.length === 0 && <Empty text="시즌 기록이 없어요" />}
    </div>
  );
}
