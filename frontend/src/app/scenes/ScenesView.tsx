"use client";

import Link from "next/link";
/* eslint-disable @next/next/no-img-element -- 정적 내보내기: 썸네일 핫링크(설계 8-2) */
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Wrap, clipLength, gameHref, sceneTitle } from "@/components/home/common";
import type { Playing } from "@/components/home/DayScenes";
import InlinePlayer from "@/components/InlinePlayer";
import { thumbnailUrl } from "@/components/ScenePlayer";
import GameScore from "@/components/schedule/GameScore";
import NoGames from "@/components/schedule/NoGames";
import WeekStrip from "@/components/schedule/WeekStrip";
import { Chip, Empty } from "@/components/ui/Chip";
import { PlayGlyph, TeamLogo, mmss } from "@/components/ui/Media";
import Seg from "@/components/ui/Seg";
import { getDay, getMeta, qk, type DayGame, type DayScene } from "@/lib/api";
import { longDate } from "@/lib/dates";
import { md } from "@/lib/format";
import { useMyTeam } from "@/lib/local";
import { team as teamOf, type Team } from "@/lib/teams";
import { ChevronDown } from "@/components/ui/Chevron";

type Filter = "all" | "home_run" | "outing" | "my";

/**
 * 10 장면 (Figma 182:2066) — 날짜별 · 경기별로 그날 확정 장면을 모아 본다.
 * 위쪽 한 주 띠(API-34) → 고른 날의 경기 카드(API-14). 장면은 누른 경기 카드 안에서 바로 재생한다 (별도 창 없음)
 * 경기장 이름은 데이터에 없어 넣지 않는다 (시안 「종료 · 광주」 → 「종료」)
 */
