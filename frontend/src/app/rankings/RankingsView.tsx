"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, useState } from "react";
import { Wrap, clipLength } from "@/components/home/common";
import ScenePlayer from "@/components/ScenePlayer";
import { playerHref } from "@/components/SearchBox";
import { PlayGlyph, PlayerAvatar, TeamLogo, mmss } from "@/components/ui/Media";
import { getMeta, getRankings, qk, type RankRow } from "@/lib/api";
import { AXES, GROUP_RULE, axisGap, gapText, rankingsHref, type AxisCopy, type Role } from "@/lib/axes";
import { md } from "@/lib/format";
import { leaguePosition } from "@/lib/position";
import { useRosterTeam } from "@/lib/local";
import { team as teamOf } from "@/lib/teams";
import { barOpacity, isTop20, josa } from "@/lib/abilities";
import Help from "@/components/ui/Help";
import Slide from "@/components/ui/Slide";
import { GROUP_HELP } from "@/lib/constants";
import PlayersHead from "./PlayersHead";
import TeamPicker from "./TeamPicker";

const FIRST = 10; // 처음엔 10위까지, 「11 ~ n위 더 보기」로 전부
const COLS = "grid-cols-[48px_minmax(0,1.5fr)_minmax(0,1.2fr)_110px_70px_70px_70px_150px]";

/**
 * 05 능력별 순위 (Figma 142:805) — 선수 탭의 두 번째 탭 (첫 화면은 팀별 선수, 10-31 사용자). 타자 · 투수(선발) 지표 5개마다 비교 대상 전원 순위.
 * 줄마다 「리그 평균 대비」 — 등수만으로는 안 보이는 선수 사이 간격을 보여준다. 숫자는 실제 차이, 막대는 좋은 쪽을
 * 오른쪽으로 두고 평균을 가운데, 전체에서 가장 먼 차이를 끝으로 잡는다. 상위 · 하위 문구(lib/position.ts)는 마우스를 올리면 나온다.
 * 대표 장면은 그 줄 바로 아래에서 재생한다 (별도 창 없음).
 * 팀 로고 줄(?team=)로 한 팀만 걸러 본다 — 등수는 리그 등수 그대로, 막대 눈금도 리그 전체 기준 (10-31 사용자)
 */
