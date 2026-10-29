"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  adminToken, ApiError, getMoveCandidates, getReviewQueue, getReviewStats, qk, saveReview, type ReviewActionKind,
  type Clip, type ReviewItem, type ReviewMode, type TargetKind,
} from "@/lib/api";
import ScenePlayer, { thumbnailUrl } from "@/components/ScenePlayer";

// BO-AD-01 장면 검수 (설계 8-4). 공개 화면에 링크를 두지 않는다
const TARGET_KO: Record<TargetKind, string> = { game: "경기", pa: "타석", outing: "등판" };
const REASON_KO: Record<string, string> = {
  doubleheader: "더블헤더 미판정", ambiguous: "후보 여럿·동명이인", claim_mismatch: "제목 주장 불일치",
  milestone: "기록 달성", neutral: "챕터 중립 · 무실점이지만 안타 허용", no_claim: "제목 주장 없음", excluded_words: "인터뷰·모음 등",
  low_gap: "1·2등 점수 차 작음", multi_hr: "그날 홈런 여럿", multi_hit: "어느 안타인지 모름", no_title_date: "제목에 날짜 없음",
  not_hr: "결과 단어 없음 (타점 등)", not_hr_title: "제목에 홈런 단어 없음", unplayable: "영상 소실", "-": "기타",
};
const PRECISION_KO = { scene: "바로 그 장면", inning: "그 이닝부터", game: "경기 요약" } as const;
const NAME_KEY = "baseon.admin.reviewer";