export default function ScenesView() {
  const params = useSearchParams();
  const router = useRouter();
  const [myTeam] = useMyTeam();
  const meta = useQuery({ queryKey: qk.meta(), queryFn: ({ signal }) => getMeta(signal) });
  const asOf = meta.data?.data_as_of ?? null;
  const date = params.get("date") ?? asOf;
  const day = useQuery({ queryKey: qk.day(date), queryFn: ({ signal }) => getDay(date, signal), enabled: !!date });
  const [filter, setFilter] = useState<Filter>("all");
  const [playing, setPlaying] = useState<(Playing & { gamePk: string }) | null>(null);
  const pick = (d: string) => {
    setPlaying(null);
    router.replace(`/scenes/?date=${d}`, { scroll: false });
  };

  const games = day.data?.games ?? [];
  const all = games.flatMap((g) => g.scenes);
  const count = {
    all: all.length,
    home_run: all.filter((s) => s.kind === "home_run").length,
    outing: all.filter((s) => s.kind === "outing").length,
    my: myTeam ? all.filter((s) => s.team === myTeam).length : 0,
  };
  const keep = (s: DayScene) =>
    filter === "all" || (filter === "my" ? s.team === myTeam : s.kind === filter);
  const shown = games
    .map((g) => ({ game: g, scenes: g.scenes.filter(keep).sort(byTime) }))
    .filter((x) => filter === "all" || x.scenes.length > 0)
    .sort((a, b) => Number(isMine(b.game, myTeam)) - Number(isMine(a.game, myTeam))); // 응원팀 경기를 맨 위로
  const future = !!(date && asOf && date > asOf);

  return (
    <Wrap className="pt-3 pb-6 md:pt-10 md:pb-24">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-black tracking-tight md:text-[40px] md:font-extrabold">장면</h1>
          <p className="mt-1 text-xs text-fg-2 md:mt-1.5 md:text-sm">
            {[meta.data?.season && `${meta.data.season} 정규시즌`, asOf && `${md(asOf)} 기준`, "날짜별 · 경기별"].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="hidden flex-wrap gap-2 md:flex" role="group" aria-label="장면 종류">
          <Chip on={filter === "all"} onClick={() => setFilter("all")}>전체 {count.all}</Chip>
          <Chip on={filter === "home_run"} onClick={() => setFilter("home_run")}>홈런 {count.home_run}</Chip>
          <Chip on={filter === "outing"} onClick={() => setFilter("outing")}>투수 {count.outing}</Chip>
          {myTeam && (
            <Chip on={filter === "my"} onClick={() => setFilter("my")}>
              <TeamLogo team={myTeam} height={14} /> 응원팀 {myTeam} {count.my}
            </Chip>
          )}
        </div>
      </div>

      <Seg className="mt-3 md:hidden" label="장면 종류" value={filter} onChange={setFilter}
           items={[{ key: "all", label: `전체 ${count.all}` }, { key: "home_run", label: `홈런 ${count.home_run}` }, { key: "outing", label: `투수 ${count.outing}` },
                   ...(myTeam ? [{ key: "my" as const, label: `${myTeam} ${count.my}` }] : [])]} />

      {date && (
        <div className="mt-2 md:mt-7">
          <WeekStrip date={date} onPick={pick} caption={(d) => `${d.games}경기 · 장면 ${d.home_run_scenes + d.pitcher_scenes}`} short={(d) => `${d.home_run_scenes + d.pitcher_scenes}`} />
        </div>
      )}

      {date && (future || day.data?.games.length === 0) ? (
        <NoGames date={date} asOf={asOf} prev={day.data?.prev_date ?? null} next={day.data?.next_date ?? null} onPick={pick} />
      ) : day.isError || (!date && meta.isError) ? (
        <Empty text="장면을 불러오지 못했어요" sub="잠시 뒤 다시 시도해 주세요."
               action={{ label: "다시 시도", onClick: () => (date ? day.refetch() : meta.refetch()) }} />
      ) : !day.data ? (
        <div className="mt-8 h-[600px] animate-pulse rounded-3xl bg-surface-2" />
      ) : (
        <div className="animate-appear">
          <h2 className="mt-9 hidden text-2xl font-bold md:block">
            {longDate(day.data.date)} · {games.length}경기 · 장면 {count.all} (홈런 {count.home_run} · 투수 {count.outing})
          </h2>
          <div className="mt-5 md:hidden">
            <h2 className="text-xl font-black">{longDate(day.data.date)}</h2>
            <p className="mt-1 text-xs text-fg-2">{games.length}경기 · 장면 {count.all} (홈런 {count.home_run} · 투수 {count.outing})</p>
          </div>
          {shown.length === 0 && (
            <Empty text={filter === "my" && !games.some((g) => isMine(g, myTeam)) ? `이날은 ${myTeam} 경기가 없어요` : "이날은 고른 종류의 장면이 없어요"}
                   action={{ label: "전체 보기", onClick: () => setFilter("all") }} />
          )}
          <ul className="mt-2 space-y-2 md:mt-5 md:space-y-4">
            {shown.map(({ game, scenes }, i) => (
              <GameCard
                key={game.game_pk}
                game={game}
                first={i < 2}
                scenes={scenes}
                mine={isMine(game, myTeam) ? teamOf(myTeam) : null}
                playing={playing?.gamePk === game.game_pk ? playing : null}
                onPlay={(p) => setPlaying(p && { ...p, gamePk: game.game_pk })}
              />
            ))}
          </ul>
        </div>
      )}
    </Wrap>
  );
}

const isMine = (g: DayGame, my: string | null) => !!my && (g.away.team === my || g.home.team === my);

/** 경기 안 장면 순서: 등판(선발 → 구원) 먼저, 홈런은 나온 순서 (회 → 초 · 말) */
const byTime = (a: DayScene, b: DayScene) => {
  const k = (s: DayScene) => (s.kind === "outing" ? (s.role === "선발" ? -2 : -1) : (s.inning ?? 0) * 2 + (s.inningHalf === "말" ? 1 : 0));
  return k(a) - k(b);
};

function sceneSubLine(s: DayScene) {
  if (s.kind === "outing") return `${s.role} 등판`;
  return `${s.inning}회${s.inningHalf}`;
}

const MOBILE_SCENES = 3; // 모바일은 펼친 경기도 장면 세 줄까지, 나머지는 「모두 보기」

function GameCard({ game: g, scenes, first, mine, playing, onPlay }: {
  game: DayGame;
  scenes: DayScene[];
  /** 모바일은 위 두 경기만 펼쳐 둔다 (M10). 나머지는 누르면 펼침 */
  first: boolean;
  mine: Team | null;
  playing: Playing | null;
  onPlay: (p: Playing | null) => void;
}) {
  const [opened, setOpened] = useState(false);
  const [all, setAll] = useState(false);
  const open = first || opened || !!mine || !!playing;
  const fold = open ? "" : "hidden md:block";
  const extra = (g.innings ?? 9) > 9 ? `연장 ${g.innings}회` : null;
  const draw = g.away.result === "D" ? "무승부" : null;
  const hr = scenes.filter((s) => s.kind === "home_run").length;
  const summary = [["종료", extra, draw].filter(Boolean).join(" · "), `장면 ${scenes.length}${scenes.length ? ` (${[hr && `홈런 ${hr}`, scenes.length - hr && `투수 ${scenes.length - hr}`].filter(Boolean).join(" · ")})` : ""}`].join(" · ");
  return (
    <li
      className="grid gap-2 rounded-2xl border border-line bg-surface p-3.5 md:gap-6 md:rounded-3xl md:p-6 lg:grid-cols-[220px_1fr]"
      style={mine ? { borderColor: mine.band, borderWidth: 2 } : undefined} // 응원팀 경기는 팀 색 테두리
    >
      {open ? (
        <div className="md:hidden">
          <GameScore game={g} />
          <p className="mt-1 text-center text-xs text-fg-2">{summary}</p>
        </div>
      ) : (
        <button onClick={() => setOpened(true)} aria-expanded={false} className="flex w-full items-center gap-2 text-left md:hidden">
          <span className="min-w-0 flex-1">
            <GameScore game={g} />
            <span className="mt-1 block text-center text-xs text-fg-2">{summary}</span>
          </span>
          <ChevronDown />
        </button>
      )}
      <div className={fold}>
        <p className="hidden items-center gap-1.5 text-xs text-fg-2 md:flex">
          {["종료", extra, draw, g.stage_label].filter(Boolean).join(" · ")}
          {mine && <span className="rounded-md bg-brand-soft px-1.5 py-0.5 text-[11px] font-bold text-brand-text">응원팀</span>}
        </p>
        <div className="mt-3 hidden space-y-2 md:block">
          {[g.away, g.home].map((t) => (
            <p key={t.team} className="flex items-center gap-2.5">
              <TeamLogo team={t.team} height={22} />
              <span className={`flex-1 text-[15px] ${t.result === "W" ? "font-bold" : "font-medium text-fg-2"}`}>{t.team}</span>
              <span className={`font-display text-[28px] leading-none font-extrabold ${t.result === "W" ? "" : "text-muted"}`}>{t.score}</span>
            </p>
          ))}
        </div>
        <Link href={gameHref(g.game_pk)} className="mt-3 hidden text-xs font-bold text-brand-text hover:underline md:inline-block">경기 상세 ›</Link>
        {g.highlight && (
          <button
            onClick={() => onPlay({ clip: g.highlight!, title: `${g.away.team} : ${g.home.team} 경기 하이라이트`, sub: "처음부터" })}
            className="flex h-11 w-full items-center justify-center gap-1.5 rounded-xl bg-surface-2 text-[13px] font-bold hover:bg-surface-3 md:mt-4 md:h-8 md:w-auto md:rounded-full md:px-3.5 md:text-xs"
          >
            <PlayGlyph size={7} /> 이 경기 하이라이트 {mmss(clipLength(g.highlight))}
          </button>
        )}
        {g.homeRuns.some((h) => !h.clip) && (
          <p className="mt-2 text-xs text-fg-2 md:mt-3 md:text-muted">
            영상 없음 · {g.homeRuns.filter((h) => !h.clip).map((h) => `${h.name}${h.hrSeq ? ` ${h.hrSeq}호` : ""}`).join(", ")}
          </p>
        )}
      </div>

      <div className={`min-w-0 ${fold}`}>
        {playing && <InlinePlayer playing={playing} onClose={() => onPlay(null)} className="mb-5" />}
        {scenes.length === 0 ? (
          <p className="py-6 text-sm text-fg-2">이 경기는 확정된 장면이 아직 없어요</p>
        ) : (
          <ul className="grid divide-y divide-line md:grid-cols-4 md:gap-4 md:divide-y-0">
            {scenes.map((s, i) => {
              const title = sceneTitle(s);
              const on = playing?.clip.videoId === s.clip.videoId && playing.title === title; // 한 영상에 홈런 둘이 담긴 경우가 있어 제목까지 본다
              return (
                <li key={`${s.kind}-${s.player.player_id}-${s.inning ?? ""}${s.inningHalf ?? ""}`} className={!all && i >= MOBILE_SCENES ? "hidden md:block" : ""}>
                  <button
                    onClick={() => onPlay({ clip: s.clip, title, sub: sceneSubLine(s) })}
                    aria-current={on ? "true" : undefined}
                    className="group flex w-full items-center gap-3 py-2 text-left aria-[current=true]:opacity-50 md:block md:py-0"
                  >
                    <span className="relative block aspect-video w-28 shrink-0 overflow-hidden rounded-lg md:w-auto md:rounded-xl">
                      <img src={thumbnailUrl(s.clip.videoId)} alt="" className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]" />
                      <span className={`absolute top-2 left-2 hidden rounded-md px-1.5 py-0.5 text-[11px] font-bold text-white md:block ${s.kind === "outing" ? "bg-brand" : "bg-black/75"}`}>
                        {s.kind === "outing" ? "투수" : "홈런"}
                      </span>
                      <span className="absolute bottom-2 left-2 flex items-center gap-1 rounded-md bg-black/75 px-1.5 py-0.5 font-num text-[11px] font-semibold text-white">
                        <PlayGlyph size={7} /> {mmss(clipLength(s.clip))}
                      </span>
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-bold group-hover:underline md:mt-2">{title}</span>
                      <span className="mt-0.5 block text-xs text-fg-2">{sceneSubLine(s)}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {!all && scenes.length > MOBILE_SCENES && (
          <button onClick={() => setAll(true)} className="flex h-11 w-full items-center justify-center text-[13px] font-bold text-brand-text md:hidden">
            이 경기 장면 {scenes.length}개 모두 보기 ›
          </button>
        )}
      </div>
    </li>
  );
}
