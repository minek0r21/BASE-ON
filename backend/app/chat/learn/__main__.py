"""
챗봇 학습 순환 (로컬 전용). 서버 · 등록부는 건드리지 않고, 결과는 backend/chat_logs/learn/<run>/ 에만 쓴다.

    docker compose exec api python -m app.chat.learn run --family rank --n 10     질문 만들기 → 이해 → 후보 → 검사 → 검토 목록
    docker compose exec api python -m app.chat.learn promote <run 폴더 이름>       review.csv에서 승인(O)한 질문 → 채점 질문
    docker compose exec api python -m app.chat.learn collect                      못 답한 질문 기록 → 갈래별 개수

AI 호출: 질문 n개면 1(문장 만들기) + n(이해) + 3n(후보) 번. 실행 끝에 호출 수를 찍는다 — 비용은 AI Studio 콘솔로 확인.
"""
import argparse
import sys
from collections import Counter

from ... import db
from . import steps
from .families import FAMILIES


def run(fam_id: str, n: int, seed: int):
    fam = FAMILIES[fam_id]
    day = steps.as_of_now()
    run_dir = steps.new_run(fam_id)
    items = steps.generate(fam, n, seed)
    steps.save(run_dir, items)
    for i, it in enumerate(items, 1):
        try:
            steps.understand(it, fam, day)
            steps.candidates(it)
            steps.check(it, fam)
        except steps.llm.LLMError as e:
            it["error"] = str(e)[:300]
        steps.save(run_dir, items)  # 중간에 멈춰도 여기까지는 남는다
        print(f"{i:>3}. {steps.MARK.get(it.get('verdict'), '?')} {'이해O' if it.get('understood') else '이해X'} "
              f"blind={it.get('blind')} {it['question']}")
    steps.review(run_dir, items)
    v = Counter(it.get("verdict") for it in items)
    fg = sum(1 for it in items if it.get("false_green"))
    blind_pass = sum(1 for it in items if it.get("blind") == "pass")
    print(f"\n질문 이해 맞음 {sum(1 for it in items if it.get('understood'))}/{len(items)}"
          f" · 판정 🟢{v.get('green', 0)} 🟡{v.get('yellow', 0)} 🔴{v.get('red', 0)}"
          f" · blind 통과 {blind_pass} 중 정답과 틀림(false_green) {fg}")
    print(f"AI 호출 {steps.CALLS['n']}번 · 검토 목록: {run_dir / 'review.md'}")


def main():
    ap = argparse.ArgumentParser(prog="python -m app.chat.learn")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--family", default="rank", choices=list(FAMILIES))
    r.add_argument("--n", type=int, default=10)
    r.add_argument("--seed", type=int, default=1)
    p = sub.add_parser("promote")
    p.add_argument("run")
    sub.add_parser("collect")
    a = ap.parse_args()

    db.connect()
    try:
        if a.cmd == "run":
            run(a.family, a.n, a.seed)
        elif a.cmd == "promote":
            print(f"채점 질문 {steps.promote(steps.ROOT / a.run)}개 추가 → 다음은 grade --gate")
        else:
            got = steps.collect()
            if not got:
                print("기록 없음")
            for reason, xs in sorted(got.items(), key=lambda kv: -len(kv[1])):
                print(f"{len(xs):>4}  {reason:<18} {steps.BUCKET.get(reason, '')}")
                for x in xs[:3]:
                    print(f"        · {x.get('q')}")
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
