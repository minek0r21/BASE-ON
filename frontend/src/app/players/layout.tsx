import type { Metadata } from "next";

export const metadata: Metadata = { title: "선수" };

export default function Layout({ children }: LayoutProps<"/players">) {
  return children;
}
