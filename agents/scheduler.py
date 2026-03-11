"""
NanoClaw Scheduler
- 주간 데이터 동기화 스케줄
- 토큰 헬스체크 스케줄
- cron 기반 및 내장 스케줄러 지원
"""
import json
import logging
import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import BASE_DIR, TARGET_COUNTRIES, SLACK_CHANNEL_ID

logger = logging.getLogger("nanoclaw.scheduler")


class NanoClawScheduler:
    """
    NanoClaw 내장 스케줄러

    주요 스케줄:
    1. 주간 데이터 동기화: 매주 월요일 09:00
    2. 토큰 헬스체크: 매시간
    3. 일일 요약 보고: 매일 18:00 (수집이 있었을 경우)
    """

    def __init__(self):
        self._stop_event = threading.Event()
        self._threads = []
        self.last_sync = None
        self.sync_history = []

        # 스케줄 설정 (환경변수로 커스터마이즈 가능)
        self.weekly_sync_day = int(os.getenv("NANOCLAW_SYNC_DAY", "0"))  # 0=월요일
        self.weekly_sync_hour = int(os.getenv("NANOCLAW_SYNC_HOUR", "9"))
        self.sync_countries = os.getenv(
            "NANOCLAW_SYNC_COUNTRIES",
            ",".join(TARGET_COUNTRIES.keys())
        ).split(",")

    def start(self):
        """모든 스케줄 시작"""
        logger.info("[Scheduler] NanoClaw 스케줄러 시작")
        logger.info(
            f"[Scheduler] 주간 동기화: 매주 "
            f"{'월화수목금토일'[self.weekly_sync_day]}요일 "
            f"{self.weekly_sync_hour:02d}:00"
        )
        logger.info(f"[Scheduler] 동기화 대상: {', '.join(self.sync_countries)}")

        # 1. 주간 동기화 스레드
        t1 = threading.Thread(
            target=self._weekly_sync_loop,
            daemon=True,
            name="weekly-sync",
        )
        self._threads.append(t1)
        t1.start()

        # 2. 토큰 헬스체크 스레드
        t2 = threading.Thread(
            target=self._token_health_loop,
            daemon=True,
            name="token-health",
        )
        self._threads.append(t2)
        t2.start()

        logger.info("[Scheduler] 모든 스케줄 스레드 시작 완료")

    def stop(self):
        """모든 스케줄 중지"""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=5)
        logger.info("[Scheduler] 스케줄러 중지")

    def _weekly_sync_loop(self):
        """주간 동기화 루프"""
        while not self._stop_event.is_set():
            now = datetime.now()
            next_run = self._next_weekly_run(now)
            wait_seconds = (next_run - now).total_seconds()

            logger.info(
                f"[Scheduler] 다음 주간 동기화: {next_run.strftime('%Y-%m-%d %H:%M')} "
                f"({wait_seconds/3600:.1f}시간 후)"
            )

            # 다음 실행 시각까지 대기 (중간에 stop 가능)
            if self._stop_event.wait(timeout=wait_seconds):
                break  # stop 요청 시 종료

            # 동기화 실행
            self.run_sync()

    def _next_weekly_run(self, now: datetime) -> datetime:
        """다음 주간 실행 시각 계산"""
        target = now.replace(
            hour=self.weekly_sync_hour, minute=0, second=0, microsecond=0
        )

        # 이번 주 목표 요일까지 남은 일수
        days_ahead = self.weekly_sync_day - now.weekday()
        if days_ahead < 0:
            days_ahead += 7
        elif days_ahead == 0 and now >= target:
            days_ahead = 7  # 이미 오늘 지났으면 다음 주

        target += timedelta(days=days_ahead)
        return target

    def run_sync(self, countries: list = None):
        """
        데이터 동기화 실행
        Orchestrator를 호출하여 전체 수집 파이프라인 실행
        """
        sync_countries = countries or self.sync_countries
        started_at = datetime.now()

        logger.info(f"[Scheduler] 주간 동기화 시작: {', '.join(sync_countries)}")

        # Slack 알림
        self._notify_slack(
            f"*[NanoClaw 주간 동기화 시작]*\n"
            f"- 대상: {', '.join(sync_countries)}\n"
            f"- 시작: {started_at.strftime('%Y-%m-%d %H:%M')}"
        )

        try:
            from agents.orchestrator import Orchestrator

            orch = Orchestrator(use_slack=True)
            summary = orch.run(sync_countries)

            elapsed = (datetime.now() - started_at).total_seconds()
            self.last_sync = datetime.now().isoformat()

            sync_record = {
                "timestamp": self.last_sync,
                "countries": sync_countries,
                "summary": summary,
                "elapsed_seconds": elapsed,
            }
            self.sync_history.append(sync_record)

            # 히스토리 파일 저장
            self._save_sync_history()

            # Slack 완료 알림
            self._notify_slack(
                f"*[NanoClaw 주간 동기화 완료]*\n"
                f"- 국가: {summary.get('countries', 0)}개\n"
                f"- 수집: {summary.get('items', 0)}건\n"
                f"- 신규: {summary.get('new_items', 0)}건\n"
                f"- 변경: {summary.get('changed_items', 0)}건\n"
                f"- 오류: {summary.get('errors', 0)}건\n"
                f"- 소요: {elapsed:.0f}초"
            )

            logger.info(f"[Scheduler] 주간 동기화 완료 ({elapsed:.0f}초)")
            return summary

        except Exception as e:
            logger.error(f"[Scheduler] 주간 동기화 실패: {e}", exc_info=True)
            self._notify_slack(f"*[NanoClaw 주간 동기화 오류]*\n{str(e)[:500]}")
            return None

    def _token_health_loop(self):
        """토큰 헬스체크 루프 (매시간)"""
        while not self._stop_event.is_set():
            try:
                from agents.token_manager import TokenManager
                tm = TokenManager()
                health = tm.health_check()

                if health["healthy"]:
                    logger.debug(f"[Scheduler] 토큰 헬스체크 OK")
                else:
                    logger.warning(f"[Scheduler] 토큰 헬스체크 FAIL: {health.get('error')}")

                    # Token Rotation 모드면 갱신 시도
                    if tm.rotation_enabled:
                        success = tm.rotate_token()
                        if success:
                            logger.info("[Scheduler] 토큰 자동 갱신 성공")
                        else:
                            self._notify_slack(
                                "*[NanoClaw 경고]* Slack 토큰 갱신 실패! 수동 확인 필요"
                            )
                    else:
                        self._notify_slack(
                            f"*[NanoClaw 경고]* Slack 토큰 이상: {health.get('error')}\n"
                            "토큰 재발급이 필요할 수 있습니다."
                        )

            except Exception as e:
                logger.error(f"[Scheduler] 헬스체크 오류: {e}")

            # 1시간 대기
            if self._stop_event.wait(timeout=3600):
                break

    def _notify_slack(self, text: str):
        """Slack 채널에 알림 전송"""
        try:
            from agents.slack_reporter import SlackReporter
            reporter = SlackReporter()
            reporter.send_message(text)
        except Exception as e:
            logger.error(f"[Scheduler] Slack 알림 실패: {e}")

    def _save_sync_history(self):
        """동기화 히스토리 저장"""
        history_path = BASE_DIR / "logs" / "sync_history.json"
        history_path.parent.mkdir(parents=True, exist_ok=True)

        # 최근 52주(1년) 히스토리만 유지
        recent = self.sync_history[-52:]

        history_path.write_text(
            json.dumps(recent, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def get_status(self) -> dict:
        """스케줄러 상태 조회"""
        now = datetime.now()
        next_run = self._next_weekly_run(now)

        return {
            "running": not self._stop_event.is_set(),
            "last_sync": self.last_sync,
            "next_sync": next_run.isoformat(),
            "sync_countries": self.sync_countries,
            "sync_count": len(self.sync_history),
            "schedule": (
                f"매주 {'월화수목금토일'[self.weekly_sync_day]}요일 "
                f"{self.weekly_sync_hour:02d}:00"
            ),
        }