export default function RankingsView() {
  const params = useSearchParams();
  const router = useRouter();
  const role: Role = params.get("role") === "pitcher" ? "pitcher" : "batter";
  const axes = AXES[role];
  const axis = axes.find((a) => a.key === params.get("axis")) ?? axes[0];
  const teamF = teamOf(params.get("team"))?.name ?? null;
  const [, setLastTeam] = useRosterTeam();
  const href = (r: Role, a: string | undefined, t: string | null) => `${rankingsHref(r, a)}${t ? `&${new URLSearchParams({ team: t })}` : ""}`;
  const go = (r: Role, a?: string) => router.replace(href(r, a, teamF), { scroll: false });
  const pickTeam = (t: string | null) => {
    if (t) setLastTeam(t); // 팀별 선수 탭도 이 팀으로
    setMore(false); setPlaying(null);
    router.replace(href(role, axis.key, t), { scroll: false });
  };

  const meta = useQuery({ queryKey: qk.meta(), queryFn: ({ signal }) => getMeta(signal) });
  const q = useQuery({ queryKey: qk.rankings(role, axis.key), queryFn: ({ signal }) => getRankings(role, axis.key, signal) });
  const [more, setMore] = useState(false);
  const [playing, setPlaying] = useState<string | null>(null); // 재생 중인 줄의 player_id

  const asOf = meta.data?.data_as_of;
  const data = q.data;
  const list = data ? (teamF ? data.rows.filter((r) => r.team === teamF) : data.rows) : [];
  const rows = teamF || more ? list : list.slice(0, FIRST); // 한 팀이면 전부
  const maxGap = data ? Math.max(0, ...data.rows.map((r) => Math.abs(axisGap(axis.copy, r.value, data.leagueAvg) ?? 0))) : 0;

  return (
    <Wrap className="pt-10 pb-24">
      <PlayersHead tab="rank" sub={[data?.season && `${data.season} 정규시즌`, asOf && `${md(asOf)} 기준`].filter(Boolean).join(" · ")} />

      <div className="mt-7 flex flex-wrap items-center gap-3">
        <Slide mark="rounded-full bg-surface-3" className="flex rounded-full border border-line bg-surface p-1" role="group" aria-label="타자 · 투수">
          {(["batter", "pitcher"] as const).map((r) => (
            <button
              key={r}
              onClick={() => { setMore(false); setPlaying(null); go(r); }}
              aria-pressed={role === r}
              className="relative h-[30px] rounded-full px-5 text-[13px] font-medium text-fg-2 transition-colors duration-[120ms] aria-pressed:font-bold aria-pressed:text-fg"
            >
              {r === "batter" ? "타자" : "투수"}
            </button>
          ))}
        </Slide>
        <div className="flex flex-wrap gap-2" role="group" aria-label="지표">
          {axes.map((a) => (
            <button
              key={a.key}
              onClick={() => { setMore(false); setPlaying(null); go(role, a.key); }}
              aria-pressed={axis.key === a.key}
              className="h-9 rounded-full border border-line bg-surface px-4 text-[13px] font-medium transition-colors duration-[120ms] hover:bg-surface-2 aria-pressed:border-accent aria-pressed:bg-accent aria-pressed:font-bold aria-pressed:text-white"
            >
              {a.copy.chip}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4"><TeamPicker value={teamF} onPick={pickTeam} withAll /></div>

      <Summary copy={axis.copy} role={role} data={data} shown={rows} team={teamF} />

      {q.isError ? (
        <div className="mt-5 flex items-center justify-between rounded-3xl border border-line bg-surface px-6 py-5 text-sm">
          <span className="text-fg-2">순위를 불러오지 못했어요</span>
          <button onClick={() => q.refetch()} className="rounded-xl bg-surface-2 px-4 py-2 font-bold hover:bg-surface-3">다시 시도</button>
        </div>
      ) : !data ? (
        <div className="mt-5 h-[640px] animate-pulse rounded-3xl bg-surface-2" />
      ) : (
        <div className="animate-appear mt-5 overflow-x-auto rounded-3xl border border-line bg-surface">
          <div className="min-w-[960px]">
            <div className={`grid ${COLS} items-center gap-4 border-b border-line px-6 py-3 text-xs font-medium text-muted`}>
              <span>순위</span>
              <span>선수</span>
              <span>리그 평균 대비</span>
              <span className="text-right">{axis.copy.metric}</span>
              {data.rows[0]?.stats.map((s) => <span key={s.label} className="text-right">{s.label}</span>)}
              <span className="text-right">대표 장면</span>
            </div>
            {teamF && rows.length === 0 && (
              <p className="px-6 py-10 text-center text-sm text-fg-2">{teamF} 선수 중 {josa(GROUP_RULE[role], "이", "가")} 없어요</p>
            )}
            <ol>
              {rows.map((r, i) => (
                <Fragment key={r.player_id}>
                  <Row row={r} copy={axis.copy} n={data.groupSize} avg={data.leagueAvg} maxGap={maxGap} playing={playing === r.player_id}
                       onPlay={() => setPlaying(playing === r.player_id ? null : r.player_id)} />
                  {/* 상위 20% 마지막 줄 아래 경계 (막대 농도와 같은 기준) */}
                  {isTop20(r.percentile) && rows[i + 1] && !isTop20(rows[i + 1].percentile) && (
                    <li className="flex items-center gap-2 border-b border-line bg-surface-2 px-6 py-1.5 text-[11px] font-bold text-brand-text">
                      <span className="h-px w-4 bg-brand" aria-hidden /> 여기까지 상위 20%
                      <span className="font-medium text-muted">{data.groupSize}명 중 {r.rank}위까지</span>
                    </li>
                  )}
                  {playing === r.player_id && r.scene && (
                    <li className="border-b border-line bg-night px-6 py-6 text-white">
                      <div className="mx-auto max-w-[720px]">
                        <div className="aspect-video w-full overflow-hidden rounded-2xl">
                          <ScenePlayer bare clip={r.scene.clip} label={r.scene.title} />
                        </div>
                        <div className="mt-3 flex items-center justify-between gap-4">
                          <p>
                            <span className="text-[17px] font-bold">{r.scene.title}</span>
                            <span className="ml-2 text-[13px] text-[#a1a1a8]">{md(r.scene.date)}</span>
                          </p>
                          <button onClick={() => setPlaying(null)} className="text-[13px] font-bold text-[#d3d4d8] hover:underline">닫기</button>
                        </div>
                      </div>
                    </li>
                  )}
                </Fragment>
              ))}
            </ol>
            {!teamF && !more && data.rows.length > FIRST && (
              <button onClick={() => setMore(true)} className="w-full py-4 text-[13px] font-medium text-fg-2 hover:bg-surface-2">
                {FIRST + 1} ~ {data.rows.length}위 더 보기
              </button>
            )}
          </div>
        </div>
      )}
    </Wrap>
  );
}

function Summary({ copy, role, data, shown, team }: {
  copy: AxisCopy; role: Role; data?: { groupSize: number; leagueAvg: number | null; rows: RankRow[] }; shown: RankRow[]; team: string | null;
}) {
  const first = team ? shown[0] : data?.rows[0];
  const withScene = shown.filter((r) => r.scene).length;
  return (
    <div className="mt-6 flex flex-wrap items-center justify-between gap-6 rounded-3xl border border-line bg-surface px-7 py-6">
      <div>
        <h2 className="text-xl font-bold">
          {copy.chip} · {copy.title}
        </h2>
        <p className="mt-1.5 text-[13px] text-fg-2">
          {copy.sub}
          {data && <> · {GROUP_RULE[role]} {data.groupSize}명 비교 <Help title={role === "pitcher" ? "규정이닝" : "규정타석"} body={GROUP_HELP[role]} inline /></>}
          {team && data && ` · ${team} ${shown.length}명만 보기`}
        </p>
      </div>
      {data && (
        <dl className="flex gap-9">
          <Stat label="리그 평균" value={copy.fmt(data.leagueAvg)} />
          <Stat label={team ? `${team} 최고 (리그 ${first?.rank ?? "–"}위)` : "1위"} value={first ? copy.fmt(first.value) : "–"} />
          <Stat label={`장면 볼 수 있는 선수 (${shown.length}명 중)`} value={`${withScene}명`} />
        </dl>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 font-display text-[28px] leading-none font-extrabold">{value}</dd>
    </div>
  );
}

function Row({ row, copy, n, avg, maxGap, playing, onPlay }: {
  row: RankRow; copy: AxisCopy; n: number; avg: number | null; maxGap: number; playing: boolean; onPlay: () => void;
}) {
  const pos = leaguePosition(row.percentile, row.rank, n);
  const gap = axisGap(copy, row.value, avg);
  const w = gap == null || maxGap === 0 ? 0 : (Math.abs(gap) / maxGap) * 50; // 막대 반쪽(50%) 기준
  return (
    <li className={`grid ${COLS} items-center gap-4 border-b border-line px-6 py-3.5 last:border-b-0`}>
      <span className="font-display text-[28px] leading-none font-extrabold">{row.rank}</span>
      <Link href={playerHref(row.player_id)} className="group flex min-w-0 items-center gap-3">
        <PlayerAvatar id={row.player_id} name={row.name} team={row.team} size={44} />
        <span className="min-w-0">
          <span className="flex items-center gap-1.5 text-[15px] font-bold group-hover:underline">
            <span className="truncate">{row.name}</span> <TeamLogo team={row.team} height={14} />
          </span>
          <span className="block truncate text-xs text-muted">{row.meta}</span>
        </span>
      </Link>
      <span title={pos.label} className="flex items-center gap-3">
        <span className={`w-[68px] shrink-0 text-right font-num text-[15px] font-bold ${gap != null && gap < 0 ? "text-muted" : ""}`}>{gapText(copy, row.value, avg)}</span>
        <span className="relative block h-2 w-full max-w-[160px] rounded-full bg-surface-2">
          <span className="absolute inset-y-[-3px] left-1/2 w-px bg-line-strong" aria-hidden /> {/* 리그 평균 */}
          <span
            className={`absolute inset-y-0 ${gap != null && gap < 0 ? "right-1/2 rounded-l-full bg-line-strong" : "left-1/2 rounded-r-full bg-brand"}`}
            style={{ width: `${w}%`, opacity: gap != null && gap < 0 ? 1 : barOpacity(row.percentile) }} // 평균 위 막대: 상위 20% 진하게 · 50% 이내 중간
          />
        </span>
      </span>
      <span className="text-right font-num text-[15px] font-semibold">{copy.fmt(row.value)}</span>
      {row.stats.map((s) => (
        <span key={s.label} className="text-right font-num text-sm text-fg-2">{s.value}</span>
      ))}
      <span className="flex justify-end">
        {row.scene ? (
          <button
            onClick={onPlay}
            aria-expanded={playing}
            aria-label={`${row.scene.title} ${playing ? "닫기" : "재생"}`}
            className="flex h-8 items-center gap-1.5 rounded-full bg-accent px-3.5 text-xs font-bold text-white hover:opacity-90 aria-expanded:bg-brand"
          >
            <PlayGlyph size={7} /> {playing ? "재생 중" : `장면 ${mmss(clipLength(row.scene.clip))}`}
          </button>
        ) : (
          <span className="text-xs text-muted">장면 준비 중</span>
        )}
      </span>
    </li>
  );
}
