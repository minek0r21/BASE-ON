"""
챗봇 호출 제한 — 공개 사이트에서 AI 비용이 새지 않게 막는다. 메모리에만 센다 (uvicorn --workers 1이라 한 곳에서 센다).
  CHAT_PER_MIN    IP 하나가 1분에 (기본 8 — 질문 하나에 되묻기 1~2번이 붙는다)
  CHAT_PER_DAY    IP 하나가 하루에 (기본 60)
  CHAT_DAILY_CAP  서버 전체 하루 (기본 200) — 남은 예산 ÷ 남은 날 ÷ 질문당 실제 비용으로 정한다
하루는 한국 날짜로 바뀐다. 서버를 다시 켜면 처음부터 센다.
"""
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def _env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


class Limiter:
    def __init__(self, per_min: int | None = None, per_day: int | None = None, daily_cap: int | None = None, clock=time.time):
        self.per_min = per_min if per_min is not None else _env("CHAT_PER_MIN", 8)
        self.per_day = per_day if per_day is not None else _env("CHAT_PER_DAY", 60)
        self.daily_cap = daily_cap if daily_cap is not None else _env("CHAT_DAILY_CAP", 200)
        self.clock = clock
        self.lock = threading.Lock()
        self.day = ""
        self.recent: dict[str, deque] = defaultdict(deque)
        self.today: dict[str, int] = defaultdict(int)
        self.total = 0

    def _roll(self, now: float):
        d = datetime.fromtimestamp(now, KST).date().isoformat()
        if d != self.day:
            self.day, self.today, self.total = d, defaultdict(int), 0
            self.recent.clear()

    def check(self, ip: str) -> str | None:
        """통과면 None, 막히면 이유("minute" · "day" · "cap").
        되묻기 버튼으로 다시 보낸 질문도 AI를 부르니 똑같이 센다 (빼 주면 한 IP가 그 길로 서버 하루 몫을 다 쓸 수 있다)"""
        now = self.clock()
        with self.lock:
            self._roll(now)
            if self.total >= self.daily_cap:
                return "cap"
            q = self.recent[ip]
            while q and now - q[0] >= 60:
                q.popleft()
            if len(q) >= self.per_min:
                return "minute"
            if self.today[ip] >= self.per_day:
                return "day"
            q.append(now)
            self.today[ip] += 1
            self.total += 1
            return None


MESSAGE = {
    "minute": "질문이 너무 빨라요. 1분 뒤에 다시 물어봐 주세요.",
    "day": "오늘 물어볼 수 있는 만큼 다 물어봤어요. 내일 다시 와 주세요.",
    "cap": "오늘 챗봇 사용량이 다 찼어요. 내일 다시 와 주세요.",
}

limiter = Limiter()
