"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Wrap } from "@/components/home/common";
import { Retry } from "@/components/ui/Chip";
import { TeamLogo } from "@/components/ui/Media";
import type { Standing } from "@/lib/api";
import { TEAM_NAMES, teamHref, withGwa, type Team } from "@/lib/teams";

const NAV = 64; // 위 메뉴 높이 (top-16)
const BAR = 48; // 따라오는 팀 막대 높이 (h-12)

/**
 * 06 팀 머리 — 팀 색으로 채운 머리 + 가로 순위 띠(10팀, 이 팀 칸만 팀 색).
 * 스크롤하면 머리 글자가 위로 밀리며 옅어지고, 머리 아래 끝이 메뉴에 닿는 순간 같은 색 막대가 이어받는다.
 * 막대 안 엠블럼 · 팀 이름 · 순위는 차례로 들어온다. 움직임 줄이기 설정이면 머리는 그대로, 막대는 바로 나타난다
 */
export default function TeamHead({ name, t, sub, me, all, season, myTeam, setMyTeam, onPick, onRetry }: {
  name: string;
  t: Team;
  sub: string;
  me?: Standing;
  all?: Standing[];
  season?: number;
  myTeam: string | null;
  setMyTeam: (n: string) => void;
  onPick: () => void;
  onRetry?: () => void;
}) {
  const hero = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(false);
  useEffect(() => {
    const el = hero.current;
    if (!el) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    const update = () => {
      frame = 0;
      const r = el.getBoundingClientRect();
      if (!still) el.style.setProperty("--p", String(Math.min(1, Math.max(0, (NAV - r.top) / (r.height - BAR)))));
      setStuck(r.bottom <= NAV + BAR);
    };
    const onScroll = () => { frame ||= requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <>
      <div ref={hero} className="text-white" style={{ background: t.band }}>
        <Wrap className="py-10">
          {/* --p: 머리를 지나간 정도 0 → 1 */}
          <div className="origin-left [opacity:calc(1_-_var(--p,0)*0.7)] [transform:translateY(calc(var(--p,0)*-28px))_scale(calc(1_-_var(--p,0)*0.04))]">
            <nav className="text-[13px] text-white/70" aria-label="위치">팀 <span aria-hidden>›</span> {t.full}</nav>
            <div className="mt-5 flex gap-7">
              <div className="flex h-[136px] w-[136px] shrink-0 items-center justify-center rounded-3xl bg-white">
                <TeamLogo team={name} height={80} />
              </div>
              <div className="min-w-0">
                <h1 className="text-[44px] leading-tight font-extrabold tracking-tight">{t.full}</h1>
                <p className="mt-1.5 text-sm text-white/80">{sub}</p>
                {me && all && <Tags me={me} all={all} t={t} />}
                <Actions name={name} band={t.band} myTeam={myTeam} setMyTeam={setMyTeam} onPick={onPick} />
              </div>
            </div>
          </div>
        </Wrap>
      </div>
      <Wrap>
        {!all && onRetry
          ? <div className="mt-8"><Retry text="팀 순위를 불러오지 못했어요" onRetry={onRetry} /></div>
          : <StandingStrip all={all} me={name} t={t} season={season} />}
      </Wrap>
      <StickyBar show={stuck} t={t} name={name} me={me} />
    </>
  );
}

function Actions({ name, band, myTeam, setMyTeam, onPick }: { name: string; band: string; myTeam: string | null; setMyTeam: (n: string) => void; onPick: () => void }) {
  const [open, setOpen] = useState(false);
  const ghost = "border border-white/40 text-white hover:bg-white/10";
  return (
    <>
      <div className="mt-4 flex flex-wrap gap-2">
        {myTeam === name ? (
          <span className={`flex h-10 items-center rounded-full px-4 text-sm font-bold ${ghost}`}>응원팀</span>
        ) : (
          <button onClick={() => setMyTeam(name)} className="h-10 rounded-full bg-white px-4 text-sm font-bold hover:opacity-90" style={{ color: band }}>
            응원팀으로 정하기
          </button>
        )}
        <button onClick={() => setOpen(!open)} aria-expanded={open} className={`h-10 rounded-full px-4 text-sm font-medium ${ghost}`}>
          다른 팀 보기
        </button>
      </div>
      {open && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {TEAM_NAMES.filter((x) => x !== name).map((x) => (
            <li key={x}>
              <Link href={teamHref(x)} onClick={() => { setOpen(false); onPick(); }} className="flex h-10 items-center gap-2 rounded-full border border-line bg-surface pr-4 pl-3 text-sm font-medium text-fg hover:bg-surface-2">
                <TeamLogo team={x} height={18} /> {x}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** 「정규시즌 4위 · 1위와 8.0경기」 · 「5위 두산과 1.0경기 차」(바로 아래 팀, 꼴찌면 바로 위 팀) */
function Tags({ me, all, t }: { me: Standing; all: Standing[]; t: Team }) {
  const near = all.find((x) => x.rank === me.rank + 1) ?? all.find((x) => x.rank === me.rank - 1);
  return (
    <p className="mt-3 flex flex-wrap gap-2 text-xs font-bold">
      <span className="rounded-lg bg-white px-2.5 py-1" style={{ color: t.band }}>
        정규시즌 {me.rank}위{me.rank > 1 && ` · 1위와 ${me.gb.toFixed(1)}경기`}
      </span>
      {near && (
        <span className="rounded-lg bg-white/15 px-2.5 py-1 text-white">
          {near.rank}위 {withGwa(near.team)} {Math.abs(near.gb - me.gb).toFixed(1)}경기 차
        </span>
      )}
    </p>
  );
}

/** 가로 순위 띠 — 10팀 한 줄. 이 팀 칸만 팀 색 */
function StandingStrip({ all, me, t, season }: { all?: Standing[]; me: string; t: Team; season?: number }) {
  if (!all) return <div className="mt-8 h-[92px] animate-pulse rounded-3xl bg-surface-2" />;
  return (
    <section className="mt-8">
      <p className="mb-2.5 flex items-baseline gap-2 text-sm font-bold">
        {season} 순위 <span className="text-xs font-medium text-muted">오른쪽 숫자는 1위와 경기 차</span>
      </p>
      <ol className="grid grid-cols-5 gap-1.5 lg:grid-cols-10">
        {all.map((x) => {
          const on = x.team === me;
          return (
            <li key={x.team}>
              <Link
                href={teamHref(x.team)}
                aria-current={on ? "page" : undefined}
                className={`flex h-[60px] items-center gap-2 rounded-2xl px-3 ${on ? "text-white" : "border border-line bg-surface hover:bg-surface-2"}`}
                style={on ? { background: t.band } : undefined}
              >
                <span className="font-display text-lg leading-none font-extrabold">{x.rank}</span>
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${on ? "bg-white" : ""}`}>
                  <TeamLogo team={x.team} height={18} />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-bold">{x.team}</span>
                  <span className={`block font-num text-[11px] ${on ? "text-white/80" : "text-muted"}`}>{x.gb === 0 ? "–" : x.gb.toFixed(1)}</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** 따라오는 팀 막대 — 막대는 옅게 내려오고, 안의 세 덩어리는 60ms씩 늦게 들어온다 */
function StickyBar({ show, t, name, me }: { show: boolean; t: Team; name: string; me?: Standing }) {
  const step = `transition-[opacity,translate,scale] duration-300 ease-out ${show ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"}`;
  const delay = (i: number) => ({ transitionDelay: show ? `${80 + i * 60}ms` : "0ms" });
  return (
    <div
      className={`fixed inset-x-0 top-16 z-20 text-white transition-[opacity,translate,box-shadow] duration-200 ease-out ${show ? "translate-y-0 opacity-100 shadow-md" : "pointer-events-none -translate-y-2 opacity-0"}`}
      style={{ background: t.band }}
      aria-hidden={!show}
    >
      <Wrap className="flex h-12 items-center gap-3">
        <span className={`${step} flex h-8 w-8 items-center justify-center rounded-full bg-white ${show ? "scale-100" : "scale-75"}`} style={delay(0)}>
          <TeamLogo team={name} height={20} />
        </span>
        <span className={`${step} text-[15px] font-bold`} style={delay(1)}>{t.full}</span>
        {me && <span className={`${step} text-[13px] text-white/80`} style={delay(2)}>{me.rank}위 · {me.w}승 {me.d}무 {me.l}패</span>}
      </Wrap>
    </div>
  );
}
