# 수동 DB Factor-id 체계 평가 및 매핑 전략

> 작성일: 2026-03-12
> 평가 대상: `/projects/doc` EF_Database Factor-id 체계
> 평가 관점: 프로그래밍, 아키텍처, 글로벌 API 서비스

---

## 1. 수동 DB Factor-id 구조 분석

### 1.1 형식

```
GBR-S1-C-11 11 11 00-11-0-2022
 │   │  │  │         │  │  │
 │   │  │  │         │  │  └─ 기준연도
 │   │  │  │         │  └──── 가스타입 (0=Total, 1=CO2, 2=CH4, 3=N2O)
 │   │  │  │         └─────── 단위코드 (11=tonne, 20=litre, 39=mmBtu...)
 │   │  │  └───────────────── 카테고리코드 (4개 2-digit, 공백 구분)
 │   │  └──────────────────── 접두사 (항상 C, 한국EPD는 C-3A)
 │   └─────────────────────── Scope (S1/S2/S3)
 └─────────────────────────── 국가코드 (3자리 ISO)
```

### 1.2 실제 예시

```
GBR-S1-C-11 11 11 00-11-0-2022    (UK, Butane, tonne, Total CO2e)
GBR-S1-C-11 11 11 00-11-1-2022    (UK, Butane, tonne, CO2 only)
GBR-S1-C-11 11 11 00-20-0-2022    (UK, Butane, litre, Total CO2e)
USA-S1-C-11 11 11 00-39-1-2021    (US, Butane, mmBtu, CO2 only)
USA-S1-C-11 11 11 00-26-1-2021    (US, Butane, gallon, CO2 only)
KOR-S3-C-3A 11 11 11-9A-0-2025   (KR, EPD제품, 특수단위, Total)
CHN-S1-C-11 11 42 00-10-0-2021    (CN, Coke gas, 일반단위)
GLO-S1-C-11 11 63 10-30-1-2006    (Global, Gas works, 에너지단위)
```

---

## 2. 평가: 6/10 (보통)

### 2.1 잘 설계된 부분

| 항목 | 평가 | 설명 |
|------|------|------|
| 다차원 인코딩 | 좋음 | 국가/Scope/카테고리/단위/가스/연도를 하나의 ID에 담음 |
| 동일 항목 변형 | 좋음 | Butane 1개 → 단위 4종 × 가스 4종 = 16개 변형을 체계적 관리 |
| 정렬 가능성 | 좋음 | 문자열 정렬로 국가별/Scope별 그룹화 가능 |
| 유일성 보장 | 좋음 | 각 변형이 고유하게 식별됨 |

### 2.2 프로그래밍 관점에서 문제점

#### 문제 1: ID에 공백 포함 (Critical)
```
GBR-S1-C-11 11 11 00-11-0-2022
             ^  ^  ^
```
- URL 인코딩 필수 (`%20` 또는 `+`)
- JSON 키로 사용 시 혼란
- SQL WHERE 절에서 반드시 따옴표 필요
- REST API 경로에 사용 불가
- 코드 내 주석: `"작업 편의상 blank 삽입, 완료 후 삭제 예정"` → 미완료

#### 문제 2: 한국 EPD에서 규칙 파괴 (High)
```
표준: GBR-S1-C-11 11 11 00-11-0-2022     (C + 숫자코드)
한국: KOR-S3-C-3A 11 11 11-9A-0-2025     (C-3A + 16진수)
```
- 파서를 2개 만들어야 함
- 정규식 복잡도 증가
- 향후 다른 국가에서도 변형이 생길 가능성

#### 문제 3: 카테고리 번호 불투명 (High)
```
Level3 코드: 11, 13, 14, 15, 17, 19, 23, 25, 31, 33, 37, 39, 41...77
간격:        +2  +1  +1  +2  +2  +4  +2  +6  +2  +4  +2  +2 ...
```
- 코드만 보고 항목 식별 불가 (11=Butane? 39=Propane? 왜?)
- 국제 표준(UN CPC, HS Code, ISIC)과 무관한 독자 체계
- 새 항목 추가 시 번호 충돌 위험

#### 문제 4: 단위코드 매핑 불명확 (Medium)
```
10=?, 11=tonne, 20=litre, 22=?, 23=?, 26=gallon,
30=?, 33=kWh(Net), 34=kWh(Gross), 39=mmBtu, 9A=?
```
- 공식 매핑 문서 없음
- 22, 23, 30의 의미를 코드만으로 알 수 없음

#### 문제 5: Scope 2 부재 (Medium)
```
S1: 64개, S2: 0개, S3: 8개(한국만)
```
- 전력 배출계수(Scope 2 핵심)가 이 체계에 어떻게 포함되는지 불명확

#### 문제 6: 3자리 vs 2자리 국가코드 (Low)
```
수동: GBR, USA, KOR, CHN, JPN, AUS  (ISO 3166-1 alpha-3)
자동: GB, US, KR, CN, JP, AU        (ISO 3166-1 alpha-2)
API:  대부분 alpha-2 사용 (REST API 표준)
```

### 2.3 결론

