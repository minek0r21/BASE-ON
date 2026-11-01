"use client";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기: next/image 최적화 서버가 없다 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Wrap } from "@/components/home/common";
import { playerHref } from "@/components/SearchBox";
import { Empty } from "@/components/ui/Chip";
import { PlayGlyph, TeamLogo } from "@/components/ui/Media";
import { getMeta, getRoster, getStandings, qk, type AxisKey, type PitchAxisKey, type RosterBatter, type RosterPitcher } from "@/lib/api";
import { josa, verdict } from "@/lib/abilities";
import { axisCopy } from "@/lib/axes";
import { innings, md, rate3 } from "@/lib/format";
import { useMyTeam, useRosterTeam } from "@/lib/local";
import { photoUrl, team as teamOf, teamHref } from "@/lib/teams";
import PlayersHead from "./PlayersHead";
import TeamPicker, { useTeamOrder } from "./TeamPicker";

/** 응원팀 설정이 승인되면 true — 처음 팀을 응원팀으로 (10-31 사용자). 그 전엔 마지막으로 고른 팀 → 순위 1위 팀 */
const MY_TEAM_FIRST = false;
const STARTERS = 9;   // 「주전」 = 팀 타석 상위 9명
const SHOW_RANK = 5;  // 팀 안 순위는 5위 안일 때만 붙인다

/** 한 줄 소개 — 가장 강한 능력의 판정(선수 화면 능력 칸과 같은 문구) + 리그 위치. 비교 대상이 아니면 note만 */
type Lead = { text: string; pos: string; pct: number } | { note: string };
type Card = { id: string; name: string; back: string | number | null; meta: string; role: string | null; lead: Lead; main: string; sub: string; scenes: number };
type Group = { key: string; title: string; sub: string; cards: Card[] };

/**
 * 선수 탭 첫 화면 「팀별 선수」 — 팀 로고 줄(순위순)에서 한 팀을 고르면 그 시즌 그 팀에서 뛴 선수 전원을 포지션별 카드로.
 * 카드는 입문 팬 기준(10-31 사용자): 용어(WHIP · OPS · 지표 이름) 대신 판정 한 줄 + 그 능력 막대 하나 + 익숙한 기록(팀 안 순위).
 * 06 팀 화면 표(규정타석 50% · 선발만)와 달리 구원 · 백업 · 신인까지 다 나온다
 */
export default function TeamRoster() {
  const params = useSearchParams();
  const router = useRouter();
  const [myTeam] = useMyTeam();
  const [lastTeam, setLastTeam] = useRosterTeam();
  const order = useTeamOrder();
  const meta = useQuery({ queryKey: qk.meta(), queryFn: ({ signal }) => getMeta(signal) });
  const standings = useQuery({ queryKey: qk.standings(), queryFn: ({ signal }) => getStandings(signal) });

  const valid = (t: string | null | undefined) => (t && teamOf(t) ? t : null);
  const name = valid(params.get("team")) ?? (MY_TEAM_FIRST ? valid(myTeam) : null) ?? valid(lastTeam) ?? order[0];
  const pick = (t: string | null) => {
    if (!t) return;
    setLastTeam(t);
    router.replace(`/rankings/?${new URLSearchParams({ team: t })}`, { scroll: false });
  };

  const q = useQuery({ queryKey: qk.roster(name), queryFn: ({ signal }) => getRoster(name, signal) });
  const t = teamOf(name)!;
  const st = standings.data?.teams.find((x) => x.team === name);
  const asOf = meta.data?.data_as_of;
  const groups = q.data ? groupsOf(q.data.batters, q.data.pitchers) : [];
  const count = (pitch: boolean) => groups.filter((g) => g.key.startsWith("p-") === pitch).reduce((n, g) => n + g.cards.length, 0);

  return (
    <Wrap className="pt-10 pb-24">
      <PlayersHead tab="team" sub={[q.data && `${q.data.season} 정규시즌`, asOf && `${md(asOf)} 기준`, "출전 선수 전원"].filter(Boolean).join(" · ")} />
      <div className="mt-6"><TeamPicker value={name} onPick={pick} /></div>

      <div className="mt-10 flex flex-wrap items-end justify-between gap-4 border-t-4 pt-6" style={{ borderColor: t.band }}>
        <div className="flex items-center gap-4">
          <TeamLogo team={name} height={44} />
          <div>
            <h2 className="text-[28px] font-extrabold tracking-tight">{t.full}</h2>
            <p className="mt-0.5 text-[13px] text-fg-2">
              {[st && `${st.rank}위 · ${st.w}승 ${st.d}무 ${st.l}패`, q.data && `선수 ${count(true) + count(false)}명 · 타자 ${count(false)} · 투수 ${count(true)}`].filter(Boolean).join(" · ")}
            </p>
          </div>
        </div>
        <Link href={teamHref(name)} className="text-sm font-bold text-brand-text hover:underline">팀 화면 ›</Link>
      </div>

      {q.isError ? (
        <div className="mt-8"><Empty text="선수 명단을 불러오지 못했어요" action={{ label: "다시 시도", onClick: () => q.refetch() }} /></div>
      ) : !q.data ? (
        <div className="mt-8 h-[640px] animate-pulse rounded-3xl bg-surface-2" />
      ) : (
        groups.filter((g) => g.cards.length).map((g) => (
          <section key={g.key} className="mt-12 animate-appear">
            <div className="mb-4 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
              <h3 className="text-xl font-bold">{g.title}</h3>
              <span className="font-num text-[15px] font-bold text-fg-2">{g.cards.length}</span>
              <span className="text-xs text-fg-2">{g.sub}</span>
            </div>
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {g.cards.map((c) => <li key={c.id}><RosterCard c={c} team={name} /></li>)}
            </ul>
          </section>
        ))
      )}
    </Wrap>
  );
}

