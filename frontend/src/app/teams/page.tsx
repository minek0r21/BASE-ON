import { Suspense } from "react";
import TeamView from "./TeamView";

// /teams/?team=KIA — 06 팀 (내비 「팀」). 정적 내보내기라 쿼리로 받는다 (useSearchParams → Suspense 필요)
export default function TeamsPage() {
  return (
    <Suspense fallback={null}>
      <TeamView />
    </Suspense>
  );
}
