import { Suspense } from "react";
import PlayerView from "./PlayerView";

// /players/?id=&tab=&season= — 정적 내보내기라 id는 쿼리로 받는다 (useSearchParams → Suspense 필요)
export default function PlayersPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6">
      <Suspense fallback={<p className="text-muted">불러오는 중…</p>}>
        <PlayerView />
      </Suspense>
    </div>
  );
}
