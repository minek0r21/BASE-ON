"use client";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기: 썸네일 핫링크(설계 8-2) */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Wrap, clipLength, gameHref, sceneTitle, weekday } from "@/components/home/common";
import { bigThumb } from "@/components/player/Hero";
import ShareButton, { BTN } from "@/components/ui/ShareButton";
import ScenePlayer, { thumbnailUrl } from "@/components/ScenePlayer";
import { playerHref } from "@/components/SearchBox";
import StageTag from "@/components/StageTag";
import { Empty } from "@/components/ui/Chip";
import { PlayGlyph, PlayerAvatar, TeamLogo, mmss } from "@/components/ui/Media";
import Slide from "@/components/ui/Slide";
import { ApiError, gameDate, getDay, getGameBox, qk, type BoxTeam, type Clip, type DayGame, type DayScene } from "@/lib/api";
import { innings, md, rate3 } from "@/lib/format";
import { useReducedMotion } from "@/lib/motion";
import { team as teamOf, teamHref } from "@/lib/teams";
import { useDocTitle, useNavCrumb } from "@/lib/title";

const RUNS = ["", "솔로", "투런", "스리런", "만루"];
type Now = { key: string; clip: Clip; label: string; title: string };

/**
 * 04 경기 상세 (Figma 181:2012 「경기 하이라이트 모드」) — /games/?id=경기번호. 위쪽 큰 플레이어 하나가 무대:
 * 처음엔 경기 하이라이트, 홈런 칩 · 오른쪽 장면을 누르면 같은 자리에서 그 장면 (11-01 사용자: 이 화면만 위쪽 플레이어 하나).
 * 아래 이 경기(이닝별 점수 · 홈런) · 경기 기록(박스스코어 API-38), 오른쪽 이 경기의 장면 · 같은 날 다른 경기 (API-14)
 */
