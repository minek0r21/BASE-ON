import type { Metadata } from "next";
import { Wrap } from "@/components/home/common";
import { Empty } from "@/components/ui/Chip";

// 없는 주소 (정적 내보내기 → out/404.html, 서버 Caddy handle_errors 404가 이 파일을 보여 준다). 09 예외 상태: 이유 + 다른 길
export const metadata: Metadata = { title: "없는 화면" };

export default function NotFound() {
  return (
    <Wrap className="pt-10 pb-24">
      <Empty text="찾는 화면이 없어요" sub="주소가 바뀌었거나 잘못 입력됐을 수 있어요."
             actions={[{ label: "홈", href: "/" }, { label: "선수", href: "/rankings/" }, { label: "일정", href: "/schedule/" }]} />
    </Wrap>
  );
}