export default function ReviewPage() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<ReviewMode>("pending");
  const [targetKind, setTargetKind] = useState<TargetKind | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  // 검수자 이름은 이 브라우저에 기억, 토큰은 sessionStorage에만 (설계 6-4). 정적 빌드 때(window 없음)는 빈 값
  const [reviewer, setReviewer] = useState(() => {
    if (typeof window === "undefined") return "";
    try { return localStorage.getItem(NAME_KEY) ?? ""; } catch { return ""; }
  });
  const [token, setToken] = useState(() => (typeof window === "undefined" ? "" : adminToken.get()));
  const [playing, setPlaying] = useState<{ clip: Clip; label: string } | null>(null);

  const stats = useQuery({ queryKey: qk.reviewStats(), queryFn: getReviewStats });
  const queue = useQuery({
    queryKey: qk.reviewQueue(mode, targetKind, reason, null, offset),
    queryFn: () => getReviewQueue({ mode, targetKind, reason, season: null, offset }),
    placeholderData: keepPreviousData,
  });
  const save = useMutation({
    mutationFn: (v: { it: ReviewItem; action: ReviewActionKind; start?: number; end?: number; to?: string }) =>
      saveReview(v.it, { action: v.action, reviewer, start_sec: v.start, end_sec: v.end, to_target_id: v.to }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reviewQueue"] });
      qc.invalidateQueries({ queryKey: qk.reviewStats() });
    },
  });

  const unauthorized = queue.error instanceof ApiError && queue.error.status === 401;
  const reasons = (queue.data?.counts ?? []).filter((c) => !targetKind || c.target_kind === targetKind);

  return (
    <div className="mx-auto w-full max-w-5xl space-y-5 px-4 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold">장면 검수</h1>
          <p className="text-sm text-muted">자동으로 확신하지 못한 연결을 보고 승인·반려합니다. 승인한 장면만 화면에 나옵니다.</p>
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          <label className="flex items-center gap-1.5">
            <span className="text-muted">검수자</span>
            <input
              value={reviewer}
              onChange={(e) => {
                setReviewer(e.target.value);
                try { localStorage.setItem(NAME_KEY, e.target.value); } catch { /* 저장소 막힘 */ }
              }}
              className="w-24 rounded-lg border border-line bg-surface px-2 py-1"
              placeholder="이름"
              suppressHydrationWarning
            />
          </label>
          <label className="flex items-center gap-1.5">
            <span className="text-muted">토큰</span>
            <input
              type="password"
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                adminToken.set(e.target.value);
              }}
              className="w-32 rounded-lg border border-line bg-surface px-2 py-1"
              placeholder="서버에 설정했을 때만"
              suppressHydrationWarning
            />
          </label>
        </div>
      </header>

      {/* 대상별 현황 */}
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {(Object.keys(TARGET_KO) as TargetKind[]).map((k) => {
          const s = stats.data?.[k];
          return (
            <div key={k} className="rounded-xl border border-line bg-surface p-4">
              <div className="text-sm font-semibold">{TARGET_KO[k]} 장면</div>
              <div className="mt-1 text-2xl font-bold">
                {s?.pending ?? "–"}
                <span className="ml-1 text-sm font-normal text-muted">대기</span>
              </div>
              <div className="mt-1 text-xs text-muted">
                자동 확정 {s?.auto_confirmed ?? 0} · 승인 {s?.approved ?? 0} · 반려 {s?.rejected ?? 0}
                {s?.accuracy != null && ` · 자동 정확도 ${(s.accuracy * 100).toFixed(1)}%`}
                {s && s.auto_reviewed_ok + s.auto_reviewed_ng > 0 && ` (확인 ${s.auto_reviewed_ok + s.auto_reviewed_ng} · 틀림 ${s.auto_reviewed_ng})`}
              </div>
            </div>
          );
        })}
      </section>

      {/* 보기: 검수 대기 / 자동 확정 표본 (NFR-07 오매칭 표본 확인) */}
      <div className="flex flex-wrap items-center gap-2 text-sm" role="group" aria-label="보기">
        {(["pending", "auto_confirmed"] as ReviewMode[]).map((m) => (
          <button
            key={m}
            onClick={() => { setMode(m); setReason(null); setOffset(0); }}
            aria-pressed={mode === m}
            className={`rounded-lg border px-3 py-1 font-semibold ${mode === m ? "border-fg bg-fg text-bg" : "border-line bg-surface text-muted hover:text-fg"}`}
          >
            {m === "pending" ? "검수 대기" : "자동 확정 표본"}
          </button>
        ))}
        {mode === "auto_confirmed" && (
          <span className="text-xs text-muted">
            자동 확정된 연결을 무작위 순서로 보여 줍니다. 맞으면 「맞음」, 틀리면 「틀림」을 누르세요(틀린 연결은 화면에서 내려갑니다). 홈런은 300개 중 틀림 1개 이하가 목표입니다(NFR-07).
          </span>
        )}
      </div>

      {/* 필터 */}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {([null, "game", "pa", "outing"] as (TargetKind | null)[]).map((k) => (
          <button
            key={k ?? "all"}
            onClick={() => { setTargetKind(k); setReason(null); setOffset(0); }}
            aria-pressed={targetKind === k}
            className={`rounded-full border px-3 py-1 ${targetKind === k ? "border-fg bg-fg text-bg" : "border-line bg-surface text-muted hover:text-fg"}`}
          >
            {k ? TARGET_KO[k] : "전체"}
          </button>
        ))}
        <select
          value={reason ?? ""}
          onChange={(e) => { setReason(e.target.value || null); setOffset(0); }}
          className="rounded-lg border border-line bg-surface px-2 py-1"
          aria-label="검수 이유"
        >
          <option value="">{mode === "pending" ? "이유 전체" : "전체"}</option>
          {reasons.map((c) => (
            <option key={`${c.target_kind}-${c.reason}`} value={c.reason === "-" ? "" : c.reason}>
              {!targetKind && `${TARGET_KO[c.target_kind]} · `}{REASON_KO[c.reason] ?? c.reason} ({c.n})
            </option>
          ))}
        </select>
        {queue.data && <span className="text-muted">{mode === "pending" ? "대기" : "자동 확정"} {queue.data.total}개</span>}
      </div>

      {playing && (
        <div className="sticky top-16 z-10">
          <ScenePlayer clip={playing.clip} label={playing.label} onClose={() => setPlaying(null)} />
        </div>
      )}

      {unauthorized ? (
        <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">관리자 토큰을 입력해 주세요.</p>
      ) : queue.isPending ? (
        <p className="text-muted">불러오는 중…</p>
      ) : queue.isError ? (
        <p className="text-muted">검수 목록을 불러오지 못했습니다.</p>
      ) : queue.data.items.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">검수할 연결이 없습니다.</p>
      ) : (
        <ul className="space-y-3">
          {queue.data.items.map((it) => (
            <ReviewRow
              key={`${it.target_kind}-${it.target_id}-${it.video.video_id}`}
              it={it}
              busy={save.isPending}
              canSave={reviewer.trim().length > 0}
              onPlay={(clip) => setPlaying({ clip, label: `${TARGET_KO[it.target_kind]} · ${it.summary}` })}
              sample={mode === "auto_confirmed"}
              onSave={(action, start, end, to) => save.mutate({ it, action, start, end, to })}
            />
          ))}
        </ul>
      )}
      {save.isError && <p className="text-sm text-red-600">저장하지 못했습니다: {(save.error as Error).message}</p>}

      {queue.data && queue.data.total > 20 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}
            className="rounded-lg border border-line px-3 py-1 disabled:opacity-40">이전</button>
          <span className="tabular-nums text-muted">{offset + 1}–{Math.min(offset + 20, queue.data.total)} / {queue.data.total}</span>
          <button disabled={offset + 20 >= queue.data.total} onClick={() => setOffset(offset + 20)}
            className="rounded-lg border border-line px-3 py-1 disabled:opacity-40">다음</button>
        </div>
      )}
    </div>
  );
}

