# 수동 vs 자동 수집 현황 비교 분석

> 최종 갱신: 2026-03-13 (v7)
> 목적: 수동/자동 수집 데이터 수준 비교 및 자동 수집 실패 원인 분석

---

## 1. 전체 요약

| 항목 | 수동 수집 (doc) | 자동 수집 v7 (2026-03-13) |
|------|----------------|--------------------------|
| **배출계수 수** | **99,200건** | **20,832건** (21.0%) |
| **국가** | 100+ 코드 | 18개 설정, 6개국 성공 |
| **소스/기관** | 28개 파일 | 33개 설정, 7개 성공 |
| **분류 체계** | 4단계 + Scope | 4단계 + Scope |
| **GWP 버전** | SAR~AR6 5개 | SAR~AR6 5개 |
| **개별 가스** | CO2/CH4/N2O 분리 | 지원 |
| **Scope 정규화** | Scope 1/2/3 | Scope 1/2/3 (v7 통일) |

### 개선 이력

| 버전 | DB 레코드 | 수집률 | 주요 변경 |
|------|----------|--------|----------|
| v1 (초기) | 1,378 | 1.4% | 기본 파서 |
| v2 | 9,333 | 9.4% | eGRID 전용 파서 |
| v3 | 10,807 | 10.9% | CBAM 전용 파서 |
| v4 | 11,341 | 11.4% | DEFRA 멀티컬럼 파서 |
| v5 | 18,291 | 18.4% | CBAM 121개국 파서 |
| v6 | 18,421 | 18.6% | URL 연도 추출 확장 |
| **v7** | **20,832** | **21.0%** | DEFRA fuel_label 매핑 수정, item_cols 확장, Outside of scopes 처리, Scope 정규화 |

---

## 2. v7 개선 내역 요약

### 코드 개선 (v1 → v7)

| 개선 항목 | 파일 | 효과 |
|----------|------|------|
| eGRID 전용 파서 | extractor.py | +7,411건 (주별/서브리전별 배출계수) |
| CBAM 121개국 파서 | extractor.py | 258 → 7,183건 |
| DEFRA 멀티컬럼 파서 | extractor.py | 296 → 5,264건 |
| DEFRA fuel_label 정확 매핑 | extractor.py | Waste/Material/Hotel 등 개선 |
| DEFRA item_cols 키워드 확장 | extractor.py | Refrigerant 5→357, Hotel 1→39 |
| Outside of scopes 처리 | extractor.py | +56건 (개별 가스 only 시트) |
| URL 기반 연도 추출 | orchestrator.py | NZ MFE 3년 분리, DEFRA year=0 해결 |
| Unicode 구독자 정규화 | extractor.py | NZ MFE kg CO₂e → CO2e |
| eGRID 단위 변환 추가 | normalizer.py | lb/MWh, lb/mmBtu 단위 지원 |
| Scope 형식 통일 | normalizer.py | "Scope1" → "Scope 1" |
| JP MOE default_unit 추가 | JP.json | 534건 복원 |

### 주요 버그 수정

| 버그 | 원인 | 수정 |
|------|------|------|
| `fetch_auto` 포맷 불일치 | data_format을 URL 확장자보다 우선 적용 | URL 확장자 → Content-Type → data_format 순 판별 |
| Sub-header 오탐 | 숫자 포함 데이터 행을 단위 행으로 인식 | numeric_cells <= 1 조건 추가 |
| DEFRA year=0 | URL에서 연도 미추출 | 다중 패턴 regex 추가 |
| Scope 혼재 | TAXONOMY_HIERARCHY에서 "Scope1", extractor에서 "Scope 1" | normalizer에서 통일 |

---

## 3. 추가 개선 기회

### 단기 (자동화 가능, 파서 개선 필요)

| 순위 | 소스 | 현재 | 예상 | 작업 내용 |
|------|------|------|------|----------|
| 1 | GB/DEFRA | 5,264 | ~8,000 | 개별 가스(CO2/CH4/N2O) 별도 행 저장 시 수동 수준 도달 |
| 2 | US/EPA Hub | 160 | ~3,000 | Table 2~5 파싱 (Mobile, 산업공정 등) |
| 3 | NZ/MFE | 277 | ~1,500 | 시트별 전용 파서 (UID 개선) |
| 4 | JP/MOE | 534 | ~2,000 | itiran.xlsx 다중 시트 파싱 개선 |
| 5 | AU/DCCEEW | 0 | ~1,600 | PDF URL 갱신, timeout 증가 |

