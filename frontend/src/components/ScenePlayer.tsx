"use client";

import { useEffect, useRef, useState } from "react";
import { reportUnplayable, type Clip } from "@/lib/api";

/**
 * 장면 플레이어 (설계 8-2)
 * - 썸네일을 먼저 그리고, 누를 때 YouTube IFrame 플레이어를 붙인다. 자동재생 없음
 * - 구간 재생: loadVideoById({videoId, startSeconds, endSeconds})
 * - 종료 강제(FR-04-02): 재생 중 250ms마다 현재 위치가 end_sec를 넘으면 멈추고 end_sec로 되돌린다
 * - 다른 장면으로 바꿀 때 iframe을 다시 만들지 않고 loadVideoById만 부른다
 * - 재생 불가(onError 100·101·150·153) → 안내 문구 + 신고(API-12). 서버가 확인해 그 영상을 검수로 보낸다
 */

type YTPlayer = {
  loadVideoById: (o: { videoId: string; startSeconds?: number; endSeconds?: number }) => void;
  getCurrentTime: () => number;
  getPlayerState: () => number;
  pauseVideo: () => void;
  seekTo: (s: number, allowSeekAhead: boolean) => void;
  destroy: () => void;
};
type YTNamespace = {
  Player: new (
    el: HTMLElement,
    opts: {
      videoId: string;
      width?: string;
      height?: string;
      playerVars?: Record<string, number | string>;
      events?: { onReady?: () => void; onError?: (e: { data: number }) => void };
    },
  ) => YTPlayer;
  PlayerState: { PLAYING: number };
};
declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiPromise: Promise<YTNamespace> | null = null;
function loadYouTubeApi(): Promise<YTNamespace> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  apiPromise ??= new Promise((resolve) => {
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      prev?.();
      resolve(window.YT!);
    };
    const s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(s);
  });
  return apiPromise;
}

const UNPLAYABLE = new Set([100, 101, 150, 153]);
const POLL_MS = 250;

export const thumbnailUrl = (videoId: string) => `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`;

