"""
NanoClaw Seed Data
- 검증용 시드 데이터 (공식 발표된 주요 배출계수)
- 초기 DB 구축 및 파이프라인 검증용
"""

# 공식 발표된 주요 글로벌 배출계수 (출처 명시)
SEED_DATA = [
    # ── 한국 (KR) ──
    {
        "country_code": "KR", "source_org": "GIR", "source_type": "Government",
        "data_reliability_score": 5, "category": "electricity",
        "item_name_original": "전력 간접배출계수",
        "item_name_standard": "electricity",
        "standard_value": 0.4594, "standard_unit": "kgCO2e/kWh",
        "year": 2022, "language_code": "ko",
        "raw_file_path": "seed_data", "mapping_log": "GIR 국가 배출계수 공식 데이터",
    },
    {
        "country_code": "KR", "source_org": "GIR", "source_type": "Government",
        "data_reliability_score": 5, "category": "natural_gas",
        "item_name_original": "천연가스 (LNG)",
        "item_name_standard": "natural_gas",
        "standard_value": 2.176, "standard_unit": "kgCO2e/m3",
        "year": 2022, "language_code": "ko",
        "raw_file_path": "seed_data", "mapping_log": "GIR 국가 배출계수 공식 데이터",
    },
    {
        "country_code": "KR", "source_org": "GIR", "source_type": "Government",
        "data_reliability_score": 5, "category": "diesel",
        "item_name_original": "경유",
        "item_name_standard": "diesel",
        "standard_value": 2.582, "standard_unit": "kgCO2e/L",
        "year": 2022, "language_code": "ko",
        "raw_file_path": "seed_data", "mapping_log": "GIR 국가 배출계수 공식 데이터",
    },
    {
        "country_code": "KR", "source_org": "GIR", "source_type": "Government",
        "data_reliability_score": 5, "category": "gasoline",
        "item_name_original": "휘발유",
        "item_name_standard": "gasoline",
        "standard_value": 2.097, "standard_unit": "kgCO2e/L",
        "year": 2022, "language_code": "ko",
        "raw_file_path": "seed_data", "mapping_log": "GIR 국가 배출계수 공식 데이터",
    },
    {
        "country_code": "KR", "source_org": "GIR", "source_type": "Government",
        "data_reliability_score": 5, "category": "lpg",
        "item_name_original": "LPG (프로판)",
        "item_name_standard": "lpg",
        "standard_value": 1.554, "standard_unit": "kgCO2e/L",
        "year": 2022, "language_code": "ko",
        "raw_file_path": "seed_data", "mapping_log": "GIR 국가 배출계수 공식 데이터",
    },

    # ── 미국 (US) ──
    {
        "country_code": "US", "source_org": "EPA", "source_type": "Government",
        "data_reliability_score": 5, "category": "electricity",
        "item_name_original": "US National Average Grid Electricity",
        "item_name_standard": "electricity",
        "standard_value": 0.3717, "standard_unit": "kgCO2e/kWh",
        "year": 2022, "language_code": "en",
        "raw_file_path": "seed_data", "mapping_log": "EPA eGRID 2022 national average",
    },
    {
        "country_code": "US", "source_org": "EPA", "source_type": "Government",
        "data_reliability_score": 5, "category": "natural_gas",
        "item_name_original": "Natural Gas",
        "item_name_standard": "natural_gas",
        "standard_value": 53.06, "standard_unit": "kgCO2e/GJ",
        "year": 2022, "language_code": "en",
        "raw_file_path": "seed_data", "mapping_log": "EPA GHG Emission Factors Hub",
    },
    {
        "country_code": "US", "source_org": "EPA", "source_type": "Government",
        "data_reliability_score": 5, "category": "diesel",
        "item_name_original": "Diesel Fuel",
        "item_name_standard": "diesel",
        "standard_value": 2.697, "standard_unit": "kgCO2e/L",
        "year": 2022, "language_code": "en",
        "raw_file_path": "seed_data", "mapping_log": "EPA GHG Emission Factors Hub",
    },

    # ── 일본 (JP) ──
    {
        "country_code": "JP", "source_org": "MOE", "source_type": "Government",
        "data_reliability_score": 5, "category": "electricity",
        "item_name_original": "電力排出係数 (全国平均)",
        "item_name_standard": "electricity",
        "standard_value": 0.441, "standard_unit": "kgCO2e/kWh",
        "year": 2022, "language_code": "ja",
        "raw_file_path": "seed_data", "mapping_log": "MOE 환경성 공식 발표",
    },

    # ── 영국 (GB) ──
    {
        "country_code": "GB", "source_org": "DEFRA", "source_type": "Government",
        "data_reliability_score": 5, "category": "electricity",
        "item_name_original": "UK Grid Electricity",
        "item_name_standard": "electricity",
        "standard_value": 0.2071, "standard_unit": "kgCO2e/kWh",
        "year": 2023, "language_code": "en",
        "raw_file_path": "seed_data", "mapping_log": "DEFRA GHG Conversion Factors 2024",
    },
    {
        "country_code": "GB", "source_org": "DEFRA", "source_type": "Government",
        "data_reliability_score": 5, "category": "natural_gas",
        "item_name_original": "Natural Gas",
        "item_name_standard": "natural_gas",
        "standard_value": 2.024, "standard_unit": "kgCO2e/m3",
        "year": 2023, "language_code": "en",
        "raw_file_path": "seed_data", "mapping_log": "DEFRA GHG Conversion Factors 2024",
    },

    # ── 독일 (DE) ──
    {
        "country_code": "DE", "source_org": "UBA", "source_type": "Government",
        "data_reliability_score": 5, "category": "electricity",
        "item_name_original": "Stromverbrauch (Bundesmix)",
        "item_name_standard": "electricity",
        "standard_value": 0.380, "standard_unit": "kgCO2e/kWh",
        "year": 2023, "language_code": "de",
        "raw_file_path": "seed_data", "mapping_log": "UBA 연방환경청 전력배출계수",
    },

    # ── 프랑스 (FR) ──
    {
        "country_code": "FR", "source_org": "ADEME", "source_type": "Government",
        "data_reliability_score": 5, "category": "electricity",
        "item_name_original": "Electricité (mix réseau)",
        "item_name_standard": "electricity",
        "standard_value": 0.0569, "standard_unit": "kgCO2e/kWh",
        "year": 2022, "language_code": "fr",
        "raw_file_path": "seed_data", "mapping_log": "ADEME Base Carbone (원자력 비중 높아 매우 낮음)",
    },

    # ── 호주 (AU) ──
    {
        "country_code": "AU", "source_org": "DCCEEW", "source_type": "Government",
        "data_reliability_score": 5, "category": "electricity",
        "item_name_original": "National Electricity Market Average",
        "item_name_standard": "electricity",
        "standard_value": 0.68, "standard_unit": "kgCO2e/kWh",
        "year": 2023, "language_code": "en",
        "raw_file_path": "seed_data", "mapping_log": "DCCEEW NGA Factors",
    },

    # ── 국제기구 ──
    {
        "country_code": "INTL", "source_org": "IEA", "source_type": "International",
        "data_reliability_score": 4, "category": "electricity",
        "item_name_original": "World Average Electricity Emission Factor",
        "item_name_standard": "electricity",
        "standard_value": 0.494, "standard_unit": "kgCO2e/kWh",
        "year": 2022, "language_code": "en",
        "raw_file_path": "seed_data", "mapping_log": "IEA World Energy Outlook",
    },
    {
        "country_code": "INTL", "source_org": "IPCC", "source_type": "International",
        "data_reliability_score": 4, "category": "natural_gas",
        "item_name_original": "IPCC Default Natural Gas EF",
        "item_name_standard": "natural_gas",
        "standard_value": 56.1, "standard_unit": "kgCO2e/GJ",
        "year": 2006, "language_code": "en",
        "raw_file_path": "seed_data", "mapping_log": "IPCC 2006 Guidelines default factor",
    },
    {
        "country_code": "INTL", "source_org": "IPCC", "source_type": "International",
        "data_reliability_score": 4, "category": "coal",
        "item_name_original": "IPCC Default Coal EF (Bituminous)",
        "item_name_standard": "coal",
        "standard_value": 94.6, "standard_unit": "kgCO2e/GJ",
        "year": 2006, "language_code": "en",
        "raw_file_path": "seed_data", "mapping_log": "IPCC 2006 Guidelines default factor",
    },
]
