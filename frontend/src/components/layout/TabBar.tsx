"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { isCurrent, MENU } from "./Nav";

// 모바일 하단 탭 (Figma 모바일/Tab bar 306:1795). 메뉴는 데스크톱 내비와 같고, md 이상에서는 내비가 대신한다.
// 웹페이지라 브라우저 툴바 · 홈 표시줄을 피해 안전 영역 위에 놓는다 — 높이를 바꾸면 layout.tsx의 body 아래 여백도 같이 바꾼다
const ICON: Record<string, ReactNode> = {
  홈: <path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z" />,
  선수: <><circle cx="12" cy="8" r="4" /><path d="M4.5 20.5c.8-4 3.8-6 7.5-6s6.7 2 7.5 6" /></>,
  장면: <><rect x="3" y="5" width="18" height="14" rx="3" /><path d="m10.5 9.5 4 2.5-4 2.5z" /></>,
  팀: <path d="M12 3.5 19.5 6v6c0 4.3-3 7.2-7.5 8.5C7.5 19.2 4.5 16.3 4.5 12V6z" />,
  일정: <><rect x="3.5" y="5" width="17" height="15.5" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></>,
};

export default function TabBar() {
  const path = usePathname();
  if (path.startsWith("/games")) return null; // 경기 상세는 영상을 보는 어두운 화면 (M04b)
  return (
    <nav aria-label="주 메뉴" className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-raised/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
      <ul className="flex h-14">
        {MENU.map((m) => m.href && (
          <li key={m.label} className="flex-1">
            <Link
              href={m.href}
              aria-current={isCurrent(path, m) ? "page" : undefined}
              className="flex h-full flex-col items-center justify-center gap-0.5 text-xs font-medium text-fg-2 aria-[current=page]:font-bold aria-[current=page]:text-brand-text"
            >
              <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" aria-hidden>
                {ICON[m.label]}
              </svg>
              {m.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
