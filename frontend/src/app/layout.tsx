import type { Metadata } from "next";
import { Big_Shoulders, Geist, Noto_Sans_KR } from "next/font/google";
import Footer from "@/components/layout/Footer";
import Nav from "@/components/layout/Nav";
import Providers from "./providers";
import "./globals.css";

// 글꼴 (Figma 2.0): 본문 Noto Sans KR · 큰 숫자 Big Shoulders Display · 표 숫자 Geist. 빌드 때 받아 같이 배포한다
const noto = Noto_Sans_KR({ weight: ["400", "500", "700", "900"], subsets: ["latin"], variable: "--font-noto", display: "swap" });
const shoulders = Big_Shoulders({ weight: ["800"], subsets: ["latin"], variable: "--font-big-shoulders", display: "swap" });
const geist = Geist({ weight: ["500", "600", "700"], subsets: ["latin"], variable: "--font-geist", display: "swap" });

export const metadata: Metadata = {
  title: "BASE:ON",
  description: "기록에서 장면으로. KBO 입문 팬을 위한 기록 해석 · 장면 연결 서비스",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className={`h-full antialiased ${noto.variable} ${shoulders.variable} ${geist.variable}`}>
      <body className="flex min-h-full flex-col">
        <Providers>
          <Nav />
          {/* 화면마다 폭이 달라서(메인은 히어로가 화면 끝까지) 폭은 각 화면이 정한다 */}
          <main className="flex-1">{children}</main>
          <Footer />
        </Providers>
      </body>
    </html>
  );
}
