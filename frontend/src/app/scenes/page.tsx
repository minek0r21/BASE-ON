import { Suspense } from "react";
import ScenesView from "./ScenesView";

// /scenes/?date= — 10 장면 (내비 「장면」). 정적 내보내기라 쿼리로 받는다 (useSearchParams → Suspense 필요)
export default function ScenesPage() {
  return (
    <Suspense fallback={null}>
      <ScenesView />
    </Suspense>
  );
}
