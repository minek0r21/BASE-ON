import { Suspense } from "react";
import RankingsView from "./RankingsView";

// /rankings/?role=&axis= — 05 능력별 순위 (내비 「선수」). 정적 내보내기라 쿼리로 받는다 (useSearchParams → Suspense 필요)
export default function RankingsPage() {
  return (
    <Suspense fallback={null}>
      <RankingsView />
    </Suspense>
  );
}
