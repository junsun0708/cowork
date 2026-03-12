# NanoClaw v2.0 변경 기록

> 작성일: 2026-03-12
> 목적: 수동 수집(doc) 장점을 자동 수집(cowork)에 통합 + 수동 수집 단점 개선

---

## 1. 변경 파일 요약

| 파일 | 변경 유형 | 핵심 내용 |
|------|-----------|-----------|
| `config/settings.py` | 대규모 확장 | 4단계 계층, GWP 5개 버전, 18개국, 다국어 사전 |
| `agents/db_sync.py` | 스키마 확장 | 개별 가스, GWP 다중값, 이력 테이블, 계층 컬럼 |
| `agents/extractor.py` | 기능 추가 | CO2/CH4/N2O 분리 추출, Scope/GWP 감지, 다국어 확장 |
| `agents/normalizer.py` | 기능 추가 | GWP 다중버전 산출, Scope 자동배정, Factor-id 생성 |
| `source_registry/*.json` | 신규 9개 | NZ, VN, ID, MX, CR, PE, TW, TH, IN |

---

## 2. 수동 수집 장점 → 자동 수집에 통합

### 2.1 분류 체계: 1단계 → 4단계 + Scope

**이전**: 5개 대분류, 25개 카테고리 (flat 구조)
```
TAXONOMY = { "Energy": ["electricity", "diesel", ...], ... }
```

**현재**: Scope → Level1 → Level2 → Level3 (4단계 계층)
```
TAXONOMY_HIERARCHY = {
    "Scope1": {
        "Fuels": {
            "Gaseous_fuels": ["natural_gas", "lpg", "propane", ...],
            "Liquid_fuels": ["diesel", "gasoline", "kerosene", ...],
            "Solid_fuels": ["coal", "anthracite", ...],
        },
        "Process_emissions": {
            "Industrial": ["cement", "steel", "aluminum", ...],
            ...
        },
    },
    "Scope2": { "Electricity": { ... } },
    "Scope3": {
        "Purchased_goods": { ... },
        "Transportation": { ... },
        "Waste": { ... },
        "Employee_activities": { "Commuting": [...], "Travel": [...], "Events": [...] },
        "Supply_chain": { "Economic_model": ["spend_base", "eeio", ...] },
        "Agriculture": { ... },
    },
}
```

- 기존 flat TAXONOMY는 계층에서 자동 생성 → 하위 호환 유지
- `get_scope_for_category()`, `get_hierarchy_for_category()` 헬퍼 함수 추가
- 카테고리 수: 25개 → **80개+** (EPD, PCF, 물류, 통근, 출장, 이벤트 등)

### 2.2 GWP 5개 평가주기 지원

**이전**: 단일 CO2e 값만 저장

**현재**: SAR/TAR/AR4/AR5/AR6 모든 IPCC 평가보고서 기준 값 동시 산출
```python
GWP_VERSIONS = {
    "SAR": {"CO2": 1, "CH4": 21,   "N2O": 310},   # 1995
    "TAR": {"CO2": 1, "CH4": 23,   "N2O": 296},   # 2001
    "AR4": {"CO2": 1, "CH4": 25,   "N2O": 298},   # 2007
    "AR5": {"CO2": 1, "CH4": 28,   "N2O": 265},   # 2014
    "AR6": {"CO2": 1, "CH4": 27.9, "N2O": 273},   # 2021
}
```

- DB 컬럼: `value_sar`, `value_tar`, `value_ar4`, `value_ar5`, `value_ar6`
- 개별 가스(CO2, CH4, N2O)가 있으면 자동 산출
- 보고 기준에 맞는 값을 유연하게 조회 가능

### 2.3 개별 가스 분리 저장 (CO2, CH4, N2O)

**이전**: CO2e 통합값만 저장

**현재**: 개별 온실가스 값과 단위를 분리 저장
```
DB 컬럼 추가:
  co2_value REAL, co2_unit TEXT,
  ch4_value REAL, ch4_unit TEXT,
  n2o_value REAL, n2o_unit TEXT,
```

- Extractor에서 테이블의 CO2/CH4/N2O 별도 컬럼 자동 감지
- 헤더 키워드: `"co2"`, `"carbon dioxide"`, `"이산화탄소"`, `"二酸化炭素"` 등
- 개별 가스 → GWP 버전별 CO2e 자동 변환

### 2.4 소스 커버리지: 10개국 → 18개국

