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
      {/* 배경: 그날 장면 썸네일을 흐리게 */}
      <div className="absolute inset-0 grid grid-cols-6 gap-4 opacity-60 blur-[6px]" aria-hidden>
        {[...collage, ...collage, ...collage].slice(0, 24).map((v, i) => (
          <img key={i} src={thumbnailUrl(v)} alt="" className="aspect-video w-full rounded-xl object-cover" />
        ))}
      </div>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(230,231,234,0.92)_30%,rgba(230,231,234,0.75)_100%)]" aria-hidden />
      <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-b from-transparent to-bg" aria-hidden />

      <Wrap className="relative grid items-center gap-14 py-10 lg:grid-cols-[600px_1fr]">
        <div>
          <p className="text-sm font-bold text-brand-text">선수 찾기</p>
          <h1 className="mt-2 text-4xl leading-[1.2] font-black tracking-tight">누구의 장면을 볼까요?</h1>
          <div className="mt-6">
            <SearchBox large autoFocus />
          </div>
          {chips.length > 0 && (
            <div className="mt-5">
              <div className="mb-2 flex items-center justify-between gap-3">
                <span className="text-[13px] text-fg-2">{firstVisit ? "추천 선수" : "최근 본 선수"}</span>
                {firstVisit && <span className="text-xs text-muted">지금 잘하는 선수 · 선수 화면을 보면 「최근 본 선수」로 바뀌어요</span>}
              </div>
              <ul className="flex flex-wrap gap-2">
                {chips.map((p, i) => (
                  <li key={p.id}>
                    <Link
                      href={playerHref(p.id)}
                      className={`flex h-11 items-center gap-2 rounded-full border pr-4 pl-1.5 text-sm font-medium transition-colors duration-[120ms] ${
                        !firstVisit && i === 0 ? "border-brand bg-brand-soft" : "border-line bg-surface hover:bg-surface-2"
                      }`}
                    >
                      <PlayerAvatar id={p.id} name={p.name} team={p.team} size={32} />
                      {p.name}
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
          <PickTeamCard onPick={setMyTeam} />
        )}
      </Wrap>
    </section>
  );
}

function MyTeamCard({ team, day, onChange, onPlay }: { team: string; day: Day | undefined; onChange: () => void; onPlay: (c: Clip, l: string) => void }) {
  const g = day?.games.find((x) => x.away.team === team || x.home.team === team);
  const home = g?.home.team === team;
  const me = g ? (home ? g.home : g.away) : null;
  const opp = g ? (home ? g.away : g.home) : null;
  const len = g?.highlight ? clipLength(g.highlight) : null;
  return (
    <div className="rounded-3xl border border-line bg-surface p-6">
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
          <p className="mt-0.5 text-xs">
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
          className="mt-4 flex h-9 w-full items-center justify-center gap-2 rounded-xl bg-surface-2 text-[13px] font-bold transition-colors duration-[120ms] hover:bg-surface-3"
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
