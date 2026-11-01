"use client";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기: 썸네일 핫링크(설계 8-2) */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useRef, useState, type ReactNode } from "react";
import { SectionHead, Wrap, clipLength, gameHref } from "@/components/home/common";
import type { Playing } from "@/components/home/DayScenes";
import InlinePlayer from "@/components/InlinePlayer";
import { thumbnailUrl } from "@/components/ScenePlayer";
import { playerHref } from "@/components/SearchBox";
import { Retry } from "@/components/ui/Chip";
import { PlayGlyph, PlayerAvatar, TeamLogo, mmss } from "@/components/ui/Media";
import {
  getMeta, getStandings, getTeamBatters, getTeamGames, getTeamPitchers, getTeamScenes, qk,
  type TeamScene,
} from "@/lib/api";
import { axisCopy } from "@/lib/axes";
import { weekdayOf } from "@/lib/dates";
import { innings, md, outingLine, rate3 } from "@/lib/format";
import { useMyTeam } from "@/lib/local";
import { team as teamOf } from "@/lib/teams";
import TeamHead from "./TeamHead";

const HR_RUNS = ["", "솔로", "투런", "스리런", "만루"];

/**
 * 06 팀 (Figma 144:832) — 팀 색 머리 · 가로 순위 띠(API-13, TeamHead) · 최근 경기(API-35) · 최근 장면(API-33) · 타자 표(API-16) · 선발 표(API-26).
 * 장면 · 경기 하이라이트는 누른 구역 바로 아래에서 재생한다 (별도 창 없음)
 */
