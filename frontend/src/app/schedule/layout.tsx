import type { Metadata } from "next";

export const metadata: Metadata = { title: "일정" };

export default function Layout({ children }: LayoutProps<"/schedule">) {
  return children;
}
