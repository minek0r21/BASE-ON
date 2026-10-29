"""
07 --step outing : 영상 → 등판(Outing). 설계: docs/장면.md 5-3(07d 등판 클립)·5-4(07e 챕터 투수 줄)

07d 등판 클립 (10분 이하)
  제목의 투수 이름 + 날짜(없으면 게시일부터 7일 전까지)로 등판 후보를 찾고,
  제목의 주장(n이닝 · nK · KKK · 무실점 · 노히트 · 완봉 · 세이브)을 등판 기록과 대조한다.
  기록 달성(통산·역대·달성·최초·세 자리 숫자 K)은 대조 없이 검수로.
07e 챕터 투수 줄 (설명란 「05:03 6회초 … 송승기의 QS」)
  채널 팀 + 날짜로 경기를 정하고, 그 이닝에 그 투수가 던졌으면 연결(precision inning).
  긍정 문구 → 자동 확정, 부정 문구(실점·강판·허용 …) → 연결 안 함(잘한 장면만, S8), 그 밖 → 검수.
축 태그(tags)는 기록으로 확인된 주장에서만 단다: strikeout · hit_prevention · control.
"""
import re
from collections import defaultdict
from datetime import timedelta

import pandas as pd

from prepare import build_games, build_outings, build_pa, charge_runs, filter_season, pa_ends, read_pitches
from match_pa import latest_day_before
from scenes import RE_EXCLUDE, RE_INNING, chapter_end, chapter_game, chapter_lines, date_in, stage_game, teams_in

GATE = re.compile(r"탈삼진|(?<![\d,])\d{1,2}\s*K(?![A-Za-z])|KK|삼진|무실점|노히트|노히터|퍼펙트|완봉|완투|세이브|홀드|"
                  r"\d+(?:\.\d)?\s*이닝|호투|피칭|역투|쾌투|QS|승리투수|삼자범퇴")
EXCLUDE = re.compile(r"불펜\s*피칭|인터뷰|모음|비하인드|덕아웃캠|직캠|유니폼|굿즈|Mic'd|마이크|시구")
HR_WORD = re.compile(r"홈런|솔로포|투런|스리런|쓰리런|만루포|그랜드슬램")  # 홈런 클립은 타석 단계(pa)가 가져간다
MILESTONE = re.compile(r"통산|역대|달성|최초|\d{3,}\s*(?:K|탈삼진|세이브|승)")
# 챕터 투수 줄 문구 (잘한 장면만, S8)
POS = re.compile(r"삼자범퇴|탈삼진|삼진|KK|무실점|호투|QS|퀄리티|위기[를을]?\s?(?:관리|탈출|넘|잠재|막)|삭제|지워|막아|지켜|잡아|"
                 r"돌려세|틀어막|깔끔|완벽|철벽|세이브|홀드|역투|쾌투|병살|무사사구|노히트")
NEG = re.compile(r"피홈런|홈런을 허용|홈런 허용|실점|강판|볼넷|사구|흔들|허용|맞고|맞은")
KST = timedelta(hours=9)


# ---------------------------------------------------------------- 이름 찾기
NON_SCENE = re.compile(r"터뷰|애프터|시상식|톡\]|TALK|리포터|프리뷰|브이로그|직후|겨울방학|야구기인|야구대표자")  # 인터뷰 · 시상식 · 토크 = 장면 아님 (S15)
BAT_WORDS = re.compile(r"안타|루타|적시|타점|득점권|해결사|홈런|타석|타격|장타|볼넷|출루|도루|수비|영웅들")  # 같은 이름 타자 영상 · 수비 장면을 등판으로 확정하지 않게


def names_in(text: str, names: set[str]) -> list[str]:
    """긴 이름부터, 이미 쓴 자리는 지운다 (김민 ⊂ 김민혁 방지). 제목에 나온 순서대로"""
    found, rest = [], text
    for n in sorted(names, key=len, reverse=True):
        if len(n) >= 2 and n in rest:
            found.append((rest.index(n), n))
            rest = rest.replace(n, "□" * len(n))
    return [n for _, n in sorted(found)]


# ---------------------------------------------------------------- 제목 주장 ↔ 등판 기록
def claims(t: str) -> dict:
    c = {}
    m = re.search(r"(\d{1,2})(?:\.(\d))?\s*이닝", t)
    if m:
        c["outs"] = int(m.group(1)) * 3 + (int(m.group(2)) if m.group(2) else 0)
        c["outs_whole"] = m.group(2) is None
    m = re.search(r"(?<![\d,])(\d{1,2})\s*(?:K(?![A-Za-z])|탈삼진)", t)
    if m:
        c["so"] = int(m.group(1))
    elif "KKK" in t:
        c["so_min"] = 3
    if "무실점" in t:
        c["r0"] = True
    if re.search(r"노히트|노히터", t):
        c["h0"] = True
    if "완봉" in t:
        c["shutout"] = True
    if "세이브" in t:
        c["save"] = True
    if re.search(r"무사사구|무4사구", t):
        c["bb0"] = True
    return c


