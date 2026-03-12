"""
NanoClaw Slack Bot (Socket Mode)
- Slack 채널에서 명령을 받아 수집 파이프라인 실행
- 스레드 기반 대화형 인터페이스
- 수집 결과를 같은 스레드에 보고

사용법 (채널에서):
  @NanoClaw KR 수집           → 한국 배출계수 수집
  @NanoClaw KR US JP 수집     → 여러 국가 수집
  @NanoClaw 상태              → 현재 수집 상태 확인
  @NanoClaw 조회 KR           → 한국 DB 데이터 조회
  @NanoClaw 조회 electricity  → 전력 배출계수 국가별 비교
  @NanoClaw 도움말            → 명령어 안내
  @NanoClaw 스케줄            → 주간 동기화 스케줄 상태
  @NanoClaw 동기화            → 즉시 전체 동기화 실행
"""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import SLACK_CHANNEL_ID, TARGET_COUNTRIES, TAXONOMY

logger = logging.getLogger("nanoclaw.slackbot")


class NanoClawBot:
    """NanoClaw Slack Bot + Token Manager + Scheduler"""

    def __init__(self):
        # ── Token Manager로 토큰 관리 ──
        from agents.token_manager import TokenManager
        self.token_manager = TokenManager()

        bot_token = self.token_manager.get_bot_token()
        app_token = self.token_manager.get_app_token()

        if not bot_token or not app_token:
            raise ValueError(
                "SLACK_BOT_TOKEN과 SLACK_APP_TOKEN 환경변수가 필요합니다.\n"
                "설정 가이드: nanoclaw/docs/SLACK_SETUP.md 참조"
            )

        self.app = App(token=bot_token)
        self.app_token = app_token
        self.channel_id = os.getenv("SLACK_CHANNEL_ID", SLACK_CHANNEL_ID)

        # ── Scheduler 초기화 ──
        from agents.scheduler import NanoClawScheduler
        self.scheduler = NanoClawScheduler()

        # 수집 상태 추적
        self.running_jobs = {}  # {thread_ts: {country, status, started_at}}

        # 이벤트 핸들러 등록
        self._register_handlers()

    def _register_handlers(self):
        """Slack 이벤트 핸들러 등록"""

        # 앱 멘션 이벤트 (@coworkbot ...)
        @self.app.event("app_mention")
        def handle_mention(event, say, client):
            logger.info(f"[Bot] app_mention 이벤트 수신: user={event.get('user')}, channel={event.get('channel')}")
            self._handle_command(event, say, client)

        # 일반 메시지 이벤트
        @self.app.event("message")
        def handle_message(event, say, client):
            logger.info(f"[Bot] message 이벤트 수신: channel_type={event.get('channel_type')}, user={event.get('user')}")
            # DM에서 온 메시지만 처리 (채널 메시지는 멘션으로 처리)
            if event.get("channel_type") == "im":
                self._handle_command(event, say, client)

        # 미처리 이벤트 로깅
        @self.app.event({"type": re.compile(".*")})
        def catch_all(event, body):
            event_type = body.get("event", {}).get("type", "unknown")
            if event_type not in ("app_mention", "message"):
                logger.info(f"[Bot] 기타 이벤트: {event_type}")

    def _handle_command(self, event, say, client):
        """명령어 파싱 및 실행"""
        text = event.get("text", "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        user = event.get("user", "")

        # 봇 멘션 텍스트 제거
        text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        logger.info(f"[Bot] 명령 수신: '{text}' from <@{user}>")

        # ── 명령어 라우팅 ──
        if not text:
            say(text=self._help_text(), thread_ts=thread_ts)
            return

        text_lower = text.lower()

        # 도움말
        if any(kw in text_lower for kw in ["도움말", "help", "사용법"]):
            say(text=self._help_text(), thread_ts=thread_ts)

        # 수집 명령
        elif any(kw in text_lower for kw in ["수집", "collect", "시작"]):
            self._handle_collect(text, thread_ts, user, say, client)

        # 상태 확인
        elif any(kw in text_lower for kw in ["상태", "status"]):
            self._handle_status(thread_ts, say)

        # 데이터 조회
        elif any(kw in text_lower for kw in ["조회", "query", "검색"]):
            self._handle_query(text, thread_ts, say)

        # DB 통계
        elif any(kw in text_lower for kw in ["통계", "stats", "요약"]):
            self._handle_stats(thread_ts, say)

        # 국가 목록
        elif any(kw in text_lower for kw in ["국가", "countries", "목록"]):
            self._handle_countries(thread_ts, say)

        # 스케줄 상태
        elif any(kw in text_lower for kw in ["스케줄", "schedule"]):
            self._handle_schedule(thread_ts, say)

        # 즉시 동기화
        elif any(kw in text_lower for kw in ["동기화", "sync"]):
            self._handle_sync(text, thread_ts, user, say, client)

        # 헬스체크
        elif any(kw in text_lower for kw in ["헬스", "health", "토큰"]):
            self._handle_health(thread_ts, say)

        # 알 수 없는 명령
        else:
            safe_text = text[:50].replace('`', "'")
            say(
                text=f"알 수 없는 명령입니다: `{safe_text}`\n`도움말`을 입력하면 사용 가능한 명령어를 확인할 수 있습니다.",
                thread_ts=thread_ts,
            )

    def _handle_collect(self, text, thread_ts, user, say, client):
        """수집 명령 처리"""
        # 국가 코드 추출
        country_codes = re.findall(r"(?<![A-Z])([A-Z]{2})(?![A-Z])", text.upper())

        # 알려진 국가만 필터
        valid_countries = [c for c in country_codes if c in TARGET_COUNTRIES or c == "INTL"]

        if not valid_countries:
            # 국가 코드 없으면 전체 목록에서 한글 매칭 시도
            for code, name in TARGET_COUNTRIES.items():
                if name in text:
                    valid_countries.append(code)

        if not valid_countries:
            say(
                text=(
                    "수집할 국가를 지정해주세요.\n"
                    "예: `KR 수집`, `KR US JP 수집`, `한국 수집`\n\n"
                    f"지원 국가: {', '.join(f'{k}({v})' for k, v in TARGET_COUNTRIES.items())}"
                ),
                thread_ts=thread_ts,
            )
            return

        # 이미 실행 중인 작업 확인
        for ts, job in self.running_jobs.items():
            if job["status"] == "running":
                say(
                    text=f"현재 `{job['countries']}` 수집이 진행 중입니다. 완료 후 다시 시도해주세요.",
                    thread_ts=thread_ts,
                )
                return

        country_names = [f"{c}({TARGET_COUNTRIES.get(c, c)})" for c in valid_countries]
        say(
            text=(
                f"*[NanoClaw] 수집 시작*\n"
                f"- 대상: {', '.join(country_names)}\n"
                f"- 요청자: <@{user}>\n"
                f"- 시작 시각: {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"수집 진행 상황을 이 스레드에 보고합니다..."
            ),
            thread_ts=thread_ts,
        )

        # 백그라운드 스레드에서 수집 실행
        self.running_jobs[thread_ts] = {
            "countries": valid_countries,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "user": user,
        }

        worker = threading.Thread(
            target=self._run_collection,
            args=(valid_countries, thread_ts, client),
            daemon=True,
        )
        worker.start()

    def _run_collection(self, country_codes, thread_ts, client):
        """백그라운드에서 수집 파이프라인 실행"""
        try:
            from agents.orchestrator import Orchestrator

            # Slack Reporter를 스레드 모드로 설정
            orch = Orchestrator(use_slack=False)  # 기본 Slack Reporter 비활성화

            total = len(country_codes)
            all_results = {"countries": 0, "items": 0, "new_items": 0, "errors": 0}

            for idx, country in enumerate(country_codes):
                progress = int(((idx) / total) * 100)
                self._post_thread(
                    client, thread_ts,
                    f"[{progress}%] `{country}` 수집 중... ({idx+1}/{total})"
                )

                try:
                    result = orch.collect_country(country)
                    items = len(result.get("processed", []))
                    all_results["countries"] += 1
                    all_results["items"] += items

                    if items > 0:
                        self._post_thread(
                            client, thread_ts,
                            f"`{country}` 수집 완료 - {items}건 추출"
                        )
                    else:
                        self._post_thread(
                            client, thread_ts,
                            f"`{country}` Raw 데이터 저장 완료 (추출 항목: 하위 페이지/PDF 탐색 필요)"
                        )

                except Exception as e:
                    all_results["errors"] += 1
                    self._post_thread(
                        client, thread_ts,
                        f"`{country}` 수집 중 오류가 발생했습니다. 로그를 확인해주세요."
                    )

            # 최종 결과
            elapsed = (datetime.now() - datetime.fromisoformat(
                self.running_jobs[thread_ts]["started_at"]
            )).total_seconds()

            db_stats = orch.db.get_stats()

            self._post_thread(
                client, thread_ts,
                (
                    f"*[NanoClaw] 수집 완료!*\n\n"
                    f"- 국가: {all_results['countries']}개 처리\n"
                    f"- 수집 항목: {all_results['items']}건\n"
                    f"- 오류: {all_results['errors']}건\n"
                    f"- 소요 시간: {elapsed:.1f}초\n\n"
                    f"*DB 현황:* 총 {db_stats['total_records']}건 | "
                    f"{db_stats['countries']}개국 | "
                    f"{db_stats['orgs']}개 기관 | "
                    f"{db_stats['categories']}개 카테고리"
                )
            )

            self.running_jobs[thread_ts]["status"] = "completed"

        except Exception as e:
            logger.error(f"[Bot] 수집 파이프라인 오류: {e}", exc_info=True)
            self._post_thread(client, thread_ts, "수집 파이프라인에서 오류가 발생했습니다. 로그를 확인해주세요.")
            self.running_jobs[thread_ts]["status"] = "error"

    def _handle_status(self, thread_ts, say):
        """현재 수집 상태"""
        running = [j for j in self.running_jobs.values() if j["status"] == "running"]
        if running:
            job = running[0]
            say(
                text=(
                    f"*현재 수집 진행 중*\n"
                    f"- 대상: {', '.join(job['countries'])}\n"
                    f"- 시작: {job['started_at']}\n"
                    f"- 요청자: <@{job['user']}>"
                ),
                thread_ts=thread_ts,
            )
        else:
            say(text="현재 진행 중인 수집 작업이 없습니다.", thread_ts=thread_ts)

    def _handle_query(self, text, thread_ts, say):
        """DB 데이터 조회"""
        try:
            from agents.db_sync import DBSync
            db = DBSync()

            # 국가 코드로 조회
            country_match = re.search(r"\b([A-Z]{2})\b", text.upper())
            if country_match:
                code = country_match.group(1)
                data = db.query_by_country(code)
                if data:
                    lines = [f"*{code} 배출계수 조회 결과 ({len(data)}건)*\n"]
                    for r in data[:15]:
                        lines.append(
                            f"  `{r['item_name_standard']:18s}` "
                            f"{r['standard_value']:>8.4f} {r['standard_unit']:15s} "
                            f"({r['year']}) - {r['source_org']}"
                        )
                    if len(data) > 15:
                        lines.append(f"  ... 외 {len(data)-15}건")
                    say(text="\n".join(lines), thread_ts=thread_ts)
                else:
                    say(text=f"`{code}` 데이터가 없습니다.", thread_ts=thread_ts)
                return

            # 카테고리로 조회
            all_cats = []
            for cats in TAXONOMY.values():
                all_cats.extend(cats)

            for cat in all_cats:
                if cat in text.lower() or cat.replace("_", " ") in text.lower():
                    data = db.query_by_category(cat)
                    if data:
                        lines = [f"*{cat} 국가별 배출계수 ({len(data)}건)*\n"]
                        for r in data[:15]:
                            lines.append(
                                f"  `{r['country_code']:4s}` {r['source_org']:8s} "
                                f"{r['standard_value']:>8.4f} {r['standard_unit']:15s} "
                                f"({r['year']})"
                            )
                        say(text="\n".join(lines), thread_ts=thread_ts)
                    else:
                        say(text=f"`{cat}` 데이터가 없습니다.", thread_ts=thread_ts)
                    return

            say(
                text="조회 대상을 지정해주세요.\n예: `조회 KR`, `조회 electricity`, `조회 diesel`",
                thread_ts=thread_ts,
            )
        except Exception as e:
            logger.error(f"[Bot] 조회 오류: {e}", exc_info=True)
            say(text="조회 중 오류가 발생했습니다. 로그를 확인해주세요.", thread_ts=thread_ts)

    def _handle_stats(self, thread_ts, say):
        """DB 통계"""
        try:
            from agents.db_sync import DBSync
            db = DBSync()
            stats = db.get_stats()
            say(
                text=(
                    f"*NanoClaw DB 통계*\n\n"
                    f"- 총 레코드: {stats['total_records']}건\n"
                    f"- 국가: {stats['countries']}개\n"
                    f"- 기관: {stats['orgs']}개\n"
                    f"- 카테고리: {stats['categories']}개"
                ),
                thread_ts=thread_ts,
            )
        except Exception as e:
            logger.error(f"[Bot] 통계 조회 오류: {e}", exc_info=True)
            say(text="통계 조회 중 오류가 발생했습니다.", thread_ts=thread_ts)

    def _handle_countries(self, thread_ts, say):
        """지원 국가 목록"""
        lines = ["*NanoClaw 지원 국가*\n"]
        for code, name in TARGET_COUNTRIES.items():
            lines.append(f"  `{code}` - {name}")
        lines.append(f"  `INTL` - 국제기구 (IPCC, IEA, UNFCCC 등)")
        say(text="\n".join(lines), thread_ts=thread_ts)

    def _handle_schedule(self, thread_ts, say):
        """스케줄 상태 조회"""
        status = self.scheduler.get_status()
        say(
            text=(
                f"*NanoClaw 주간 동기화 스케줄*\n\n"
                f"- 상태: {'실행 중' if status['running'] else '중지'}\n"
                f"- 스케줄: {status['schedule']}\n"
                f"- 다음 실행: {status['next_sync'][:16]}\n"
                f"- 마지막 실행: {status['last_sync'] or '없음'}\n"
                f"- 대상 국가: {', '.join(status['sync_countries'])}\n"
                f"- 누적 동기화: {status['sync_count']}회"
            ),
            thread_ts=thread_ts,
        )

    def _handle_sync(self, text, thread_ts, user, say, client):
        """즉시 동기화 실행"""
        # 국가 코드 지정 가능
        country_codes = re.findall(r"(?<![A-Z])([A-Z]{2})(?![A-Z])", text.upper())
        valid = [c for c in country_codes if c in TARGET_COUNTRIES or c == "INTL"]

        say(
            text=(
                f"*[NanoClaw] 즉시 동기화 시작*\n"
                f"- 대상: {', '.join(valid) if valid else '전체 국가'}\n"
                f"- 요청자: <@{user}>\n\n"
                f"진행 상황을 이 스레드에 보고합니다..."
            ),
            thread_ts=thread_ts,
        )

        def run_sync():
            try:
                result = self.scheduler.run_sync(valid if valid else None)
                if result:
                    self._post_thread(
                        client, thread_ts,
                        f"*동기화 완료!* {result.get('items', 0)}건 수집, "
                        f"{result.get('new_items', 0)}건 신규"
                    )
                else:
                    self._post_thread(client, thread_ts, "동기화 중 오류가 발생했습니다.")
            except Exception as e:
                logger.error(f"[Bot] 동기화 오류: {e}", exc_info=True)
                self._post_thread(client, thread_ts, "동기화 중 오류가 발생했습니다. 로그를 확인해주세요.")

        worker = threading.Thread(target=run_sync, daemon=True)
        worker.start()

    def _handle_health(self, thread_ts, say):
        """토큰 헬스체크"""
        health = self.token_manager.health_check()
        if health["healthy"]:
            say(
                text=(
                    f"*Slack 토큰 상태: 정상*\n"
                    f"- Team: {health.get('team')}\n"
                    f"- Bot: {health.get('user')}\n"
                    f"- Rotation: {'활성' if self.token_manager.rotation_enabled else '비활성 (고정 토큰)'}"
                ),
                thread_ts=thread_ts,
            )
        else:
            say(
                text=(
                    f"*Slack 토큰 상태: 이상*\n"
                    f"- 오류: {health.get('error')}\n"
                    f"- 조치: 토큰 재발급 또는 Token Rotation 설정 필요"
                ),
                thread_ts=thread_ts,
            )

    def _help_text(self) -> str:
        """도움말 텍스트"""
        return (
            "*NanoClaw 글로벌 배출계수 수집 에이전트*\n\n"
            "*수집 명령:*\n"
            "  `KR 수집` - 한국 배출계수 수집\n"
            "  `KR US JP 수집` - 여러 국가 동시 수집\n"
            "  `한국 수집` - 한글 국가명도 지원\n\n"
            "*조회 명령:*\n"
            "  `조회 KR` - 한국 데이터 조회\n"
            "  `조회 electricity` - 전력 배출계수 국가별 비교\n"
            "  `조회 diesel` - 경유 배출계수 비교\n\n"
            "*동기화 & 스케줄:*\n"
            "  `동기화` - 전체 국가 즉시 동기화\n"
            "  `동기화 KR US` - 지정 국가만 동기화\n"
            "  `스케줄` - 주간 동기화 스케줄 확인\n"
            "  `헬스` - Slack 토큰 상태 확인\n\n"
            "*기타:*\n"
            "  `상태` - 현재 수집 진행 상태\n"
            "  `통계` - DB 통계\n"
            "  `국가` - 지원 국가 목록\n"
            "  `도움말` - 이 안내\n\n"
            "_채널에서 `@NanoClaw 명령어`, 스레드에서도 가능합니다._\n"
            "_주간 동기화: 매주 월요일 09:00 자동 실행_"
        )

    def _post_thread(self, client, thread_ts, text):
        """스레드에 메시지 전송"""
        try:
            client.chat_postMessage(
                channel=self.channel_id,
                text=text,
                thread_ts=thread_ts,
            )
        except Exception as e:
            logger.error(f"[Bot] 스레드 메시지 전송 실패: {e}")

    def start(self):
        """Bot 시작 (Socket Mode) + 토큰 갱신 + 주간 스케줄러"""
        logger.info("[Bot] NanoClaw Slack Bot 시작...")

        # 1. 토큰 자동 갱신 시작
        self.token_manager.start_auto_refresh()
        logger.info("[Bot] 토큰 자동 헬스체크/갱신 시작")

        # 2. 주간 동기화 스케줄러 시작
        self.scheduler.start()
        status = self.scheduler.get_status()
        logger.info(f"[Bot] 주간 동기화 스케줄 시작: {status['schedule']}")
        logger.info(f"[Bot] 다음 동기화: {status['next_sync'][:16]}")

        # 3. Socket Mode 리스너 시작 (블로킹)
        handler = SocketModeHandler(self.app, self.app_token)
        try:
            handler.start()
        except KeyboardInterrupt:
            logger.info("[Bot] 종료 요청...")
            self.scheduler.stop()
            self.token_manager.stop_auto_refresh()
            logger.info("[Bot] NanoClaw Bot 종료 완료")


def main():
    """CLI 진입점"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        bot = NanoClawBot()
        print("NanoClaw Slack Bot 시작! (Ctrl+C로 종료)")
        bot.start()
    except ValueError as e:
        print(f"\n[오류] {e}")
        print("\n── Slack App 설정이 필요합니다 ──")
        print("1. https://api.slack.com/apps 에서 앱 생성")
        print("2. Socket Mode 활성화 → App Token (xapp-) 발급")
        print("3. Bot Token (xoxb-) 발급")
        print("4. 환경변수 설정:")
        print("   export SLACK_BOT_TOKEN=xoxb-...")
        print("   export SLACK_APP_TOKEN=xapp-...")
        print("\n자세한 안내: docs/SLACK_SETUP.md")


if __name__ == "__main__":
    main()
