# 배출계수 수집 패턴 비교 분석

> 작성일: 2026-03-12
> 비교 대상: 수동 수집 (`/projects/doc`) vs 자동 수집 (`/projects/cowork`)

---

## 1. 수동 수집 행동 패턴 분석 (`/projects/doc`)

### 1.1 수집 프로세스

TS-CMS 매뉴얼 및 파일 구조에서 파악된 수동 수집 워크플로우:

```
1. 출처 선정
   └─ 각국 환경/에너지 부처, IPCC, EC, EEA 등 공신력 있는 기관 직접 탐색

2. 원본 데이터 확보
   └─ 정부 보고서, PDF, Excel 파일을 직접 다운로드

3. 데이터 정제 및 표준화
   ├─ GWP 기준 확인 (SAR/TAR/AR4/AR5/AR6 모두 지원)
   ├─ 단위 통일: kgCO2e 기준으로 환산
   ├─ 다국어 항목명 → 표준 분류체계 매핑
   └─ Factor-id 부여 (국가-Scope-카테고리-코드-버전년도)

4. Excel DB 파일로 정리
   ├─ 출처별 개별 파일: EF_Database (UK BEIS 2025)_v250707.xlsx
   ├─ 마스터 통합 파일: EF_Database_v251215.xlsx (13.1MB)
   └─ 인덱스 파일: EF_Directory_v260302.xlsx

5. 보조 도구 관리
   ├─ 다국어 사전: EF_Database_Multilingual_Dictionary_v250806.xlsx
   └─ 관리 매뉴얼: TS-CMS 배출계수 관리 매뉴얼_260302.docx
```

### 1.2 데이터 소스 (26개 파일, 24개국+)

| 유형 | 소스 수 | 예시 |
|------|---------|------|
| 정부/공식 기관 | 11 | UK BEIS, US EPA, JP MOE, AU DCCEEW, NZ MFE, KEITI |
| 국제기구/학술 | 5 | IPCC, EC-JRC(CBAM), World Bank, Carbon Catalogue, KAIST EEIO |
| 산업/분야 특화 | 5 | Logistics, Worldsteel, WRAP, Events, Commuting&Travel |
| 제품 특화 | 1 | Laptop PCF |
| 유틸리티 특화 | 1 | Electricity (CN, VN, ID) |
| 지역 통합 | 1 | BRA, MEX, CRI, PER |
| 참조/인덱스 | 2 | EF_Directory, Multilingual Dictionary |

### 1.3 분류 체계

```
Scope (1/2/3)
  └─ Level1 (대분류): Fuels, Electricity, Purchased services, Waste ...
       └─ Level2 (중분류): Gaseous fuels, Liquid fuels, Solid fuels ...
            └─ Level3 (소분류): Butane, Diesel, LPG ...
                 └─ Level4 (세부): 제품별 상세 (EPD 등)
```

- **Factor-id 예시**: `GBR-S1-C-11 11 11 00-11-0-2022` (영국, Scope1, 가스연료, 부탄, 2022)
- **4단계 계층** + Scope 분류로 수천 개 배출계수 체계적 관리

### 1.4 데이터 품질 관리

- GWP 5개 평가주기(SAR~AR6) 모두 지원 → 어떤 기준으로든 환산 가능
- CO2, CH4, N2O 개별 가스 배출계수 + 통합 CO2e 값 동시 보유
- 분자량, 무게 환산(lb→kg) 등 메타 데이터 포함
- 동일 출처 다년도 버전 병행 관리 (UK BEIS 2023/2024/2025)

### 1.5 버전 관리

```
파일명 규칙: EF_Database (출처명)_vYYMMDD.xlsx
업데이트 빈도:
  - 활발: 월~분기 단위 (Elec. CN VN ID v260227, Laptop PCF v260226)
  - 안정: 연 1~2회 (정부 공식 데이터)
  - 보존: 업데이트 없음 (Events & Conferences v231102)
```