function ReviewRow({
  it, busy, canSave, sample, onPlay, onSave,
}: {
  it: ReviewItem;
  /** 자동 확정 표본 확인: 버튼을 맞음·틀림으로 */
  sample: boolean;
  busy: boolean;
  canSave: boolean;
  onPlay: (clip: Clip) => void;
  onSave: (action: ReviewActionKind, start?: number, end?: number, to?: string) => void;
}) {
  const [moving, setMoving] = useState(false);
  const cands = useQuery({
    queryKey: ["moveCandidates", it.target_kind, it.target_id, it.video.video_id],
    queryFn: () => getMoveCandidates(it),
    enabled: moving,
  });
  const [start, setStart] = useState(String(it.start_sec ?? 0));
  const [end, setEnd] = useState(String(it.end_sec ?? it.video.duration_sec ?? ""));
  const clip: Clip = {
    videoId: it.video.video_id, title: it.video.title, startSec: it.start_sec ?? 0,
    endSec: it.end_sec ?? it.video.duration_sec, durationSec: it.video.duration_sec, precision: it.precision,
  };
  return (
    <li className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-3 sm:flex-row">
      <button onClick={() => onPlay(clip)} className="relative w-full shrink-0 overflow-hidden rounded-lg sm:w-48" aria-label="재생">
        {/* eslint-disable-next-line @next/next/no-img-element -- 정적 내보내기: 썸네일 핫링크(설계 8-2) */}
        <img src={thumbnailUrl(it.video.video_id)} alt="" className="aspect-video w-full object-cover" />
        <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1.5 text-xs text-white tabular-nums">
          {it.start_sec ?? 0}–{it.end_sec ?? it.video.duration_sec}초
        </span>
      </button>
      <div className="min-w-0 flex-1 space-y-1 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-bg px-1.5 py-0.5 text-xs font-semibold">{TARGET_KO[it.target_kind]}</span>
          <span className="font-semibold">{it.summary}</span>
          <span className="text-xs text-muted">{it.date}</span>
        </div>
        <p className="truncate text-muted" title={it.video.title}>
          [{it.video.channel}] {it.video.title}
        </p>
        <p className="text-xs">
          <span className="rounded-full border border-accent px-2 py-0.5 font-semibold">{sample ? "자동 확정" : (REASON_KO[it.review_reason ?? "-"] ?? it.review_reason)}</span>
          <span className="ml-2 text-muted">{PRECISION_KO[it.precision]} · 점수 {it.score ?? "–"} · {it.reasons}</span>
        </p>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button disabled={busy || !canSave} onClick={() => onSave("approve")}
            className="rounded-lg bg-fg px-3 py-1 text-xs font-semibold text-bg disabled:opacity-40">{sample ? "맞음" : "승인"}</button>
          <button disabled={busy || !canSave} onClick={() => onSave("reject")}
            className="rounded-lg border border-line px-3 py-1 text-xs font-semibold disabled:opacity-40">{sample ? "틀림" : "반려"}</button>
          {it.precision !== "game" && (
            <span className="flex items-center gap-1 text-xs">
              <input value={start} onChange={(e) => setStart(e.target.value)} inputMode="numeric" aria-label="시작 초"
                className="w-14 rounded border border-line bg-surface px-1.5 py-0.5 tabular-nums" />
              ~
              <input value={end} onChange={(e) => setEnd(e.target.value)} inputMode="numeric" aria-label="종료 초"
                className="w-14 rounded border border-line bg-surface px-1.5 py-0.5 tabular-nums" />
              <button disabled={busy || !canSave} onClick={() => onSave("retime", Number(start), Number(end))}
                className="rounded-lg border border-line px-2 py-0.5 font-semibold disabled:opacity-40">구간 고쳐 승인</button>
            </span>
          )}
          {!sample && (
            <button disabled={busy} onClick={() => setMoving((m) => !m)} aria-expanded={moving}
              className="rounded-lg border border-line px-3 py-1 text-xs font-semibold disabled:opacity-40">옮김</button>
          )}
          {!canSave && <span className="text-xs text-muted">검수자 이름을 먼저 적어 주세요</span>}
        </div>
        {moving && (
          <div className="mt-2 rounded-lg border border-line bg-bg p-2 text-xs">
            <p className="mb-1 text-muted">이 영상이 맞는 {TARGET_KO[it.target_kind]}을(를) 고르면 지금 연결은 반려되고 그쪽에 승인 연결이 생깁니다.</p>
            {cands.isPending ? (
              <p className="text-muted">불러오는 중…</p>
            ) : cands.isError ? (
              <p className="text-muted">후보를 불러오지 못했습니다.</p>
            ) : cands.data.length === 0 ? (
              <p className="text-muted">옮길 후보가 없습니다.</p>
            ) : (
              <ul className="space-y-1">
                {cands.data.map((c) => (
                  <li key={c.target_id} className="flex items-center gap-2">
                    <span className="w-28 shrink-0 text-muted">{c.why}</span>
                    <span className="w-20 shrink-0 tabular-nums text-muted">{c.date}</span>
                    <span className="min-w-0 flex-1 truncate">{c.summary}</span>
                    <button disabled={busy || !canSave} onClick={() => onSave("move", undefined, undefined, c.target_id)}
                      className="shrink-0 rounded border border-line bg-surface px-2 py-0.5 font-semibold disabled:opacity-40">여기로</button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </li>
  );
}
