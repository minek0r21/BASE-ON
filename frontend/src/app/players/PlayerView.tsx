"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Wrap } from "@/components/home/common";
import Abilities from "@/components/player/Abilities";
import CompareTab from "@/components/player/CompareTab";
import GamesTab from "@/components/player/GamesTab";
import Hero, { teamCrumb, type Role } from "@/components/player/Hero";
import MatchupTab from "@/components/player/MatchupTab";
import OutingsTab from "@/components/player/OutingsTab";
import { BatterScenes, PitcherOutings } from "@/components/player/SceneList";
import SeasonsTab from "@/components/player/SeasonsTab";
import { FormCard, SeasonStrip, SeasonsCard } from "@/components/player/SideCards";
import Similar from "@/components/player/Similar";
import {
  ApiError, getMeta, getPitcherOutings, getPlayer, getPlayerScenes, getPlayerSeasons, qk, type PitcherOutings as Outings, type PlayerScenes,
} from "@/lib/api";
import { pushRecentPlayer } from "@/lib/local";
import { team as teamOf } from "@/lib/teams";

const TABS = ["overview", "scenes", "games", "seasons", "matchup"] as const;
type Tab = (typeof TABS)[number] | "compare";

/**
 * 03 타자 · 03b 투수 (Figma 138:519 · 139:1125) — 구단 색 4px 띠 · 머리(+ 대표 장면 플레이어) · 시즌 기록 띠 · 리그 안 위치 5칸 · 탭(개요 · 장면/등판 · 경기 기록 · 시즌 기록 · 맞대결).
 * 06 팀 화면과 같은 틀 (10-31 사용자 A안). 구단 색은 데이터에만 — --team(띠 · 막대 · 선) · --team-text(강한 숫자) · --team-soft(연한 바탕).
 * 개요 = 장면(투수는 등판) 4열 카드 → 요즘 타격감 · 시즌별 기록 반반 → 비슷한 선수.
 * 비교(07)는 머리 「비교하기」로 들어간다(?tab=compare). 장면은 누른 자리에서 바로 재생 (별도 창 없음).
 */
