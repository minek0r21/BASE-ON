"use client";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기: 썸네일 핫링크(설계 8-2) */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Fragment, useState, type ReactNode } from "react";
import type { Playing } from "@/components/home/DayScenes";
import { clipLength } from "@/components/home/common";
import InlinePlayer from "@/components/InlinePlayer";
import { thumbnailUrl } from "@/components/ScenePlayer";
import StageTag from "@/components/StageTag";
import { Empty } from "@/components/ui/Chip";
import { PlayGlyph, TeamLogo, mmss } from "@/components/ui/Media";
import { getOutingDetail, getPlayerOutings, qk, type OutingDetail, type OutingInning, type OutingPa, type OutingRow } from "@/lib/api";
import { innings, md } from "@/lib/format";
import { team as teamOf } from "@/lib/teams";

const RESULT_KO = { W: "승", L: "패", D: "무" } as const;
const KINDS = [["strikeout", "삼진"], ["on_base", "안타 · 사구"], ["out", "아웃"]] as const;
type Kind = (typeof KINDS)[number][0];

/**
 * 03b 투수 경기 기록 = 등판 상세 (Figma 155:2065) — 왼쪽 그 달 등판 목록(누르면 고름), 오른쪽 고른 등판의
 * 경기 머리 · 7칸 기록 · 이 등판의 장면 · 이닝별 상대 타자(API-30). 처음엔 그 달 가장 최근 등판. 고른 등판은 주소 ?outing=
 */
export default function OutingsTab({ playerId, playerName, season, month, outing, onChange, onPick }: {
  playerId: string;
  playerName: string;
  season: number | null;
  month: number | null;
  outing: string | null;
  onChange: (season: number | null, month: number | null) => void;
  onPick: (outingId: string) => void;
}) {
  const q = useQuery({
    queryKey: qk.outings(playerId, season, month),
    queryFn: ({ signal }) => getPlayerOutings(playerId, season, month, signal),
    placeholderData: keepPreviousData,
  });

  if (q.isPending) return <div className="h-[640px] animate-pulse rounded-3xl bg-surface-2" />;
  if (q.isError) return <Empty text="등판 기록을 불러오지 못했어요" action={{ label: "다시 시도", onClick: () => q.refetch() }} />;
  const d = q.data;
  if (!d.season || !d.outings.length) return <Empty text="등판 기록이 없어요" />;

  const picked = d.outings.find((o) => o.outingId === outing)?.outingId ?? d.outings[0].outingId;
  const starts = d.outings.filter((o) => o.role === "선발").length;
  const sum = d.outings.reduce((a, o) => ({ outs: a.outs + o.line.outs, so: a.so + o.line.so }), { outs: 0, so: 0 });
  const sub = [`${d.month}월`, starts === d.outings.length ? `선발 ${starts}경기` : `${d.outings.length}경기`, `${innings(sum.outs)}이닝 ${sum.so}탈삼진`].join(" · ");

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
      <section className="overflow-hidden rounded-3xl border border-line bg-surface lg:sticky lg:top-32">
        <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-4">
          <div>
            <h2 className="text-xl font-bold">등판 경기</h2>
            <p className="mt-1 text-xs text-fg-2">{sub}</p>
          </div>
          <label>
            <span className="sr-only">월</span>
            <select value={d.month ?? ""} onChange={(e) => onChange(d.season, Number(e.target.value))}
                    className="h-9 rounded-full border border-line bg-surface px-3 text-[13px] font-bold">
              {d.months.map((m) => <option key={m} value={m}>{m}월</option>)}
            </select>
          </label>
        </div>
        <ul className="border-t border-line">
          {d.outings.map((o) => <OutingItem key={o.outingId} o={o} on={o.outingId === picked} onClick={() => onPick(o.outingId)} />)}
        </ul>
        <p className="border-t border-line px-5 py-3 text-[11px] text-fg-2">장면 = 투구만 모은 영상 · 경기 = 경기 하이라이트</p>
      </section>
      <Detail key={picked} id={picked} playerName={playerName} />
    </div>
  );
}

