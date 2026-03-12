# NanoClaw 보안 점검 보고서 (ISO 27001)

> 점검일: 2026-03-12
> 대상: `/projects/cowork` (NanoClaw 배출계수 수집 에이전트)
> 기준: ISO 27001:2022 Annex A

---

## 1. 종합 평가

| 항목 | 점검 전 | 조치 후 |
|------|---------|---------|
| 비밀번호/토큰 관리 | **Critical** | **Medium** (Git 히스토리 정리 필요) |
| 예외 처리 (정보 노출) | Medium | **Resolved** |
| 로깅 보안 | Medium | **Resolved** |
| 입력 검증 | Medium | **Low** |
| 파일 권한 | High | **Resolved** |
| 의존성 관리 | Low | **Resolved** |
| 네트워크 보안 | Medium | **Resolved** |
| 배포/운영 보안 | Low | Low (기존 양호) |

---

## 2. 수정 완료 항목

### 2.1 [Critical] `.env` 토큰 노출 제거
- **파일**: `.env`
- **문제**: 실제 Slack Bot Token(`xoxb-`), App Token(`xapp-`)이 평문으로 커밋됨
- **조치**: 토큰 값을 빈 문자열로 교체 (재발급 후 로컬에서만 설정)
- **잔여 조치**: Git 히스토리에서 토큰 제거 필요 (`git filter-branch` 또는 BFG Repo Cleaner)

### 2.2 [High] `.env` 파일 권한 강화
- **파일**: `.env`
- **문제**: 권한이 `644` (그룹/기타 읽기 가능)
- **조치**: `chmod 600` 적용 (소유자만 읽기/쓰기)

### 2.3 [Medium] 예외 메시지 민감정보 유출 차단
- **파일**: `agents/slack_bot.py`
- **문제**: `except` 블록에서 `str(e)` 전체를 Slack 채널에 전송 → 시스템 경로, 스택 트레이스 노출 가능
- **조치**: 모든 예외 핸들러에서 상세 에러는 `logger.error(exc_info=True)`로 로그에만 기록, Slack에는 일반적인 오류 메시지만 전송
- **변경 위치**:
  - `_run_collection()` (수집 오류, 파이프라인 오류)
  - `_handle_query()` (조회 오류)
  - `_handle_stats()` (통계 오류)
  - `_handle_sync()` (동기화 오류)

### 2.4 [Medium] 로그에서 민감정보 제거
- **파일**: `agents/slack_bot.py`
- **문제**: `app_mention` 핸들러에서 전체 `event` 객체를 로깅 → 토큰/메시지 내용 노출 가능
- **조치**: `event.get('user')`, `event.get('channel')` 등 필요한 필드만 로깅

