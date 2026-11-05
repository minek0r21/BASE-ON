import type { Metadata, Viewport } from "next";
import { Big_Shoulders, Geist, Noto_Sans_KR } from "next/font/google";
import Footer from "@/components/layout/Footer";
import Nav from "@/components/layout/Nav";
import Providers from "./providers";
import "./globals.css";

// 글꼴 (Figma 2.0): 본문 Noto Sans KR · 큰 숫자 Big Shoulders Display · 표 숫자 Geist. 빌드 때 받아 같이 배포한다
const noto = Noto_Sans_KR({ weight: ["400", "500", "700", "900"], subsets: ["latin"], variable: "--font-noto", display: "swap" });
const shoulders = Big_Shoulders({ weight: ["800"], subsets: ["latin"], variable: "--font-big-shoulders", display: "swap" });
const geist = Geist({ weight: ["500", "600", "700"], subsets: ["latin"], variable: "--font-geist", display: "swap" });

const DESCRIPTION = "기록에서 장면으로. KBO 입문 팬을 위한 기록 해석 · 장면 연결 서비스";

// 탭 제목: 화면마다 「선수 · BASE:ON」 (경로 폴더의 layout.tsx), 선수 · 팀 · 경기는 이름을 받은 뒤 바꾼다(lib/title.ts)
// 아이콘: app/icon.svg · favicon.ico · apple-icon.png (내비 로고와 같은 모양)
export const metadata: Metadata = {
  title: { default: "BASE:ON", template: "%s · BASE:ON" },
  description: DESCRIPTION,
  applicationName: "BASE:ON",
  // 시험 서비스(서버 비밀번호 잠금 · 데이터 이용 범위 README)라 검색엔진에 올리지 않는다 — robots.ts와 같이 바꾼다
  robots: { index: false, follow: false },
  openGraph: { type: "website", siteName: "BASE:ON", locale: "ko_KR", title: "BASE:ON", description: DESCRIPTION },
  formatDetection: { telephone: false, date: false, address: false, email: false }, // 기록 숫자를 전화번호로 잡지 않게
};

export const viewport: Viewport = { themeColor: "#2b63f0" };

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
