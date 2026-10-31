import { Suspense } from "react";
import PlayerView from "./PlayerView";

// /players/?id=&tab=&season=&view= — 03 · 03b 선수. 정적 내보내기라 id는 쿼리로 받는다 (useSearchParams → Suspense 필요)
export default function PlayersPage() {
  return (
    <Suspense fallback={null}>
      <PlayerView />
    </Suspense>
  );
}
