"""
2차 시험 (10-21) — 안타 검수 대기 · 투수 클립 검수 대기 · 챕터 구간. docs/장면.md 11장
  python pilot2.py run     판독 (응답은 pilot2_out/에 저장, 한도에 걸리면 기다렸다 이어서)
  python pilot2.py score   채점
표본·정답표: pilot2_truth.py (etl 컨테이너)
"""
import collections
import json
import re
import sys
from pathlib import Path

from gemini import Judge, mmss, parsed

HERE = Path(__file__).resolve().parent
TRUTH = json.load(open(HERE / "pilot2_truth.json", encoding="utf-8"))
OUT = HERE / "pilot2_out"

S = lambda **p: {"type": "OBJECT", "properties": p}  # noqa: E731
STR, INT = {"type": "STRING", "nullable": True}, {"type": "INTEGER", "nullable": True}
SCORE = {**S(away_team=STR, away=INT, home_team=STR, home=INT), "nullable": True}
COMMON = ("화면(중계 점수판, 자막 그래픽, 유니폼 이름·등번호)과 음성(해설)에서 실제로 보이거나 들린 것만 적고, "
          "보이지 않으면 null로 두세요. 제목이나 상식으로 추측하지 마세요. 시각은 영상 안의 「분:초」 문자열(예: 1:05)로.")

BAT_PROMPT = f"""이 영상은 KBO(한국 프로야구) 영상입니다. 타자가 안타·2루타·3루타·홈런·볼넷·희생플라이로 출루하거나 타점을 올린 장면을 모두 찾아 주세요.
{COMMON}
장면마다: batter(타자 이름), evidence(이름 근거: scoreboard·caption·commentary·jersey), result(안타·2루타·3루타·홈런·볼넷·희생플라이·기타 중 하나),
rbi(이 장면의 타점), inning·half(초/말), score_after(이 장면 직후 점수판 점수), pitcher, date_text(화면의 날짜), time(타격 순간)"""
BAT_SCHEMA = S(plays={"type": "ARRAY", "items": S(batter=STR, evidence={"type": "ARRAY", "items": {"type": "STRING"}}, result=STR,
                                                rbi=INT, inning=INT, half=STR, score_after=SCORE, pitcher=STR, date_text=STR, time=STR)})

PIT_PROMPT = f"""이 영상은 KBO(한국 프로야구) 영상입니다. 영상에 나오는 투수를 판독해 주세요.
{COMMON}
투수마다: pitcher(이름), evidence(이름 근거: scoreboard(P. 표시)·caption·commentary·jersey), team, opponent(상대 팀), date_text(화면의 날짜),
innings(나온 이닝 숫자 목록), strikeouts(영상에서 잡은 삼진 수), runs_allowed(영상에서 내준 점수), score_seen(점수판에 보인 점수와 그때 이닝 inning),
subject(영상의 주인공: 투수·타자·수비·기타), good(이 투수가 잘 던진 장면인가 true/false)"""
PIT_SCHEMA = S(pitchers={"type": "ARRAY", "items": S(
    pitcher=STR, evidence={"type": "ARRAY", "items": {"type": "STRING"}}, team=STR, opponent=STR, date_text=STR,
    innings={"type": "ARRAY", "items": {"type": "INTEGER"}}, strikeouts=INT, runs_allowed=INT,
    score_seen={**S(away_team=STR, away=INT, home_team=STR, home=INT, inning=INT), "nullable": True},
    subject=STR, good={"type": "BOOLEAN", "nullable": True})})

SEG_PROMPT = f"""이 구간은 KBO(한국 프로야구) 경기 영상의 일부입니다. 이 구간에 나오는 플레이를 순서대로 적어 주세요.
{COMMON}
플레이마다: time, pitcher, batter, result(삼진·땅볼 아웃·뜬공 아웃·안타·2루타·볼넷·실점 등 짧게), runs(이 플레이로 난 점수).
그리고 focus: 이 구간의 주인공(투수·타자·수비·기타)과 한 줄 요약 summary."""
SEG_SCHEMA = S(plays={"type": "ARRAY", "items": S(time=STR, pitcher=STR, batter=STR, result=STR, runs=INT)}, focus=STR, summary=STR)


def run():
    j = Judge(OUT)
    for t in TRUTH:
        g = t["group"]
        if g.startswith("hit"):
            r = j.ask("hit_" + t["video_id"], t["video_id"], BAT_PROMPT, BAT_SCHEMA)
        elif g.startswith("pitch"):
            r = j.ask("pit_" + t["video_id"], t["video_id"], PIT_PROMPT, PIT_SCHEMA)
        else:
            r = j.ask(f"seg_{t['video_id']}_{t['start']}", t["video_id"], SEG_PROMPT, SEG_SCHEMA, t["start"], t["end"])
        u = r["body"].get("usageMetadata", {})
        print(g, t["video_id"], r["status"], r.get("model"), r.get("sec"), "s", u.get("promptTokenCount"), "tok", flush=True)


