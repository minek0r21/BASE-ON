"use client";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기: 썸네일 핫링크(설계 8-2) */
import { useQuery } from "@tanstack/react-query";
import { Fragment, useRef, useState, type ReactNode, type Ref } from "react";
import type { Playing } from "@/components/home/DayScenes";
import { SectionHead, clipLength } from "@/components/home/common";
import InlinePlayer from "@/components/InlinePlayer";
import { thumbnailUrl } from "@/components/ScenePlayer";
import { Chip, Empty } from "@/components/ui/Chip";
import { PlayGlyph, mmss } from "@/components/ui/Media";
import { getPitcherOutings, getPlayerScenes, qk, type Clip, type OutingRow, type PlayerPaScene } from "@/lib/api";
import { josa } from "@/lib/abilities";
import { innings, md } from "@/lib/format";

const HR_RUNS = ["", "솔로", "투런", "스리런", "만루"];
const OUTS = ["무사", "1사", "2사"];
const EVENT_KO: Record<string, string> = { single: "안타", double: "2루타", triple: "3루타", walk: "볼넷", hit_by_pitch: "몸에 맞는 공" };

/**
 * 03 「장면」 (Figma 138:645) — 이 타자의 확정 장면(잘한 것만, 장면.md S8) 최신순. 거르기: 전체 · 홈런 · 안타 · 볼넷.
 * 누르면 그 자리에서 재생 (별도 창 없음). 제목은 우리 기록으로 만든다 (「30호 · 솔로 홈런」)
 * 개요는 06 팀 「최근 장면」과 같은 4열 카드, 장면 탭(all)은 전부 줄 목록
 */
export function BatterScenes({ id, name, season, all, kind, onKind, onGames }: {
  id: string; name: string; season: number; all?: boolean;
  kind: "all" | "home_run" | "on_base"; onKind: (k: "all" | "home_run" | "on_base") => void; onGames?: () => void;
}) {
  const q = useQuery({ queryKey: qk.playerScenes(id, season, "batter"), queryFn: ({ signal }) => getPlayerScenes(id, season, signal) });
  const c = q.data?.counts;
  const rows = (q.data?.scenes ?? []).filter((s) => kind === "all" || s.kind === kind);
  return (
    <ListShell
      title="장면"
      sub={c && `장면 ${c.scenes}개 · 홈런 ${c.home_runs}개 중 ${c.home_run_scenes}개는 영상 있음 · 최신순`}
      chips={c && [
        { key: "all", label: "전체", n: c.scenes },
        { key: "home_run", label: "홈런", n: c.home_run_scenes },
        { key: "on_base", label: "안타 · 볼넷", n: c.on_base_scenes },
      ]}
      chip={kind}
      onChip={(k) => onKind(k as typeof kind)}
      loading={q.isPending}
      error={q.isError ? () => q.refetch() : null}
      empty={`${season} 시즌 장면이 아직 없어요`}
      none={c?.scenes === 0 ? {
        line: `장면 · 아직 없음${c.home_runs ? ` (홈런 ${c.home_runs}개)` : ""}`,
        sub: c.home_runs ? `홈런 ${c.home_runs}개 모두 아직 영상과 이어지지 않았어요.` : `${season} 시즌에 영상과 이어진 타석이 아직 없어요.`,
        action: onGames && { label: "경기 기록에서 경기 하이라이트 보기", onClick: onGames },
      } : undefined}
      all={all}
      rows={rows.map((s) => ({ key: s.paId, clip: s.clip, ...batterText(s, name) }))}
    />
  );
}

function batterText(s: PlayerPaScene, name: string) {
  const what = s.kind === "home_run"
    ? `${s.hrSeq ? `${s.hrSeq}호 · ` : ""}${HR_RUNS[s.runs ?? 0] ?? ""} 홈런`
    : `${EVENT_KO[s.events] ?? s.events}${s.runs ? ` · ${s.runs}타점` : ""}`;
  const full = s.count.balls === 3 && s.count.strikes === 2;
  const where = [`${md(s.date)} ${s.opponent}전`, `${s.inning}회${s.inningHalf}${s.outs != null ? ` ${OUTS[s.outs] ?? ""}` : ""}`, full && "풀카운트"]
    .filter(Boolean).join(" · ");
  return {
    tag: s.stage_label ?? "정규시즌",
    badge: s.kind === "home_run" ? (s.hrSeq ? `시즌 ${s.hrSeq}호` : "홈런") : (EVENT_KO[s.events] ?? s.events),
    title: what,
    lines: [where, `vs ${s.pitcher.name}`],
    playTitle: `${name} ${what}`,
    playSub: where,
  };
}

/**
 * 03b 「등판」 (Figma 139:1250) — 그 시즌 등판 전부(경기 하이라이트는 기본, 등판 장면이 있으면 그것). 거르기: 전체 · 무실점 · 7이닝 이상 · 장면 있음
 */
