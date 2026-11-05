import type { Metadata } from "next";

export const metadata: Metadata = { title: "경기" };

export default function Layout({ children }: LayoutProps<"/games">) {
  return children;
}
