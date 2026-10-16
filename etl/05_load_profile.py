"""
선수 프로필(포지션, 등번호, 생년월일, 투타)을 Player 노드에 추가한다.
    python etl/05_load_profile.py
- 01_load_core.py 다음에 실행. 다시 실행해도 같은 값으로 덮어쓰기만 한다.
- 파일: data/player_profile_view_cp949.csv (팀원이 정리한 2024~2026 선수 847명, 인코딩 cp949)
- 선수코드 = player_id (2024~2026 원본 선수 847명과 코드·이름 100% 일치 확인, 10.11)
"""
import pandas as pd

from common import ROOT, get_driver, load_rows, run

PROFILE = ROOT / "player_profile_view_cp949.csv"

Q = """
UNWIND $rows AS r
MATCH (p:Player {player_id: r.player_id})
SET p.position = r.position,         // 투수 / 포수 / 내야수 / 외야수
    p.back_number = r.back_number,   // 등번호 (없으면 null)
    p.birth_date = CASE WHEN r.birth_date IS NULL THEN null ELSE date(r.birth_date) END,
    p.bats_throws = r.bats_throws    // 공식 표기 (예: 우투좌타)
"""


def val(x):  # 빈칸이면 None, 아니면 앞뒤 공백 제거 (CSV에 포지션 빈칸 3명: 최근 시즌 2024인 선수)
    return None if pd.isna(x) or str(x).strip() == "" else str(x).strip()


def main():
    df = pd.read_csv(PROFILE, encoding="cp949", dtype=str)
    rows = [
        {
            "player_id": val(r["선수코드"]),
            "position": val(r["포지션"]),
            "back_number": int(float(r["등번호"])) if val(r["등번호"]) else None,
            "birth_date": val(r["생년월일"]),
            "bats_throws": val(r["투타"]),
        }
        for _, r in df.iterrows()
    ]
    print(f"프로필 {len(rows)}명 읽음")

    driver = get_driver()
    ids = [r["player_id"] for r in rows]
    found = run(driver, "MATCH (p:Player) WHERE p.player_id IN $ids RETURN count(p) AS n", ids=ids)[0]["n"]
    total = run(driver, "MATCH (p:Player) RETURN count(p) AS n")[0]["n"]
    print(f"DB 선수 {total}명 중 프로필과 맞는 선수 {found}명")

    load_rows(driver, Q, rows, "선수 프로필")

    missing = run(driver, "MATCH (p:Player) WHERE p.birth_date IS NULL RETURN p.player_id AS id, p.name AS 이름 LIMIT 10")
    print("프로필이 없는 DB 선수 (없어야 정상):", missing or "없음")
    print(run(driver, "MATCH (p:Player) RETURN p.position AS 포지션, count(*) AS 인원 ORDER BY 인원 DESC"))
    driver.close()


if __name__ == "__main__":
    main()
