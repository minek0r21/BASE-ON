"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import SearchBox, { playerHref } from "@/components/SearchBox";
import { PlayerAvatar } from "@/components/ui/Media";
import { rankingsHref } from "@/lib/axes";
import { useRecentPlayers } from "@/lib/local";

const Label = ({ children }: { children: ReactNode }) => <h2 className="px-4 pt-4 pb-2 text-[13px] font-bold text-fg-2">{children}</h2>;
const Arrow = () => <span className="shrink-0 text-xl text-fg-2" aria-hidden>›</span>;

function Way({ href, title, sub }: { href: string; title: string; sub: string }) {
  return (
    <Link href={href} className="flex items-center justify-between gap-3 rounded-2xl bg-surface px-4 py-3">
      <span className="min-w-0">
        <span className="block text-[15px] font-bold">{title}</span>
        <span className="block truncate text-[13px] text-fg-2">{sub}</span>
      </span>
      <Arrow />
    </Link>
  );
}

// M02 검색 (Figma 308:1785 · 308:1702). 모바일 상단 ⌕로 들어오는 전체 화면 — 주소가 있어야 브라우저 뒤로 가기로 닫힌다.
// 내비 · 하단 탭 위를 덮고, md 이상은 내비에 검색칸이 있어 일반 화면으로 둔다
export default function SearchPage() {
  const router = useRouter();
  const recent = useRecentPlayers();

  const back = (
    <button type="button" aria-label="뒤로" onClick={() => (history.length > 1 ? router.back() : router.push("/"))}
            className="flex h-11 w-11 shrink-0 items-center justify-center">
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="m15 5-7 7 7 7" />
      </svg>
    </button>
  );

  const idle = (
    <>
      {recent.length > 0 && (
        <>
          <Label>최근 본 선수</Label>
          <ul>
            {recent.slice(0, 3).map((r) => (
              <li key={r.id}>
                <Link href={playerHref(r.id)} className="flex min-h-[60px] items-center gap-3 px-4 py-2">
                  <PlayerAvatar id={r.id} name={r.name} team={r.team} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-base font-bold">{r.name}</span>
                    {r.team && <span className="block text-[13px] text-fg-2">{r.team}</span>}
                  </span>
                  <Arrow />
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
      <Label>선수 찾는 다른 길</Label>
      <div className="space-y-2 px-4">
        <Way href="/rankings/" title="팀별 선수" sub="10개 팀 · 포지션별" />
        <Way href={rankingsHref("batter")} title="능력별 순위" sub="삼진 회피 · 안타 생산 · 파워 · 선구안 · 꾸준함" />
      </div>
      <p className="px-4 pt-4 text-xs leading-relaxed break-keep text-fg-2">찾을 수 있는 범위: 2024~2026 1군 기록 · 이름 · 초성(ㄱㄷㅇ) · 옛 이름</p>
    </>
  );

  return (
    <div className="fixed inset-0 z-40 overflow-y-auto bg-bg pb-[calc(1rem+env(safe-area-inset-bottom))] md:static md:mx-auto md:max-w-[560px] md:pt-6">
      <SearchBox autoFocus screen={{ back, idle }} />
    </div>
  );
}
