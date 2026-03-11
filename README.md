# NanoClaw - 글로벌 배출계수 자동 수집 AI 에이전트

## 개요
NanoClaw는 전 세계 배출계수(Emission Factors)를 자율적으로 탐색, 수집, 저장, 정규화, DB 적재하는 AI 에이전트 시스템입니다.

## 아키텍처

```
Orchestrator (전체 작업 관리)
  ├── Source Discovery Agent (국가별 기관 자동 발견)
  ├── Web Search Agent (웹 검색 기반 소스 발견)
  ├── Fetcher (HTML / PDF / API 수집)
  ├── Extractor (배출계수 데이터 추출)
  ├── Normalizer (단위 변환 및 표준화)
  ├── DB Sync (SQLite DB upsert + diff)
  ├── Logger Agent (로그 및 리포트)
  └── Slack Reporter (Slack 진행 보고)
```

## 디렉토리 구조

```
nanoclaw/
├── agents/                    # 에이전트 모듈
│   ├── orchestrator.py        # 메인 오케스트레이터
│   ├── source_discovery.py    # 소스 탐색
│   ├── web_search_agent.py    # 웹 검색
│   ├── fetcher.py             # 데이터 수집
│   ├── extractor.py           # 데이터 추출
│   ├── normalizer.py          # 정규화
│   ├── db_sync.py             # DB 동기화
│   ├── logger_agent.py        # 로깅
│   ├── slack_reporter.py      # Slack 보고
│   └── seed_data.py           # 시드 데이터
├── config/
│   └── settings.py            # 전체 설정
├── data/
│   ├── storage/raw/           # 원본 데이터 저장
│   └── alerts/                # 구조 변경 알림
├── logs/prompts/              # 프롬프트 로그
├── output/                    # 일일 수집 결과
├── source_registry/           # 국가별 소스 레지스트리
├── parsing_profiles/          # 기관별 파싱 프로필
├── run.py                     # CLI 실행 스크립트
├── requirements.txt           # 의존성
└── .env.example               # 환경변수 템플릿
```

## 빠른 시작

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정
```bash
cp .env.example .env
# .env 파일에 Slack Bot Token 설정
```

### 3. 실행
```bash
# 전체 국가 수집
python run.py

# 특정 국가만 수집
python run.py KR
python run.py KR US JP

# 특정 기관만 수집
python run.py KR --org GIR

# Slack 알림 없이 실행
python run.py --no-slack KR
```

## 서버 배포 (~/projects/cowork)

```bash
# 프로젝트 복사
cp -r nanoclaw ~/projects/cowork/nanoclaw

# 환경변수 설정
export NANOCLAW_ROOT=~/projects/cowork/nanoclaw
export NANOCLAW_DB_PATH=~/projects/cowork/nanoclaw/data/nanoclaw.db
export SLACK_BOT_TOKEN=xoxb-your-token
export SLACK_CHANNEL_ID=C08RS2EE25P

# 실행
python run.py KR US JP DE GB FR AU
```

## Slack 연동
- 채널: `#탄소관리-개발팀` (C08RS2EE25P)
- Bot Token 또는 Webhook 방식 지원
- 진행률, 수집 결과, 알림, 일일 요약 자동 전송

## 지원 국가 (Source Registry)
KR (한국), US (미국), JP (일본), DE (독일), GB (영국), FR (프랑스), AU (호주), CN (중국), INTL (국제기구)

## DB 스키마 (processed_emissions)
| 컬럼 | 설명 |
|------|------|
| uid | 고유ID (KR-GIR-electricity-2022) |
| country_code | 국가코드 |
| source_org | 출처 기관 |
| category | 택소노미 카테고리 |
| standard_value | 표준화된 배출계수 값 |
| standard_unit | 표준 단위 |
| year | 기준년도 |

## 택소노미
Energy, Transportation, Industry, Waste, Agriculture 5개 대분류, 21개 세부 카테고리
