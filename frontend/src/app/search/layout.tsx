import type { Metadata } from "next";

export const metadata: Metadata = { title: "검색" };

export default function Layout({ children }: LayoutProps<"/search">) {
  return children;
}