function OutingItem({ o, on, onClick }: { o: OutingRow; on: boolean; onClick: () => void }) {
  const l = o.line;
  return (
    <li className="border-b border-line last:border-0">
      <button onClick={onClick} aria-current={on ? "true" : undefined}
              className="relative flex w-full items-center gap-3 px-5 py-3.5 text-left hover:bg-surface-2 aria-[current=true]:bg-surface-2">
        {on && <span className="absolute inset-y-0 left-0 w-1 bg-(--team)" aria-hidden />}
        <span className="w-11 shrink-0 text-center">
          <span className="block font-num text-[15px] font-bold">{md(o.date)}</span>
          <span className="block text-[11px] text-fg-2">{o.weekday}</span>
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5 text-sm font-bold">
            <TeamLogo team={o.opponent} height={14} />
            <span className="truncate">{o.opponent} {o.home ? "홈" : "원정"} · {o.score.team}:{o.score.opponent}</span>
            <span className={`shrink-0 rounded px-1 py-px text-[10px] font-bold ${o.result === "W" ? "bg-(--team) text-white" : "bg-surface-3 text-fg-2"}`}>팀 {RESULT_KO[o.result]}</span>
          </span>
          <span className="mt-0.5 block truncate text-xs text-fg-2">
            {innings(l.outs)}이닝 {l.r === 0 ? "무실점" : `${l.r}실점`} · {l.so}탈삼진{o.role !== "선발" ? " · 구원" : ""}
          </span>
        </span>
        {(o.scene || o.highlight) && (
          <span className={`flex h-6 shrink-0 items-center gap-1 rounded-full px-2 text-[11px] font-bold ${o.scene ? "bg-accent text-white" : "border border-line text-fg-2"}`}>
            <PlayGlyph size={6} /> {o.scene ? "장면" : "경기"}
          </span>
        )}
      </button>
    </li>
  );
}

/** 고른 등판 — 경기 머리 · 7칸 기록 · 장면 카드 · 이닝별 상대 타자 */
function Detail({ id, playerName }: { id: string; playerName: string }) {
  const q = useQuery({ queryKey: qk.outingDetail(id), queryFn: ({ signal }) => getOutingDetail(id, signal) });
  const [playing, setPlaying] = useState<(Playing & { at: "head" | "scene" }) | null>(null);
  if (q.isError) return <Empty text="등판 상세를 불러오지 못했어요" action={{ label: "다시 시도", onClick: () => q.refetch() }} />;
  const d = q.data;
  if (!d) return <div className="h-[640px] animate-pulse rounded-3xl bg-surface-2" />;

  const stadium = teamOf(d.home ? d.team : d.opponent)?.home;
  const head = [`${d.date.replaceAll("-", ".")} (${d.weekday})`, `${d.home ? "홈" : "원정"}${stadium ? ` ${stadium}` : ""}`, d.stage_label ?? "정규시즌"].join(" · ");
  const l = d.line;
  const cells: [string, ReactNode][] = [
    ["이닝", innings(l.outs)], ["상대 타자", l.tbf], ["투구 수", l.pitches], ["탈삼진", l.so], ["피안타", l.h],
    ["볼넷 · 몸에 맞는 공", `${l.bb} · ${l.hbp}`], ["실점", l.r],
  ];

  return (
    <div className="min-w-0 space-y-5">
      <section className="rounded-3xl border border-line bg-surface p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-xs text-fg-2">{head} <StageTag label={d.stage_label} /></p>
            <p className="mt-2 flex items-center gap-3 font-display text-[40px] leading-none font-extrabold">
              <TeamLogo team={d.team} height={30} /> {d.team} {d.score.team} : {d.score.opponent} {d.opponent} <TeamLogo team={d.opponent} height={30} />
              <span className={`ml-1 rounded-md px-2 py-0.5 font-sans text-xs font-bold ${d.result === "W" ? "bg-(--team) text-white" : "bg-surface-3 text-fg-2"}`}>팀 {RESULT_KO[d.result]}</span>
            </p>
            <p className="mt-2 text-sm font-bold">{playerName} · {d.role} · {innings(l.outs)}이닝 {l.r === 0 ? "무실점" : `${l.r}실점`}</p>
          </div>
          {d.highlight && (
            <div className="text-right">
              <button onClick={() => setPlaying(playing?.at === "head" ? null : { at: "head", clip: d.highlight!, title: `${md(d.date)} ${d.opponent}전 하이라이트`, sub: d.highlightChannel ?? undefined })}
                      aria-expanded={playing?.at === "head"}
                      className="flex h-9 items-center gap-1.5 rounded-full border border-line bg-surface px-4 text-[13px] font-bold hover:border-accent hover:bg-accent hover:text-white aria-expanded:border-accent aria-expanded:bg-accent aria-expanded:text-white">
                <PlayGlyph size={8} /> 이 경기 하이라이트 {mmss(clipLength(d.highlight))}
              </button>
              {d.highlightChannel && <p className="mt-1.5 text-[11px] text-fg-2">{d.highlightChannel} · 경기 전체 영상</p>}
            </div>
          )}
        </div>
        <dl className="mt-5 grid grid-cols-4 gap-y-4 md:grid-cols-[1fr_1fr_1fr_1fr_1fr_1.7fr_1fr] md:divide-x md:divide-line">
          {cells.map(([k, v]) => (
            <div key={k} className="min-w-0 md:px-4 md:first:pl-0">
              <dt className="truncate text-xs text-fg-2" title={k}>{k}</dt>
              <dd className="mt-1 font-display text-[28px] leading-none font-extrabold">{v}</dd>
            </div>
          ))}
        </dl>
        {playing?.at === "head" && <InlinePlayer playing={playing} onClose={() => setPlaying(null)} className="mt-5" />}
      </section>

      {d.scene && <SceneCard d={d} playerName={playerName} playing={playing?.at === "scene" ? playing : null}
                             onPlay={(p) => setPlaying(p ? { ...p, at: "scene" } : null)} />}

      <Innings d={d} />
    </div>
  );
}