/** 팀 안 등수 (값이 클수록 위, 같으면 공동) */
function teamRank<T>(rows: T[], val: (r: T) => number | null) {
  const vs = rows.map(val).filter((v): v is number => v != null);
  return (r: T) => { const v = val(r); return v == null ? null : 1 + vs.filter((x) => x > v).length; };
}
const withRank = (text: string, rank: number | null) => (rank != null && rank <= SHOW_RANK ? `${text} · 팀 ${rank}위` : text);

/** who = 비교 무리 (리그 · 선발 중 · 구원 중). 상위 N = 100 − 백분위, 50% 넘으면 하위 (lib/position과 같은 문턱) */
function lead(p: Record<string, number | null> | null, who: string, note: string): Lead {
  const best = p && Object.entries(p).filter((e): e is [string, number] => e[1] != null).sort((a, b) => b[1] - a[1])[0];
  if (!best) return { note };
  const top = Math.max(1, Math.round(100 - best[1]));
  const v = verdict(best[0] as AxisKey | PitchAxisKey, best[1]);
  const chip = axisCopy(best[0])?.chip ?? best[0];
  // 「중간이에요」만으로는 어느 능력인지 몰라서 능력 이름을 붙인다
  return { text: v === "중간이에요" ? `${josa(chip, "은", "는")} 중간이에요` : v, pos:`${who} ${top <= 50 ? `상위 ${top}` : `하위 ${Math.max(1, Math.round(best[1]))}`}%`, pct: best[1] };
}

function groupsOf(batters: RosterBatter[], pitchers: RosterPitcher[]): Group[] {
  const pitcherIds = new Set(pitchers.map((p) => p.player_id));
  const fielders = batters.filter((b) => !pitcherIds.has(b.player_id) && b.position !== "투수"); // 타석에 선 투수는 투수 묶음에만
  const paRank = teamRank(fielders, (b) => b.pa);
  const hrRank = teamRank(fielders, (b) => b.hr);
  const hRank = teamRank(fielders, (b) => b.h);
  const avgRank = teamRank(fielders, (b) => ((b.pa ?? 0) >= 100 ? b.avg : null)); // 타율은 100타석 넘는 선수끼리
  const outsRank = teamRank(pitchers, (p) => p.outs);
  const soRank = teamRank(pitchers, (p) => p.so);
  const gRank = teamRank(pitchers, (p) => p.g);

  const bCard = (b: RosterBatter): Card => {
    // 익숙한 기록 셋(홈런 · 타율 · 안타) 중 팀 안 등수가 가장 높은 것을 앞에
    const cands = [
      { r: hrRank(b), text: `홈런 ${b.hr ?? 0}개` },
      { r: avgRank(b), text: `타율 ${rate3(b.avg)}` },
      { r: hRank(b), text: `안타 ${b.h ?? 0}개` },
    ].filter((c) => c.r != null).sort((a, x) => a.r! - x.r!);
    const top = cands[0];
    const rest = [`홈런 ${b.hr ?? 0}개`, `타율 ${rate3(b.avg)}`].filter((s) => s !== top?.text)[0];
    return {
      id: b.player_id, name: b.name, back: b.back_number, meta: [b.position, b.bats_throws].filter(Boolean).join(" · "),
      role: (paRank(b) ?? 99) <= STARTERS ? "주전" : null,
      lead: lead(b.percentiles, "리그", "타석이 적어 리그 비교는 아직이에요"),
      main: top ? withRank(top.text, top.r) : `${b.pa ?? 0}타석`,
      sub: `${rest} · ${b.games ?? "–"}경기 출전`,
      scenes: b.scene_count,
    };
  };
  const pCard = (p: RosterPitcher): Card => {
    const starter = p.role === "starter";
    const cands = starter
      ? [{ r: outsRank(p), text: `${innings(p.outs)}이닝` }, { r: soRank(p), text: `삼진 ${p.so}개` }]
      : [{ r: gRank(p), text: `${p.g}경기 등판` }, { r: soRank(p), text: `삼진 ${p.so}개` }];
    const top = [...cands].sort((a, x) => (a.r ?? 99) - (x.r ?? 99))[0];
    const other = cands.find((c) => c !== top)!;
    return {
      id: p.player_id, name: p.name, back: p.back_number, meta: ["투수", p.bats_throws].filter(Boolean).join(" · "),
      role: null,
      lead: lead(p.percentiles, starter ? "선발 중" : "구원 중", "이닝이 적어 리그 비교는 아직이에요"),
      main: withRank(top.text, top.r),
      sub: starter ? `${other.text} · 선발 ${p.gs}경기` : `${other.text} · ${innings(p.outs)}이닝`,
      scenes: p.scene_count,
    };
  };

  const pos = (p: string) => fielders.filter((b) => b.position === p).map(bCard);
  const known = new Set(["포수", "내야수", "외야수"]);
  const fieldSub = `타석 많은 순 · 주전은 팀에서 타석이 많은 ${STARTERS}명`;
  return [
    { key: "p-starter", title: "선발 투수", sub: "이닝 많은 순", cards: pitchers.filter((p) => p.role === "starter").sort((a, b) => b.outs - a.outs).map(pCard) },
    { key: "p-reliever", title: "구원 투수", sub: "등판 많은 순", cards: pitchers.filter((p) => p.role !== "starter").sort((a, b) => b.g - a.g).map(pCard) },
    { key: "c", title: "포수", sub: fieldSub, cards: pos("포수") },
    { key: "if", title: "내야수", sub: fieldSub, cards: pos("내야수") },
    { key: "of", title: "외야수", sub: fieldSub, cards: pos("외야수") },
    { key: "etc", title: "그 밖의 야수", sub: "포지션 정보 없음 · 타석 많은 순", cards: fielders.filter((b) => !b.position || !known.has(b.position)).map(bCard) },
  ];
}