export default function GameView() {
  const id = useSearchParams().get("id") ?? "";
  const d = id ? gameDate(id) : "";
  const date = /^\d{4}-\d{2}-\d{2}$/.test(d) && !Number.isNaN(Date.parse(d)) ? d : null; // 번호 앞 8자리 = 날짜
  const day = useQuery({ queryKey: qk.day(date), queryFn: ({ signal }) => getDay(date, signal), enabled: !!date });
  const box = useQuery({ queryKey: qk.gameBox(id), queryFn: ({ signal }) => getGameBox(id, signal), enabled: !!id });
  const [now, setNow] = useState<(Now & { on: boolean }) | null>(null);
  const [ended, setEnded] = useState<string | null>(null); // 끝까지 본 장면의 key → 다음 장면 카운트다운

  const g = day.data?.games.find((x) => x.game_pk === id);
  useNavCrumb("경기 상세");
  useDocTitle(g && date ? `${md(date)} ${g.away.team} ${g.away.score} : ${g.home.score} ${g.home.team}` : null);
  // 없는 경기 번호면 그날(번호에서 읽은 날짜가 맞으면) 일정으로 보낸다
  const missing = !id || !date || (box.error instanceof ApiError && box.error.status === 404) || (!!day.data && !g);
  if (missing) {
    return (
      <Wrap className="pt-2 pb-24">
        <Empty text="경기를 찾을 수 없어요" sub="주소가 맞는지 확인해 주세요."
               action={date ? { label: `${md(date)} 일정 보기`, href: `/schedule/?date=${date}` } : { label: "일정 보기", href: "/schedule/" }} />
      </Wrap>
    );
  }
  if (day.isError || box.isError) return <Wrap className="pt-2 pb-24"><Empty text="경기를 불러오지 못했어요" sub="잠시 뒤 다시 시도해 주세요." action={{ label: "다시 시도", onClick: () => { day.refetch(); box.refetch(); } }} /></Wrap>;
  if (!day.data || !g) return <Wrap className="pt-10 pb-24"><div className="h-[720px] animate-pulse rounded-3xl bg-surface-2" /></Wrap>;

  const winner = g.away.result === "W" ? g.away.team : g.home.result === "W" ? g.home.team : null;
  const stadium = teamOf(g.home.team)?.home;
  const inn = g.line.away.length;
  const meta = [`${box.data?.season ?? date!.slice(0, 4)} ${g.stage_label ? "포스트시즌" : "정규시즌"}`, `${md(date!)}(${weekday(date!)})`, stadium, `${inn}이닝`, winner ? `${winner} 승` : "무승부"]
    .filter(Boolean).join(" · ");
  const base: Now | null = g.highlight ? { key: "highlight", clip: g.highlight, label: "경기 하이라이트", title: `${scoreLine(g)} 하이라이트` } : null;
  const cur = now ?? (base && { ...base, on: false });
  const play = (n: Now) => { setEnded(null); setNow({ ...n, on: true }); };
  const scenes = orderScenes(g.scenes);
  const nows: Now[] = scenes.map((s) => ({ key: sceneKey(s), clip: s.clip, label: s.kind === "outing" ? "등판 장면" : "홈런 장면", title: sceneTitle(s) }));
  // 다음 장면: 오른쪽 「이 경기의 장면」 순서로 하나 뒤 (마지막 장면 · 경기 하이라이트 · 영상 없는 홈런 뒤에는 없음)
  const at = cur ? nows.findIndex((n) => n.key === cur.key) : -1;
  const next = at >= 0 ? nows[at + 1] ?? null : null;

  return (
    <Wrap className="night-mobile animate-appear pb-6 md:pt-10 md:pb-24">
      <nav className="hidden text-[13px] text-muted md:block" aria-label="위치">
        <Link href={`/schedule/?${new URLSearchParams({ date: date! })}`} className="hover:underline">일정</Link> <span aria-hidden>›</span> {md(date!)}({weekday(date!)})
      </nav>
      <div className="grid grid-cols-[minmax(0,1fr)] items-start md:mt-4 lg:grid-cols-[minmax(0,1fr)_380px] lg:gap-8">
        {/* 좁은 폭 순서: 영상 → 정보 → 점수판 → 이 경기의 장면 → 경기 기록 */}
        <div className="contents min-w-0 lg:block">
          <Stage now={cur} onStart={() => cur && play(cur)} onEnded={() => cur && setEnded(cur.key)}
                 fallback={base && cur && cur.key !== base.key && cur.clip.videoId !== base.clip.videoId
                   ? { label: "이 경기 하이라이트로 보기", onClick: () => play(base) } : undefined}>
            {cur?.on && ended === cur.key && next && <NextUp key={next.key} next={next} onGo={() => play(next)} onCancel={() => setEnded(null)} />}
          </Stage>
          <p className="mt-3 flex flex-wrap items-center gap-2 text-xs font-bold md:mt-5">
            {g.stage_label ? <StageTag label={g.stage_label} /> : <span className="rounded-md bg-fg px-2 py-1 text-bg">정규시즌</span>}
            <span className="rounded-md bg-surface-2 px-2 py-1 text-fg-2">{md(date!)} ({weekday(date!)})</span>
            {cur && <span className="rounded-md bg-surface-2 px-2 py-1 text-fg-2">{cur.label}</span>}
          </p>
          <h1 className="mt-2 flex flex-wrap items-center gap-2 text-[22px] leading-tight font-bold tracking-tight md:mt-3 md:gap-3 md:text-[36px] md:font-extrabold">
            <span className="hidden md:block"><TeamLogo team={g.away.team} height={32} /></span> {scoreLine(g)} <span className="hidden md:block"><TeamLogo team={g.home.team} height={32} /></span>
          </h1>
          <p className="mt-1 text-[13px] text-fg-2 md:mt-1.5 md:text-sm">{meta}</p>
          <div className="mt-3 grid grid-cols-2 gap-1.5 md:mt-4 md:flex md:flex-wrap md:gap-2 [&>*]:max-md:h-11 [&>*]:max-md:justify-center [&>*]:max-md:rounded-xl [&>*]:max-md:px-1 [&>*]:max-md:text-[13px]">
            {[g.away.team, g.home.team].map((t) => (
              <Link key={t} href={teamHref(t)} className={`${BTN} flex items-center gap-2`}><TeamLogo team={t} height={18} /> {t} 팀 보기</Link>
            ))}
            <Link href={`/schedule/?${new URLSearchParams({ date: date! })}`} className={`${BTN} flex items-center`}>일정에서 보기</Link>
            <ShareButton />
          </div>

          <ThisGame g={g} winner={winner} current={cur?.key ?? null} onPlay={play} />
          <div className="order-3 min-w-0"><Box box={box.data} pending={box.isPending} /></div>
        </div>

        <aside className="order-2 mt-4 space-y-3 md:space-y-5 lg:sticky lg:top-24 lg:mt-0">
          <Panel title={`이 경기의 장면 ${scenes.length}`}>
            {scenes.length ? (
              <ul className="space-y-1">
                {scenes.map((s, i) => {
                  const n = nows[i];
                  return (
                    <li key={n.key}>
                      <SceneRow clip={s.clip} title={n.title} sub={s.kind === "outing" ? `${s.team} · ${s.role} 등판` : `${s.inning}회${s.inningHalf} · ${s.team}`}
                                on={cur?.key === n.key} onClick={() => play(n)} />
                    </li>
                  );
                })}
              </ul>
            ) : <p className="py-4 text-[13px] text-fg-2">이 경기 장면이 아직 없어요</p>}
          </Panel>
          {day.data.games.length > 1 && (
            <Panel title="같은 날 다른 경기">
              <ul className="space-y-1">
                {day.data.games.filter((x) => x.game_pk !== id).map((x) => (
                  <li key={x.game_pk}>
                    <Link href={gameHref(x.game_pk)} className="group flex items-center gap-3 rounded-2xl p-2 hover:bg-surface-2">
                      <Thumb clip={x.highlight} />
                      <span className="min-w-0">
                        <span className="flex items-center gap-1.5 text-[15px] font-bold group-hover:underline">
                          <TeamLogo team={x.away.team} height={14} /> {scoreLine(x)} <TeamLogo team={x.home.team} height={14} />
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-fg-2">
                          {[x.stage_label, `홈런 ${x.homeRuns.length}`, x.scenes.length && `장면 ${x.scenes.length}`].filter(Boolean).join(" · ")}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </aside>
      </div>
    </Wrap>
  );
}

const scoreLine = (g: DayGame) => `${g.away.team} ${g.away.score} : ${g.home.score} ${g.home.team}`;
const sceneKey = (s: DayScene) => `${s.kind}-${s.player.player_id}-${s.inning ?? ""}${s.inningHalf ?? ""}-${s.hrSeq ?? ""}`;
/** 등판 장면(선발 먼저) → 홈런 장면은 나온 이닝 순 */
const orderScenes = (ss: DayScene[]) => [
  ...ss.filter((s) => s.kind === "outing"),
  ...ss.filter((s) => s.kind === "home_run").sort((a, b) => (a.inning ?? 0) - (b.inning ?? 0) || (a.inningHalf === "초" ? -1 : 1)),
];

/** 위쪽 무대 — 처음엔 썸네일 + ▶ (누를 때 영상을 불러온다), 고른 장면은 바로 재생 */
// 플레이어는 장면이 바뀌어도 다시 만들지 않는다(loadVideoById) — 첫 재생 뒤라 다음 장면도 이어 재생된다
function Stage({ now, onStart, onEnded, fallback, children }: {
  now: (Now & { on: boolean }) | null; onStart: () => void; onEnded: () => void;
  /** 장면 영상이 재생되지 않을 때 「이 경기 하이라이트로 보기」 (경기 하이라이트를 보고 있을 때는 없음) */
  fallback?: { label: string; onClick: () => void };
  children?: ReactNode;
}) {
  return (
    <div className="relative -mx-4 aspect-video overflow-hidden bg-night md:mx-0 md:rounded-[28px]">
      {!now ? (
        <div className="flex h-full items-center justify-center text-sm text-[#a1a1a8]">이 경기 영상이 아직 없어요</div>
      ) : now.on ? (
        <div className="h-full w-full animate-grow"><ScenePlayer bare clip={now.clip} label={now.title} onEnded={onEnded} fallback={fallback} /></div>
      ) : (
        <button onClick={onStart} className="group absolute inset-0" aria-label={`${now.title} 재생`}>
          <img src={bigThumb(now.clip.videoId)} alt="" className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.02]" />
          <span className="absolute top-4 left-4 rounded-full bg-black/70 px-3 py-1 text-xs font-bold text-white">{now.label}</span>
          <span className="absolute inset-0 m-auto flex h-16 w-16 items-center justify-center rounded-full bg-accent text-white"><PlayGlyph size={20} /></span>
          <span className="absolute right-4 bottom-4 rounded-md bg-black/70 px-2 py-0.5 font-num text-xs font-semibold text-white">{mmss(clipLength(now.clip))}</span>
        </button>
      )}
      {children}
    </div>
  );
}

/**
 * 다음 장면 (HANDOFF 모션 후보 「04 다음 장면」) — 4초 카운트다운 링 뒤 이어 재생, 바로 보기 · 취소.
 * 움직임 줄이기면 저절로 넘어가지 않고 「다음 장면 ▶」 버튼만
 */
function NextUp({ next, onGo, onCancel }: { next: Now; onGo: () => void; onCancel: () => void }) {
  const reduce = useReducedMotion();
  const go = useRef(onGo);
  useEffect(() => { go.current = onGo; }, [onGo]);
  useEffect(() => {
    if (reduce) return;
    const t = setTimeout(() => go.current(), 4000);
    return () => clearTimeout(t);
  }, [reduce]);
  return (
    <div className="absolute inset-0 flex animate-appear flex-col items-center justify-center gap-3 bg-black/75 text-white">
      <p className="text-[13px] text-[#a1a1a8]">다음 장면</p>
      <p className="px-6 text-center text-xl font-bold">{next.title}</p>
      <button onClick={onGo} className="relative mt-2 flex h-16 w-16 items-center justify-center rounded-full bg-white/15 hover:bg-white/25" aria-label={`${next.title} 바로 보기`}>
        {!reduce && (
          <svg viewBox="0 0 64 64" className="absolute inset-0 -rotate-90" aria-hidden>
            <circle cx="32" cy="32" r="30" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="3" />
            <circle cx="32" cy="32" r="30" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeDasharray="188.5" className="animate-countdown" />
          </svg>
        )}
        <PlayGlyph size={18} />
      </button>
      <button onClick={onCancel} className="text-[13px] font-bold text-[#d3d4d8] hover:underline">취소</button>
    </div>
  );
}

function Panel({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-surface p-3 md:rounded-3xl md:p-5">
      <div className="mb-2 flex items-center justify-between gap-3 md:mb-3">
        <h2 className="text-[15px] font-bold md:text-lg">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

function Thumb({ clip }: { clip: Clip | null }) {
  return (
    <span className="relative block aspect-video w-28 shrink-0 overflow-hidden rounded-lg bg-night md:w-[128px] md:rounded-xl">
      {clip && <img src={thumbnailUrl(clip.videoId)} alt="" className="h-full w-full object-cover" loading="lazy" />}
      {clip && <span className="absolute right-1.5 bottom-1.5 rounded bg-black/75 px-1 py-px font-num text-[10px] font-semibold text-white">{mmss(clipLength(clip))}</span>}
    </span>
  );
}

function SceneRow({ clip, title, sub, on, onClick }: { clip: Clip; title: string; sub: string; on: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} aria-current={on ? "true" : undefined}
            className="group flex w-full items-center gap-3 rounded-2xl px-2 py-2.5 text-left hover:bg-surface-2 aria-[current=true]:bg-surface-2 md:p-2">
      {/* 휴대폰은 썸네일 대신 ▶ — 위 영상 칸과 같은 하이라이트 그림이 줄마다 되풀이돼서 (M04b · 11-08) */}
      <span className="hidden md:block"><Thumb clip={clip} /></span>
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-3 md:hidden"><PlayGlyph size={7} /></span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-bold group-hover:underline md:text-[15px]">{title}</span>
        <span className="mt-0.5 block truncate text-xs text-fg-2">{sub}</span>
        {on && <span className="mt-1 inline-block rounded bg-accent px-1.5 py-px text-[10px] font-bold text-white">지금 보는 장면</span>}
      </span>
      <span className="shrink-0 font-num text-xs text-fg-2 md:hidden">{mmss(clipLength(clip))}</span>
    </button>
  );
}

/** 이 경기 — 이닝별 점수판(이긴 팀 굵게) + 홈런 칩(장면이 있으면 위쪽 무대에서 재생) */
function ThisGame({ g, winner, current, onPlay }: { g: DayGame; winner: string | null; current: string | null; onPlay: (n: Now) => void }) {
  const n = g.line.away.length;
  const rows = [
    { team: g.away.team, runs: g.line.away, score: g.away.score, h: g.line.away_h },
    { team: g.home.team, runs: g.line.home, score: g.home.score, h: g.line.home_h },
  ];
  const withScene = g.homeRuns.filter((h) => h.clip).length;
  return (
    <section className="mt-3 rounded-2xl border border-line bg-surface p-3 md:mt-8 md:rounded-3xl md:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-xl font-bold">이 경기</h2>
        <span className="text-[13px] text-fg-2">종료 · {winner ? `${winner} 승` : "무승부"}</span>
      </div>
      <div className="overflow-x-auto rounded-xl bg-surface-2 px-2.5 py-2 md:rounded-2xl md:px-4 md:py-3">
        <table className="w-full table-fixed font-num text-xs md:min-w-[520px] md:table-auto md:text-sm">
          <thead className="text-xs text-fg-2">
            <tr>
              <th className="w-10 py-1.5 text-left font-medium md:w-24" />
              {Array.from({ length: n }, (_, i) => <th key={i} className="py-1.5 text-center font-medium">{i + 1}</th>)}
              <th className="w-7 py-1.5 text-center font-medium md:w-auto md:pl-3">점수</th>
              <th className="w-7 py-1.5 text-center font-medium md:w-auto">안타</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.team} className={r.team === winner ? "font-bold" : "text-fg-2"}>
                <td className="py-1.5"><span className="flex items-center gap-1.5 font-sans"><span className="hidden md:block"><TeamLogo team={r.team} height={14} /></span> {r.team}</span></td>
                {r.runs.map((v, i) => <td key={i} className="py-1.5 text-center">{v ?? "–"}</td>)}
                <td className="py-1.5 text-center font-display text-lg font-extrabold text-fg md:pl-3 md:text-[20px]">{r.score}</td>
                <td className="py-1.5 text-center font-display text-lg font-extrabold md:text-[20px]">{r.h}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-[13px] text-fg-2">이 경기 홈런 {g.homeRuns.length}개{g.homeRuns.length ? ` · 장면 있음 ${withScene}` : ""}{withScene > 0 && <span className="md:hidden"> · 장면은 아래 목록</span>}</p>
      {g.homeRuns.length > 0 && (
        // 휴대폰은 장면이 있는 홈런을 아래 「이 경기의 장면」에서만 보여 준다 (같은 내용 두 번 → 한 번)
        <div className={`mt-2.5 flex-wrap gap-2 ${withScene === g.homeRuns.length ? "hidden md:flex" : "flex"}`}>
          {g.homeRuns.map((h) => {
            const k = `home_run-${h.player_id}-${h.inning}${h.inningHalf}-${h.hrSeq ?? ""}`;
            const text = `${h.name} ${h.label ?? (h.hrSeq ? `${h.hrSeq}호` : "홈런")} · ${h.inning}회${h.inningHalf}${h.runs > 1 ? ` ${RUNS[h.runs] ?? ""}` : ""}`;
            return h.clip ? (
              <button key={k} onClick={() => onPlay({ key: k, clip: h.clip!, label: "홈런 장면", title: text })} aria-current={current === k ? "true" : undefined}
                      className="hidden h-11 items-center gap-1.5 rounded-xl border border-line bg-surface px-3 text-xs font-bold md:flex hover:border-accent md:h-8 md:rounded-full hover:bg-accent hover:text-white aria-[current=true]:border-accent aria-[current=true]:bg-accent aria-[current=true]:text-white">
                <PlayGlyph size={7} /> {text}
              </button>
            ) : g.highlight ? (
              // 이 홈런만 영상이 없으면 경기 하이라이트로 (09 「한 장면만 영상이 없을 때」)
              <button key={k} onClick={() => onPlay({ key: k, clip: g.highlight!, label: "이 홈런은 영상 없음 · 경기 하이라이트", title: `${text} · 경기 하이라이트` })}
                      aria-current={current === k ? "true" : undefined} title="이 홈런은 연결된 영상이 없어요. 경기 하이라이트에 들어 있을 수 있어요."
                      className="flex h-11 items-center rounded-xl border border-dashed border-line px-3 text-xs md:h-8 md:rounded-full text-fg-2 hover:border-fg-2 hover:text-fg aria-[current=true]:border-fg aria-[current=true]:text-fg">
                {text}
              </button>
            ) : (
              <span key={k} title="이 홈런은 연결된 영상이 없어요" className="flex h-11 items-center rounded-xl border border-dashed border-line px-3 text-xs md:h-8 md:rounded-full text-fg-2">{text}</span>
            );
          })}
        </div>
      )}
    </section>
  );
}

/** 경기 기록 (박스스코어, API-38) — 팀 탭, 타자 · 투수 표. 이름은 선수 화면으로, 투수는 그 등판 상세(03b)로 */
function Box({ box, pending }: { box?: { away: BoxTeam; home: BoxTeam; date: string; season: number }; pending: boolean }) {
  const [side, setSide] = useState<"away" | "home">("away");
  if (pending) return <div className="mt-6 h-[420px] animate-pulse rounded-3xl bg-surface-2" />;
  if (!box) return null;
  const t = box[side];
  const bat = t.batters.reduce((a, b) => ({ pa: a.pa + b.pa, ab: a.ab + b.ab, h: a.h + b.h, hr: a.hr + b.hr, bb: a.bb + b.bb, so: a.so + b.so }), { pa: 0, ab: 0, h: 0, hr: 0, bb: 0, so: 0 });
  const th = "py-2.5 pl-2 text-right font-medium";
  const td = "py-2.5 pl-2 text-right font-num";
  return (
    <section className="mt-3 rounded-2xl border border-line bg-surface p-3 md:mt-6 md:rounded-3xl md:p-6">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3 md:mb-4">
        <h2 className="text-[17px] font-bold md:text-xl">경기 기록</h2>
        <Slide mark="rounded-full bg-surface-3" className="flex rounded-full border border-line bg-surface p-1" role="group" aria-label="팀">
          {(["away", "home"] as const).map((k) => (
            <button key={k} onClick={() => setSide(k)} aria-pressed={side === k}
                    className="relative flex h-[30px] items-center gap-1.5 rounded-full px-4 text-[13px] font-medium text-fg-2 aria-pressed:font-bold aria-pressed:text-fg">
              <TeamLogo team={box[k].team} height={14} /> {box[k].team}
            </button>
          ))}
        </Slide>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px] md:min-w-[560px] md:text-sm">
          <thead className="text-xs text-fg-2">
            <tr className="border-b border-line">
              <th className="py-2.5 text-left font-medium">타자</th>
              <th className={th}>타석</th><th className={`${th} max-md:hidden`}>타수</th><th className={th}>안타</th><th className={th}>홈런</th><th className={th}>볼넷</th><th className={th}>삼진</th>
            </tr>
          </thead>
          <tbody>
            {t.batters.map((b) => (
              <tr key={b.player_id} className="border-b border-line">
                <td className="py-2">
                  <Link href={playerHref(b.player_id)} className="group flex items-center gap-2.5">
                    <span className="hidden md:block"><PlayerAvatar id={b.player_id} name={b.name} team={t.team} size={28} /></span>
                    <span className="font-bold group-hover:underline">{b.name}</span>
                    {b.position && <span className="hidden text-xs text-fg-2 md:block">{b.position}</span>}
                  </Link>
                </td>
                <td className={td}>{b.pa}</td><td className={`${td} max-md:hidden`}>{b.ab}</td>
                <td className={`${td} ${b.h >= 2 ? "font-bold" : ""}`}>{b.h}</td>
                <td className={`${td} ${b.hr ? "font-bold text-(--team-text)" : ""}`} style={b.hr ? ({ "--team-text": teamOf(t.team)?.text } as CSSProperties) : undefined}>{b.hr}</td>
                <td className={td}>{b.bb}</td><td className={td}>{b.so}</td>
              </tr>
            ))}
            <tr className="font-bold">
              <td className="py-2.5">합계 <span className="ml-1 hidden text-xs font-normal text-fg-2 md:inline">타율 {rate3(bat.ab ? bat.h / bat.ab : null)}</span></td>
              <td className={td}>{bat.pa}</td><td className={`${td} max-md:hidden`}>{bat.ab}</td><td className={td}>{bat.h}</td><td className={td}>{bat.hr}</td><td className={td}>{bat.bb}</td><td className={td}>{bat.so}</td>
            </tr>
          </tbody>
        </table>
        <table className="mt-4 w-full text-[13px] md:mt-6 md:min-w-[560px] md:text-sm">
          <thead className="text-xs text-fg-2">
            <tr className="border-b border-line">
              <th className="py-2.5 text-left font-medium">투수</th>
              <th className={th}>이닝</th><th className={`${th} max-md:hidden`}>상대 타자</th><th className={th}>피안타</th><th className={`${th} max-md:hidden`}>볼넷 · 몸에 맞는 공</th><th className={th}>삼진</th><th className={th}>실점</th>
            </tr>
          </thead>
          <tbody>
            {t.pitchers.map((p) => (
              <tr key={p.outing_id} className="border-b border-line last:border-0">
                <td className="py-2">
                  <Link href={playerHref(p.player_id, { view: "pitcher", tab: "games", season: String(box.season), month: String(Number(box.date.slice(5, 7))), outing: p.outing_id })} className="group flex items-center gap-2.5">
                    <span className="hidden md:block"><PlayerAvatar id={p.player_id} name={p.name} team={t.team} size={28} /></span>
                    <span className="font-bold group-hover:underline">{p.name}</span>
                    <span className="hidden text-xs text-fg-2 md:block">{p.role}</span>
                  </Link>
                </td>
                <td className={td}>{innings(p.outs)}</td><td className={`${td} max-md:hidden`}>{p.tbf}</td><td className={td}>{p.h}</td>
                <td className={`${td} max-md:hidden`}>{p.bb} · {p.hbp}</td><td className={td}>{p.so}</td>
                <td className={`${td} ${p.r === 0 && p.outs >= 9 ? "font-bold" : ""}`}>{p.r}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
