"""
07. 영상 제목 ↔ 타석 매칭 (DB 안 건드림)

06에서 받은 영상 목록(CSV)의 제목을 읽고, 그 경기의 타석 중 어느 타석 장면인지 점수를 매긴다.
결과는 CSV로만 저장한다. 눈으로 확인한 뒤 08_load_videos.py로 DB에 넣는다.

제목 예)
  [LG vs KIA] 단숨에 대량 득점을 뽑아낸 LG 문성주 2타점과 김현수 스리런 홈런! | 7.24 | 크보모먼트 ...
   └ 원정 vs 홈   └ 내용: 선수 이름 + 결과 + 상황                                └ 경기 날짜

순서
  1) 제목에서 [원정 vs 홈 (DH1)] 과 | 월.일 | 을 읽어 경기를 정한다
  2) 영상 종류를 나눈다: 시구·수비 등(연결 안 함) / 투수 / 타자
  3) 그 경기 타자 이름 중 제목에 나온 이름을 찾는다 (긴 이름부터)
  4) 그 타자의 타석마다 결과·타점·상황·이닝·시즌 N호·상대 투수가 제목과 맞는지 점수를 매긴다
  5) 타자마다 상위 3개 = 후보(CANDIDATE), 기준 점수를 넘은 1등 = 자동 연결(MATCHED_TO, 대기)

실행 (data 폴더에서)
  python etl/07_match_videos.py --season 2025 --videos videos/playlist_PLMtML65ksOv0.csv
결과
  videos/match_2025.csv      영상-타석 후보 한 줄씩 (score, rank, matched, reasons)
  videos/unmatched_2025.csv  연결 못 한 영상과 이유
"""
import argparse
import re
from pathlib import Path

import pandas as pd
from baseon_rules.events import HITS

from prepare import TEAM_NAMES, build_games, build_pa, filter_season, read_pitches

ROOT = Path(__file__).resolve().parent.parent  # data 폴더
NAME_TO_CODE = {v: k for k, v in TEAM_NAMES.items()}  # "KIA" → "HT"

MATCH_MIN = 70      # 자동 연결 기준 점수 (이름 50 + 결과 30 = 80이면 통과)
TOP_N = 3           # 타자마다 후보로 남길 타석 수

# ---------------------------------------------------------------- 제목 읽기 규칙
RE_TEAMS = re.compile(r"\[\s*(\S+)\s+vs\s+(\S+?)(?:\s*DH\s*(\d))?\s*\]")
RE_DATE = re.compile(r"\|\s*#?\s*(\d{1,2})\.(\d{1,2})\s*\|")
RE_INNING = re.compile(r"(\d{1,2})\s*회\s*(초|말)?")
RE_HR_SEQ = re.compile(r"(?:시즌\s*)?(\d{1,2})\s*호(?!\s*도루)")
RE_RBI = re.compile(r"(?<!\d)(?<!시즌 )(?<!시즌)(\d)\s*타점")  # "시즌 153타점" 같은 누적 기록은 제외

# 연결하지 않는 영상 (타석 결과 장면이 아님)
SKIP_WORDS = ["시구", "애국가", "수비", "캐치", "하.점.캐", "다이빙", "보살", "송구",
              "삼중살", "병살", "도루", "주루", "인터뷰", "세리머니", "판정", "비디오 판독"]
# 투수 영상 (지금은 연결 안 함. 나중에 투수 기준 매칭)
PITCHER_WORDS = ["K ", "KK", "탈삼진", "무실점", "이닝", "완봉", "완투", "세이브", "피칭", "투구",
                 "호투", "승리투수", "노히트", "퍼펙트"]

# 결과 단어 → events 묶음
EVENT_WORDS = {
    "home_run": ["홈런", "솔로", "투런", "스리런", "쓰리런", "그랜드슬램", "아치", "대포", "담장", "넘기", "넘어갑",
                 "선제포", "결승포", "쐐기포", "동점포", "역전포", "추격포", "만루포", "백투백"],
    "triple": ["3루타"],
    "double": ["2루타"],
    "hit": ["안타", "적시타", "결승타", "끝내기타", "싹쓸이"],
    "walk": ["볼넷", "밀어내기"],
    "sac_fly": ["희생플라이", "희플"],
}
HR_RUNS = {"솔로": 1, "투런": 2, "스리런": 3, "쓰리런": 3, "만루": 4, "그랜드슬램": 4}
SITUATIONS = ["끝내기", "역전", "동점"]


