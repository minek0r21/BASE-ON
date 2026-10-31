"use client";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기: next/image 최적화 서버가 없다 */
import { useQueries, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type CSSProperties, type ReactNode } from "react";
import type { Playing } from "@/components/home/DayScenes";
import { Wrap, clipLength } from "@/components/home/common";
import InlinePlayer from "@/components/InlinePlayer";
import { representative, type Role } from "@/components/player/Hero";
import { thumbnailUrl } from "@/components/ScenePlayer";
import SearchBox, { playerHref } from "@/components/SearchBox";
import { Empty } from "@/components/ui/Chip";
import { PlayGlyph, PlayerAvatar, TeamLogo, mmss } from "@/components/ui/Media";
import { getCompare, getMeta, getPlayer, getSimilar, qk, type ComparePlayer, type PlayerSummary } from "@/lib/api";
import { josa } from "@/lib/abilities";
import { axisCopy } from "@/lib/axes";
import { innings, md, rate3 } from "@/lib/format";
import { leaguePosition } from "@/lib/position";
import { photoUrl, team as teamOf } from "@/lib/teams";

const MAX = 3;
/** 선수 순서별 고정색 (데이터 막대 · 점). 소속 팀은 카드의 구단 색 · 이름 옆 로고로 따로 보여 준다 (11-01 사용자) */
const SERIES = ["var(--s1)", "var(--s2)", "var(--s3)"];
const tint = (i: number, pct = 14) => `color-mix(in srgb, ${SERIES[i]} ${pct}%, transparent)`;
const CLOSE = 5; // 백분위 차이가 이보다 작으면 「비슷해요」

type Row = { label: string; get: (s: Record<string, number | null>) => number | null; fmt: (v: number | null) => string; better?: "high" | "low" };
const pct1 = (v: number | null) => (v == null ? "–" : `${(v * 100).toFixed(1)}%`);
const int = (v: number | null) => (v == null ? "–" : String(v));
const BAT_ROWS: Row[] = [
  { label: "홈런", get: (s) => s.hr, fmt: int, better: "high" },
  { label: "타율", get: (s) => s.avg, fmt: rate3, better: "high" },
  { label: "출루율", get: (s) => s.obp, fmt: rate3, better: "high" },
  { label: "장타율", get: (s) => s.slg, fmt: rate3, better: "high" },
  { label: "OPS", get: (s) => s.ops, fmt: rate3, better: "high" },
  { label: "삼진 비율", get: (s) => s.k_pct, fmt: pct1, better: "low" },
  { label: "볼넷 비율", get: (s) => s.bb_pct, fmt: pct1, better: "high" },
  { label: "타석", get: (s) => s.pa, fmt: int },
];
const PIT_ROWS: Row[] = [
  { label: "이닝", get: (s) => s.outs, fmt: (v) => innings(v), better: "high" },
  { label: "탈삼진", get: (s) => s.so, fmt: int, better: "high" },
  { label: "WHIP", get: (s) => s.whip, fmt: (v) => (v == null ? "–" : v.toFixed(2)), better: "low" },
  { label: "피안타율", get: (s) => s.avg, fmt: rate3, better: "low" },
  { label: "볼넷 · 몸에 맞는 공", get: (s) => (s.bb == null ? null : s.bb + (s.hbp ?? 0)), fmt: int },
  { label: "피홈런", get: (s) => s.hr, fmt: int },
  { label: "등판 (선발)", get: (s) => s.g, fmt: int },
];

/**
 * 07 선수 비교 (Figma 145:923) — 2~3명, 타자끼리 · 투수끼리 (API-11 as=). 선수 화면 「비교하기」로 들어온다 (/compare/?ids=&as=).
 * 막대 · 점은 순서별 고정색(파랑 · 주황 · 초록), 소속 팀은 카드 사진 바탕(구단 연한 색) · 큰 로고와 이름마다 붙는 작은 로고로.
 * 한 명뿐이면 「선수 추가」 칸에 비슷한 선수(API-31) 바로가기 + 검색
 */
