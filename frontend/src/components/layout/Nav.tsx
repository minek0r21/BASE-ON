"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import SearchBox from "@/components/SearchBox";
import ShareButton from "@/components/ui/ShareButton";
import { getMeta, qk } from "@/lib/api";
import { md } from "@/lib/format";
import { useCrumb } from "@/lib/title";

// 내비 (Figma 2.0/Nav). 메뉴: 홈 · 선수 → 05 능력별 순위 · 장면 → 10 · 팀 → 06 · 일정 → 08 (디자인_2.0_구현 2장)
// 아직 옮기지 않은 화면은 메뉴를 회색으로 두고 누르지 못하게 한다
type Menu = { label: string; href: string | null };
export const MENU: Menu[] = [
  { label: "홈", href: "/" },
  { label: "선수", href: "/rankings/" },
  { label: "장면", href: "/scenes/" },
  { label: "팀", href: "/teams/" },
  { label: "일정", href: "/schedule/" },
];

/** 지금 화면이 이 메뉴인가 — 선수 메뉴는 선수 화면 · 비교까지 */
export function isCurrent(path: string, m: Menu) {
  if (!m.href) return false;
  if (m.href === "/") return path === "/";
  return path.startsWith(m.href.replace(/\/$/, "")) || (m.label === "선수" && (path.startsWith("/players") || path.startsWith("/compare")));
}

export function Logo() {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand md:h-7 md:w-7" aria-hidden>
        <svg viewBox="0 0 20 20" className="h-4 w-4">
          <path d="M10 2 18 10 10 18 2 10Z" fill="none" stroke="#fff" strokeWidth="2" />
          <path d="M10 7.5 12.5 10 10 12.5 7.5 10Z" fill="#fff" />
        </svg>
      </span>
      <span className="text-base font-extrabold tracking-tight md:text-[19px]">BASE:ON</span>
    </span>
  );
}

export default function Nav() {
  const path = usePathname();
  const router = useRouter();
  const crumb = useCrumb();
  const home = path === "/";
  // 탭 메뉴 아래 화면(선수 · 비교 · 경기)은 모바일에서 로고 대신 뒤로 + 위치 (M03 · M07)
  const detail = ["/players", "/compare", "/games"].some((x) => path.startsWith(x));
  const meta = useQuery({ queryKey: qk.meta(), queryFn: ({ signal }) => getMeta(signal) });
  const asOf = meta.data?.data_as_of;

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-raised/95 backdrop-blur">
      <div className="mx-auto flex h-11 max-w-[1200px] items-center gap-4 px-4 md:h-[63px] lg:gap-8 xl:px-0">
        {detail && (
          <div className="-ml-3 flex min-w-0 flex-1 items-center md:hidden">
            <button type="button" aria-label="뒤로" onClick={() => (history.length > 1 ? router.back() : router.push("/"))} className="flex h-11 w-11 shrink-0 items-center justify-center">
              <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="m15 5-7 7 7 7" /></svg>
            </button>
            <span className="truncate text-sm font-medium text-fg-2">{crumb}</span>
          </div>
        )}
        <Link href="/" aria-label="BASE:ON 홈" className={detail ? "hidden md:block" : "flex h-11 items-center md:h-auto"}>
          <Logo />
        </Link>
        <nav aria-label="주 메뉴" className="hidden gap-1 md:flex">
          {MENU.map((m) =>
            m.href ? (
              <Link
                key={m.label}
                href={m.href}
                aria-current={isCurrent(path, m) ? "page" : undefined}
                className="rounded-lg px-2.5 py-1.5 text-[15px] font-medium whitespace-nowrap text-fg-2 transition-colors lg:px-3 duration-[120ms] hover:bg-surface-2 aria-[current=page]:font-bold aria-[current=page]:text-fg"
              >
                {m.label}
              </Link>
            ) : (
              <span key={m.label} className="cursor-not-allowed rounded-lg px-3 py-1.5 text-[15px] font-medium text-muted/60" title="준비 중">
                {m.label}
              </span>
            ),
          )}
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-1 md:gap-4">
          {asOf && <span className={`shrink-0 text-xs text-fg-2 ${detail ? "hidden md:inline" : ""}`} title="경기 기록은 공개 데이터 기준이라 이 날짜까지 있어요"><span className="hidden md:inline">기록 </span>{md(asOf)} 기준</span>}
          {!home && (
            <>
              <div className="hidden w-40 min-w-0 md:block lg:w-64">
                <SearchBox placeholder="선수 · 장면 검색" />
              </div>
              {path.startsWith("/players") && <ShareButton icon className="md:hidden" />}
              {/* 모바일은 칸 대신 ⌕ → 전체 화면 검색 (M02). 홈은 히어로에 검색칸이 있어 안 둔다 */}
              <Link href="/search/" aria-label="선수 검색" className="-mr-3 flex h-11 w-11 items-center justify-center md:hidden">
                <svg viewBox="0 0 24 24" className="h-[22px] w-[22px]" aria-hidden>
                  <circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
                  <path d="m15.5 15.5 4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
