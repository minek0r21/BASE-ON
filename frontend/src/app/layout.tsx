import type { Metadata } from "next";
import Link from "next/link";
import SearchBox from "@/components/SearchBox";
import Providers from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "BASE:ON",
  description: "KBO 타자 기록과 장면을 한 번에",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <Providers>
          <header className="sticky top-0 z-20 border-b border-line bg-surface/90 backdrop-blur">
            <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
              <Link href="/" className="shrink-0 text-lg font-extrabold tracking-tight">
                BASE<span className="text-accent">:</span>ON
              </Link>
              <div className="min-w-0 flex-1">
                <SearchBox />
              </div>
              {/* 기준일: API-20(/meta) 생기면 여기에 (설계 9장 공통) */}
            </div>
          </header>

          <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>

          {/* 출처 고지 (NFR-02) */}
          <footer className="border-t border-line py-6 text-xs leading-relaxed text-muted">
            <div className="mx-auto max-w-5xl px-4">
              <p>
                경기 기록: Hugging Face slothman3878/kbo_playbyplay (CC BY 4.0 · 리비전 6afc8af 고정) · 원천 정보: NAVER
                Sports 문자중계 (원문은 저장·공개하지 않음)
              </p>
              <p>선수 프로필 일부: 위키백과 (CC BY-SA 4.0) · 영상: KBO·구단 공식 YouTube 임베드</p>
              <p>BASE:ON은 KBO·NAVER·각 구단의 공식 서비스가 아니며 제휴 관계가 없는 비상업 수업 프로젝트입니다.</p>
            </div>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
