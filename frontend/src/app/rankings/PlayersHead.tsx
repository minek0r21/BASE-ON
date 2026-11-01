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
      <nav className="text-[13px] text-muted" aria-label="위치">
        선수 <span aria-hidden>›</span> {tab === "team" ? "팀별 선수" : "능력별 순위"}
      </nav>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[40px] font-extrabold tracking-tight">선수</h1>
          {sub && <p className="mt-1.5 text-sm text-fg-2">{sub}</p>}
        </div>
        <div className="w-full max-w-[360px]"><SearchBox /></div>
      </div>
      <nav className="mt-7 border-b border-line" aria-label="선수 보기">
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
