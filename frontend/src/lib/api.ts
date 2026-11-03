/**
 * BASE:ON API 클라이언트 — 응답 타입·변환·호출을 이 파일 하나에 둔다.
 *
 * 구조
 *   Raw*      : 지금 FastAPI가 실제로 돌려주는 모양 (backend/app/routers/*.py)
 *   도메인 타입: 화면이 쓰는 모양. 설계 6-3(API-02 `axes` 배열·`data_as_of`)을 기준으로 잡았다
 *   to*()     : Raw → 도메인 변환. 백엔드 응답이 바뀌면 Raw 타입과 이 함수만 고친다
 *
 * 백엔드에 response_model이 생기면 Raw 타입은 openapi-typescript 생성 타입으로 바꾼다(설계 9장).
 */

import { innings, outingLine, rate3 } from "./format";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1";

// ------------------------------------------------------------------ 공통

/** 서버 오류 형식 `{"error": {"code", "message"}}` (설계 6-1) */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

async function get<T>(path: string, query: Query = {}, signal?: AbortSignal): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v != null) qs.set(k, String(v));
  const url = `${API_BASE}${path}${qs.size ? `?${qs}` : ""}`;

  const res = await fetch(url, { signal });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const err = body?.error;
    throw new ApiError(res.status, err?.code ?? "HTTP_ERROR", err?.message ?? `요청 실패 (${res.status})`);
  }
  return res.json() as Promise<T>;
}

// ------------------------------------------------------------------ API-01 검색

type RawSearch = {
  players: {
    player_id: string;
    name: string;
    team: string | null;
    position: string | null;
    bats_throws: string | null;
  }[];
};

export type PlayerHit = RawSearch["players"][number];

/** 검색어 규칙: 공백 제거 후 1~20자 (설계 6-1) */
export const normalizeQuery = (q: string) => q.replace(/\s+/g, "").slice(0, 20);

export async function searchPlayers(q: string, signal?: AbortSignal, role?: "batter" | "pitcher"): Promise<PlayerHit[]> {
  const raw = await get<RawSearch>("/players", { q: normalizeQuery(q), role }, signal);
  return raw.players;
}

// ------------------------------------------------------------------ API-02 선수 요약

type RawPctKey = "contact" | "hit" | "power" | "eye" | "consistency";

type RawStats = {
  pa: number; ab: number; h: number; hr: number;
  avg: number | null; obp: number | null; slg: number | null; ops: number | null;
  bb_pct: number | null; k_pct: number | null; iso: number | null; ops_sd: number | null;
};

type RawHr = {
  pa_id: string;
  date: string;
  opponent: string;
  pitcher: { player_id: string; name: string };
  runs: number;
  hr_seq: number;
  video: {
    video_id: string; title: string; duration_sec?: number | null; start_sec?: number | null; end_sec?: number | null;
    precision?: "scene" | "inning";
  } | null;
};

type RawPlayer = {
  player_id: string;
  name: string;
  team: string | null;
  position: string | null;
  back_number: number | string | null;
  birth_date: string | null;
  bats_throws: string | null;
  season: number | null;
  stats: RawStats | null;
  qualified: boolean;
  qualify_pa?: number | null;
  percentiles: Record<RawPctKey, number | null> | null;
  axis_ranks: Record<RawPctKey, number | null> | null;
  group_size: number | null;
  stat_ranks?: Partial<Record<"hr" | "slg" | "ops" | "obp" | "avg", number | null>> | null;
  last_hr: RawHr | null;
  last_hr_video: RawHr | null;
  recent_video: { video_id: string; title: string; date: string; opponent: string; pa_id: string } | null;
  /** 축 옆 ▶ — 안타·선구안 축의 그 시즌 가장 최근 확정 장면 (없는 축은 빠짐) */
  axis_scenes?: Partial<Record<"hit" | "eye", RawBatAxisScene>>;
  // 설계 6-3 이후 생기는 칸 (지금 응답에는 없다)
  data_as_of?: string;
  primary_role?: "batter" | "pitcher" | null;
  pitching?: RawPitching | null;
};

type RawBatAxisScene = {
  video_id: string; title: string; duration_sec: number | null; start_sec: number; end_sec: number | null;
  precision: "scene" | "inning" | "game" | null;
  pa_id: string; date: string; inning: number; inning_half: string; events: string; runs: number; opponent: string;
};

type RawPitching = {
  role: "starter" | "reliever";
  role_label: string;
  g: number; gs: number; outs: number; tbf: number;
  h: number; hr: number; bb: number; hbp: number; so: number; r: number;
  avg: number | null; whip: number | null;
  avg_velo: number | null; league_avg_velo: number | null;
  qualified: boolean;
  group_size: number | null;
  axes: {
    key: PitchAxisKey; label: string; metric: string; value: number | null;
    reverse: boolean; percentile: number | null; rank: number | null;
    scene?: RawPitchScene | null;
  }[];
  not_qualified_message: string | null;
  qualify_outs?: number | null;
  stat_ranks?: Partial<Record<"outs" | "so" | "whip" | "avg", number | null>> | null;
  recent_scene?: RawPitchScene | null;
};

type RawScene = {
  video_id: string;
  title: string;
  duration_sec: number | null;
  start_sec: number | null;
  end_sec: number | null;
  precision: "scene" | "inning" | "game";
  scene_type: string | null;
  tags: string[];
};
type RawPitchScene = RawScene & { outing_id: string; date: string; line: OutingLine };

/** 등판 한 줄 기록 (장면 표기 「7.16 · 6이닝 8K 무실점」 재료) */
export type OutingLine = { outs: number; so: number; r: number; h: number };

const sceneClip = (s: RawScene): Clip => ({
  videoId: s.video_id,
  title: s.title,
  startSec: s.start_sec ?? 0,
  endSec: s.end_sec ?? s.duration_sec,
  durationSec: s.duration_sec,
  precision: s.precision,
});

/** 등판 장면 (투수 요약의 최근 장면·축 옆 ▶) */
export type PitchScene = { clip: Clip; date: string; line: OutingLine };
const toPitchScene = (s: RawPitchScene): PitchScene => ({ clip: sceneClip(s), date: s.date, line: s.line });

export type PitchAxisKey = "strikeout" | "control" | "chase" | "hit_prevention" | "power_prevention";

export type PitchAxis = {
  key: PitchAxisKey;
  label: string;
  metric: string;
  value: number | null;
  percentile: number | null;
  topPct: number | null;
  rank: number | null;
  reverse: boolean;
  /** 이 축을 보여 주는 확정 장면 (탈삼진·안타 억제·제구만, docs/장면.md 6장) */
  scene: PitchScene | null;
};

/** 투수 요약 (docs/투수.md 6-1·8장) */
export type PitchingSummary = {
  role: "starter" | "reliever";
  roleLabel: string;
  g: number; gs: number;
  /** 잡은 아웃. 이닝 표기는 format.innings() */
  outs: number;
  tbf: number; h: number; hr: number; bb: number; hbp: number; so: number;
  avg: number | null;
  whip: number | null;
  avgVelo: number | null;
  leagueAvgVelo: number | null;
  qualified: boolean;
  groupSize: number | null;
  axes: PitchAxis[];
  notQualifiedMessage: string | null;
  /** 비교 대상이 되려면 필요한 아웃 수 (이닝 × 3). 대상이면 null */
  qualifyOuts: number | null;
  /** 시즌 기록 등수 (같은 역할 비교 대상 안). 대상 밖이면 null */
  statRanks: NonNullable<RawPitching["stat_ranks"]> | null;
  recentScene: PitchScene | null;
};

