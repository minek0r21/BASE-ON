"""
적재 규칙(정제)에 해당하는 건수를 시즌별로 센다. DB는 쓰지 않는다.
    python etl/04_count_rules.py
2023은 사용하지 않지만, 예전 문서 숫자(2023~2026 전체)와 비교하려고 같이 보여준다.
"""
import pandas as pd

from common import KBO_PBP_DIR
from prepare import COLUMNS, SEASONS

paths = sorted(KBO_PBP_DIR.glob("kbo_pbp_*.parquet"))  # 2023 파일이 있으면 비교용으로 같이 읽는다
if not paths:
    raise SystemExit(f"원본 파일이 없습니다: {KBO_PBP_DIR} (python scripts/get_data.py)")
df = pd.concat([pd.read_parquet(p, columns=COLUMNS) for p in paths], ignore_index=True)
df["season"] = df["game_date"].astype("string").str[:4].astype(int)
df["events"] = df["events"].astype("string").str.strip().replace("", pd.NA)
df["pitch_result"] = df["pitch_result"].astype("string").str.strip()

keys = ["game_pk", "at_bat_number"]
df = df.sort_values(keys + ["pitch_number"])
g = df.groupby(keys, sort=False)
last = g.tail(1)                                  # 타석의 마지막 공
batters = g["batter"].nunique().rename("n_batter").reset_index()
batters["season"] = batters["game_pk"].map(df.drop_duplicates("game_pk").set_index("game_pk")["season"])

abn = df.drop_duplicates(keys)[["game_pk", "season", "at_bat_number"]]
gap = abn.groupby(["game_pk", "season"])["at_bat_number"].agg(["max", "nunique"]).reset_index()
gap["has_gap"] = gap["max"] != gap["nunique"]     # 1..max 중 빈 번호가 있음

rows = []
for s, part in df.groupby("season"):
    l = last[last["season"] == s]
    rows.append({
        "시즌": s,
        "사용": "O" if s in SEASONS else "X (제외)",
        "경기": part["game_pk"].nunique(),
        "타석(원본)": len(l),
        "결과 빈 타석(제외)": int(l["events"].isna().sum()),
        "적재 타석": int(l["events"].notna().sum()),
        "대타 교체 타석": int((batters[batters["season"] == s]["n_batter"] > 1).sum()),
        "번호 빈 경기": int(gap[gap["season"] == s]["has_gap"].sum()),
        "V 투구": int((part["pitch_result"] == "V").sum()),
        "싱커→투심": int((part["_naver_pitch_name"].astype("string").str.strip() == "싱커").sum()),
    })
t = pd.DataFrame(rows).set_index("시즌")
use = t[t["사용"] == "O"].drop(columns="사용").sum()
pd.set_option("display.width", 200)
print(t.to_string())
print("\n[2024~2026 합계]")
print(use.to_string())
print("\n[2023~2026 합계 — 예전 문서 숫자와 비교용]")
print(t.drop(columns="사용").sum().to_string())
