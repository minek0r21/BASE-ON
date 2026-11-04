"use client";

import { useEffect } from "react";

/**
 * 쿼리 주소 화면(선수 · 팀 · 경기)의 탭 제목. 정적 내보내기라 빌드 때 이름을 몰라서 데이터를 받은 뒤 바꾼다.
 * 경로마다 기본 제목은 그 폴더의 layout.tsx metadata (예: 「선수 · BASE:ON」)
 */
export function useDocTitle(title: string | null | undefined) {
  useEffect(() => {
    if (title) document.title = `${title} · BASE:ON`;
  }, [title]);
}
