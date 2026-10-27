import type { NextConfig } from "next";

// 정적 내보내기 (설계 9장·T11). `npm run build` → out/ 를 Caddy가 그대로 서빙한다.
// 선수 화면은 /players/?id= 쿼리 주소 — 동적 경로는 빌드 때 id를 전부 알아야 해서 쓰지 않는다.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true, // /players/ → out/players/index.html (서버 설정 없이 바로 서빙)
  images: { unoptimized: true }, // 정적 내보내기에는 이미지 최적화 서버가 없다
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
