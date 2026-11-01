#!/usr/bin/env bash
# EC2를 처음 만들었을 때 한 번만 (Ubuntu 24.04 · 26.04 LTS arm64, t4g.small — 26.04에서 실제로 돌림). docs/배포.md 2장
#   scp deploy/server_setup.sh ubuntu@<서버>:~ && ssh ubuntu@<서버> 'sudo bash server_setup.sh'
# 스왑 2GB · Docker(compose 포함) · SSH 잠그기 · /opt/baseon 폴더. 두 번 돌려도 된다
set -euo pipefail

USER_NAME="${SUDO_USER:-ubuntu}"

# 1) 스왑 — 메모리 2GB에 Neo4j(JVM) + API + Caddy가 1.2~1.5GB를 쓴다. 이미지 빌드 · DB 적재 때 넘치지 않게
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
sysctl -q vm.swappiness=10
echo 'vm.swappiness=10' > /etc/sysctl.d/99-baseon.conf

# 2) Docker 공식 apt 저장소 (docker compose 플러그인 포함)
if ! command -v docker >/dev/null; then
  apt-get update -q
  apt-get install -y -q ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker "$USER_NAME"

# 컨테이너 로그가 디스크를 채우지 않게
mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
  echo '{"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "3"}}' > /etc/docker/daemon.json
  systemctl restart docker
fi
systemctl enable --now docker

# 3) SSH — 보안 그룹은 22를 어디서나 연다(집 IP가 바뀌어도 배포가 되게). 그 대신 키로만 들어오고,
#    여러 번 틀린 IP는 막고(fail2ban), 보안 업데이트는 자동으로 (docs/배포.md 2장)
cat > /etc/ssh/sshd_config.d/99-baseon.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
MaxAuthTries 3
EOF
sshd -t && systemctl try-reload-or-restart ssh
apt-get update -q
apt-get install -y -q fail2ban unattended-upgrades
systemctl enable --now fail2ban || echo "fail2ban을 켜지 못했다 — systemctl status fail2ban 확인"

# 4) 배포 폴더 — app(코드 · 화면, deploy.py code가 통째로 바꾼다) · dumps(DB 덤프)
mkdir -p /opt/baseon/app /opt/baseon/dumps
chown -R "$USER_NAME":"$USER_NAME" /opt/baseon

echo "끝. 한 번 나갔다 다시 접속하면 sudo 없이 docker를 쓸 수 있다."
docker --version
docker compose version
free -h
