"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import SearchBox from "@/components/SearchBox";
import { getMeta, qk } from "@/lib/api";
import { md } from "@/lib/format";

// 내비 (Figma 2.0/Nav). 메뉴: 홈 · 선수 → 05 능력별 순위 · 장면 → 10 · 팀 → 06 · 일정 → 08 (디자인_2.0_구현 2장)
// 아직 옮기지 않은 화면은 메뉴를 회색으로 두고 누르지 못하게 한다
const MENU: { label: string; href: string | null }[] = [
  { label: "홈", href: "/" },
  { label: "선수", href: "/rankings/" },
  { label: "장면", href: "/scenes/" },
  { label: "팀", href: null },
  { label: "일정", href: null },
];

export function Logo() {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand" aria-hidden>
        <svg viewBox="0 0 20 20" className="h-4 w-4">
          <path d="M10 2 18 10 10 18 2 10Z" fill="none" stroke="#fff" strokeWidth="2" />
          <path d="M10 7.5 12.5 10 10 12.5 7.5 10Z" fill="#fff" />
        </svg>
      </span>
      <span className="text-[19px] font-extrabold tracking-tight">BASE:ON</span>
    </span>
  );
}

export default function Nav() {
  const path = usePathname();
  const home = path === "/";
  const meta = useQuery({ queryKey: qk.meta(), queryFn: ({ signal }) => getMeta(signal) });
  const asOf = meta.data?.data_as_of;

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-raised/95 backdrop-blur">
      <div className="mx-auto flex h-[63px] max-w-[1200px] items-center gap-8 px-4 xl:px-0">
        <Link href="/" aria-label="BASE:ON 홈">
          <Logo />
        </Link>
        <nav aria-label="주 메뉴" className="hidden gap-1 md:flex">
          {MENU.map((m) =>
            m.href ? (
              <Link
                key={m.label}
                href={m.href}
                aria-current={(m.href === "/" ? path === "/" : path.startsWith(m.href.replace(/\/$/, ""))) ? "page" : undefined}
                className="rounded-lg px-3 py-1.5 text-[15px] font-medium text-fg-2 transition-colors duration-[120ms] hover:bg-surface-2 aria-[current=page]:font-bold aria-[current=page]:text-fg"
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
        <div className="ml-auto flex min-w-0 items-center gap-4">
          {asOf && <span className="shrink-0 text-xs text-fg-2" title="경기 기록은 공개 데이터 기준이라 이 날짜까지 있어요">기록 {md(asOf)} 기준</span>}
          {!home && (
            <div className="w-64 min-w-0">
              <SearchBox placeholder="선수 · 장면 검색" />
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
