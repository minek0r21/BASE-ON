"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import RankingsView from "./RankingsView";
import TeamRoster from "./TeamRoster";

// /rankings/ — 내비 「선수」. 첫 화면은 팀별 선수(?team=), role · axis가 있으면 05 능력별 순위(?role=&axis=, rankingsHref).
// 정적 내보내기라 쿼리로 받는다 (useSearchParams → Suspense 필요)
function PlayersPage() {
  const params = useSearchParams();
  return params.has("role") || params.has("axis") ? <RankingsView /> : <TeamRoster />;
}

export default function RankingsPage() {
  return (
    <Suspense fallback={null}>
      <PlayersPage />
    </Suspense>
  );
}
