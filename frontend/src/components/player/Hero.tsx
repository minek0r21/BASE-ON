"use client";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기: next/image 최적화 서버가 없다 */
import Link from "next/link";
import { useState } from "react";
import { clipLength } from "@/components/home/common";
import ScenePlayer from "@/components/ScenePlayer";
import { PlayGlyph, TeamLogo, mmss } from "@/components/ui/Media";
import ShareButton, { BTN } from "@/components/ui/ShareButton";
import type { Clip, PlayerSummary } from "@/lib/api";
import { axisCopy } from "@/lib/axes";
import { innings, md, rate3 } from "@/lib/format";
import { photoUrl, team as teamOf, teamHref } from "@/lib/teams";

export type Role = "batter" | "pitcher";


/**
 * 03 · 03b 선수 머리 (Figma 138:519 · 139:1127) — 왼쪽 사진 · 이름 · 프로필 한 줄 · 꼬리표 2개 · 비교하기 / 공유,
 * 오른쪽 대표 장면 플레이어(썸네일 + ▶, 누르면 그 자리에서 재생). 바탕은 흰색 (10-30 사용자).
 * 사진 180×225 = 영상 칸(400px 16:9) 높이 — 사진과 영상의 위아래 끝을 맞춘다 (10-31 사용자).
 * 대표 장면 = 타자 최근 홈런 장면, 투수 지표 장면이 있으면 그것 · 없으면 최근 등판 장면 (장면.md 6장).
 * 「관심 선수」는 도착지가 정해질 때까지 넣지 않는다 (10-30 보류)
 */
export default function Hero({ p, role, asOf, onCompare }: {
  p: PlayerSummary;
  role: Role;
  asOf: string | null;
  onCompare: () => void;
}) {
  const t = teamOf(p.team);
  const scene = representative(p, role);
  const tags = heroTags(p, role);
  const pos = role === "pitcher" && p.pitching ? `투수 (${p.pitching.roleLabel})` : p.position;
  const meta = [p.backNumber != null && `#${p.backNumber}`, t?.full ?? p.team, pos, p.batsThrows, p.birthDate && birthText(p.birthDate, asOf)]
    .filter(Boolean) as string[];

  return (
    <div className={`grid items-start gap-8 ${scene ? "lg:grid-cols-[minmax(0,1fr)_400px]" : ""}`}>
      <div className="flex flex-col gap-6 sm:flex-row">
        <Photo id={p.playerId} name={p.name} />
        <div className="min-w-0">
          <h1 className="flex items-center gap-3 text-[48px] leading-tight font-extrabold tracking-tight">
            {p.name} <TeamLogo team={p.team} height={28} />
          </h1>
          <p className="mt-2 text-[15px] text-fg-2">{meta.join(" · ")}</p>
          {tags.length > 0 && (
            <p className="mt-4 flex flex-wrap gap-2 text-[13px] font-bold">
              {tags.map((x, i) => (
                <span key={x.text} className={`flex items-center gap-1 rounded-lg px-3 py-1.5 ${i === 0 ? "bg-accent text-white" : "bg-surface-2 text-fg-2"}`}>
                  {x.trophy && <Trophy />} {x.text}
                </span>
              ))}
            </p>
          )}
          <div className="mt-5 flex flex-wrap gap-2">
            <button onClick={onCompare} className={BTN}>비교하기</button>
            <ShareButton />
          </div>
        </div>
      </div>
      {scene && <SceneBox name={p.name} scene={scene} />}
    </div>
  );
}

/** 대표 장면 — 처음엔 썸네일 + ▶ (영상은 누를 때 불러온다), 누르면 그 자리에서 재생 */
function SceneBox({ name, scene }: { name: string; scene: { clip: Clip; title: string; sub: string } }) {
  const [on, setOn] = useState(false);
  return (
    <figure className="min-w-0">
      <div className="relative aspect-video overflow-hidden rounded-2xl bg-night">
        {on ? (
          <ScenePlayer bare clip={scene.clip} label={`${name} · ${scene.title}`} />
        ) : (
          <button onClick={() => setOn(true)} className="group absolute inset-0" aria-label={`대표 장면 ${scene.title} 재생`}>
            <img src={bigThumb(scene.clip.videoId)} alt="" className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.02]" />
            <span className="absolute bottom-3 left-3 flex h-11 w-11 items-center justify-center rounded-full bg-accent text-white">
              <PlayGlyph size={14} />
            </span>
            <span className="absolute top-3 right-3 rounded-md bg-black/70 px-1.5 py-0.5 font-num text-[11px] font-semibold text-white">{mmss(clipLength(scene.clip))}</span>
          </button>
        )}
      </div>
      <figcaption className="mt-2 flex items-baseline justify-between gap-3">
        <span className="min-w-0 truncate">
          <span className="text-xs font-bold text-fg-2">대표 장면</span>
          <span className="ml-2 text-[15px] font-bold">{scene.title}</span>
          <span className="ml-2 text-[13px] text-fg-2">{scene.sub}</span>
        </span>
        {on && <button onClick={() => setOn(false)} className="shrink-0 text-[13px] font-bold text-fg-2 hover:underline">닫기</button>}
      </figcaption>
    </figure>
  );
}