def check(o, c: dict) -> list[str]:
    """맞지 않는 주장 목록. 정수 「n이닝」은 3n−1 아웃도 허용 (구단 채널 반올림, 10-20 조사)"""
    bad = []
    if "outs" in c and not (o.outs == c["outs"] or (c["outs_whole"] and o.outs == c["outs"] - 1)):
        bad.append(f"이닝 {c['outs']}≠{o.outs}")
    if "so" in c and c["so"] != o.so:
        bad.append(f"K {c['so']}≠{o.so}")
    if "so_min" in c and o.so < c["so_min"]:
        bad.append("KKK")
    if c.get("r0") and o.r != 0:
        bad.append(f"실점 {o.r}")
    if c.get("h0") and o.h != 0:
        bad.append(f"피안타 {o.h}")
    if c.get("shutout") and not (o.team_pitchers == 1 and o.r == 0):
        bad.append("완봉")
    if c.get("save") and not (o.finisher and not o.starter):
        bad.append("세이브")
    if c.get("bb0") and o.bb + o.hbp != 0:
        bad.append("무사사구")
    return bad


def tags_of(c: dict) -> list[str]:
    """대조를 통과한 주장 → 축 태그 (docs/장면.md 5-3)"""
    t = []
    if c.get("so", 0) >= 5 or c.get("so_min", 0) >= 3:
        t.append("strikeout")
    if c.get("r0") or c.get("h0") or c.get("shutout"):
        t.append("hit_prevention")
    if c.get("bb0"):
        t.append("control")
    return t


