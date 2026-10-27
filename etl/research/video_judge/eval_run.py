"""
영상 판독 매칭 시험 (보류 — docs/장면.md 11장). 오매칭 자동 검수 가능성 시험 — 표본 40개 (자동 확정 24 · 검수 대기 12 · 경기 하이라이트 4)
  python eval_run.py captions   YouTube captions.list : 자동 자막(asr) 트랙이 있는지 (키 필요, 영상당 50 units)
  python eval_run.py comments   YouTube commentThreads.list : 타임스탬프 댓글 (키 필요, 영상당 1 unit)
  python eval_run.py gemini     Gemini에 YouTube URL을 넘겨 홈런 장면 판독 (GEMINI_API_KEY 필요)
  python eval_run.py score      저장된 응답으로 채점
키: 환경변수 또는 저장소 맨 위 .env 의 YOUTUBE_API_KEY · GEMINI_API_KEY (GEMINI_MODEL로 모델 지정 가능)
응답은 eval_out/<시험>/<video_id>.json 에 저장하고, 있으면 다시 부르지 않는다.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[2]  # 저장소 루트 (.env)
TRUTH = json.load(open(HERE / "_eval_truth.json", encoding="utf-8"))
OUT = HERE / "eval_out"


def key(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    for line in open(LAB / ".env", encoding="utf-8"):
        k, _, v = line.strip().partition("=")
        if k == name and v:
            return v
    raise SystemExit(f"{name}가 없습니다 (환경변수나 저장소 맨 위 .env)")


def http(url: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def cached(test: str, vid: str, fetch):
    p = OUT / test / f"{vid}.json"
    if p.exists():
        return json.load(open(p, encoding="utf-8"))
    p.parent.mkdir(parents=True, exist_ok=True)
    res = fetch()
    if res.get("status") != 200:  # 실패(한도·결제 등)는 저장하지 않고 다음에 다시 부른다
        return res
    json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return res


# ------------------------------------------------------------------ YouTube
YT = "https://www.googleapis.com/youtube/v3/"


def run_captions():
    k = key("YOUTUBE_API_KEY")
    for t in TRUTH:
        def fetch():
            st, d = http(YT + "captions?" + urllib.parse.urlencode({"part": "snippet", "videoId": t["video_id"], "key": k}))
            return {"status": st, "body": d}
        r = cached("captions", t["video_id"], fetch)
        print(t["video_id"], r["status"], [(i["snippet"]["language"], i["snippet"]["trackKind"]) for i in r["body"].get("items", [])],
              (r["body"].get("error") or {}).get("message", "")[:100])


def run_comments():
    k = key("YOUTUBE_API_KEY")
    for t in TRUTH:
        def fetch():
            st, d = http(YT + "commentThreads?" + urllib.parse.urlencode({
                "part": "snippet", "videoId": t["video_id"], "maxResults": 100, "order": "relevance",
                "textFormat": "plainText", "key": k}))
            return {"status": st, "body": d}
        r = cached("comments", t["video_id"], fetch)
        print(t["video_id"], r["status"], len(r["body"].get("items", [])))


# ------------------------------------------------------------------ Gemini
GEM = "https://generativelanguage.googleapis.com/v1beta/"
PROMPT = """이 영상은 KBO(한국 프로야구) 영상입니다. 영상에 나오는 홈런 장면을 모두 찾아 주세요.
화면(중계 점수판, 자막 그래픽, 유니폼 이름·등번호)과 음성(중계 해설)에서 실제로 보이거나 들린 것만 적고,
보이지 않으면 null로 두세요. 제목이나 상식으로 추측하지 마세요.
각 홈런마다:
- batter: 홈런 친 타자 이름 (한글)
- batter_evidence: 이름을 어디서 확인했는지 목록 (scoreboard, caption, commentary, jersey 중)
- team: 타자 팀
- season_hr_no: 「시즌 N호」처럼 화면이나 해설에 나온 시즌 홈런 번호
- inning, half: 이닝 숫자와 초/말 (점수판·자막·해설 근거)
- score_after: 홈런 직후 점수 {away_team, away, home_team, home} — 점수판·자막에 보인 값
- pitcher: 상대 투수 이름 (점수판 P. 표시나 해설)
- date_text: 화면에 날짜가 나오면 그대로
- t_sec: 영상 안에서 타격 순간의 시각 (초)
- confidence: 0~1"""
SCHEMA = {
    "type": "OBJECT",
    "properties": {"home_runs": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "batter": {"type": "STRING", "nullable": True},
        "batter_evidence": {"type": "ARRAY", "items": {"type": "STRING"}},
        "team": {"type": "STRING", "nullable": True},
        "season_hr_no": {"type": "INTEGER", "nullable": True},
        "inning": {"type": "INTEGER", "nullable": True},
        "half": {"type": "STRING", "nullable": True},
        "score_after": {"type": "OBJECT", "nullable": True, "properties": {
            "away_team": {"type": "STRING", "nullable": True}, "away": {"type": "INTEGER", "nullable": True},
            "home_team": {"type": "STRING", "nullable": True}, "home": {"type": "INTEGER", "nullable": True}}},
        "pitcher": {"type": "STRING", "nullable": True},
        "date_text": {"type": "STRING", "nullable": True},
        "t_sec": {"type": "NUMBER", "nullable": True},
        "confidence": {"type": "NUMBER"},
    }}}},
}


def gemini_models(k: str) -> list[str]:
    """무료 등급으로 시도할 모델 순서: GEMINI_MODEL(쉼표로 여럿) > flash(최신순) > flash-lite(최신순).
    무료 등급은 모델마다 하루·분당 한도가 따로라서, 한도(429)에 걸리면 다음 모델로 넘어간다"""
    if os.environ.get("GEMINI_MODEL"):
        return [m.strip() for m in os.environ["GEMINI_MODEL"].split(",")]
    st, d = http(GEM + "models?" + urllib.parse.urlencode({"key": k, "pageSize": 200}))
    names = [m["name"].removeprefix("models/") for m in d.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    ver = lambda n: float(n.split("-")[1])
    flash = sorted((n for n in names if re.fullmatch(r"gemini-\d+(\.\d+)?-flash", n)), key=ver, reverse=True)
    lite = sorted((n for n in names if re.fullmatch(r"gemini-\d+(\.\d+)?-flash-lite", n)), key=ver, reverse=True)
    return flash + lite


SLEEP = float(os.environ.get("GEMINI_SLEEP", 15))  # 무료 등급 분당 요청 한도 대비 호출 간격 (초)


def run_gemini():
    k = key("GEMINI_API_KEY")
    models = gemini_models(k)
    print("모델 순서:", models)
    for t in TRUTH:
        def fetch():
            busy = 0
            while models:
                model, t0 = models[0], time.time()
                st, d = http(GEM + f"models/{model}:generateContent?key={k}", {
                    "contents": [{"parts": [{"file_data": {"file_uri": f"https://www.youtube.com/watch?v={t['video_id']}"}},
                                            {"text": PROMPT}]}],
                    # 낮은 해상도: 무료 등급 토큰 한도를 덜 쓴다 (점수판·자막 글씨가 읽히는지도 이 시험에서 본다)
                    "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0,
                                         "mediaResolution": os.environ.get("GEMINI_MEDIA_RES", "MEDIA_RESOLUTION_LOW")},
                })
                time.sleep(SLEEP)
                if st == 402:  # 결제 연결 프로젝트의 잔액 부족 — 모델을 바꿔도 같으므로 멈춘다
                    raise SystemExit("402 결제 잔액 부족: 결제가 연결되지 않은 프로젝트의 키(무료 등급)로 바꿔 주세요")
                if st in (404, 429):  # 없는 모델 · 그 모델 무료 한도 소진 → 다음 모델
                    print("  ", model, st, "→ 다음 모델"); models.pop(0); continue
                if st in (500, 503):  # 일시적 과부하: 30초 뒤 한 번 더, 그래도면 이 모델을 뒤로 돌린다
                    busy += 1
                    if busy > 2 * len(models):
                        raise SystemExit("모든 모델이 과부하입니다. 잠시 뒤 다시 돌려 주세요")
                    if busy % 2:
                        time.sleep(30)
                    else:
                        print("  ", model, st, "→ 뒤로"); models.append(models.pop(0))
                    continue
                return {"status": st, "model": model, "sec": round(time.time() - t0, 1), "body": d}
            raise SystemExit("모든 모델의 무료 한도를 다 썼습니다. 내일 다시 돌리면 이어서 합니다")
        r = cached("gemini", t["video_id"], fetch)
        u = r["body"].get("usageMetadata", {})
        print(t["video_id"], t["group"], r.get("model"), r["status"], r["sec"], "s", u.get("promptTokenCount"), "tok",
              (r["body"].get("error") or {}).get("message", "")[:100])


# ------------------------------------------------------------------ 채점
RE_TS = re.compile(r"(?<!\d)(\d{1,2}):([0-5]\d)(?!\d)")


def given(name: str) -> str:
    return name[1:] if len(name) == 3 else name


def name_hit(said: str | None, real: str) -> bool:
    return bool(said) and (real in said or said in real or given(real) in said)


def judge(hr: dict, pa: dict) -> str:
    """판독 홈런 하나 vs 기록 타석 하나 → 'match'(독립 근거 일치) / 'conflict' / 'name_only' / 'other'"""
    if not name_hit(hr.get("batter"), pa["batter"]):
        return "other"
    checks = []
    if hr.get("season_hr_no") is not None:
        checks.append(hr["season_hr_no"] == pa["hr_seq"])
    if hr.get("inning") is not None:
        half = {"t": "초", "b": "말"}.get((hr.get("half") or "")[:1].lower(), (hr.get("half") or "")[:1])
        checks.append(hr["inning"] == pa["inning"] and (not half or half == pa["half"][:1]))
    sa = hr.get("score_after") or {}
    if sa.get("away") is not None and sa.get("home") is not None:
        # 중계사마다 원정·홈 순서가 달라서 두 순서 모두 허용 (팀 이름이 있으면 그걸로 맞춤)
        ok = {(sa["away"], sa["home"]), (sa["home"], sa["away"])}
        if sa.get("away_team") and pa["home"] in sa["away_team"]:
            ok = {(sa["home"], sa["away"])}
        checks.append((pa["away_post"], pa["home_post"]) in ok)
    if not checks:
        return "name_only"
    return "match" if all(checks) else "conflict"


def score():
    rows = []
    for t in TRUTH:
        vid, group = t["video_id"], t["group"]
        row = {"video_id": vid, "group": group, "sec": t["sec"], "channel": t["channel"]}
        p = OUT / "captions" / f"{vid}.json"
        if p.exists():
            c = json.load(open(p, encoding="utf-8"))
            items = c["body"].get("items", []) if c["status"] == 200 else None
            row["captions"] = "error %s" % c["status"] if items is None else \
                ",".join(f"{i['snippet']['language']}:{i['snippet']['trackKind']}" for i in items) or "none"
        p = OUT / "comments" / f"{vid}.json"
        if p.exists():
            c = json.load(open(p, encoding="utf-8"))
            texts = [i["snippet"]["topLevelComment"]["snippet"]["textDisplay"] for i in c["body"].get("items", [])]
            ts = [x for x in texts if RE_TS.search(x)]
            names = {h["batter"] for h in t["game_hrs"]}
            row["comments"] = len(texts) if c["status"] == 200 else f"error {c['status']}"
            row["ts_comments"] = len(ts)
            row["ts_with_hr_name"] = sum(any(n in x or given(n) in x for n in names) for x in ts)
        p = OUT / "gemini" / f"{vid}.json"
        if p.exists():
            g = json.load(open(p, encoding="utf-8"))
            u = g["body"].get("usageMetadata", {})
            row["tokens"] = u.get("promptTokenCount")
            try:
                hrs = json.loads(g["body"]["candidates"][0]["content"]["parts"][0]["text"])["home_runs"]
            except Exception:
                row["gemini"] = f"error {g['status']}"
                rows.append(row)
                continue
            row["found"] = len(hrs)
            linked = {l["pa_id"] for l in t["links"]}
            game = {h["pa_id"]: h for h in t["game_hrs"]}
            if group == "game_highlight":
                hit = {pid for pid, pa in game.items() if any(judge(h, pa) in ("match", "name_only") for h in hrs)}
                row["gemini"] = f"경기 홈런 {len(game)}개 중 {len(hit)}개 찾음"
                row["conflicts"] = sum(any(judge(h, pa) == "conflict" for pa in game.values()) and
                                       not any(judge(h, pa) == "match" for pa in game.values()) for h in hrs)
                row["t_secs"] = [(h.get("batter"), h.get("inning"), h.get("t_sec")) for h in hrs]
            else:
                verdicts = {pid: max((judge(h, game[pid]) for h in hrs), key=["other", "name_only", "conflict", "match"].index,
                                     default="other") for pid in linked if pid in game}
                if any(v == "match" for v in verdicts.values()):
                    m = [pid for pid, v in verdicts.items() if v == "match"]
                    row["gemini"] = "일치" if len(m) == 1 or group == "auto" else f"일치 여럿 {m}"
                    row["picked"] = m
                elif any(v == "conflict" for v in verdicts.values()):
                    row["gemini"] = "모순"
                elif any(v == "name_only" for v in verdicts.values()):
                    row["gemini"] = "이름만"
                else:
                    row["gemini"] = "증거 없음" if not hrs else "다른 홈런"
                row["detail"] = [{k: h.get(k) for k in ("batter", "batter_evidence", "season_hr_no", "inning", "half",
                                                        "score_after", "date_text", "t_sec")} for h in hrs]
        rows.append(row)
    json.dump(rows, open(HERE / "eval_score.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for r in rows:
        print({k: v for k, v in r.items() if k != "detail"})


STRONG = ("시즌 n호", "점수(값)", "화면 날짜")  # 제목 신호와 독립인 근거. 초·말은 오독이 잦아 판정에 쓰지 않는다


def date_hit(txt: str | None, date: str):
    """화면 날짜의 월·일만 비교 (연도는 「26」을 「24」로 읽는 오독이 있었다)"""
    if not txt:
        return None
    nums = [int(x) for x in re.findall(r"\d+", txt)]
    if len(nums) >= 3 and nums[0] > 12:  # 26. 5. 7. 같이 연도가 앞에
        nums = nums[1:]
    return nums[:2] == [int(date[5:7]), int(date[8:10])] if len(nums) >= 2 else None


def score2():
    """클립 판정: 독립 근거가 2개 이상 맞으면 자동 승인 후보, 하나라도 어긋나면 사람에게 (docs/장면.md 11장)"""
    import collections
    field = collections.defaultdict(lambda: [0, 0])
    rows = collections.Counter()
    for t in TRUTH:
        p = OUT / "gemini" / f"{t['video_id']}.json"
        if t["group"] == "game_highlight" or not p.exists():
            continue
        g = json.load(open(p, encoding="utf-8"))
        hrs = json.loads(g["body"]["candidates"][0]["content"]["parts"][0]["text"])["home_runs"]
        linked = {l["pa_id"] for l in t["links"]}
        best = None
        for pa in (h for h in t["game_hrs"] if h["pa_id"] in linked):
            for h in hrs:
                if not name_hit(h.get("batter"), pa["batter"]):
                    continue
                res = {}
                if h.get("season_hr_no") is not None:
                    res["시즌 n호"] = h["season_hr_no"] == pa["hr_seq"]
                if h.get("inning") is not None:
                    res["이닝"] = h["inning"] == pa["inning"]
                half = {"t": "초", "b": "말"}.get((h.get("half") or "")[:1].lower(), (h.get("half") or "")[:1])
                if half:
                    res["초·말"] = half == pa["half"][:1]
                sa = h.get("score_after") or {}
                if sa.get("away") is not None and sa.get("home") is not None:  # 원정·홈을 뒤바꿔 적기도 해서 두 값 묶음으로
                    res["점수(값)"] = sorted([sa["away"], sa["home"]]) == sorted([pa["away_post"], pa["home_post"]])
                d = date_hit(h.get("date_text"), pa["date"])
                if d is not None:
                    res["화면 날짜"] = d
                ok = sum(v for k, v in res.items() if k in STRONG)
                bad = sum(not v for k, v in res.items() if k in STRONG)
                if best is None or (ok, -bad) > (best[0], -best[1]):
                    best = (ok, bad, res)
        if best is None:
            verdict = "이름 못 찾음"
        else:
            ok, bad, res = best
            for k, v in res.items():
                field[k][0 if v else 1] += 1
            verdict = "근거 충돌" if bad else ("일치 · 근거 2개+" if ok >= 2 else ("일치 · 근거 1개" if ok else "이름만"))
        rows[(t["group"].split(":")[0], verdict)] += 1
    for k in sorted(rows):
        print(k, rows[k])
    for k, (a, b) in field.items():
        print(f"{k}: {a}/{a + b}")


if __name__ == "__main__":
    {"captions": run_captions, "comments": run_comments, "gemini": run_gemini, "score": score, "score2": score2}[sys.argv[1]]()