**추가된 국가 (8개)**:

| 국가 | 코드 | 주요 기관 | 언어 |
|------|------|-----------|------|
| 뉴질랜드 | NZ | MFE | en |
| 베트남 | VN | MONRE, EVN | vi |
| 인도네시아 | ID | KLHK, PLN | id |
| 멕시코 | MX | SEMARNAT, CRE | es |
| 코스타리카 | CR | MINAE, IMN | es |
| 페루 | PE | MINAM, OSINERGMIN | es |
| 대만 | TW | MOENV, BOE | zh |
| 태국 | TH | TGO, EPPO | th |
| 인도 | IN | MoEFCC, CEA | en |

### 2.5 Factor-id 호환

**이전**: `KR-GIR-electricity-2022` (자체 단순 UID)

**현재**: 수동 DB 호환 Factor-id 체계 추가
```
형식: KR-S1-C-diesel-0-0-2024
구성: {국가}-{Scope}-C-{카테고리}-{시퀀스}-{버전}-{년도}
```

- `generate_factor_id()` 함수로 자동 생성
- 수동 DB의 Factor-id와 매핑/병합 가능
- DB 컬럼 `factor_id` 추가 + 인덱스

### 2.6 다국어 사전 확장: 6개 → 8개 언어

**이전**: 영어, 한국어, 일본어, 독일어, 프랑스어, 중국어

**현재**: + 스페인어, 포르투갈어, 태국어, 베트남어, 인도네시아어
```python
MULTILINGUAL_DICT = {
    "electricity": {
        "ko": "전력", "ja": "電力", "zh": "电力",
        "de": "Strom", "fr": "électricité",
        "es": "electricidad", "pt": "eletricidade", "th": "ไฟฟ้า"
    },
    # ... 24개 카테고리 × 8개 언어
}
```

- Extractor의 `standardize_item_name()`에도 모든 언어 번역 반영
- `classify_category()`에 모든 언어 키워드 추가

### 2.7 Scope 3 카테고리 대폭 확대

**이전**: 미지원

**현재**: GHG 프로토콜 Scope 3 전체 카테고리 지원
```
Purchased_goods: 구매 제품/서비스, EPD, PCF, 자본재
Transportation: 도로/항공/해운/철도/물류
Waste: 매립/소각/폐수/재활용
Employee_activities: 통근, 출장, 행사/컨퍼런스
Supply_chain: 경제입출력 모델 (EEIO, Spend-base)
Agriculture: 축산/작물/비료
```

---

## 3. 수동 수집 단점 → 자동으로 개선

### 3.1 다년도 이력 보존

**수동의 문제**: 파일 버전으로 전체 스냅샷 → 용량 비효율, 변경 추적 어려움

**자동의 개선**: `emission_history` 테이블로 변경 이력 자동 보존
```sql
CREATE TABLE emission_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT,
    standard_value REAL,
    previous_value REAL,
    change_type TEXT,    -- value_change, unit_change, category_change
    changed_at TEXT,
    ...
);
```

- upsert 시 이전 값 자동 보관
- `query_history(uid)` 로 특정 항목의 전체 변경 이력 조회
- 변경 유형(값/단위/카테고리)별 분류

### 3.2 실시간 변경 감지

**수동의 문제**: 정부 사이트 업데이트를 사람이 수동 확인 → 누락/지연

**자동의 개선**: HTML 해시 비교, diff_report 자동 생성, Slack 즉시 알림

### 3.3 비정기 수집 → 주간 자동 동기화

**수동의 문제**: 담당자 스케줄에 의존 → 수일~수주 지연

**자동의 개선**: 매주 월요일 09:00 자동 실행 + Slack 명령으로 즉시 트리거 가능

### 3.4 원본 추적성 강화

**수동의 문제**: 정제된 결과만 남기고 원본은 별도 보관 안함

**자동의 개선**:
- Raw 데이터 JSON 자동 보존 (`data/storage/raw/`)
- `extraction_method`, `mapping_log`, `table_context` 자동 기록
- `raw_file_path`로 원본 역추적 가능

---

## 4. DB 스키마 변경 사항

### 4.1 processed_emissions 테이블 (확장)