export default function CompareView() {
  const params = useSearchParams();
  const router = useRouter();
  const role: Role = params.get("as") === "pitcher" ? "pitcher" : "batter";
  const ids = [...new Set((params.get("ids") ?? "").split(",").filter(Boolean))].slice(0, MAX);
  const go = (next: string[], r: Role = role) =>
    router.replace(`/compare/?${new URLSearchParams({ ...(next.length ? { ids: next.join(",") } : {}), as: r })}`, { scroll: false });

  const meta = useQuery({ queryKey: qk.meta(), queryFn: ({ signal }) => getMeta(signal) });
  const cmp = useQuery({
    queryKey: qk.compare(ids, null, role),
    queryFn: ({ signal }) => getCompare(ids, null, signal, role),
    enabled: ids.length >= 2,
  });
  const players = useQueries({ queries: ids.map((id) => ({ queryKey: qk.player(id, null), queryFn: ({ signal }: { signal: AbortSignal }) => getPlayer(id, null, signal) })) });
  const summaries = players.map((q) => q.data);
  const season = cmp.data?.season ?? summaries[0]?.season ?? null;
  const asOf = meta.data?.data_as_of;
  const data = ids.length >= 2 ? cmp.data : undefined;

  const sub = [season && `${season} 정규시즌`, asOf && `${md(asOf)} 기준`,
    role === "pitcher" ? "순위는 각자 역할(선발 · 불펜) 비교 대상 안" : cmp.data?.group_size && `타자 ${cmp.data.group_size}명 중 순위`, `최대 ${MAX}명`].filter(Boolean).join(" · ");

  return (
    <Wrap className="pt-10 pb-24">
      <nav className="text-[13px] text-muted" aria-label="위치">
        <Link href="/rankings/" className="hover:underline">선수</Link> <span aria-hidden>›</span> 비교
      </nav>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[40px] font-extrabold tracking-tight">선수 비교</h1>
          <p className="mt-1.5 text-sm text-fg-2">{sub}</p>
        </div>
        <div className="flex rounded-full border border-line bg-surface p-1" role="group" aria-label="타자 · 투수">
          {(["batter", "pitcher"] as const).map((r) => (
            <button key={r} onClick={() => r !== role && go([], r)} aria-pressed={role === r}
                    className="h-[30px] rounded-full px-5 text-[13px] font-medium text-fg-2 aria-pressed:bg-surface-3 aria-pressed:font-bold aria-pressed:text-fg">
              {r === "batter" ? "타자" : "투수"}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-7 grid items-start gap-4 lg:grid-cols-3">
        {ids.map((id, i) => (
          <PlayerCard key={id} i={i} p={summaries[i]} c={data?.players[i]} role={role}
                      onSwap={(nid) => go(ids.map((x) => (x === id ? nid : x)))}
                      onRemove={ids.length > 1 ? () => go(ids.filter((x) => x !== id)) : undefined} exclude={ids} />
        ))}
        {ids.length < MAX && (
          <AddCard role={role} base={ids[0]} season={season} exclude={ids} open={ids.length < 2} onAdd={(nid) => go([...ids, nid])} />
        )}
      </div>

      {ids.length >= 2 && (cmp.isError ? (
        <div className="mt-6"><Empty text="비교 기록을 불러오지 못했어요" action={{ label: "다시 시도", onClick: () => cmp.refetch() }} /></div>
      ) : !data ? (
        <div className="mt-6 h-[520px] animate-pulse rounded-3xl bg-surface-2" />
      ) : (
        <>
          <Abilities data={data.players} n={data.group_size ?? null} />
          <div className="mt-6 grid items-start gap-6 lg:grid-cols-2">
            <Stats players={data.players} rows={role === "pitcher" ? PIT_ROWS : BAT_ROWS} />
            <Scenes ids={ids} summaries={summaries} role={role} names={data.players.map((p) => p.name)} />
          </div>
        </>
      ))}
    </Wrap>
  );
}

/** 이름 + 작은 팀 로고 (이름이 나오는 모든 자리) */
function Name({ name, team, i, bold = true }: { name: string; team: string | null | undefined; i?: number; bold?: boolean }) {
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      {i != null && <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: SERIES[i] }} aria-hidden />}
      <span className={`truncate ${bold ? "font-bold" : ""}`}>{name}</span>
      <TeamLogo team={team} height={13} />
    </span>
  );
}

