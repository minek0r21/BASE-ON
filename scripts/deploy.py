"""
서버 배포 — docs/배포.md. PC에서 돌린다. 서버에는 코드 · 화면 · DB 덤프만 올리고, 적재 · 검수는 PC에서만 한다.

    python scripts/deploy.py setup     # 처음 한 번: deploy/server_setup.sh를 올려 실행 (스왑 · Docker · /opt/baseon)
    python scripts/deploy.py code      # 화면 빌드(npm run build) + 커밋된 코드 → 서버, docker compose up --build
    python scripts/deploy.py db        # PC DB 덤프(Neo4j 잠시 멈춤) → 서버 DB를 통째로 바꾼다
    python scripts/deploy.py status    # 컨테이너 · 메모리 · 디스크 · API 응답
    python scripts/deploy.py code --local <폴더>   # 서버 대신 이 PC의 폴더에 똑같이 (시험용, http://localhost:8080)

.env (저장소 맨 위, PC)
    DEPLOY_HOST=ubuntu@<서버 IP 또는 도메인>
    DEPLOY_KEY=C:/Users/<나>/.ssh/baseon.pem     # EC2 키 페어
    DEPLOY_DIR=/opt/baseon                        # 생략하면 이 값
서버의 deploy/.env(비밀번호 · 도메인)는 서버에만 있고, code가 지우지 않는다.
이 스크립트는 표준 라이브러리와 Windows 기본 ssh · scp만 쓴다.
"""
import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "out"
STAGE = ROOT / "data" / "deploy"       # 올리기 전 묶음 · 덤프 (git 제외)


def read_env() -> dict:
    """.env를 읽는다 (값은 로그에 남기지 않는다)"""
    env = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$", line)
            if m and not line.lstrip().startswith("#"):
                env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return env

# 서버에서 code가 하는 일: 새 폴더에 풀기 → deploy/.env 옮기기 → 바꿔 끼우기 → 빌드 · 켜기.
# Caddy는 화면 폴더를 연결해 두므로 폴더를 바꾼 뒤 다시 만들어야 새 화면을 본다
REMOTE_CODE = r"""
set -euo pipefail
cd "$DEPLOY_DIR"
rm -rf app.new && mkdir app.new
tar xzf release.tar.gz -C app.new && rm release.tar.gz
if [ -f app/deploy/.env ]; then cp app/deploy/.env app.new/deploy/.env; fi
rm -rf app.old
if [ -d app ]; then mv app app.old; fi
mv app.new app
cd app/deploy
if [ ! -f .env ]; then
  echo "deploy/.env가 없다 — 서버에서 cp $DEPLOY_DIR/app/deploy/.env.example $DEPLOY_DIR/app/deploy/.env 후 값을 채우고 다시 code"
  exit 3
fi
docker compose up -d --build --remove-orphans
docker compose up -d --force-recreate --no-deps caddy
docker image prune -f >/dev/null
docker compose ps --format '{{.Service}} {{.Status}}'
"""

# 서버에서 db가 하는 일: API · Neo4j를 멈추고 덤프를 덮어쓴 뒤 다시 켠다 (계정은 system DB라 그대로).
# 스크립트를 bash -s 표준 입력으로 넘기므로 docker compose run · exec는 </dev/null — 아니면 남은 줄을 먹어 버린다
REMOTE_DB = r"""
set -euo pipefail
cd "$DEPLOY_DIR/app/deploy"
docker compose stop api neo4j
docker compose run --rm --no-deps -T neo4j neo4j-admin database load neo4j --from-path=/dumps --overwrite-destination=true </dev/null
docker compose up -d
for i in $(seq 1 40); do
  if docker compose exec -T api python -c "import urllib.request as u; u.urlopen('http://localhost:8000/api/v1/health', timeout=5)" </dev/null 2>/dev/null; then
    echo "API 응답 확인"; exit 0
  fi
  sleep 5
done
echo "API가 200초 안에 응답하지 않는다"; exit 4
"""

REMOTE_STATUS = r"""
cd "$DEPLOY_DIR/app/deploy" 2>/dev/null || { echo "아직 code를 올리지 않았다"; exit 0; }
docker compose ps --format '{{.Service}} {{.Status}}'
docker stats --no-stream --format '{{.Name}} {{.MemUsage}} CPU {{.CPUPerc}}'
free -h | head -3
df -h / | tail -1
docker compose exec -T api python -c "import urllib.request as u, json; print('meta', json.load(u.urlopen('http://localhost:8000/api/v1/meta', timeout=5)))" </dev/null
"""


