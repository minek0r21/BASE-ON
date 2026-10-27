"""
07 --step game : 경기 하이라이트(10분 안팎)·챕터 영상 → 경기 (기본층). 설계: docs/장면.md 5-1
"""
import pandas as pd

from prepare import build_games, filter_season, read_pitches
from scenes import RE_EXCLUDE, date_in, dh_in, stage_game, teams_in


def channel_priority(channel: str, kind: str) -> int:
    """같은 경기 하이라이트끼리 순서: KBO 공식 > 티빙 > 구단 (어느 한 팀 시점이 아닌 것부터, docs/장면.md 5-1)"""
    if channel == "KBO" and kind == "game_highlight":
        return 1
    return 2 if channel == "티빙" else 3


def match_game(videos: pd.DataFrame, season: int) -> tuple[list, pd.DataFrame, dict]:
    """07b 경기 하이라이트(10분 초과)·챕터 영상 → 경기 하나 (precision game).
    제목의 두 팀 + 날짜로 경기를 찾는다. 구단 채널은 제목에 상대 팀만 있어도 자기 팀을 더한다.
    더블헤더는 제목의 DH·차전으로 고르고, 모르면 두 경기 모두 검수 대기(doubleheader)."""
    games = build_games(filter_season(read_pitches(), season))
    game_list = list(games.itertuples(index=False))
    by_key: dict = {}
    for g in games.itertuples(index=False):
        by_key.setdefault((g.date, frozenset((g.home_team, g.away_team))), []).append(g)

    matched, skipped = [], []
    for v in videos[videos["kind"].isin(["game_highlight", "chapter"])].itertuples():
        base = {"video_id": v.video_id, "title": v.title}
        if RE_EXCLUDE.search(v.title):
            skipped.append({**base, "reason": "국제대회·다른 종목 등"})
            continue
        teams = teams_in(v.title, v.channel)
        date = date_in(v.title, v.published_at)
        _, sg = stage_game(v.title, game_list, v.published_at)  # 포스트시즌 「WC 1차전」 · 「KS 3차전」 → 날짜와 상관없이 그 경기
        if sg is not None:
            matched.append({"video_id": v.video_id, "game_pk": sg.game_pk, "date": sg.date, "unique": True,
                            "priority": channel_priority(v.channel, v.kind), "published_at": v.published_at,
                            "end_sec": v.duration_sec, "reasons": "단계+차전"})
            continue
        if len(teams) != 2 or not date:
            skipped.append({**base, "reason": "팀 둘·날짜를 못 읽음"})
            continue
        if not date.startswith(str(season)):
            continue
        gs = by_key.get((date, frozenset(teams)), [])
        dh = dh_in(v.title)
        if len(gs) > 1 and dh:
            gs = [g for g in gs if g.dh_no == dh]
        if not gs:
            skipped.append({**base, "reason": "경기 없음"})
            continue
        for g in gs:
            matched.append({"video_id": v.video_id, "game_pk": g.game_pk, "date": date, "unique": len(gs) == 1,
                            "priority": channel_priority(v.channel, v.kind), "published_at": v.published_at,
                            "end_sec": v.duration_sec, "reasons": "+".join(["팀", "날짜"] + (["DH"] if dh else []))})

    m = pd.DataFrame(matched)
    links = []
    if len(m):
        m = m.sort_values(["game_pk", "priority", "published_at"])
        m["rank"] = m.groupby("game_pk").cumcount() + 1
        for r in m.itertuples(index=False):
            links.append({"rel": "matched", "target_kind": "game", "target_id": r.game_pk, "video_id": r.video_id,
                          "scene_type": "game", "precision": "game", "start_sec": 0, "end_sec": r.end_sec,
                          "status": "auto_confirmed" if r.unique else "pending", "origin": "auto",
                          "review_reason": None if r.unique else "doubleheader",
                          "score": 100 if r.unique else 50, "rank": r.rank, "reasons": r.reasons})
    miss = pd.DataFrame(skipped)
    confirmed = m[m["unique"]]["game_pk"].nunique() if len(m) else 0
    print(f"\n경기 {len(games)}개 중 확정 하이라이트가 있는 경기: {confirmed}개 ({confirmed / max(len(games), 1):.1%})")
    if len(m):
        channel = dict(zip(videos["video_id"], videos["channel"]))
        print("1순위 채널:", m[m["rank"] == 1]["video_id"].map(channel).value_counts().to_dict())
        print(f"더블헤더 미판정(검수): {int((~m['unique']).sum())}줄")
    print("연결 못 한 이유:", miss["reason"].value_counts().to_dict() if len(miss) else {})
    game_date = m.drop_duplicates("video_id").set_index("video_id")["date"].to_dict() if len(m) else {}
    return links, miss, game_date


