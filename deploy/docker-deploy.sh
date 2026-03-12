#!/bin/bash
#===============================================================
# NanoClaw Docker 배포 스크립트 (Git Clone 기반)
#
# 최초 설치:
#   curl -sL https://raw.githubusercontent.com/<OWNER>/nanoclaw/main/deploy/docker-deploy.sh | bash -s setup
#   또는:
#   git clone https://github.com/<OWNER>/nanoclaw.git /opt/nanoclaw
#   cd /opt/nanoclaw && ./deploy/docker-deploy.sh setup
#
# 명령어:
#   ./deploy/docker-deploy.sh setup     최초 클론 + 빌드 + 실행
#   ./deploy/docker-deploy.sh update    git pull + 재빌드 + 재시작
#   ./deploy/docker-deploy.sh stop      중지
#   ./deploy/docker-deploy.sh logs      로그 보기
#   ./deploy/docker-deploy.sh status    상태 확인
#   ./deploy/docker-deploy.sh shell     컨테이너 접속
#   ./deploy/docker-deploy.sh db-backup DB 백업
#===============================================================

set -e

CONTAINER_NAME="cowork-bot-emission-factor-collector"
IMAGE_NAME="cowork-bot-emission-factor-collector"
APP_DIR="$HOME/projects/cowork"
# ※ 실제 GitHub 리포 주소로 변경하세요
GIT_REPO="https://github.com/junsun0708/cowork.git"
GIT_BRANCH="main"

# 컬러 출력
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[NanoClaw]${NC} $1"; }
warn() { echo -e "${YELLOW}[경고]${NC} $1"; }
err()  { echo -e "${RED}[오류]${NC} $1"; exit 1; }
info() { echo -e "${CYAN}[안내]${NC} $1"; }

# Docker 설치 확인
check_docker() {
    if ! command -v docker &>/dev/null; then
        err "Docker가 설치되어 있지 않습니다.\n  설치: https://docs.docker.com/engine/install/"
    fi
    if ! docker compose version &>/dev/null; then
        err "Docker Compose V2가 필요합니다.\n  설치: https://docs.docker.com/compose/install/"
    fi
}

# .env 파일 확인
check_env() {
    if [ ! -f "$APP_DIR/.env" ]; then
        warn ".env 파일이 없습니다. .env.example에서 복사합니다..."
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        echo ""
        err ".env 파일에 실제 Slack 토큰을 입력한 후 다시 실행하세요:\n  vi $APP_DIR/.env"
    fi

    if grep -q "YOUR-BOT-TOKEN" "$APP_DIR/.env"; then
        err ".env 파일에 실제 Slack 토큰을 입력해주세요:\n  vi $APP_DIR/.env"
    fi
}

# Git 변경사항 요약
show_changes() {
    cd "$APP_DIR"
    local PREV_HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo "none")
    git pull origin $GIT_BRANCH --ff-only
    local CURR_HEAD=$(git rev-parse --short HEAD)

    if [ "$PREV_HEAD" != "$CURR_HEAD" ]; then
        log "변경사항 ($PREV_HEAD → $CURR_HEAD):"
        git log --oneline "$PREV_HEAD..$CURR_HEAD" 2>/dev/null | head -10 | sed 's/^/  /'
    else
        log "이미 최신 상태입니다."
    fi
}

