"""
챗봇 자동 채점 — tests/chat_questions.csv의 질문을 전부 챗봇에 넣고 맞음/틀림 표를 만든다.
    docker compose exec api python -m app.chat.grade
질문을 추가할 때는 CSV에 한 줄 더 적기만 하면 된다.
  기대메뉴  pa · games · stats · other · chat · 되묻기
  기대조건  "칸=값; 칸=값" (목록은 값 하나만 적어도 포함되면 맞음). 칸 이름은 prompts.py의 cond 칸
  시즌선택  되묻기가 나오면 대신 고를 시즌 (0 = 전체)
  기대개수  결과 총 개수 (모르면 비움)
결과는 화면에 찍고 backend/chat_logs/grade_<시각>.csv에도 남긴다.
"""
import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

from .. import db
from .service import LOG, ChatRequest, chat

CSV = Path(__file__).resolve().parents[2] / "tests" / "chat_questions.csv"


def check(row: dict, reply: dict) -> tuple[bool, str]:
    if reply.get("error"):
        return False, "LLM 오류 (로그 확인)"
    want_menu = row["기대메뉴"].strip()
    if want_menu == "되묻기":
        return reply.get("type") == "clarify", f"되묻기 {reply.get('slot')}" if reply.get("type") == "clarify" else "되묻지 않음"
    if reply.get("type") == "clarify":
        return False, f"되물음({reply.get('slot')})"
    menu = reply.get("menu") or "chat"
    if menu != want_menu:
        return False, f"메뉴 {menu} (기대 {want_menu})"
    cond = ((reply.get("context") or {}).get("parsed") or {}).get("cond") or {}
    for part in filter(None, (p.strip() for p in row["기대조건"].split(";"))):
        k, _, v = part.partition("=")
        got = cond.get(k.strip())
        ok = (v.strip() in [str(x) for x in got]) if isinstance(got, list) else (str(got) == v.strip())
        if not ok:
            return False, f"조건 {k}={got} (기대 {v})"
    if row["기대개수"].strip() and str(reply.get("total")) != row["기대개수"].strip():
        return False, f"개수 {reply.get('total')} (기대 {row['기대개수']})"
    return True, ""


def main():
    db.connect()
    rows = list(csv.DictReader(CSV.open(encoding="utf-8-sig")))
    out, passed = [], 0
    gap = float(os.getenv("GRADE_GAP", "4"))  # 질문 사이 쉬는 초 (무료 사용량의 1분당 요청 수 때문에)
    for i, row in enumerate(rows, 1):
        if i > 1:
            time.sleep(gap)
        q = row["질문"]
        reply = chat(ChatRequest(message=q))
        pick = row.get("시즌선택", "").strip()
        if reply.get("type") == "clarify" and reply.get("slot") == "season" and pick != "" and row["기대메뉴"] != "되묻기":
            reply = chat(ChatRequest(message=q, resolved={"season": int(pick)}))
        ok, why = check(row, reply)
        passed += ok
        print(f"{'O' if ok else 'X'} {i:>2}. {q}  {why}\n      → {str(reply.get('text', ''))[:90]}")
        out.append({**row, "결과": "O" if ok else "X", "이유": why, "답": reply.get("text", ""),
                    "해석": json.dumps(((reply.get("context") or {}).get("parsed")), ensure_ascii=False), "ms": reply.get("ms", "")})
    db.close()
    print(f"\n{passed} / {len(rows)} 맞음")
    LOG.parent.mkdir(exist_ok=True)
    f = LOG.parent / f"grade_{datetime.now():%Y%m%d_%H%M}.csv"
    with f.open("w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)
    print(f"저장: {f}")


if __name__ == "__main__":
    main()
