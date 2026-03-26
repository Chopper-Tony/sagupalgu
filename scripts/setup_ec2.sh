#!/bin/bash
# ── EC2 초기 세팅 스크립트 ──────────────────────────────────
# Ubuntu 22.04 기준. EC2에 SSH 접속 후 최초 1회 실행.
#
# 사용법:
#   ssh -i your-key.pem ubuntu@EC2_PUBLIC_IP
#   curl -fsSL https://raw.githubusercontent.com/Chopper-Tony/sagupalgu/main/scripts/setup_ec2.sh | bash
# ──────────────────────────────────────────────────────────

set -euo pipefail

echo "=== 1/5 시스템 업데이트 ==="
sudo apt-get update -y
sudo apt-get upgrade -y

echo "=== 2/5 Docker 설치 ==="
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
  echo "Docker 설치 완료. 재로그인 후 docker 명령 사용 가능."
fi

echo "=== 3/5 Docker Compose 설치 ==="
if ! command -v docker compose &>/dev/null; then
  sudo apt-get install -y docker-compose-plugin
fi

echo "=== 4/5 프로젝트 클론 ==="
if [ ! -d ~/sagupalgu ]; then
  git clone https://github.com/Chopper-Tony/sagupalgu.git ~/sagupalgu
fi

echo "=== 5/5 환경 변수 설정 ==="
cd ~/sagupalgu
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "=========================================="
  echo "  .env 파일이 생성됐습니다."
  echo "  nano ~/sagupalgu/.env 로 API 키를 입력하세요."
  echo "=========================================="
fi

echo ""
echo "=== 세팅 완료! ==="
echo ""
echo "다음 단계:"
echo "  1. nano ~/sagupalgu/.env  → API 키 입력"
echo "  2. cd ~/sagupalgu && docker compose up -d --build"
echo "  3. http://EC2_PUBLIC_IP 로 접속"
echo ""
