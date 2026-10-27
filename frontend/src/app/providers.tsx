"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "@/lib/api";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // 데이터는 스냅샷 고정(NFR-04)이라 자주 다시 받을 필요가 없다
            staleTime: 5 * 60_000,
            refetchOnWindowFocus: false,
            // 4xx(없는 선수·잘못된 검색어)는 다시 시도해도 같다
            retry: (n, err) => !(err instanceof ApiError && err.status < 500) && n < 2,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
