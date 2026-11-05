import type { Metadata } from "next";

export const metadata: Metadata = { title: "선수 비교" };

export default function Layout({ children }: LayoutProps<"/compare">) {
  return children;
}