---

## 2. 자동 수집 패턴 분석 (`/projects/cowork`)

### 2.1 수집 파이프라인

```
Source Discovery → Fetcher → Extractor → Normalizer → DB Sync → Reporting
     (소스 탐색)   (데이터 수집)  (항목 추출)  (정규화)    (DB 저장)  (Slack 보고)
```

### 2.2 데이터 소스 (10개국 + 5개 국제기구)

| 국가 | 기관 | 포맷 |
|------|------|------|
| KR | GIR, KEITI | html, html |
| US | EPA, eGRID | xlsx, xlsx |
| JP | MOE, IGES | xlsx, html |
| GB | DEFRA | xlsx |
| DE | UBA | pdf |
| FR | ADEME | csv |
| AU | DCCEEW | pdf |
| CN | MEE | 미정의 |
| INTL | IPCC, IEA, UNFCCC, EDGAR, WorldBank | 다양 |

### 2.3 분류 체계

```
5개 대분류 → 25개 세부 카테고리:
  Energy (8): electricity, natural_gas, coal, diesel, gasoline, lpg, fuel_oil, renewable_energy
  Transportation (4): road_transport, aviation, marine_transport, rail_transport
  Industry (5): cement, steel, chemical, aluminum, fertilizer
  Waste (3): landfill, wastewater, recycling
  Agriculture (3): livestock, rice, fertilizer_use
```

### 2.4 DB 스키마 (SQLite)

```
processed_emissions 테이블:
  uid, country_code, source_org, source_type, data_reliability_score,
  category, item_name_original, item_name_standard,
  standard_value, standard_unit, year, language_code,
  raw_file_path, mapping_log, conversion_factor,
  extraction_method, table_context, last_checked_at, created_at
```

### 2.5 파싱 프로필

| 프로필 | 국가 | 포맷 | 특징 |
|--------|------|------|------|
| EPA | US | html+xlsx | "per" 형식 단위 지원 |
| GIR | KR | pdf+html | 한국어 키워드 매칭 |
| DEFRA | GB | xlsx | kg CO2e 직접 매핑 |

- 3개 프로필만 존재, 나머지 국가는 범용 추출 로직 사용

---

## 3. 핵심 차이점 비교

### 3.1 소스 커버리지

| 항목 | 수동 수집 | 자동 수집 | 차이 |
|------|-----------|-----------|------|
| 국가 수 | 24개국+ | 10개국 | 수동이 2.4배 넓음 |
| 소스 파일 수 | 26개 DB | 15개 소스 | 수동이 다양 |
| LATAM 지역 | BRA, MEX, CRI, PER | BR만 | 수동이 넓음 |
| NZ | 2022, 2023 버전 | 미포함 | 자동에 누락 |
| VN, ID | 전력 배출계수 포함 | 미포함 | 자동에 누락 |
| 산업 특화 | Worldsteel, WRAP, Logistics | 카테고리만 존재 | 수동이 깊음 |
| 제품 레벨 | Laptop PCF, EPD 상세 | 미지원 | 수동만 가능 |
| 행사/출장 | Events, Commuting&Travel | 미지원 | 수동만 가능 |
| Spend Base | 경제입출력 모델 | 미지원 | 수동만 가능 |

### 3.2 분류 체계 깊이

| 항목 | 수동 수집 | 자동 수집 |
|------|-----------|-----------|
| 계층 깊이 | **4단계** (Level1~4) | **1단계** (25개 카테고리) |
| Scope 구분 | Scope 1/2/3 명시 | 구분 없음 |
| Factor-id | 국가-Scope-코드-버전 체계적 ID | country-org-item-year 단순 UID |
| GWP 기준 | SAR/TAR/AR4/AR5/AR6 **5개 모두** | 단일 값만 저장 |
| 개별 가스 | CO2, CH4, N2O 분리 저장 | CO2e 통합값만 |