### 중기 (소스 추가 필요)

| 소스 | 예상 건수 | 필요 작업 |
|------|----------|----------|
| US Supply Chain | ~1,000 | source_registry 추가 + 파서 |
| Logistics | ~1,000 | source_registry 추가 |
| WRAP | ~700 | source_registry 추가 |
| WorldBank API | ~600 | API 파서 개선 |
| Commuting/Travel KR | ~200 | source_registry 추가 |

### 자동화 불가 (수동 유지)

| 소스 | 건수 | 사유 |
|------|------|------|
| EF_Database 메인 | 25,136 | 수동 가공 통합 DB |
| Spend Base | 9,896 | 학술 데이터 |
| Laptop PCF | 6,108 | 제조사별 상이 |
| IPCC 2006 | 4,079 | 로그인/CAPTCHA |
| KEITI EPD | 3,081 | API 키 발급 필요 |
| KAIST EEIO | 393 | 학술 데이터 |
| Carbon Catalogue | 844 | 유료/인증 |
| Events | 121 | 수동 조사 |

---

## 6. 소스별 수집률 현황 및 원인 분석 (v7 기준)

> 기준: 2026-03-13 v7 실행 결과

### 자동 수집 성공 소스

| 소스 | 수동 건수 | 자동 v7 | 수집률 | 비고 |
|------|----------|---------|--------|------|
| US/eGRID | (EF_Database_v251215.xlsx 포함) | **7,411** | — | 전용 파서, 주별/서브리전별 CO2/CH4/N2O/CO2e |
| CBAM EC-JRC | 7,649 | **7,183** | 93.9% | 121개국 시트 전용 파서 |
| GB/DEFRA (3개년) | 21,071 | **5,264** | 25.0% | v7에서 fuel_label 매핑 수정, item_cols 확장 |
| JP/MOE | 3,813 | **534** | 14.0% | 전력 배출계수 중심 |
| NZ/MFE (3개년) | 5,588 | **277** | 5.0% | URL 연도 추출로 3년 분리 |
| US/EPA Hub | 3,540 | **160** | 4.5% | Table 1, 6만 추출 |
| DE/UBA | — | **3** | — | PDF 파싱 제한적 |

### 자동 수집 미대응 소스 (수동에만 존재)

| 소스 | 수동 건수 | 미수집 원인 | 자동화 가능성 |
|------|----------|------------|-------------|
| EF_Database (메인) | 25,136 | 수동 가공 통합 DB | 낮음 (원본 데이터 필요) |
| Spend Base | 9,896 | 학술 데이터 | 불가 |
| Laptop PCF | 6,108 | 제조사별 상이 구조 | 불가 |
| IPCC 2006 | 4,079 | EFDB 로그인/CAPTCHA | 불가 (수동 다운로드 필요) |
| KEITI EPD | 3,081 | 공공데이터포털 API 키 필요 | 가능 (키 발급 후) |
| AU DCCEEW (2개년) | 1,649 | PDF timeout | 중간 (URL 갱신 필요) |
| BRA/MEX/CRI/PER | 1,131 | 403/404/timeout | 낮음 |
| China MEE | 1,022 | 비구조화 HTML | 낮음 |
| US Supply Chain | 1,062 | 미설정 | 중간 |
| Logistics | 1,014 | 미설정 | 중간 |
| Carbon Catalogue | 844 | 유료/인증 | 불가 |
| WRAP | 719 | 미설정 | 중간 |
| WorldBank | 591 | API 구조 상이 | 중간 |
| KAIST EEIO | 393 | 학술 데이터 | 불가 |
| US EPA EnergyStar | 321 | 에너지 효율 데이터 (배출계수 아님) | 해당없음 |
| Commuting/Travel KR | 198 | 미설정 | 중간 |
| Worldsteel | 136 | 미설정 | 중간 |
| Events/Conferences | 121 | 수동 조사 | 불가 |
| Elec. CN/VN/ID | 38 | 미설정 | 높음 |

### 수집률 요약

| 구분 | 건수 | 비율 |
|------|------|------|
| **자동 수집 성공** | **20,832** | **21.0%** |
| 자동화 가능 (미구현) | ~5,000 | ~5% |
| 자동화 불가 (수동 only) | ~73,368 | ~74% |
| **수동 수집 총계** | **99,200** | 100% |
