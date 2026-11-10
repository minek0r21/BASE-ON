"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  adminToken, ApiError, getAdminMe, getGameHrs, getMoveCandidates, getNfr07, getRecheck, getReviewQueue, getReviewStats, qk,
  saveRecheck, saveReview, type ReviewActionKind, type Clip, type ClipCheck, type ClipVerdict, type Nfr07, type RecheckQueue,
  type RecheckResult, type ReviewItem, type ReviewMode, type TargetKind, type WrongReason,
} from "@/lib/api";
import ScenePlayer, { thumbnailUrl } from "@/components/ScenePlayer";
import { mmss } from "@/components/ui/Media";
import ManualQueue from "./ManualQueue";

// BO-AD-01 장면 검수 (설계 8-4). 공개 화면에 링크를 두지 않는다
const TARGET_KO: Record<TargetKind, string> = { game: "경기", pa: "타석", outing: "등판" };
const REASON_KO: Record<string, string> = {
  doubleheader: "더블헤더 미판정", ambiguous: "후보 여럿·동명이인", claim_mismatch: "제목 주장 불일치",
  milestone: "기록 달성", neutral: "챕터 중립 · 무실점이지만 안타 허용", no_claim: "제목 주장 없음", excluded_words: "인터뷰·모음 등",
  low_gap: "1·2등 점수 차 작음", multi_hr: "그날 홈런 여럿", multi_hit: "어느 안타인지 모름", no_title_date: "제목에 날짜 없음",
  not_hr: "결과 단어 없음 (타점 등)", not_hr_title: "제목에 홈런 단어 없음", unplayable: "영상 소실",
  highlight_weak: "하이라이트 판독 근거 약함", multi_scene_clip: "멀티 홈런 클립 (어느 홈런인지 · 15초 밖)", "-": "기타",
};
const PRECISION_KO = { scene: "바로 그 장면", inning: "그 이닝부터", game: "경기 요약" } as const;
const NAME_KEY = "baseon.admin.reviewer";
const PART_KEY = "baseon.admin.nfr07part";
// NFR-07 표본을 여럿이 나눠 볼 때 내 몫 (「2/3」 = 세 명 중 두 번째, 표본 순번 % 3)
const PARTS = ["1/1", "1/2", "2/2", "1/3", "2/3", "3/3", "1/4", "2/4", "3/4", "4/4"];
const NFR07_SEASON = 2026;
const ORIGIN_KO: Record<string, string> = { highlight: "하이라이트 장면", auto: "클립(제목 규칙)", manual: "사람 표시", gemini_manual: "사람 표시" };
// Gemini 확인 판독(장면.md 11-6) — 위험한 것부터
const VERDICT_KO: Record<ClipVerdict | "unread", string> = {
  conflict: "근거 충돌", other: "다른 타자", none: "홈런 못 읽음", name_only: "이름만", match1: "근거 1개 일치", match2: "근거 2개↑ 일치",
  unread: "판독 전",
};
// 틀림 이유 (K 다음에 1 · 2 · 3). 홈런이 아니면 「다른 장면」
const WRONG_KO: Record<WrongReason | "unknown", string> = { other_hr: "다른 홈런", late: "15초 안에 안 나옴", absent: "영상에 없음", unknown: "이유 없음" };
const wrongLabel = (r: WrongReason, hr: boolean) => (r === "other_hr" && !hr ? "다른 장면" : WRONG_KO[r]);

