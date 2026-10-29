"""선수 사진 · 구단 엠블럼을 화면 폴더로 복사한다 (저장소에는 넣지 않는다 — 팀 문서 「데이터_이용.md」).

    python scripts/sync_media.py

저장소 맨 위 photos/(선수 ID.jpg) · logos/(구단 코드.png)를 frontend/public/media/로 복사한다.
scripts/upscale_media.py로 만든 4배 폴더(photos_x4/ · logos_x4/)가 있으면 그 파일을 먼저 쓴다.
frontend/public/media/는 git 제외. 정적 빌드(out/)에 같이 들어가 서버에서 /media/… 로 나간다.
파일이 없는 선수는 화면이 이름 첫 글자로 대신 그린다.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "frontend" / "public" / "media"

for name in ("photos", "logos"):
    src, big = ROOT / name, ROOT / f"{name}_x4"
    if not src.is_dir():
        print(f"{name}/ 없음 — 건너뜀 (화면은 대체 표시)")
        continue
    out = DEST / name
    out.mkdir(parents=True, exist_ok=True)
    n = n_big = 0
    for f in src.iterdir():
        if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            pick = big / f.name if (big / f.name).exists() else f  # 4배가 있으면 4배
            t = out / f.name
            if not t.exists() or t.stat().st_mtime < pick.stat().st_mtime or t.stat().st_size != pick.stat().st_size:
                shutil.copy2(pick, t)
                n += 1
            n_big += pick.parent == big
    print(f"{name}: {n}개 복사 (4배 {n_big}개) → {out.relative_to(ROOT)}")