### 2.5 [Medium] 사용자 입력 길이 제한 및 이스케이프
- **파일**: `agents/slack_bot.py`
- **문제**: 알 수 없는 명령어를 그대로 Slack에 반환 → XSS/인젝션 가능성
- **조치**: 입력 텍스트를 50자로 제한, 백틱(`) 이스케이프 처리

### 2.6 [Medium] 하드코딩된 채널 ID 제거
- **파일**: `agents/slack_reporter.py`
- **문제**: `SLACK_CHANNEL_ID` 기본값에 실제 채널 ID(`C08RS2EE25P`) 하드코딩
- **조치**: 기본값을 빈 문자열로 변경 (환경변수 필수 설정)

### 2.7 [Medium] User-Agent 정보 은닉
- **파일**: `agents/fetcher.py`
- **문제**: `NanoClaw/1.0 (Emission Factor Data Collector)` → 프로젝트명/용도 노출
- **조치**: 일반적인 브라우저 User-Agent로 교체

### 2.8 [Medium] SSL 검증 명시적 설정
- **파일**: `agents/fetcher.py`
- **문제**: `requests.get()` 호출 시 `verify` 파라미터 미설정
- **조치**: `verify=True` 명시적 지정

### 2.9 [Low] 의존성 버전 핀닝
- **파일**: `requirements.txt`
- **문제**: `>=` 범위 지정으로 예측 불가능한 버전 설치 가능
- **조치**: 모든 패키지를 특정 버전으로 핀닝 (`==`)

### 2.10 [Low] `.gitignore`에 토큰 저장소 추가
- **파일**: `.gitignore`
- **문제**: `config/.tokens.json` (Token Rotation 시 생성)이 Git에 포함될 수 있음
- **조치**: `.gitignore`에 `config/.tokens.json` 추가

### 2.11 [Low] `.dockerignore` 강화
- **파일**: `.dockerignore`
- **문제**: `.env.*` 파일과 토큰 저장소가 Docker 빌드에 포함될 수 있음
- **조치**: `.env.*`, `config/.tokens.json` 추가

---

## 3. 기존 양호 항목 (변경 없음)

| 항목 | 상태 | 위치 |
|------|------|------|
| Docker 비root 실행 | 양호 | `Dockerfile` (USER nanoclaw) |
| systemd 보안 설정 | 양호 | `deploy/nanoclaw.service` (NoNewPrivileges, ProtectSystem) |
| 토큰 저장소 권한 | 양호 | `agents/token_manager.py` (chmod 0o600) |
| SQL 파라미터화 쿼리 | 양호 | `agents/db_sync.py` (Parameterized Query) |
| 네트워크 타임아웃 | 양호 | 모든 HTTP 요청에 timeout 설정 |
| Docker 리소스 제한 | 양호 | `docker-compose.yml` (memory: 512M, cpus: 1.0) |
| Docker 로그 로테이션 | 양호 | `docker-compose.yml` (max-size: 10m, max-file: 3) |
| Token Rotation 지원 | 양호 | `agents/token_manager.py` (OAuth 자동 갱신) |

---

## 4. 잔여 권고사항 (수동 조치 필요)

### 4.1 [Critical] Git 히스토리에서 토큰 제거
```bash
# BFG Repo Cleaner 사용 권장
# 1. 토큰 패턴 파일 생성
echo "xoxb-3466109186274-*" > /tmp/tokens.txt
echo "xapp-1-A0AKM9YG3KM-*" >> /tmp/tokens.txt

# 2. BFG 실행
bfg --replace-text /tmp/tokens.txt .

# 3. Git GC
git reflog expire --expire=now --all && git gc --prune=now --aggressive

# 4. Force push (주의: 팀원에게 사전 공지)
git push --force
```

### 4.2 [Critical] Slack 토큰 재발급
1. https://api.slack.com/apps 에서 기존 토큰 회수(Revoke)
2. 새 Bot Token(`xoxb-`) 재발급
3. 새 App Token(`xapp-`) 재발급
4. `.env` 파일에 새 토큰 설정

### 4.3 [Medium] 외부 시크릿 관리 서비스 도입 (장기)
- AWS Secrets Manager, HashiCorp Vault, 또는 Docker Swarm Secrets 사용 권장
- `.env` 파일 의존 → 런타임 시크릿 주입 방식으로 전환

### 4.4 [Low] 프로덕션 로그 레벨 조정
- 현재: `logging.INFO` → 프로덕션: `logging.WARNING` 권장
- 환경변수로 제어: `NANOCLAW_LOG_LEVEL=WARNING`

---

## 5. ISO 27001 매핑

| ISO 27001 통제 항목 | 해당 조치 |
|---------------------|-----------|
| A.5.15 접근 제어 | 2.1, 2.2 (토큰 관리, 파일 권한) |
| A.5.33 정보 보호 | 2.3, 2.4 (민감정보 노출 차단) |
| A.8.4 소스코드 접근 | 2.10, 2.11 (.gitignore, .dockerignore) |
| A.8.9 구성 관리 | 2.9 (의존성 핀닝) |
| A.8.12 데이터 유출 방지 | 2.5, 2.6 (입력 검증, 하드코딩 제거) |
| A.8.24 암호화 사용 | 2.8 (SSL 명시적 검증) |
| A.8.25 개발 보안 | 2.7 (정보 은닉) |
| A.8.28 보안 코딩 | 2.3, 2.5 (에러 처리, 입력 검증) |

---

## 6. 수정 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `.env` | 토큰 값 제거 |
| `.gitignore` | `config/.tokens.json` 추가 |
| `.dockerignore` | `.env.*`, `config/.tokens.json` 추가 |
| `agents/slack_bot.py` | 로그 민감정보 제거, 예외 메시지 일반화, 입력 길이 제한 |
| `agents/slack_reporter.py` | 하드코딩된 채널 ID 제거 |
| `agents/fetcher.py` | User-Agent 변경, SSL verify=True 명시 |
| `requirements.txt` | 의존성 버전 핀닝 |