export default function ReviewPage() {
  const qc = useQueryClient();
  // 보기: 검수 대기 · 자동 확정 표본(API 7') · NFR-07 표본(API 7'') · 수동 표시(API 11-2)
  const [view, setView] = useState<ReviewMode | "nfr07" | "recheck" | "manual">("pending");
  const mode: ReviewMode = view === "auto_confirmed" || view === "nfr07" ? "auto_confirmed" : "pending";
  const [targetKind, setTargetKind] = useState<TargetKind | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [own, setOwn] = useState(false);  // 틀림 다시 보기: false 다른 사람이 누른 것 / true 내가 누른 것
  // 검수자 이름은 이 브라우저에 기억, 토큰은 sessionStorage에만 (설계 6-4). 정적 빌드 때(window 없음)는 빈 값
  const [name, setName] = useState(() => {
    if (typeof window === "undefined") return "";
    try { return localStorage.getItem(NAME_KEY) ?? ""; } catch { return ""; }
  });
  const [token, setToken] = useState(() => (typeof window === "undefined" ? "" : adminToken.get()));
  const [draft, setDraft] = useState("");
  const [part, setPart] = useState(() => {
    if (typeof window === "undefined") return "1/1";
    try { const v = localStorage.getItem(PART_KEY); return v && PARTS.includes(v) ? v : "1/1"; } catch { return "1/1"; }
  });
  const [mine, of] = part.split("/").map(Number);
  const [playing, setPlaying] = useState<{ clip: Clip; label: string } | null>(null);

  // 「입력」을 누르면 토큰이 바뀌어 다시 확인한다. 통과해야 검수 화면을 연다
  const me = useQuery({ queryKey: qk.adminMe(token), queryFn: getAdminMe, retry: false });
  const authed = me.isSuccess;
  const reviewer = me.data?.reviewer ?? name;  // 토큰이 있으면 토큰의 이름, 로컬 개발은 적은 이름

  const stats = useQuery({ queryKey: qk.reviewStats(), queryFn: getReviewStats, enabled: authed });
  const queue = useQuery({
    queryKey: view === "nfr07" ? qk.nfr07(NFR07_SEASON, offset, part)
      : view === "recheck" ? qk.recheck(offset, reviewer, own) : qk.reviewQueue(mode, targetKind, reason, null, offset),
    queryFn: () => (view === "nfr07" ? getNfr07(NFR07_SEASON, offset, mine, of)
      : view === "recheck" ? getRecheck(offset, reviewer, own) : getReviewQueue({ mode, targetKind, reason, season: null, offset })),
    placeholderData: keepPreviousData,
    enabled: authed && view !== "manual",
  });
  const after = () => {
    qc.invalidateQueries({ queryKey: ["reviewQueue"] });
    qc.invalidateQueries({ queryKey: qk.reviewStats() });
  };
  const save = useMutation({
    mutationFn: (v: { it: ReviewItem; action: ReviewActionKind; start?: number; end?: number; to?: string; why?: WrongReason }) =>
      saveReview(v.it, { action: v.action, reviewer, start_sec: v.start, end_sec: v.end, to_target_id: v.to, wrong_reason: v.why }),
    onSuccess: after,
  });
  const recheck = useMutation({
    mutationFn: (v: { it: ReviewItem; result: RecheckResult; start?: number }) =>
      saveRecheck(v.it, { result: v.result, reviewer, start_sec: v.start, own }),
    onSuccess: after,
  });

  const reasons = (queue.data?.counts ?? []).filter((c) => !targetKind || c.target_kind === targetKind);

  if (!authed) {
    const wrong = me.error instanceof ApiError && me.error.status === 401;
    return (
      <div className="mx-auto w-full max-w-sm px-4 py-16">
        <form
          className="space-y-3 rounded-xl border border-line bg-surface p-6"
          onSubmit={(e) => {
            e.preventDefault();
            const t = draft.trim();
            adminToken.set(t);
            setToken(t);
            if (t === token) me.refetch();
          }}
        >
          <h1 className="text-xl font-extrabold">장면 검수</h1>
          <label className="block text-sm">
            <span className="mb-1.5 block text-muted">검수자 토큰</span>
            <input
              type="password"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              autoComplete="off"
              autoFocus
              className="w-full rounded-lg border border-line bg-bg px-3 py-2"
            />
          </label>
          <button
            type="submit"
            disabled={!draft.trim() || me.isFetching}
            className="w-full rounded-lg bg-fg px-3 py-2 font-semibold text-bg disabled:opacity-50"
          >
            {me.isFetching ? "확인 중" : "입력"}
          </button>
          {token && wrong && !me.isFetching && <p role="alert" className="text-sm text-red-600">토큰이 맞지 않습니다.</p>}
          {me.isError && !wrong && !me.isFetching && <p role="alert" className="text-sm text-red-600">확인하지 못했습니다. 다시 눌러 주세요.</p>}
        </form>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-5 px-4 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold">장면 검수</h1>
          <p className="text-sm text-muted">자동 확정 조건을 넘지 못한 연결을 승인·반려하고, 장면 없는 홈런은 경기 하이라이트에서 직접 표시합니다.</p>
        </div>
        {me.data?.reviewer ? (
          <span className="text-sm"><span className="text-muted">검수자</span> <b>{me.data.reviewer}</b></span>
        ) : (
          <label className="flex items-center gap-1.5 text-sm">
            <span className="text-muted">검수자</span>
            <input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                try { localStorage.setItem(NAME_KEY, e.target.value); } catch { /* 저장소 막힘 */ }
              }}
              className="w-24 rounded-lg border border-line bg-surface px-2 py-1"
              placeholder="이름"
              suppressHydrationWarning
            />
          </label>
        )}
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
              {s?.gemini && (
                <div className="mt-1 text-xs text-muted">
                  Gemini 제안으로 표시 {s.gemini.marked} · 5초 안 {s.gemini.within5} · 평균 {s.gemini.avg_shift}초 옮김
                </div>
              )}
            </div>
          );
        })}
      </section>

      {/* 보기: 검수 대기 / 자동 확정 표본 (NFR-07 오매칭 표본 확인) */}
      <div className="flex flex-wrap items-center gap-2 text-sm" role="group" aria-label="보기">
        {(["pending", "auto_confirmed", "nfr07", "recheck", "manual"] as const).map((m) => (
          <button
            key={m}
            onClick={() => { setView(m); setReason(null); setOffset(0); }}
            aria-pressed={view === m}
            className={`rounded-lg border px-3 py-1 font-semibold ${view === m ? "border-fg bg-fg text-bg" : "border-line bg-surface text-muted hover:text-fg"}`}
          >
            {{ pending: "검수 대기", auto_confirmed: "자동 확정 표본", nfr07: `NFR-07 표본 (${NFR07_SEASON} 홈런 300)`, recheck: "틀림 다시 보기", manual: "수동 표시 (장면 없는 홈런)" }[m]}
          </button>
        ))}
        {view === "recheck" && queue.data && "mine" in queue.data && (
          <span className="flex gap-1 text-xs" role="group" aria-label="누가 누른 틀림">
            {([false, true] as const).map((o) => (
              <button
                key={String(o)}
                onClick={() => { setOwn(o); setOffset(0); }}
                aria-pressed={own === o}
                className={`rounded-full border px-2 py-0.5 tabular-nums ${own === o ? "border-fg font-semibold" : "border-line text-muted hover:text-fg"}`}
              >
                {o ? "내가 누른 틀림" : "다른 사람이 누른 틀림"} {o ? (queue.data as RecheckQueue).mine : (queue.data as RecheckQueue).others}
              </button>
            ))}
          </span>
        )}
        {view === "recheck" && (
          <span className="text-xs text-muted">
            {own ? "내가 「틀림」을 누른 장면을 한 번 더 봅니다." : "다른 사람이 「틀림」을 누른 장면을 한 번 더 봅니다."} 그 홈런이 영상 안에 있으면 투구 직전에서 멈추고 「여기부터」를 누르세요 — 시작 초만 고쳐 화면에 다시 나갑니다. NFR-07에는 틀림으로 그대로 남습니다.
          </span>
        )}
        {view === "auto_confirmed" && (
          <span className="text-xs text-muted">
            자동 확정된 연결을 무작위 순서로 보여 줍니다. 맞으면 「맞음」, 틀리면 「틀림」을 누르세요(틀린 연결은 화면에서 내려갑니다). 홈런은 300개 중 틀림 1개 이하가 목표입니다(NFR-07).
          </span>
        )}
        {view === "nfr07" && (
          <span className="text-xs text-muted">
            화면에 나가는 홈런 장면 300개를 하나씩 재생합니다. 시작 15초 안에 그 타자의 그 홈런이 보이면 맞음(J), 아니면 틀림(K).
          </span>
        )}
        {view === "nfr07" && (
          <label className="flex items-center gap-1 text-xs">
            <span className="text-muted">나눠 보기</span>
            <select
              value={part}
              onChange={(e) => {
                setPart(e.target.value);
                try { localStorage.setItem(PART_KEY, e.target.value); } catch { /* 저장소 막힘 */ }
              }}
              className="rounded border border-line bg-surface px-1 py-0.5"
            >
              {PARTS.map((p) => {
                const [a, b] = p.split("/");
                return <option key={p} value={p}>{b === "1" ? "혼자 전부" : `${b}명 중 ${a}번째`}</option>;
              })}
            </select>
          </label>
        )}
      </div>
      {view === "nfr07" && queue.data && "progress" in queue.data && (<>
        <Nfr07Panel d={queue.data as Nfr07} />
        {queue.data.items[0] ? (
          <Nfr07Runner
            key={`${queue.data.items[0].target_id}-${queue.data.items[0].video.video_id}`}
            it={queue.data.items[0]}
            left={queue.data.total}
            busy={save.isPending || queue.isFetching}
            canSave={reviewer.trim().length > 0}
            onSave={(action, why) => save.mutate({ it: queue.data!.items[0], action, why })}
          />
        ) : (
          <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">
            {(queue.data as Nfr07).sample ? (of > 1 ? "내 몫을 다 봤습니다." : "표본을 다 봤습니다.") : "표본이 아직 없습니다 (etl 11 --sample)."}
          </p>
        )}
      </>)}
      {view === "recheck" && queue.data && "mine" in queue.data && (() => {
        const d = queue.data as RecheckQueue;
        const it = d.items[0];
        return (<>
          {it ? (
            <RecheckRunner
              key={`${it.target_kind}-${it.target_id}-${it.video.video_id}`}
              it={it}
              left={d.total}
              busy={recheck.isPending || queue.isFetching}
              canSave={reviewer.trim().length > 0}
              onSave={(result, start) => recheck.mutate({ it, result, start })}
            />
          ) : (
            <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">다시 볼 틀림이 없습니다.</p>
          )}
        </>);
      })()}

      {view === "manual" ? <ManualQueue reviewer={reviewer} canSave={reviewer.trim().length > 0} /> : view === "nfr07" || view === "recheck" ? (
        (save.isError || recheck.isError) && <p className="text-sm text-red-600">저장하지 못했습니다: {((save.error ?? recheck.error) as Error).message}</p>
      ) : (<>
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

      {queue.isPending ? (
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
      </>)}
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
        {it.check && <CheckLine c={it.check} />}
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

/** NFR-07 진행: 확인 수 · 틀림 · 95% 상한 + 출처(하이라이트 장면 · 클립)별 */
function Nfr07Panel({ d }: { d: Nfr07 }) {
  const p = d.progress;
  return (
    <section className="rounded-xl border border-line bg-surface p-4 text-sm">
      <p className="font-semibold">
        확인 <span className="tabular-nums">{p.seen} / {d.sample}</span> · 틀림 <span className="tabular-nums">{p.wrong}</span>
        <span className="ml-2 font-normal text-muted">
          {p.upper95 != null ? `틀림 비율 95% 상한 ${(p.upper95 * 100).toFixed(2)}% (목표 1% 이하)` : `${d.sample}개를 다 보면 95% 상한이 나옵니다 (틀림 0개면 0.99%)`}
        </span>
      </p>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted tabular-nums">
        {Object.entries(d.by_origin).map(([k, t]) => (
          <span key={k}>{ORIGIN_KO[k] ?? k} {t.n}{t.seen > 0 && ` (확인 ${t.seen} · 틀림 ${t.wrong})`}</span>
        ))}
      </div>
      {p.wrong > 0 && (
        <p className="mt-1 text-xs text-muted tabular-nums">
          틀림 이유: {(Object.entries(p.by_reason) as [WrongReason | "unknown", number][]).map(([k, n]) => `${WRONG_KO[k]} ${n}`).join(" · ")}
          {" · "}다시 봄 {p.rechecked} / {p.wrong}
        </p>
      )}
    </section>
  );
}

/** 틀림 이유 고르기 (K 다음): 1 다른 홈런 · 2 15초 안에 안 나옴 · 3 영상에 없음, Esc 취소 */
function WrongReasons({ hr, busy, canSave, onPick, onCancel }: {
  hr: boolean; busy: boolean; canSave: boolean; onPick: (r: WrongReason) => void; onCancel: () => void;
}) {
  const order: WrongReason[] = ["other_hr", "late", "absent"];
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-bg p-2 text-sm">
      <span className="text-xs text-muted">왜 틀렸나요?</span>
      {order.map((r, i) => (
        <button key={r} disabled={busy || !canSave} onClick={() => onPick(r)}
          className="rounded-lg border border-line bg-surface px-3 py-1 font-semibold disabled:opacity-40">
          {wrongLabel(r, hr)} <kbd className="ml-1 text-xs opacity-70">{i + 1}</kbd>
        </button>
      ))}
      <button onClick={onCancel} className="rounded-lg px-2 py-1 text-xs text-muted">취소 <kbd className="ml-1 opacity-70">Esc</kbd></button>
    </div>
  );
}

/** NFR-07 하나씩: 장면 시각부터 바로 재생, J 맞음 · K 틀림(→ 이유 1 · 2 · 3) · R 처음부터 다시. 저장하면 다음 장면으로 */
function Nfr07Runner({ it, left, busy, canSave, onSave }: {
  it: ReviewItem; left: number; busy: boolean; canSave: boolean; onSave: (action: "approve" | "reject", why?: WrongReason) => void;
}) {
  const [again, setAgain] = useState(0);
  const [asking, setAsking] = useState(false);  // K를 눌러 이유를 고르는 중
  const clip: Clip = {
    videoId: it.video.video_id, title: it.video.title, startSec: it.start_sec ?? 0,
    endSec: it.end_sec ?? it.video.duration_sec, durationSec: it.video.duration_sec, precision: it.precision,
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.key === "r" || e.key === "R") { setAgain((n) => n + 1); return; }
      if (asking && e.key === "Escape") { setAsking(false); return; }
      if (busy || !canSave) return;
      if (asking) {
        const why = ({ "1": "other_hr", "2": "late", "3": "absent" } as const)[e.key as "1" | "2" | "3"];
        if (why) onSave("reject", why);
        return;
      }
      if (e.key === "j" || e.key === "J") onSave("approve");
      if (e.key === "k" || e.key === "K") setAsking(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, canSave, onSave, asking]);
  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold">{it.summary}</span>
        <span className="text-xs text-muted">{it.date}</span>
        <span className="rounded-full border border-line px-2 py-0.5 text-xs">{ORIGIN_KO[it.origin] ?? it.origin}</span>
        <span className="ml-auto text-xs text-muted tabular-nums">남은 {left}개</span>
      </div>
      <div className="aspect-video w-full overflow-hidden rounded-lg">
        <ScenePlayer key={again} clip={clip} label={`${it.summary} · ${clip.startSec}초부터`} bare />
      </div>
      <p className="truncate text-xs text-muted" title={it.video.title}>[{it.video.channel}] {it.video.title}</p>
      <div className="flex flex-wrap items-center gap-2">
        <button disabled={busy || !canSave} onClick={() => onSave("approve")}
          className="rounded-lg bg-fg px-4 py-1.5 text-sm font-semibold text-bg disabled:opacity-40">맞음 <kbd className="ml-1 text-xs opacity-70">J</kbd></button>
        <button disabled={busy || !canSave} onClick={() => setAsking(true)} aria-expanded={asking}
          className="rounded-lg border border-line px-4 py-1.5 text-sm font-semibold disabled:opacity-40">틀림 <kbd className="ml-1 text-xs opacity-70">K</kbd></button>
        <button onClick={() => setAgain((n) => n + 1)} className="rounded-lg border border-line px-3 py-1.5 text-sm">처음부터 <kbd className="ml-1 text-xs opacity-70">R</kbd></button>
        {!canSave && <span className="text-xs text-muted">검수자 이름을 먼저 적어 주세요</span>}
      </div>
      {asking && (
        <WrongReasons hr={it.scene_type === "home_run"} busy={busy} canSave={canSave}
          onPick={(why) => onSave("reject", why)} onCancel={() => setAsking(false)} />
      )}
    </section>
  );
}