case "${1:-help}" in

    # ──────────────────────────────────────────
    # 최초 설치: git clone → .env 설정 → 빌드 → 실행
    # ──────────────────────────────────────────
    setup)
        log "=== NanoClaw 최초 배포 (Git Clone) ==="
        check_docker

        # 1. Git Clone
        if [ -d "$APP_DIR/.git" ]; then
            log "기존 저장소 발견, pull 실행..."
            cd "$APP_DIR"
            git pull origin $GIT_BRANCH --ff-only
        else
            log "저장소 클론: $GIT_REPO → $APP_DIR"
            git clone -b $GIT_BRANCH "$GIT_REPO" "$APP_DIR"
        fi

        cd "$APP_DIR"

        # 2. .env 설정
        if [ ! -f .env ]; then
            cp .env.example .env
            echo ""
            info "=== .env 파일이 생성되었습니다 ==="
            info "Slack 토큰을 입력해주세요:"
            echo ""
            echo "  vi $APP_DIR/.env"
            echo ""
            echo "  필요한 값:"
            echo "    SLACK_BOT_TOKEN=xoxb-..."
            echo "    SLACK_APP_TOKEN=xapp-..."
            echo ""
            info "토큰 입력 후 다시 실행:"
            echo "  cd $APP_DIR && ./deploy/docker-deploy.sh setup"
            exit 0
        fi

        check_env

        # 3. 데이터 디렉토리
        mkdir -p data logs output

        # 4. Docker 빌드 + 실행
        log "Docker 이미지 빌드..."
        docker compose build

        log "컨테이너 시작..."
        docker compose up -d

        sleep 3
        if docker ps --filter "name=$CONTAINER_NAME" --format '{{.Status}}' | grep -q "Up"; then
            log "=== 배포 완료! ==="
            echo ""
            echo "  컨테이너: $CONTAINER_NAME"
            echo "  이미지:   $IMAGE_NAME"
            echo "  소스:     $APP_DIR (git: $GIT_BRANCH)"
            echo ""
            echo "  로그:     ./deploy/docker-deploy.sh logs"
            echo "  상태:     ./deploy/docker-deploy.sh status"
            echo "  업데이트: ./deploy/docker-deploy.sh update"
            echo "  중지:     ./deploy/docker-deploy.sh stop"
            echo ""
            docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
        else
            err "컨테이너 시작 실패!\n  로그 확인: docker compose logs"
        fi
        ;;

    # ──────────────────────────────────────────
    # 업데이트: git pull → 재빌드 → 재시작
    # ──────────────────────────────────────────
    update)
        log "=== NanoClaw 업데이트 (Git Pull + Rebuild) ==="
        check_docker

        if [ ! -d "$APP_DIR/.git" ]; then
            err "$APP_DIR 에 Git 저장소가 없습니다. 먼저 setup을 실행하세요."
        fi

        cd "$APP_DIR"
        check_env

        # Git Pull
        log "최신 소스 가져오기..."
        show_changes

        # 재빌드 + 재시작
        log "이미지 재빌드 + 컨테이너 재시작..."
        docker compose up -d --build

        sleep 3
        log "=== 업데이트 완료! ==="
        docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
        ;;

    # ──────────────────────────────────────────
    # 기본 관리 명령
    # ──────────────────────────────────────────
    stop)
        cd "$APP_DIR"
        log "컨테이너 중지..."
        docker compose down
        log "중지 완료"
        ;;

    restart)
        cd "$APP_DIR"
        log "컨테이너 재시작..."
        docker compose restart
        log "재시작 완료"
        ;;

    logs)
        cd "$APP_DIR"
        docker compose logs -f --tail=100
        ;;

    status)
        echo ""
        log "=== 컨테이너 상태 ==="
        docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}" 2>/dev/null || echo "  (실행 중인 컨테이너 없음)"

        echo ""
        log "=== Git 정보 ==="
        if [ -d "$APP_DIR/.git" ]; then
            cd "$APP_DIR"
            echo "  브랜치: $(git branch --show-current)"
            echo "  커밋:   $(git log -1 --format='%h %s (%cr)')"
            echo "  원격:   $(git remote get-url origin 2>/dev/null || echo 'N/A')"
        else
            echo "  (Git 저장소 없음)"
        fi

        echo ""
        log "=== 볼륨 ==="
        docker volume ls --filter "name=nanoclaw" --format "table {{.Name}}\t{{.Driver}}" 2>/dev/null

        echo ""
        log "=== 최근 로그 (10줄) ==="
        cd "$APP_DIR" 2>/dev/null && docker compose logs --tail=10 2>/dev/null || echo "  (로그 없음)"
        ;;

    shell)
        log "컨테이너 접속..."
        docker exec -it $CONTAINER_NAME /bin/bash || docker exec -it $CONTAINER_NAME /bin/sh
        ;;

    db-backup)
        BACKUP_FILE="nanoclaw-db-backup-$(date +%Y%m%d-%H%M%S).db"
        log "DB 백업: $BACKUP_FILE"
        docker cp "$CONTAINER_NAME:/app/data/nanoclaw.db" "./$BACKUP_FILE"
        log "백업 완료: $(ls -lh $BACKUP_FILE | awk '{print $5}')"
        ;;

    *)
        echo ""
        echo "NanoClaw Docker 배포 관리 (Git 기반)"
        echo ""
        echo "사용법: $0 {setup|update|stop|restart|logs|status|shell|db-backup}"
        echo ""
        echo "  setup      최초 설치 (git clone + 빌드 + 실행)"
        echo "  update     업데이트 (git pull + 재빌드 + 재시작)"
        echo "  stop       중지"
        echo "  restart    재시작"
        echo "  logs       로그 보기 (실시간)"
        echo "  status     상태 + Git 정보 확인"
        echo "  shell      컨테이너 접속"
        echo "  db-backup  DB 백업 파일 생성"
        echo ""
        echo "최초 설치:"
        echo "  git clone $GIT_REPO $APP_DIR"
        echo "  cd $APP_DIR"
        echo "  cp .env.example .env && vi .env"
        echo "  ./deploy/docker-deploy.sh setup"
        echo ""
        ;;
esac
