#!/bin/bash
#===============================================================
# NanoClaw Docker 배포 스크립트
#
# 사용법:
#   ./docker-deploy.sh              최초 빌드 + 실행
#   ./docker-deploy.sh update       소스 변경 후 재빌드 + 재시작
#   ./docker-deploy.sh stop         중지
#   ./docker-deploy.sh logs         로그 보기
#   ./docker-deploy.sh status       상태 확인
#   ./docker-deploy.sh shell        컨테이너 접속
#   ./docker-deploy.sh db-backup    DB 백업
#===============================================================

set -e

CONTAINER_NAME="cowork-bot-emission-factor-collector"
IMAGE_NAME="cowork-bot-emission-factor-collector"

# 프로젝트 루트로 이동
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# 컬러 출력
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[NanoClaw]${NC} $1"; }
warn() { echo -e "${YELLOW}[경고]${NC} $1"; }
err()  { echo -e "${RED}[오류]${NC} $1"; exit 1; }

# .env 파일 확인
check_env() {
    if [ ! -f ".env" ]; then
        warn ".env 파일이 없습니다. 템플릿에서 생성합니다..."
        cat > .env << 'EOF'
# NanoClaw 환경변수
# ※ 실제 토큰값으로 변경하세요!

SLACK_BOT_TOKEN=xoxb-YOUR-BOT-TOKEN
SLACK_APP_TOKEN=xapp-YOUR-APP-TOKEN
SLACK_CHANNEL_ID=C0AKQDRG7EH

NANOCLAW_SYNC_DAY=0
NANOCLAW_SYNC_HOUR=9
NANOCLAW_SYNC_COUNTRIES=KR,US,JP,DE,GB,FR,AU
EOF
        err ".env 파일에 실제 Slack 토큰을 입력한 후 다시 실행하세요:\n  vi .env"
    fi

    # 토큰 유효성 간단 체크
    if grep -q "YOUR-BOT-TOKEN" .env; then
        err ".env 파일에 실제 Slack 토큰을 입력해주세요:\n  vi .env"
    fi
}

case "${1:-start}" in

    start)
        log "=== NanoClaw Docker 배포 ==="
        check_env

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
            echo ""
            echo "  로그:     ./docker-deploy.sh logs"
            echo "  상태:     ./docker-deploy.sh status"
            echo "  업데이트: ./docker-deploy.sh update"
            echo "  중지:     ./docker-deploy.sh stop"
            echo ""
            docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
        else
            err "컨테이너 시작 실패! 로그 확인: docker compose logs"
        fi
        ;;

    update)
        log "=== NanoClaw 업데이트 ==="
        check_env

        log "이미지 재빌드 + 컨테이너 재시작..."
        docker compose up -d --build

        sleep 3
        log "업데이트 완료!"
        docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
        ;;

    stop)
        log "컨테이너 중지..."
        docker compose down
        log "중지 완료"
        ;;

    logs)
        docker compose logs -f --tail=100
        ;;

    status)
        echo ""
        log "=== 컨테이너 상태 ==="
        docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}" 2>/dev/null || echo "  (실행 중인 컨테이너 없음)"

        echo ""
        log "=== 볼륨 ==="
        docker volume ls --filter "name=nanoclaw" --format "table {{.Name}}\t{{.Driver}}" 2>/dev/null

        echo ""
        log "=== 최근 로그 (10줄) ==="
        docker compose logs --tail=10 2>/dev/null || echo "  (로그 없음)"
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
        echo "사용법: $0 {start|update|stop|logs|status|shell|db-backup}"
        echo ""
        echo "  start      최초 빌드 + 실행"
        echo "  update     소스 변경 후 재빌드 + 재시작"
        echo "  stop       중지"
        echo "  logs       로그 보기 (실시간)"
        echo "  status     상태 확인"
        echo "  shell      컨테이너 접속"
        echo "  db-backup  DB 백업 파일 생성"
        ;;
esac
