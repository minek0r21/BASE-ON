"use client";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기: 썸네일 핫링크(설계 8-2) */
import Link from "next/link";
import SearchBox, { playerHref } from "@/components/SearchBox";
import { thumbnailUrl } from "@/components/ScenePlayer";
import { PlayGlyph, PlayerAvatar, TeamLogo, mmss } from "@/components/ui/Media";
import type { Clip, Day } from "@/lib/api";
import { md } from "@/lib/format";
import { useMyTeam, useRecentPlayers, type RecentPlayer } from "@/lib/local";
import { TEAMS, TEAM_NAMES } from "@/lib/teams";
import { Wrap, clipLength, weekday } from "./common";

/**
 * 히어로 (Figma 01 홈 · 장면이 주인공): 왼쪽 검색 + 최근 본 선수, 오른쪽 응원팀 경기 카드.
 * 첫 방문(응원팀 · 최근 본 선수 없음)이면 추천 선수 + 응원팀 고르기 카드 (186:2093)
 */
export default function Hero({ day, recommended, onPlay }: {
  day: Day | undefined;
  recommended: RecentPlayer[];
  onPlay: (clip: Clip, label: string) => void;
}) {
  const recent = useRecentPlayers();
  const [myTeam, setMyTeam] = useMyTeam();
  const firstVisit = recent.length === 0;
  const chips = firstVisit ? recommended : recent.slice(0, 4);
  const collage = (day?.games ?? []).flatMap((g) => g.scenes.map((s) => s.clip.videoId)).slice(0, 12);

  return (
    <section className="relative overflow-hidden">
      {/* 배경: 그날 장면 썸네일을 흐리게. 모바일은 안 그리는데, lazy가 없으면 숨겨도 24장을 다 받는다 */}
      <div className="absolute inset-0 hidden grid-cols-6 gap-4 opacity-60 blur-[6px] md:grid" aria-hidden>
        {[...collage, ...collage, ...collage].slice(0, 24).map((v, i) => (
          <img key={i} src={thumbnailUrl(v)} alt="" loading="lazy" className="aspect-video w-full rounded-xl object-cover" />
        ))}
      </div>
      <div className="absolute inset-0 hidden bg-[radial-gradient(ellipse_at_center,rgba(230,231,234,0.92)_30%,rgba(230,231,234,0.75)_100%)] md:block" aria-hidden />
      <div className="absolute inset-x-0 bottom-0 hidden h-24 bg-gradient-to-b from-transparent to-bg md:block" aria-hidden />

      <Wrap className="relative grid items-center gap-3 pt-3 pb-5 md:gap-14 md:py-10 lg:grid-cols-[600px_1fr]">
        <div>
          <p className="hidden text-sm font-bold text-brand-text md:block">선수 찾기</p>
          <h1 className="text-[26px] leading-[1.2] font-black tracking-tight md:mt-2 md:text-4xl">누구의 장면을 볼까요?</h1>
          <div className="mt-3.5 md:mt-6">
            <SearchBox large autoFocus />
          </div>
          <MobileTeams team={myTeam} onPick={setMyTeam} />
          {chips.length > 0 && (
            <div className={`mt-3.5 md:mt-5 ${firstVisit && !myTeam ? "" : "hidden md:block"}`}>
              <div className="mb-2 flex flex-col gap-0.5 md:flex-row md:items-center md:justify-between md:gap-3">
                <span className="text-[13px] font-bold md:font-normal md:text-fg-2">{firstVisit ? "추천 선수" : "최근 본 선수"}</span>
                {firstVisit && <span className="text-xs text-fg-2 md:text-muted">지금 잘하는 선수 · 선수 화면을 보면 「최근 본 선수」로 바뀌어요</span>}
              </div>
              <ul className="grid grid-cols-2 gap-2 md:flex md:flex-wrap">
                {chips.map((p, i) => (
                  <li key={p.id}>
                    <Link
                      href={playerHref(p.id)}
                      className={`flex h-11 items-center gap-2 rounded-xl border pr-3 pl-1.5 text-sm font-bold transition-colors duration-[120ms] md:h-12 md:gap-2.5 md:rounded-full md:pr-4 md:pl-1 md:font-medium ${
                        !firstVisit && i === 0 ? "border-brand bg-brand-soft" : "border-line bg-surface hover:bg-surface-2"
                      }`}
                    >
                      <PlayerAvatar id={p.id} name={p.name} team={p.team} size={32} />
                      <span className="truncate">{p.name}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {myTeam ? (
          <MyTeamCard team={myTeam} day={day} onChange={() => setMyTeam(null)} onPlay={onPlay} />
        ) : (
          <div className="hidden md:block"><PickTeamCard onPick={setMyTeam} /></div>
        )}
      </Wrap>
    </section>
  );
}

/** M01 응원팀 5 × 2 — 가로로 밀지 않는다. 칸은 폭을 똑같이 나눠 가져 320에서도 두 줄이다. 고른 팀을 다시 누르면 해제 */
function MobileTeams({ team, onPick }: { team: string | null; onPick: (t: string | null) => void }) {
  return (
    <div className="md:hidden">
      {/* 안내 상자는 첫 화면을 1/6 차지해서 칸 이름 한 줄로 줄였다 (M01b · 11-08) */}
      <div className="mt-3.5 mb-2 flex items-center justify-between gap-2">
        <span className="text-[13px] font-bold">{team ? "응원팀" : "응원팀 고르기"}</span>
        <span className="text-xs text-fg-2">이 브라우저에만 저장</span>
      </div>
      <ul className="grid grid-cols-5 gap-1.5">
        {TEAM_NAMES.map((t) => (
          <li key={t}>
            <button
              onClick={() => onPick(team === t ? null : t)}
              aria-pressed={team === t}
              aria-label={`응원팀 ${TEAMS[t].full}`}
              className="flex h-11 w-full items-center justify-center gap-1 rounded-xl border border-line bg-surface text-[13px] font-bold aria-pressed:border-fg aria-pressed:bg-fg aria-pressed:text-white"
            >
              <TeamLogo team={t} height={14} />
              {t}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function MyTeamCard({ team, day, onChange, onPlay }: { team: string; day: Day | undefined; onChange: () => void; onPlay: (c: Clip, l: string) => void }) {
  const g = day?.games.find((x) => x.away.team === team || x.home.team === team);
  const home = g?.home.team === team;
  const me = g ? (home ? g.home : g.away) : null;
  const opp = g ? (home ? g.away : g.home) : null;
  const len = g?.highlight ? clipLength(g.highlight) : null;
  return (
    <div className="rounded-2xl border border-line bg-surface p-3.5 md:rounded-3xl md:p-6">
      <div className="flex items-start gap-3">
        <TeamLogo team={team} height={22} />
        <div className="min-w-0 flex-1">
          <p className="text-xs text-fg-2">
            응원팀 {team}
            {day && g && ` · ${md(day.date)} (${weekday(day.date)}) ${opp!.team}전`}
          </p>
          {g && me && opp ? (
            <p className="mt-0.5 flex items-center gap-2 text-base font-bold">
              {team} {me.score} : {opp.score} {opp.team}
              <span className="rounded-md bg-surface-3 px-1.5 py-0.5 text-[11px] font-medium text-fg-2">
                {me.result === "W" ? "승" : me.result === "L" ? "패" : "무"}
              </span>
            </p>
          ) : (
            <p className="mt-0.5 text-base font-bold">{day ? `${md(day.date)}에는 ${team} 경기가 없어요` : "…"}</p>
          )}
          <p className="mt-0.5 hidden text-xs md:block">
            <button onClick={onChange} className="text-brand-text hover:underline">
              응원팀 바꾸기 ›
            </button>
            <span className="text-muted"> · 이 브라우저에만 저장돼요</span>
          </p>
        </div>
      </div>
      {g?.highlight && (
        <button
          onClick={() => onPlay(g.highlight!, `${g.away.team} ${g.away.score} : ${g.home.score} ${g.home.team} 하이라이트`)}
          className="mt-3 flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-surface-2 text-[13px] font-bold transition-colors duration-[120ms] hover:bg-surface-3 md:mt-4 md:h-9"
        >
          <PlayGlyph /> 이 경기 하이라이트 {mmss(len)}
        </button>
      )}
    </div>
  );
}

function PickTeamCard({ onPick }: { onPick: (t: string) => void }) {
  return (
    <div className="rounded-3xl border border-line bg-surface p-6">
      <div className="rounded-2xl bg-brand-soft px-4 py-3">
        <p className="text-sm font-bold text-brand-text">응원팀을 골라 보세요</p>
        <p className="mt-0.5 text-xs leading-relaxed text-fg-2">
          고르면 그 팀 경기 결과와 장면이 맨 위에 와요. 로그인 없이 이 브라우저에만 저장돼요. 건너뛰어도 돼요.
        </p>
      </div>
      <p className="mt-4 mb-2 text-[13px] text-fg-2">응원팀</p>
      <ul className="flex flex-wrap gap-2">
        {TEAM_NAMES.map((t) => (
          <li key={t}>
            <button
              onClick={() => onPick(t)}
              className="flex h-11 items-center gap-2 rounded-full border border-line bg-surface pr-4 pl-3 text-sm font-medium transition-colors duration-[120ms] hover:bg-surface-2"
              aria-label={`응원팀 ${TEAMS[t].full}`}
            >
              <TeamLogo team={t} height={18} />
              {t}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