/** 큰 칸이라 mqdefault(320px)보다 큰 hqdefault — 4:3 위아래 검은 띠는 object-cover로 잘린다 */
export const bigThumb = (videoId: string) => `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;

function Photo({ id, name }: { id: string; name: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="flex h-[225px] w-[180px] shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-line bg-surface">
      {failed ? (
        <span className="text-5xl font-extrabold text-muted" aria-hidden>{name.slice(0, 1)}</span>
      ) : (
        <img src={photoUrl(id)} alt={`${name} 사진`} className="h-full w-full object-cover object-top" onError={() => setFailed(true)} />
      )}
    </div>
  );
}

function Trophy() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4ZM7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4" />
    </svg>
  );
}

/** 「2003. 10. 2. (22세)」 — 만 나이, 기록 기준일 기준 */
function birthText(birth: string, asOf: string | null) {
  const [y, m, d] = birth.split("-").map(Number);
  const ref = asOf ? asOf.split("-").map(Number) : [new Date().getFullYear(), new Date().getMonth() + 1, new Date().getDate()];
  const age = ref[0] - y - (ref[1] < m || (ref[1] === m && ref[2] < d) ? 1 : 0);
  return `${y}. ${m}. ${d}. (${age}세)`;
}

/** 대표 장면 + 설명 문구 */
export function representative(p: PlayerSummary, role: Role): { clip: Clip; title: string; sub: string } | null {
  if (role === "pitcher") {
    const pi = p.pitching;
    const s = pi?.axes.find((a) => a.scene)?.scene ?? pi?.recentScene;
    if (!s) return null;
    return { clip: s.clip, title: `${md(s.date)} ${innings(s.line.outs)}이닝`, sub: "등판 장면" };
  }
  const s = p.recentScene;
  if (!s) return null;
  return { clip: s.clip, title: `${s.hrSeq ? `${s.hrSeq}호 ` : ""}홈런`, sub: `${md(s.date)} ${s.opponent}전` };
}

/** 꼬리표 2개: ① 시즌 기록 중 가장 높은 등수(3위 안이면 트로피) ② 가장 강한 능력 */
function heroTags(p: PlayerSummary, role: Role): { text: string; trophy: boolean }[] {
  const out: { text: string; trophy: boolean }[] = [];
  const season = p.season ?? "";
  if (role === "batter" && p.statRanks && p.stats) {
    const st = p.stats;
    const cand = [
      { k: "hr", label: "홈런", v: `${st.hr}개` },
      { k: "ops", label: "OPS", v: rate3(st.ops) },
      { k: "slg", label: "장타율", v: rate3(st.slg) },
      { k: "obp", label: "출루율", v: rate3(st.obp) },
      { k: "avg", label: "타율", v: rate3(st.avg) },
    ] as const;
    const best = cand.map((c) => ({ ...c, r: p.statRanks?.[c.k] ?? 99 })).sort((a, b) => a.r - b.r)[0];
    if (best && best.r <= 10) out.push({ text: `${season} ${best.label} ${best.r}위 · ${best.v}`, trophy: best.r <= 3 });
  }
  if (role === "pitcher" && p.pitching?.statRanks) {
    const pi = p.pitching;
    const cand = [
      { k: "outs", label: "최다 이닝", v: `${innings(pi.outs)}이닝` },
      { k: "so", label: "탈삼진", v: `${pi.so}개` },
      { k: "whip", label: "WHIP", v: pi.whip?.toFixed(2) ?? "–" },
      { k: "avg", label: "피안타율", v: rate3(pi.avg) },
    ] as const;
    const best = cand.map((c) => ({ ...c, r: pi.statRanks?.[c.k] ?? 99 })).sort((a, b) => a.r - b.r)[0];
    if (best && best.r <= 10) out.push({ text: `${season} ${best.label} ${best.r}위 · ${best.v}`, trophy: best.r <= 3 });
  }
  const axes = role === "pitcher" ? p.pitching?.axes ?? [] : p.axes;
  const strong = axes.filter((a) => a.percentile != null && a.rank != null).sort((a, b) => b.percentile! - a.percentile!)[0];
  if (strong) out.push({ text: `${strong.label} ${strong.rank}위 · ${axisCopy(strong.key)?.fmt(strong.value) ?? ""}`, trophy: false });
  return out;
}

export function teamCrumb(team: string | null) {
  const t = teamOf(team);
  return t ? <Link href={teamHref(t.name)} className="hover:underline">{t.full}</Link> : null;
}
