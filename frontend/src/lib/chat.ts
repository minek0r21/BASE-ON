/**
 * 챗봇 API (POST /chat) — 질문 하나 → 답 하나. 백엔드: backend/app/chat/service.py
 * 대화 상태는 서버에 남기지 않는다. 앞 답의 context와 되묻기에서 고른 값(resolved)을 화면이 다시 보내 준다.
 */
import { API_BASE, type Clip } from "./api";

export type ChatVideo = { video_id: string; title: string; duration_sec: number | null; start_sec: number; end_sec: number | null; precision: string };

export type PaRow = {
  pa_id: string; date: string; batter: string; pitcher: string; bat_team: string; pit_team: string;
  inning: number; inning_half: string; result: string; runs: number | null; situation: string | null; video: ChatVideo | null;
};
export type GameRow = { game_pk: string; date: string; is_home: boolean; team: string; opponent: string; team_score: number; opp_score: number; result: string };

export type ChatAnswer = {
  type: "answer";
  text: string;
  menu?: "pa" | "games" | "stats" | "other";
  conditions?: string[];
  total?: number;
  shown?: number;
  rows?: (PaRow | GameRow)[];
  record?: { win: number; loss: number; draw: number; win_pct: number | null };
  name?: string;
  season?: number;
  batting?: Record<string, number | boolean | string | null> | null;
  pitching?: Record<string, number | boolean | string | null> | null;
  columns?: string[];
  table?: unknown[][];
  note?: string;
  context?: Record<string, unknown>;
  /** DB의 마지막 경기일 (답이 이 날까지의 기록이라는 뜻) */
  as_of?: string;
  /** 조회하지 않고 끝난 답의 까닭: other_off(메뉴 밖) · after_as_of(기준일 뒤) · limited(호출 제한) · off(꺼짐) */
  reason?: "other_off" | "after_as_of" | "limited" | "off";
};
export type ChatClarify = { type: "clarify"; slot: string; text: string; options: { value: string | number; label: string }[] };
export type ChatReply = ChatAnswer | ChatClarify;

/** 챗봇을 켤지 (서버에 AI 키가 있나) + 기록 기준일. 못 받으면 끈 것으로 본다 */
export async function getChatStatus(): Promise<{ enabled: boolean; as_of: string | null }> {
  try {
    const res = await fetch(`${API_BASE}/chat/status`);
    return res.ok ? await res.json() : { enabled: false, as_of: null };
  } catch {
    return { enabled: false, as_of: null };
  }
}

export async function postChat(body: { message: string; context?: Record<string, unknown> | null; resolved?: Record<string, unknown> | null }): Promise<ChatReply> {
  const res = await fetch(`${API_BASE}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    return { type: "answer", text: err?.error?.message ?? `답을 가져오지 못했어요 (${res.status})` };
  }
  return res.json();
}

/** 챗봇 영상 → 기존 재생기(ScenePlayer)가 쓰는 Clip */
export const toClip = (v: ChatVideo): Clip => ({
  videoId: v.video_id, title: v.title, startSec: v.start_sec ?? 0, endSec: v.end_sec, durationSec: v.duration_sec,
  precision: (v.precision as Clip["precision"]) ?? "scene",
});
