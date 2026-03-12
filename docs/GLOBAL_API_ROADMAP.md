# NanoClaw 글로벌 API 서비스 로드맵

> 작성일: 2026-03-12
> 현재 상태: Slack Bot 기반 내부 수집 시스템
> 목표 상태: 글로벌 배출계수 REST API 서비스

---

## 1. 현재 시스템 진단

### 1.1 준비도 총점: 1.9 / 5.0

| 항목 | 점수 | 현재 상태 |
|------|------|-----------|
| API 엔드포인트 | **0/5** | 없음. Slack Bot만 존재 |
| 인증/인가 | **0/5** | 없음. Slack Token만 사용 |
| Rate Limiting | **0/5** | 없음. 무제한 접근 |
| DB 확장성 | **1/5** | SQLite 단일 파일 (동시 쓰기 1개) |
| 캐싱 | **0/5** | 없음. 매 쿼리 DB 직접 조회 |
| API 버전 관리 | **0/5** | 없음 |
| 모니터링 | **1/5** | 파일 로그만 |
| 보안 | **3.5/5** | 대부분 양호 (Git 히스토리 토큰 제외) |
| 배포 | **4/5** | Docker + systemd 양호 |
| 데이터 모델 | **4/5** | 4단계 계층, GWP 5버전, 개별 가스 |
| 다국어 | **4/5** | 8개 언어 지원 |
| 데이터 신선도 | **3/5** | last_checked_at 추적, TTL 미정의 |

### 1.2 치명적 결핍 사항

```
1. REST API 엔드포인트가 아예 없음
2. 클라이언트 인증 수단 없음 (API Key, JWT 등)
3. SQLite는 글로벌 동시 접속 불가
4. 요청 제한(Rate Limit) 없어 DDoS에 취약
```

---

## 2. 보안 관점 개선사항

### 2.1 즉시 조치 (Critical)

| # | 항목 | 현재 | 목표 |
|---|------|------|------|
| 1 | Git 히스토리 토큰 | 노출됨 | BFG로 제거 + 토큰 재발급 |
| 2 | API 인증 | 없음 | JWT + API Key 이중 인증 |
| 3 | HTTPS 강제 | 미설정 | TLS 1.3 필수 |
| 4 | CORS 정책 | 없음 | 허용 도메인 화이트리스트 |

### 2.2 API 보안 계층 설계

```
클라이언트 요청
    │
    ▼
[1] TLS/HTTPS 강제 (Let's Encrypt)
    │
    ▼
[2] Rate Limiter (IP + API Key 기반)
    │  - 무료: 100 req/일
    │  - 기본: 1,000 req/일
    │  - 프로: 50,000 req/일
    │
    ▼
[3] API Key 검증 (헤더: X-API-Key)
    │
    ▼
[4] JWT Token 검증 (Bearer Token, 선택)
    │
    ▼
[5] 입력 검증 (Pydantic 스키마)
    │  - country_code: 정규식 [A-Z]{2}
    │  - year: 1990~2030 범위
    │  - category: TAXONOMY 화이트리스트
    │
    ▼
[6] SQL Parameterized Query (기존 유지)
    │
    ▼
[7] 응답 필터링 (민감정보 제거)
```

### 2.3 데이터 보안

| 항목 | 현재 | 목표 |
|------|------|------|
| DB 암호화 | 없음 | PostgreSQL TDE 또는 pgcrypto |
| 전송 암호화 | SSL verify=True (수집) | TLS 1.3 (API 제공) |
| 시크릿 관리 | .env 파일 | HashiCorp Vault 또는 AWS Secrets Manager |
| 감사 로그 | 없음 | API 호출 로그 (who/when/what) |
| 개인정보 | 해당 없음 | GDPR 준수 (EU 사용자 대응) |

---

## 3. 글로벌 서비스 관점 개선사항

### 3.1 API 엔드포인트 설계

```yaml
# 배출계수 조회
GET  /api/v1/emissions
GET  /api/v1/emissions/{country_code}
GET  /api/v1/emissions/{country_code}/{category}

# 계층 탐색
GET  /api/v1/taxonomy
GET  /api/v1/taxonomy/{scope}
GET  /api/v1/taxonomy/{scope}/{level1}

# 국가/기관 목록
GET  /api/v1/countries
GET  /api/v1/countries/{code}/sources

# 비교/분석
GET  /api/v1/compare?countries=KR,US,JP&category=electricity
GET  /api/v1/history/{uid}
GET  /api/v1/trends?category=electricity&years=2020-2025

# Factor-id 매핑
GET  /api/v1/mapping/{auto_uid}
GET  /api/v1/mapping/manual/{manual_factor_id}

# 시스템
GET  /api/v1/health
GET  /api/v1/stats
POST /api/v1/sync/{country_code}  (관리자 전용)
```