### 3.3 데이터 품질

| 항목 | 수동 수집 | 자동 수집 |
|------|-----------|-----------|
| 정확도 | 사람이 직접 검증 → **높음** | 정규식 자동 추출 → **변동적** |
| 단위 환산 | 분자량, 무게 환산 메타데이터 포함 | 23가지 규칙 기반 자동 변환 |
| 다국어 | 7개 언어 사전 보유 | 6개 언어 항목명 매핑 (200+) |
| 다년도 관리 | 동일 출처 여러 해 병행 보유 | 최신 값만 유지 (upsert) |
| 변경 이력 | 파일명 버전으로 전체 스냅샷 보존 | diff_report만 생성, 이전 값 덮어쓰기 |

### 3.4 운영 방식

| 항목 | 수동 수집 | 자동 수집 |
|------|-----------|-----------|
| 수집 주기 | 비정기 (담당자 판단) | 주간 자동 + 수동 트리거 |
| 소요 시간 | 수일~수주 | 수분 |
| 확장성 | 인력 비례 | 소스 등록만 하면 자동 확장 |
| 구조 변경 대응 | 사람이 즉시 판단 | HTML 해시 변경 감지 알림 |
| 알림 | 없음 | Slack 실시간 보고 |

---

## 4. 수동 수집의 강점 (자동 수집에 없는 것)

### 4.1 깊이 있는 도메인 지식 반영
- **EPD(환경성적표지) 제품 레벨 배출계수**: 가공곡물, 고단백바 등 개별 제품까지 수집
- **PCF(제품탄소발자국)**: Laptop 모델별 탄소 발자국 (Scope 3 상세)
- **경제입출력 모델**: KAIST EEIO, US Supply Chain 등 산업연관분석 기반 데이터
- **Carbon Catalogue**: CDP 연계 기업 단위 배출 데이터

### 4.2 맥락적 판단
- 동일 항목의 여러 출처 비교 후 **최적 값 선택**
- GWP 평가주기별 차이를 이해하고 **적용 맥락에 맞는 값 제공**
- 정부 통계의 **개정/수정 반영** (errata 등)

### 4.3 체계적 표준화
- Factor-id가 **글로벌 고유 식별자** 역할 → 시스템 간 연동 가능
- 4단계 계층 분류 → 세밀한 검색/필터링 가능
- 다국어 사전으로 **일관된 용어 사용** 보장

---

## 5. 자동 수집의 강점 (수동 수집에 없는 것)

### 5.1 운영 효율
- **주간 자동 동기화**: 사람 개입 없이 최신 데이터 유지
- **Slack Bot 인터페이스**: 채널에서 즉시 수집/조회/동기화 가능
- **변경 감지**: 웹페이지 구조 변경 시 자동 알림

### 5.2 Raw 데이터 보존
- 원본 HTML/PDF/Excel 텍스트를 JSON으로 보존 → 추후 재추출 가능
- 수동 수집은 정제된 결과만 남기고 원본은 별도 보관하지 않음

### 5.3 파이프라인 추적성
- `extraction_method`, `mapping_log`, `table_context` 등 추출 과정 기록
- `last_checked_at`으로 데이터 신선도 추적

---

## 6. 개선 방향 제안

### 6.1 자동 수집 시스템 개선 (우선순위 순)

#### P1: 분류 체계 고도화
- **현재**: 1단계 25개 카테고리 (flat)
- **목표**: 수동 수집의 4단계 계층 구조 도입
- **방법**: EF_Directory의 Scope/Level1~4 체계를 DB 스키마에 반영
- **효과**: 기존 수동 DB와 호환 가능, 세밀한 검색/필터링

#### P2: Scope 구분 추가
- **현재**: Scope 개념 없음
- **목표**: Scope 1/2/3 자동 분류
- **방법**: 카테고리-Scope 매핑 테이블 + 소스별 Scope 메타데이터 활용
- **효과**: GHG 프로토콜 준수, 기업 탄소 보고에 직접 활용 가능