function toPitching(p: RawPitching): PitchingSummary {
  return {
    role: p.role, roleLabel: p.role_label, g: p.g, gs: p.gs, outs: p.outs, tbf: p.tbf,
    h: p.h, hr: p.hr, bb: p.bb, hbp: p.hbp, so: p.so, avg: p.avg, whip: p.whip,
    avgVelo: p.avg_velo, leagueAvgVelo: p.league_avg_velo, qualified: p.qualified, groupSize: p.group_size,
    axes: p.axes.map(({ scene, ...a }) => ({
      ...a,
      topPct: a.percentile == null ? null : 100 - a.percentile,
      scene: scene ? toPitchScene(scene) : null,
    })),
    notQualifiedMessage: p.not_qualified_message,
    qualifyOuts: p.qualify_outs ?? null,
    statRanks: p.stat_ranks ?? null,
    recentScene: p.recent_scene ? toPitchScene(p.recent_scene) : null,
  };
}

/** 경기 꼬리표 (docs/포스트시즌.md 8-1). 정규시즌이면 stage · stage_label이 null */
export type GameTag = {
  game_type: "regular" | "postseason";
  stage: "WC" | "SPO" | "PO" | "KS" | null;
  series_game_no: number | null;
  /** 「준PO 2차전」 */
  stage_label: string | null;
};

// ------------------------------------------------------------------ API-23 투수 경기 기록 (등판 목록)

type RawOutings = {
  seasons: number[];
  season: number | null;
  months: number[];
  month: number | null;
  outings: (GameTag & {
    outing_id: string;
    game_pk: string;
    date: string;
    weekday: string;
    opponent: string;
    home: boolean;
    score: { team: number; opponent: number };
    result: "W" | "L" | "D";
    role: string;
    line: OutingLine & { tbf: number; bb: number; hbp: number; hr: number; pitches: number };
    scene: RawScene | null;
    highlight: RawHighlight;
  })[];
};

export type OutingRow = Omit<RawOutings["outings"][number], "scene" | "highlight" | "outing_id"> & {
  outingId: string;
  /** 보너스층: 이 등판의 확정 장면 (클립 scene · 챕터 inning) */
  scene: Clip | null;
  /** 기본층: 이 경기 하이라이트 */
  highlight: Clip | null;
};
export type PlayerOutings = { seasons: number[]; season: number | null; months: number[]; month: number | null; outings: OutingRow[] };

// ------------------------------------------------------------------ API-30 등판 상세 (03b)

export type OutingPa = {
  pa_id: string; batter: { player_id: string; name: string };
  events: string; events_ko: string; kind: "strikeout" | "on_base" | "out";
  runs_scored: number | null; pitches: number | null;
  count: { balls: number | null; strikes: number | null }; outs: number | null;
  runners: { on_1b: boolean; on_2b: boolean; on_3b: boolean };
  last_pitch: { name: string | null; speed_kmh: number | null };
};
export type OutingInning = {
  inning: number; inning_half: string;
  summary: { batters: number; h: number; so: number; bb: number; hbp: number; runs: number };
  plate_appearances: OutingPa[];
};
export type OutingDetail = GameTag & {
  outing_id: string; game_pk: string; date: string; weekday: string;
  pitcher: { player_id: string; name: string };
  team: string; opponent: string; home: boolean;
  score: { team: number; opponent: number }; result: "W" | "L" | "D"; role: string;
  line: { outs: number; tbf: number; so: number; bb: number; hbp: number; h: number; hr: number; r: number; pitches: number };
  scene: Clip | null; highlight: Clip | null; highlightChannel: string | null;
  innings: OutingInning[];
};

export async function getOutingDetail(outingId: string, signal?: AbortSignal): Promise<OutingDetail> {
  const r = await get<Omit<OutingDetail, "scene" | "highlight" | "highlightChannel"> & { scene: RawScene | null; highlight: RawHighlight }>(
    `/outings/${encodeURIComponent(outingId)}/plate-appearances`, {}, signal);
  return { ...r, scene: r.scene ? sceneClip(r.scene) : null, highlight: r.highlight ? toClip(r.highlight) : null, highlightChannel: r.highlight?.channel ?? null };
}

export async function getPlayerOutings(id: string, season: number | null, month: number | null, signal?: AbortSignal): Promise<PlayerOutings> {
  const r = await get<RawOutings>(`/players/${encodeURIComponent(id)}/outings`, { season, month }, signal);
  return {
    seasons: r.seasons,
    season: r.season,
    months: r.months,
    month: r.month,
    outings: r.outings.map(({ outing_id, scene, highlight, ...o }) => ({
      ...o,
      outingId: outing_id,
      scene: scene ? sceneClip(scene) : null,
      highlight: highlight ? toClip(highlight) : null,
    })),
  };
}

export type AxisKey = RawPctKey;
export type StatKey = keyof RawStats;

export type Axis = {
  key: AxisKey;
  label: string;
  metric: StatKey;
  value: number | null;
  percentile: number | null;
  /** 상위 N% = 100 − 백분위 (FR-02-02) */
  topPct: number | null;
  rank: number | null;
  /** true면 원 수치가 낮을수록 좋다 (삼진율·월별 OPS 표준편차) */
  reverse: boolean;
  /** 비교 대상인데 이 축만 계산 못 했을 때 이유 */
  unavailable: string | null;
  /** 축 옆 ▶ 장면 (안타생산 = 안타, 선구안 = 볼넷). 파워는 recentScene(홈런)을 쓴다 */
  scene: { clip: Clip; label: string } | null;
};

/** 타자 홈런 장면 (최근 장면·파워 축 ▶, docs/장면.md 6장) */
export type Scene = {
  paId: string;
  clip: Clip;
  date: string;
  hrSeq: number | null;
  opponent: string;
};

export type PlayerSummary = {
  playerId: string;
  name: string;
  team: string | null;
  position: string | null;
  /** 문자열 — `0`과 `00`이 다르다 (설계 T5) */
  backNumber: string | null;
  birthDate: string | null;
  batsThrows: string | null;
  season: number | null;
  dataAsOf: string | null;
  /** 이 시즌 타자 기록이 있나 (투수만 뛴 시즌이면 false) */
  isBatter: boolean;
  stats: RawStats | null;
  qualified: boolean;
  groupSize: number | null;
  /** 시즌 기록 등수 (비교 대상 안). 대상 밖이면 null */
  statRanks: NonNullable<RawPlayer["stat_ranks"]> | null;
  axes: Axis[];
  notQualifiedMessage: string | null;
  /** 비교 대상이 되려면 필요한 타석 수 (규정타석의 50%). 대상이면 null */
  qualifyPa: number | null;
  lastHr: RawHr | null;
  recentScene: Scene | null;
  /** 그 시즌 기본 화면: 타자 요약 / 투수 요약 (투수.md P7) */
  primaryRole: "batter" | "pitcher" | null;
  pitching: PitchingSummary | null;
};

/** 고정 순서: 삼진회피 → 안타생산 → 파워 → 선구안 → 꾸준함 (설계 6-3, etl/prepare.py 지표 대응) */
export const AXIS_DEFS: { key: AxisKey; label: string; metric: StatKey; reverse: boolean }[] = [
  { key: "contact", label: "삼진회피", metric: "k_pct", reverse: true },
  { key: "hit", label: "안타생산", metric: "avg", reverse: false },
  { key: "power", label: "파워", metric: "iso", reverse: false },
  { key: "eye", label: "선구안", metric: "bb_pct", reverse: false },
  { key: "consistency", label: "꾸준함", metric: "ops_sd", reverse: true },
];

const NOT_QUALIFIED = "리그 비교 대상 아님(타석 부족)"; // 「규정타석 미달」이라고 쓰지 않는다 (설계 6-3)

const EVENT_SCENE_KO: Record<string, string> = { single: "안타", double: "2루타", triple: "3루타", walk: "볼넷" };

function toAxisScene(name: string, s: RawBatAxisScene | undefined): Axis["scene"] {
  if (!s) return null;
  const what = `${EVENT_SCENE_KO[s.events] ?? s.events}${s.runs > 0 ? ` ${s.runs}타점` : ""}`;
  return {
    label: `${name} · ${Number(s.date.slice(5, 7))}.${Number(s.date.slice(8, 10))} ${s.opponent}전 ${s.inning}회${s.inning_half} ${what}`,
    clip: {
      videoId: s.video_id, title: s.title, startSec: s.start_sec ?? 0, endSec: s.end_sec ?? s.duration_sec ?? null,
      durationSec: s.duration_sec ?? null, precision: s.precision ?? "scene",
    },
  };
}

