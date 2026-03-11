"""
NanoClaw Slack Sender - CoworkBot 토큰으로 메시지 발송
Claude/Cowork에서 직접 호출하여 MCP 대신 봇 이름으로 메시지를 보냄

사용법:
  python -m agents.slack_sender "메시지 내용"
  python -m agents.slack_sender --thread 1234567890.123456 "스레드 답글"
  python -m agents.slack_sender --channel C0AKQDRG7EH "특정 채널에 보내기"
"""
import argparse
import json
import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 설정
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def send_message(
    text: str,
    channel_id: str = None,
    thread_ts: str = None,
    blocks: list = None,
) -> dict:
    """
    CoworkBot 토큰으로 Slack 메시지 발송

    Args:
        text: 메시지 내용 (마크다운 지원)
        channel_id: 채널 ID (기본: .env의 SLACK_CHANNEL_ID)
        thread_ts: 스레드 부모 메시지 timestamp (스레드 답글 시)
        blocks: Slack Block Kit 블록 (선택)

    Returns:
        dict: {"ok": True, "ts": "메시지_타임스탬프", "channel": "채널ID"}
    """
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    if not bot_token:
        return {"ok": False, "error": "SLACK_BOT_TOKEN 환경변수가 설정되지 않았습니다."}

    if not channel_id:
        channel_id = os.getenv("SLACK_CHANNEL_ID", "C0AKQDRG7EH")

    client = WebClient(token=bot_token)

    try:
        kwargs = {
            "channel": channel_id,
            "text": text,
        }
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        if blocks:
            kwargs["blocks"] = blocks

        response = client.chat_postMessage(**kwargs)
        return {
            "ok": True,
            "ts": response["ts"],
            "channel": response["channel"],
        }
    except SlackApiError as e:
        return {
            "ok": False,
            "error": str(e.response["error"]),
            "detail": str(e),
        }


def read_channel(channel_id: str = None, limit: int = 10) -> dict:
    """
    CoworkBot 토큰으로 채널 메시지 읽기

    Args:
        channel_id: 채널 ID (기본: .env의 SLACK_CHANNEL_ID)
        limit: 읽을 메시지 수 (기본 10)

    Returns:
        dict: {"ok": True, "messages": [...]}
    """
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    if not bot_token:
        return {"ok": False, "error": "SLACK_BOT_TOKEN 환경변수가 설정되지 않았습니다."}

    if not channel_id:
        channel_id = os.getenv("SLACK_CHANNEL_ID", "C0AKQDRG7EH")

    client = WebClient(token=bot_token)

    try:
        response = client.conversations_history(channel=channel_id, limit=limit)
        messages = []
        for msg in response.get("messages", []):
            messages.append({
                "ts": msg.get("ts"),
                "user": msg.get("user", msg.get("bot_id", "unknown")),
                "text": msg.get("text", "")[:200],
                "thread_ts": msg.get("thread_ts"),
            })
        return {"ok": True, "messages": messages}
    except SlackApiError as e:
        return {"ok": False, "error": str(e.response["error"])}


def read_thread(thread_ts: str, channel_id: str = None, limit: int = 50) -> dict:
    """
    CoworkBot 토큰으로 스레드 메시지 읽기

    Args:
        thread_ts: 스레드 부모 메시지 timestamp
        channel_id: 채널 ID (기본: .env의 SLACK_CHANNEL_ID)
        limit: 읽을 메시지 수

    Returns:
        dict: {"ok": True, "messages": [...]}
    """
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    if not bot_token:
        return {"ok": False, "error": "SLACK_BOT_TOKEN 환경변수가 설정되지 않았습니다."}

    if not channel_id:
        channel_id = os.getenv("SLACK_CHANNEL_ID", "C0AKQDRG7EH")

    client = WebClient(token=bot_token)

    try:
        response = client.conversations_replies(
            channel=channel_id, ts=thread_ts, limit=limit
        )
        messages = []
        for msg in response.get("messages", []):
            messages.append({
                "ts": msg.get("ts"),
                "user": msg.get("user", msg.get("bot_id", "unknown")),
                "text": msg.get("text", "")[:200],
            })
        return {"ok": True, "messages": messages}
    except SlackApiError as e:
        return {"ok": False, "error": str(e.response["error"])}


def main():
    parser = argparse.ArgumentParser(description="NanoClaw Slack Sender (CoworkBot)")
    subparsers = parser.add_subparsers(dest="command", help="명령어")

    # send 명령
    send_parser = subparsers.add_parser("send", help="메시지 발송")
    send_parser.add_argument("text", help="보낼 메시지")
    send_parser.add_argument("--channel", help="채널 ID")
    send_parser.add_argument("--thread", help="스레드 timestamp")

    # read 명령
    read_parser = subparsers.add_parser("read", help="채널 메시지 읽기")
    read_parser.add_argument("--channel", help="채널 ID")
    read_parser.add_argument("--limit", type=int, default=10, help="메시지 수")

    # thread 명령
    thread_parser = subparsers.add_parser("thread", help="스레드 읽기")
    thread_parser.add_argument("thread_ts", help="스레드 timestamp")
    thread_parser.add_argument("--channel", help="채널 ID")
    thread_parser.add_argument("--limit", type=int, default=50, help="메시지 수")

    args = parser.parse_args()

    # 기본 명령이 없으면 send로 간주 (단축 사용)
    if not args.command:
        # python slack_sender.py "메시지" 형태 지원
        if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
            result = send_message(sys.argv[1])
            print(json.dumps(result, ensure_ascii=False))
            return
        parser.print_help()
        return

    if args.command == "send":
        result = send_message(
            text=args.text,
            channel_id=args.channel,
            thread_ts=args.thread,
        )
    elif args.command == "read":
        result = read_channel(channel_id=args.channel, limit=args.limit)
    elif args.command == "thread":
        result = read_thread(
            thread_ts=args.thread_ts,
            channel_id=args.channel,
            limit=args.limit,
        )
    else:
        parser.print_help()
        return

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