# ---------------------------------------------------------------- 채점
KIND = {"안타": {"single", "double", "triple"}, "2루타": {"double"}, "3루타": {"triple"}, "홈런": {"home_run"},
        "볼넷": {"walk"}, "희생플라이": {"sac_fly"}}


def name_hit(said, real):
    return bool(said) and (real in said or said in real or (len(real) == 3 and real[1:] in said))


def md_of(txt):
    nums = [int(x) for x in re.findall(r"\d+", txt or "")]
    if len(nums) >= 3 and nums[0] > 12:
        nums = nums[1:]
    return tuple(nums[:2]) if len(nums) >= 2 else None


def score_hits(t, plays):
    """이 타자의 판독 장면 → 기록 타석. 결과 종류 + (이닝·직후 점수) 중 맞는 근거가 2개 이상이고 타석이 하나로 정해져야"""
    found = {}
    for pl in plays:
        if not name_hit(pl.get("batter"), t["name"]):
            continue
        kinds = KIND.get(pl.get("result") or "", set())
        sa = pl.get("score_after") or {}
        cands = []
        for q in t["pool"]:
            ev = {"kind": q["events"] in kinds}
            if pl.get("inning") is not None:
                ev["inning"] = pl["inning"] == q["inning"]
            if sa.get("away") is not None and sa.get("home") is not None:
                ev["score"] = sorted([sa["away"], sa["home"]]) == sorted([q["away_post"], q["home_post"]])
            if all(ev.values()) and len(ev) >= 2:
                cands.append(q["pa_id"])
        if len(cands) == 1:
            found[cands[0]] = mmss(pl.get("time"))
    return found


def score():
    res = collections.Counter()
    for t in TRUTH:
        g, vid = t["group"], t["video_id"]
        key = "hit_" + vid if g.startswith("hit") else "pit_" + vid if g.startswith("pitch") else f"seg_{vid}_{t['start']}"
        p = OUT / f"{key}.json"
        if not p.exists():
            print(g, vid, "응답 없음"); continue
        r = json.load(open(p, encoding="utf-8"))
        d = parsed(r) or {}
        if g.startswith("hit"):
            found = score_hits(t, d.get("plays", []))
            verdict = ("연결 타석 맞음" if t["linked"] in found and len(found) == 1 else
                       "연결 타석 맞음 + 다른 안타도" if t["linked"] in found else
                       "다른 타석으로 정해짐" if found else "못 정함")
            res[(g, verdict)] += 1
            events = {q["pa_id"]: f"{q['inning']}{q['half']} {q['events']} {q['away_post']}:{q['home_post']}" for q in t["pool"]}
            print(f"{g:20} {vid} {t['name']} | {verdict} | 연결 {events[t['linked']]} | 판독 →",
                  {events[k]: v for k, v in found.items()}, "|", t["title"][:50])
        elif g.startswith("pitch"):
            ps = d.get("pitchers", [])
            ok = []
            for c in t["cands"]:
                for pl in ps:
                    if not name_hit(pl.get("pitcher"), c["pitcher"]):
                        continue
                    ev = {}
                    if md_of(pl.get("date_text")):
                        ev["date"] = md_of(pl["date_text"]) == (int(c["date"][5:7]), int(c["date"][8:10]))
                    if pl.get("opponent"):
                        ev["opp"] = c["opponent"] in pl["opponent"] or pl["opponent"] in c["opponent"]
                    if ev and all(ev.values()):
                        ok.append((c["outing_id"], pl.get("good"), pl.get("subject"), tuple(ev)))
            ids = {o[0] for o in ok}
            verdict = "후보 하나로 정해짐" if len(ids) == 1 else "여럿 맞음" if ids else "못 정함"
            res[(g, verdict)] += 1
            print(f"{g:20} {vid} | 후보 {len(t['cands'])} | {verdict} | 근거 {[o[3] for o in ok][:2]} · 잘한 장면 {[o[1] for o in ok][:1]} · 주인공 {[o[2] for o in ok][:1]} | {t['title'][:45]}")
        else:
            res[(g, "판독됨" if d else "실패")] += 1
            print(f"{g:20} {vid} {t['pitcher']} {t['inning']}회 기록 {t['evs']} | Gemini: {d.get('focus')} · {d.get('summary')} | "
                  + "; ".join(f"{x.get('time')} {x.get('pitcher')}→{x.get('batter')} {x.get('result')}" for x in d.get("plays", [])[:6]))
        u = r["body"].get("usageMetadata", {})
        res[("토큰", g.split(":")[0])] += u.get("promptTokenCount") or 0
    print()
    for k in sorted(res, key=str):
        print(k, res[k])


if __name__ == "__main__":
    {"run": run, "score": score}[sys.argv[1]]()
