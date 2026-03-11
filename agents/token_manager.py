"""
NanoClaw Token Manager
- Slack Token Rotation 자동 갱신
- 토큰 만료 감지 및 헬스체크
- 토큰 저장소 관리 (파일 기반)
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread, Event

import requests

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import BASE_DIR

logger = logging.getLogger("nanoclaw.token_manager")

TOKEN_STORE_PATH = BASE_DIR / "config" / ".tokens.json"


class TokenManager:
    """
    Slack 토큰 자동 관리

    두 가지 모드 지원:
    1. 고정 토큰 (기본): xoxb- 토큰이 만료 안됨 → 헬스체크만 수행
    2. Token Rotation 모드: refresh_token으로 자동 갱신

    Token Rotation 활성화 시 필요한 환경변수:
    - SLACK_CLIENT_ID
    - SLACK_CLIENT_SECRET
    - SLACK_REFRESH_TOKEN (최초 OAuth 인증 시 발급)
    """

    def __init__(self):
        self.bot_token = os.getenv("SLACK_BOT_TOKEN", "")
        self.app_token = os.getenv("SLACK_APP_TOKEN", "")
        self.client_id = os.getenv("SLACK_CLIENT_ID", "")
        self.client_secret = os.getenv("SLACK_CLIENT_SECRET", "")
        self.refresh_token = os.getenv("SLACK_REFRESH_TOKEN", "")

        self.rotation_enabled = bool(self.client_id and self.client_secret and self.refresh_token)
        self._stop_event = Event()
        self._worker = None

        # 토큰 저장소 로드
        self._load_tokens()

    def _load_tokens(self):
        """저장된 토큰 로드"""
        if TOKEN_STORE_PATH.exists():
            try:
                data = json.loads(TOKEN_STORE_PATH.read_text(encoding="utf-8"))
                # 저장된 토큰이 환경변수보다 최신이면 사용
                if data.get("bot_token") and data.get("updated_at"):
                    self.bot_token = data["bot_token"]
                    self.refresh_token = data.get("refresh_token", self.refresh_token)
                    logger.info(
                        f"[TokenManager] 저장된 토큰 로드 (갱신: {data['updated_at']})"
                    )
            except Exception as e:
                logger.warning(f"[TokenManager] 토큰 저장소 로드 실패: {e}")

    def _save_tokens(self):
        """토큰 저장"""
        TOKEN_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "bot_token": self.bot_token,
            "refresh_token": self.refresh_token,
            "updated_at": datetime.now().isoformat(),
        }
        TOKEN_STORE_PATH.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        # 권한 제한 (소유자만 읽기/쓰기)
        TOKEN_STORE_PATH.chmod(0o600)

    def health_check(self) -> dict:
        """Slack API 연결 헬스체크"""
        try:
            resp = requests.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                timeout=10,
            )
            data = resp.json()
            if data.get("ok"):
                return {
                    "healthy": True,
                    "bot_id": data.get("bot_id"),
                    "team": data.get("team"),
                    "user": data.get("user"),
                }
            else:
                error = data.get("error", "unknown")
                logger.warning(f"[TokenManager] 헬스체크 실패: {error}")
                return {"healthy": False, "error": error}
        except Exception as e:
            logger.error(f"[TokenManager] 헬스체크 오류: {e}")
            return {"healthy": False, "error": str(e)}

    def rotate_token(self) -> bool:
        """
        Token Rotation으로 새 토큰 발급
        https://api.slack.com/authentication/rotation
        """
        if not self.rotation_enabled:
            logger.info("[TokenManager] Token Rotation 미활성화 (고정 토큰 모드)")
            return False

        try:
            resp = requests.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                },
                timeout=15,
            )
            data = resp.json()

            if data.get("ok"):
                self.bot_token = data["access_token"]
                self.refresh_token = data.get("refresh_token", self.refresh_token)
                self._save_tokens()

                # 환경변수도 업데이트 (현재 프로세스 내)
                os.environ["SLACK_BOT_TOKEN"] = self.bot_token

                logger.info(
                    f"[TokenManager] 토큰 갱신 성공 "
                    f"(만료: {data.get('expires_in', '?')}초)"
                )
                return True
            else:
                logger.error(f"[TokenManager] 토큰 갱신 실패: {data.get('error')}")
                return False

        except Exception as e:
            logger.error(f"[TokenManager] 토큰 갱신 오류: {e}")
            return False

    def start_auto_refresh(self, interval_hours: int = 10):
        """
        백그라운드에서 토큰 자동 갱신 + 헬스체크

        - Token Rotation 모드: interval_hours 마다 토큰 갱신
          (Slack 토큰 만료는 보통 12시간)
        - 고정 토큰 모드: 1시간마다 헬스체크만 수행
        """
        self._stop_event.clear()

        def worker():
            logger.info(
                f"[TokenManager] 자동 갱신 시작 "
                f"({'Rotation 모드' if self.rotation_enabled else '헬스체크 모드'})"
            )

            while not self._stop_event.is_set():
                # 헬스체크
                health = self.health_check()
                if health["healthy"]:
                    logger.info(f"[TokenManager] 헬스체크 OK: {health.get('team')}")
                else:
                    logger.warning(f"[TokenManager] 헬스체크 FAIL: {health.get('error')}")

                    # 토큰이 만료됐으면 갱신 시도
                    if health.get("error") in ("token_expired", "invalid_auth", "token_revoked"):
                        if self.rotation_enabled:
                            success = self.rotate_token()
                            if not success:
                                logger.critical(
                                    "[TokenManager] 토큰 갱신 실패! 수동 개입 필요"
                                )

                # Token Rotation 모드면 주기적 갱신
                if self.rotation_enabled:
                    self.rotate_token()

                # 대기
                wait_seconds = interval_hours * 3600 if self.rotation_enabled else 3600
                self._stop_event.wait(wait_seconds)

        self._worker = Thread(target=worker, daemon=True, name="token-refresh")
        self._worker.start()

    def stop_auto_refresh(self):
        """자동 갱신 중지"""
        self._stop_event.set()
        if self._worker:
            self._worker.join(timeout=5)
            logger.info("[TokenManager] 자동 갱신 중지")

    def get_bot_token(self) -> str:
        """현재 유효한 Bot Token 반환"""
        return self.bot_token

    def get_app_token(self) -> str:
        """App Token 반환 (Socket Mode용, 갱신 불필요)"""
        return self.app_token
