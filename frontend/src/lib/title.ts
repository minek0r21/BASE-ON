"use client";

import { useEffect, useSyncExternalStore } from "react";

/**
 * 쿼리 주소 화면(선수 · 팀 · 경기)의 탭 제목. 정적 내보내기라 빌드 때 이름을 몰라서 데이터를 받은 뒤 바꾼다.
 * 경로마다 기본 제목은 그 폴더의 layout.tsx metadata (예: 「선수 · BASE:ON」)
 */
/** 모바일 상단 바의 위치 글자 (「선수 › KIA 타이거즈」). 화면이 정하고 내비가 읽는다 */
let crumb: string | null = null;
const crumbListeners = new Set<() => void>();
const setCrumb = (v: string | null) => { crumb = v; crumbListeners.forEach((l) => l()); };
export const useCrumb = () => useSyncExternalStore((l) => { crumbListeners.add(l); return () => { crumbListeners.delete(l); }; }, () => crumb, () => null);
export function useNavCrumb(text: string | null) {
  useEffect(() => {
    setCrumb(text);
    return () => setCrumb(null);
  }, [text]);
}

export function useDocTitle(title: string | null | undefined) {
  useEffect(() => {
    if (title) document.title = `${title} · BASE:ON`;
  }, [title]);
}