function RosterCard({ c, team }: { c: Card; team: string }) {
  return (
    <div className="group relative flex h-full flex-col rounded-3xl border border-line bg-surface p-4 hover:bg-surface-2">
      <div className="flex gap-3.5">
        <Portrait id={c.id} name={c.name} team={team} />
        <div className="min-w-0 flex-1">
          <p className="flex items-center justify-between gap-2">
            <span className="truncate font-num text-xs font-bold text-fg-2">{c.back != null && `#${c.back} · `}{c.meta}</span>
            {c.role && (
              <span className="shrink-0 rounded-md bg-fg px-1.5 py-0.5 text-[11px] font-bold text-bg">{c.role}</span>
            )}
          </p>
          <Link href={playerHref(c.id)} className="mt-0.5 block truncate text-lg font-bold group-hover:underline after:absolute after:inset-0 after:content-['']">
            {c.name}
          </Link>
          <p className="mt-2 truncate text-[13px] font-bold">{c.main}</p>
          <p className="truncate text-xs text-fg-2">{c.sub}</p>
        </div>
      </div>
      <div className="mt-3.5 flex min-h-[44px] items-end gap-3 border-t border-line pt-3">
        <div className="min-w-0 flex-1">
          {"text" in c.lead ? (
            <>
              <p className="truncate text-[15px] font-bold">{c.lead.text}</p>
              <p className="mt-1 flex items-center gap-2">
                <span className="block h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
                  <span className="block h-full rounded-full" style={{ width: `${c.lead.pct}%`, background: teamOf(team)?.band }} />
                </span>
                <span className="shrink-0 text-[11px] font-bold text-fg-2">{c.lead.pos}</span>
              </p>
            </>
          ) : (
            <p className="truncate text-xs text-muted">{c.lead.note}</p>
          )}
        </div>
        {c.scenes > 0 && ( // 장면 수 = 선수 화면 장면 탭(투수는 등판 탭 「장면 있음」)과 같은 기준 (API-16 · 26)
          <Link href={playerHref(c.id, { tab: "scenes" })} aria-label={`${c.name} 장면 ${c.scenes}개 보기`}
                className="relative z-10 flex h-7 shrink-0 items-center gap-1 rounded-full bg-accent px-2.5 text-[11px] font-bold text-white hover:brightness-95">
            <PlayGlyph size={7} /> 장면 {c.scenes}
          </Link>
        )}
      </div>
    </div>
  );
}

/** 4:5 세로 사진 — 없으면 구단 연한 색 바탕에 이름 첫 글자 */
function Portrait({ id, name, team }: { id: string; name: string; team: string }) {
  const [failed, setFailed] = useState(false);
  const t = teamOf(team);
  return (
    <span className="flex h-[90px] w-[72px] shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-line bg-surface-2"
          style={failed ? { background: t?.soft } : undefined}>
      {failed ? (
        <span className="text-3xl font-extrabold" style={{ color: t?.text }} aria-hidden>{name.slice(0, 1)}</span>
      ) : (
        <img src={photoUrl(id)} alt="" className="h-full w-full object-cover object-top" loading="lazy" onError={() => setFailed(true)} />
      )}
    </span>
  );
}