function SceneCard({ d, playerName, playing, onPlay }: { d: OutingDetail; playerName: string; playing: Playing | null; onPlay: (p: Playing | null) => void }) {
  const s = d.scene!;
  const kind = s.precision === "scene" ? "투구 장면" : "이닝 장면";
  const title = `${md(d.date)} ${d.opponent}전 · ${kind}`;
  return (
    <section className="rounded-3xl border border-line bg-surface p-6">
      <div className="grid items-center gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <button onClick={() => onPlay(playing ? null : { clip: s, title: `${playerName} · ${title}`, sub: s.title })} aria-label={`${title} 재생`}
                className="group relative block aspect-video overflow-hidden rounded-2xl bg-night">
          <img src={thumbnailUrl(s.videoId)} alt="" className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]" />
          <span className="absolute bottom-3 left-3 flex items-center gap-1 rounded-md bg-black/75 px-2 py-1 font-num text-xs font-semibold text-white">
            <PlayGlyph size={8} /> {mmss(clipLength(s))}
          </span>
        </button>
        <div>
          <p className="text-xs font-bold text-fg-2">이 등판의 장면</p>
          <p className="mt-1.5 text-[22px] font-bold">{title}</p>
          <p className="mt-2 line-clamp-2 text-[13px] text-fg-2">{s.title}</p>
          <button onClick={() => onPlay(playing ? null : { clip: s, title: `${playerName} · ${title}`, sub: s.title })}
                  className="mt-4 flex h-9 items-center gap-1.5 rounded-full bg-accent px-4 text-[13px] font-bold text-white hover:brightness-95">
            <PlayGlyph size={8} /> {playing ? "닫기" : `장면 재생 ${mmss(clipLength(s))}`}
          </button>
        </div>
      </div>
      {playing && <InlinePlayer playing={playing} onClose={() => onPlay(null)} className="mt-5" />}
    </section>
  );
}

/** 「3안타 1볼넷 2삼진 1실점」 — 사사구 같은 줄임말 대신 풀어 쓴다 */
function innSummary(s: OutingInning["summary"]) {
  return [s.h && `${s.h}안타`, s.bb && `${s.bb}볼넷`, s.hbp && `몸에 맞는 공 ${s.hbp}`, s.so && `${s.so}삼진`, s.runs && `${s.runs}실점`].filter(Boolean).join(" ") || "삼자범퇴";
}

