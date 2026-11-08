"use client";

import Link from "next/link";
import SearchBox from "@/components/SearchBox";
import Slide from "@/components/ui/Slide";
import { rankingsHref } from "@/lib/axes";

/** 내비 「선수」 머리 — 제목 · 기준 한 줄 · 이름 찾기, 아래 탭 「팀별 선수 | 능력별 순위」 (10-31 사용자: 첫 화면은 팀별 선수) */
export default function PlayersHead({ tab, sub }: { tab: "team" | "rank"; sub?: string }) {
  const tabs = [
    { key: "team", label: "팀별 선수", href: "/rankings/" },
    { key: "rank", label: "능력별 순위", href: rankingsHref("batter") },
  ] as const;
  return (
    <>
      <nav className="hidden text-[13px] text-muted md:block" aria-label="위치">
        선수 <span aria-hidden>›</span> {tab === "team" ? "팀별 선수" : "능력별 순위"}
      </nav>
      <div className="flex flex-wrap items-end justify-between gap-4 md:mt-3">
        <div>
          <h1 className="text-[26px] font-black tracking-tight md:text-[40px] md:font-extrabold">선수</h1>
          {/* 기준일은 내비가 먼저 받아 두면 첫 그림부터 들어온다 — 칸을 늘 그려 두어 서버 HTML과 어긋나지 않게 */}
          {sub !== undefined && <p className="mt-1.5 min-h-5 text-xs text-fg-2 md:text-sm" suppressHydrationWarning>{sub}</p>}
        </div>
        <div className="hidden w-full max-w-[360px] md:block"><SearchBox /></div>
      </div>
      <nav className="mt-2 border-b border-line md:mt-7" aria-label="선수 보기">
        <Slide line mark="-bottom-px h-0.5 bg-fg" className="flex gap-7">
        {tabs.map((x) => (
          <Link
            key={x.key}
            href={x.href}
            aria-current={tab === x.key ? "page" : undefined}
            className="relative flex h-12 items-center text-[15px] font-medium text-fg-2 hover:text-fg aria-[current=page]:font-bold aria-[current=page]:text-fg"
          >
            {x.label}
          </Link>
        ))}
        </Slide>
      </nav>
    </>
  );
}