/** 틀림 다시 보기 하나씩: 영상 전체를 연결된 시각부터 틀고, 같은 경기 홈런의 시각으로 넘어갈 수 있다.
 *  1 맞음(잘못 누름) · 2 다른 홈런 → 여기부터 · 3 늦게 나옴 → 여기부터 · 4 영상에 없음 · R 처음부터 */
function RecheckRunner({ it, left, busy, canSave, onSave }: {
  it: ReviewItem; left: number; busy: boolean; canSave: boolean; onSave: (result: RecheckResult, start?: number) => void;
}) {
  const hr = it.scene_type === "home_run";
  const [from, setFrom] = useState({ sec: it.start_sec ?? 0, n: 0 });  // n: 같은 시각을 다시 눌러도 처음부터
  const now = useRef<(() => number) | null>(null);
  const [pos, setPos] = useState<number | null>(null);
  const hrs = useQuery({
    queryKey: qk.gameHrs(it.target_id, it.video.video_id),
    queryFn: () => getGameHrs(it),
    enabled: it.target_kind === "pa" && hr,
  });
  // 영상 끝까지 튼다 — 원래 구간 밖에 있는 그 홈런을 찾아야 하므로
  const clip: Clip = {
    videoId: it.video.video_id, title: it.video.title, startSec: from.sec,
    endSec: it.video.duration_sec, durationSec: it.video.duration_sec, precision: "scene",
  };
  useEffect(() => {
    const t = setInterval(() => { if (now.current) setPos(Math.floor(now.current())); }, 500);
    return () => clearInterval(t);
  }, []);
  const here = () => Math.floor(now.current?.() ?? from.sec);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.key === "r" || e.key === "R") { setFrom((f) => ({ sec: it.start_sec ?? 0, n: f.n + 1 })); return; }
      if (busy || !canSave) return;
      if (e.key === "1") onSave("mistake");
      if (e.key === "2") onSave("other_hr", here());
      if (e.key === "3") onSave("late", here());
      if (e.key === "4") onSave("absent");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  const btn = "rounded-lg border border-line px-3 py-1.5 text-sm font-semibold disabled:opacity-40";
  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold">{it.summary}</span>
        <span className="text-xs text-muted">{it.date}</span>
        <span className="rounded-full border border-line px-2 py-0.5 text-xs">{ORIGIN_KO[it.origin] ?? it.origin}</span>
        {it.nfr07 === "v2" && <span className="rounded-full border border-accent px-2 py-0.5 text-xs font-semibold">NFR-07 표본</span>}
        <span className="ml-auto text-xs text-muted tabular-nums">남은 {left}개</span>
      </div>
      <p className="text-xs text-muted">
        처음 판정: <b className="text-fg">{it.reviewer ?? "–"}</b> 「틀림」{it.wrong_reason && ` · ${wrongLabel(it.wrong_reason, hr)}`}
        {" · "}연결된 시각 {mmss(it.start_sec ?? 0)}~{mmss(it.end_sec ?? it.video.duration_sec ?? 0)}
      </p>
      <div className="aspect-video w-full overflow-hidden rounded-lg">
        <ScenePlayer key={from.n} clip={clip} label={`${it.summary} · ${from.sec}초부터`} bare onReady={(f) => { now.current = f; }} />
      </div>
      <p className="truncate text-xs text-muted" title={it.video.title}>[{it.video.channel}] {it.video.title}</p>
      {hrs.data && hrs.data.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-muted">이 경기 홈런</span>
          {hrs.data.map((h) => {
            const label = `${h.batter}${h.hr_seq != null ? ` ${h.hr_seq}호` : ""} · ${h.inning}회${h.half}`;
            return h.start_sec != null ? (
              <button key={h.pa_id} onClick={() => setFrom((f) => ({ sec: h.start_sec!, n: f.n + 1 }))}
                className={`rounded-full border px-2 py-0.5 tabular-nums ${h.this ? "border-fg font-semibold" : "border-line"} ${h.status === "rejected" && !h.this ? "text-muted line-through" : ""}`}
                title={h.this ? "이 홈런의 연결된 시각" : h.status === "rejected" ? "이 연결도 틀림" : "이 시각으로 넘어가기"}>
                {label} {mmss(h.start_sec)}
              </button>
            ) : (
              <span key={h.pa_id} className="rounded-full border border-dashed border-line px-2 py-0.5 text-muted">{label} · 이 영상 시각 없음</span>
            );
          })}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted tabular-nums">지금 {pos != null ? mmss(pos) : "–"}</span>
        <button disabled={busy || !canSave} onClick={() => onSave("other_hr", here())}
          className="rounded-lg bg-fg px-3 py-1.5 text-sm font-semibold text-bg disabled:opacity-40">{wrongLabel("other_hr", hr)}였음 → 여기부터 <kbd className="ml-1 text-xs opacity-70">2</kbd></button>
        <button disabled={busy || !canSave} onClick={() => onSave("late", here())}
          className="rounded-lg bg-fg px-3 py-1.5 text-sm font-semibold text-bg disabled:opacity-40">늦게 나옴 → 여기부터 <kbd className="ml-1 text-xs opacity-70">3</kbd></button>
        <button disabled={busy || !canSave} onClick={() => onSave("absent")} className={btn}>영상에 없음 <kbd className="ml-1 text-xs opacity-70">4</kbd></button>
        <button disabled={busy || !canSave} onClick={() => onSave("mistake")} className={btn}>맞음 (잘못 누름) <kbd className="ml-1 text-xs opacity-70">1</kbd></button>
        <button onClick={() => setFrom((f) => ({ sec: it.start_sec ?? 0, n: f.n + 1 }))} className="rounded-lg border border-line px-3 py-1.5 text-sm">처음부터 <kbd className="ml-1 text-xs opacity-70">R</kbd></button>
        {!canSave && <span className="text-xs text-muted">검수자 이름을 먼저 적어 주세요</span>}
      </div>
      <p className="text-xs text-muted">「여기부터」는 지금 재생 위치부터 20초를 이 홈런 장면으로 저장합니다(화면에 다시 나감). 투구 직전에 멈추고 누르세요.</p>
    </section>
  );
}