class Target:
    """서버(ssh · scp) 또는 시험용 로컬 폴더(bash · 복사)"""

    def __init__(self, env: dict, local: str | None):
        self.local = Path(local).resolve() if local else None
        if self.local:
            self.dir = self.local.as_posix()
            return
        self.host = env.get("DEPLOY_HOST") or sys.exit(".env에 DEPLOY_HOST(ubuntu@<서버>)가 없다")
        self.dir = env.get("DEPLOY_DIR") or "/opt/baseon"
        self.ssh_opts = ["-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=30"]
        if env.get("DEPLOY_KEY"):
            self.ssh_opts += ["-i", env["DEPLOY_KEY"], "-o", "IdentitiesOnly=yes"]  # 서버는 시도 3번까지 (server_setup.sh)

    def put(self, src: Path, dst: str):
        print(f"올리기 {src.name} ({src.stat().st_size / 1e6:.0f} MB) → {dst}", flush=True)
        if self.local:
            target = Path(dst)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)
        else:
            run(["scp", *self.ssh_opts, str(src), f"{self.host}:{dst}"])

    def sh(self, script: str, check: bool = True) -> int:
        script = f'DEPLOY_DIR="{self.dir}"\n' + script
        if self.local:
            # 시험용: 서버와 겹치지 않는 프로젝트 이름 · 포트 (로컬 개발 환경이 켜져 있어도 된다)
            # MSYS_NO_PATHCONV: Git Bash가 /dumps 같은 컨테이너 안 경로를 Windows 경로로 바꾸지 않게
            env = {**os.environ, "COMPOSE_PROJECT_NAME": "baseon-deploytest", "HTTP_PORT": "8080", "HTTPS_PORT": "8443",
                   "MSYS_NO_PATHCONV": "1"}
            cmd = [shutil.which("bash") or "bash", "-s"]
        else:
            env, cmd = None, ["ssh", *self.ssh_opts, self.host, "bash -s"]
        p = subprocess.run(cmd, input=script.replace("\r\n", "\n").encode(), env=env)
        if check and p.returncode:
            sys.exit(f"서버 명령 실패 (종료 코드 {p.returncode})")
        return p.returncode


def run(cmd: list[str], **kw):
    print("$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


# ------------------------------------------------------------------ code
def build_frontend():
    env = {k: v for k, v in os.environ.items() if k != "NEXT_PUBLIC_API_BASE"}  # 배포 빌드는 같은 주소의 /api/v1
    run(["npm", "run", "build"], cwd=ROOT / "frontend", env=env, shell=os.name == "nt")
    if not (OUT / "index.html").exists():
        sys.exit("frontend/out/index.html이 없다 — 빌드 실패")


def make_release() -> Path:
    """커밋된 코드(git archive HEAD) + 방금 빌드한 frontend/out 을 한 묶음으로"""
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        print("주의: 커밋하지 않은 변경은 올라가지 않는다 (git archive HEAD)\n" + dirty, flush=True)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    code = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, capture_output=True, check=True).stdout
    STAGE.mkdir(parents=True, exist_ok=True)
    out = STAGE / "release.tar.gz"
    with tarfile.open(out, "w:gz") as dst, tarfile.open(fileobj=io.BytesIO(code)) as src:
        for m in src.getmembers():
            dst.addfile(m, src.extractfile(m) if m.isfile() else None)
        dst.add(OUT, arcname="frontend/out")
        info = tarfile.TarInfo("RELEASE")
        stamp = f"{head} {time.strftime('%Y-%m-%d %H:%M')}\n".encode()
        info.size = len(stamp)
        dst.addfile(info, io.BytesIO(stamp))
    print(f"묶음 {out.name}: 커밋 {head}", flush=True)
    return out


def cmd_code(t: Target, skip_build: bool):
    if not skip_build:
        build_frontend()
    pkg = make_release()
    t.put(pkg, f"{t.dir}/release.tar.gz")
    t.sh(REMOTE_CODE)


# ------------------------------------------------------------------ db
def local_volume(env: dict) -> tuple[str, str]:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    image = re.search(r"^\s*image:\s*(neo4j:\S+)", text, re.M).group(1)
    server = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    if image != re.search(r"^\s*image:\s*(neo4j:\S+)", server, re.M).group(1):
        sys.exit("로컬과 서버의 Neo4j 버전이 다르다 — docker-compose.yml 두 개를 맞춘다")
    project = env.get("COMPOSE_PROJECT_NAME") or re.search(r"^name:\s*(\S+)", text, re.M).group(1)
    return image, f"{project}_neo4jdata"


def dump_local(env: dict) -> Path:
    """PC Neo4j를 잠시 멈추고 덤프 → 다시 켠다 (Community는 켜 둔 채 덤프할 수 없다)"""
    image, volume = local_volume(env)
    STAGE.mkdir(parents=True, exist_ok=True)
    run(["docker", "compose", "stop", "neo4j"], cwd=ROOT)
    try:
        run(["docker", "run", "--rm", "-v", f"{volume}:/data", "-v", f"{STAGE}:/backups", image,
             "neo4j-admin", "database", "dump", "neo4j", "--to-path=/backups", "--overwrite-destination=true"])
    finally:
        run(["docker", "compose", "up", "-d", "--wait", "neo4j"], cwd=ROOT)
    return STAGE / "neo4j.dump"


def cmd_db(t: Target, env: dict, dump: str | None):
    src = Path(dump) if dump else dump_local(env)
    t.put(src, f"{t.dir}/dumps/neo4j.dump")
    t.sh(REMOTE_DB)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="서버 배포 (docs/배포.md)")
    ap.add_argument("action", choices=["setup", "code", "db", "status"])
    ap.add_argument("--local", metavar="폴더", help="서버 대신 이 PC의 폴더에 (시험용)")
    ap.add_argument("--skip-build", action="store_true", help="code: 이미 빌드한 frontend/out을 그대로")
    ap.add_argument("--dump", help="db: 새로 덤프하지 않고 이 파일을 올린다 (예: data/deploy/neo4j.dump)")
    a = ap.parse_args()
    env = read_env()
    t = Target(env, a.local)
    if a.action == "setup":
        if t.local:
            sys.exit("setup은 서버에서만")
        t.put(ROOT / "deploy" / "server_setup.sh", "server_setup.sh")
        t.sh("sudo bash server_setup.sh")
    elif a.action == "code":
        cmd_code(t, a.skip_build)
    elif a.action == "db":
        cmd_db(t, env, a.dump)
    else:
        t.sh(REMOTE_STATUS, check=False)


if __name__ == "__main__":
    main()