export default function PlayerView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const id = params.get("id") ?? "";
  const seasonParam = Number(params.get("season")) || null;
  const monthParam = Number(params.get("month")) || null;
  const tabParam = params.get("tab");
  const tab: Tab = tabParam === "compare" ? "compare" : (TABS.find((t) => t === tabParam) ?? "overview");

  const setParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value == null) next.delete(key);
      else next.set(key, value);
    }
    router.replace(`${pathname}?${next}`, { scroll: false });
  };

  const meta = useQuery({ queryKey: qk.meta(), queryFn: ({ signal }) => getMeta(signal) });
  const player = useQuery({ queryKey: qk.player(id, seasonParam), queryFn: ({ signal }) => getPlayer(id, seasonParam, signal), enabled: id !== "" });
  const seasons = useQuery({ queryKey: qk.seasons(id), queryFn: ({ signal }) => getPlayerSeasons(id, signal), enabled: id !== "" });
  const [kind, setKind] = useState<string>("all");

  // 메인 「최근 본 선수」 (이 브라우저에만 저장)
  const loaded = player.data;
  useEffect(() => {
    if (loaded) pushRecentPlayer({ id, name: loaded.name, team: loaded.team ?? null });
  }, [id, loaded]);
  // 다른 선수 · 시즌으로 가면 거르기를 처음으로 (머리 플레이어는 key로 새로 그린다)
  const [shownFor, setShownFor] = useState(`${id}-${seasonParam}`);
  if (shownFor !== `${id}-${seasonParam}`) {
    setShownFor(`${id}-${seasonParam}`);
    setKind("all");
  }

  const p = player.data;
  // 그 시즌 기본 화면: 주소의 view가 우선, 없으면 primary_role (투수.md P7)
  const viewParam = params.get("view");
  const role: Role = viewParam === "pitcher" || viewParam === "batter" ? viewParam : p?.primaryRole === "pitcher" ? "pitcher" : "batter";
  const season = p?.season ?? null;
  const has = !!p && (role === "pitcher" ? !!p.pitching : p.isBatter);

  // 탭 이름의 숫자 (「장면 30」 · 「등판 20」) — 개요 목록과 같은 캐시
  const counts = useQuery<PlayerScenes | Outings>({
    queryKey: qk.playerScenes(id, season, role),
    queryFn: ({ signal }) => (role === "pitcher" ? getPitcherOutings(id, season!, signal) : getPlayerScenes(id, season!, signal)),
    enabled: has && season != null,
  });
  const sceneCount = counts.data ? ("outings" in counts.data ? counts.data.counts.outings : counts.data.counts.scenes) : null;

  if (!id) return <Notice>선수를 검색해 주세요.</Notice>;
  if (player.isError) {
    const e = player.error;
    return (
      <Notice>
        {e instanceof ApiError && e.status === 404 ? e.message : "선수 정보를 불러오지 못했어요."}{" "}
        <Link href="/" className="font-bold underline">처음으로</Link>
      </Notice>
    );
  }
  if (!p) return <Wrap className="pt-10 pb-24"><div className="h-[620px] animate-pulse rounded-3xl bg-surface-2" /></Wrap>;

  const t = teamOf(p.team);
  const colors = {
    "--team": t?.band ?? "var(--brand)", "--team-text": t?.text ?? "var(--brand-text)", "--team-soft": t?.soft ?? "var(--brand-soft)",
  } as CSSProperties;
  const asOf = meta.data?.data_as_of ?? null;
  const seasonList = seasons.data?.all ?? (p.season ? [p.season] : []);
  const goTab = (x: Tab) => setParams({ tab: x === "overview" ? null : x });

  const list = season != null && has && (role === "pitcher"
    ? <PitcherOutings id={id} name={p.name} season={season} all={tab === "scenes"} kind={kind as "all"} onKind={setKind} />
    : <BatterScenes id={id} name={p.name} season={season} all={tab === "scenes"} kind={kind as "all"} onKind={setKind} />);

  let body: ReactNode;
  if (!has) body = <Notice inline>{p.season} 시즌 {role === "pitcher" ? "투구" : "타자"} 기록이 없어요.</Notice>;
  else if (tab === "overview") body = (
    <>
      {list}
      <div className="mt-14 grid gap-5 lg:grid-cols-2">
        {season != null && <FormCard id={id} season={season} role={role} />}
        <SeasonsCard role={role} seasons={seasons.data} current={season} />
      </div>
      {season != null && <Similar id={id} season={season} role={role} asOf={asOf} />}
    </>
  );
  else if (tab === "scenes") body = list;
  else if (tab === "games") body = role === "pitcher" ? (
    <OutingsTab playerId={p.playerId} playerName={p.name} season={seasonParam} month={monthParam}
                onChange={(s, m) => setParams({ season: s == null ? null : String(s), month: m == null ? null : String(m) })} />
  ) : (
    <GamesTab playerId={p.playerId} playerName={p.name} season={seasonParam} month={monthParam}
              onChange={(s, m) => setParams({ season: s == null ? null : String(s), month: m == null ? null : String(m) })} />
  );
  else if (tab === "seasons") body = (
    <SeasonsTab playerId={p.playerId} onScenes={(s, r) => setParams({ season: String(s), month: null, tab: "scenes", view: p.isBatter && p.pitching ? r : null })} />
  );
  else if (tab === "matchup") body = <MatchupTab key={role} playerId={p.playerId} playerName={p.name} season={p.season} role={role} />; // 투수 화면은 상대한 타자
  else body = (
    <CompareTab playerId={p.playerId} season={p.season} withIds={(params.get("with") ?? "").split(",").filter(Boolean)}
                onChange={(ids) => setParams({ with: ids.length ? ids.join(",") : null })} />
  );

  const tabs: { key: Tab; label: string; n?: number | null }[] = [
    { key: "overview", label: "개요" },
    { key: "scenes", label: role === "pitcher" ? "등판" : "장면", n: sceneCount },
    { key: "games", label: "경기 기록" },
    { key: "seasons", label: "시즌 기록" },
    { key: "matchup", label: "맞대결" },
    ...(tab === "compare" ? [{ key: "compare" as const, label: "비교" }] : []),
  ];

  return (
    <div style={colors}>
      <div className="h-1 bg-(--team)" aria-hidden />
      <Wrap className="pt-6 pb-8">
        <nav className="flex items-center gap-1.5 text-[13px] text-muted" aria-label="위치">
          <Link href="/rankings/" className="hover:underline">선수</Link> {t && <><span aria-hidden>›</span> {teamCrumb(p.team)}</>}
        </nav>
        <div className="mt-5">
          <Hero key={`${id}-${season}-${role}`} p={p} role={role} asOf={asOf} onCompare={() => goTab("compare")} />
        </div>
        {has && <div className="mt-8"><SeasonStrip p={p} role={role} seasons={seasons.data} asOf={asOf} /></div>}
        {has && <div className="mt-14"><Abilities p={p} role={role} asOf={asOf} /></div>}
      </Wrap>

      <div className="sticky top-16 z-10 border-b border-line bg-bg/95 backdrop-blur">
        <Wrap className="flex flex-wrap items-center justify-between gap-3">
          <nav className="flex gap-7 overflow-x-auto" aria-label="선수 화면">
            {tabs.map((x) => (
              <button
                key={x.key}
                onClick={() => goTab(x.key)}
                aria-current={tab === x.key ? "page" : undefined}
                className="flex h-12 shrink-0 items-center gap-1.5 border-b-2 border-transparent text-[15px] font-medium text-fg-2 hover:text-fg aria-[current=page]:border-fg aria-[current=page]:font-bold aria-[current=page]:text-fg"
              >
                {x.label}
                {x.n != null && <span className="rounded-full bg-surface-2 px-2 py-0.5 font-num text-[11px] font-bold text-fg">{x.n}</span>}
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            {p.isBatter && p.pitching && (
              <div className="flex rounded-full border border-line bg-surface p-0.5" role="group" aria-label="타자 · 투수">
                {(["batter", "pitcher"] as const).map((v) => (
                  <button key={v} onClick={() => setParams({ view: v })} aria-pressed={role === v}
                          className="h-7 rounded-full px-3 text-[13px] font-medium text-fg-2 aria-pressed:bg-surface-3 aria-pressed:font-bold aria-pressed:text-fg">
                    {v === "batter" ? "타자" : "투수"}
                  </button>
                ))}
              </div>
            )}
            {seasonList.length > 0 && (
              <label>
                <span className="sr-only">시즌</span>
                <select value={p.season ?? ""} onChange={(e) => setParams({ season: e.target.value, month: null })}
                        className="h-[34px] rounded-xl border border-line bg-surface px-3 text-[13px] font-medium">
                  {seasonList.map((s) => <option key={s} value={s}>{s} 시즌</option>)}
                </select>
              </label>
            )}
          </div>
        </Wrap>
      </div>

      <Wrap className="pt-10 pb-24">{body}</Wrap>
    </div>
  );
}

function Notice({ children, inline }: { children: ReactNode; inline?: boolean }) {
  const box = <p className="rounded-3xl border border-line bg-surface p-10 text-center text-sm text-fg-2">{children}</p>;
  return inline ? box : <Wrap className="pt-10 pb-24">{box}</Wrap>;
}