function toPlayerSummary(r: RawPlayer): PlayerSummary {
  const axes: Axis[] = AXIS_DEFS.map((d) => {
    const percentile = r.percentiles?.[d.key] ?? null;
    return {
      ...d,
      value: r.stats?.[d.metric] ?? null,
      percentile,
      topPct: percentile == null ? null : 100 - percentile,
      rank: r.axis_ranks?.[d.key] ?? null,
      unavailable: r.qualified && percentile == null ? "월별 타석 부족" : null,
      scene: d.key === "hit" || d.key === "eye" ? toAxisScene(r.name, r.axis_scenes?.[d.key]) : null,
    };
  });

  // 최근 장면 = 그 시즌 확정 홈런 장면 중 가장 최근 (잘한 장면만, 장면.md S8)
  const v = r.last_hr_video ?? null;
  const recentScene: Scene | null = v?.video
    ? {
        paId: v.pa_id,
        date: v.date,
        hrSeq: v.hr_seq,
        opponent: v.opponent,
        clip: {
          videoId: v.video.video_id,
          title: v.video.title,
          startSec: v.video.start_sec ?? 0,
          endSec: v.video.end_sec ?? v.video.duration_sec ?? null,
          durationSec: v.video.duration_sec ?? null,
          precision: v.video.precision ?? "scene",
        },
      }
    : null;

  return {
    playerId: r.player_id,
    name: r.name,
    team: r.team,
    position: r.position,
    backNumber: r.back_number == null ? null : String(r.back_number),
    birthDate: r.birth_date,
    batsThrows: r.bats_throws,
    season: r.season,
    dataAsOf: r.data_as_of ?? null,
    isBatter: r.stats != null,
    stats: r.stats,
    qualified: r.qualified,
    groupSize: r.group_size,
    statRanks: r.stat_ranks ?? null,
    axes,
    notQualifiedMessage: r.stats != null && !r.qualified ? NOT_QUALIFIED : null,
    qualifyPa: r.qualify_pa ?? null,
    lastHr: r.last_hr,
    recentScene,
    primaryRole: r.primary_role ?? (r.stats != null ? "batter" : null),
    pitching: r.pitching ? toPitching(r.pitching) : null,
  };
}

export async function getPlayer(id: string, season?: number | null, signal?: AbortSignal): Promise<PlayerSummary> {
  return toPlayerSummary(await get<RawPlayer>(`/players/${encodeURIComponent(id)}`, { season }, signal));
}

// ------------------------------------------------------------------ API-19 시즌별 기록

type RawSeasons = {
  player_id: string;
  name: string;
  seasons: ({ season: number; teams: string[]; games: number } & Partial<RawStats> & Record<string, unknown>)[];
  pitching_seasons?: ({ season: number; role: string; role_label: string; teams: string[] } & Record<string, unknown>)[];
  /** 포스트시즌 기록 (PS1 · PS3): 시즌마다 한 줄, 백분위 없음 */
  postseason_seasons?: ({ season: number; games: number } & Record<string, unknown>)[];
  postseason_pitching?: ({ season: number } & Record<string, unknown>)[];
};

export type SeasonRow = RawSeasons["seasons"][number];
export type PostSeasonRow = { season: number } & Record<string, unknown>;
export type PlayerSeasons = {
  name: string;
  batting: SeasonRow[];
  pitching: NonNullable<RawSeasons["pitching_seasons"]>;
  postBatting: PostSeasonRow[];
  postPitching: PostSeasonRow[];
  all: number[];
};

export async function getPlayerSeasons(id: string, signal?: AbortSignal): Promise<PlayerSeasons> {
  const r = await get<RawSeasons>(`/players/${encodeURIComponent(id)}/seasons`, {}, signal);
  const pitching = r.pitching_seasons ?? [];
  // 시즌 선택 목록 = 타자·투수 기록이 있는 시즌 전부 (최근 시즌부터)
  const all = [...new Set([...r.seasons.map((s) => s.season), ...pitching.map((s) => s.season)])].sort((a, b) => b - a);
  return { name: r.name, batting: r.seasons, pitching, postBatting: r.postseason_seasons ?? [], postPitching: r.postseason_pitching ?? [], all };
}

// ------------------------------------------------------------------ API-17 상대한 투수 · API-06 맞대결

export type BattingLine = { pa: number; ab: number; h: number; hr: number; bb: number; so: number; avg: number | null };
export type VsPitcher = BattingLine & { player_id: string; name: string; team: string | null };
export type Matchups = { season: number | null; min_pa: number; pitchers: VsPitcher[] };

/** as=pitcher면 이 투수가 상대한 타자 (응답 batters) — 화면이 같은 모양으로 쓰게 pitchers 자리에 담는다 */
export async function getMatchups(id: string, season: number | null, minPa: number, signal?: AbortSignal, as: "batter" | "pitcher" = "batter"): Promise<Matchups> {
  const r = await get<Matchups & { batters?: VsPitcher[] }>(`/players/${encodeURIComponent(id)}/matchups`, { season, min_pa: minPa, as }, signal);
  return { season: r.season, min_pa: r.min_pa, pitchers: r.pitchers ?? r.batters ?? [] };
}

export type MatchupPa = GameTag & { pa_id: string; date: string; inning: number; inning_half: string; events: string; events_ko: string; has_video: boolean };
export type Matchup = {
  batter: { player_id: string; name: string };
  pitcher: { player_id: string; name: string };
  season: number | null;
  summary: BattingLine;
  plate_appearances: MatchupPa[];
};

export async function getMatchup(batter: string, pitcher: string, season: number | null, signal?: AbortSignal): Promise<Matchup> {
  return get<Matchup>("/matchup", { batter, pitcher, season }, signal);
}

// ------------------------------------------------------------------ API-37 맞대결 예상

export type ForecastKey = "single" | "xbh" | "home_run" | "bb" | "so" | "out";
type ForecastLine = { avg: number | null; obp: number; slg: number; ops: number };
export type Forecast = {
  season: number;
  batter: { player_id: string; name: string; team: string | null; bats: string | null };
  pitcher: { player_id: string; name: string; team: string | null; throws: string | null };
  /** 「우타 vs 우투」 — 투타 정보가 없으면 null (좌우 빼고 계산) */
  platoon: string | null;
  basis: { batter_pa: number; pitcher_tbf: number; h2h_pa: number; h2h_weight: number };
  /** 타석당 확률 6갈래 (합 1) */
  probs: Record<ForecastKey, number>;
  expected: ForecastLine;
  /** 같은 좌우 조합 리그 평균 */
  league: ForecastLine & { probs: Record<ForecastKey, number> };
  edge: "batter" | "even" | "pitcher";
  h2h: { pa: number; ab: number; h: number; hr: number; avg: number | null };
};

export async function getForecast(batter: string, pitcher: string, season: number, signal?: AbortSignal): Promise<Forecast> {
  return get<Forecast>("/matchup/forecast", { batter, pitcher, season }, signal);
}

// ------------------------------------------------------------------ 장면 (영상 구간)

/** 화면이 재생하는 영상 한 구간. precision: scene 바로 그 장면 / inning 그 이닝부터 / game 경기 요약 처음부터 */
export type Clip = {
  videoId: string;
  title: string;
  startSec: number;
  endSec: number | null;
  durationSec: number | null;
  precision: "scene" | "inning" | "game";
};

type RawHighlight = {
  video_id: string;
  title: string;
  channel: string | null;
  duration_sec: number | null;
  start_sec: number | null;
  end_sec: number | null;
  precision: "game";
} | null;

const toClip = (h: NonNullable<RawHighlight>): Clip => ({
  videoId: h.video_id,
  title: h.title,
  startSec: h.start_sec ?? 0,
  endSec: h.end_sec,
  durationSec: h.duration_sec,
  precision: h.precision,
});

// ------------------------------------------------------------------ API-03 출전 경기 목록

