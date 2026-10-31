"use client";

import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Playing } from "@/components/home/DayScenes";
import { SectionHead } from "@/components/home/common";
import InlinePlayer from "@/components/InlinePlayer";
import StageTag from "@/components/StageTag";
import { Chip, Empty } from "@/components/ui/Chip";
import Help from "@/components/ui/Help";
import { PlayGlyph, PlayerAvatar, TeamLogo } from "@/components/ui/Media";
import { getMatchup, getMatchups, getPaClip, qk, type VsPitcher } from "@/lib/api";
import { md, rate3 } from "@/lib/format";
import { ForecastPicker, NextTime } from "./Forecast";

// BO-PB-05 맞대결 (API-17 상대한 투수 → API-06 타석 목록). 10타석 미만은 성적보다 타석별 결과로 보여 준다 (시안 v9)
// 06 팀 화면 표와 같은 틀 — 섹션 제목 + 기간 칩 · 이름 찾기, 요약 카드 3장(타율 가장 높은 · 낮은 · 홈런 많이 친 투수), 팀 칩, 칸 머리 정렬.
// 줄을 누르면 그 줄 아래에 「다음에 붙으면」 예상 + 타석 목록 · 재생. 표 위 「이 투수와 붙으면」은 리그 투수 누구나 (API-37). 타율 .300 이상은 구단 글자색 (10-31 사용자)
const MIN_PA = 10;
const FIRST = 12;
type SortKey = "pa" | "ab" | "h" | "hr" | "bb" | "so" | "avg";
const COLS: [SortKey, string][] = [["pa", "타석"], ["ab", "타수"], ["h", "안타"], ["hr", "홈런"], ["bb", "볼넷"], ["so", "삼진"], ["avg", "타율"]];
const avgOf = (p: VsPitcher) => (p.pa >= MIN_PA ? p.avg : null); // 10타석 미만은 타율을 매기지 않는다

