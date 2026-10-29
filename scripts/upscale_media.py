"""선수 사진 · 구단 엠블럼을 4배로 키운다 (원본이 작아 고해상도 화면에서 깨지기 때문).

    python scripts/upscale_media.py --esrgan <realesrgan-ncnn-vulkan.exe 경로>

원본은 KBO 공식 사이트의 사진 94×118 · 엠블럼 64×41 / 97×65가 가장 큰 크기라(10-29 확인) AI로 키운다.
- 도구: Real-ESRGAN ncnn-vulkan (github.com/xinntao/Real-ESRGAN 릴리스 v0.2.5.0, 그래픽카드 사용)
- 사진: AI 4배(realesrgan-x4plus)만 쓰면 피부가 매끈해져 그림처럼 보인다 → 같은 4배 크기에서
        「AI 30% + 원본 고품질 확대 · 선명화 70%」로 섞는다 (10-29 비교 E안). 결과 photos_x4/*.jpg (376×472)
- 엠블럼: 그림용 모델(realesrgan-x4plus-anime) 4배 그대로. 결과 logos_x4/*.png
원본 photos/ · logos/는 그대로 둔다. 결과 폴더도 저장소에 넣지 않는다(.gitignore).
이미 만든 파일은 건너뛴다. 다 만든 뒤 scripts/sync_media.py가 *_x4/를 먼저 쓴다.
"""
import argparse
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
AI_WEIGHT = 0.3          # 섞을 때 AI 쪽 비율 (E안)
SHARPEN = ImageFilter.UnsharpMask(radius=2.5, percent=90, threshold=2)  # 4배 크기 기준 선명화


def run_esrgan(exe: Path, src: Path, dst: Path, model: str) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(exe), "-i", str(src), "-o", str(dst), "-n", model, "-s", "4", "-f", "png"],
                   cwd=exe.parent, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def photos(exe: Path, limit: int | None) -> None:
    src_dir, out_dir = ROOT / "photos", ROOT / "photos_x4"
    out_dir.mkdir(exist_ok=True)
    todo = [f for f in sorted(src_dir.glob("*.jpg")) if not (out_dir / f.name).exists()][:limit]
    print(f"사진: {len(todo)}장 처리 (이미 있음 {len(list(out_dir.glob('*.jpg')))}장)")
    if not todo:
        return
    with tempfile.TemporaryDirectory() as tmp:
        tin, tout = Path(tmp) / "in", Path(tmp) / "out"
        tin.mkdir()
        for f in todo:
            shutil.copy2(f, tin / f.name)
        t = time.time()
        run_esrgan(exe, tin, tout, "realesrgan-x4plus")
        print(f"  AI 4배 {time.time() - t:.0f}초")
        for f in todo:
            orig = Image.open(f).convert("RGB")
            ai = Image.open(tout / f"{f.stem}.png").convert("RGB")
            base = orig.resize(ai.size, Image.LANCZOS).filter(SHARPEN)
            Image.blend(base, ai, AI_WEIGHT).save(out_dir / f.name, quality=92)
    print(f"  → {out_dir.relative_to(ROOT)}")


def logos(exe: Path) -> None:
    src_dir, out_dir = ROOT / "logos", ROOT / "logos_x4"
    with tempfile.TemporaryDirectory() as tmp:
        tin = Path(tmp) / "in"
        tin.mkdir()
        for f in sorted(src_dir.glob("*.png")):
            Image.open(f).convert("RGBA").save(tin / f.name)  # 팔레트(P) PNG는 투명을 살리려고 RGBA로
        run_esrgan(exe, tin, out_dir, "realesrgan-x4plus-anime")
    print(f"엠블럼: {len(list(out_dir.glob('*.png')))}개 → {out_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--esrgan", type=Path, required=True, help="realesrgan-ncnn-vulkan.exe 경로 (models/ 폴더가 옆에 있어야 함)")
    ap.add_argument("--limit", type=int, default=None, help="사진 몇 장만 (시험용)")
    ap.add_argument("--skip-logos", action="store_true")
    a = ap.parse_args()
    if not a.skip_logos:
        logos(a.esrgan)
    photos(a.esrgan, a.limit)
