import { Suspense } from "react";
import CompareView from "./CompareView";

// /compare/?ids=&as= — 07 선수 비교. 정적 내보내기라 쿼리로 받는다 (useSearchParams → Suspense 필요)
export default function ComparePage() {
  return (
    <Suspense fallback={null}>
      <CompareView />
    </Suspense>
  );
}