type RawGames = {
  seasons: number[];
  season: number | null;
  months: number[];
  month: number | null;
  games: (GameTag & {
    game_pk: string;
    date: string;
    weekday: string;
    opponent: string;
    home: boolean;
    score: { team: number; opponent: number };
    result: "W" | "L" | "D";
    line: { ab: number; h: number; hr: number };
    video_count: number;
    highlight?: RawHighlight;
    /** 이 경기 이 선수 영상 — 멀티 히트처럼 여러 타석을 담은 영상, 처음부터 재생 (docs/장면.md S13) */
    player_video?: { video_id: string; title: string; duration_sec: number | null; start_sec: number | null; end_sec: number | null } | null;
  })[];
};

export type GameRow = Omit<RawGames["games"][number], "highlight" | "game_pk" | "video_count" | "player_video" | keyof GameTag> & {
  /** 이 경기 이 선수 영상 (여러 타석을 담은 영상, 처음부터) */
  playerVideo: Clip | null;
  /** 포스트시즌 꼬리표 「준PO 2차전」 (정규시즌 null) */
  stageLabel: string | null;
  gamePk: string;
  /** 기본층 「이 경기 하이라이트」 (docs/장면.md). 없으면 null */
  highlight: Clip | null;
};

export type PlayerGames = { seasons: number[]; season: number | null; months: number[]; month: number | null; games: GameRow[] };

export async function getPlayerGames(id: string, season: number | null, month: number | null, signal?: AbortSignal): Promise<PlayerGames> {
  const r = await get<RawGames>(`/players/${encodeURIComponent(id)}/games`, { season, month }, signal);
  return {
    seasons: r.seasons,
    season: r.season,
    months: r.months,
    month: r.month,
    games: r.games.map((g) => ({
      gamePk: g.game_pk,
      date: g.date,
      weekday: g.weekday,
      opponent: g.opponent,
      home: g.home,
      score: g.score,
      result: g.result,
      line: g.line,
      stageLabel: g.stage_label,
      highlight: g.highlight ? toClip(g.highlight) : null,
      playerVideo: g.player_video
        ? { videoId: g.player_video.video_id, title: g.player_video.title, startSec: g.player_video.start_sec ?? 0,
            endSec: g.player_video.end_sec ?? g.player_video.duration_sec, durationSec: g.player_video.duration_sec, precision: "game" }
        : null,
    })),
  };
}

// ------------------------------------------------------------------ API-04 경기 요약 + 그 선수 타석

type RawGamePas = {
  game: {
    game_pk: string;
    date: string;
    away: { team: string; score: number };
    home: { team: string; score: number };
    innings: number;
    highlight?: RawHighlight;
  };
  line: { ab: number; h: number; hr: number; bb: number };
  plate_appearances: {
    pa_id: string;
    pa_no: number;
    inning: number;
    inning_half: "초" | "말";
    events: string;
    events_ko: string;
    runs_scored: number;
    hr_seq: number | null;
    /** 포스트시즌 n호 (PS5). 정규시즌 홈런이면 null */
    post_hr_seq: number | null;
    /** 「시즌 45호」 · 「2026 포스트시즌 2호」 */
    hr_label: string | null;
    runners: { on_1b: boolean; on_2b: boolean; on_3b: boolean };
    pitcher: { player_id: string; name: string };
    has_video: boolean;
  }[];
};

export type PaRow = RawGamePas["plate_appearances"][number];
export type GameDetail = { highlight: Clip | null; line: RawGamePas["line"]; pas: PaRow[] };

export async function getGamePas(gamePk: string, playerId: string, signal?: AbortSignal): Promise<GameDetail> {
  const r = await get<RawGamePas>(`/games/${encodeURIComponent(gamePk)}/plate-appearances`, { player: playerId }, signal);
  return { highlight: r.game.highlight ? toClip(r.game.highlight) : null, line: r.line, pas: r.plate_appearances };
}

// ------------------------------------------------------------------ API-05 타석의 확정 장면

type RawPaVideo = {
  pa_id: string;
  videos: {
    video_id: string; title: string; duration_sec: number | null; start_sec: number | null; end_sec: number | null;
    precision?: "scene" | "inning";
  }[];
};

/** 타석의 확정 장면 중 첫째 (rank 순: 클립이 챕터보다 앞) */
export async function getPaClip(paId: string, signal?: AbortSignal): Promise<Clip | null> {
  const r = await get<RawPaVideo>(`/plate-appearances/${encodeURIComponent(paId)}/video`, {}, signal);
  const v = r.videos[0];
  return v
    ? {
        videoId: v.video_id, title: v.title, startSec: v.start_sec ?? 0, endSec: v.end_sec ?? v.duration_sec,
        durationSec: v.duration_sec, precision: v.precision ?? "scene",
      }
    : null;
}

// ------------------------------------------------------------------ API-12 재생 불가 신고

/** 재생 오류가 난 영상을 알린다. 서버가 YouTube에 확인해 재생 불가면 검수 「영상 소실」로 보낸다 (설계 8-3).
 *  응답은 늘 202라 기다리지 않고, 실패해도 화면에는 영향이 없다 */
export function reportUnplayable(videoId: string): void {
  fetch(`${API_BASE}/video-links/${encodeURIComponent(videoId)}/report`, { method: "POST", keepalive: true }).catch(() => {});
}

// ------------------------------------------------------------------ API-11 타자 비교

/** 07 비교 — 타자끼리(as=batter) · 투수끼리(as=pitcher). 투수는 백분위 · 등수가 각자 역할(선발 · 불펜) 안 기준이라 group_size가 선수마다 */
export type ComparePlayer = {
  player_id: string; name: string; team: string | null; position: string | null;
  has_stats: boolean; qualified: boolean;
  role?: string | null; role_label?: string | null; group_size?: number | null;
  stats: Record<string, number | null> | null;
  axes: { key: AxisKey | PitchAxisKey; label: string; metric: string; reverse: boolean; value: number | null; percentile: number | null; rank: number | null }[];
  message: string | null;
};
export type CompareResult = { season: number; group_size?: number; players: ComparePlayer[] };

export async function getCompare(ids: string[], season: number | null, signal?: AbortSignal, as: "batter" | "pitcher" = "batter"): Promise<CompareResult> {
  return get<CompareResult>("/players/compare", { ids: ids.join(","), season, as }, signal);
}

// ------------------------------------------------------------------ 관리자 검수 (/admin/review, 설계 6-4·8-4)

export type TargetKind = "game" | "pa" | "outing";

export type ReviewItem = {
  target_kind: TargetKind;
  target_id: string;
  date: string | null;
  summary: string;
  video: { video_id: string; title: string; channel: string | null; kind: string | null; duration_sec: number | null };
  status: string;
  origin: string;
  scene_type: string | null;
  precision: "scene" | "inning" | "game";
  start_sec: number | null;
  end_sec: number | null;
  score: number | null;
  reasons: string | null;
  review_reason: string | null;
  tags: string[] | null;
};
export type ReviewQueue = {
  total: number; limit: number; offset: number;
  counts: { target_kind: TargetKind; reason: string; n: number }[];
  items: ReviewItem[];
};
export type ReviewStats = Partial<Record<TargetKind, {
  pending: number; auto_confirmed: number; approved: number; rejected: number; manual: number; accuracy: number | null;
  /** 자동 연결 중 검수에서 맞음(승인)·틀림(반려) — 표본 확인(NFR-07) */
  auto_reviewed_ok: number; auto_reviewed_ng: number;
  /** 타석만: Gemini 제안을 보고 표시한 수 · 사람이 옮긴 시작 시각 평균(초) · 5초 안 */
  gemini?: { marked: number; avg_shift: number; within5: number };
}>>;

/** 관리자 토큰은 sessionStorage에만 (탭을 닫으면 사라진다, 설계 6-4) */
const TOKEN_KEY = "baseon.admin.token";
export const adminToken = {
  get: () => { try { return sessionStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; } },
  set: (t: string) => { try { if (t) sessionStorage.setItem(TOKEN_KEY, t); else sessionStorage.removeItem(TOKEN_KEY); } catch { /* 저장소 막힘 */ } },
};

