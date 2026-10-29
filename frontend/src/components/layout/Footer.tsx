import { Logo } from "./Nav";

// 출처 고지 (NFR-02 · 팀 문서 「데이터_이용.md」): 데이터 출처와 원천 정보 제공처를 따로 적는다
export default function Footer() {
  return (
    <footer className="mt-24 border-t border-line bg-raised">
      <div className="mx-auto max-w-[1200px] px-4 py-14 xl:px-0">
        <div className="grid gap-10 md:grid-cols-[1fr_auto_auto]">
          <div>
            <Logo />
            <p className="mt-4 text-[13px] leading-relaxed text-fg-2">
              기록에서 장면으로.
              <br />
              KBO 입문 팬을 위한 기록 해석 · 장면 연결 서비스
            </p>
          </div>
          <div className="text-[13px] leading-7 text-fg-2">
            <p className="mb-1 font-bold text-fg">데이터 출처</p>
            <p>경기 기록 · Hugging Face slothman3878/kbo_playbyplay (CC BY 4.0 · 리비전 6afc8af 고정)</p>
            <p>원천 정보 · NAVER Sports 문자중계 (원문은 저장 · 공개하지 않음)</p>
            <p>선수 프로필 · 위키백과 (CC BY-SA 4.0)</p>
            <p>영상 · KBO · 구단 공식 YouTube 임베드</p>
            <p>선수 사진 · 구단 엠블럼 · KBO 공식 사이트</p>
          </div>
        </div>
        <p className="mt-10 border-t border-line pt-6 text-xs leading-relaxed text-muted">
          BASE:ON은 KBO · NAVER · 각 구단의 공식 서비스가 아니며 제휴 관계가 없는 비상업 수업 프로젝트입니다. 영상은 각 채널이 올린 원본을
          그대로 재생하며 저장하지 않습니다.
        </p>
      </div>
    </footer>
  );
}
