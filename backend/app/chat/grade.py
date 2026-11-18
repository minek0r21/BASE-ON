"""
챗봇 자동 채점 — tests/chat_questions.csv의 질문을 전부 챗봇에 넣고 맞음/틀림 표를 만든다.
    docker compose exec api python -m app.chat.grade              (한 번씩)
    docker compose exec -e GRADE_REPEAT=3 api python -m app.chat.grade   (세 번 모두 맞아야 맞음 — AI 답은 매번 다를 수 있다)
질문을 추가할 때는 CSV에 한 줄 더 적기만 하면 된다.
  기대메뉴  pa · games · stats · other · chat · 되묻기
  기대조건  "칸=값; 칸=값" (목록은 값 하나만 적어도 포함되면 맞음). 칸 이름은 prompts.PARSE_SCHEMA의 cond 칸
  시즌선택  되묻기가 나오면 대신 고를 시즌 (0 = 전체)
  기대개수  결과 총 개수 (모르면 비움). 숫자는 사이트 API · DB로 확인한 값만 적는다 (other 결과를 정답으로 옮기지 않는다)
  기대값    답 JSON에서 꺼내 볼 값 "경로=값; 경로~글자" (예: record.win=7; pitching.so=108; reason=after_as_of; text~없는 기록)
  앞질문    이어 묻기 시험 — 이 질문을 먼저 보내고, 그 답의 context를 붙여 본 질문을 보낸다
결과는 화면에 찍고 backend/chat_logs/grade_<시각>.csv에도 남긴다. 단계별(메뉴 → 조건 → 개수 · 값)로 어디서 틀렸는지 센다.
호출 제한(limits.py)은 거치지 않는다.
"""
import csv
import json
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from .. import db
from .service import LOG, ChatRequest, answer

CSV = Path(__file__).resolve().parents[2] / "tests" / "chat_questions.csv"


def dig(reply: dict, path: str):
    cur = reply
    for k in path.split("."):  # rows.0.team_score처럼 목록은 번호로
        if isinstance(cur, list) and k.isdigit():
            cur = cur[int(k)] if int(k) < len(cur) else None
        else:
            cur = cur.get(k) if isinstance(cur, dict) else None
    return cur


def same(got, want: str) -> bool:
    if isinstance(got, bool) or got is None:
        return str(got).lower() == want.lower()
    if isinstance(got, (int, float)):
        try:
            return abs(float(got) - float(want)) < 1e-6
        except ValueError:
            return False
    return str(got) == want


def check(row: dict, reply: dict) -> tuple[str | None, str]:
    """(틀린 단계, 이유). 맞으면 (None, "")"""
    if reply.get("error"):
        return "오류", "LLM 오류 (로그 확인)"
    want_menu = row["기대메뉴"].strip()
    if want_menu == "되묻기":
        return (None, "") if reply.get("type") == "clarify" else ("메뉴", "되묻지 않음")
    if reply.get("type") == "clarify":
        return "메뉴", f"되물음({reply.get('slot')})"
    menu = reply.get("menu") or "chat"
    if menu != want_menu:
        return "메뉴", f"메뉴 {menu} (기대 {want_menu})"
    cond = ((reply.get("context") or {}).get("parsed") or {}).get("cond") or {}
    for part in filter(None, (p.strip() for p in row["기대조건"].split(";"))):
        k, _, v = part.partition("=")
        got = cond.get(k.strip())
        ok = (v.strip() in [str(x) for x in got]) if isinstance(got, list) else (str(got) == v.strip())
        if not ok:
            return "조건", f"조건 {k}={got} (기대 {v})"
    if row["기대개수"].strip() and str(reply.get("total")) != row["기대개수"].strip():
        return "개수 · 값", f"개수 {reply.get('total')} (기대 {row['기대개수']})"
    for part in filter(None, (p.strip() for p in (row.get("기대값") or "").split(";"))):
        if "~" in part and ("=" not in part or part.index("~") < part.index("=")):
            k, _, v = part.partition("~")
            if v.strip() not in str(dig(reply, k.strip()) or ""):
                return "개수 · 값", f"{k.strip()}에 「{v.strip()}」 없음"
        else:
            k, _, v = part.partition("=")
            got = dig(reply, k.strip())
            if not same(got, v.strip()):
                return "개수 · 값", f"{k.strip()}={got} (기대 {v.strip()})"
    return None, ""


def ask(row: dict) -> dict:
    context = None
    if (row.get("앞질문") or "").strip():
        first = answer(ChatRequest(message=row["앞질문"]), row["앞질문"])
        context = first.get("context")
    q = row["질문"]
    reply = answer(ChatRequest(message=q, context=context), q)
    pick = row.get("시즌선택", "").strip()
    if reply.get("type") == "clarify" and reply.get("slot") == "season" and pick != "" and row["기대메뉴"] != "되묻기":
        reply = answer(ChatRequest(message=q, context=context, resolved={"season": int(pick)}), q)
    return reply


def main():
    os.environ.setdefault("LLM_RETRIES", "2")  # 채점은 429면 기다렸다 다시 (웹 요청은 0)
    repeat = max(1, int(os.getenv("GRADE_REPEAT", "1")))
    gap = float(os.getenv("GRADE_GAP", "4"))  # 질문 사이 쉬는 초 (1분당 요청 수 때문에)
    db.connect()
    rows = list(csv.DictReader(CSV.open(encoding="utf-8-sig")))
    out, passed, stages = [], 0, Counter()
    for i, row in enumerate(rows, 1):
        fails, reply = [], {}
        for _ in range(repeat):
            time.sleep(gap)
            reply = ask(row)
            stage, why = check(row, reply)
            if stage:
                fails.append((stage, why))
        ok = not fails
        passed += ok
        if fails:
            stages[fails[0][0]] += 1
        why = "" if ok else f"{len(fails)}/{repeat}번 틀림 · {fails[0][1]}"
        print(f"{'O' if ok else 'X'} {i:>3}. {row['질문']}  {why}\n       → {str(reply.get('text', ''))[:90]}")
        out.append({**row, "결과": "O" if ok else "X", "틀린 단계": fails[0][0] if fails else "", "이유": why,
                    "답": reply.get("text", ""), "ms": reply.get("ms", ""),
                    "해석": json.dumps(((reply.get("context") or {}).get("parsed")), ensure_ascii=False)})
    db.close()
    print(f"\n{passed} / {len(rows)} 맞음" + (f" (질문마다 {repeat}번 모두 맞아야 맞음)" if repeat > 1 else ""))
    if stages:
        print("틀린 단계: " + " · ".join(f"{k} {v}" for k, v in stages.most_common()))
    LOG.parent.mkdir(exist_ok=True)
    f = LOG.parent / f"grade_{datetime.now():%Y%m%d_%H%M}.csv"
    with f.open("w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)
    print(f"저장: {f}")


if __name__ == "__main__":
    main()