async function admin<T>(method: "GET" | "PATCH" | "POST", path: string, query: Query = {}, body?: unknown): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v != null) qs.set(k, String(v));
  const token = adminToken.get();
  const res = await fetch(`${API_BASE}${path}${qs.size ? `?${qs}` : ""}`, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => null))?.error;
    throw new ApiError(res.status, err?.code ?? "HTTP_ERROR", err?.message ?? `요청 실패 (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export type ReviewMode = "pending" | "auto_confirmed";

export const getReviewQueue = (f: { mode: ReviewMode; targetKind: TargetKind | null; reason: string | null; season: number | null; offset: number }) =>
  admin<ReviewQueue>("GET", "/admin/review/queue", { status: f.mode, target_kind: f.targetKind, reason: f.reason, season: f.season, limit: 20, offset: f.offset });

export const getReviewStats = () => admin<ReviewStats>("GET", "/admin/review/stats");

export type ReviewActionKind = "approve" | "reject" | "retime" | "move";
const reviewPath = (it: ReviewItem) =>
  `/admin/review/${it.target_kind}/${encodeURIComponent(it.target_id)}/videos/${encodeURIComponent(it.video.video_id)}`;

export const saveReview = (it: ReviewItem, body: { action: ReviewActionKind; reviewer: string; start_sec?: number; end_sec?: number; to_target_id?: string }) =>
  admin<unknown>("PATCH", reviewPath(it), {}, body);

/** 옮김 후보: 타석 = 같은 경기 그 타자 다른 타석 + 영상 매칭 후보, 등판 = 같은 투수 앞뒤 7일 + 같은 경기 다른 투수, 경기 = 같은 날 다른 경기 */
export type MoveCandidate = { target_id: string; date: string; why: string; summary: string };
export const getMoveCandidates = (it: ReviewItem) =>
  admin<{ candidates: MoveCandidate[] }>("GET", reviewPath(it) + "/move-candidates").then((r) => r.candidates);

/** 수동 표시 큐 (API 11-2): 장면 없는 정규시즌 홈런 + 홈런 장면 목표(NFR-06, 70%) */
export type MissingHr = {
  pa_id: string; date: string; game_pk: string; game: string; batter: string; pitcher: string;
  inning: number; half: "초" | "말"; hr_seq: number | null; runs: number;
  on_1b: boolean; on_2b: boolean; on_3b: boolean; outs: number | null; balls: number | null; strikes: number | null;
  /** 이 타석에 검수 대기 연결이 있다 → 검수 대기에서 먼저 본다 */
  has_pending: boolean;
  highlight: { video_id: string; title: string; channel: string | null; duration_sec: number | null; start_sec: number; end_sec: number | null } | null;
  /** Gemini 제안 시각 (etl/09_suggest_times.py). found=false = 하이라이트를 다 봤는데 못 찾음 → 「영상에 없음」 후보 */
  suggestion: {
    video_id: string; title: string; channel: string | null; duration_sec: number | null;
    found: boolean; t_sec: number | null; start_sec: number | null; end_sec: number | null;
    strength: "strong" | "weak" | null; checks: string; evidence: string; model: string | null;
  } | null;
};
export type MissingHrList = { season: number; goal: { total: number; done: number; target: number; rate: number }; total: number; items: MissingHr[] };
export const getMissingHr = (season: number) => admin<MissingHrList>("GET", "/admin/review/missing-hr", { season, limit: 500 });
/** API 12-2: 재생 시각으로 장면 표시 (end_sec 생략 = 시작 + 20초) */
export const markManual = (b: { pa_id: string; video_id: string; start_sec: number; end_sec?: number; reviewer: string; suggested_sec?: number }) =>
  admin<unknown>("POST", "/admin/review/manual", {}, b);
/** API 12-3: 이 홈런은 영상에 없음 (큐에서 빠진다) */
export const markNoVideo = (b: { pa_id: string; reviewer: string }) => admin<unknown>("POST", "/admin/review/no-video", {}, b);

// ------------------------------------------------------------------ TanStack Query 키

export const qk = {
  search: (q: string) => ["search", normalizeQuery(q)] as const,
  player: (id: string, season: number | null) => ["player", id, season] as const,
  seasons: (id: string) => ["seasons", id] as const,
  games: (id: string, season: number | null, month: number | null) => ["games", id, season, month] as const,
  gamePas: (gamePk: string, playerId: string) => ["gamePas", gamePk, playerId] as const,
  outings: (id: string, season: number | null, month: number | null) => ["outings", id, season, month] as const,
  outingDetail: (outingId: string) => ["outingDetail", outingId] as const,
  compare: (ids: string[], season: number | null, as: "batter" | "pitcher" = "batter") => ["compare", ids.join(","), season, as] as const,
  matchups: (id: string, season: number | null, minPa: number, as: "batter" | "pitcher" = "batter") => ["matchups", id, season, minPa, as] as const,
  matchup: (batter: string, pitcher: string, season: number | null) => ["matchup", batter, pitcher, season] as const,
  forecast: (batter: string, pitcher: string, season: number) => ["forecast", batter, pitcher, season] as const,
  searchRole: (q: string, role: "batter" | "pitcher") => ["search", normalizeQuery(q), role] as const,
  reviewQueue: (m: string, k: string | null, r: string | null, s: number | null, o: number) => ["reviewQueue", m, k, r, s, o] as const,
  reviewStats: () => ["reviewStats"] as const,
  missingHr: (season: number) => ["missingHr", season] as const,
  postseason: () => ["postseason"] as const,
  recentHrs: (limit: number) => ["recentHrs", limit] as const,
  meta: () => ["meta"] as const,
  day: (date: string | null) => ["day", date] as const,
  gameBox: (gamePk: string) => ["gameBox", gamePk] as const,
  leaders: (role: "batter" | "pitcher") => ["leaders", role] as const,
  topBatters: () => ["topBatters"] as const,
  topPitchers: () => ["topPitchers"] as const,
  standings: () => ["standings"] as const,
  standingsHistory: (season: number) => ["standingsHistory", season] as const,
  roster: (team: string) => ["roster", team] as const,
  rankings: (role: string, axis: string) => ["rankings", role, axis] as const,
  gameDays: (start: string) => ["gameDays", start] as const,
  team: (kind: string, team: string) => ["team", kind, team] as const,
  playerScenes: (id: string, season: number | null, as: "batter" | "pitcher") => ["playerScenes", id, season, as] as const,
  form: (id: string, season: number | null, as: "batter" | "pitcher") => ["form", id, season, as] as const,
  similar: (id: string, season: number | null, as: "batter" | "pitcher") => ["similar", id, season, as] as const,
};

// ------------------------------------------------------------------ API-25 포스트시즌 코너 · API-15 최근 홈런 (메인)

type RawClip = { video_id: string; title: string; duration_sec: number | null; start_sec: number | null; end_sec: number | null; precision: "scene" | "inning" | "game" | null };
const rawClip = (c: RawClip): Clip => ({
  videoId: c.video_id, title: c.title, startSec: c.start_sec ?? 0, endSec: c.end_sec ?? c.duration_sec,
  durationSec: c.duration_sec, precision: c.precision ?? "scene",
});

export type PostScene = {
  kind: "walkoff" | "comeback" | "home_run" | "go_ahead" | "pitching";
  label: string;
  gamePk: string;
  player: { player_id: string; name: string };
  clip: Clip;
};
export type PostSeries = {
  stage: "WC" | "SPO" | "PO" | "KS";
  name: string;
  teams: string[];
  wins: Record<string, number>;
  winner: string | null;
  games: { gamePk: string; stageLabel: string; date: string; away: { team: string; score: number }; home: { team: string; score: number }; highlight: Clip | null }[];
  scenes: PostScene[];
};
export type Postseason = { season: number; period: { start: string | null; end: string | null; active: boolean }; series: PostSeries[] };

type RawPostseason = {
  season: number;
  period: Postseason["period"];
  series: (Omit<PostSeries, "games" | "scenes"> & {
    games: { game_pk: string; stage_label: string; date: string; away: { team: string; score: number }; home: { team: string; score: number }; highlight: RawHighlight }[];
    scenes: { kind: PostScene["kind"]; label: string; game_pk: string; player: PostScene["player"]; clip: RawClip }[];
  })[];
};

/** 메인 「포스트시즌 코너」 (docs/포스트시즌.md PS6). period.active일 때만 그린다 */
export async function getPostseason(signal?: AbortSignal): Promise<Postseason> {
  const r = await get<RawPostseason>("/postseason", {}, signal);
  return {
    season: r.season,
    period: r.period,
    series: r.series.map((s) => ({
      ...s,
      games: s.games.map((g) => ({ gamePk: g.game_pk, stageLabel: g.stage_label, date: g.date, away: g.away, home: g.home, highlight: g.highlight ? toClip(g.highlight) : null })),
      scenes: s.scenes.map((c) => ({ kind: c.kind, label: c.label, gamePk: c.game_pk, player: c.player, clip: rawClip(c.clip) })),
    })),
  };
}

export type RecentHr = GameTag & {
  pa_id: string;
  date: string;
  inning: number;
  inning_half: "초" | "말";
  runs: number;
  hr_label: string | null;
  situation: string | null;
  batter: { player_id: string; name: string; team: string };
  pitcher: { player_id: string; name: string };
  opponent: string;
  has_video: boolean;
  video: { video_id: string; title: string } | null;
};
export type RecentHrs = { season: number; includes_postseason: boolean; home_runs: RecentHr[] };

/** 메인 「최근 홈런 장면」 (API-15). 포스트시즌 기간이면 포스트시즌 홈런도 최신순으로 (PS7) */
export async function getRecentHomeRuns(limit = 9, signal?: AbortSignal): Promise<RecentHrs> {
  return get<RecentHrs>("/home-runs", { limit }, signal);
}


// ------------------------------------------------------------------ 메인 2.0 (API-20 · 14 · 18 · 29 · 16 · 26 · 13)

/** API-20 기록 기준일 — 내비 「기록 7.26 기준」 */
export type Meta = { data_as_of: string | null; season: number | null };
export const getMeta = (signal?: AbortSignal) => get<Meta>("/meta", {}, signal);

type RawSceneClip = RawClip & { scene_type?: string | null; tags?: string[] };
type RawDayGame = GameTag & {
  game_pk: string;
  dh_no: number;
  innings: number | null;
  away: { team: string; score: number; result: "W" | "L" | "D" };
  home: { team: string; score: number; result: "W" | "L" | "D" };
  home_runs: { pa_id: string; inning: number; inning_half: "초" | "말"; runs: number; hr_seq: number | null; hr_label: string | null;
               batter: { player_id: string; name: string }; scene: RawSceneClip | null }[];
  pitcher_scenes: { outing_id: string; pitcher: { player_id: string; name: string }; team: string; role: "선발" | "구원";
                    line: OutingLine & { tbf: number; bb: number; hbp: number; hr: number; pitches: number }; scene: RawSceneClip }[];
  line: GameLine;
  highlight: RawHighlight;
};
/** 이닝별 점수 · 안타 (API-14 `line`). null = 그 반 이닝이 없음(홈팀이 이겨 안 한 9회말 등) */
export type GameLine = { away: (number | null)[]; home: (number | null)[]; away_h: number; home_h: number };
type RawDay = { date: string; prev_date: string | null; next_date: string | null;
                scene_counts: { home_runs: number; home_run_scenes: number; pitcher_scenes: number }; games: RawDayGame[] };

/** 그날 장면 한 개 — 홈런(타자) 또는 등판(투수). 제목은 우리 기록으로 만든다 (장면.md · 코드 outingLine) */
export type DayScene = {
  kind: "home_run" | "outing";
  gamePk: string;
  player: { player_id: string; name: string };
  team: string;
  clip: Clip;
  hrSeq?: number | null;
  runs?: number;
  inning?: number;
  inningHalf?: "초" | "말";
  role?: "선발" | "구원";
  line?: OutingLine;
};
export type DayGame = Omit<RawDayGame, "home_runs" | "pitcher_scenes" | "highlight"> & {
  highlight: Clip | null;
  scenes: DayScene[]; // 등판 장면(선발 먼저) → 홈런 장면(시즌 몇 호가 큰 순)
  homeRuns: DayHomeRun[]; // 그 경기 홈런 전부, 나온 순서 (08 일정 홈런 칩 · 10 「영상 없음」)
};
export type DayHomeRun = { player_id: string; name: string; hrSeq: number | null; inning: number; inningHalf: "초" | "말"; clip: Clip | null;
                            runs: number; label: string | null };
export type Day = Omit<RawDay, "games"> & { games: DayGame[] };

// ------------------------------------------------------------------ API-38 경기 박스스코어 (04 경기 상세)

export type BoxBatter = { player_id: string; name: string; position: string | null; pa: number; ab: number; h: number; hr: number; bb: number; so: number };
export type BoxPitcher = { player_id: string; name: string; outing_id: string; role: "선발" | "구원";
                           outs: number; tbf: number; h: number; hr: number; bb: number; hbp: number; so: number; r: number };
export type BoxTeam = { team: string; score: number; result: "W" | "L" | "D"; batters: BoxBatter[]; pitchers: BoxPitcher[] };
export type GameBox = GameTag & { game_pk: string; date: string; season: number; innings: number | null; away: BoxTeam; home: BoxTeam };
export const getGameBox = (gamePk: string, signal?: AbortSignal) => get<GameBox>(`/games/${encodeURIComponent(gamePk)}/box`, {}, signal);

/** 경기번호 앞 8자리가 날짜 (20260726WOHT02026 → 2026-07-26) */
export const gameDate = (gamePk: string) => `${gamePk.slice(0, 4)}-${gamePk.slice(4, 6)}-${gamePk.slice(6, 8)}`;

/** API-14 날짜별 경기 · 그날 장면. date를 비우면 데이터의 마지막 경기일 */
export async function getDay(date: string | null, signal?: AbortSignal): Promise<Day> {
  const r = await get<RawDay>("/games", { date }, signal);
  return {
    ...r,
    games: r.games.map((g) => {
      const scenes: DayScene[] = [
        ...g.pitcher_scenes.map((p): DayScene => ({
          kind: "outing", gamePk: g.game_pk, player: p.pitcher, team: p.team, clip: rawClip(p.scene), role: p.role, line: p.line,
        })),
        ...g.home_runs.filter((h) => h.scene).sort((a, b) => (b.hr_seq ?? 0) - (a.hr_seq ?? 0)).map((h): DayScene => ({
          kind: "home_run", gamePk: g.game_pk, player: h.batter, team: h.inning_half === "초" ? g.away.team : g.home.team,
          clip: rawClip(h.scene!), hrSeq: h.hr_seq, runs: h.runs, inning: h.inning, inningHalf: h.inning_half,
        })),
      ];
      const { home_runs, pitcher_scenes, ...rest } = g; // eslint-disable-line @typescript-eslint/no-unused-vars
      const homeRuns = g.home_runs.map((h): DayHomeRun => ({
        ...h.batter, hrSeq: h.hr_seq, inning: h.inning, inningHalf: h.inning_half, clip: h.scene ? rawClip(h.scene) : null,
        runs: h.runs, label: h.hr_label,
      }));
      return { ...rest, highlight: g.highlight ? toClip(g.highlight) : null, scenes, homeRuns };
    }),
  };
}

/** 메인 능력 카드 한 장 — 타자(API-18) · 투수(API-29) 같은 모양으로 맞춘다 */
export type LeaderPlayer = { rank: number; player_id: string; name: string; team: string | null; value: number | null; percentile: number };
export type LeaderCard = { key: string; players: LeaderPlayer[] };
export type Leaders = { season: number; groupSize: number; cards: LeaderCard[] };

export async function getLeaders(role: "batter" | "pitcher", signal?: AbortSignal): Promise<Leaders> {
  if (role === "batter") {
    const r = await get<{ season: number; group_size: number; leaders: Record<string, { players: LeaderPlayer[] }> }>("/leaders", { limit: 3 }, signal);
    return { season: r.season, groupSize: r.group_size, cards: Object.entries(r.leaders).map(([key, v]) => ({ key, players: v.players })) };
  }
  const r = await get<{ season: number; group_size: number; leaders: Record<string, { players: LeaderPlayer[] }> }>("/pitchers/leaders", { limit: 3 }, signal);
  return { season: r.season, groupSize: r.group_size, cards: Object.entries(r.leaders).map(([key, v]) => ({ key, players: v.players })) };
}

/** 「지금 가장 잘하는 선수」 — 타자 OPS 순(API-16) · 선발 WHIP 순(API-26) 5명 */
export type TopBatter = { rank: number; player_id: string; name: string; team: string | null; position: string | null;
                          back_number: string | number | null; ops: number | null; hr: number | null; scene_count: number };
export type TopPitcher = { rank: number; player_id: string; name: string; team: string | null; back_number: string | number | null;
                           whip: number | null; so: number | null; scene_count: number };
export const getTopBatters = (signal?: AbortSignal) =>
  get<{ season: number; group_size: number; batters: TopBatter[] }>("/batters", { sort: "ops", limit: 5 }, signal);
export const getTopPitchers = (signal?: AbortSignal) =>
  get<{ season: number; group_size: number; pitchers: TopPitcher[] }>("/pitchers", { role: "starter", qualified: true, sort: "whip", limit: 5 }, signal);

/** API-13 팀 순위 */
export type Standing = { team_id: string; team: string; games: number; w: number; l: number; d: number; pct: number; rank: number; gb: number };
export const getStandings = (signal?: AbortSignal) => get<{ season: number; teams: Standing[] }>("/standings", {}, signal);

/** API-28 순위 변동 — 주마다 마지막 경기일의 순위 (ranks: 팀 이름 → 순위, 공동 순위 있음) */
export type StandingsHistory = { season: number; teams: number; points: { date: string; ranks: Record<string, number> }[] };
export const getStandingsHistory = (season: number, signal?: AbortSignal) =>
  get<StandingsHistory>("/standings/history", { season }, signal);

/** 05 능력별 순위 — 타자(API-16 `sort=지표`) · 선발(API-26 `role=starter&qualified=true&sort=지표`)을 같은 줄 모양으로 */
export type RankRow = {
  rank: number; // 지표 등수 (공동 순위)
  player_id: string;
  name: string;
  team: string | null;
  meta: string; // 「LG · 내야수」 · 「NC · 선발」
  percentile: number;
  value: number | null; // 지표 원 수치
  stats: { label: string; value: string }[]; // 타석 · 홈런 · OPS / 탈삼진 · 이닝 · WHIP
  scene: { clip: Clip; title: string; date: string } | null; // 대표 장면 (타자 최근 홈런 · 투수 그 지표 등판)
};
export type Rankings = { season: number; groupSize: number; leagueAvg: number | null; rows: RankRow[] };

type RawRankScene = RawClip & { date: string; hr_seq?: number | null; line?: OutingLine };
const BAT_VALUE: Record<string, "k_pct" | "avg" | "iso" | "bb_pct" | "ops_sd"> = { contact: "k_pct", hit: "avg", power: "iso", eye: "bb_pct", consistency: "ops_sd" };

export async function getRankings(role: "batter" | "pitcher", axis: string, signal?: AbortSignal): Promise<Rankings> {
  const scene = (name: string, s: RawRankScene | null | undefined) => s ? {
    clip: rawClip(s), date: s.date,
    title: s.line ? `${name} ${outingLine(s.line)}` : `${name} ${s.hr_seq ? `${s.hr_seq}호 ` : ""}홈런`,
  } : null;
  if (role === "batter") {
    type B = { player_id: string; name: string; team: string | null; position: string | null; pa: number | null; hr: number | null; ops: number | null;
               percentiles: Record<string, number | null>; axis_ranks: Record<string, number>; scene?: RawRankScene | null } & Record<string, unknown>;
    const r = await get<{ season: number; group_size: number; league_avg: number | null; batters: B[] }>("/batters", { sort: axis, limit: 500 }, signal);
    return {
      season: r.season, groupSize: r.group_size, leagueAvg: r.league_avg,
      rows: r.batters.map((b) => ({
        rank: b.axis_ranks[axis], player_id: b.player_id, name: b.name, team: b.team,
        meta: [b.team, b.position].filter(Boolean).join(" · "), percentile: b.percentiles[axis] ?? 0,
        value: (b[BAT_VALUE[axis]] as number | null) ?? null,
        stats: [{ label: "타석", value: String(b.pa ?? "–") }, { label: "홈런", value: String(b.hr ?? "–") }, { label: "OPS", value: rate3(b.ops) }],
        scene: scene(b.name, b.scene),
      })),
    };
  }
  type P = { player_id: string; name: string; team: string | null; so: number | null; outs: number | null; whip: number | null;
             metrics: Record<string, number | null>; percentiles: Record<string, number | null>; axis_ranks: Record<string, number>; scene?: RawRankScene | null };
  const r = await get<{ season: number; group_size: number; league_avg: number | null; pitchers: P[] }>(
    "/pitchers", { role: "starter", qualified: true, sort: axis }, signal);
  return {
    season: r.season, groupSize: r.group_size, leagueAvg: r.league_avg,
    rows: r.pitchers.map((p) => ({
      rank: p.axis_ranks[axis], player_id: p.player_id, name: p.name, team: p.team,
      meta: [p.team, "선발"].filter(Boolean).join(" · "), percentile: p.percentiles[axis] ?? 0, value: p.metrics[axis],
      stats: [{ label: "탈삼진", value: String(p.so ?? "–") }, { label: "이닝", value: innings(p.outs) }, { label: "WHIP", value: p.whip?.toFixed(2) ?? "–" }],
      scene: scene(p.name, p.scene),
    })),
  };
}

/** API-34 날짜마다 경기 수 · 홈런 수 · 장면 수 (08 일정 · 10 장면 위쪽 한 주 띠). days는 경기가 있는 날만 */
export type GameDayCount = { date: string; games: number; home_runs: number; home_run_scenes: number; pitcher_scenes: number };
export type GameDays = { start: string; end: string; first_date: string | null; last_date: string | null; days: GameDayCount[] };
export const getGameDays = (start: string, end: string, signal?: AbortSignal) => get<GameDays>("/games/days", { start, end }, signal);

// ------------------------------------------------------------------ 06 팀 (API-35 최근 경기 · API-33 최근 장면 · API-16 · 26 선수 표)

export type TeamGame = GameTag & { game_pk: string; date: string; home: boolean; opponent: string; innings: number | null;
                                   score: { team: number; opponent: number }; result: "W" | "L" | "D"; highlight: Clip | null };
export async function getTeamGames(team: string, signal?: AbortSignal): Promise<TeamGame[]> {
  type Raw = Omit<TeamGame, "highlight"> & { highlight: RawHighlight };
  const r = await get<{ games: Raw[] }>(`/teams/${encodeURIComponent(team)}/games`, { limit: 5 }, signal);
  return r.games.map((g) => ({ ...g, highlight: g.highlight ? toClip(g.highlight) : null }));
}

/** 팀 장면 한 개 — 홈런이면 「30호 · 솔로 홈런 · 4회말」, 등판이면 「6이닝 8K 무실점 · 선발」 재료 */
export type TeamScene = {
  kind: "home_run" | "outing"; date: string; opponent: string; player: { player_id: string; name: string }; clip: Clip;
  hrSeq?: number | null; inning?: number; inningHalf?: "초" | "말"; runs?: number; role?: "선발" | "구원"; line?: OutingLine;
};
export type TeamScenes = { counts: { home_run_scenes: number; pitcher_scenes: number; total: number }; scenes: TeamScene[] };
export async function getTeamScenes(team: string, signal?: AbortSignal): Promise<TeamScenes> {
  type Raw = Omit<TeamScene, "clip" | "hrSeq" | "inningHalf"> & { scene: RawClip; hr_seq?: number | null; inning_half?: "초" | "말" };
  const r = await get<{ counts: TeamScenes["counts"]; scenes: Raw[] }>(`/teams/${encodeURIComponent(team)}/scenes`, { limit: 12 }, signal);
  return {
    counts: r.counts,
    scenes: r.scenes.map(({ scene, hr_seq, inning_half, ...s }) => ({ ...s, clip: rawClip(scene), hrSeq: hr_seq, inningHalf: inning_half })),
  };
}

export type TeamBatter = { player_id: string; name: string; back_number: string | number | null; position: string | null; hr: number | null;
                           ops: number | null; pa: number | null; scene_count: number; strengths: { axis: string; rank: number }[] };
export const getTeamBatters = (team: string, signal?: AbortSignal) =>
  get<{ group_size: number; batters: TeamBatter[] }>("/batters", { team, sort: "ops", limit: 30 }, signal);

export type TeamPitcher = { player_id: string; name: string; back_number: string | number | null; g: number; gs: number; outs: number;
                            so: number; whip: number | null; qualified: boolean; scene_count: number; axis_ranks: Record<string, number> | null };
export const getTeamPitchers = (team: string, signal?: AbortSignal) =>
  get<{ group_size: number; pitchers: TeamPitcher[] }>("/pitchers", { team, role: "starter", sort: "outs", limit: 30 }, signal);

/** 선수 탭 「팀별 선수」 — 그 시즌 그 팀에서 뛴 선수 전원 (API-16 `qualified=false` + API-26). 트레이드면 마지막 팀 */
type Pcts = Record<string, number | null> | null; // 지표 백분위 (비교 대상이 아니면 null)
export type RosterBatter = TeamBatter & { bats_throws: string | null; qualified: boolean; games: number | null; avg: number | null; h: number | null;
                                          percentiles: Pcts; axis_ranks: Record<string, number> | null };
export type RosterPitcher = TeamPitcher & { bats_throws: string | null; role: "starter" | "reliever" | null; percentiles: Pcts };
export type Roster = { season: number; batters: RosterBatter[]; pitchers: RosterPitcher[] };
export async function getRoster(team: string, signal?: AbortSignal): Promise<Roster> {
  const [b, p] = await Promise.all([
    get<{ season: number; batters: RosterBatter[] }>("/batters", { team, qualified: false, sort: "pa", limit: 500 }, signal),
    get<{ pitchers: RosterPitcher[] }>("/pitchers", { team, sort: "outs", limit: 500 }, signal),
  ]);
  return { season: b.season, batters: b.batters, pitchers: p.pitchers };
}

// ------------------------------------------------------------------ API-36 선수의 장면 목록 · API-27/32 요즘 타격감 · 투구감 · API-31 비슷한 선수

export type PlayerPaScene = GameTag & {
  paId: string; date: string; weekday: string; gamePk: string;
  opponent: string; home: boolean; inning: number; inningHalf: string;
  events: string; kind: "home_run" | "on_base"; hrSeq: number | null; runs: number | null;
  outs: number | null; count: { balls: number | null; strikes: number | null };
  pitcher: { player_id: string; name: string };
  clip: Clip;
};
export type PlayerScenes = {
  counts: { scenes: number; home_runs: number; home_run_scenes: number; on_base_scenes: number };
  scenes: PlayerPaScene[];
};

export async function getPlayerScenes(id: string, season: number, signal?: AbortSignal): Promise<PlayerScenes> {
  type Raw = { counts: PlayerScenes["counts"]; scenes: (Omit<PlayerPaScene, "paId" | "gamePk" | "inningHalf" | "hrSeq" | "clip"> & {
    pa_id: string; game_pk: string; inning_half: string; hr_seq: number | null; scene: RawScene })[] };
  const r = await get<Raw>(`/players/${encodeURIComponent(id)}/scenes`, { season }, signal);
  return {
    counts: r.counts,
    scenes: r.scenes.map(({ pa_id, game_pk, inning_half, hr_seq, scene, ...x }) => ({
      ...x, paId: pa_id, gamePk: game_pk, inningHalf: inning_half, hrSeq: hr_seq, clip: sceneClip(scene),
    })),
  };
}

export type PitcherOutings = {
  counts: { outings: number; highlights: number; scenes: number; scoreless: number; seven_plus: number };
  outings: OutingRow[];
};

export async function getPitcherOutings(id: string, season: number, signal?: AbortSignal): Promise<PitcherOutings> {
  const r = await get<{ counts: PitcherOutings["counts"]; outings: RawOutings["outings"] }>(
    `/players/${encodeURIComponent(id)}/scenes`, { season, as: "pitcher" }, signal);
  return {
    counts: r.counts,
    outings: r.outings.map(({ outing_id, scene, highlight, ...o }) => ({
      ...o, outingId: outing_id, scene: scene ? sceneClip(scene) : null, highlight: highlight ? toClip(highlight) : null,
    })),
  };
}

/** 요즘 타격감(최근 20경기 OPS) · 투구감(최근 10등판 WHIP) — 한 모양으로 맞춘다 */
export type Form = {
  kind: "batter" | "pitcher";
  window: number;
  season: number | null; recent: number | null; league: number | null;
  verdict: "up" | "down" | "flat" | null;
  range: [string, string] | null;
  points: { date: string; value: number }[];
};

export async function getForm(id: string, season: number, as: "batter" | "pitcher", signal?: AbortSignal): Promise<Form> {
  if (as === "batter") {
    const r = await get<{ window: number; season_ops: number | null; recent_ops: number | null; league_ops: number | null;
      verdict: Form["verdict"]; points: { date: string; ops: number }[] }>(`/players/${encodeURIComponent(id)}/form`, { season }, signal);
    const pts = r.points.slice(-r.window);
    return {
      kind: "batter", window: r.window, season: r.season_ops, recent: r.recent_ops, league: r.league_ops, verdict: r.verdict,
      range: pts.length ? [pts[0].date, pts[pts.length - 1].date] : null,
      points: r.points.map((p) => ({ date: p.date, value: p.ops })),
    };
  }
  const r = await get<{ window: number; season_whip: number | null; recent_whip: number | null; league_whip: number | null;
    verdict: Form["verdict"]; recent_range: [string, string] | null; points: { date: string; whip: number }[] }>(
    `/players/${encodeURIComponent(id)}/pitching-form`, { season }, signal);
  return {
    kind: "pitcher", window: r.window, season: r.season_whip, recent: r.recent_whip, league: r.league_whip, verdict: r.verdict,
    range: r.recent_range, points: r.points.map((p) => ({ date: p.date, value: p.whip })),
  };
}

export type SimilarPlayer = {
  player_id: string; name: string; team: string | null; rank: number; value: number | null;
  ops?: number | null; hr?: number | null; whip?: number | null; so?: number | null;
  clip: Clip | null; sceneTitle: string | null;
};
export type Similar = { axis: string; label: string; myRank: number | null; groupSize: number | null; players: SimilarPlayer[] };

export async function getSimilar(id: string, season: number, as: "batter" | "pitcher", signal?: AbortSignal): Promise<Similar> {
  type RawSim = { axis: string; label: string; my_rank: number | null; group_size: number | null;
    players: (Omit<SimilarPlayer, "clip" | "sceneTitle"> & { scene: (RawScene & { date: string; hr_seq?: number | null; line?: OutingLine }) | null })[] };
  const r = await get<RawSim>(`/players/${encodeURIComponent(id)}/similar`, { season, as }, signal);
  return {
    axis: r.axis, label: r.label, myRank: r.my_rank, groupSize: r.group_size,
    players: r.players.map(({ scene, ...p }) => ({
      ...p,
      clip: scene ? sceneClip(scene) : null,
      sceneTitle: scene ? `${p.name} ${scene.line ? outingLine(scene.line) : `${scene.hr_seq ? `${scene.hr_seq}호 ` : ""}홈런`}` : null,
    })),
  };
}