export default function ScenePlayer({ clip, label, onClose, bare = false }: {
  clip: Clip;
  label: string;
  onClose?: () => void;
  /** 화면 안 그 자리에서 바로 재생 (메인 「그날 장면」): 머리줄 · 설명 없이 영상 칸만, 누른 뒤라 바로 시작 */
  bare?: boolean;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  const clipRef = useRef(clip);
  const [started, setStarted] = useState(bare);
  // 오류는 영상 ID와 묶어 둔다 → 다른 장면으로 바꾸면 저절로 사라진다
  const [error, setError] = useState<{ videoId: string; code: number } | null>(null);
  const shownError = error?.videoId === clip.videoId ? <ErrorText code={error.code} /> : null;

  useEffect(() => {
    clipRef.current = clip;
  }, [clip]);

  // 플레이어 만들기 (처음 누를 때 한 번). YT는 넘겨받은 요소를 iframe으로 바꿔 끼우므로
  // React가 관리하는 div가 아니라 그 안에 직접 만든 요소를 넘긴다
  useEffect(() => {
    if (!started || playerRef.current || !hostRef.current) return;
    let cancelled = false;
    loadYouTubeApi().then((YT) => {
      if (cancelled || !hostRef.current) return;
      const c = clipRef.current;
      const el = document.createElement("div");
      hostRef.current.appendChild(el);
      playerRef.current = new YT.Player(el, {
        videoId: c.videoId,
        width: "100%",
        height: "100%",
        playerVars: {
          start: Math.floor(c.startSec),
          ...(c.endSec ? { end: Math.ceil(c.endSec) } : {}),
          autoplay: 1, // 사용자가 누른 뒤라 자동재생 정책에 걸리지 않는다
          rel: 0,
          playsinline: 1,
          origin: window.location.origin,
        },
        events: {
          onError: (e) => {
            const videoId = clipRef.current.videoId;
            if (UNPLAYABLE.has(e.data)) reportUnplayable(videoId);
            setError({ videoId, code: e.data });
          },
        },
      });
    });
    return () => {
      cancelled = true;
    };
  }, [started]);

  // 장면이 바뀌면 같은 플레이어로 구간만 바꿔 재생
  useEffect(() => {
    const p = playerRef.current;
    if (p && typeof p.loadVideoById === "function") {
      p.loadVideoById({ videoId: clip.videoId, startSeconds: clip.startSec, endSeconds: clip.endSec ?? undefined });
    }
  }, [clip.videoId, clip.startSec, clip.endSec]);

  // 종료 강제: 진행바로 종료 뒤로 옮겨도 멈춘다
  useEffect(() => {
    if (!started) return;
    const t = setInterval(() => {
      const p = playerRef.current;
      const end = clipRef.current.endSec;
      if (!p || !end || typeof p.getCurrentTime !== "function") return;
      if (p.getCurrentTime() > end + 0.3) {
        p.pauseVideo();
        p.seekTo(end, true);
      }
    }, POLL_MS);
    return () => clearInterval(t);
  }, [started]);

  // 닫을 때 플레이어 정리
  useEffect(() => () => playerRef.current?.destroy(), []);

  if (bare) {
    return (
      <div className="relative h-full w-full bg-black" aria-label={`${label} 재생 중`}>
        <div ref={hostRef} className="absolute inset-0 h-full w-full [&>*]:h-full [&>*]:w-full" />
        {shownError && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/85 p-4 text-center text-sm text-white">{shownError}</div>
        )}
      </div>
    );
  }

  return (
    <section className="overflow-hidden rounded-xl border border-line bg-surface" aria-label="장면 재생">
      <header className="flex items-center justify-between gap-2 px-4 py-2 text-sm">
        <span className="min-w-0 truncate font-semibold">{label}</span>
        <button onClick={() => onClose?.()} className="shrink-0 rounded px-2 py-1 text-muted hover:bg-bg" aria-label="닫기">
          닫기
        </button>
      </header>
      <div className="relative aspect-video w-full bg-black">
        {!started ? (
          <button onClick={() => setStarted(true)} className="group absolute inset-0" aria-label="재생">
            {/* eslint-disable-next-line @next/next/no-img-element -- 정적 내보내기: next/image 최적화 없음, 썸네일 핫링크(설계 8-2) */}
            <img src={thumbnailUrl(clip.videoId)} alt="" className="h-full w-full object-cover opacity-90" />
            <span className="absolute inset-0 m-auto flex h-16 w-16 items-center justify-center rounded-full bg-accent text-2xl text-white shadow-lg group-hover:scale-105">
              ▶
            </span>
          </button>
        ) : (
          <div ref={hostRef} className="absolute inset-0 h-full w-full [&>*]:h-full [&>*]:w-full" />
        )}
        {shownError && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/85 p-4 text-center text-sm text-white">
            {shownError}
          </div>
        )}
      </div>
      <p className="px-4 py-2 text-xs text-muted">
        {clip.precision === "game" ? "이 경기 하이라이트입니다. 이 선수의 장면이 나오지 않을 수도 있습니다." : clip.title}
      </p>
    </section>
  );
}

/** 재생 불가 안내 (09 「영상을 재생할 수 없을 때」). 신고(API-12)는 onError에서 이미 보냈다 */
function ErrorText({ code }: { code: number }) {
  const gone = UNPLAYABLE.has(code);
  return (
    <div>
      <p className="text-base font-bold">{gone ? "이 영상을 재생할 수 없어요" : "영상을 재생하지 못했어요"}</p>
      <p className="mt-1.5 text-white/70">{gone ? "채널에서 비공개로 바뀌었거나 삭제됐을 수 있어요." : `잠시 뒤 다시 시도해 주세요. (오류 ${code})`}</p>
    </div>
  );
}
