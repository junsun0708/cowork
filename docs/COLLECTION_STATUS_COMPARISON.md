# 수동 vs 자동 수집 현황 비교 분석

> 작성일: 2026-03-12
> 목적: 수동/자동 수집 데이터 수준 비교 및 자동 수집 실패 원인 분석

---

## 1. 전체 요약

| 항목 | 수동 수집 (doc) | 자동 수집 - 코드 | 자동 수집 - 실제 |
|------|----------------|-----------------|-----------------|
| **배출계수 수** | **99,380건** | 설계상 무제한 | **~384건** (0.4%) |
| **국가** | **214개** 코드 | 18개 설정 | **2개** 성공 |
| **소스/기관** | 28개 파일 | 33개 | 2개 성공 |
| **분류 체계** | 4단계 + Scope | 4단계 + Scope (v2) | 미검증 |
| **GWP 버전** | SAR~AR6 5개 | SAR~AR6 5개 (v2) | 미검증 |
| **개별 가스** | CO2/CH4/N2O 분리 | 지원 (v2) | 미검증 |
| **Factor-id** | 체계적 ID (99,380건) | 호환 ID 생성 (v2) | 미검증 |

**코드 설계: 수동 수집 수준의 ~90% 도달 / 실제 데이터: ~0.4% 수준**

---

## 2. 국가별 수집 성공/실패 현황

### 성공 (2개국)

| 국가 | 기관 | 포맷 | 수집건수 | 성공 이유 |
|------|------|------|---------|-----------|
| US | EPA | xlsx | 65건 | xlsx 직접 다운로드 URL 제공 |
| JP | MOE | xlsx | 319건 | xlsx 직접 다운로드 URL 제공 |

### 실패 (16개국) - 원인별 분류

#### A. data_urls가 안내 페이지 URL (직접 데이터 파일이 아님) — 8개국

| 국가 | 기관 | 문제 URL | 실제 필요 |
|------|------|---------|-----------|
| NZ | MFE | 가이드 HTML 페이지 | xlsx 직접 URL |
| IN | MoEFCC | GHG 프로그램 소개 페이지 | PDF 보고서 URL |
| IN | CEA | CDM 안내 페이지 | 실제 PDF/Excel URL |
| MX | SEMARNAT | 정책 안내 페이지 | 데이터 파일 URL |
| MX | CRE | 기사 페이지 | 데이터 파일 URL |
| CR | MINAE/IMN | 기관 안내 페이지 | 데이터 파일 URL |
| PE | MINAM/OSINERGMIN | 안내 페이지 | 데이터 파일 URL |
| VN | MONRE/EVN | 뉴스/안내 페이지 | 데이터 파일 URL |

#### B. data_format과 URL 타입 불일치 (코드 버그) — 3개국

| 국가 | 기관 | 설정 format | 실제 URL 타입 | 문제 |
|------|------|------------|-------------|------|
| GB | DEFRA | xlsx | URL 1개는 HTML, 1개는 xlsx | HTML을 xlsx로 파싱 시도 → 실패 |
| FR | ADEME | csv | HTML 다운로드 페이지 | HTML을 csv로 파싱 시도 → 실패 |
| NZ | MFE | xlsx | HTML 가이드 페이지 | HTML을 xlsx로 파싱 시도 → 실패 |

#### C. 인증/동적 페이지 — 3개국

| 국가 | 기관 | 문제 |
|------|------|------|
| KR | GIR (NGMS) | 로그인 인증 필요 |
| KR | KEITI | data_urls 없음 |
| TW | MOENV/BOE | ASP.NET 동적 페이지, JS 렌더링 필요 |

#### D. data_urls 미설정 — 2개국

| 국가 | 기관 | 문제 |
|------|------|------|
| CN | MEE | data_urls 없음, 메인 페이지만 |
| BR | — | source_registry/BR.json 파일 자체가 없음 |

#### E. PDF/접근 문제 — 3개국

| 국가 | 기관 | 문제 |
|------|------|------|
| AU | DCCEEW | PDF URL이 2025년판 (미발행 가능성) |
| DE | UBA | PDF URL 유효성 불확실 |
| JP | IGES | 403 Forbidden (봇 차단) |

#### F. INTL 소스 — 전체 영향

| 기관 | 문제 |
|------|------|
| IPCC, IEA, UNFCCC, EDGAR, WorldBank | 5개 모두 data_urls 없음 → 매 국가 수집 시 불필요하게 홈페이지 크롤링 |

---

## 3. 핵심 버그: `fetch_auto` 포맷 판별

```python
# 현재 코드 (fetcher.py:220-231)
def fetch_auto(self, url, data_format="html", save_dir=None):
    if data_format == "xlsx":        # ← data_format을 먼저 체크
        return self.fetch_excel(url)  # ← HTML 페이지도 xlsx로 파싱 시도!
```

**문제**: 소스 레벨에서 `data_format: "xlsx"`로 설정하면, 해당 소스의 모든 `data_urls`에 동일 포맷 적용.
GB/DEFRA처럼 URL이 2개(HTML 안내 + xlsx 파일)인 경우, HTML 안내 페이지도 xlsx로 파싱 → 실패.

**수정**: URL 확장자를 먼저 판별하고, 확장자가 없을 때만 data_format 사용.

---

## 4. 수동 수집에만 있는 데이터 (자동으로 수집 불가)

| 데이터 유형 | 수동 DB 건수 | 자동 수집 가능성 |
|------------|-------------|----------------|
| EPD/제품 레벨 | ~3,000건 | 불가 (비표준 구조) |
| EEIO/Spend Base | ~10,000건 | 불가 (학술 데이터) |
| Carbon Catalogue (CDP) | ~300건 | 불가 (유료/인증) |
| Laptop PCF | ~6,000행 | 불가 (제조사별 상이) |
| Events/Conferences | ~100건 | 불가 (수동 조사) |

---

## 5. 즉시 수정 가능한 항목

| 순위 | 수정 내용 | 예상 효과 |
|------|----------|-----------|
| 1 | `fetch_auto` URL 확장자 우선 판별 | GB, FR, NZ 수집 성공 가능 |
| 2 | INTL 소스 data_urls 없으면 스킵 | 불필요 크롤링 제거, 속도 개선 |
| 3 | GB/DEFRA xlsx URL 최신화 | +7,000건 수집 가능 (수동 DB 최대 소스) |
| 4 | eGRID xlsx 직접 URL 추가 | US 수집 건수 확대 |
| 5 | BR.json 생성 | 브라질 수집 가능 |