function PlayerCard({ i, p, c, role, onSwap, onRemove, exclude }: {
  i: number; p?: PlayerSummary; c?: ComparePlayer; role: Role; onSwap: (id: string) => void; onRemove?: () => void; exclude: string[];
}) {
  const [swap, setSwap] = useState(false);
  const t = teamOf(c?.team ?? p?.team);
  const pi = p?.pitching;
  const chip = role === "pitcher"
    ? pi && `${innings(pi.outs)}이닝 · WHIP ${pi.whip?.toFixed(2) ?? "–"}`
    : p?.stats && `${p.stats.hr}홈런 · OPS ${rate3(p.stats.ops)}`;
  const pos = role === "pitcher" ? (pi ? `투수 (${pi.roleLabel})` : "투수") : p?.position;
  return (
    <div className="overflow-hidden rounded-3xl border border-line bg-surface">
      <div className="h-1" style={{ background: SERIES[i] }} aria-hidden />
      <div className="flex gap-4 p-5">
        <span className="flex h-[88px] w-[70px] shrink-0 items-end justify-center overflow-hidden rounded-2xl" style={{ background: t?.soft ?? "var(--surface-2)" }}>
          {p && <img src={photoUrl(p.playerId)} alt="" className="h-full w-full object-cover object-top" onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <Link href={p ? playerHref(p.playerId) : "#"} className="flex min-w-0 items-center gap-2 text-[22px] leading-tight font-extrabold hover:underline">
              <span className="truncate">{p?.name ?? c?.name ?? "…"}</span> <TeamLogo team={t?.name} height={22} />
            </Link>
            <span className="flex shrink-0 gap-2 text-xs font-bold text-fg-2">
              <button onClick={() => setSwap(!swap)} className="hover:text-fg hover:underline">{swap ? "닫기" : "바꾸기"}</button>
              {onRemove && <button onClick={onRemove} className="hover:text-fg hover:underline">빼기</button>}
            </span>
          </div>
          <p className="mt-1 truncate text-[13px] text-fg-2">{[t?.full ?? p?.team, pos].filter(Boolean).join(" · ")}</p>
          {chip && (
            <p className="mt-2 inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-bold" style={{ background: tint(i) }}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: SERIES[i] }} aria-hidden /> {chip}
            </p>
          )}
          {c?.message && <p className="mt-1.5 text-xs text-muted">{c.message}</p>}
        </div>
      </div>
      {swap && <div className="border-t border-line p-4"><Picker role={role} base={exclude[0]} season={p?.season ?? null} exclude={exclude} onPick={(id) => { setSwap(false); onSwap(id); }} /></div>}
    </div>
  );
}

function AddCard({ role, base, season, exclude, open, onAdd }: {
  role: Role; base?: string; season: number | null; exclude: string[]; open: boolean; onAdd: (id: string) => void;
}) {
  const [on, setOn] = useState(false);
  if (!open && !on) return (
    <button onClick={() => setOn(true)} className="flex min-h-[132px] flex-col items-center justify-center gap-1.5 rounded-3xl border-2 border-dashed border-line text-sm font-bold text-fg-2 hover:bg-surface">
      <span className="text-2xl leading-none" aria-hidden>+</span> 선수 추가
    </button>
  );
  return (
    <div className="rounded-3xl border-2 border-dashed border-line p-5">
      <p className="mb-3 text-sm font-bold">선수 추가</p>
      <Picker role={role} base={base} season={season} exclude={exclude} onPick={(id) => { setOn(false); onAdd(id); }} />
    </div>
  );
}