### 3.2 API 응답 형식

```json
{
  "status": "success",
  "data": {
    "uid": "KR-GIR-scope1-diesel-2024",
    "factor_id": "KR-S1-C-diesel-0-0-2024",
    "country": {"code": "KR", "name": "South Korea", "name_local": "대한민국"},
    "scope": "Scope1",
    "hierarchy": {
      "level1": "Fuels",
      "level2": "Liquid_fuels",
      "level3": "diesel"
    },
    "item": {
      "name": "diesel",
      "name_original": "경유",
      "name_localized": "경유"
    },
    "emission_factor": {
      "value": 2.68,
      "unit": "kgCO2e/L",
      "gases": {
        "co2": {"value": 2.6, "unit": "kgCO2/L"},
        "ch4": {"value": 0.001, "unit": "kgCH4/L"},
        "n2o": {"value": 0.0003, "unit": "kgN2O/L"}
      },
      "gwp_values": {
        "SAR": 2.6954,
        "TAR": 2.7007,
        "AR4": 2.7144,
        "AR5": 2.7075,
        "AR6": 2.7098
      },
      "gwp_version": "AR6"
    },
    "source": {
      "org": "GIR",
      "name": "온실가스종합정보센터",
      "type": "Government",
      "reliability": 5
    },
    "year": 2024,
    "freshness": {
      "collected_at": "2026-03-12T09:00:00Z",
      "last_checked_at": "2026-03-12T09:00:00Z",
      "is_stale": false,
      "stale_after_days": 365
    }
  },
  "meta": {
    "api_version": "v1",
    "request_id": "req_abc123",
    "response_time_ms": 45
  }
}
```

### 3.3 다국어 API 지원

```
# 헤더 기반
Accept-Language: ko
Accept-Language: ja

# 파라미터 기반
GET /api/v1/emissions/KR?lang=ko
GET /api/v1/emissions/KR?lang=ja

# 응답 변환
{
  "item": {
    "name": "diesel",           // 항상 영문 표준명
    "name_localized": "경유"     // 요청 언어에 따라 변환
  }
}
```

### 3.4 데이터 신선도 관리

```
# 신선도 정책
- 정부 데이터: 365일 (연 1회 갱신)
- 전력 배출계수: 90일 (분기 갱신)
- EPD/PCF: 180일 (반기 갱신)
- 국제기구: 365일

# API 필터
GET /api/v1/emissions?max_age_days=30    (30일 이내 데이터만)
GET /api/v1/emissions?include_stale=true (만료 데이터 포함)

# 응답 헤더
X-Data-Freshness: fresh
X-Data-Collected-At: 2026-03-12T09:00:00Z
X-Data-Stale-After: 2027-03-12T09:00:00Z
```

---

## 4. 인프라 아키텍처

### 4.1 현재 → 목표

```
[현재]                              [목표]

Slack Bot ──→ SQLite               Client (Web/Mobile/API)
   │              │                      │
   └── 수집 ──────┘                      ▼
                                    ┌─────────┐
                                    │ CDN/WAF  │ (CloudFlare)
                                    └────┬────┘
                                         │
                                    ┌────▼────┐
                                    │ API GW   │ (Kong / AWS API GW)
                                    │ + Auth   │
                                    │ + Rate   │
                                    └────┬────┘
                                         │
                              ┌──────────┼──────────┐
                              ▼          ▼          ▼
                         ┌────────┐ ┌────────┐ ┌────────┐
                         │ API #1 │ │ API #2 │ │ API #3 │ (FastAPI)
                         └───┬────┘ └───┬────┘ └───┬────┘
                             │          │          │
                         ┌───▼──────────▼──────────▼───┐
                         │         Redis Cache          │
                         └──────────────┬───────────────┘
                                        │
                         ┌──────────────▼───────────────┐
                         │   PostgreSQL (Primary)        │
                         │   + Read Replica (1~N)        │
                         └──────────────────────────────┘
                                        │
                         ┌──────────────▼───────────────┐
                         │   수집 Worker (Background)    │
                         │   Slack Bot + Scheduler       │
                         └──────────────────────────────┘
```

### 4.2 DB 마이그레이션: SQLite → PostgreSQL

| 항목 | SQLite (현재) | PostgreSQL (목표) |
|------|---------------|-------------------|
| 동시 접속 | 1 writer | 수천 개 동시 |
| 용량 | ~100GB 한계 | 사실상 무제한 |
| 복제 | 불가 | Read Replica 지원 |
| 트랜잭션 | 기본 | MVCC, 격리 수준 제어 |
| JSON 지원 | 제한적 | JSONB 네이티브 |
| 전문 검색 | 없음 | Full Text Search |
| 지리 데이터 | 없음 | PostGIS 확장 |
| 백업 | 파일 복사 | pg_dump, WAL 연속 아카이빙 |

