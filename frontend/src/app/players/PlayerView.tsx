"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ApiError, getPlayer, getPlayerSeasons, qk } from "@/lib/api";
import { teamColor } from "@/lib/constants";
import Summary from "@/components/player/Summary";
import GamesTab from "@/components/player/GamesTab";
import PitcherSummary from "@/components/player/PitcherSummary";
import OutingsTab from "@/components/player/OutingsTab";
import CompareTab from "@/components/player/CompareTab";
import SeasonsTab from "@/components/player/SeasonsTab";
import MatchupTab from "@/components/player/MatchupTab";

// BO-PB-01~05 탭 (설계 9장). 요약 말고는 다음 단계
const TABS = [
  { key: "summary", label: "요약" },
  { key: "games", label: "경기 기록" },
  { key: "seasons", label: "시즌 기록" },
  { key: "compare", label: "비교" },
  { key: "matchup", label: "맞대결" },
] as const;
type Tab = (typeof TABS)[number]["key"];

export default function PlayerView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const id = params.get("id") ?? "";
  const seasonParam = Number(params.get("season")) || null;
  const tab = (TABS.find((t) => t.key === params.get("tab"))?.key ?? "summary") as Tab;

  const monthParam = Number(params.get("month")) || null;

  const setParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value == null) next.delete(key);
      else next.set(key, value);
    }
    router.replace(`${pathname}?${next}`, { scroll: false });
  };
  const setParam = (key: string, value: string | null) => setParams({ [key]: value });

  const player = useQuery({
    queryKey: qk.player(id, seasonParam),
    queryFn: ({ signal }) => getPlayer(id, seasonParam, signal),
    enabled: id !== "",
  });
  const seasons = useQuery({
    queryKey: qk.seasons(id),
    queryFn: ({ signal }) => getPlayerSeasons(id, signal),
    enabled: id !== "",
  });

  if (!id) return <Notice>선수를 검색해 주세요.</Notice>;
  if (player.isPending) return <p className="text-muted">불러오는 중…</p>;
  if (player.isError) {
    const e = player.error;
    return (
      <Notice>
        {e instanceof ApiError && e.status === 404 ? e.message : "선수 정보를 불러오지 못했습니다."}{" "}
        <Link href="/" className="underline">
          처음으로
        </Link>
      </Notice>
    );
  }

  const p = player.data;
  // 그 시즌 요약 화면: 주소의 view가 우선, 없으면 primary_role (투수.md P7)
  const viewParam = params.get("view");
  const view: "batter" | "pitcher" =
    viewParam === "pitcher" || viewParam === "batter" ? viewParam : p.primaryRole === "pitcher" ? "pitcher" : "batter";
  const seasonList = seasons.data?.all ?? (p.season ? [p.season] : []);

  return (
    <div className="space-y-5">
      {/* 프로필 */}
      <section className="flex flex-wrap items-center gap-4 rounded-xl border border-line bg-surface p-5">
        <span className="h-14 w-1.5 rounded-full" style={{ background: teamColor(p.team) }} />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-extrabold">
            {p.name}
            {p.backNumber != null && <span className="ml-2 text-base font-semibold text-muted">#{p.backNumber}</span>}
          </h1>
          <p className="text-sm text-muted">
            {[p.team, p.position, p.batsThrows, p.birthDate && `${p.birthDate} 생`].filter(Boolean).join(" · ")}
          </p>
        </div>
        {seasonList.length > 0 && (
          <label className="text-sm">
            <span className="sr-only">시즌</span>
            <select
              value={p.season ?? ""}
              onChange={(e) => setParam("season", e.target.value)}
              className="rounded-lg border border-line bg-surface px-2 py-1.5"
            >
              {seasonList.map((s) => (
                <option key={s} value={s}>
                  {s} 시즌
                </option>
              ))}
            </select>
          </label>
        )}
      </section>

      {/* 탭 */}
      <nav className="flex gap-1 overflow-x-auto border-b border-line" aria-label="선수 화면">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setParam("tab", t.key === "summary" ? null : t.key)}
            aria-current={tab === t.key ? "page" : undefined}
            className={`shrink-0 border-b-2 px-3 py-2 text-sm font-semibold ${
              tab === t.key ? "border-fg" : "border-transparent text-muted hover:text-fg"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {(tab === "summary" || tab === "games") && p.isBatter && p.pitching && (
        <div className="flex gap-1" role="group" aria-label="타자 · 투수">
          {(["batter", "pitcher"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setParam("view", v)}
              aria-pressed={view === v}
              className={`rounded-full border px-3 py-1 text-sm ${
                view === v ? "border-fg bg-fg text-bg" : "border-line bg-surface text-muted hover:text-fg"
              }`}
            >
              {v === "batter" ? "타자" : "투수"}
            </button>
          ))}
        </div>
      )}

      {tab === "summary" ? (
        view === "pitcher" && p.pitching ? (
          <PitcherSummary p={p.pitching} season={p.season} name={p.name} />
        ) : (
          <Summary p={p} />
        )
      ) : tab === "games" && view === "pitcher" ? (
        <OutingsTab
          playerId={p.playerId}
          playerName={p.name}
          season={seasonParam}
          month={monthParam}
          onChange={(s, m) => setParams({ season: s == null ? null : String(s), month: m == null ? null : String(m) })}
        />
      ) : tab === "compare" ? (
        <CompareTab
          playerId={p.playerId}
          season={p.season}
          withIds={(params.get("with") ?? "").split(",").filter(Boolean)}
          onChange={(ids) => setParam("with", ids.length ? ids.join(",") : null)}
        />
      ) : tab === "games" ? (
        <GamesTab
          playerId={p.playerId}
          playerName={p.name}
          season={seasonParam}
          month={monthParam}
          onChange={(s, m) => setParams({ season: s == null ? null : String(s), month: m == null ? null : String(m) })}
        />
      ) : tab === "seasons" ? (
        <SeasonsTab
          playerId={p.playerId}
          profile={{ backNumber: p.backNumber, position: p.position, batsThrows: p.batsThrows, birthDate: p.birthDate }}
        />
      ) : tab === "matchup" && p.isBatter ? (
        <MatchupTab playerId={p.playerId} playerName={p.name} season={p.season} />
      ) : tab === "matchup" ? (
        <Notice>맞대결은 타자 기준으로 보여 줘요. 이 시즌 타자 기록이 없습니다.</Notice>
      ) : (
        <Notice>준비 중입니다.</Notice>
      )}
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">{children}</p>;
}