/** 검색 + 비슷한 선수 바로가기 (첫 선수 기준, API-31) */
function Picker({ role, base, season, exclude, onPick }: { role: Role; base?: string; season: number | null; exclude: string[]; onPick: (id: string) => void }) {
  const sim = useQuery({
    queryKey: qk.similar(base ?? "", season ?? 0, role),
    queryFn: ({ signal }) => getSimilar(base!, season!, role, signal),
    enabled: !!base && season != null,
  });
  const picks = (sim.data?.players ?? []).filter((x) => !exclude.includes(x.player_id)).slice(0, 4);
  return (
    <div>
      <SearchBox onSelect={(h) => onPick(h.player_id)} placeholder={`${role === "pitcher" ? "투수" : "타자"} 이름 · 초성`} />
      {picks.length > 0 && (
        <>
          <p className="mt-3 text-xs font-bold text-fg-2">{josa(sim.data!.label, "이", "가")} 비슷한 {role === "pitcher" ? "투수" : "타자"}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {picks.map((x) => (
              <button key={x.player_id} onClick={() => onPick(x.player_id)}
                      className="flex h-9 items-center gap-1.5 rounded-full border border-line bg-surface pr-3 pl-1 text-[13px] font-bold hover:bg-surface-2">
                <PlayerAvatar id={x.player_id} name={x.name} team={x.team} size={28} /> {x.name} <TeamLogo team={x.team} height={12} />
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Panel({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-3xl border border-line bg-surface p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

function Legend({ players }: { players: { name: string; team: string | null }[] }) {
  return (
    <div className="flex flex-wrap gap-4 text-[13px]">
      {players.map((p, i) => <Name key={p.name + i} name={p.name} team={p.team} i={i} bold={false} />)}
    </div>
  );
}

/** 능력 비교 — 능력마다 선수별 막대(이긴 선수는 진하게), 오른쪽 「○○ 우세」 · 「비슷해요」.
 *  같은 비교 무리면 백분위로(차이 5 미만은 비슷해요), 선발 · 불펜이 섞이면 무리가 달라 실제 값으로 판정한다 */
function Abilities({ data, n }: { data: ComparePlayer[]; n: number | null }) {
  const keys = data[0]?.axes.map((a) => a.key) ?? [];
  const mixed = new Set(data.map((p) => p.role ?? "batter")).size > 1;
  return (
    <div className="mt-6">
      <Panel title="능력 비교" right={<Legend players={data} />}>
        <ul className="divide-y divide-line">
          {keys.map((key) => {
            const copy = axisCopy(key);
            const cells = data.map((p) => p.axes.find((a) => a.key === key));
            const scored = mixed
              ? cells.map((c, i) => ({ i, p: c?.value == null ? null : c.reverse ? -c.value : c.value })).filter((x) => x.p != null).sort((a, b) => b.p! - a.p!)
              : cells.map((c, i) => ({ i, p: c?.percentile ?? null })).filter((x) => x.p != null).sort((a, b) => b.p! - a.p!);
            const win = scored.length >= 2 ? (scored[0].p! - scored[1].p! < (mixed ? Number.EPSILON : CLOSE) ? null : scored[0].i) : null;
            return (
              <li key={key} className="grid items-center gap-4 py-4 md:grid-cols-[180px_minmax(0,1fr)_96px]">
                <div>
                  <p className="text-[15px] font-bold">{cells[0]?.label ?? copy?.chip}</p>
                  <p className="mt-0.5 text-xs text-fg-2">{copy?.sub}</p>
                </div>
                <div className="space-y-2">
                  {cells.map((c, i) => {
                    const size = n ?? data[i].group_size ?? 0;
                    const pos = c?.percentile != null && c.rank != null ? leaguePosition(c.percentile, c.rank, size) : null;
                    return (
                      <div key={i} className="grid grid-cols-[96px_minmax(0,1fr)_118px_52px] items-center gap-3 text-[13px]">
                        <Name name={data[i].name} team={data[i].team} bold={false} />
                        {c?.percentile != null ? (
                          <span className="h-2 overflow-hidden rounded-full bg-surface-3">
                            <span className="block h-full rounded-full" style={{ width: `${c.percentile}%`, background: SERIES[i], opacity: win == null || win === i ? 1 : 0.45 }} />
                          </span>
                        ) : (
                          <span className="text-xs text-muted">비교 대상 아님</span>
                        )}
                        <span className="font-bold">{pos ? `${pos.side} ${pos.pct}% · ${c!.rank}위` : ""}</span>
                        <span className="text-right font-num text-xs text-fg-2">{copy?.fmt(c?.value ?? null) ?? "–"}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="md:text-right">
                  {scored.length >= 2 && (
                    <span className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-bold"
                          style={{ background: win == null ? "var(--surface-2)" : tint(win) } as CSSProperties}>
                      {win != null && <span className="h-1.5 w-1.5 rounded-full" style={{ background: SERIES[win] }} aria-hidden />}
                      {win == null ? "비슷해요" : `${data[win].name} 우세`}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </Panel>
    </div>
  );
}

/** 기록 비교 — 좋은 쪽 숫자를 굵게 (타석 · 등판처럼 많이 뛴 정도는 비교하지 않음) */
function Stats({ players, rows }: { players: ComparePlayer[]; rows: Row[] }) {
  const cols = { gridTemplateColumns: `minmax(0,1fr) repeat(${players.length}, minmax(0,1fr))` };
  return (
    <Panel title="기록 비교">
      <div className="grid items-center gap-3 border-b border-line pb-3 text-[13px]" style={cols}>
        <span />
        {players.map((p, i) => <span key={p.player_id} className="flex justify-end"><Name name={p.name} team={p.team} i={i} /></span>)}
      </div>
      {rows.map((r) => {
        const vals = players.map((p) => (p.stats ? r.get(p.stats) : null));
        const known = vals.filter((v): v is number => v != null);
        const best = r.better && known.length >= 2 ? (r.better === "high" ? Math.max(...known) : Math.min(...known)) : null;
        return (
          <div key={r.label} className="grid items-center gap-3 border-b border-line py-2.5 last:border-0" style={cols}>
            <span className="text-[13px] text-fg-2">{r.label}</span>
            {vals.map((v, i) => (
              <span key={i} className={`text-right font-display text-[22px] leading-none ${v != null && v === best ? "font-extrabold" : "font-semibold text-fg-2"}`}>{r.fmt(v)}</span>
            ))}
          </div>
        );
      })}
    </Panel>
  );
}

/** 장면으로 비교 — 각자 대표 장면(타자 최근 홈런 · 투수 등판 장면, 선수 화면 머리와 같은 규칙). 누르면 패널 아래에서 재생 */
function Scenes({ ids, summaries, role, names }: { ids: string[]; summaries: (PlayerSummary | undefined)[]; role: Role; names: string[] }) {
  const [playing, setPlaying] = useState<(Playing & { id: string }) | null>(null);
  return (
    <Panel title="장면으로 비교">
      <p className="-mt-2 mb-4 text-xs text-fg-2">{role === "pitcher" ? "가장 최근 등판 장면" : "가장 최근 홈런 장면"}</p>
      <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${ids.length}, minmax(0,1fr))` }}>
        {ids.map((id, i) => {
          const p = summaries[i];
          const s = p ? representative(p, role) : null;
          return (
            <div key={id} className="min-w-0">
              {s ? (
                <button onClick={() => setPlaying(playing?.id === id ? null : { id, clip: s.clip, title: `${p!.name} · ${s.title}`, sub: s.sub })}
                        aria-current={playing?.id === id ? "true" : undefined} className="group block w-full text-left aria-[current=true]:opacity-60">
                  <span className="relative block aspect-video overflow-hidden rounded-xl bg-night">
                    <img src={thumbnailUrl(s.clip.videoId)} alt="" className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]" loading="lazy" />
                    <span className="absolute bottom-2 left-2 flex items-center gap-1 rounded-md bg-black/75 px-1.5 py-0.5 font-num text-[11px] font-semibold text-white">
                      <PlayGlyph size={7} /> {mmss(clipLength(s.clip))}
                    </span>
                  </span>
                  <span className="mt-2 block text-[13px]"><Name name={`${names[i]} · ${s.title}`} team={p?.team} i={i} /></span>
                  <span className="mt-0.5 block truncate text-xs text-fg-2">{s.sub}</span>
                </button>
              ) : (
                <div className="flex aspect-video items-center justify-center rounded-xl bg-surface-2 text-xs text-muted">{p ? "장면이 아직 없어요" : ""}</div>
              )}
            </div>
          );
        })}
      </div>
      {playing && <InlinePlayer playing={playing} onClose={() => setPlaying(null)} className="mt-5" />}
    </Panel>
  );
}