| 컬럼 | 타입 | 상태 | 설명 |
|------|------|------|------|
| uid | TEXT PK | 기존 | 고유 식별자 |
| **factor_id** | TEXT | **신규** | 수동 DB 호환 Factor-id |
| country_code | TEXT | 기존 | 국가 코드 |
| source_org | TEXT | 기존 | 출처 기관 |
| source_type | TEXT | 기존 | 기관 유형 |
| data_reliability_score | INT | 기존 | 신뢰도 (1-5) |
| **scope** | TEXT | **신규** | Scope 1/2/3 |
| **level1** | TEXT | **신규** | 대분류 (Fuels, Electricity, ...) |
| **level2** | TEXT | **신규** | 중분류 (Liquid_fuels, Grid, ...) |
| **level3** | TEXT | **신규** | 소분류 (diesel, electricity, ...) |
| category | TEXT | 기존 | 카테고리 (하위 호환) |
| item_name_original | TEXT | 기존 | 원본 항목명 |
| item_name_standard | TEXT | 기존 | 표준 항목명 |
| standard_value | REAL | 기존 | CO2e 통합값 |
| standard_unit | TEXT | 기존 | 단위 |
| **co2_value** | REAL | **신규** | CO2 개별값 |
| **ch4_value** | REAL | **신규** | CH4 개별값 |
| **n2o_value** | REAL | **신규** | N2O 개별값 |
| **co2_unit** | TEXT | **신규** | CO2 단위 |
| **ch4_unit** | TEXT | **신규** | CH4 단위 |
| **n2o_unit** | TEXT | **신규** | N2O 단위 |
| **gwp_version** | TEXT | **신규** | GWP 기준 (AR6 기본) |
| **value_sar** | REAL | **신규** | SAR 기준 CO2e |
| **value_tar** | REAL | **신규** | TAR 기준 CO2e |
| **value_ar4** | REAL | **신규** | AR4 기준 CO2e |
| **value_ar5** | REAL | **신규** | AR5 기준 CO2e |
| **value_ar6** | REAL | **신규** | AR6 기준 CO2e |
| year | INT | 기존 | 기준년도 |
| language_code | TEXT | 기존 | 언어 코드 |
| raw_file_path | TEXT | 기존 | Raw 파일 경로 |
| mapping_log | TEXT | 기존 | 변환 로그 |
| conversion_factor | REAL | 기존 | 단위 변환 계수 |
| extraction_method | TEXT | 기존 | 추출 방법 |
| table_context | TEXT | 기존 | 테이블 컨텍스트 |
| last_checked_at | TEXT | 기존 | 마지막 확인 |
| created_at | TEXT | 기존 | 생성 시간 |

### 4.2 emission_history 테이블 (신규)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| uid | TEXT FK | 배출계수 UID |
| factor_id | TEXT | Factor-id |
| country_code | TEXT | 국가 코드 |
| standard_value | REAL | 변경 후 값 |
| previous_value | REAL | 변경 전 값 |
| change_type | TEXT | 변경 유형 |
| changed_at | TEXT | 변경 시간 |
| ... | | (scope, level, 가스값 등 포함) |

### 4.3 마이그레이션

- `_migrate_schema()` 메서드가 기존 DB를 자동 마이그레이션
- `PRAGMA table_info`로 컬럼 확인 후 없는 컬럼만 `ALTER TABLE ADD COLUMN`
- 기존 데이터 보존 (비파괴적)

---

## 5. 수동 대비 자동 수집 최종 비교

| 항목 | v1 (이전) | v2 (현재) | 수동 DB |
|------|-----------|-----------|---------|
| 국가 수 | 10개 | **18개** | 24개+ |
| 분류 깊이 | 1단계 | **4단계+Scope** | 4단계+Scope |
| GWP 기준 | 단일 | **SAR~AR6 5개** | SAR~AR6 5개 |
| 개별 가스 | CO2e만 | **CO2/CH4/N2O 분리** | CO2/CH4/N2O 분리 |
| 카테고리 수 | 25개 | **80개+** | 수천 |
| Scope 3 | 미지원 | **전체 카테고리** | 전체 카테고리 |
| 제품 레벨 | 미지원 | **EPD/PCF 카테고리** | EPD/PCF 상세 |
| Factor-id | 단순 UID | **수동 호환 ID** | 체계적 ID |
| 다국어 | 6개 | **8개+** | 7개 |
| 이력 보존 | 덮어쓰기 | **history 테이블** | 파일 버전 |
| 수집 주기 | 수동/주간 | 주간 자동 | 비정기 |
| 변경 감지 | 해시 비교 | 해시+diff+알림 | 수동 확인 |
