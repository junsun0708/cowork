"""
NanoClaw Slack Reporter Agent
- Slack 채널에 진행 상황, 결과, 알림을 전송
- Webhook 또는 Bot Token 방식 지원
"""
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger("nanoclaw.slack")

# Slack Bot Token (환경변수에서 로드)
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


class SlackReporter:
    """Slack 채널에 NanoClaw 에이전트 상태를 보고하는 클래스"""

    def __init__(self, channel_id: str = None, bot_token: str = None):
        self.channel_id = channel_id or SLACK_CHANNEL_ID
        self.bot_token = bot_token or SLACK_BOT_TOKEN
        self.webhook_url = SLACK_WEBHOOK_URL

    def send_message(self, text: str, thread_ts: str = None) -> dict:
        """Slack 채널에 메시지 전송"""
        import requests

        if self.bot_token:
            return self._send_via_bot(text, thread_ts)
        elif self.webhook_url:
            return self._send_via_webhook(text)
        else:
            logger.warning("[Slack] 토큰/Webhook 미설정 - 콘솔 출력으로 대체")
            print(f"[SLACK] {text}")
            return {"ok": False, "error": "no_credentials"}

    def _send_via_bot(self, text: str, thread_ts: str = None) -> dict:
        """Bot Token으로 메시지 전송"""
        import requests

        url = "https://slack.com/api/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "channel": self.channel_id,
            "text": text,
            "mrkdwn": True,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            logger.error(f"[Slack] 전송 실패: {e}")
            return {"ok": False, "error": str(e)}

    def _send_via_webhook(self, text: str) -> dict:
        """Webhook으로 메시지 전송"""
        import requests

        try:
            resp = requests.post(
                self.webhook_url,
                json={"text": text},
                timeout=10,
            )
            return {"ok": resp.status_code == 200}
        except Exception as e:
            logger.error(f"[Slack Webhook] 전송 실패: {e}")
            return {"ok": False, "error": str(e)}

    def send_progress(self, progress_pct: int, message: str, details: str = ""):
        """진행률 보고"""
        bar = self._progress_bar(progress_pct)
        text = (
            f"*[NanoClaw 진행 상황]* {bar} {progress_pct}%\n"
            f"> {message}\n"
        )
        if details:
            text += f"```{details}```"
        return self.send_message(text)

    def send_collection_result(self, country: str, org: str, count: int, errors: int = 0):
        """수집 결과 보고"""
        status = "완료" if errors == 0 else f"완료 (오류 {errors}건)"
        text = (
            f"*[NanoClaw 수집 결과]*\n"
            f"> 국가: `{country}` | 기관: `{org}`\n"
            f"> 수집 항목: *{count}*건 | 상태: {status}"
        )
        return self.send_message(text)

    def send_alert(self, alert_type: str, message: str):
        """알림 전송 (구조 변경, 오류 등)"""
        emoji = {"structure_change": "🚨", "error": "❌", "warning": "⚠️", "info": "ℹ️"}
        icon = emoji.get(alert_type, "📢")
        text = f"{icon} *[NanoClaw 알림 - {alert_type}]*\n> {message}"
        return self.send_message(text)

    def send_daily_summary(self, summary: dict):
        """일일 수집 요약 보고"""
        text = (
            f"*[NanoClaw 일일 요약 - {datetime.now().strftime('%Y-%m-%d')}]*\n"
            f"> 수집 국가: {summary.get('countries', 0)}개\n"
            f"> 수집 기관: {summary.get('orgs', 0)}개\n"
            f"> 수집 항목: {summary.get('items', 0)}건\n"
            f"> 신규 항목: {summary.get('new_items', 0)}건\n"
            f"> 변경 항목: {summary.get('changed_items', 0)}건\n"
            f"> 오류: {summary.get('errors', 0)}건"
        )
        return self.send_message(text)

    @staticmethod
    def _progress_bar(pct: int, length: int = 10) -> str:
        filled = int(length * pct / 100)
        bar = "█" * filled + "░" * (length - filled)
        return f"[{bar}]"