export default function TeamView() {
  const params = useSearchParams();
  const [myTeam, setMyTeam] = useMyTeam();
  const standings = useQuery({ queryKey: qk.standings(), queryFn: ({ signal }) => getStandings(signal) });
  const name = [params.get("team"), myTeam, standings.data?.teams[0]?.team].find((t) => t && teamOf(t)) ?? null;
  const t = teamOf(name);

  const meta = useQuery({ queryKey: qk.meta(), queryFn: ({ signal }) => getMeta(signal) });
  const games = useQuery({ queryKey: qk.team("games", name ?? ""), queryFn: ({ signal }) => getTeamGames(name!, signal), enabled: !!name });
  const scenes = useQuery({ queryKey: qk.team("scenes", name ?? ""), queryFn: ({ signal }) => getTeamScenes(name!, signal), enabled: !!name });
  const batters = useQuery({ queryKey: qk.team("batters", name ?? ""), queryFn: ({ signal }) => getTeamBatters(name!, signal), enabled: !!name });
  const pitchers = useQuery({ queryKey: qk.team("pitchers", name ?? ""), queryFn: ({ signal }) => getTeamPitchers(name!, signal), enabled: !!name });
  const [playing, setPlaying] = useState<(Playing & { at: "games" | "scenes" }) | null>(null);

  if (!name || !t) return (
    <Wrap className="pt-10 pb-24">
      {standings.isError
        ? <Retry text="팀 순위를 불러오지 못했어요" onRetry={() => standings.refetch()} />
        : <div className="h-[600px] animate-pulse rounded-3xl bg-surface-2" />}
    </Wrap>
  );
  const st = standings.data?.teams;
  const me = st?.find((x) => x.team === name);
  const asOf = meta.data?.data_as_of;
  const season = standings.data?.season;
  const sub = [season && `${season} 정규시즌`, asOf && `${md(asOf)} 기준`,
    me && `${me.games}경기 ${me.w}승 ${me.d}무 ${me.l}패`, me && `승률 ${rate3(me.pct)}`, `홈 ${t.home}`].filter(Boolean).join(" · ");

  return (
    <>
      <TeamHead name={name} t={t} sub={sub} me={me} all={st} season={season} myTeam={myTeam} setMyTeam={setMyTeam} onPick={() => setPlaying(null)}
                onRetry={standings.isError ? () => standings.refetch() : undefined} />
      <Wrap className="pb-24">
        {/* 최근 경기 */}
        <section className="mt-14">
          <SectionHead
            title="최근 경기"
            sub={games.data?.length ? `${md(games.data.at(-1)!.date)} ~ ${md(games.data[0].date)} · 최근 ${games.data.length}경기` : undefined}
            right={<Link href="/schedule/" className="text-sm font-bold text-brand-text hover:underline">일정 전체 ›</Link>}
          />
          {games.isError ? (
            <Retry text="최근 경기를 불러오지 못했어요" onRetry={() => games.refetch()} />
          ) : !games.data ? (
            <div className="h-[150px] animate-pulse rounded-3xl bg-surface-2" />
          ) : (
            <ul className="animate-appear grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {games.data.map((g) => (
                <li key={g.game_pk} className="rounded-2xl border border-line bg-surface p-4">
                  <p className="flex items-center justify-between text-xs text-fg-2">
                    <span>{md(g.date)} ({weekdayOf(g.date)}) · {g.home ? "홈" : "원정"}</span>
                    <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${g.result === "W" ? "text-white" : "bg-surface-2 text-fg-2"}`}
                          style={g.result === "W" ? { background: t.band } : undefined}>
                      {{ W: "승", L: "패", D: "무" }[g.result]}
                    </span>
                  </p>
                  <p className="mt-3 flex items-center justify-center gap-3">
                    <TeamLogo team={name} height={22} />
                    <span className="font-display text-[34px] leading-none font-extrabold">{g.score.team} : {g.score.opponent}</span>
                    <TeamLogo team={g.opponent} height={22} />
                  </p>
                  <p className="mt-2 flex items-center justify-between text-xs text-fg-2">
                    <span>vs {g.opponent}{g.stage_label ? ` · ${g.stage_label}` : ""}</span>
                    <Link href={gameHref(g.game_pk)} className="font-bold text-brand-text hover:underline">경기 상세 ›</Link>
                  </p>
                  {g.highlight && (
                    <button
                      onClick={() => setPlaying({ clip: g.highlight!, title: `${md(g.date)} ${name} ${g.score.team} : ${g.score.opponent} ${g.opponent}`, sub: "경기 하이라이트 · 처음부터", at: "games" })}
                      className="mt-3 flex items-center gap-1.5 text-xs font-bold hover:underline"
                    >
                      <PlayGlyph size={7} /> 이 경기 하이라이트 {mmss(clipLength(g.highlight))}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {playing?.at === "games" && <InlinePlayer playing={playing} onClose={() => setPlaying(null)} className="mt-5" />}
        </section>

        {/* 최근 장면 */}
        <section className="mt-14">
          {scenes.isError ? (
            <Retry text={`${name}의 최근 장면을 불러오지 못했어요`} onRetry={() => scenes.refetch()} />
          ) : (
            <SceneRow
              team={name}
              data={scenes.data}
              playingId={playing?.at === "scenes" ? playing.title : null}
              onPlay={(clip, title, sub) => setPlaying({ clip, title, sub, at: "scenes" })}
            />
          )}
          {playing?.at === "scenes" && <InlinePlayer playing={playing} onClose={() => setPlaying(null)} className="mt-5" />}
        </section>

        {/* 선수 표 — 전원 명단은 선수 탭 「팀별 선수」로 */}
        <div className="mt-14 mb-3 flex justify-end">
          <Link href={`/rankings/?${new URLSearchParams({ team: name })}`} className="text-sm font-bold text-brand-text hover:underline">선수 전체 ›</Link>
        </div>
        <div className="grid gap-5 lg:grid-cols-2">
          {batters.isError ? <Retry text="타자 기록을 불러오지 못했어요" onRetry={() => batters.refetch()} /> : <PlayerTable
            title="타자"
            sub={`OPS 순 · ${asOf ? `${md(asOf)} 기준 · ` : ""}규정타석 50% 이상`}
            loading={!batters.data}
            rows={(batters.data?.batters ?? []).map((b) => {
              const best = b.strengths[0];
              return {
                id: b.player_id, name: b.name, team: name,
                meta: [b.back_number != null && `#${b.back_number}`, b.position, b.hr != null && `${b.hr}홈런`].filter(Boolean).join(" · "),
                tag: best ? `${axisCopy(best.axis)?.chip ?? best.axis} ${best.rank}위` : null,
                value: rate3(b.ops), scenes: b.scene_count,
              };
            })}
          />}
          {pitchers.isError ? <Retry text="선발 투수 기록을 불러오지 못했어요" onRetry={() => pitchers.refetch()} /> : <PlayerTable
            title="선발 투수"
            sub={`이닝 순 · ${asOf ? `${md(asOf)} 기준 · ` : ""}오른쪽 숫자는 WHIP (낮을수록 좋아요)`}
            loading={!pitchers.data}
            rows={(pitchers.data?.pitchers ?? []).map((p) => {
              const best = p.axis_ranks && Object.entries(p.axis_ranks).sort((a, b) => a[1] - b[1])[0];
              return {
                id: p.player_id, name: p.name, team: name,
                meta: [p.back_number != null && `#${p.back_number}`, `${p.g}경기 ${innings(p.outs)}이닝`, `${p.so}삼진`].filter(Boolean).join(" · "),
                tag: best ? `${axisCopy(best[0])?.chip ?? best[0]} ${best[1]}위` : `선발 ${p.gs}경기`,
                value: p.whip?.toFixed(2) ?? "–", scenes: p.scene_count,
              };
            })}
          />}
        </div>
      </Wrap>
    </>
  );
}

function teamSceneText(s: TeamScene) {
  if (s.kind === "outing") {
    return { badge: s.role === "선발" ? "선발 등판" : "구원 등판", line: s.line ? outingLine(s.line) : "등판", title: `${s.player.name} ${s.line ? outingLine(s.line) : ""}`.trim() };
  }
  const what = `${HR_RUNS[s.runs ?? 0] ?? ""} 홈런 · ${s.inning}회${s.inningHalf}`.trim();
  return { badge: s.hrSeq ? `시즌 ${s.hrSeq}호` : "홈런", line: what, title: `${s.player.name} ${s.hrSeq ? `${s.hrSeq}호 · ` : ""}${HR_RUNS[s.runs ?? 0] ?? ""} 홈런`.replace("  ", " ") };
}

