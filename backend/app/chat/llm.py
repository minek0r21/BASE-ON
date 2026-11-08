"""
LLM 연결부 — 질문 이해 · 요약 · Cypher 작성에 쓰는 LLM을 한 곳에서 부른다.
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
TIMEOUT = int(os.getenv("LLM_TIMEOUT", "90"))  # 초. 생각하는 모델은 느릴 수 있다
THINKING = os.getenv("LLM_THINKING", "low")     # Gemini 생각 수준 (low · medium · high). 질문 해석은 low로 충분


class LLMError(Exception):
    pass


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "gemini").strip().lower()


def ready() -> bool:  # 키가 들어 있는가
    return bool(os.getenv("GEMINI_API_KEY" if provider() == "gemini" else "ANTHROPIC_API_KEY"))


RETRIES = 2  # 무료 사용량의 「1분당 요청 수」에 걸리면(429) 잠깐 기다렸다 다시


def _post(url: str, body: dict, headers: dict) -> dict:
    for attempt in range(RETRIES + 1):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if e.code == 429 and attempt < RETRIES:
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
        cfg = {"temperature": 0}
        if as_json:
            cfg["responseMimeType"] = "application/json"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": cfg | ({"thinkingConfig": {"thinkingLevel": THINKING}} if THINKING else {})}
        try:
            res = _post(url, body, {"x-goog-api-key": key})
        except LLMError as e:  # 생각 수준을 모르는 모델이면 빼고 한 번 더
            if "400" not in str(e) or "thinking" not in str(e).lower():
                raise
            body["generationConfig"] = cfg
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


def complete_json(system: str, user: str) -> dict:
    """JSON 답을 dict로. 앞뒤에 글자가 붙어 와도 가장 바깥 {...}만 꺼낸다"""
    text = complete(system, user, as_json=True).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    raise LLMError(f"LLM이 JSON이 아닌 답을 보냈어요: {text[:200]}")
