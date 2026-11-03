"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ApiError, getMissingHr, markManual, markNoVideo, qk, type Clip, type MissingHr } from "@/lib/api";
import ScenePlayer from "@/components/ScenePlayer";
import { mmss } from "@/components/ui/Media";

// 수동 표시 (FR-08-03 · NFR-06): 장면이 없는 홈런을 경기 하이라이트에서 찾아 그 순간을 표시한다.
// Gemini 제안(etl/09_suggest_times.py)이 있으면 그 구간이 채워진 채 열리고, 사람은 끝까지 보고 확정한다 (장면.md 11-5)
const SEASONS = [2026, 2025, 2024];
const KIND: Record<number, string> = { 1: "솔로", 2: "투런", 3: "스리런", 4: "만루" };
const LEN = 20; // 기본 구간 길이(초) — API 12-2 기본값과 같다
type Filter = "all" | "suggested" | "absent";

export default function ManualQueue({ reviewer, canSave }: { reviewer: string; canSave: boolean }) {
  const qc = useQueryClient();
  const [season, setSeason] = useState(SEASONS[0]);
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);
  const q = useQuery({ queryKey: qk.missingHr(season), queryFn: () => getMissingHr(season), placeholderData: keepPreviousData });
  const after = () => {
    qc.invalidateQueries({ queryKey: ["missingHr"] });
    qc.invalidateQueries({ queryKey: qk.reviewStats() });
    setOpen(null);
  };
  const mark = useMutation({ mutationFn: markManual, onSuccess: after });
  const none = useMutation({ mutationFn: markNoVideo, onSuccess: after });
  const err = (mark.error ?? none.error) as Error | null;

  if (q.error instanceof ApiError && q.error.status === 401)
    return <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">관리자 토큰을 입력해 주세요.</p>;
  if (q.isError) return <p className="text-muted">수동 표시 목록을 불러오지 못했습니다.</p>;
  if (!q.data) return <p className="text-muted">불러오는 중…</p>;

  const { goal, items } = q.data;
  const left = Math.max(0, goal.target - goal.done);
  const suggested = items.filter((it) => it.suggestion?.found);
  const absent = items.filter((it) => it.suggestion && !it.suggestion.found);
  const shown = filter === "suggested" ? suggested : filter === "absent" ? absent : items;
  return (
    <div className="space-y-4">
      {/* 홈런 장면 목표 (NFR-06) */}
      <section className="rounded-xl border border-line bg-surface p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-sm font-semibold">
            {season} 홈런 장면 <span className="tabular-nums">{goal.done} / {goal.total}</span>
            <span className="ml-1 text-muted">({Math.round((goal.done / goal.total) * 100)}%)</span>
          </p>
          <p className="text-xs text-muted">
            목표 {Math.round(goal.rate * 100)}% = {goal.target}개 · {left ? `${left}개 남음` : "달성"} · 장면 없는 홈런 {q.data.total}개
          </p>
        </div>
        <div className="relative mt-2 h-2 rounded-full bg-surface-3" aria-hidden>
          <span className="absolute inset-y-0 left-0 rounded-full bg-brand" style={{ width: `${(goal.done / goal.total) * 100}%` }} />
          <span className="absolute -inset-y-1 w-0.5 bg-fg" style={{ left: `${goal.rate * 100}%` }} title="목표" />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          {SEASONS.map((s) => (
            <button key={s} onClick={() => { setSeason(s); setOpen(null); }} aria-pressed={season === s}
              className={`rounded-full border px-3 py-1 ${season === s ? "border-fg bg-fg text-bg" : "border-line bg-surface text-muted hover:text-fg"}`}>
              {s}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-line" aria-hidden />
          {([["all", `전체 ${items.length}`], ["suggested", `Gemini 제안 ${suggested.length}`], ["absent", `Gemini: 하이라이트에 없음 ${absent.length}`]] as const).map(([k, label]) => (
            <button key={k} onClick={() => { setFilter(k); setOpen(null); }} aria-pressed={filter === k}
              className={`rounded-full border px-3 py-1 ${filter === k ? "border-fg bg-fg text-bg" : "border-line bg-surface text-muted hover:text-fg"}`}>
              {label}
            </button>
          ))}
        </div>
      </section>

      {err && <p className="text-sm text-red-600">저장하지 못했습니다: {err.message}</p>}
      {shown.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">해당하는 홈런이 없습니다.</p>
      ) : (
        <ul className="space-y-2">
          {shown.map((it) => (
            <Row key={it.pa_id} it={it} open={open === it.pa_id} onToggle={() => setOpen(open === it.pa_id ? null : it.pa_id)}
              busy={mark.isPending || none.isPending} canSave={canSave}
              onMark={(videoId, start, end, suggestedSec) => mark.mutate({ pa_id: it.pa_id, video_id: videoId, start_sec: start, end_sec: end, reviewer, suggested_sec: suggestedSec })}
              onNone={() => none.mutate({ pa_id: it.pa_id, reviewer })} />
          ))}
        </ul>
      )}
    </div>
  );
}

function situation(it: MissingHr) {
  const bases = [it.on_1b && "1", it.on_2b && "2", it.on_3b && "3"].filter(Boolean);
  return [
    bases.length ? `주자 ${bases.join("·")}루` : "주자 없음",
    it.outs != null && `${it.outs}아웃`,
    it.balls != null && it.strikes != null && `${it.balls}-${it.strikes}`,
  ].filter(Boolean).join(" · ");
}

function Row({ it, open, busy, canSave, onToggle, onMark, onNone }: {
  it: MissingHr; open: boolean; busy: boolean; canSave: boolean;
  onToggle: () => void; onMark: (videoId: string, start: number, end: number, suggestedSec?: number) => void; onNone: () => void;
}) {
  const s = it.suggestion?.found && it.suggestion.start_sec != null ? it.suggestion : null;
  // 제안이 있으면 그 영상(하이라이트 2등일 수도 있다), 없으면 화면이 쓰는 1등 하이라이트
  const v = s ?? it.highlight;
  const now = useRef<(() => number) | null>(null);
  const [start, setStart] = useState<number | null>(s?.start_sec ?? null);
  const [end, setEnd] = useState<number | null>(s?.end_sec ?? null);
  const [preview, setPreview] = useState(!!s);
  // 자동화 편향 방지: 제안 구간은 끝까지 재생해 봐야 저장할 수 있다. 직접 「지금 시각」을 찍으면 풀린다
  const [watched, setWatched] = useState(!s);
  const clip: Clip | null = v && {
    videoId: v.video_id, title: v.title, durationSec: v.duration_sec, precision: preview ? "scene" : "game",
    startSec: preview && start != null ? start : 0, endSec: preview && end != null ? end : v.duration_sec,
  };
  const capture = () => {
    const t = Math.floor(now.current?.() ?? 0);
    setStart(t);
    setEnd(Math.min(t + LEN, v?.duration_sec ?? t + LEN));
    setPreview(false);
    setWatched(true);
  };
  const num = (x: string) => (x.trim() === "" || Number.isNaN(Number(x)) ? null : Math.max(0, Math.floor(Number(x))));
  const valid = start != null && end != null && end > start;

  return (
    <li className="rounded-xl border border-line bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="w-20 shrink-0 tabular-nums text-muted">{it.date}</span>
        <span className="font-semibold">
          {it.batter} {it.hr_seq != null && `${it.hr_seq}호 `}{KIND[it.runs] ?? ""} 홈런 · {it.inning}회{it.half}
        </span>
        <span className="text-xs text-muted">{it.game} · 투수 {it.pitcher} · {situation(it)}</span>
        {it.has_pending && <span className="rounded-full border border-accent px-2 py-0.5 text-xs font-semibold">검수 대기 연결 있음</span>}
        {s && (
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${s.strength === "strong" ? "bg-brand text-white" : "border border-brand text-brand-text"}`}
                title={`근거: 이름${s.checks ? ` · ${s.checks}` : ""}${s.evidence ? ` (${s.evidence})` : ""} · ${s.model ?? ""}`}>
            Gemini {mmss(s.t_sec)} · {s.strength === "strong" ? "근거 강함" : "근거 약함"}
          </span>
        )}
        {it.suggestion && !it.suggestion.found && (
          <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted">Gemini: 하이라이트에 없음</span>
        )}
        <span className="ml-auto flex gap-2">
          {v ? (
            <button onClick={onToggle} aria-expanded={open}
              className="rounded-lg border border-line px-3 py-1 text-xs font-semibold hover:bg-surface-2">
              {open ? "닫기" : s ? "제안 확인" : `하이라이트에서 찾기 ${mmss(v.duration_sec)}`}
            </button>
          ) : (
            <span className="self-center text-xs text-muted">경기 하이라이트 없음</span>
          )}
          <button disabled={busy || !canSave} onClick={onNone}
            className="rounded-lg border border-line px-3 py-1 text-xs font-semibold disabled:opacity-40">영상에 없음</button>
        </span>
      </div>

      {open && clip && v && (
        <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_260px]">
          <div className="aspect-video overflow-hidden rounded-lg bg-night">
            <ScenePlayer bare clip={clip} label={v.title} onReady={(f) => { now.current = f; }}
              onEnded={() => { if (preview) setWatched(true); }} />
          </div>
          <div className="space-y-2 text-xs">
            <p className="text-muted" title={v.title}>[{v.channel}] {v.title}</p>
            {s && (
              <p className="rounded-lg bg-surface-2 p-2">
                Gemini 제안 {mmss(s.start_sec)}~{mmss(s.end_sec)} (타격 {mmss(s.t_sec)}) · 근거 이름{s.checks && ` · ${s.checks}`}
                {s.strength === "weak" && " — 근거가 약하니 타자 · 이닝을 꼭 확인하세요"}
              </p>
            )}
            <button onClick={capture} className="w-full rounded-lg bg-fg px-3 py-2 text-sm font-semibold text-bg">지금 시각으로 시작 표시</button>
            <div className="flex items-center gap-1">
              <input value={start ?? ""} onChange={(e) => setStart(num(e.target.value))} inputMode="numeric" aria-label="시작 초"
                className="w-16 rounded border border-line bg-surface px-1.5 py-1 tabular-nums" placeholder="시작" />
              ~
              <input value={end ?? ""} onChange={(e) => setEnd(num(e.target.value))} inputMode="numeric" aria-label="종료 초"
                className="w-16 rounded border border-line bg-surface px-1.5 py-1 tabular-nums" placeholder="종료" />
              <span className="text-muted tabular-nums">{valid && `${mmss(start)}~${mmss(end)}`}</span>
            </div>
            <div className="flex gap-2">
              <button disabled={!valid} onClick={() => setPreview(!preview)} aria-pressed={preview}
                className="flex-1 rounded-lg border border-line px-2 py-1 font-semibold disabled:opacity-40">
                {preview ? "하이라이트 처음부터" : "구간 미리 보기"}
              </button>
              <button disabled={!valid || !watched || busy || !canSave} onClick={() => valid && onMark(v.video_id, start, end, s?.start_sec ?? undefined)}
                className="flex-1 rounded-lg bg-brand px-2 py-1 font-semibold text-white disabled:opacity-40">이 구간으로 표시</button>
            </div>
            {!watched && <p className="text-muted">제안 구간을 끝까지 보면 표시할 수 있어요</p>}
            {!canSave && <p className="text-muted">검수자 이름을 먼저 적어 주세요</p>}
            <p className="text-muted">표시하면 바로 확정(승인) 장면이 되어 선수 화면에 나옵니다. 처음 {LEN}초가 기본 구간입니다.</p>
          </div>
        </div>
      )}
    </li>
  );
}