# ---------------------------------------------------------------- 07d · 07e
def match_outing(videos: pd.DataFrame, season: int) -> tuple[list, pd.DataFrame, dict]:
    df = filter_season(read_pitches(), season)
    games = build_games(df)
    pa = build_pa(df, games)
    outings = build_outings(df, pa)
    names = df.dropna(subset=["pitcher_name"]).groupby("pitcher")["pitcher_name"].last()
    outings["name"] = outings["player_id"].map(names)
    by_date: dict = defaultdict(list)
    for o in outings.itertuples(index=False):
        if isinstance(o.name, str):
            by_date[o.date].append(o)
    oid_by_key = {(o.game_pk, o.player_id): o for o in outings.itertuples(index=False)}

    # 이닝 단위 기록 (챕터 줄 대조): 투수 × 경기 × 이닝 × 초말
    ends = pa_ends(df)
    ch = charge_runs(ends).merge(ends[["game_pk", "at_bat_number", "inning", "inning_topbot"]], on=["game_pk", "at_bat_number"])
    inn_runs = ch.groupby(["game_pk", "pitcher", "inning", "inning_topbot"])["runs"].sum()
    ev = pa["events"]
    inn = pa.assign(so=ev.eq("strikeout"), h=ev.isin({"single", "double", "triple", "home_run"}),
                    on=ev.isin({"walk", "hit_by_pitch"})) \
        .groupby(["game_pk", "pitcher", "inning", "inning_topbot"]).agg(tbf=("pa_id", "size"), so=("so", "sum"),
                                                                        h=("h", "sum"), on=("on", "sum"))
    games_by_date: dict = defaultdict(list)
    for g in games.itertuples(index=False):
        games_by_date[g.date].append(g)
    game_list = list(games.itertuples(index=False))
    staff: dict = defaultdict(dict)  # 경기 → {투수 이름: 투수 ID}
    for o in outings.itertuples(index=False):
        if isinstance(o.name, str):
            staff[o.game_pk][o.name] = o.player_id

    links, skipped, game_date = [], [], {}

    def add(o, v, *, scene_type, precision, start, end, status, review_reason, score, reasons, tags):
        links.append({"rel": "matched", "target_kind": "outing", "target_id": o.outing_id, "video_id": v.video_id,
                      "scene_type": scene_type, "precision": precision, "start_sec": start, "end_sec": end,
                      "status": status, "origin": "auto", "review_reason": review_reason, "score": score,
                      "reasons": reasons, "tags": "+".join(tags) if tags else None})
        game_date[v.video_id] = o.date

    # ---- 07d 등판 클립
    for v in videos[videos["kind"].eq("clip")].itertuples():
        t = v.title
        if not GATE.search(t) or EXCLUDE.search(t) or RE_EXCLUDE.search(t) or HR_WORD.search(t):
            continue
        base = {"video_id": v.video_id, "title": t}
        _, sg = stage_game(t, game_list, v.published_at)  # 포스트시즌 「KS 3차전」 → 날짜와 상관없이 그 경기
        td = sg.date if sg is not None else date_in(t, v.published_at)
        pub = (pd.Timestamp(v.published_at) + KST).normalize()
        dates = [td] if td else [(pub - timedelta(days=k)).strftime("%Y-%m-%d") for k in range(0, 8)]
        if not any(d.startswith(str(season)) for d in dates):
            continue
        teams = teams_in(t, v.channel)
        pool = [o for d in dates for o in by_date.get(d, []) if sg is None or o.game_pk == sg.game_pk]
        found = set(names_in(t, {o.name for o in pool}))  # 그날들 등판한 투수 이름 전체로 한 번에 (김민 ⊂ 김민혁 방지)
        cand = [o for o in pool if o.name in found]
        team_ok = not teams or any(o.team_id in teams for o in cand)  # 팀이 안 맞아 팀 없이 다시 찾은 경우는 확정하지 않는다
        if teams:
            cand = [o for o in cand if o.team_id in teams] or cand
        if not cand:
            skipped.append({**base, "reason": "이름·날짜 맞는 등판 없음"})
            continue
        c = claims(t)
        if MILESTONE.search(t):
            # 기록 달성(「100홀드」 · 「시즌 11승」): 달성 여부는 확인 못 해도 어느 등판인지 확실하면 확정 (S15)
            pick = cand if td else [x for x in cand if x.date == latest_day_before(
                sorted({y.date for y in cand if y.player_id == x.player_id}), v.published_at)]
            ok = len({x.outing_id for x in pick}) == 1 and team_ok and not NON_SCENE.search(t) and not BAT_WORDS.search(t)
            o = pick[0] if ok else max(cand, key=lambda x: x.date)
            add(o, v, scene_type="milestone", precision="scene", start=0, end=v.duration_sec,
                status="auto_confirmed" if ok else "pending", review_reason=None if ok else "milestone",
                score=70 if ok else 50, reasons="이름+날짜+기록 달성", tags=[])
            continue
        if len({x.outing_id for x in cand}) > 1 and c:
            ok = [o for o in cand if not check(o, c)]
            cand = ok or cand
        if len({x.outing_id for x in cand}) > 1 and not td and c:  # 날짜 없는 제목: 주장이 맞는 가장 최근 등판
            latest = max(x.date for x in cand)
            cand = [x for x in cand if x.date == latest]
        pub_ok = bool(td)
        if not td:  # 날짜 없는 제목: 투수마다 올린 시각 직전 등판 (docs/장면.md S14, 날짜 있는 클립 269개로 잰 정확도 99.6%)
            near = [x for x in cand if x.date == latest_day_before(sorted({y.date for y in cand if y.player_id == x.player_id}),
                                                                   v.published_at)]
            if near:
                cand, pub_ok = near, True
        one_game = len({x.game_pk for x in cand}) == 1 and len({x.player_id for x in cand}) == len(cand)
        if len(cand) > 1 and one_game and pub_ok and not NON_SCENE.search(t):  # 「곽빈의 승, 김택연이 지켰다」: 한 경기 투수 여럿 → 각자의 등판에 (S14)
            ok = [o for o in cand if not (c and check(o, c))]
            for o in cand:
                good = o in ok or not ok
                add(o, v, scene_type="closing" if re.search(r"세이브|홀드", t) else "outing", precision="scene", start=0,
                    end=v.duration_sec, status="auto_confirmed" if good and ok else "pending",
                    review_reason=None if good and ok else "claim_mismatch", score=80, reasons="이름+날짜+투수 여럿", tags=[])
            continue
        if len({x.outing_id for x in cand}) > 1:
            for o in cand:
                add(o, v, scene_type="outing", precision="scene", start=0, end=v.duration_sec, status="pending",
                    review_reason="ambiguous", score=40, reasons="이름+날짜(후보 여럿)", tags=[])
            continue
        o = cand[0]
        bad = check(o, c)
        scene_type = "closing" if re.search(r"세이브|홀드", t) else "outing"
        if c and not bad:
            add(o, v, scene_type=scene_type, precision="scene", start=0, end=v.duration_sec, status="auto_confirmed",
                review_reason=None, score=90, reasons="이름+날짜+" + "+".join(k for k in c if k != "outs_whole"),
                tags=tags_of(c))
        elif not c and pub_ok and team_ok and not BAT_WORDS.search(t) and not NON_SCENE.search(t):
            # 확인할 주장은 없지만 그 투수의 그날 등판은 하나 → 어느 등판인지는 확실하다 (S14). 타자 영상(「LG 김현수, 역전을 이끄는 해결사」)은 빼고
            add(o, v, scene_type=scene_type, precision="scene", start=0, end=v.duration_sec, status="auto_confirmed",
                review_reason=None, score=70, reasons="이름+날짜", tags=[])
        else:
            add(o, v, scene_type=scene_type, precision="scene", start=0, end=v.duration_sec, status="pending",
                review_reason="claim_mismatch" if bad else "no_claim", score=60, reasons="; ".join(bad) or "이름+날짜",
                tags=[])

    # ---- 07e 챕터 투수 줄
    for v in videos[videos["kind"].eq("chapter")].itertuples():
        lines = chapter_lines(v.description)
        g = chapter_game(v.title, v.channel, v.published_at, lines, games_by_date, season)
        if g is None:
            continue  # 경기를 하나로 못 정하면 건너뛴다 (더블헤더·일상 영상)
        roster = staff.get(g.game_pk, {})
        for i, (sec, text) in enumerate(lines):
            im = RE_INNING.search(text)
            if not im:
                continue
            inning, half = int(im.group(1)), im.group(2)
            for n in names_in(text, set(roster)):
                pid = roster[n]
                halves = [h for h in (["top", "bot"] if not half else ["top" if half == "초" else "bot"])
                          if (g.game_pk, pid, inning, h) in inn.index]
                if not halves:
                    continue
                if NEG.search(text):
                    continue  # 잘한 장면만 (S8)
                o = oid_by_key[(g.game_pk, pid)]
                st = inn.loc[(g.game_pk, pid, inning, halves[0])]
                runs = int(inn_runs.get((g.game_pk, pid, inning, halves[0]), 0))
                tags = []
                k = 3 if "KKK" in text else 2 if "KK" in text else 0
                if k and st["so"] >= k:
                    tags.append("strikeout")
                if ("삼자범퇴" in text and st["tbf"] == 3 and st["h"] == 0 and st["on"] == 0) or ("무실점" in text and runs == 0):
                    tags.append("hit_prevention")
                positive = bool(POS.search(text))
                by_record = False
                if not positive:
                    # 중립 줄(「1회말 ○○○ 투구」)은 그 이닝 기록으로 정한다 (10-21): 실점(책임 주자 기준)이면 연결하지 않고(S8),
                    # 무실점에 삼진이 있거나 무안타면 잘한 이닝으로 확정, 무실점이지만 안타를 맞았으면 사람이
                    if runs > 0:
                        continue
                    by_record = True  # 무실점 이닝은 막아낸 장면 → 확정 (S15, 전에는 안타를 맞았으면 사람이)
                ok = positive or by_record
                add(o, v, scene_type="outing", precision="inning", start=sec, end=chapter_end(lines, i, v.duration_sec),
                    status="auto_confirmed" if ok else "pending", review_reason=None if ok else "neutral",
                    score=80 if positive else 70 if by_record else 50,
                    reasons=f"챕터+{inning}회" + ("+긍정" if positive else "+기록 무실점" if by_record else ""), tags=tags)

    if links:
        lk = pd.DataFrame(links)
        lk["_p"] = lk["precision"].map({"scene": 0, "inning": 1})
        lk["_s"] = lk["status"].map({"auto_confirmed": 0, "pending": 1})
        # 챕터 영상 하나에 같은 투수 줄이 여럿(1회·2회·…)이면 (등판, 영상) 쌍 하나로 합친다:
        # 가장 좋은 상태의 가장 이른 줄을 남기고, 태그는 모든 줄의 것을 합친다 (DB 관계는 쌍마다 하나)
        lk = lk.sort_values(["target_id", "video_id", "_s", "start_sec"])
        tags = lk.groupby(["target_id", "video_id"])["tags"].agg(
            lambda x: "+".join(sorted({t for v in x.dropna() for t in v.split("+")})) or None)
        lk = lk.drop_duplicates(["target_id", "video_id"]).drop(columns="tags") \
            .merge(tags.rename("tags").reset_index(), on=["target_id", "video_id"])
        # 같은 등판의 연결 순서: 자동 확정 먼저, 그중 클립(scene) 먼저, 그다음 챕터
        lk = lk.sort_values(["target_id", "_s", "_p", "start_sec"])
        lk["rank"] = lk.groupby("target_id").cumcount() + 1
        links = lk.drop(columns=["_p", "_s"]).to_dict("records")
    lk = pd.DataFrame(links)
    miss = pd.DataFrame(skipped)
    if len(lk):
        print(f"\n등판 연결 {len(lk)}줄 · 등판 {lk['target_id'].nunique()}개 / 전체 {len(outings)}개")
        print("상태:", lk.groupby(["precision", "status"]).size().to_dict())
        print("검수 이유:", lk["review_reason"].value_counts().to_dict())
        print("태그:", lk["tags"].dropna().str.split("+").explode().value_counts().to_dict())
    return links, miss, game_date