def parse_title(title: str, season: int) -> dict | None:  # 제목 → 팀·날짜·더블헤더
    t, d = RE_TEAMS.search(title), RE_DATE.search(title)
    if not (t and d):
        return None
    return {
        "away": t.group(1), "home": t.group(2), "dh": t.group(3),
        "date": f"{season}-{int(d.group(1)):02d}-{int(d.group(2)):02d}",
        "body": title[t.end():d.start()],  # 팀·날짜를 뺀 내용 부분
    }


def kind_of(body: str, names: list[str]) -> str:  # 영상 종류
    has_event = has_event_word(body)
    skip = any(w in body for w in SKIP_WORDS) or re.search(r"(?<!적)시타", body)  # '적시타'의 '시타'는 제외
    if skip and not has_event:
        return "기타"
    if any(w in body for w in PITCHER_WORDS) and not names:
        return "투수"
    return "타자"


def find_names(body: str, candidates: set[str]) -> list[str]:  # 제목에 나온 타자 이름 (긴 이름부터, 겹치면 하나만)
    used, found = [False] * len(body), []
    for name in sorted(candidates, key=len, reverse=True):
        for m in re.finditer(re.escape(name), body):
            if not any(used[m.start():m.end()]):
                used[m.start():m.end()] = [True] * (m.end() - m.start())
                found.append((m.start(), name))
    return [n for _, n in sorted(found)]


def has_event_word(text: str) -> bool:
    return any(w in text for words in EVENT_WORDS.values() for w in words)


def segment_for(body: str, name: str, names: list[str]) -> str:  # 이 선수 이름부터 다음 선수 이름 전까지
    start = body.find(name)
    ends = [body.find(n, start + len(name)) for n in names if n != name]
    ends = [e for e in ends if e > start]
    seg = body[start:min(ends)] if ends else body[start:]
    # "구자욱과 디아즈의 백투백 홈런"처럼 결과가 뒤 선수 쪽에 몰려 있으면 뒤까지 본다
    return seg if has_event_word(seg) else body[start:]