> 수동 DB의 Factor-id는 **Excel 수동 관리에 최적화**된 체계.
> 사람이 눈으로 정렬/필터하기엔 괜찮지만, **프로그램이 파싱/생성/검증하기엔 부적합**.
> 글로벌 API에서 이 ID를 그대로 쓰면 안됨.

---

## 3. 자동 수집 Factor-id 체계 (현재)

### 3.1 형식

```
KR-GIR-scope1-diesel-2024
│   │    │      │      │
│   │    │      │      └─ 기준연도
│   │    │      └──────── 항목 표준명 (영문, 가독성 높음)
│   │    └─────────────── Scope (소문자)
│   └──────────────────── 출처 기관
└──────────────────────── 국가코드 (2자리 ISO)
```

### 3.2 장점

| 항목 | 평가 |
|------|------|
| 가독성 | `KR-GIR-scope1-diesel-2024` → 즉시 이해 가능 |
| 파싱 용이 | 공백 없음, `-` 구분, split 한번으로 파싱 |
| URL 호환 | REST API 경로에 바로 사용 가능 |
| 일관성 | 모든 국가에서 동일한 형식 |
| 확장성 | 새 국가/항목 추가 시 충돌 없음 |

### 3.3 한계

| 항목 | 평가 |
|------|------|
| 단위 구분 | 동일 항목의 다른 단위(tonne vs litre) 구분 불가 |
| 가스 분리 | CO2/CH4/N2O 개별값에 대한 별도 ID 없음 |
| 수동 DB 호환 | 직접 매핑 불가 (구조가 다름) |

---

## 4. 매핑 테이블 설계

### 4.1 개념

수동 DB Factor-id ↔ 자동 수집 UID를 **별도 매핑 테이블**로 연결.
억지로 형식을 통일하지 않고, 각자의 장점을 유지하면서 양방향 조회 가능.

### 4.2 DB 스키마

```sql
CREATE TABLE IF NOT EXISTS factor_id_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 자동 수집 시스템 ID
    auto_uid TEXT NOT NULL,

    -- 수동 DB Factor-id (원본 그대로)
    manual_factor_id TEXT,

    -- 정규화된 수동 Factor-id (공백 제거)
    manual_factor_id_normalized TEXT,

    -- 매핑 메타데이터
    country_code_alpha2 TEXT,      -- GB (자동)
    country_code_alpha3 TEXT,      -- GBR (수동)
    scope TEXT,                     -- Scope1
    category_code TEXT,            -- 11 11 11 00 (수동 원본)
    unit_code TEXT,                -- 11 (수동 단위코드)
    unit_name TEXT,                -- tonne (해석된 단위명)
    gas_type INTEGER,              -- 0=Total, 1=CO2, 2=CH4, 3=N2O
    gas_name TEXT,                 -- Total, CO2, CH4, N2O

    -- 매핑 상태
    mapping_status TEXT DEFAULT 'auto',  -- auto, manual, unmatched
    confidence REAL DEFAULT 1.0,         -- 매핑 신뢰도 (0.0~1.0)
    mapped_at TEXT DEFAULT (datetime('now')),
    notes TEXT,

    UNIQUE(auto_uid, manual_factor_id)
);

CREATE INDEX idx_mapping_auto ON factor_id_mapping(auto_uid);
CREATE INDEX idx_mapping_manual ON factor_id_mapping(manual_factor_id);
CREATE INDEX idx_mapping_normalized ON factor_id_mapping(manual_factor_id_normalized);
CREATE INDEX idx_mapping_country ON factor_id_mapping(country_code_alpha2);
```

### 4.3 국가코드 변환표

```sql
CREATE TABLE IF NOT EXISTS country_code_mapping (
    alpha2 TEXT PRIMARY KEY,    -- ISO 3166-1 alpha-2 (자동 수집)
    alpha3 TEXT NOT NULL,       -- ISO 3166-1 alpha-3 (수동 DB)
    country_name_en TEXT,
    country_name_ko TEXT
);

-- 데이터
INSERT INTO country_code_mapping VALUES
    ('GB', 'GBR', 'United Kingdom', '영국'),
    ('US', 'USA', 'United States', '미국'),
    ('KR', 'KOR', 'South Korea', '대한민국'),
    ('JP', 'JPN', 'Japan', '일본'),
    ('DE', 'DEU', 'Germany', '독일'),
    ('FR', 'FRA', 'France', '프랑스'),
    ('AU', 'AUS', 'Australia', '호주'),
    ('NZ', 'NZL', 'New Zealand', '뉴질랜드'),
    ('CN', 'CHN', 'China', '중국'),
    ('BR', 'BRA', 'Brazil', '브라질'),
    ('VN', 'VNM', 'Vietnam', '베트남'),
    ('ID', 'IDN', 'Indonesia', '인도네시아'),
    ('MX', 'MEX', 'Mexico', '멕시코'),
    ('CR', 'CRI', 'Costa Rica', '코스타리카'),
    ('PE', 'PER', 'Peru', '페루'),
    ('TW', 'TWN', 'Taiwan', '대만'),
    ('TH', 'THA', 'Thailand', '태국'),
    ('IN', 'IND', 'India', '인도'),
    ('INTL', 'GLO', 'Global', '글로벌');
```

