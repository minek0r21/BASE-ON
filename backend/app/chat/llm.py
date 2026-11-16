"""
LLM 연결부 — 질문 이해(와 로컬 전용 other의 Cypher 작성)에 쓰는 LLM을 한 곳에서 부른다.
.env 로 고른다 (코드 수정 없이 바꿀 수 있다):
    LLM_PROVIDER=gemini   GEMINI_API_KEY=...      (LLM_MODEL 생략 시 아래 기본값)
    LLM_PROVIDER=claude   ANTHROPIC_API_KEY=...
새 패키지 없이 표준 라이브러리(urllib)로 REST API를 부른다. 키는 로그에 남기지 않는다.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

DEFAULT_MODEL = {"gemini": "gemini-3.5-flash-lite", "claude": "claude-haiku-4-5-20251001"}
TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))     # 초. 웹 요청이라 오래 붙잡지 않는다
THINKING = os.getenv("LLM_THINKING", "minimal")   # Gemini 생각 수준 (minimal · low · medium · high). 질문 해석은 minimal로 충분 (빠르고 싸다)


class LLMError(Exception):
    pass


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "gemini").strip().lower()


def ready() -> bool:  # 키가 들어 있는가
    return bool(os.getenv("GEMINI_API_KEY" if provider() == "gemini" else "ANTHROPIC_API_KEY"))


def retries() -> int:
    """429(1분당 요청 수)에 걸렸을 때 기다렸다 다시 묻는 횟수. 웹 요청은 0 — 사용자를 40초씩 붙잡지 않는다. 채점(grade.py)만 2"""
    try:
        return int(os.getenv("LLM_RETRIES", "0"))
    except ValueError:
        return 0


def _post(url: str, body: dict, headers: dict) -> dict:
    n = retries()
    for attempt in range(n + 1):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if e.code == 429 and attempt < n:
                m = re.search(r'"retryDelay":\s*"(\d+)', text)  # 구글이 알려 주는 기다릴 시간
                time.sleep(min(int(m.group(1)) + 1 if m else 20, 40))
                continue
            raise LLMError(f"LLM 오류 {e.code}: {text[:300]}") from None
        except OSError as e:
            raise LLMError(f"LLM 연결 실패: {e}") from None


def complete(system: str, user: str, as_json: bool = False) -> str:
    """system(규칙) + user(질문) → 답 문자열. as_json이면 JSON 하나만 돌려 달라고 한다"""
    p = provider()
    model = os.getenv("LLM_MODEL") or DEFAULT_MODEL.get(p, "")
    if p == "gemini":
        key = os.getenv("GEMINI_API_KEY") or ""
        if not key:
            raise LLMError("GEMINI_API_KEY가 .env에 없어요")
        cfg: dict = {"temperature": 0}
        if as_json:
            cfg["responseMimeType"] = "application/json"
        if THINKING:
            cfg["thinkingConfig"] = {"thinkingLevel": THINKING}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": cfg}
        try:
            res = _post(url, body, {"x-goog-api-key": key})
        except LLMError as e:  # 생각 수준을 모르는 모델이면 빼고 한 번 더
            msg = str(e).lower()
            if "400" not in msg or "thinking" not in msg:
                raise
            body["generationConfig"] = {k: v for k, v in cfg.items() if k != "thinkingConfig"}
            res = _post(url, body, {"x-goog-api-key": key})
        try:
            return "".join(part.get("text", "") for part in res["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            raise LLMError(f"LLM 응답을 읽지 못했어요: {str(res)[:200]}") from None
    if p == "claude":
        key = os.getenv("ANTHROPIC_API_KEY") or ""
        if not key:
            raise LLMError("ANTHROPIC_API_KEY가 .env에 없어요")
        sys_text = system + ("\n\n반드시 JSON 객체 하나만 출력하라. 설명이나 코드블록 없이." if as_json else "")
        res = _post("https://api.anthropic.com/v1/messages",
                    {"model": model, "max_tokens": 1500, "temperature": 0, "system": sys_text,
                     "messages": [{"role": "user", "content": user}]},
                    {"x-api-key": key, "anthropic-version": "2023-06-01"})
        return "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
    raise LLMError(f"모르는 LLM_PROVIDER: {p}")


def parse_json(text: str) -> dict | None:
    """앞뒤에 글자가 붙어 와도 가장 바깥 {...}만 꺼낸다. 못 읽으면 None"""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    for s in (text, (re.search(r"\{.*\}", text, flags=re.S) or [""])[0]):
        try:
            v = json.loads(s)
            return v if isinstance(v, dict) else None
        except ValueError:
            continue
    return None


def complete_json(system: str, user: str) -> dict:
    """JSON 답을 dict로. 깨진 JSON이 오면(드물게 글자 코드가 잘린다) 한 번만 다시 묻는다"""
    for _ in range(2):
        text = complete(system, user, as_json=True)
        if (v := parse_json(text)) is not None:
            return v
    raise LLMError(f"LLM이 JSON이 아닌 답을 보냈어요: {text.strip()[:200]}")
