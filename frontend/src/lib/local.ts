"use client";

import { useSyncExternalStore } from "react";

/**
 * 이 브라우저에만 저장하는 값 — 로그인이 없다 (화면에 「이 브라우저에만 저장돼요」를 적는다, 디자인_2.0_구현 6장)
 *   응원팀: 팀 이름 하나 / 최근 본 선수: 선수 화면을 열 때마다 앞에 넣고 최대 6명
 * 저장소가 막혀 있어도(사생활 보호 창 등) 화면은 빈 값으로 그려진다.
 */
const KEY_TEAM = "baseon.myTeam";
const KEY_RECENT = "baseon.recentPlayers";
const RECENT_MAX = 6;

export type RecentPlayer = { id: string; name: string; team: string | null };

const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
function subscribe(l: () => void) {
  listeners.add(l);
  window.addEventListener("storage", l);
  return () => {
    listeners.delete(l);
    window.removeEventListener("storage", l);
  };
}
function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string | null) {
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* 저장 못 해도 화면은 그대로 */
  }
  emit();
}

export function useMyTeam(): [string | null, (team: string | null) => void] {
  const v = useSyncExternalStore(subscribe, () => read(KEY_TEAM), () => null);
  return [v, (t) => write(KEY_TEAM, t)];
}

let recentCache: { raw: string | null; list: RecentPlayer[] } = { raw: null, list: [] };
function readRecent(): RecentPlayer[] {
  const raw = read(KEY_RECENT);
  if (raw !== recentCache.raw) {
    let list: RecentPlayer[] = [];
    try {
      list = raw ? (JSON.parse(raw) as RecentPlayer[]).filter((p) => p && p.id && p.name) : [];
    } catch {
      list = [];
    }
    recentCache = { raw, list };
  }
  return recentCache.list;
}
const EMPTY: RecentPlayer[] = [];

export function useRecentPlayers(): RecentPlayer[] {
  return useSyncExternalStore(subscribe, readRecent, () => EMPTY);
}

export function pushRecentPlayer(p: RecentPlayer) {
  const list = [p, ...readRecent().filter((x) => x.id !== p.id)].slice(0, RECENT_MAX);
  write(KEY_RECENT, JSON.stringify(list));
}