### 4.3 캐싱 전략

```
Redis 캐시 계층:

L1: 자주 조회되는 국가별 최신 데이터
    - Key: ef:{country}:{category}:{year}
    - TTL: 1시간
    - 갱신: 수집 완료 시 invalidate

L2: 비교/트렌드 쿼리 결과
    - Key: compare:{hash(params)}
    - TTL: 6시간

L3: 전체 국가/카테고리 목록
    - Key: taxonomy:all, countries:all
    - TTL: 24시간
```

---

## 5. 구현 로드맵

### Phase 1: API 기반 구축 (3주)

```
Week 1: FastAPI 프로젝트 구조
  - api/ 디렉토리 생성
  - 라우터, 스키마, 미들웨어 설계
  - OpenAPI/Swagger 문서 자동 생성

Week 2: 핵심 엔드포인트 구현
  - GET /emissions, /countries, /taxonomy
  - Pydantic 요청/응답 모델
  - 에러 핸들링

Week 3: 인증 + Rate Limiting
  - API Key 발급/관리
  - JWT 토큰 인증
  - slowapi Rate Limiter
  - CORS 설정
```

### Phase 2: DB 마이그레이션 (3주)

```
Week 4: PostgreSQL 스키마 설계
  - SQLAlchemy ORM 모델
  - Alembic 마이그레이션 도구
  - 기존 SQLite 데이터 이전 스크립트

Week 5: 연결 풀링 + Read Replica
  - PgBouncer 또는 SQLAlchemy 풀
  - 읽기 전용 복제 설정
  - 자동 백업 (pg_dump + WAL)

Week 6: 매핑 테이블 구현
  - factor_id_mapping 테이블
  - country_code_mapping
  - unit_code_mapping
  - 자동 매핑 로직
```

### Phase 3: 성능 + 모니터링 (3주)

```
Week 7: Redis 캐시
  - 캐시 계층 구현
  - 캐시 무효화 전략
  - 수집 완료 → 캐시 갱신 연동

Week 8: 모니터링
  - Prometheus 메트릭 수집
  - Grafana 대시보드
  - Sentry 에러 추적
  - API 응답 시간/에러율 모니터링

Week 9: 부하 테스트 + 최적화
  - Locust 부하 테스트
  - 쿼리 최적화 (EXPLAIN ANALYZE)
  - N+1 쿼리 방지
  - 인덱스 튜닝
```

### Phase 4: 글로벌 배포 (2주)

```
Week 10: 컨테이너 오케스트레이션
  - Kubernetes 매니페스트
  - Helm chart
  - HPA (Horizontal Pod Autoscaler)
  - Secret 관리 (Vault)

Week 11: CDN + 글로벌 엣지
  - CloudFlare WAF
  - API 버전 관리 (v1, v2)
  - SDK 배포 (Python, JS, Go)
  - 공식 문서 사이트 (docs.nanoclaw.io)
```

---

## 6. 예상 기술 스택

| 영역 | 기술 | 용도 |
|------|------|------|
| API 프레임워크 | FastAPI + Uvicorn | REST API 서비스 |
| 인증 | python-jose (JWT) + API Key | 클라이언트 인증 |
| DB | PostgreSQL 16 | 메인 데이터베이스 |
| ORM | SQLAlchemy 2.0 | DB 추상화 |
| 마이그레이션 | Alembic | 스키마 버전 관리 |
| 캐시 | Redis 7 | 쿼리 결과 캐싱 |
| Rate Limit | slowapi | 요청 제한 |
| 모니터링 | Prometheus + Grafana | 메트릭/대시보드 |
| 에러 추적 | Sentry | 실시간 에러 알림 |
| 로깅 | structlog (JSON) | 구조화 로그 |
| 컨테이너 | Docker + K8s | 배포/스케일링 |
| CDN/WAF | CloudFlare | 보안/성능 |
| CI/CD | GitHub Actions | 자동 빌드/배포 |
| 문서 | Swagger UI (자동) | API 문서 |

---

## 7. 우선순위 정리

### 지금 당장 (이번 주)
1. Git 히스토리 토큰 제거
2. Slack 토큰 재발급

### 1차 목표 (1개월)
3. FastAPI 기본 엔드포인트
4. API Key 인증
5. PostgreSQL 전환

### 2차 목표 (2개월)
6. Redis 캐시
7. Rate Limiting
8. 모니터링 (Prometheus)
9. 매핑 테이블 구현

### 3차 목표 (3개월)
10. Kubernetes 배포
11. CDN/WAF
12. SDK 배포
13. 공식 문서 사이트