export default function MatchupTab({ playerId, playerName, season }: { playerId: string; playerName: string; season: number | null }) {
  const [scope, setScope] = useState<"all" | "season">("all");
  const [picked, setPicked] = useState<VsPitcher | null>(null);
  const [filter, setFilter] = useState("");
  const [team, setTeam] = useState<string | null>(null);
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "pa", desc: true });
  const [more, setMore] = useState(false);
  const s = scope === "season" ? season : null;

  const list = useQuery({ queryKey: qk.matchups(playerId, s, 1), queryFn: ({ signal }) => getMatchups(playerId, s, 1, signal) });

  if (list.isPending) return <div className="h-[560px] animate-pulse rounded-3xl bg-surface-2" />;
  if (list.isError) return <Empty text="맞대결 기록을 불러오지 못했어요" action={{ label: "다시 시도", onClick: () => list.refetch() }} />;

  const all = list.data.pitchers;
  const many = all.filter((p) => p.pa >= MIN_PA);
  const few = all.filter((p) => p.pa < MIN_PA);
  const f = filter.trim();
  const base = f ? all.filter((p) => p.name.includes(f)) : many;
  const teams = [...new Set(base.map((p) => p.team).filter((t): t is string => !!t))].sort((a, b) => a.localeCompare(b, "ko"));
  const val = (p: VsPitcher) => (sort.key === "avg" ? avgOf(p) : p[sort.key]);
  const cmp = (a: VsPitcher, b: VsPitcher) => {
    const x = val(a), y = val(b);
    if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1; // 타율 없는 줄은 늘 아래
    return (sort.desc ? y - x : x - y) || b.pa - a.pa;
  };
  const rows = base.filter((p) => !team || p.team === team).sort(cmp);
  const shown = f || more ? rows : rows.slice(0, FIRST);
  const scopeLabel = scope === "all" ? "2024~2026 정규시즌 누적" : `${season ?? ""} 정규시즌`;
  const sortLabel = COLS.find(([k]) => k === sort.key)![1];

  const reset = () => { setPicked(null); setMore(false); setTeam(null); };
  const open = (p: VsPitcher) => {
    setFilter(""); setTeam(null); setPicked(p);
    setMore(more || [...many].sort(cmp).findIndex((x) => x.player_id === p.player_id) >= FIRST); // 접힌 쪽에 있으면 펼친다
    requestAnimationFrame(() => document.getElementById(`vs-${p.player_id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
  };
  const sortBy = (k: SortKey) => setSort(sort.key === k ? { key: k, desc: !sort.desc } : { key: k, desc: k !== "so" });

  return (
    <section>
      <SectionHead
        title="상대한 투수"
        sub={`${scopeLabel} · ${MIN_PA}타석 이상 맞붙은 투수 ${many.length}명`}
        right={
          <div className="flex flex-wrap items-center gap-2">
            {([["all", "2024~2026 누적"], ["season", `${season ?? ""} 시즌`]] as const).map(([k, l]) => (
              <Chip key={k} on={scope === k} onClick={() => { setScope(k); reset(); }}>{l}</Chip>
            ))}
            <input value={filter} onChange={(e) => { setFilter(e.target.value); setTeam(null); }} placeholder={`그 밖 ${few.length}명 이름으로 찾기`} aria-label="상대 투수 이름"
                   className="h-9 w-52 rounded-full border border-line bg-surface px-4 text-[13px]" />
          </div>
        }
      />
      <Highlights rows={many} onOpen={open} />
      {season != null && (
        <ForecastPicker key={playerId} batter={playerId} season={season}
                        initial={all[0] ? { id: all[0].player_id, name: all[0].name, team: all[0].team } : null} />
      )}
      <div className="mb-4 flex flex-wrap items-center gap-2" role="group" aria-label="상대 팀">
        <Chip on={team == null} onClick={() => setTeam(null)}>전체 <span className="font-num opacity-70">{base.length}</span></Chip>
        {teams.map((t) => (
          <Chip key={t} on={team === t} onClick={() => { setTeam(team === t ? null : t); setMore(false); }}>
            <TeamLogo team={t} height={14} /> {t} <span className="font-num opacity-70">{base.filter((p) => p.team === t).length}</span>
          </Chip>
        ))}
        <span className="ml-auto text-xs text-fg-2">{sortLabel} {sort.key === "avg" ? (sort.desc ? "높은" : "낮은") : sort.desc ? "많은" : "적은"} 순</span>
      </div>
      <div className="overflow-hidden rounded-3xl border border-line bg-surface px-6 pt-2 pb-3">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="text-xs text-fg-2">
              <tr className="border-b border-line">
                <th className="py-3 text-left font-semibold">투수</th>
                <th className="py-3 text-left font-semibold">팀</th>
                {COLS.map(([k, h]) => (
                  <th key={k} className="py-3 pl-2 text-right font-semibold" aria-sort={sort.key === k ? (sort.desc ? "descending" : "ascending") : undefined}>
                    <button onClick={() => sortBy(k)} className={`hover:text-fg ${sort.key === k ? "font-bold text-fg" : ""}`}>
                      {h}{sort.key === k && (sort.desc ? " ↓" : " ↑")}
                    </button>
                    {k === "ab" && <> <Help title="타수" body="타석에서 볼넷 · 몸에 맞는 공 · 희생타를 뺀 수예요. 타율은 안타 ÷ 타수로 계산해요." inline below /></>}
                  </th>
                ))}
                <th className="w-10" aria-hidden />
              </tr>
            </thead>
            <tbody>
              {shown.map((p) => {
                const on = picked?.player_id === p.player_id;
                const avg = avgOf(p);
                return (
                  <Fragment key={p.player_id}>
                    <tr id={`vs-${p.player_id}`} onClick={() => setPicked(on ? null : p)} aria-expanded={on}
                        className={`scroll-mt-32 cursor-pointer border-b border-line hover:bg-surface-2 ${on ? "bg-surface-2" : ""}`}>
                      <td className="py-2.5">
                        <span className="flex items-center gap-2.5">
                          <PlayerAvatar id={p.player_id} name={p.name} team={p.team} size={32} />
                          <span className="font-bold">{p.name}</span>
                        </span>
                      </td>
                      <td className="py-2.5">
                        <span className="flex items-center gap-1.5 text-fg-2"><TeamLogo team={p.team} height={14} /> {p.team ?? "–"}</span>
                      </td>
                      {COLS.map(([k]) => (
                        <td key={k} className={`py-2.5 pl-2 text-right font-num ${
                          k === "avg" && avg != null && avg >= 0.3 ? "font-bold text-(--team-text)" : k === sort.key ? "font-bold" : ""}`}>
                          {k === "avg" ? (avg == null ? "–" : rate3(avg)) : p[k]}
                        </td>
                      ))}
                      <td className="py-2.5 text-right text-xs text-fg-2">{on ? "▴" : "▾"}</td>
                    </tr>
                    {on && (
                      <tr className="border-b border-line">
                        <td colSpan={COLS.length + 3} className="py-3">
                          <Detail playerId={playerId} playerName={playerName} p={p} season={s} forecastSeason={season} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {shown.length === 0 && (
                <tr><td colSpan={COLS.length + 3} className="py-10 text-center text-fg-2">{f ? "그 이름의 상대 투수가 없어요" : `${MIN_PA}타석 이상 상대한 투수가 없어요`}</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {!f && rows.length > FIRST && (
          <button onClick={() => setMore(!more)} className="mt-3 h-11 w-full rounded-2xl bg-surface-2 text-sm font-bold hover:bg-surface-3">
            {more ? "접기" : `${rows.length - FIRST}명 더 보기 ›`}
          </button>
        )}
      </div>
    </section>
  );
}

/** 요약 3장 — 10타석 이상 상대 중 타율 최고 · 최저, 홈런 최다(같으면 타석 많은 쪽). 누르면 표의 그 줄을 펼친다 */
function Highlights({ rows, onOpen }: { rows: VsPitcher[]; onOpen: (p: VsPitcher) => void }) {
  const rated = rows.filter((p) => p.avg != null);
  if (rated.length < 2) return null;
  const byAvg = [...rated].sort((a, b) => b.avg! - a.avg! || b.pa - a.pa);
  const hr = [...rows].sort((a, b) => b.hr - a.hr || b.pa - a.pa)[0];
  const cards = [
    { label: "타율이 가장 높은 투수", p: byAvg[0], big: rate3(byAvg[0].avg), strong: true },
    { label: "타율이 가장 낮은 투수", p: byAvg.at(-1)!, big: rate3(byAvg.at(-1)!.avg), strong: false },
    ...(hr.hr > 0 ? [{ label: "홈런을 가장 많이 친 투수", p: hr, big: `${hr.hr}홈런`, strong: true }] : []),
  ];
  return (
    <ul className="mb-8 grid gap-4 md:grid-cols-3">
      {cards.map((c) => (
        <li key={c.label}>
          <button onClick={() => onOpen(c.p)} className="group flex w-full items-center gap-4 rounded-3xl border border-line bg-surface p-5 text-left hover:bg-surface-2">
            <PlayerAvatar id={c.p.player_id} name={c.p.name} team={c.p.team} size={56} />
            <span className="min-w-0 flex-1">
              <span className="block text-xs font-bold text-fg-2">{c.label}</span>
              <span className="mt-1 flex items-center gap-1.5 text-[17px] font-bold group-hover:underline">
                <span className="truncate">{c.p.name}</span> <TeamLogo team={c.p.team} height={14} />
              </span>
              <span className="mt-0.5 block truncate text-xs text-fg-2">{c.p.pa}타석 {c.p.h}안타 {c.p.hr}홈런 · 삼진 {c.p.so}</span>
            </span>
            <span className={`shrink-0 font-display text-[30px] leading-none font-extrabold ${c.strong ? "text-(--team-text)" : ""}`}>{c.big}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** 그 투수 상대 타석 — 홈런은 구단 글자색, 확정 장면이 있으면 ▶ (그 자리에서 재생) */
function Detail({ playerId, playerName, p, season, forecastSeason }: {
  playerId: string; playerName: string; p: VsPitcher; season: number | null; forecastSeason: number | null;
}) {
  const [playing, setPlaying] = useState<(Playing & { id: string }) | null>(null);
  const q = useQuery({
    queryKey: qk.matchup(playerId, p.player_id, season),
    queryFn: ({ signal }) => getMatchup(playerId, p.player_id, season, signal),
  });

  const play = async (paId: string, title: string, sub: string) => {
    if (playing?.id === paId) return setPlaying(null);
    const clip = await getPaClip(paId);
    if (clip) setPlaying({ id: paId, clip, title, sub });
  };

  return (
    <div className="space-y-3 rounded-2xl bg-surface-2 p-3">
      {forecastSeason != null && <NextTime batter={playerId} pitcher={p.player_id} season={forecastSeason} />}
      <div className="px-2">
        <p className="text-[13px] font-bold">
          {p.name} 상대 {p.pa}타석
          {p.pa < MIN_PA && <span className="ml-2 font-normal text-fg-2">아직 {MIN_PA}타석 전이라 타율은 매기지 않아요</span>}
        </p>
        {q.isPending ? (
          <p className="py-3 text-[13px] text-fg-2">불러오는 중…</p>
        ) : q.isError ? (
          <p className="py-3 text-[13px] text-fg-2">타석을 불러오지 못했어요</p>
        ) : (
          <ol className="mt-1 divide-y divide-line">
            {q.data.plate_appearances.map((pa) => {
              const when = `${pa.date.slice(0, 4)}. ${md(pa.date)}`;
              const hr = pa.events === "home_run";
              return (
                <li key={pa.pa_id} className="flex h-11 items-center gap-4 text-[13px]">
                  <span className="w-20 shrink-0 font-num text-fg-2">{when}</span>
                  <span className="w-14 shrink-0 font-num text-fg-2">{pa.inning}회{pa.inning_half}</span>
                  <StageTag label={pa.stage_label} />
                  <span className={`min-w-0 flex-1 truncate ${hr ? "font-bold text-(--team-text)" : "font-medium"}`}>{pa.events_ko}</span>
                  {pa.has_video && (
                    <button
                      onClick={() => play(pa.pa_id, `${playerName} vs ${p.name} · ${pa.events_ko}`, `${when} ${pa.inning}회${pa.inning_half}`)}
                      aria-expanded={playing?.id === pa.pa_id}
                      aria-label={`${when} ${pa.events_ko} 장면 재생`}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-white"
                    >
                      <PlayGlyph size={9} />
                    </button>
                  )}
                </li>
              );
            })}
          </ol>
        )}
        {playing && <InlinePlayer playing={playing} onClose={() => setPlaying(null)} className="mt-3" />}
      </div>
    </div>
  );
}