function SceneRow({ team, data, playingId, onPlay }: {
  team: string;
  data?: { counts: { home_run_scenes: number; pitcher_scenes: number }; scenes: TeamScene[] };
  playingId: string | null;
  onPlay: (clip: TeamScene["clip"], title: string, sub: string) => void;
}) {
  const ref = useRef<HTMLUListElement>(null);
  const scroll = (dir: 1 | -1) => ref.current?.scrollBy({ left: dir * ref.current.clientWidth * 0.75, behavior: "smooth" });
  return (
    <>
      <SectionHead
        title={`${team}의 최근 장면`}
        sub={data ? `${team} 선수들의 홈런 장면 ${data.counts.home_run_scenes} · 등판 장면 ${data.counts.pitcher_scenes} · 최신순` : undefined}
        right={
          <div className="flex gap-2">
            {([-1, 1] as const).map((d) => (
              <button key={d} onClick={() => scroll(d)} aria-label={d < 0 ? "앞 장면" : "다음 장면"} className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface hover:bg-surface-2">
                {d < 0 ? "‹" : "›"}
              </button>
            ))}
          </div>
        }
      />
      {!data ? (
        <div className="h-[220px] animate-pulse rounded-3xl bg-surface-2" />
      ) : data.scenes.length === 0 ? (
        <p className="rounded-3xl border border-line bg-surface py-10 text-center text-sm text-fg-2">이번 시즌 확정된 장면이 아직 없어요</p>
      ) : (
        <ul ref={ref} className="animate-appear flex snap-x gap-4 overflow-x-auto pb-2 [scrollbar-width:none]">
          {data.scenes.map((s) => {
            const x = teamSceneText(s);
            const sub = `vs ${s.opponent} · ${md(s.date)}`;
            return (
              <li key={`${s.kind}-${s.player.player_id}-${s.date}-${s.inning ?? ""}${s.inningHalf ?? ""}`} className="w-[calc((100%-48px)/4)] min-w-[220px] shrink-0 snap-start">
                <button onClick={() => onPlay(s.clip, x.title, sub)} aria-current={playingId === x.title ? "true" : undefined} className="group block w-full text-left aria-[current=true]:opacity-50">
                  <span className="relative block aspect-video overflow-hidden rounded-xl">
                    <img src={thumbnailUrl(s.clip.videoId)} alt="" className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]" />
                    <span className="absolute top-2 left-2 rounded-md bg-black/75 px-1.5 py-0.5 text-[11px] font-bold text-white">{x.badge}</span>
                    <span className="absolute bottom-2 left-2 flex items-center gap-1 rounded-md bg-black/75 px-1.5 py-0.5 font-num text-[11px] font-semibold text-white">
                      <PlayGlyph size={7} /> {mmss(clipLength(s.clip))}
                    </span>
                  </span>
                  <span className="mt-2.5 flex items-center gap-2">
                    <PlayerAvatar id={s.player.player_id} name={s.player.name} team={team} size={28} />
                    <span className="text-sm font-bold group-hover:underline">{s.player.name}</span>
                  </span>
                  <span className="mt-1 block text-xs text-fg-2">{x.line}</span>
                  <span className="mt-0.5 block text-xs text-muted">{sub}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}


type TableRow = { id: string; name: string; team: string; meta: string; tag: string | null; value: string; scenes: number };

function PlayerTable({ title, sub, rows, loading }: { title: string; sub: ReactNode; rows: TableRow[]; loading: boolean }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, 6);
  return (
    <section className="rounded-3xl border border-line bg-surface p-6">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold">{title}</h2>
          <p className="mt-1 text-xs text-fg-2">{sub}</p>
        </div>
        {rows.length > 6 && (
          <button onClick={() => setAll(!all)} className="shrink-0 text-xs font-bold text-brand-text hover:underline">{all ? "접기" : `전체 ${rows.length}명 ›`}</button>
        )}
      </div>
      {loading ? (
        <div className="h-[360px] animate-pulse rounded-2xl bg-surface-2" />
      ) : rows.length === 0 ? (
        <p className="py-10 text-center text-sm text-fg-2">비교 대상 선수가 없어요</p>
      ) : (
        <ol className="animate-appear divide-y divide-line">
          {shown.map((r) => (
            <li key={r.id}>
              <Link href={playerHref(r.id)} className="grid grid-cols-[44px_1fr_auto_56px_auto] items-center gap-3 py-3 hover:bg-surface-2">
                <PlayerAvatar id={r.id} name={r.name} team={r.team} size={44} />
                <span className="min-w-0">
                  <span className="block truncate text-[15px] font-bold">{r.name}</span>
                  <span className="block truncate text-xs text-muted">{r.meta}</span>
                </span>
                <span className="rounded-md bg-surface-2 px-2 py-1 text-[11px] font-bold text-fg-2">{r.tag}</span>
                <span className="text-right font-num text-[17px] font-bold">{r.value}</span>
                <span className="flex h-7 items-center gap-1 rounded-full bg-accent px-2.5 text-[11px] font-bold text-white">
                  <PlayGlyph size={7} /> 장면 {r.scenes}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
