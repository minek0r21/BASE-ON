import type { Metadata } from "next";

export const metadata: Metadata = { title: "팀" };

export default function Layout({ children }: LayoutProps<"/teams">) {
  return children;
}