export function PitcherOutings({ id, name, season, all, kind, onKind, }: {
  id: string; name: string; season: number; all?: boolean;
  kind: "all" | "scoreless" | "seven_plus" | "scene"; onKind: (k: "all" | "scoreless" | "seven_plus" | "scene") => void;
}) {
  const q = useQuery({ queryKey: qk.playerScenes(id, season, "pitcher"), queryFn: ({ signal }) => getPitcherOutings(id, season, signal) });
  const c = q.data?.counts;
  const keep = (o: OutingRow) =>
    kind === "all" || (kind === "scoreless" && o.line.r === 0) || (kind === "seven_plus" && o.line.outs >= 21) || (kind === "scene" && !!o.scene);
  const rows = (q.data?.outings ?? []).filter(keep).filter((o) => o.scene || o.highlight);
  const starts = q.data?.outings.filter((o) => o.role === "선발").length ?? 0;
  return (
    <ListShell
      title="등판"
      sub={c && [`${starts === c.outings ? "선발 " : ""}${c.outings}경기`, `경기 영상 ${c.highlights}`, `투구 장면 ${c.scenes}`, "최신순"].join(" · ")}
      chips={c && [
        { key: "all", label: "전체", n: c.outings },
        { key: "scoreless", label: "무실점", n: c.scoreless },
        { key: "seven_plus", label: "7이닝 이상", n: c.seven_plus },
        { key: "scene", label: "장면 있음", n: c.scenes },
      ]}
      chip={kind}
      onChip={(k) => onKind(k as typeof kind)}
      loading={q.isPending}
      error={q.isError ? () => q.refetch() : null}
      empty={`${season} 시즌 등판 영상이 아직 없어요`}
      all={all}
      rows={rows.map((o) => ({ key: o.outingId, clip: (o.scene ?? o.highlight)!, ...outingText(o, name) }))}
    />
  );
}

function outingText(o: OutingRow, name: string) {
  const l = o.line;
  const title = `${innings(l.outs)}이닝 ${l.r === 0 ? "무실점" : `${l.r}실점`} · ${l.so}탈삼진`;
  const result = { W: "팀 승리", L: "팀 패배", D: "무승부" }[o.result];
  return {
    tag: o.scene ? "투구 장면" : "경기 영상",
    badge: o.scene ? "투구 장면" : "경기 영상",
    title,
    lines: [
      `${md(o.date)} ${o.opponent}전 (${o.home ? "홈" : "원정"}) · ${result} ${o.score.team}:${o.score.opponent} · ${l.pitches}구`,
      o.scene ? `${name} 등판 장면` : "이 경기 하이라이트 · 처음부터",
    ],
    playTitle: `${name} ${title}`,
    playSub: `${md(o.date)} ${o.opponent}전`,
  };
}

type Row = { key: string; clip: Clip; tag: string; badge: string; title: string; lines: string[]; playTitle: string; playSub: string };
type ChipDef = { key: string; label: string; n: number };
type None = { line: string; sub: string; action?: { label: string; onClick: () => void } };

function ListShell({ title, sub, chips, chip, onChip, loading, error, empty, none, all, rows }: {
  title: string; sub?: string; chips?: ChipDef[]; chip: string; onChip: (k: string) => void;
  loading: boolean; error: (() => void) | null; empty: string; none?: None; all?: boolean; rows: Row[];
}) {
  const [playing, setPlaying] = useState<(Playing & { key: string }) | null>(null);
  const scroller = useRef<HTMLUListElement>(null);
  const pick = (k: string) => { setPlaying(null); onChip(k); };
  const play = (r: Row) => setPlaying(playing?.key === r.key ? null : { key: r.key, clip: r.clip, title: r.playTitle, sub: r.playSub });

  // 장면이 하나도 없으면 크게 비우지 않고 장면 칸 자리에 한 줄만 (09 「선수에게 연결된 장면이 없을 때」 · 장면.md 6장)
  if (none && !error && !loading) return (
    <section className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-3xl border border-line bg-surface px-6 py-5 text-sm">
      <span className="font-bold">{none.line}</span>
      <span className="text-fg-2">{none.sub}</span>
      {none.action && (
        <button onClick={none.action.onClick} className="ml-auto flex h-9 items-center gap-1.5 rounded-full bg-surface-2 px-4 text-[13px] font-bold hover:bg-surface-3">
          <PlayGlyph size={6} /> {none.action.label}
        </button>
      )}
    </section>
  );

  let state: ReactNode = null;
  if (error) state = <Empty text={`${josa(title, "을", "를")} 불러오지 못했어요`} sub="잠시 뒤 다시 시도해 주세요." action={{ label: "다시 시도", onClick: error }} />;
  else if (loading) state = <div className="h-[460px] animate-pulse rounded-3xl bg-surface-2" />;
  else if (!rows.length && chips && chip !== chips[0].key) {
    state = <Empty text="고른 조건에 맞는 장면이 없어요" action={{ label: `${chips[0].label} 보기`, onClick: () => pick(chips[0].key) }} />;
  } else if (!rows.length) state = <Empty text={empty} />;

  const chipRow = chips && (
    <div className="flex flex-wrap gap-2" role="group" aria-label={`${title} 거르기`}>
      {chips.map((x) => (
        <Chip key={x.key} on={chip === x.key} onClick={() => pick(x.key)}>
          {x.label} <span className="font-num opacity-70">{x.n}</span>
        </Chip>
      ))}
    </div>
  );

  if (!all) return (
    <section className="min-w-0">
      <SectionHead title={title} sub={sub} right={
        <div className="flex flex-wrap items-center gap-2">
          {chipRow}
          {rows.length > 4 && ([-1, 1] as const).map((d) => (
            <button key={d} onClick={() => scroller.current?.scrollBy({ left: d * scroller.current.clientWidth * 0.75, behavior: "smooth" })}
                    aria-label={d < 0 ? "앞 장면" : "다음 장면"} className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface hover:bg-surface-2">
              {d < 0 ? "‹" : "›"}
            </button>
          ))}
        </div>
      } />
      {state ?? <Carousel ref={scroller} rows={rows} playingKey={playing?.key ?? null} onPlay={play} />}
      {playing && <InlinePlayer playing={playing} onClose={() => setPlaying(null)} className="mt-5" />}
    </section>
  );

  return (
    <section className="min-w-0">
      <SectionHead title={title} sub={sub} />
      {chipRow}
      {state ?? (
        <ul className="mt-3 -mx-2.5 animate-appear">
          {rows.map((r) => (
            <Fragment key={r.key}>
              <SceneRow row={r} on={playing?.key === r.key} onPlay={() => play(r)} />
              {playing?.key === r.key && <li><InlinePlayer playing={playing} onClose={() => setPlaying(null)} className="my-2" /></li>}
            </Fragment>
          ))}
        </ul>
      )}
    </section>
  );
}

