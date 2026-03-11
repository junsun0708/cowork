# NanoClaw Slack Bot 설정 가이드

## 1. Slack App 생성

1. https://api.slack.com/apps 접속
2. **Create New App** → **From scratch** 선택
3. App Name: `NanoClaw`
4. Workspace: `thingspire-tft` 선택
5. **Create App** 클릭

## 2. Socket Mode 활성화

1. 좌측 메뉴 **Socket Mode** 클릭
2. **Enable Socket Mode** 토글 ON
3. Token Name: `nanoclaw-socket` 입력 → **Generate**
4. 생성된 `xapp-...` 토큰 복사 → 이것이 **SLACK_APP_TOKEN**

## 3. Bot Token 권한 설정

1. 좌측 메뉴 **OAuth & Permissions** 클릭
2. **Bot Token Scopes** 에 아래 추가:
   - `app_mentions:read` (멘션 수신)
   - `chat:write` (메시지 전송)
   - `channels:read` (채널 목록)
   - `channels:history` (채널 히스토리)
   - `im:read` (DM 수신)
   - `im:history` (DM 히스토리)
3. 페이지 상단 **Install to Workspace** 클릭
4. **허용** 클릭
5. 생성된 `xoxb-...` 토큰 복사 → 이것이 **SLACK_BOT_TOKEN**

## 4. Event Subscriptions 설정

1. 좌측 메뉴 **Event Subscriptions** 클릭
2. **Enable Events** 토글 ON
3. **Subscribe to bot events** 에 아래 추가:
   - `app_mention` (앱 멘션)
   - `message.im` (DM 메시지)
4. **Save Changes** 클릭

## 5. 환경변수 설정

```bash
# ~/.bashrc 또는 .env 파일에 추가
export SLACK_BOT_TOKEN=xoxb-발급받은-토큰
export SLACK_APP_TOKEN=xapp-발급받은-토큰
export SLACK_CHANNEL_ID=C08RS2EE25P
```

## 6. 채널에 Bot 초대

`#탄소관리-개발팀` 채널에서:
```
/invite @NanoClaw
```

## 7. Bot 실행

```bash
cd ~/projects/cowork/nanoclaw
python -m agents.slack_bot
```

## 8. 사용법

채널에서:
```
@NanoClaw KR 수집
@NanoClaw KR US JP 수집
@NanoClaw 조회 KR
@NanoClaw 조회 electricity
@NanoClaw 상태
@NanoClaw 통계
@NanoClaw 도움말
```

## 9. 백그라운드 실행 (서버)

```bash
# systemd 서비스 또는 nohup
nohup python -m agents.slack_bot > logs/slackbot.log 2>&1 &

# 또는 supervisord, pm2 등 프로세스 매니저 사용 권장
```
