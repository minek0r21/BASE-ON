import { Suspense } from "react";
import GameView from "./GameView";

// /games/?id=경기번호 — 04 경기 상세. 정적 내보내기라 쿼리로 받는다 (useSearchParams → Suspense 필요)
export default function GamePage() {
  return (
    <Suspense fallback={null}>
      <GameView />
    </Suspense>
  );
}