function SceneRow({ row, on, onPlay }: { row: Row; on: boolean; onPlay: () => void }) {
  return (
    <li>
      <button onClick={onPlay} aria-expanded={on} className="group flex w-full items-center gap-4 rounded-2xl p-2.5 text-left hover:bg-surface aria-expanded:bg-surface">
        <span className="relative block aspect-video w-[152px] shrink-0 overflow-hidden rounded-xl bg-night">
          <img src={thumbnailUrl(row.clip.videoId)} alt="" className="h-full w-full object-cover" loading="lazy" />
          <span className="absolute right-2 bottom-2 rounded bg-black/70 px-1.5 py-0.5 font-num text-[11px] font-bold text-white">{mmss(clipLength(row.clip))}</span>
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] font-bold text-fg-2">{row.tag}</span>
            <span className="truncate text-[17px] font-bold">{row.title}</span>
          </span>
          <span className="mt-1 block truncate text-sm text-fg-2">{row.lines[0]}</span>
          <span className="mt-0.5 block truncate text-xs text-muted">{row.lines[1]}</span>
        </span>
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-line bg-surface group-hover:border-accent group-hover:bg-accent group-hover:text-white group-aria-expanded:border-accent group-aria-expanded:bg-accent group-aria-expanded:text-white">
          <PlayGlyph size={11} />
        </span>
      </button>
    </li>
  );
}

/** 06 팀 「최근 장면」과 같은 4열 카드 — 옆으로 넘긴다 */
function Carousel({ ref, rows, playingKey, onPlay }: { ref: Ref<HTMLUListElement>; rows: Row[]; playingKey: string | null; onPlay: (r: Row) => void }) {
  return (
    <ul ref={ref} className="animate-appear flex snap-x gap-4 overflow-x-auto pb-2 [scrollbar-width:none]">
      {rows.map((r) => (
        <li key={r.key} className="w-[calc((100%-48px)/4)] min-w-[220px] shrink-0 snap-start">
          <button onClick={() => onPlay(r)} aria-current={playingKey === r.key ? "true" : undefined} className="group block w-full text-left aria-[current=true]:opacity-50">
            <span className="relative block aspect-video overflow-hidden rounded-xl bg-night">
              <img src={thumbnailUrl(r.clip.videoId)} alt="" className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]" loading="lazy" />
              <span className="absolute top-2 left-2 rounded-md bg-black/75 px-1.5 py-0.5 text-[11px] font-bold text-white">{r.badge}</span>
              <span className="absolute bottom-2 left-2 flex items-center gap-1 rounded-md bg-black/75 px-1.5 py-0.5 font-num text-[11px] font-semibold text-white">
                <PlayGlyph size={7} /> {mmss(clipLength(r.clip))}
              </span>
            </span>
            <span className="mt-2.5 block truncate text-[15px] font-bold group-hover:underline">{r.title}</span>
            <span className="mt-1 block truncate text-xs text-fg-2">{r.lines[0]}</span>
            <span className="mt-0.5 block truncate text-xs text-muted">{r.lines[1]}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