#### P3: GWP 다중 기준 지원
- **현재**: 단일 CO2e 값만 저장
- **목표**: SAR/AR4/AR5/AR6 별 값 또는 CO2/CH4/N2O 개별 가스 저장
- **방법**: DB 컬럼 확장 또는 별도 테이블
- **효과**: 보고 기준에 맞는 유연한 값 제공

#### P4: 소스 커버리지 확대
- **현재**: 10개국 + 5개 국제기구
- **목표**: 수동 수집 수준의 24개국+ 커버리지
- **우선 추가 대상**:
  - NZ (MFE) - 이미 수동 DB에 2개 버전 존재
  - VN, ID - 전력 배출계수
  - MEX, CRI, PER - LATAM 확대
  - Worldsteel, WRAP - 산업 특화

#### P5: 파싱 프로필 확대
- **현재**: EPA, GIR, DEFRA 3개만
- **필요**: 국가/기관별 데이터 포맷이 다르므로 프로필 추가 필수
- **우선 대상**: JP MOE, AU DCCEEW, DE UBA, FR ADEME

#### P6: 다년도 데이터 보존
- **현재**: upsert로 최신 값만 유지 (이전 값 덮어쓰기)
- **목표**: 연도별 이력 보존
- **방법**: UID에서 year를 분리하거나, 이력 테이블 별도 관리
- **효과**: 시계열 분석, 트렌드 파악 가능

#### P7: Factor-id 호환
- **현재**: `KR-GIR-electricity-2022` (자체 UID)
- **목표**: 수동 DB의 Factor-id 체계와 매핑/호환
- **방법**: Factor-id 생성 규칙을 EF_Directory 기준으로 통일
- **효과**: 수동 DB ↔ 자동 DB 간 데이터 병합 가능

### 6.2 수동 수집 프로세스 개선

#### M1: 자동 수집으로 대체 가능한 영역 식별
- 정부 공식 사이트에서 정기 발행하는 데이터 → 자동화 우선 대상
- UK BEIS, US EPA, JP MOE 등은 이미 자동 수집 대상

#### M2: 수동 수집이 반드시 필요한 영역 정의
- EPD/PCF 제품 레벨 데이터 (구조가 비표준)
- 경제입출력 모델 데이터 (KAIST EEIO, Supply Chain)
- 신규 출처 탐색 및 최초 수집

#### M3: 검증 워크플로우 구축
- 자동 수집 결과를 수동 DB와 교차 검증
- 차이가 큰 항목에 대해 사람이 확인하는 하이브리드 모델

---

## 7. 요약 비교표

| 비교 항목 | 수동 수집 (doc) | 자동 수집 (cowork) |
|-----------|-----------------|---------------------|
| 소스 범위 | 26개 DB, 24개국+ | 15개 소스, 10개국 |
| 분류 깊이 | 4단계 + Scope | 1단계 (25 카테고리) |
| GWP 기준 | 5개 (SAR~AR6) | 단일 값 |
| 개별 가스 | CO2, CH4, N2O 분리 | CO2e 통합만 |
| 제품 레벨 | EPD, PCF 상세 | 미지원 |
| 산업 특화 | 철강, 물류, 식품 등 | 카테고리만 |
| 다국어 | 7개 언어 사전 | 6개 언어 매핑 |
| Factor-id | 체계적 글로벌 ID | 단순 UID |
| 수집 속도 | 수일~수주 | 수분 |
| 수집 주기 | 비정기 | 주간 자동 |
| 변경 감지 | 수동 확인 | 자동 알림 |
| 원본 보존 | 별도 보관 | JSON 자동 저장 |
| 데이터 이력 | 파일 버전으로 보존 | 최신만 유지 |
| 확장성 | 인력 비례 | 소스 등록 시 자동 |
