"""
원본 기록(parquet)을 리비전을 고정해 받는다. 팀원 모두 같은 파일을 쓰게 하려는 것이다.
    python scripts/get_data.py                 # 2024~2026 → data/kbo_pbp/
    python scripts/get_data.py --with-2023     # 04_count_rules.py 비교용 2023도
    python scripts/get_data.py --dest D:/kbo   # 다른 폴더 (.env의 KBO_PBP_DIR도 같이 바꾼다)

출처: Hugging Face slothman3878/kbo_playbyplay (CC BY 4.0), 리비전 6afc8af (2026-07-26 경기까지)
이미 받은 파일은 SHA-256이 맞으면 건너뛰고, 다르면 다시 받는다.
"""
import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVISION = "6afc8af044e3bba5f326b688e8cb41d7ff7065ec"
URL = "https://huggingface.co/datasets/slothman3878/kbo_playbyplay/resolve/{rev}/v0/{name}"
SHA256 = {  # statscene-neo4j/data/raw/kbo_pbp/SHA256SUMS 와 같다
    "kbo_pbp_2023.parquet": "818f6016655b02fe48b8118281d1b04bfe3548d376fdc70131a41ea539341edb",
    "kbo_pbp_2024.parquet": "8332cd716cf0126a4ab0bf390383f43deff22ab320a57fb70d02b31025bdf553",
    "kbo_pbp_2025.parquet": "2c824919495809722a5ff0290a823ff9a44d88f61640ad9b288ff3dca2652f2c",
    "kbo_pbp_2026.parquet": "9d330311d28371806028b878191fcc85b9170839c8951b00ff9c64ec8aa28630",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="data/kbo_pbp", help="받을 폴더 (상대 경로는 BASEON 폴더 기준)")
    ap.add_argument("--with-2023", action="store_true", help="2023 파일도 받는다 (서비스에는 안 씀)")
    args = ap.parse_args()

    dest = Path(args.dest)
    if not dest.is_absolute():
        dest = ROOT / dest
    dest.mkdir(parents=True, exist_ok=True)

    names = [n for n in SHA256 if args.with_2023 or "2023" not in n]
    for name in names:
        path = dest / name
        if path.exists() and sha256(path) == SHA256[name]:
            print(f"  {name}: 이미 있음 (확인 완료)")
            continue
        print(f"  {name}: 받는 중…")
        tmp = path.with_suffix(".part")
        req = urllib.request.Request(URL.format(rev=REVISION, name=name), headers={"User-Agent": "BASEON-capstone"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        if sha256(tmp) != SHA256[name]:
            tmp.unlink()
            raise SystemExit(f"{name}: SHA-256이 다릅니다. 받은 파일을 지웠습니다.")
        tmp.replace(path)
        print(f"  {name}: 완료 (확인 완료)")
    (dest / "REVISION").write_text(REVISION + "\n", encoding="utf-8")
    print(f"\n저장 위치: {dest}")


if __name__ == "__main__":
    main()