def score_pa(pa: pd.Series, seg: str, body: str) -> tuple[int, list[str]]:  # 타석 하나의 점수와 맞은 요소
    score, why = 50, ["이름"]
    ev = pa["events"]
    # 이름 뒤에 가장 먼저 나오는 결과 단어 하나만 본다 ("홈런과 연속 안타" → 홈런)
    hits = [(seg.find(w), k) for k, words in EVENT_WORDS.items() for w in words if w in seg]
    wanted = [min(hits)[1]] if hits else []
    if wanted:
        ok = any(ev == k or (k == "hit" and ev in HITS) for k in wanted)
        score += 30 if ok else -30
        if ok:
            why.append({"home_run": "홈런", "hit": "안타", "triple": "3루타", "double": "2루타",
                        "walk": "볼넷", "sac_fly": "희생플라이"}[next(k for k in wanted if ev == k or (k == "hit" and ev in HITS))])
    elif ("타점" in seg or "득점" in seg) and pa["runs_scored"] > 0:
        score += 20
        why.append("타점")
    # 적시타·결승타·싹쓸이는 점수가 난 타석이어야 한다
    if any(w in seg for w in ["적시타", "결승타", "싹쓸이", "타점"]) and ev != "home_run":
        if pa["runs_scored"] > 0:
            score += 10
            why.append("득점")
        else:
            score -= 10
    m = re.search(r"([1-4])\s*점\s*홈런", seg)  # "3점 홈런"
    hr_words = dict(HR_RUNS, **({m.group(0): int(m.group(1))} if m else {}))
    for word, runs in hr_words.items():
        if word in seg and ev == "home_run":
            if pa["runs_scored"] == runs:
                score += 10
                why.append(word)
            else:
                score -= 20
            break
    m = RE_RBI.search(seg)
    if m and pa["runs_scored"] == int(m.group(1)):
        score += 10
        why.append(f"{m.group(1)}타점")
    for s in SITUATIONS:
        if s in seg:
            if pa["situation"] == s:
                score += 30 if s == "끝내기" else 10  # 끝내기 타석은 경기에 하나뿐이라 강한 단서
                why.append(s)
            break
    m = RE_INNING.search(body)
    if m:
        if pa["inning"] == int(m.group(1)) and (not m.group(2) or pa["inning_half"] == m.group(2)):
            score += 10
            why.append(f"{m.group(1)}회")
    m = RE_HR_SEQ.search(seg)
    if m and ev == "home_run" and pa["hr_seq"] == int(m.group(1)):
        score += 10
        why.append(f"{m.group(1)}호")
    if isinstance(pa["pitcher_name"], str) and pa["pitcher_name"] in body:
        score += 10
        why.append("투수")
    return score, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--videos", default="videos/playlist_PLMtML65ksOv0.csv")
    args = ap.parse_args()

    videos = pd.read_csv(ROOT / args.videos, dtype=str, encoding="utf-8-sig")
    print(f"영상 {len(videos)}개 읽음. 타석 만드는 중…")
    df = filter_season(read_pitches(), args.season)
    games = build_games(df)
    pa = build_pa(df, games)
    pa["bat_name"] = pa["batter_name"]
    by_game = {k: g for k, g in pa.groupby("game_pk")}

    rows, skipped = [], []
    for v in videos.itertuples():
        t = parse_title(v.title, args.season)
        base = {"video_id": v.video_id, "title": v.title}
        if not t:
            skipped.append({**base, "reason": "제목 형식 다름"}); continue
        away, home = NAME_TO_CODE.get(t["away"]), NAME_TO_CODE.get(t["home"])
        if not (away and home):
            skipped.append({**base, "reason": "KBO 경기 아님"}); continue
        g = games[(games["date"] == t["date"]) & (games["away_team"] == away) & (games["home_team"] == home)]
        if t["dh"]:
            g = g[g["dh_no"] == int(t["dh"])]
        if len(g) != 1:
            skipped.append({**base, "reason": "경기 없음" if g.empty else "더블헤더 구분 필요"}); continue
        game_pk = g["game_pk"].iloc[0]
        gpa = by_game[game_pk]
        names = find_names(t["body"], set(gpa["bat_name"].dropna()))
        kind = kind_of(t["body"], names)
        if kind != "타자":
            skipped.append({**base, "game_pk": game_pk, "reason": f"{kind} 영상"}); continue
        if not names:
            skipped.append({**base, "game_pk": game_pk, "reason": "타자 이름 없음"}); continue

        for name in names:
            seg = segment_for(t["body"], name, names)
            cand = gpa[gpa["bat_name"] == name]
            scored = sorted(
                ((*score_pa(p, seg, t["body"]), p) for _, p in cand.iterrows()),
                key=lambda x: (-x[0], x[2]["at_bat_number"]),
            )
            # 멀티홈런·연타석이면 그 타자의 홈런 타석을 모두 연결
            multi = any(w in seg for w in ["멀티홈런", "연타석", "멀티 홈런"])
            for rank, (score, why, p) in enumerate(scored[:TOP_N], 1):
                gap = score - scored[1][0] if len(scored) > 1 and rank == 1 else None
                matched = score >= MATCH_MIN and (rank == 1 or (multi and p["events"] == "home_run"))
                rows.append({
                    **base, "game_pk": game_pk, "batter": name, "pa_id": p["pa_id"],
                    "inning": f"{p['inning']}회{p['inning_half']}", "events": p["events"],
                    "runs": p["runs_scored"], "score": score, "rank": rank, "gap": gap,
                    "matched": matched, "reasons": "+".join(why),
                })

    out = pd.DataFrame(rows)
    miss = pd.DataFrame(skipped)
    out.to_csv(ROOT / f"videos/match_{args.season}.csv", index=False, encoding="utf-8-sig")
    miss.to_csv(ROOT / f"videos/unmatched_{args.season}.csv", index=False, encoding="utf-8-sig")

    linked = out[out["matched"]]
    print(f"\n자동 연결된 영상: {linked['video_id'].nunique()}개 / 전체 {len(videos)}개")
    print(f"자동 연결된 타석: {len(linked)}개 (후보 포함 {len(out)}줄)")
    print("연결 못 한 이유:", miss["reason"].value_counts().to_dict() if len(miss) else {})
    amb = linked[linked["gap"].notna() & (linked["gap"] < 20)]
    print(f"애매함(1·2등 점수 차 20 미만): {len(amb)}개 → 검수 우선")
    print(f"\n저장: videos/match_{args.season}.csv, videos/unmatched_{args.season}.csv")


if __name__ == "__main__":
    main()