/** Gemini가 화면 · 해설에서 읽은 것 — 기록과 어긋난 칸은 빨간색 */
function CheckLine({ c }: { c: ClipCheck }) {
  const bad = new Set((c.conflicts || "").split("·").filter(Boolean));
  const part = (label: string, key: string, v: string | number | null) =>
    v == null ? null : <span key={key} className={bad.has(key) ? "font-semibold text-red-600" : ""}>{label.replace("{}", String(v))}</span>;
  const parts = [part("{}", "이름", c.read_batter), part("{}호", "n호", c.read_hr_no), part("{}회", "이닝", c.read_inning), part("{}", "점수", c.read_score)]
    .filter(Boolean);
  const risky = c.verdict !== "match2" && c.verdict !== "match1";
  return (
    <p className="text-xs">
      <span className={`rounded-full px-2 py-0.5 font-semibold ${risky ? "bg-red-600 text-white" : "border border-line"}`}>Gemini {VERDICT_KO[c.verdict]}</span>
      <span className="ml-2 text-muted">
        화면: {parts.length ? parts.map((x, i) => <span key={i}>{i > 0 && " · "}{x}</span>) : "읽은 것 없음"}
        {c.evidence && ` · 근거 ${c.evidence}`}
      </span>
    </p>
  );
}
