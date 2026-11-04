import type { MetadataRoute } from "next";

// robots.txt (정적 내보내기 → out/robots.txt). 시험 서비스라 전부 막는다 — 공개로 바꾸면 layout.tsx robots와 같이 바꾼다
export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return { rules: { userAgent: "*", disallow: "/" } };
}
