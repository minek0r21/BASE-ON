"""
Gemini에 YouTube 영상을 보내 JSON으로 판독 받는 공통 호출기 (docs/장면.md 11장). 09_suggest_times.py · research/video_judge가 쓴다
- 모델: flash 계열만, 최신부터 (lite는 오독이 잦아 뺀다). GEMINI_MODEL="a,b"로 정할 수 있다
- 구간: start_sec·end_sec를 주면 그 구간만 보낸다 (챕터 줄 — 토큰을 아낀다)
- 응답은 out_dir/<key>.json에 저장하고, 있으면 다시 부르지 않는다 → 멈췄다 다시 돌려도 이어서 한다
- 한도 (무료 등급):
    분당 한도(429 + RetryInfo) → 알려 준 시간만큼 기다렸다 같은 모델로
    하루 한도(429, quotaId에 PerDay) → 다음 모델로. 모든 모델이 다 차면 다음 초기화(미국 태평양 자정)까지 기다렸다 처음부터
    과부하(500·503, 「high demand」) → 10초 뒤 한 번 더, 그래도면 그 모델을 뒤로(다음 모델로). 모든 모델이 연달아 과부하면 5분 쉼
      (11-03: 무료 등급에서 최신 flash 둘이 계속 503 · 다음 버전은 바로 응답 → 오래 기다리지 않고 넘긴다)
    결제 잔액 없음(402) → 멈춘다 (모델을 바꿔도 같다)
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

GEM = "https://generativelanguage.googleapis.com/v1beta/"
ROOT = Path(__file__).resolve().parents[1]


def api_key() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    for line in open(ROOT / ".env", encoding="utf-8"):
        k, _, v = line.strip().partition("=")
        if k == "GEMINI_API_KEY" and v:
            return v
    raise SystemExit("GEMINI_API_KEY가 없습니다 (환경변수나 .env)")


def _http(url: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except (urllib.error.URLError, TimeoutError):
        return 503, {}


def flash_models(key: str) -> list[str]:
    if os.environ.get("GEMINI_MODEL"):
        return [m.strip() for m in os.environ["GEMINI_MODEL"].split(",")]
    _, d = _http(GEM + "models?" + urllib.parse.urlencode({"key": key, "pageSize": 200}))
    names = [m["name"].removeprefix("models/") for m in d.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    return sorted((n for n in names if re.fullmatch(r"gemini-\d+(\.\d+)?-flash", n)),
                  key=lambda n: float(n.split("-")[1]), reverse=True)


def next_reset() -> datetime:
    """하루 한도 초기화 = 미국 태평양 자정. 서머타임(3월 둘째 일요일 ~ 11월 첫째 일요일)이면 UTC−7, 아니면 −8"""
    now = datetime.now(timezone.utc)
    y = now.year
    dst_start = datetime(y, 3, 8 + (6 - datetime(y, 3, 8).weekday()) % 7, 10, tzinfo=timezone.utc)
    dst_end = datetime(y, 11, 1 + (6 - datetime(y, 11, 1).weekday()) % 7, 9, tzinfo=timezone.utc)
    off = timedelta(hours=-7 if dst_start <= now < dst_end else -8)
    local = now + off
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - off + timedelta(minutes=2)


def _quota(body: dict) -> tuple[bool, float]:
    """(하루 한도인가, 기다릴 초)"""
    per_day, wait = False, 60.0
    for det in (body.get("error") or {}).get("details", []):
        t = det.get("@type", "")
        if t.endswith("QuotaFailure"):
            per_day = any("PerDay" in v.get("quotaId", "") for v in det.get("violations", []))
        if t.endswith("RetryInfo"):
            m = re.match(r"([\d.]+)s", det.get("retryDelay", ""))
            if m:
                wait = float(m.group(1))
    return per_day, wait


class Judge:
    def __init__(self, out_dir: Path, sleep: float = 6.0, log=print):
        self.key = api_key()
        self.models = flash_models(self.key)
        self.exhausted: set[str] = set()
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.sleep, self.log = sleep, log
        log("모델 순서:", self.models)

    def ask(self, key: str, video_id: str, prompt: str, schema: dict, start_sec: float | None = None,
            end_sec: float | None = None) -> dict:
        p = self.out / f"{key}.json"
        if p.exists():
            return json.load(open(p, encoding="utf-8"))
        part = {"file_data": {"file_uri": f"https://www.youtube.com/watch?v={video_id}"}}
        if start_sec is not None:
            part["video_metadata"] = {"start_offset": f"{int(start_sec)}s", **({"end_offset": f"{int(end_sec)}s"} if end_sec else {})}
        body = {"contents": [{"parts": [part, {"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema, "temperature": 0,
                                     "mediaResolution": os.environ.get("GEMINI_MEDIA_RES", "MEDIA_RESOLUTION_LOW")}}
        busy = 0
        while True:
            live = [m for m in self.models if m not in self.exhausted]
            if not live:
                until = next_reset()
                self.log(f"   모든 모델 하루 한도 → {until.astimezone():%m-%d %H:%M}(이 PC 시각)까지 기다림")
                time.sleep(max(60.0, (until - datetime.now(timezone.utc)).total_seconds()))
                self.exhausted.clear()
                continue
            model, t0 = live[0], time.time()
            st, d = _http(GEM + f"models/{model}:generateContent?key={self.key}", body)
            if st == 200:
                res = {"status": 200, "model": model, "sec": round(time.time() - t0, 1), "body": d}
                json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                time.sleep(self.sleep)
                return res
            if st == 402:
                raise SystemExit("402 결제 잔액 부족: 결제가 연결되지 않은 프로젝트의 키(무료 등급)로 바꿔 주세요")
            if st == 404:
                self.log("  ", model, "404 → 뺌"); self.models.remove(model); continue
            if st == 429:
                per_day, wait = _quota(d)
                if per_day:
                    self.log("  ", model, "하루 한도 → 다음 모델"); self.exhausted.add(model)
                else:
                    self.log("  ", model, f"분당 한도 → {wait:.0f}초 기다림"); time.sleep(wait + 2)
                continue
            if st in (500, 503):
                busy += 1
                if busy % 2:
                    time.sleep(10)
                else:
                    self.log("  ", model, st, "→ 뒤로"); self.models.append(self.models.pop(self.models.index(model)))
                if busy >= 2 * len(live) + 1:
                    self.log("   모든 모델 과부하 → 5분 쉼"); time.sleep(300); busy = 0
                continue
            # 400 등 요청 자체 문제: 저장하지 않고 돌려준다 (예: 비공개·지역 제한 영상)
            return {"status": st, "model": model, "body": d}


def parsed(res: dict) -> dict | None:
    try:
        return json.loads(res["body"]["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        return None


def mmss(s: str | None) -> float | None:
    """「5:11」·「05:11」·「1:02:03」 → 초"""
    if not s or not re.fullmatch(r"\d{1,2}(:\d{2}){1,2}", s.strip()):
        return None
    n = 0
    for x in s.strip().split(":"):
        n = n * 60 + int(x)
    return float(n)
