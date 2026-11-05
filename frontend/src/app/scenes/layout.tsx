import type { Metadata } from "next";

export const metadata: Metadata = { title: "장면" };

export default function Layout({ children }: LayoutProps<"/scenes">) {
  return children;
}
