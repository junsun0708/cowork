#!/bin/bash
#===============================================================
# NanoClaw 리눅스 서버 배포 스크립트
#
# 사용법:
#   1. 이 파일을 서버로 복사
#   2. chmod +x deploy.sh
#   3. sudo ./deploy.sh          (최초 설치)
#   4. sudo ./deploy.sh update   (업데이트)
#===============================================================

set -e

APP_NAME="nanoclaw"
APP_DIR="/opt/nanoclaw"
APP_USER="nanoclaw"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="nanoclaw.service"

# 컬러 출력
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[NanoClaw]${NC} $1"; }
warn() { echo -e "${YELLOW}[경고]${NC} $1"; }
err()  { echo -e "${RED}[오류]${NC} $1"; exit 1; }

#---------------------------------------------------------------
# 0. root 확인
#---------------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
    err "root 권한이 필요합니다. sudo ./deploy.sh 로 실행하세요."
fi

#---------------------------------------------------------------
# 업데이트 모드
#---------------------------------------------------------------
if [ "$1" == "update" ]; then
    log "=== NanoClaw 업데이트 모드 ==="

    if [ ! -d "$APP_DIR" ]; then
        err "$APP_DIR 가 없습니다. 먼저 초기 설치를 진행하세요."
    fi

    log "서비스 중지..."
    systemctl stop $SERVICE_NAME 2>/dev/null || true

    log "소스 복사 (현재 디렉토리 → $APP_DIR)..."
    SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
    rsync -av --exclude='venv' --exclude='.env' --exclude='data/nanoclaw.db*' \
          --exclude='__pycache__' --exclude='logs/*.log' --exclude='output/*' \
          "$SCRIPT_DIR/" "$APP_DIR/"

    log "의존성 업데이트..."
    sudo -u $APP_USER $VENV_DIR/bin/pip install -r $APP_DIR/requirements.txt -q

    log "서비스 재시작..."
    systemctl daemon-reload
    systemctl start $SERVICE_NAME

    log "=== 업데이트 완료! ==="
    systemctl status $SERVICE_NAME --no-pager
    exit 0
fi

#---------------------------------------------------------------
# 1. 시스템 의존성 설치
#---------------------------------------------------------------
log "=== NanoClaw 초기 배포 시작 ==="

log "시스템 패키지 설치..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip rsync

# Java (tabula-py 의존성)
if ! command -v java &>/dev/null; then
    log "Java 설치 (tabula-py 의존성)..."
    apt-get install -y -qq default-jre-headless
fi

#---------------------------------------------------------------
# 2. 사용자 생성
#---------------------------------------------------------------
if ! id "$APP_USER" &>/dev/null; then
    log "시스템 사용자 '$APP_USER' 생성..."
    useradd --system --shell /bin/false --home-dir $APP_DIR $APP_USER
fi

#---------------------------------------------------------------
# 3. 소스 복사
#---------------------------------------------------------------
log "소스 복사..."
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p $APP_DIR/{data,logs,output}

rsync -av --exclude='venv' --exclude='.env' --exclude='data/nanoclaw.db*' \
      --exclude='__pycache__' --exclude='logs/*.log' --exclude='output/*' \
      --exclude='deploy' \
      "$SCRIPT_DIR/" "$APP_DIR/"

# deploy 폴더도 복사 (업데이트용)
cp -r "$SCRIPT_DIR/deploy" "$APP_DIR/"

#---------------------------------------------------------------
# 4. Python 가상환경 + 의존성
#---------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    log "Python 가상환경 생성..."
    python3 -m venv $VENV_DIR
fi

log "의존성 설치..."
$VENV_DIR/bin/pip install -r $APP_DIR/requirements.txt -q

#---------------------------------------------------------------
# 5. .env 설정
#---------------------------------------------------------------
if [ ! -f "$APP_DIR/.env" ]; then
    log ".env 파일 생성..."
    cat > "$APP_DIR/.env" << 'ENVEOF'
# NanoClaw 환경변수 설정
# ※ 실제 토큰값으로 변경하세요!

# Slack Bot Token (OAuth & Permissions에서 발급)
SLACK_BOT_TOKEN=xoxb-YOUR-BOT-TOKEN

# Slack App Token (Socket Mode 활성화 시 발급)
SLACK_APP_TOKEN=xapp-YOUR-APP-TOKEN

# Slack 채널 ID
SLACK_CHANNEL_ID=C0AKQDRG7EH

# 주간 동기화 스케줄
NANOCLAW_SYNC_DAY=0
NANOCLAW_SYNC_HOUR=9
NANOCLAW_SYNC_COUNTRIES=KR,US,JP,DE,GB,FR,AU
ENVEOF

    warn ".env 파일에 실제 Slack 토큰을 설정해야 합니다!"
    warn "편집: sudo vi $APP_DIR/.env"
else
    log ".env 파일 이미 존재 (유지)"
fi

#---------------------------------------------------------------
# 6. 권한 설정
#---------------------------------------------------------------
log "파일 권한 설정..."
chown -R $APP_USER:$APP_USER $APP_DIR
chmod 600 $APP_DIR/.env

#---------------------------------------------------------------
# 7. systemd 서비스 등록
#---------------------------------------------------------------
log "systemd 서비스 등록..."
cp $APP_DIR/deploy/nanoclaw.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable $SERVICE_NAME

#---------------------------------------------------------------
# 8. 서비스 시작
#---------------------------------------------------------------
log "서비스 시작..."
systemctl start $SERVICE_NAME

sleep 3
if systemctl is-active --quiet $SERVICE_NAME; then
    log "=== 배포 완료! ==="
    echo ""
    echo "  상태 확인:  sudo systemctl status nanoclaw"
    echo "  로그 보기:  sudo journalctl -u nanoclaw -f"
    echo "  재시작:     sudo systemctl restart nanoclaw"
    echo "  중지:       sudo systemctl stop nanoclaw"
    echo "  업데이트:   sudo ./deploy.sh update"
    echo ""
    systemctl status $SERVICE_NAME --no-pager
else
    err "서비스 시작 실패! 로그를 확인하세요: journalctl -u nanoclaw -e"
fi
