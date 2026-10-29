import { Suspense } from "react";
import ScheduleView from "./ScheduleView";

// /schedule/?date= — 08 일정 (내비 「일정」). 정적 내보내기라 쿼리로 받는다 (useSearchParams → Suspense 필요)
export default function SchedulePage() {
  return (
    <Suspense fallback={null}>
      <ScheduleView />
    </Suspense>
  );
}
