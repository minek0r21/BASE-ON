"use client";

import { useQuery } from "@tanstack/react-query";
import { getPlayerSeasons, qk } from "@/lib/api";
import { innings, rate3 } from "@/lib/format";
import StageTag from "@/components/StageTag";

// BO-PB-03 시즌 기록 (API-19). 타자 표 + 투수 표(투구 기록이 있으면) + 프로필. 숫자 머리에는 쉬운 설명(title)
type Col<T> = { key: string; label: string; help?: string; value: (r: T) => string; strong?: boolean };
type Bat = Record<string, unknown> & { season: number; teams: string[]; games: number };
type Pit = Record<string, unknown> & { season: number; teams: string[]; role_label: string };

const n = (v: unknown) => (v == null ? "–" : String(v));
const r3 = (v: unknown) => rate3(typeof v === "number" ? v : null);

const BAT: Col<Bat>[] = [
  { key: "games", label: "경기", value: (r) => n(r.games) },
  { key: "pa", label: "타석", value: (r) => n(r.pa) },
  { key: "ab", label: "타수", help: "타석에서 볼넷·사구·희생타를 뺀 수", value: (r) => n(r.ab) },
  { key: "h", label: "안타", value: (r) => n(r.h) },
  { key: "b2", label: "2루타", value: (r) => n(r.b2) },
  { key: "b3", label: "3루타", value: (r) => n(r.b3) },
  { key: "hr", label: "홈런", value: (r) => n(r.hr) },
  { key: "bb", label: "볼넷", value: (r) => n(r.bb) },
  { key: "hbp", label: "사구", help: "몸에 맞는 공", value: (r) => n(r.hbp) },
  { key: "so", label: "삼진", value: (r) => n(r.so) },
  { key: "avg", label: "타율", value: (r) => r3(r.avg) },
  { key: "obp", label: "출루율", help: "타석에서 살아 나간 비율", value: (r) => r3(r.obp) },
  { key: "slg", label: "장타율", help: "타수당 루타 수 — 장타를 많이 칠수록 높다", value: (r) => r3(r.slg) },
  { key: "ops", label: "OPS", help: "출루율 + 장타율, 타격 종합 점수", value: (r) => r3(r.ops), strong: true },
];

const PIT: Col<Pit>[] = [
  { key: "role", label: "역할", value: (r) => r.role_label },
  { key: "g", label: "등판", value: (r) => n(r.g) },
  { key: "gs", label: "선발", value: (r) => n(r.gs) },
  { key: "outs", label: "이닝", help: "아웃 3개 = 1이닝", value: (r) => innings(typeof r.outs === "number" ? r.outs : null), strong: true },
  { key: "tbf", label: "상대 타자", value: (r) => n(r.tbf) },
  { key: "h", label: "피안타", value: (r) => n(r.h) },
  { key: "hr", label: "피홈런", value: (r) => n(r.hr) },
  { key: "bb", label: "볼넷", value: (r) => n(r.bb) },
  { key: "hbp", label: "사구", value: (r) => n(r.hbp) },
  { key: "so", label: "탈삼진", value: (r) => n(r.so) },
  { key: "r", label: "실점", value: (r) => n(r.r) },
  { key: "avg", label: "피안타율", help: "맞은 안타 비율 · 낮을수록 좋아요", value: (r) => r3(r.avg) },
  { key: "whip", label: "WHIP", help: "1이닝에 내보낸 주자(안타 + 볼넷) · 낮을수록 좋아요", value: (r) => (typeof r.whip === "number" ? r.whip.toFixed(2) : "–") },
];

// 포스트시즌 줄 (PS3): 그 시즌 줄 바로 아래 「포스트시즌」. 팀 · 역할 칸이 없고 백분위도 없다
type Post = Record<string, unknown> & { season: number };

function Table<T extends { season: number; teams: string[] }>({ title, rows, cols, post = [] }: {
  title: string; rows: T[]; cols: Col<T>[]; post?: Post[];
}) {
  const postOf = new Map(post.map((p) => [p.season, p]));
  return (
    <section className="rounded-xl border border-line bg-surface p-5">
      <h2 className="mb-3 font-bold">{title}</h2>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm tabular-nums">
          <thead className="text-xs text-muted">
            <tr className="border-b border-line">
              <th className="py-2 pr-3 text-left font-semibold">시즌</th>
              <th className="py-2 pr-3 text-left font-semibold">팀</th>
              {cols.map((c) => (
                <th key={c.key} title={c.help} className={`py-2 pl-2 text-right font-semibold ${c.help ? "cursor-help underline decoration-dotted" : ""}`}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...rows].sort((a, b) => b.season - a.season).flatMap((r) => {
              const p = postOf.get(r.season);
              return [
                <tr key={`${r.season}-${cols[0].value(r)}`} className="border-b border-line last:border-0">
                  <td className="py-2 pr-3 font-bold">{r.season}</td>
                  <td className="py-2 pr-3">{r.teams.join(" · ")}</td>
                  {cols.map((c) => (
                    <td key={c.key} className={`py-2 pl-2 text-right ${c.strong ? "font-bold" : ""}`}>{c.value(r)}</td>
                  ))}
                </tr>,
                p && (
                  <tr key={`${r.season}-post`} className="border-b border-line bg-bg last:border-0">
                    <td className="py-2 pr-3 text-muted">└</td>
                    <td className="py-2 pr-3"><StageTag label={`${r.season} 포스트시즌`} /></td>
                    {cols.map((c) => (
                      <td key={c.key} className={`py-2 pl-2 text-right ${c.strong ? "font-bold" : ""}`}>
                        {c.key === "role" ? "–" : c.value(p as unknown as T)}
                      </td>
                    ))}
                  </tr>
                ),
              ];
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function SeasonsTab({ playerId, profile }: {
  playerId: string;
  profile: { backNumber: string | null; position: string | null; batsThrows: string | null; birthDate: string | null };
}) {
  const q = useQuery({ queryKey: qk.seasons(playerId), queryFn: ({ signal }) => getPlayerSeasons(playerId, signal) });
  if (q.isPending) return <p className="text-muted">불러오는 중…</p>;
  if (q.isError) return <p className="text-muted">시즌 기록을 불러오지 못했습니다.</p>;
  const { batting, pitching, postBatting, postPitching } = q.data;

  return (
    <div className="space-y-5">
      {batting.length > 0 && <Table title="타격" rows={batting as Bat[]} cols={BAT} post={postBatting} />}
      {pitching.length > 0 && <Table title="투구" rows={pitching as Pit[]} cols={PIT} post={postPitching} />}
      {batting.length === 0 && pitching.length === 0 && (
        <p className="rounded-xl border border-line bg-surface p-6 text-center text-muted">시즌 기록이 없습니다.</p>
      )}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[["등번호", profile.backNumber], ["포지션", profile.position], ["투타", profile.batsThrows], ["생년월일", profile.birthDate]].map(([k, v]) => (
          <div key={k} className="rounded-xl border border-line bg-surface px-4 py-3">
            <p className="text-xs text-muted">{k}</p>
            <p className="font-bold">{v ?? "정보 없음"}</p>
          </div>
        ))}
      </section>
      <p className="text-xs text-muted">선수 프로필 출처: 위키백과(CC BY-SA 4.0) · Wikidata · KBO 공식 페이지. 값이 없으면 「정보 없음」으로 보여 줘요.</p>
    </div>
  );
}
