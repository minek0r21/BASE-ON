import type { Metadata } from "next";

// 관리자 화면: 서버에서는 Caddy가 /admin을 막는다(404). 로컬 · 검색엔진 모두에 감춘다
export const metadata: Metadata = { title: "장면 검수", robots: { index: false, follow: false } };

export default function Layout({ children }: LayoutProps<"/admin">) {
  return children;
}
