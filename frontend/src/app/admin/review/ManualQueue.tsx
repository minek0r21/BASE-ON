"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ApiError, getMissingHr, markManual, markNoVideo, qk, type Clip, type MissingHr } from "@/lib/api";
import ScenePlayer from "@/components/ScenePlayer";
import { mmss } from "@/components/ui/Media";

// 수동 표시 (FR-08-03 · NFR-06): 장면이 없는 홈런을 경기 하이라이트에서 찾아 그 순간을 표시한다
const SEASONS = [2026, 2025, 2024];
const KIND: Record<number, string> = { 1: "솔로", 2: "투런", 3: "스리런", 4: "만루" };
const LEN = 20; // 기본 구간 길이(초) — API 12-2 기본값과 같다

export default function ManualQueue({ reviewer, canSave }: { reviewer: string; canSave: boolean }) {
  const qc = useQueryClient();
  const [season, setSeason] = useState(SEASONS[0]);
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
          <span className="text-muted">최근 경기부터 · 하이라이트를 틀어 그 타석이 시작되는 순간에 「지금 시각」을 누르세요</span>
        </div>
      </section>

      {err && <p className="text-sm text-red-600">저장하지 못했습니다: {err.message}</p>}
      {items.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">장면 없는 홈런이 없습니다.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((it) => (
            <Row key={it.pa_id} it={it} open={open === it.pa_id} onToggle={() => setOpen(open === it.pa_id ? null : it.pa_id)}
              busy={mark.isPending || none.isPending} canSave={canSave}
              onMark={(start, end) => it.highlight && mark.mutate({ pa_id: it.pa_id, video_id: it.highlight.video_id, start_sec: start, end_sec: end, reviewer })}
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
  onToggle: () => void; onMark: (start: number, end: number) => void; onNone: () => void;
}) {
  const now = useRef<(() => number) | null>(null);
  const [start, setStart] = useState<number | null>(null);
  const [end, setEnd] = useState<number | null>(null);
  const [preview, setPreview] = useState(false);
  const h = it.highlight;
  const clip: Clip | null = h && {
    videoId: h.video_id, title: h.title, durationSec: h.duration_sec, precision: preview ? "scene" : "game",
    startSec: preview && start != null ? start : h.start_sec, endSec: preview && end != null ? end : h.end_sec,
  };
  const capture = () => {
    const t = Math.floor(now.current?.() ?? 0);
    setStart(t);
    setEnd(Math.min(t + LEN, h?.duration_sec ?? t + LEN));
    setPreview(false);
  };
  const num = (v: string) => (v.trim() === "" || Number.isNaN(Number(v)) ? null : Math.max(0, Math.floor(Number(v))));
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
        <span className="ml-auto flex gap-2">
          {h ? (
            <button onClick={onToggle} aria-expanded={open}
              className="rounded-lg border border-line px-3 py-1 text-xs font-semibold hover:bg-surface-2">
              {open ? "닫기" : `하이라이트에서 찾기 ${mmss(h.duration_sec)}`}
            </button>
          ) : (
            <span className="self-center text-xs text-muted">경기 하이라이트 없음</span>
          )}
          <button disabled={busy || !canSave} onClick={onNone}
            className="rounded-lg border border-line px-3 py-1 text-xs font-semibold disabled:opacity-40">영상에 없음</button>
        </span>
      </div>

      {open && clip && (
        <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_260px]">
          <div className="aspect-video overflow-hidden rounded-lg bg-night">
            <ScenePlayer bare clip={clip} label={h!.title} onReady={(f) => { now.current = f; }} />
          </div>
          <div className="space-y-2 text-xs">
            <p className="text-muted" title={h!.title}>[{h!.channel}] {h!.title}</p>
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
              <button disabled={!valid || busy || !canSave} onClick={() => valid && onMark(start, end)}
                className="flex-1 rounded-lg bg-brand px-2 py-1 font-semibold text-white disabled:opacity-40">이 구간으로 표시</button>
            </div>
            {!canSave && <p className="text-muted">검수자 이름을 먼저 적어 주세요</p>}
            <p className="text-muted">표시하면 바로 확정(승인) 장면이 되어 선수 화면에 나옵니다. 처음 {LEN}초가 기본 구간입니다.</p>
          </div>
        </div>
      )}
    </li>
  );
}