### 4.4 단위코드 해석표

```sql
CREATE TABLE IF NOT EXISTS unit_code_mapping (
    unit_code TEXT PRIMARY KEY,   -- 수동 DB 단위코드
    unit_name TEXT NOT NULL,      -- 단위명 (영문)
    unit_standard TEXT,           -- 자동 수집 표준 단위
    notes TEXT
);

INSERT INTO unit_code_mapping VALUES
    ('10', 'default', '', '국가별 기본 단위'),
    ('11', 'tonne', 'kgCO2e/ton', '톤'),
    ('20', 'litre', 'kgCO2e/L', '리터'),
    ('22', 'GJ (AU)', 'kgCO2e/GJ', '호주 에너지 단위'),
    ('23', 'unit (JP/KR)', '', '일본/한국 특수 단위'),
    ('26', 'gallon', 'kgCO2e/gallon', '갤런 (미국)'),
    ('30', 'energy', 'kgCO2e/GJ', '에너지 단위'),
    ('33', 'kWh (Net CV)', 'kgCO2e/kWh', 'kWh 순발열량'),
    ('34', 'kWh (Gross CV)', 'kgCO2e/kWh', 'kWh 총발열량'),
    ('39', 'mmBtu', 'kgCO2/mmBtu', '백만 BTU (미국)'),
    ('9A', 'EPD unit', 'kgCO2e/unit', '한국 EPD 특수단위');
```

### 4.5 매핑 예시 데이터

```sql
INSERT INTO factor_id_mapping
    (auto_uid, manual_factor_id, manual_factor_id_normalized,
     country_code_alpha2, country_code_alpha3, scope,
     category_code, unit_code, unit_name, gas_type, gas_name,
     mapping_status, confidence)
VALUES
    -- UK Butane (tonne, Total)
    ('GB-DEFRA-scope1-lpg_butane-2022',
     'GBR-S1-C-11 11 11 00-11-0-2022',
     'GBR-S1-C-11111100-11-0-2022',
     'GB', 'GBR', 'Scope1',
     '11 11 11 00', '11', 'tonne', 0, 'Total',
     'auto', 1.0),

    -- UK Butane (tonne, CO2 only)
    ('GB-DEFRA-scope1-lpg_butane-2022',
     'GBR-S1-C-11 11 11 00-11-1-2022',
     'GBR-S1-C-11111100-11-1-2022',
     'GB', 'GBR', 'Scope1',
     '11 11 11 00', '11', 'tonne', 1, 'CO2',
     'auto', 1.0),

    -- US Diesel (mmBtu)
    ('US-EPA-scope1-diesel-2021',
     'USA-S1-C-11 13 19 00-39-1-2021',
     'USA-S1-C-11131900-39-1-2021',
     'US', 'USA', 'Scope1',
     '11 13 19 00', '39', 'mmBtu', 1, 'CO2',
     'auto', 0.9),

    -- KR EPD Product
    ('KR-KEITI-scope3-epd_product-2025',
     'KOR-S3-C-3A 11 11 11-9A-0-2025',
     'KOR-S3-C-3A111111-9A-0-2025',
     'KR', 'KOR', 'Scope3',
     '3A 11 11 11', '9A', 'EPD unit', 0, 'Total',
     'manual', 0.8);
```

### 4.6 조회 API 예시

```sql
-- 자동 UID로 수동 Factor-id 찾기
SELECT manual_factor_id, unit_name, gas_name
FROM factor_id_mapping
WHERE auto_uid = 'GB-DEFRA-scope1-lpg_butane-2022';

-- 수동 Factor-id로 자동 UID 찾기
SELECT auto_uid
FROM factor_id_mapping
WHERE manual_factor_id_normalized LIKE 'GBR-S1-C-11111100%';

-- 특정 국가의 전체 매핑 현황
SELECT mapping_status, COUNT(*) as cnt
FROM factor_id_mapping
WHERE country_code_alpha2 = 'GB'
GROUP BY mapping_status;
```

---

## 5. 매핑 자동화 전략

### 5.1 자동 매핑 가능 조건
- 국가코드(alpha2 ↔ alpha3) 변환
- 항목명 매칭 (standardize_item_name)
- Scope 매칭
- 연도 매칭

### 5.2 수동 매핑 필요 조건
- 한국 EPD 특수 형식 (C-3A)
- 카테고리코드 → 항목명 역매핑 (매핑표 필요)
- 단위코드 해석 (22, 23 등 모호한 코드)

### 5.3 매핑 신뢰도 기준

| 신뢰도 | 조건 |
|--------|------|
| 1.0 | 국가+Scope+항목명+연도 완전 일치 |
| 0.9 | 항목명 유사 매칭 (fuzzy match > 0.85) |
| 0.8 | 카테고리만 일치, 항목 세부 다름 |
| 0.5 | 수동 확인 필요 |
| 0.0 | 매핑 불가 (unmatched) |