/** 이닝별 상대 타자 — 칩 하나가 한 타석, 고른 결과(삼진 · 안타·사구 · 아웃)는 진하게. 칩을 누르면 그 타석 상황이 그 이닝 아래에 */
function Innings({ d }: { d: OutingDetail }) {
  const [kind, setKind] = useState<Kind>("strikeout");
  const [open, setOpen] = useState<string | null>(null);
  return (
    <section className="rounded-3xl border border-line bg-surface p-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-xl font-bold">이닝별 상대 타자 {d.line.tbf}명</h3>
        <div className="flex gap-2" role="group" aria-label="강조할 결과">
          {KINDS.map(([k, label]) => (
            <button key={k} onClick={() => setKind(k)} aria-pressed={kind === k}
                    className="h-8 rounded-full border border-line bg-surface px-3.5 text-xs font-bold hover:bg-surface-2 aria-pressed:border-fg aria-pressed:bg-fg aria-pressed:text-bg">
              {label}
            </button>
          ))}
        </div>
      </div>
      <ul className="divide-y divide-line">
        {d.innings.map((inn) => {
          const sel = inn.plate_appearances.find((p) => p.pa_id === open);
          return (
            <li key={`${inn.inning}-${inn.inning_half}`} className="py-3">
              <div className="grid grid-cols-[48px_minmax(0,1fr)_auto] items-center gap-3">
                <span>
                  <span className="block text-[15px] font-bold">{inn.inning}회</span>
                  <span className="block text-[11px] text-fg-2">{inn.summary.batters}타자</span>
                </span>
                <span className="flex flex-wrap gap-1.5">
                  {inn.plate_appearances.map((p) => (
                    <Fragment key={p.pa_id}>
                      <PaChip p={p} hot={p.kind === kind} on={open === p.pa_id} onClick={() => setOpen(open === p.pa_id ? null : p.pa_id)} />
                    </Fragment>
                  ))}
                </span>
                <span className="text-right text-xs text-fg-2">{innSummary(inn.summary)}</span>
              </div>
              {sel && <PaDetail p={sel} />}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function PaChip({ p, hot, on, onClick }: { p: OutingPa; hot: boolean; on: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} aria-expanded={on}
            className={`flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs ${hot ? "border-fg bg-fg text-bg" : "border-line bg-surface hover:bg-surface-2"} aria-expanded:ring-2 aria-expanded:ring-(--team) aria-expanded:ring-offset-1`}>
      <span className="font-bold">{p.batter.name}</span>
      <span className={hot ? "opacity-80" : "text-fg-2"}>{p.events_ko}</span>
      {!!p.runs_scored && <span className={`rounded px-1 text-[10px] font-bold ${hot ? "bg-bg/20" : "bg-surface-3"}`}>{p.runs_scored}점</span>}
    </button>
  );
}

const OUTS = ["무사", "1사", "2사"];
/** 그 타석 상황 — 아웃 · 주자 · 볼카운트 · 투구 수 · 마지막 공 */
function PaDetail({ p }: { p: OutingPa }) {
  const bases = [p.runners.on_1b && "1루", p.runners.on_2b && "2루", p.runners.on_3b && "3루"].filter(Boolean) as string[];
  const items = [
    p.outs != null && OUTS[p.outs],
    bases.length ? `주자 ${bases.join(" · ")}` : "주자 없음",
    p.count.balls != null && p.count.strikes != null && `볼카운트 ${p.count.balls}-${p.count.strikes}`,
    p.pitches != null && `${p.pitches}구`,
    p.last_pitch.name && `마지막 공 ${p.last_pitch.name}${p.last_pitch.speed_kmh ? ` ${Math.round(p.last_pitch.speed_kmh)}km/h` : ""}`,
    !!p.runs_scored && `${p.runs_scored}점 내줌`,
  ].filter(Boolean) as string[];
  return (
    <p className="mt-2 ml-[60px] rounded-xl bg-surface-2 px-3.5 py-2.5 text-xs">
      <b className="mr-2">{p.batter.name} · {p.events_ko}</b>
      <span className="text-fg-2">{items.join(" · ")}</span>
    </p>
  );
}
