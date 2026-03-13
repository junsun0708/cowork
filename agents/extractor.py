"""
NanoClaw Extractor Agent
- Raw 데이터에서 배출계수 항목을 추출
- 테이블 파싱, 키워드 매칭
- 배출계수 후보 식별
- EPA 스타일 멀티 테이블 지원
- 개별 가스(CO2, CH4, N2O) 추출 지원
- Scope 감지 지원
- GWP 버전 감지 지원
"""
import re
import json
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import PDF_KEYWORDS, TABLE_KEYWORDS, TAXONOMY

logger = logging.getLogger("nanoclaw.extractor")


def get_hierarchy_for_category(category: str) -> Dict[str, str]:
    """택소노미에서 카테고리의 계층 정보를 반환"""
    for parent, children in TAXONOMY.items():
        if category in children:
            return {
                "scope": "",
                "level1": parent,
                "level2": category,
                "level3": "",
            }
    return {"scope": "", "level1": "", "level2": category or "", "level3": ""}


class Extractor:
    """Raw 데이터에서 배출계수 항목 추출"""

    # 숫자 패턴 (소수점 포함)
    NUMBER_PATTERN = re.compile(r"(\d+\.?\d*)")

    # 단위 패턴 (슬래시 구분)
    UNIT_PATTERNS = [
        re.compile(r"(kg\s*CO2e?\s*/\s*kWh)", re.IGNORECASE),
        re.compile(r"(kg\s*CO2e?\s*/\s*L)", re.IGNORECASE),
        re.compile(r"(kg\s*CO2e?\s*/\s*km)", re.IGNORECASE),
        re.compile(r"(kg\s*CO2e?\s*/\s*ton)", re.IGNORECASE),
        re.compile(r"(kg\s*CO2e?\s*/\s*m3)", re.IGNORECASE),
        re.compile(r"(kg\s*CO2e?\s*/\s*GJ)", re.IGNORECASE),
        re.compile(r"(tCO2e?\s*/\s*\w+)", re.IGNORECASE),
        re.compile(r"(gCO2e?\s*/\s*kWh)", re.IGNORECASE),
        re.compile(r"(lbs?\s*CO2e?\s*/\s*MWh)", re.IGNORECASE),
    ]

    # 일본어 단위 패턴
    JP_UNIT_PATTERNS = [
        re.compile(r"(t-?CO2e?\s*/\s*kWh)", re.IGNORECASE),
        re.compile(r"\(t-?CO2/kWh\)", re.IGNORECASE),
    ]

    # EPA 스타일 단위 패턴 ("kg CO2 per mmBtu" 형식)
    EPA_UNIT_PATTERNS = [
        re.compile(r"(kg\s+CO2\s+per\s+mmBtu)", re.IGNORECASE),
        re.compile(r"(kg\s+CO2\s+per\s+short\s+ton)", re.IGNORECASE),
        re.compile(r"(kg\s+CO2\s+per\s+gallon)", re.IGNORECASE),
        re.compile(r"(kg\s+CO2\s+per\s+scf)", re.IGNORECASE),
        re.compile(r"(kg\s+CO2\s+per\s+barrel)", re.IGNORECASE),
        re.compile(r"(g\s+CH4\s+per\s+mmBtu)", re.IGNORECASE),
        re.compile(r"(g\s+N2O\s+per\s+mmBtu)", re.IGNORECASE),
        re.compile(r"(g\s+CO2\s+per\s+mmBtu)", re.IGNORECASE),
        re.compile(r"(lb\s+CO2\s+per\s+MWh)", re.IGNORECASE),
        re.compile(r"(lb\s+CO2e?\s+per\s+MWh)", re.IGNORECASE),
        re.compile(r"(kg\s+CO2e?\s+per\s+kWh)", re.IGNORECASE),
        re.compile(r"(kg\s+CO2e?\s+per\s+unit)", re.IGNORECASE),
        re.compile(r"(kg\s+CO2e?\s+per\s+\w+)", re.IGNORECASE),
        re.compile(r"(g\s+CO2e?\s+per\s+\w+)", re.IGNORECASE),
        re.compile(r"(lb\s+CO2e?\s+per\s+\w+)", re.IGNORECASE),
    ]

    # 연도 패턴
    YEAR_PATTERN = re.compile(r"\b(20[0-2]\d)\b")

    # 테이블 경계 패턴 ("Table 1", "표 1" 등)
    TABLE_BOUNDARY = re.compile(r"^(Table\s+\d+|표\s+\d+|Part\s+\d+)", re.IGNORECASE)

    # GWP 버전 패턴
    GWP_PATTERNS = [
        (re.compile(r"\bAR6\b", re.IGNORECASE), "AR6"),
        (re.compile(r"\bAR5\b", re.IGNORECASE), "AR5"),
        (re.compile(r"\bAR4\b", re.IGNORECASE), "AR4"),
        (re.compile(r"\bSAR\b", re.IGNORECASE), "SAR"),
        (re.compile(r"\bTAR\b", re.IGNORECASE), "TAR"),
        (re.compile(r"\bSixth\s+Assessment\b", re.IGNORECASE), "AR6"),
        (re.compile(r"\bFifth\s+Assessment\b", re.IGNORECASE), "AR5"),
        (re.compile(r"\bFourth\s+Assessment\b", re.IGNORECASE), "AR4"),
        (re.compile(r"\bThird\s+Assessment\b", re.IGNORECASE), "TAR"),
        (re.compile(r"\bSecond\s+Assessment\b", re.IGNORECASE), "SAR"),
        (re.compile(r"\b6차\s*평가\b", re.IGNORECASE), "AR6"),
        (re.compile(r"\b5차\s*평가\b", re.IGNORECASE), "AR5"),
        (re.compile(r"\b4차\s*평가\b", re.IGNORECASE), "AR4"),
        (re.compile(r"\bIPCC\s+2021\b", re.IGNORECASE), "AR6"),
        (re.compile(r"\bIPCC\s+2014\b", re.IGNORECASE), "AR5"),
        (re.compile(r"\bIPCC\s+2007\b", re.IGNORECASE), "AR4"),
    ]

    # Scope 패턴
    SCOPE_PATTERNS = [
        (re.compile(r"\bScope\s*3\b", re.IGNORECASE), "Scope 3"),
        (re.compile(r"\bScope\s*2\b", re.IGNORECASE), "Scope 2"),
        (re.compile(r"\bScope\s*1\b", re.IGNORECASE), "Scope 1"),
        (re.compile(r"기타\s*간접\s*배출", re.IGNORECASE), "Scope 3"),
        (re.compile(r"간접\s*배출", re.IGNORECASE), "Scope 2"),
        (re.compile(r"직접\s*배출", re.IGNORECASE), "Scope 1"),
    ]

    # 헤더 키워드 세트
    HEADER_KEYWORDS = {
        "ef": ["emission factor", "ef", "factor", "value", "co2 factor", "ch4 factor",
               "n2o factor", "계수", "排出係数", "排出量", "conversion factor", "kg co2",
               "heat content", "carbon coefficient", "基礎排出係数", "調整後排出係数",
               "배출계수", "coefficient", "default value",
               "emission rate", "output emission", "total output", "total co2",
               "co2e", "ghg", "intensity"],
        "unit": ["unit", "단위", "単位", "mmbtu", "per", "t-co2", "kwh", "co2/kwh",
                 "lb/mwh", "kg/mwh", "lb/gwh", "tonnes", "litres"],
        "item": ["activity", "fuel", "fuel type", "item", "category", "항목",
                 "연료", "活動", "source", "type", "事業者名", "電気事業者",
                 "메뉴", "メニュー", "description", "emission source", "product",
                 "plant", "region", "subregion", "name", "sector", "material",
                 "vehicle", "flight", "hotel", "freight"],
        "year": ["year", "연도", "年度", "令和"],
        "co2": ["co2", "carbon dioxide", "이산화탄소", "二酸化炭素"],
        "ch4": ["ch4", "methane", "메탄", "メタン"],
        "n2o": ["n2o", "nitrous oxide", "아산화질소", "一酸化二窒素"],
    }

    def _extract_ember(self, tables: List[List], source_info: dict) -> List[Dict]:
        """Ember Yearly Electricity Data 전용 파서 — 215개국 전력 CO2 intensity"""
        results = []
        if not tables or not tables[0] or len(tables[0]) < 2:
            return results

        table = tables[0]
        header = [str(h).strip() for h in table[0]]
        header_lower = [h.lower() for h in header]

        # 컬럼 인덱스 탐색
        col_map = {}
        for target, keywords in [
            ("area", ["area"]),
            ("iso", ["iso 3 code", "iso3", "iso_code"]),
            ("year", ["year"]),
            ("variable", ["variable"]),
            ("unit", ["unit"]),
            ("value", ["value"]),
            ("category", ["category"]),
        ]:
            for i, h in enumerate(header_lower):
                if h in keywords:
                    col_map[target] = i
                    break

        if "value" not in col_map or "variable" not in col_map:
            return results

        # 배출계수 관련 Variable만 필터
        ef_variables = {"CO2 intensity", "Total emissions"}

        for row in table[1:]:
            variable = str(row[col_map["variable"]]).strip() if col_map.get("variable") is not None and col_map["variable"] < len(row) else ""
            if variable not in ef_variables:
                continue

            val_str = str(row[col_map["value"]]).strip() if col_map.get("value") is not None and col_map["value"] < len(row) else ""
            if val_str in ("nan", "None", "", "-"):
                continue
            try:
                value = float(val_str)
            except (ValueError, TypeError):
                continue
            if value <= 0:
                continue

            area = str(row[col_map.get("area", 0)]).strip() if col_map.get("area") is not None else ""
            iso = str(row[col_map.get("iso", 0)]).strip() if col_map.get("iso") is not None else ""
            if iso in ("nan", "None", ""):
                iso = ""

            year_str = str(row[col_map.get("year", 0)]).strip() if col_map.get("year") is not None else ""
            try:
                year = int(float(year_str))
            except (ValueError, TypeError):
                year = 0

            unit = str(row[col_map.get("unit", 0)]).strip() if col_map.get("unit") is not None else ""
            category_val = str(row[col_map.get("category", 0)]).strip() if col_map.get("category") is not None else ""

            # 표준 단위 매핑
            if unit == "gCO2/kWh":
                standard_unit = "gCO2/kWh"
            elif unit == "mtCO2":
                standard_unit = "MtCO2"
            else:
                standard_unit = unit

            # 국가 코드 결정 (ISO3 → ISO2 변환은 normalizer에서)
            country_code = iso if iso else "GLOBAL"

            item_name = f"{area} - {variable}" if area else variable
            scope = "Scope 2" if variable == "CO2 intensity" else ""

            record = {
                "item_name_original": item_name,
                "item_name_standard": item_name,
                "category": "electricity" if variable == "CO2 intensity" else "total_emissions",
                "scope": scope,
                "standard_value": value,
                "standard_unit": standard_unit,
                "year": year,
                "country_code": country_code,
                "source_org": "Ember",
                "source_type": "Research",
                "data_reliability_score": 4,
                "extraction_method": "ember_parser",
                "table_context": f"{category_val}/{variable}",
            }
            if source_info:
                record["language_code"] = source_info.get("language_code", "en")
            results.append(record)

        return results

    def _extract_owid_co2(self, tables: List[List], source_info: dict) -> List[Dict]:
        """Our World in Data CO2 데이터 전용 파서 — 전세계 CO2/GHG 배출"""
        results = []
        if not tables or not tables[0] or len(tables[0]) < 2:
            return results

        table = tables[0]
        header = [str(h).strip() for h in table[0]]
        header_lower = [h.lower() for h in header]

        # 주요 컬럼 찾기
        col_map = {}
        for i, h in enumerate(header_lower):
            if h == "country":
                col_map["country"] = i
            elif h == "year":
                col_map["year"] = i
            elif h == "iso_code":
                col_map["iso"] = i
            elif h == "co2_per_capita":
                col_map["co2_per_capita"] = i
            elif h == "ghg_per_capita":
                col_map["ghg_per_capita"] = i
            elif h == "co2":
                col_map["co2_total"] = i
            elif h == "methane":
                col_map["methane"] = i
            elif h == "nitrous_oxide":
                col_map["nitrous_oxide"] = i
            elif h == "carbon_intensity_elec":
                col_map["carbon_intensity_elec"] = i

        if "year" not in col_map:
            return results

        # 최근 10년 데이터만 추출 (2015~)
        ef_cols = {
            "carbon_intensity_elec": ("gCO2/kWh", "Scope 2", "electricity"),
            "co2_per_capita": ("tCO2/person", "", "total_emissions"),
            "ghg_per_capita": ("tCO2e/person", "", "total_emissions"),
        }

        for row in table[1:]:
            year_str = str(row[col_map["year"]]).strip() if col_map["year"] < len(row) else ""
            try:
                year = int(float(year_str))
            except (ValueError, TypeError):
                continue
            if year < 2015:
                continue

            country = str(row[col_map.get("country", 0)]).strip() if col_map.get("country") is not None else ""
            iso = str(row[col_map.get("iso", 0)]).strip() if col_map.get("iso") is not None else ""
            if iso in ("nan", "None", ""):
                continue

            for col_name, (unit, scope, category) in ef_cols.items():
                if col_name not in col_map:
                    continue
                idx = col_map[col_name]
                if idx >= len(row):
                    continue
                val_str = str(row[idx]).strip()
                if val_str in ("nan", "None", "", "-"):
                    continue
                try:
                    value = float(val_str)
                except (ValueError, TypeError):
                    continue
                if value <= 0:
                    continue

                item_name = f"{country} - {col_name.replace('_', ' ')}"
                record = {
                    "item_name_original": item_name,
                    "item_name_standard": item_name,
                    "category": category,
                    "scope": scope,
                    "standard_value": value,
                    "standard_unit": unit,
                    "year": year,
                    "country_code": iso,
                    "source_org": source_info.get("source_org", "OWID"),
                    "source_type": "Research",
                    "data_reliability_score": 4,
                    "extraction_method": "owid_parser",
                    "table_context": col_name,
                }
                if source_info:
                    record["language_code"] = source_info.get("language_code", "en")
                results.append(record)

        return results

    def _extract_unfccc_ifi(self, tables: List[List], source_info: dict) -> List[Dict]:
        """UNFCCC IFI Default Grid Emission Factors 전용 파서
        xlsx 'Dataset' 시트 구조:
        Row 0: nan | Combined Margin... | nan | nan | nan | Operating Margin...
        Row 1: nan | Firm Energy | Intermittent | Energy Efficiency | Elec Consumption | nan
        Row 2: Country / Territory | nan | nan | nan | nan | nan
        Row 3+: Afghanistan | 193.24 | 331.15 | 193.24 | 193.24 | 413.89
        단위: gCO2/kWh (=tCO2/GWh)
        """
        results = []
        for table in tables:
            if not table or len(table) < 4:
                continue

            # 국가 컬럼 찾기 (Row 2에 "Country"가 있음)
            country_col = None
            header_row_idx = None
            for ri in range(min(5, len(table))):
                row = [str(c).strip().lower() for c in table[ri]]
                for ci, cell in enumerate(row):
                    if "country" in cell:
                        country_col = ci
                        header_row_idx = ri
                        break
                if country_col is not None:
                    break

            if country_col is None:
                continue

            # 카테고리 라벨 수집 (Row 0 + Row 1 결합)
            col_labels = {}
            for ci in range(len(table[0])):
                if ci == country_col:
                    continue
                label_parts = []
                for ri in range(header_row_idx):
                    if ri < len(table) and ci < len(table[ri]):
                        cell = str(table[ri][ci]).strip()
                        if cell and cell.lower() not in ("nan", "none"):
                            label_parts.append(cell)
                if label_parts:
                    col_labels[ci] = " - ".join(label_parts)

            # 데이터 행 (header_row_idx 이후)
            for row in table[header_row_idx + 1:]:
                if country_col >= len(row):
                    continue
                country = str(row[country_col]).strip()
                if not country or country.lower() in ("nan", "none", "total", "world"):
                    continue

                for ci, label in col_labels.items():
                    if ci >= len(row):
                        continue
                    val_str = str(row[ci]).strip()
                    if val_str in ("nan", "None", "", "-", "N/A", "0"):
                        continue
                    try:
                        value = float(val_str)
                    except (ValueError, TypeError):
                        continue
                    if value <= 0:
                        continue

                    # 단위 판별: gCO2/kWh (값이 대부분 100~1000 범위)
                    unit = "gCO2/kWh"

                    record = {
                        "item_name_original": f"{country} - {label}",
                        "item_name_standard": f"{country} - Grid EF ({label})",
                        "category": "electricity",
                        "scope": "Scope 2",
                        "standard_value": value,
                        "standard_unit": unit,
                        "year": 2021,
                        "country_code": country,
                        "source_org": "UNFCCC-IFI",
                        "source_type": "International",
                        "data_reliability_score": 5,
                        "extraction_method": "unfccc_ifi_parser",
                        "language_code": "en",
                    }
                    results.append(record)

        return results

    def _extract_ademe(self, tables: List[List], source_info: dict) -> List[Dict]:
        """ADEME Base Carbone CSV API 파서
        CSV 컬럼: Nom base français, Code de la catégorie, Total poste non décomposé, Unité français 등
        """
        results = []
        if not tables or not tables[0] or len(tables[0]) < 2:
            return results

        table = tables[0]
        header = [str(h).strip() for h in table[0]]
        header_lower = [h.lower() for h in header]

        # 핵심 컬럼 매핑
        col_map = {}
        for i, h in enumerate(header_lower):
            if "nom base" in h and "fran" in h:
                col_map["name"] = i
            elif h in ("nom_base_francais", "nom base français"):
                col_map["name"] = i
            elif "total poste" in h:
                col_map["value"] = i
            elif h == "total_poste_non_decompose":
                col_map["value"] = i
            elif "unité" in h or "unite" in h:
                if "unit" not in col_map:
                    col_map["unit"] = i
            elif "code" in h and "categ" in h:
                col_map["category_code"] = i
            elif h in ("tags_francais", "tags français"):
                col_map["tags"] = i
            elif h == "type_ligne":
                col_map["type"] = i

        # 이름 컬럼이 없으면 첫 번째 텍스트 컬럼 사용
        if "name" not in col_map:
            for i, h in enumerate(header_lower):
                if any(kw in h for kw in ["name", "nom", "label", "description", "libelle"]):
                    col_map["name"] = i
                    break
        if "value" not in col_map:
            for i, h in enumerate(header_lower):
                if any(kw in h for kw in ["total", "valeur", "value", "emission", "co2"]):
                    col_map["value"] = i
                    break

        if "name" not in col_map or "value" not in col_map:
            return results

        for row in table[1:]:
            name_idx = col_map["name"]
            val_idx = col_map["value"]
            if max(name_idx, val_idx) >= len(row):
                continue

            name = str(row[name_idx]).strip()
            if not name or name.lower() in ("nan", "none", ""):
                continue

            val_str = str(row[val_idx]).strip().replace(",", ".")
            if val_str in ("nan", "None", "", "-"):
                continue
            try:
                value = float(val_str)
            except (ValueError, TypeError):
                continue
            if value <= 0:
                continue

            unit = ""
            if "unit" in col_map and col_map["unit"] < len(row):
                unit = str(row[col_map["unit"]]).strip()
            if not unit or unit.lower() in ("nan", "none"):
                unit = "kgCO2e/unit"

            category_code = ""
            if "category_code" in col_map and col_map["category_code"] < len(row):
                category_code = str(row[col_map["category_code"]]).strip()

            record = {
                "item_name_original": name,
                "item_name_standard": name,
                "category": category_code if category_code else "general",
                "scope": "",
                "standard_value": value,
                "standard_unit": unit,
                "year": 2024,
                "country_code": "FR",
                "source_org": "ADEME-BC",
                "source_type": "Government",
                "data_reliability_score": 5,
                "extraction_method": "ademe_parser",
                "language_code": "fr",
            }
            results.append(record)

        return results

    def _extract_jrc_com(self, tables: List[List], source_info: dict) -> List[Dict]:
        """EU JRC Covenant of Mayors 전력 배출계수 파서
        xlsx 시트 구조 (Table1~Table6):
        Row 0: "Table 1: CoM emission fac..." (제목행)
        Row 1: Country | nan | 1990.0 | 1991.0 | ... | 2021.0
        Row 2+: BE | Belgium | 0.408 | 0.395 | ...
        단위: tCO2/MWh
        """
        results = []
        for table in tables:
            if not table or len(table) < 3:
                continue

            # 연도 컬럼이 있는 행 찾기 (float "1990.0" ~ "2030.0" 패턴)
            header_row_idx = None
            year_cols = {}
            for ri in range(min(5, len(table))):
                row = table[ri]
                found_years = {}
                for ci, cell in enumerate(row):
                    cell_str = str(cell).strip()
                    # "1990.0" or "1990" 형태
                    m = re.match(r"^(\d{4})(?:\.0)?$", cell_str)
                    if m:
                        y = int(m.group(1))
                        if 1990 <= y <= 2030:
                            found_years[y] = ci
                if len(found_years) >= 5:  # 최소 5개 연도 컬럼
                    header_row_idx = ri
                    year_cols = found_years
                    break

            if header_row_idx is None or not year_cols:
                continue

            # Country 컬럼 = header 행에서 "Country" 또는 첫 번째 컬럼
            country_col = 0
            name_col = None
            for ci, cell in enumerate(table[header_row_idx]):
                cell_str = str(cell).strip().lower()
                if "country" in cell_str:
                    country_col = ci
                    # 다음 nan 컬럼이 국가명일 수 있음
                    if ci + 1 < len(table[header_row_idx]):
                        next_cell = str(table[header_row_idx][ci + 1]).strip().lower()
                        if next_cell in ("nan", "none", ""):
                            name_col = ci + 1
                    break

            # 테이블 제목에서 유형 추출 (CO2 / GHG / LC)
            title = str(table[0][0]).strip() if table[0] else ""
            if "GHG" in title:
                ef_type = "GHG"
            elif "LC" in title or "life" in title.lower():
                ef_type = "LC"
            else:
                ef_type = "CO2"

            for row in table[header_row_idx + 1:]:
                if country_col >= len(row):
                    continue
                iso_code = str(row[country_col]).strip()
                if not iso_code or iso_code.lower() in ("nan", "none", "total"):
                    continue

                country_name = ""
                if name_col is not None and name_col < len(row):
                    country_name = str(row[name_col]).strip()
                    if country_name.lower() in ("nan", "none"):
                        country_name = ""

                display_name = country_name or iso_code

                for year, col_idx in year_cols.items():
                    if col_idx >= len(row):
                        continue
                    val_str = str(row[col_idx]).strip()
                    if val_str in ("nan", "None", "", "-", "N/A", ":"):
                        continue
                    try:
                        value = float(val_str)
                    except (ValueError, TypeError):
                        continue
                    if value <= 0:
                        continue

                    record = {
                        "item_name_original": f"{display_name} - Electricity EF {ef_type} (JRC)",
                        "item_name_standard": f"{display_name} - Electricity EF {ef_type} (JRC)",
                        "category": "electricity",
                        "scope": "Scope 2",
                        "standard_value": value,
                        "standard_unit": "tCO2/MWh",
                        "year": year,
                        "country_code": iso_code,
                        "source_org": "JRC-CoM",
                        "source_type": "International",
                        "data_reliability_score": 5,
                        "extraction_method": "jrc_com_parser",
                        "language_code": "en",
                    }
                    results.append(record)

        return results

    def extract_from_tables(self, tables: List[List], source_info: dict = None) -> List[Dict]:
        """테이블 데이터에서 배출계수 추출 (멀티 테이블 지원)"""
        # Ember 전용 파서
        if source_info and source_info.get("source_org") == "Ember":
            ember_results = self._extract_ember(tables, source_info)
            if ember_results:
                logger.info(f"[Extractor] 총 {len(ember_results)}개 항목 추출 (Ember 전용)")
                return ember_results

        # OWID CO2/Energy 전용 파서
        if source_info and source_info.get("source_org") in ("OWID-CO2", "OWID-Energy"):
            owid_results = self._extract_owid_co2(tables, source_info)
            if owid_results:
                logger.info(f"[Extractor] 총 {len(owid_results)}개 항목 추출 (OWID 전용)")
                return owid_results

        # eGRID 전용 파서 먼저 시도
        if source_info and source_info.get("source_org") == "eGRID":
            egrid_results = self._extract_egrid(tables, source_info)
            if egrid_results:
                logger.info(f"[Extractor] 총 {len(egrid_results)}개 항목 추출 (eGRID 전용)")
                return egrid_results

        # DEFRA 전용 multi-column 파서
        if source_info and source_info.get("source_org") == "DEFRA":
            defra_results = self._extract_defra(tables, source_info)
            if defra_results:
                logger.info(f"[Extractor] 총 {len(defra_results)}개 항목 추출 (DEFRA 전용)")
                return defra_results

        # CBAM 전용 파서
        if source_info and source_info.get("source_org") == "CBAM":
            cbam_results = self._extract_cbam(tables, source_info)
            if cbam_results:
                logger.info(f"[Extractor] 총 {len(cbam_results)}개 항목 추출 (CBAM 전용)")
                return cbam_results

        # UNFCCC IFI 전용 파서
        if source_info and source_info.get("source_org") == "UNFCCC-IFI":
            ifi_results = self._extract_unfccc_ifi(tables, source_info)
            if ifi_results:
                logger.info(f"[Extractor] 총 {len(ifi_results)}개 항목 추출 (UNFCCC-IFI 전용)")
                return ifi_results

        # ADEME Base Carbone 전용 파서
        if source_info and source_info.get("source_org") == "ADEME-BC":
            ademe_results = self._extract_ademe(tables, source_info)
            if ademe_results:
                logger.info(f"[Extractor] 총 {len(ademe_results)}개 항목 추출 (ADEME 전용)")
                return ademe_results

        # JRC-CoM 전용 파서
        if source_info and source_info.get("source_org") == "JRC-CoM":
            jrc_results = self._extract_jrc_com(tables, source_info)
            if jrc_results:
                logger.info(f"[Extractor] 총 {len(jrc_results)}개 항목 추출 (JRC-CoM 전용)")
                return jrc_results

        results = []

        for table in tables:
            if not table or len(table) < 2:
                continue

            # 큰 테이블은 서브 테이블로 분리 (EPA 스타일)
            sub_tables = self._split_multi_table(table)

            for sub_table in sub_tables:
                if len(sub_table) < 2:
                    continue

                extracted = self._extract_single_table(sub_table, source_info)
                results.extend(extracted)

        logger.info(f"[Extractor] 총 {len(results)}개 항목 추출")
        return results

    def _extract_defra(self, tables: List[List], source_info: dict) -> List[Dict]:
        """DEFRA 전용 파서 - multi-column, multi-fuel 시트 지원"""
        results = []
        skip_sheets = {"Introduction", "What's new", "Index", "Conversions", "Fuel properties",
                        "Haul definition", "Contents"}

        for table in tables:
            if not table or len(table) < 5:
                continue

            # 시트 이름 추출 (Row 1에 보통 시트명, Row 0은 문서 제목)
            sheet_name = ""
            for row in table[1:4]:  # Row 0 스킵 (문서 제목)
                non_empty = [str(c).strip() for c in row if str(c).strip() not in ("nan", "None", "")]
                if len(non_empty) == 1 and len(non_empty[0]) < 60:
                    sheet_name = non_empty[0]
                    break

            if any(skip in sheet_name for skip in skip_sheets):
                continue

            # Scope/Year 메타데이터 (Row 4~6에 "Scope:", "Year:" 등)
            meta_scope = ""
            meta_year = source_info.get("url_year")
            for row in table[:8]:
                row_text = " ".join(str(c).strip() for c in row if str(c).strip() not in ("nan", "None", ""))
                scope_match = self._detect_scope(row_text)
                if scope_match:
                    meta_scope = scope_match
                year_match = self.YEAR_PATTERN.search(row_text)
                if year_match and "Year:" in row_text:
                    meta_year = int(year_match.group(1))

            # 헤더 행 찾기 - DEFRA 패턴: "Activity", "Unit", "kg CO2e" 포함
            header_idx = None
            for i, row in enumerate(table[:50]):
                cells = [str(c).strip().lower() for c in row if str(c).strip() not in ("nan", "None", "")]
                if len(cells) < 3:
                    continue
                row_text = " ".join(cells)
                has_item = any(kw in row_text for kw in ["activity", "fuel", "type", "haul", "class", "category"])
                has_unit = "unit" in row_text
                has_ef = "kg co2" in row_text or "co2e" in row_text
                if has_item and has_unit and has_ef:
                    header_idx = i
                    break

            if header_idx is None:
                continue

            header = [str(c).strip() if c else "" for c in table[header_idx]]
            header_lower = [h.lower() for h in header]

            # 서브헤더 (fuel type) 행 - 헤더 위 1행에 "Diesel", "Petrol" 등
            fuel_labels = {}  # {col_idx: fuel_label}
            if header_idx > 0:
                sub_header = [str(c).strip() if c else "" for c in table[header_idx - 1]]
                for i, sh in enumerate(sub_header):
                    if sh and sh not in ("nan", "None") and len(sh) < 60:
                        fuel_labels[i] = sh

            # 컬럼 그룹 식별: 각 "kg CO2e" 컬럼을 하나의 값 그룹으로
            ef_groups = []  # [(ef_col, co2_col, ch4_col, n2o_col, fuel_label)]
            for i, h in enumerate(header_lower):
                if h == "kg co2e" or (h.startswith("kg co2e") and "of" not in h):
                    # 이 위치가 메인 ef 값
                    co2_col = i + 1 if i + 1 < len(header_lower) and "co2" in header_lower[i + 1] else None
                    ch4_col = i + 2 if i + 2 < len(header_lower) and "ch4" in header_lower[i + 2] else None
                    n2o_col = i + 3 if i + 3 < len(header_lower) and "n2o" in header_lower[i + 3] else None

                    # fuel label 결정 (서브헤더에서 정확한 컬럼 인덱스 매칭)
                    fuel = fuel_labels.get(i, "")

                    ef_groups.append({
                        "ef_col": i,
                        "co2_col": co2_col,
                        "ch4_col": ch4_col,
                        "n2o_col": n2o_col,
                        "fuel_label": fuel,
                    })

            # "Outside of scopes" 등 개별 가스 only 시트 처리
            # "kg CO2e of CO2 per unit" 같은 컬럼만 있는 경우
            if not ef_groups:
                for i, h in enumerate(header_lower):
                    if "kg co2e" in h and "of co2" in h:
                        fuel = fuel_labels.get(i, "")
                        ef_groups.append({
                            "ef_col": i,
                            "co2_col": None,
                            "ch4_col": None,
                            "n2o_col": None,
                            "fuel_label": fuel,
                        })

            if not ef_groups:
                continue

            # item/unit/year 컬럼
            item_cols = []  # 여러 열이 항목명을 구성할 수 있음
            unit_col = None
            year_col = None
            for i, h in enumerate(header_lower):
                if any(kw in h for kw in ["activity", "fuel", "type", "haul", "class",
                                           "category", "size", "market segment",
                                           "emission", "country", "waste", "material",
                                           "name", "description", "vehicle"]):
                    # ef_group 컬럼과 겹치지 않는지 확인
                    if not any(i in range(g["ef_col"], g["ef_col"] + 4) for g in ef_groups):
                        item_cols.append(i)
                if h == "unit" and unit_col is None:
                    unit_col = i
                if h == "year" and year_col is None:
                    year_col = i

            # 데이터 행 처리
            data_start = header_idx + 1
            current_items = {}  # {col_idx: last_seen_value} - DEFRA merged cell 처리

            for row in table[data_start:]:
                if len(row) < 3:
                    continue

                # 모든 ef 값이 빈 행은 스킵
                all_empty = True
                for g in ef_groups:
                    if g["ef_col"] < len(row):
                        v = str(row[g["ef_col"]]).strip()
                        if v not in ("nan", "None", "", "-"):
                            all_empty = False
                            break
                if all_empty:
                    # 카테고리/항목명 업데이트 (merged cell)
                    for col_idx in item_cols:
                        if col_idx < len(row):
                            val = str(row[col_idx]).strip()
                            if val not in ("nan", "None", "", "-"):
                                current_items[col_idx] = val
                    continue

                # 항목명 구성 (여러 열 결합)
                item_parts = []
                for col_idx in item_cols:
                    if col_idx < len(row):
                        val = str(row[col_idx]).strip()
                        if val not in ("nan", "None", "", "-"):
                            current_items[col_idx] = val
                    if col_idx in current_items and current_items[col_idx]:
                        item_parts.append(current_items[col_idx])

                if not item_parts:
                    continue

                # 단위
                row_unit_raw = ""
                if unit_col is not None and unit_col < len(row):
                    row_unit_raw = str(row[unit_col]).strip()
                    if row_unit_raw in ("nan", "None"):
                        row_unit_raw = ""

                # 년도
                year = meta_year
                if year_col is not None and year_col < len(row):
                    y_match = self.YEAR_PATTERN.search(str(row[year_col]))
                    if y_match:
                        year = int(y_match.group(1))

                # 각 ef 그룹에 대해 레코드 생성
                for g in ef_groups:
                    ef_col = g["ef_col"]
                    if ef_col >= len(row):
                        continue

                    val_str = str(row[ef_col]).strip()
                    if val_str in ("nan", "None", "", "-"):
                        continue

                    try:
                        value = float(val_str)
                    except (ValueError, TypeError):
                        continue
                    if value <= 0 or value > 100000:
                        continue
                    # 정수 2000-2030은 년도로 간주하여 스킵
                    if value == int(value) and 2000 <= int(value) <= 2030:
                        continue

                    # item name에 fuel label 추가
                    name_parts = list(item_parts)
                    if g["fuel_label"]:
                        name_parts.append(g["fuel_label"])
                    item_name = " - ".join(name_parts)

                    # 단위 결정: "kg CO2e" 헤더 + Unit 열 활동단위
                    final_unit = ""
                    if row_unit_raw:
                        activity_unit = self._normalize_activity_unit(row_unit_raw)
                        if activity_unit:
                            final_unit = f"kgCO2e/{activity_unit}"

                    # 개별 가스 값
                    co2_val = self._extract_gas_value(row, g.get("co2_col"))
                    ch4_val = self._extract_gas_value(row, g.get("ch4_col"))
                    n2o_val = self._extract_gas_value(row, g.get("n2o_col"))

                    category = self.classify_category(item_name) or ""
                    hierarchy = get_hierarchy_for_category(category)

                    record = {
                        "item_name_original": item_name,
                        "item_name_standard": self.standardize_item_name(item_name, "en"),
                        "category": category,
                        "scope": meta_scope or hierarchy.get("scope", ""),
                        "level1": hierarchy.get("level1", ""),
                        "level2": hierarchy.get("level2", ""),
                        "level3": hierarchy.get("level3", ""),
                        "standard_value": value,
                        "standard_unit": final_unit,
                        "year": year,
                        "extraction_method": "defra_multi_column",
                        "table_context": sheet_name,
                    }

                    if co2_val is not None:
                        record["co2_value"] = co2_val
                        record["co2_unit"] = final_unit
                    if ch4_val is not None:
                        record["ch4_value"] = ch4_val
                        record["ch4_unit"] = final_unit
                    if n2o_val is not None:
                        record["n2o_value"] = n2o_val
                        record["n2o_unit"] = final_unit

                    if source_info:
                        record.update(source_info)
                    results.append(record)

        return results

    def _extract_egrid(self, tables: List[List], source_info: dict) -> List[Dict]:
        """eGRID 전용 파서 - 주별/서브리전별 전력 배출계수 추출"""
        results = []

        # eGRID 시트 식별용 키워드 (설명 헤더 기반)
        # name_col/acronym_col은 동적으로 결정
        EGRID_LEVEL_MAP = {
            "state": "state",
            "subregion": "subregion",
            "nerc": "nerc_region",
            "balancing": "balancing_authority",
        }

        for table in tables:
            if not table or len(table) < 3:
                continue

            # Row 0: 설명 헤더, Row 1: 약어 코드
            header_desc = [str(c).strip() if c else "" for c in table[0]]
            header_abbr = [str(c).strip() if c else "" for c in table[1]]

            # eGRID 시트 필수조건: Row1에 emission rate 관련 약어 포함
            abbr_text = " ".join(header_abbr).upper()
            if "C2ERTA" not in abbr_text and "CO2RTA" not in abbr_text:
                # emission rate 컬럼이 없으면 스킵 (UNT, GEN, PLNT 등 대량 테이블 스킵)
                has_rate = any("emission rate" in str(d).lower() for d in header_desc)
                if not has_rate:
                    continue

            # 시트 레벨 식별 (설명 헤더 기반)
            desc_text = " ".join(header_desc[:5]).lower()
            level = None
            sheet_type = "US"  # default
            for keyword, lvl in EGRID_LEVEL_MAP.items():
                if keyword in desc_text:
                    level = lvl
                    sheet_type = keyword.upper()[:3]
                    break
            if level is None:
                # US level (no specific keyword)
                if "u.s." in desc_text or header_abbr[0] == "YEAR" and len(table) <= 5:
                    level = "national"
                    sheet_type = "US"
                else:
                    continue

            # name/acronym 컬럼 동적 결정
            name_col = None
            acronym_col = None
            year_col_idx = None
            for i, (desc, abbr) in enumerate(zip(header_desc, header_abbr)):
                dl = desc.lower()
                if "year" in dl or abbr == "YEAR":
                    year_col_idx = i
                elif "name" in dl and name_col is None:
                    name_col = i
                elif ("abbreviation" in dl or "acronym" in dl or "code" in dl) and acronym_col is None:
                    if "fips" not in dl:  # FIPS 코드 제외
                        acronym_col = i

            # state: abbreviation이 name 역할
            if name_col is None and acronym_col is not None:
                name_col = acronym_col
            if name_col is None:
                # year 다음 컬럼을 name으로
                name_col = (year_col_idx + 1) if year_col_idx is not None else 1

            sheet_config = {"name_col": name_col, "acronym_col": acronym_col, "level": level}

            # 배출률 컬럼 매핑: 설명 헤더에서 "emission rate" + "lb/MWh" 컬럼 찾기
            rate_cols = {}  # {label: col_idx}
            for i, desc in enumerate(header_desc):
                desc_lower = desc.lower()
                if "emission rate" not in desc_lower and "output emission rate" not in desc_lower:
                    continue
                if "lb/mwh" not in desc_lower and "lb/mmbtu" not in desc_lower:
                    continue

                # 단위 결정
                unit = "lbCO2e/MWh" if "lb/mwh" in desc_lower else "lbCO2e/mmBtu"

                # 가스 종류 및 유형 결정
                if "co2 equivalent" in desc_lower or "co2e" in desc_lower:
                    gas = "co2e"
                elif "co2" in desc_lower:
                    gas = "co2"
                elif "ch4" in desc_lower:
                    gas = "ch4"
                elif "n2o" in desc_lower:
                    gas = "n2o"
                else:
                    continue

                # emission type: total output / combustion / non-baseload / fuel-specific
                if "total output" in desc_lower:
                    etype = "total"
                elif "combustion" in desc_lower:
                    etype = "combustion"
                elif "non-baseload" in desc_lower or "nonbaseload" in desc_lower:
                    etype = "non_baseload"
                elif any(f in desc_lower for f in ["coal", "oil", "gas", "fossil"]):
                    continue  # 연료별 세부 스킵
                else:
                    etype = "other"

                label = f"{gas}_{etype}"
                if "lb/mwh" in desc_lower:
                    rate_cols[label] = {"idx": i, "unit": unit.replace("CO2e", gas.upper() if gas != "co2e" else "CO2e")}
                elif "lb/mmbtu" in desc_lower:
                    label_input = f"{gas}_{etype}_input"
                    rate_cols[label_input] = {"idx": i, "unit": f"lb{gas.upper() if gas != 'co2e' else 'CO2e'}/mmBtu"}

            if not rate_cols:
                continue

            year_col = year_col_idx  # 위에서 동적으로 결정됨
            name_col = sheet_config["name_col"]
            acronym_col = sheet_config["acronym_col"]

            # 데이터 행 (Row 2~)
            for row in table[2:]:
                if len(row) <= name_col:
                    continue

                # 지역명
                region_name = str(row[name_col]).strip() if name_col < len(row) else ""
                region_code = str(row[acronym_col]).strip() if acronym_col is not None and acronym_col < len(row) else ""
                if not region_name or region_name in ("nan", "None", ""):
                    continue

                year = None
                if year_col is not None and year_col < len(row):
                    try:
                        year = int(float(str(row[year_col])))
                    except (ValueError, TypeError):
                        pass

                # 핵심 배출률 추출: CO2e total output (lb/MWh) → Scope 2 전력 배출계수
                for label, col_info in rate_cols.items():
                    col_idx = col_info["idx"]
                    col_unit = col_info["unit"]
                    if col_idx >= len(row):
                        continue

                    val_str = str(row[col_idx]).strip()
                    if val_str in ("nan", "None", "", "-"):
                        continue
                    try:
                        value = float(val_str)
                    except (ValueError, TypeError):
                        continue
                    if value <= 0 or value > 100000:
                        continue

                    # item name 구성
                    item_parts = [region_name]
                    if region_code and region_code != region_name:
                        item_parts.append(f"({region_code})")

                    # label에서 type 추출
                    parts = label.split("_", 1)
                    gas_name = parts[0]
                    rate_type = parts[1] if len(parts) > 1 else "total"

                    # Scope 결정
                    scope = "Scope 2"
                    if "combustion" in rate_type:
                        scope = "Scope 1"
                    if "input" in rate_type:
                        scope = "Scope 1"

                    item_name = f"{' '.join(item_parts)} - {gas_name.upper()} {rate_type.replace('_', ' ')}"

                    record = {
                        "item_name_original": item_name,
                        "item_name_standard": f"electricity_{sheet_config['level']}_{region_code or region_name}".lower().replace(" ", "_"),
                        "category": "electricity",
                        "scope": scope,
                        "level1": "Energy",
                        "level2": "electricity",
                        "level3": sheet_config["level"],
                        "standard_value": value,
                        "standard_unit": col_unit,
                        "year": year,
                        "extraction_method": "egrid_direct",
                        "table_context": f"eGRID {sheet_type} - {rate_type}",
                    }

                    # 개별 가스 분리
                    if gas_name == "co2":
                        record["co2_value"] = value
                        record["co2_unit"] = col_unit
                    elif gas_name == "ch4":
                        record["ch4_value"] = value
                        record["ch4_unit"] = col_unit
                    elif gas_name == "n2o":
                        record["n2o_value"] = value
                        record["n2o_unit"] = col_unit

                    if source_info:
                        record.update(source_info)
                    results.append(record)

        return results

    def _split_multi_table(self, table: List[List]) -> List[List]:
        """하나의 큰 테이블을 'Table N' 경계에서 서브 테이블로 분리"""
        boundaries = []
        for i, row in enumerate(table):
            non_empty = [str(c).strip() for c in row if str(c).strip() not in ("nan", "None", "")]
            if not non_empty:
                continue
            first_text = " ".join(non_empty)
            if self.TABLE_BOUNDARY.match(first_text.strip()) and len(first_text) < 100:
                boundaries.append(i)

        if not boundaries:
            return [table]  # 경계가 없으면 전체를 하나로

        # 서브 테이블 분리
        sub_tables = []
        for idx, start in enumerate(boundaries):
            end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(table)
            sub = table[start:end]
            if len(sub) >= 3:  # 최소 3행 (제목 + 헤더 + 데이터)
                sub_tables.append(sub)

        # 경계 전 데이터도 포함 (첫 경계 앞에 헤더가 있을 수 있음)
        if boundaries[0] > 5:
            sub_tables.insert(0, table[:boundaries[0]])

        return sub_tables if sub_tables else [table]

    def _detect_gwp_version(self, text: str) -> Optional[str]:
        """텍스트에서 GWP 버전(AR4/AR5/AR6/SAR/TAR) 감지"""
        for pattern, version in self.GWP_PATTERNS:
            if pattern.search(text):
                return version
        return None

    def _detect_scope(self, text: str) -> Optional[str]:
        """텍스트에서 Scope(1/2/3) 감지"""
        for pattern, scope in self.SCOPE_PATTERNS:
            if pattern.search(text):
                return scope
        return None

    def _get_table_surrounding_text(self, table: List[List], header_idx: int) -> str:
        """테이블 헤더 위아래 텍스트를 결합하여 컨텍스트 반환"""
        parts = []
        # 헤더 위 5행
        for i in range(max(0, header_idx - 5), header_idx):
            row_text = " ".join(
                str(c).strip() for c in table[i]
                if str(c).strip() not in ("nan", "None", "")
            )
            if row_text:
                parts.append(row_text)
        # 헤더 행 자체
        if header_idx < len(table):
            header_text = " ".join(
                str(c).strip() for c in table[header_idx]
                if str(c).strip() not in ("nan", "None", "")
            )
            if header_text:
                parts.append(header_text)
        return " ".join(parts)

    def _extract_single_table(self, table: List[List], source_info: dict = None) -> List[Dict]:
        """단일 테이블에서 배출계수 추출"""
        results = []

        # 실제 헤더 행 찾기
        header_idx, header = self._find_header_row(table)
        if header_idx is None:
            return self._extract_from_text_table(table, source_info)

        header_lower = [self._normalize_subscripts(str(h).lower().strip()) for h in header]

        # 배출계수 관련 컬럼 식별
        ef_col = self._find_column(header_lower, self.HEADER_KEYWORDS["ef"])
        unit_col = self._find_column(header_lower, self.HEADER_KEYWORDS["unit"])
        item_col = self._find_column(header_lower, self.HEADER_KEYWORDS["item"])
        year_col = self._find_column(header_lower, self.HEADER_KEYWORDS["year"])

        # "Fuel" 전용 컬럼 탐색 (DEFRA: Activity=카테고리, Fuel=항목명)
        fuel_col = None
        for i, h in enumerate(header_lower):
            if i != item_col and any(kw in h for kw in ["fuel", "연료", "type"]):
                fuel_col = i
                break

        # 개별 가스 컬럼 식별 — ef_col과 중복되지 않는 것만
        co2_col = self._find_column_exclude(header_lower, self.HEADER_KEYWORDS["co2"], exclude={ef_col})
        ch4_col = self._find_column_exclude(header_lower, self.HEADER_KEYWORDS["ch4"], exclude={ef_col})
        n2o_col = self._find_column_exclude(header_lower, self.HEADER_KEYWORDS["n2o"], exclude={ef_col})
        has_individual_gas_cols = any(c is not None for c in [co2_col, ch4_col, n2o_col])

        # 서브 헤더 단위 행 검사 (EPA 스타일)
        unit_from_subheader = ""
        ef_unit_from_subheader = ""
        gas_units_from_subheader = {}  # {gas: unit_string}
        data_start = header_idx + 1

        if header_idx + 1 < len(table):
            sub_row = table[header_idx + 1]
            sub_cells = [str(c).strip() for c in sub_row]
            sub_text = " ".join(c for c in sub_cells if c not in ("nan", "None", ""))

            # 서브헤더 단위 행: 단위 키워드가 있고, 숫자 데이터가 없어야 함
            # (데이터 행이 "0.177 kWh" 등으로 잘못 인식되는 것 방지)
            has_unit_keywords = any(u in sub_text.lower() for u in [
                "kg co2", "g co2", "g ch4", "g n2o", "mmbtu",
                "lb co2", "short ton", "gallon", "barrel", "scf"
            ])
            # 숫자가 포함된 셀이 적으면 서브헤더 (데이터 행은 숫자가 많음)
            numeric_cells = sum(1 for c in sub_cells if c not in ("nan", "None", "") and
                               re.match(r"^-?\d+\.?\d*$", c))
            is_unit_row = has_unit_keywords and numeric_cells <= 1
            if is_unit_row:
                unit_from_subheader = sub_text
                # ef_col 위치의 단위 추출
                if ef_col is not None and ef_col < len(sub_cells):
                    ef_unit_from_subheader = sub_cells[ef_col].strip()
                    if ef_unit_from_subheader in ("nan", "None"):
                        ef_unit_from_subheader = ""
                # 개별 가스 컬럼 단위 추출
                for gas_name, gas_col in [("co2", co2_col), ("ch4", ch4_col), ("n2o", n2o_col)]:
                    if gas_col is not None and gas_col < len(sub_cells):
                        gas_unit = sub_cells[gas_col].strip()
                        if gas_unit not in ("nan", "None", ""):
                            gas_units_from_subheader[gas_name] = gas_unit
                data_start = header_idx + 2

        if ef_col is None and not has_individual_gas_cols:
            return self._extract_from_text_table(table, source_info)

        # EF 열 헤더에서 단위 힌트 추출 (DEFRA 스타일: 헤더="kg CO2e", Unit열="tonnes")
        ef_header_unit_hint = ""
        if ef_col is not None and ef_col < len(header):
            h = self._normalize_subscripts(str(header[ef_col]).strip())
            # 헤더 안 괄호 단위 추출 (EPA: "CO2 Factor\n(kg / unit)")
            paren_match = re.search(r"\(([^)]+)\)", h)
            if paren_match:
                paren_unit = self._detect_unit_extended(paren_match.group(1))
                if paren_unit:
                    ef_header_unit_hint = "__direct__"  # 직접 단위 감지됨
                    unit = paren_unit  # 기본 단위로 설정
            if not ef_header_unit_hint:
                if re.search(r"kg\s*CO2e?", h, re.IGNORECASE):
                    ef_header_unit_hint = "kgCO2e"
                elif re.search(r"tCO2e?", h, re.IGNORECASE):
                    ef_header_unit_hint = "tCO2e"

        # 단위 결정
        unit = ""
        if ef_unit_from_subheader:
            unit = self._detect_unit_extended(ef_unit_from_subheader)
        if not unit and unit_from_subheader:
            unit = self._detect_unit_extended(unit_from_subheader)

        # 테이블 제목에서 컨텍스트 추출
        table_context = ""
        for i in range(max(0, header_idx - 3), header_idx):
            row_text = " ".join(
                str(c).strip() for c in table[i]
                if str(c).strip() not in ("nan", "None", "")
            )
            if row_text and len(row_text) < 100:
                table_context = row_text
                break

        # 테이블 주변 텍스트에서 Scope, GWP 감지
        surrounding_text = self._get_table_surrounding_text(table, header_idx)
        table_scope = self._detect_scope(surrounding_text)
        table_gwp = self._detect_gwp_version(surrounding_text)

        # 데이터 행 처리
        current_category = ""
        for row in table[data_start:]:
            # ef_col 또는 개별 가스 컬럼 중 하나라도 접근 가능해야 함
            min_required_col = ef_col if ef_col is not None else 0
            if has_individual_gas_cols:
                gas_cols_present = [c for c in [co2_col, ch4_col, n2o_col] if c is not None]
                min_required_col = max(min_required_col or 0, max(gas_cols_present))
            if len(row) <= (min_required_col or 0):
                continue

            try:
                # 메인 ef 값 추출
                value = None
                value_str = ""
                if ef_col is not None and ef_col < len(row):
                    value_str = str(row[ef_col]).strip()
                    if value_str in ("nan", "None", "", "-"):
                        # 카테고리/섹션 행일 수 있음 (개별 가스도 없으면)
                        if not has_individual_gas_cols:
                            if item_col is not None and item_col < len(row):
                                candidate = str(row[item_col]).strip()
                                if candidate not in ("nan", "None", "", "-"):
                                    if self.TABLE_BOUNDARY.match(candidate):
                                        break
                                    current_category = candidate
                            continue
                    else:
                        value_match = self.NUMBER_PATTERN.search(value_str)
                        if value_match:
                            v = float(value_match.group(1))
                            # 연도 필터: 정수값만 필터 (2016.7 등 소수점 EF값은 통과)
                            if 0 < v <= 100000 and not (v == int(v) and 2000 <= int(v) <= 2030):
                                value = v

                # 개별 가스 값 추출
                co2_value = self._extract_gas_value(row, co2_col)
                ch4_value = self._extract_gas_value(row, ch4_col)
                n2o_value = self._extract_gas_value(row, n2o_col)

                # ef 값도 없고 개별 가스 값도 모두 없으면 건너뜀
                if value is None and co2_value is None and ch4_value is None and n2o_value is None:
                    # 카테고리 행인지 확인
                    if item_col is not None and item_col < len(row):
                        candidate = str(row[item_col]).strip()
                        if candidate not in ("nan", "None", "", "-"):
                            if self.TABLE_BOUNDARY.match(candidate):
                                break
                            current_category = candidate
                    continue

                item = ""
                # fuel_col이 있으면 실제 항목명으로 우선 사용
                if fuel_col is not None and fuel_col < len(row):
                    fuel_name = str(row[fuel_col]).strip()
                    if fuel_name not in ("nan", "None", ""):
                        item = fuel_name
                if not item or item in ("nan", "None", ""):
                    if item_col is not None and item_col < len(row):
                        item = str(row[item_col]).strip()
                if item in ("nan", "None", ""):
                    item = current_category

                if not item or item in ("nan", "None", ""):
                    continue

                # 행별 단위 (있으면)
                row_unit = unit
                if unit_col is not None and unit_col < len(row):
                    cell_unit = str(row[unit_col]).strip()
                    if cell_unit not in ("nan", "None", ""):
                        detected = self._detect_unit_extended(cell_unit)
                        if detected:
                            row_unit = detected
                        elif ef_header_unit_hint:
                            # DEFRA 스타일: 헤더 "kg CO2e" + 셀 "tonnes" → "kgCO2e/ton"
                            activity_unit = self._normalize_activity_unit(cell_unit)
                            if activity_unit:
                                row_unit = f"{ef_header_unit_hint}/{activity_unit}"

                year = None
                if year_col is not None and year_col < len(row):
                    year_match = self.YEAR_PATTERN.search(str(row[year_col]))
                    year = int(year_match.group(1)) if year_match else None
                # URL/파일명에서 추출된 년도를 fallback으로 사용
                if year is None and source_info and source_info.get("url_year"):
                    year = source_info["url_year"]

                # 행 텍스트에서 Scope/GWP 추가 감지
                row_text = " ".join(str(c) for c in row)
                row_scope = self._detect_scope(row_text) or table_scope
                row_gwp = self._detect_gwp_version(row_text) or table_gwp

                # 카테고리 분류 및 계층 정보
                category = self.classify_category(item) or current_category or ""
                # 카테고리 미분류 시 단위 기반 추론 (JP/MOE 전력회사명 등)
                if not category or category == "unknown":
                    category = self._infer_category_from_unit(row_unit) or category
                hierarchy = get_hierarchy_for_category(category)

                # 단위가 없으면 source_info의 기본 단위 사용
                final_unit = row_unit
                if not final_unit and source_info and source_info.get("default_unit"):
                    final_unit = source_info["default_unit"]

                record = {
                    "item_name_original": item,
                    "item_name_standard": self.standardize_item_name(item, "en"),
                    "category": category,
                    "scope": row_scope or hierarchy.get("scope", ""),
                    "level1": hierarchy.get("level1", ""),
                    "level2": hierarchy.get("level2", ""),
                    "level3": hierarchy.get("level3", ""),
                    "standard_value": value,
                    "standard_unit": final_unit,
                    "year": year,
                    "extraction_method": "table_column_smart",
                    "table_context": table_context,
                }

                # 개별 가스 값 추가
                if co2_value is not None:
                    record["co2_value"] = co2_value
                    record["co2_unit"] = gas_units_from_subheader.get("co2", row_unit)
                if ch4_value is not None:
                    record["ch4_value"] = ch4_value
                    record["ch4_unit"] = gas_units_from_subheader.get("ch4", row_unit)
                if n2o_value is not None:
                    record["n2o_value"] = n2o_value
                    record["n2o_unit"] = gas_units_from_subheader.get("n2o", row_unit)

                # GWP 버전
                if row_gwp:
                    record["gwp_version"] = row_gwp

                if source_info:
                    record.update(source_info)
                results.append(record)

            except (ValueError, IndexError) as e:
                logger.debug(f"[Extractor] 행 파싱 스킵: {e}")

        return results

    def _extract_gas_value(self, row: List, col: Optional[int]) -> Optional[float]:
        """행에서 특정 가스 컬럼의 수치 값을 추출"""
        if col is None or col >= len(row):
            return None
        val_str = str(row[col]).strip()
        if val_str in ("nan", "None", "", "-"):
            return None
        match = self.NUMBER_PATTERN.search(val_str)
        if not match:
            return None
        v = float(match.group(1))
        # 연도 필터: 정수값만 필터 (2016.7 등 소수점 EF값은 통과)
        if v <= 0 or v > 100000 or (v == int(v) and 2000 <= int(v) <= 2030):
            return None
        return v

    def _find_header_row(self, table: List[List]) -> tuple:
        """테이블에서 실제 헤더 행 찾기 (빈 행/제목 행/긴 문장 건너뛰기)"""
        best_match = (None, None, 0)  # (index, row, score)

        for i, row in enumerate(table[:50]):
            # nan이 아닌 셀만 추출
            non_empty = [str(c).strip() for c in row if str(c).strip() not in ("nan", "None", "")]
            if len(non_empty) < 2:
                continue

            # 긴 셀이 있으면 헤더 아님 (문장/설명 행 필터링)
            # eGRID 등 기술적 헤더를 위해 100자까지 허용 (기존 60자)
            max_cell_len = max(len(c) for c in non_empty) if non_empty else 0
            if max_cell_len > 100:
                continue

            row_text = self._normalize_subscripts(" ".join(c.lower() for c in non_empty))

            # 헤더 키워드 매칭 (ef, unit, item, year + co2, ch4, n2o)
            match_count = 0
            matched_categories = []
            for cat_name, kw_list in self.HEADER_KEYWORDS.items():
                if any(kw in row_text for kw in kw_list):
                    match_count += 1
                    matched_categories.append(cat_name)

            # ef 또는 co2 카테고리 포함 시 가중치 추가 (실제 값 컬럼이 있을 가능성 높음)
            effective_score = match_count
            if "ef" in matched_categories or "co2" in matched_categories:
                effective_score += 0.5

            if match_count >= 2 and effective_score > best_match[2]:
                best_match = (i, row, effective_score)

        if best_match[0] is not None:
            return best_match[0], best_match[1]
        return None, None

    def extract_from_text(self, text: str, source_info: dict = None) -> List[Dict]:
        """텍스트에서 배출계수 패턴 추출"""
        results = []

        # 텍스트 전체에서 GWP 버전 감지
        text_gwp = self._detect_gwp_version(text)
        text_scope = self._detect_scope(text)

        sentences = re.split(r"[.\n]", text)

        for sentence in sentences:
            has_ef_keyword = any(kw.lower() in sentence.lower() for kw in PDF_KEYWORDS)
            if not has_ef_keyword:
                continue

            unit = self._detect_unit_extended(sentence)
            if not unit:
                continue

            numbers = self.NUMBER_PATTERN.findall(sentence)
            year_match = self.YEAR_PATTERN.search(sentence)
            year = int(year_match.group(1)) if year_match else None

            # 문장별 Scope/GWP 감지
            sent_scope = self._detect_scope(sentence) or text_scope
            sent_gwp = self._detect_gwp_version(sentence) or text_gwp

            for num_str in numbers:
                try:
                    value = float(num_str)
                    if 2000 <= value <= 2030:
                        continue
                    if 0 < value < 10000:
                        record = {
                            "item_name_original": sentence.strip()[:200],
                            "standard_value": value,
                            "standard_unit": unit,
                            "year": year,
                            "extraction_method": "text_pattern",
                        }
                        if sent_scope:
                            record["scope"] = sent_scope
                        if sent_gwp:
                            record["gwp_version"] = sent_gwp
                        if source_info:
                            record.update(source_info)
                        results.append(record)
                except ValueError:
                    continue

        return results

    def classify_category(self, item_name: str) -> Optional[str]:
        """항목명을 택소노미 카테고리로 분류, 계층 정보 포함"""
        item_lower = item_name.lower()

        # TAXONOMY에서 긴 카테고리명부터 매칭 (bus_transport > bus 방지)
        all_tax_children = []
        for parent, children in TAXONOMY.items():
            for child in children:
                all_tax_children.append(child)
        all_tax_children.sort(key=len, reverse=True)

        for child in all_tax_children:
            if child.replace("_", " ") in item_lower or child in item_lower:
                return child

        keyword_map = {
            # Energy
            "electricity": [
                "전력", "전기", "grid", "power", "電力", "electricité", "egrid",
                "điện", "listrik", "ไฟฟ้า", "electricidad", "eletricidade",
                "전력사용", "grid electricity", "grid power",
            ],
            "natural_gas": [
                "천연가스", "lng", "natural gas", "天然ガス", "gaz naturel",
                "khí tự nhiên", "gas alam", "ก๊าซธรรมชาติ", "gas natural",
                "gás natural", "도시가스", "city gas",
            ],
            "coal": [
                "석탄", "coal", "anthracite", "bituminous", "lignite", "charbon",
                "than đá", "batu bara", "ถ่านหิน", "carbón", "carvão",
                "무연탄", "유연탄", "아역청탄",
            ],
            "diesel": [
                "디젤", "경유", "diesel", "distillate", "gasoil",
                "dầu diesel", "solar", "ดีเซล", "diésel", "gasóleo",
            ],
            "gasoline": [
                "가솔린", "휘발유", "gasoline", "petrol", "motor gasoline", "essence",
                "xăng", "bensin", "น้ำมันเบนซิน", "gasolina",
            ],
            "lpg": [
                "lpg", "프로판", "부탄", "propane", "butane",
                "khí hóa lỏng", "elpiji", "แอลพีจี", "glp",
            ],
            "fuel_oil": [
                "fuel oil", "residual", "중유", "kerosene", "jet fuel", "aviation",
                "dầu nhiên liệu", "minyak bahan bakar", "น้ำมันเตา",
                "aceite combustible", "óleo combustível",
                "등유", "항공유",
            ],
            "renewable_energy": [
                "재생에너지", "renewable", "solar power", "wind power", "太陽光",
                "năng lượng tái tạo", "energi terbarukan", "พลังงานหมุนเวียน",
                "energía renovable", "energia renovável",
                "태양광", "풍력", "수력",
            ],
            # Transportation
            "road_transport": [
                "도로교통", "자동차", "차량", "vehicle", "car", "truck", "bus",
                "xe hơi", "kendaraan", "ยานพาหนะ", "vehículo", "veículo",
                "승용차", "트럭", "버스",
            ],
            "aviation": [
                "항공", "비행기", "flight", "aircraft", "airline",
                "hàng không", "penerbangan", "การบิน", "aviación", "aviação",
            ],
            "marine_transport": [
                "해운", "선박", "ship", "marine", "maritime", "vessel",
                "hàng hải", "pelayaran", "การเดินเรือ", "transporte marítimo",
            ],
            "rail_transport": [
                "철도", "기차", "rail", "train", "railway",
                "đường sắt", "kereta api", "รถไฟ", "ferrocarril", "ferrovia",
            ],
            # Industry
            "cement": [
                "시멘트", "cement", "セメント", "ciment",
                "xi măng", "semen", "ซีเมนต์", "cemento", "cimento",
            ],
            "steel": [
                "철강", "steel", "鉄鋼", "acier",
                "thép", "baja", "เหล็กกล้า", "acero", "aço",
            ],
            "chemical": [
                "화학", "chemical", "化学", "chimique",
                "hóa chất", "kimia", "เคมี", "químico",
            ],
            "aluminum": [
                "알루미늄", "aluminum", "aluminium", "アルミニウム",
                "nhôm", "aluminium", "อลูมิเนียม", "aluminio",
            ],
            "fertilizer": [
                "비료", "fertilizer", "肥料",
                "phân bón", "pupuk", "ปุ๋ย", "fertilizante",
            ],
            # Waste
            "landfill": [
                "매립", "landfill", "埋立",
                "chôn lấp", "tempat pembuangan", "หลุมฝังกลบ", "vertedero", "aterro",
            ],
            "wastewater": [
                "폐수", "하수", "wastewater", "sewage",
                "nước thải", "air limbah", "น้ำเสีย", "aguas residuales", "águas residuais",
            ],
            "recycling": [
                "재활용", "recycling", "リサイクル",
                "tái chế", "daur ulang", "การรีไซเคิล", "reciclaje", "reciclagem",
            ],
            # Agriculture
            "livestock": [
                "축산", "가축", "livestock", "cattle", "畜産",
                "chăn nuôi", "peternakan", "ปศุสัตว์", "ganadería", "pecuária",
                "소", "돼지", "가금류",
            ],
            "rice": [
                "벼", "쌀", "rice", "稲作",
                "lúa", "padi", "ข้าว", "arroz",
            ],
            "fertilizer_use": [
                "비료사용", "fertilizer use", "fertilizer application",
                "sử dụng phân bón", "penggunaan pupuk",
            ],
            # Scope 3 / Indirect categories
            "purchased_goods": [
                "구매품", "purchased goods", "purchased services",
                "원자재", "raw materials", "구매 제품", "구매 서비스",
                "hàng hóa mua", "barang yang dibeli",
            ],
            "business_travel": [
                "출장", "business travel", "업무출장",
                "công tác", "perjalanan bisnis", "การเดินทางเพื่อธุรกิจ",
                "viaje de negocios", "viagem de negócios",
            ],
            "commuting": [
                "통근", "commuting", "employee commuting", "통근교통",
                "đi làm", "komuter", "การเดินทางไปทำงาน",
                "desplazamiento", "deslocamento",
            ],
            "logistics": [
                "물류", "logistics", "freight", "화물운송", "운송",
                "hậu cần", "logistik", "โลจิสติกส์", "logística",
                "upstream transport", "downstream transport",
            ],
            "events": [
                "이벤트", "행사", "event", "conference", "meeting",
                "sự kiện", "acara", "กิจกรรม", "evento",
            ],
            "capital_goods": [
                "자본재", "capital goods", "설비투자",
                "hàng vốn", "barang modal",
            ],
            "waste_generated": [
                "폐기물", "waste generated in operations", "사업장 폐기물",
                "chất thải", "limbah",
            ],
            "use_of_sold_products": [
                "판매제품 사용", "use of sold products",
            ],
            "end_of_life": [
                "폐기처리", "end-of-life treatment", "end of life",
            ],
            "leased_assets": [
                "임대자산", "leased assets",
            ],
            "franchises": [
                "프랜차이즈", "franchise",
            ],
            "investments": [
                "투자", "investments", "investment",
            ],
        }

        # 긴 키워드부터 매칭 (business travel이 bus보다 먼저 매칭되도록)
        matches = []
        for category, keywords in keyword_map.items():
            for kw in keywords:
                if kw in item_lower:
                    matches.append((len(kw), category))
        if matches:
            matches.sort(reverse=True)  # 가장 긴 매칭 우선
            return matches[0][1]

        return None

    def _normalize_activity_unit(self, raw_unit: str) -> Optional[str]:
        """활동 단위를 표준 약어로 변환 (DEFRA 'Unit' 열 대응)"""
        u = raw_unit.lower().strip()
        mapping = {
            "tonnes": "ton",
            "tonne": "ton",
            "metric ton": "ton",
            "metric tonnes": "ton",
            "t": "ton",
            "litres": "L",
            "litre": "L",
            "liter": "L",
            "liters": "L",
            "kwh (net cv)": "kWh",
            "kwh (gross cv)": "kWh",
            "kwh": "kWh",
            "mwh": "MWh",
            "cubic metres": "m3",
            "cubic meters": "m3",
            "m3": "m3",
            "m³": "m3",
            "kg": "kg",
            "gj": "GJ",
            "mj": "MJ",
            "tj": "TJ",
            "gallons": "gallon",
            "gallon": "gallon",
            "passenger km": "pkm",
            "passenger mile": "passenger-mile",
            "tonne km": "tkm",
            "tonne.km": "tkm",
            "ton km": "tkm",
            "ton.km": "tkm",
            "km": "km",
            "miles": "mile",
            "mile": "mile",
            "passenger.km": "pkm",
            "passenger-km": "pkm",
            "room per night": "night",
            "room night": "night",
            "night": "night",
            "per night": "night",
            "scf": "scf",
            "barrel": "barrel",
            "bbl": "barrel",
            "short ton": "short_ton",
            "short tons": "short_ton",
            "vehicle-mile": "vehicle-mile",
            "vehicle mile": "vehicle-mile",
            "vehicle miles": "vehicle-mile",
            "passenger-mile": "passenger-mile",
            "passenger miles": "passenger-mile",
            "number": "unit",
            "each": "unit",
            "unit": "unit",
            "fte": "person",
            "person": "person",
            "employee": "person",
            "scope 3 category": "unit",
        }
        return mapping.get(u)

    def _infer_category_from_unit(self, unit: str) -> Optional[str]:
        """단위에서 카테고리 추론 (회사명 등 비표준 항목명 대응)"""
        if not unit:
            return None
        u = unit.lower()
        if "kwh" in u or "mwh" in u:
            return "electricity"
        if "l" == u.split("/")[-1] or "/l" in u:
            return "diesel"  # 액체연료 기본
        if "gj" in u or "mj" in u or "tj" in u or "mmbtu" in u:
            return "natural_gas"  # 에너지 단위 기본
        if "tkm" in u:
            return "logistics"
        if "pkm" in u or "passenger" in u:
            return "road_transport"
        return None

    def standardize_item_name(self, original: str, language_code: str = "en") -> str:
        """항목명을 영문 표준명으로 변환"""
        translations = {
            # 한국어
            "전력": "electricity",
            "전기": "electricity",
            "천연가스": "natural_gas",
            "도시가스": "natural_gas",
            "석탄": "coal",
            "무연탄": "anthracite_coal",
            "유연탄": "bituminous_coal",
            "아역청탄": "sub_bituminous_coal",
            "갈탄": "lignite_coal",
            "경유": "diesel",
            "휘발유": "gasoline",
            "시멘트": "cement",
            "철강": "steel",
            "중유": "fuel_oil",
            "등유": "kerosene",
            "항공유": "jet_fuel",
            "프로판": "lpg_propane",
            "부탄": "lpg_butane",
            "통근": "commuting",
            "출장": "business_travel",
            "물류": "logistics",
            "구매품": "purchased_goods",
            "폐기물": "waste_generated",
            "재활용": "recycling",
            "매립": "landfill",
            "폐수": "wastewater",
            "축산": "livestock",
            "비료": "fertilizer",
            "태양광": "solar_power",
            "풍력": "wind_power",
            "알루미늄": "aluminum",
            "화학": "chemical",
            # 일본어
            "電力": "electricity",
            "天然ガス": "natural_gas",
            "石炭": "coal",
            "軽油": "diesel",
            "ガソリン": "gasoline",
            "セメント": "cement",
            "鉄鋼": "steel",
            "灯油": "kerosene",
            "重油": "fuel_oil",
            "プロパン": "lpg_propane",
            "アルミニウム": "aluminum",
            "肥料": "fertilizer",
            "畜産": "livestock",
            "廃棄物": "waste_generated",
            "リサイクル": "recycling",
            # 베트남어
            "điện": "electricity",
            "khí tự nhiên": "natural_gas",
            "than đá": "coal",
            "dầu diesel": "diesel",
            "xăng": "gasoline",
            "xi măng": "cement",
            "thép": "steel",
            "nhôm": "aluminum",
            "phân bón": "fertilizer",
            "chăn nuôi": "livestock",
            "lúa": "rice",
            "nước thải": "wastewater",
            "chất thải": "waste_generated",
            "tái chế": "recycling",
            "hàng không": "aviation",
            "đường sắt": "rail_transport",
            "hàng hải": "marine_transport",
            "công tác": "business_travel",
            "đi làm": "commuting",
            "hậu cần": "logistics",
            # 인도네시아어
            "listrik": "electricity",
            "gas alam": "natural_gas",
            "batu bara": "coal",
            "solar": "diesel",
            "bensin": "gasoline",
            "semen": "cement",
            "baja": "steel",
            "aluminium": "aluminum",
            "pupuk": "fertilizer",
            "peternakan": "livestock",
            "padi": "rice",
            "air limbah": "wastewater",
            "limbah": "waste_generated",
            "daur ulang": "recycling",
            "penerbangan": "aviation",
            "kereta api": "rail_transport",
            "pelayaran": "marine_transport",
            "perjalanan bisnis": "business_travel",
            "komuter": "commuting",
            "logistik": "logistics",
            # 태국어
            "ไฟฟ้า": "electricity",
            "ก๊าซธรรมชาติ": "natural_gas",
            "ถ่านหิน": "coal",
            "ดีเซล": "diesel",
            "น้ำมันเบนซิน": "gasoline",
            "ซีเมนต์": "cement",
            "เหล็กกล้า": "steel",
            "อลูมิเนียม": "aluminum",
            "ปุ๋ย": "fertilizer",
            "ปศุสัตว์": "livestock",
            "ข้าว": "rice",
            "น้ำเสีย": "wastewater",
            "การรีไซเคิล": "recycling",
            "การบิน": "aviation",
            "รถไฟ": "rail_transport",
            "โลจิสติกส์": "logistics",
            "แอลพีจี": "lpg",
            # 스페인어
            "electricidad": "electricity",
            "gas natural": "natural_gas",
            "carbón": "coal",
            "diésel": "diesel",
            "gasolina": "gasoline",
            "cemento": "cement",
            "acero": "steel",
            "aluminio": "aluminum",
            "fertilizante": "fertilizer",
            "ganadería": "livestock",
            "arroz": "rice",
            "aguas residuales": "wastewater",
            "reciclaje": "recycling",
            "aviación": "aviation",
            "ferrocarril": "rail_transport",
            "transporte marítimo": "marine_transport",
            "viaje de negocios": "business_travel",
            "desplazamiento": "commuting",
            "logística": "logistics",
            # 포르투갈어
            "eletricidade": "electricity",
            "gás natural": "natural_gas",
            "carvão": "coal",
            "gasóleo": "diesel",
            "cimento": "cement",
            "aço": "steel",
            "águas residuais": "wastewater",
            "reciclagem": "recycling",
            "aviação": "aviation",
            "ferrovia": "rail_transport",
            "viagem de negócios": "business_travel",
            "deslocamento": "commuting",
            # 영문 확장
            "grid electricity": "electricity",
            "grid power": "electricity",
            "natural gas": "natural_gas",
            "anthracite coal": "anthracite_coal",
            "bituminous coal": "bituminous_coal",
            "sub-bituminous coal": "sub_bituminous_coal",
            "lignite coal": "lignite_coal",
            "distillate fuel oil": "diesel",
            "residual fuel oil": "fuel_oil",
            "motor gasoline": "gasoline",
            "jet fuel": "jet_fuel",
            "kerosene": "kerosene",
            "propane": "lpg_propane",
            "business travel": "business_travel",
            "employee commuting": "commuting",
            "purchased goods": "purchased_goods",
            "purchased services": "purchased_goods",
            "capital goods": "capital_goods",
            "use of sold products": "use_of_sold_products",
            "end-of-life treatment": "end_of_life",
            "leased assets": "leased_assets",
            "upstream transport": "logistics",
            "downstream transport": "logistics",
        }

        original_lower = original.lower().strip()
        # 긴 키부터 매칭해야 "natural gas"가 "gas" 보다 먼저 매칭됨
        for key in sorted(translations.keys(), key=len, reverse=True):
            if key.lower() in original_lower:
                return translations[key]

        return original_lower.replace(" ", "_")

    @staticmethod
    def _normalize_subscripts(text: str) -> str:
        """Unicode 아래첨자/위첨자를 일반 숫자로 변환 (CO₂→CO2, CH₄→CH4)"""
        sub_map = str.maketrans("₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹", "01234567890123456789")
        return text.translate(sub_map)

    def _find_column(self, header: List[str], keywords: List[str]) -> Optional[int]:
        """헤더에서 키워드 매칭 컬럼 인덱스 찾기"""
        for i, h in enumerate(header):
            for kw in keywords:
                if kw in h:
                    return i
        return None

    def _find_column_exclude(self, header: List[str], keywords: List[str], exclude: set) -> Optional[int]:
        """헤더에서 키워드 매칭 컬럼 찾기 (exclude 인덱스 제외)"""
        for i, h in enumerate(header):
            if i in exclude:
                continue
            for kw in keywords:
                if kw in h:
                    return i
        return None

    def _detect_unit(self, text: str) -> str:
        """텍스트에서 단위 감지 (슬래시 구분 패턴)"""
        for pattern in self.UNIT_PATTERNS:
            match = pattern.search(text)
            if match:
                return self._normalize_unit(match.group(1))
        return ""

    def _detect_unit_extended(self, text: str) -> str:
        """확장 단위 감지 (슬래시 + EPA 'per' 스타일 포함)"""
        # 먼저 슬래시 패턴 시도
        unit = self._detect_unit(text)
        if unit:
            return unit

        # 일본어 패턴
        for pattern in self.JP_UNIT_PATTERNS:
            match = pattern.search(text)
            if match:
                return self._normalize_unit_extended(match.group(1))

        # EPA 'per' 스타일 패턴
        for pattern in self.EPA_UNIT_PATTERNS:
            match = pattern.search(text)
            if match:
                return self._normalize_unit_extended(match.group(1))
        return ""

    def _normalize_unit(self, unit: str) -> str:
        """단위 표준화"""
        unit_clean = re.sub(r"\s+", "", unit)
        mapping = {
            "kgCO2/kWh": "kgCO2e/kWh",
            "kgCO2e/kWh": "kgCO2e/kWh",
            "gCO2/kWh": "gCO2e/kWh",
            "gCO2e/kWh": "gCO2e/kWh",
            "tCO2/MWh": "kgCO2e/kWh",
            "kgCO2/L": "kgCO2e/L",
            "kgCO2e/L": "kgCO2e/L",
            "kgCO2/km": "kgCO2e/km",
            "kgCO2e/km": "kgCO2e/km",
            "kgCO2/ton": "kgCO2e/ton",
            "kgCO2e/ton": "kgCO2e/ton",
        }
        return mapping.get(unit_clean, unit_clean)

    def _normalize_unit_extended(self, unit: str) -> str:
        """EPA 스타일 단위 표준화 ('kg CO2 per mmBtu' → 'kgCO2/mmBtu')"""
        unit_lower = unit.lower().strip()
        mapping = {
            "kg co2 per mmbtu": "kgCO2/mmBtu",
            "kg co2 per short ton": "kgCO2/short_ton",
            "kg co2 per gallon": "kgCO2/gallon",
            "kg co2 per scf": "kgCO2/scf",
            "kg co2 per barrel": "kgCO2/barrel",
            "g ch4 per mmbtu": "gCH4/mmBtu",
            "g n2o per mmbtu": "gN2O/mmBtu",
            "g co2 per mmbtu": "gCO2/mmBtu",
            "lb co2 per mwh": "lbCO2/MWh",
            "lb co2e per mwh": "lbCO2e/MWh",
            "kg co2e per kwh": "kgCO2e/kWh",
            "kg / unit": "kgCO2e/unit",
            "kg co2 / unit": "kgCO2e/unit",
            "g / mile": "gCO2e/mile",
            "g / gallon": "gCO2e/gallon",
            "g / vehicle-mile": "gCO2e/vehicle-mile",
            "g / passenger-mile": "gCO2e/passenger-mile",
            "g / short ton": "gCO2e/short_ton",
            "lb / mwh": "lbCO2/MWh",
            "lb co2 / mwh": "lbCO2/MWh",
            "kg / mwh": "kgCO2e/MWh",
            "t-co2/kwh": "tCO2/kWh",
            "t-co2e/kwh": "tCO2e/kWh",
            "(t-co2/kwh)": "tCO2/kWh",
        }

        for key, val in mapping.items():
            if key in unit_lower:
                return val

        # 일반적 패턴: "X per Y" → "X/Y"
        m = re.match(r"(\w+\s*CO2e?)\s+per\s+(\w+)", unit, re.IGNORECASE)
        if m:
            return f"{m.group(1).replace(' ', '')}/{m.group(2)}"

        return unit.replace(" ", "")

    def _extract_from_text_table(self, table: List[List], source_info: dict = None) -> List[Dict]:
        """구조화되지 않은 테이블에서 패턴 추출"""
        results = []

        # 전체 테이블 텍스트에서 Scope/GWP 감지
        full_text = " ".join(" ".join(str(c) for c in row) for row in table)
        table_scope = self._detect_scope(full_text)
        table_gwp = self._detect_gwp_version(full_text)

        for row in table:
            row_text = " ".join(str(c) for c in row)
            unit = self._detect_unit_extended(row_text)
            if unit:
                numbers = self.NUMBER_PATTERN.findall(row_text)
                for num_str in numbers:
                    try:
                        value = float(num_str)
                        if 0 < value < 10000 and not (2000 <= value <= 2030):
                            record = {
                                "item_name_original": row_text[:200],
                                "standard_value": value,
                                "standard_unit": unit,
                                "extraction_method": "text_table_pattern",
                            }
                            if table_scope:
                                record["scope"] = table_scope
                            if table_gwp:
                                record["gwp_version"] = table_gwp
                            if source_info:
                                record.update(source_info)
                            results.append(record)
                    except ValueError:
                        continue
        return results

    def _extract_cbam(self, tables: List[List], source_info: dict) -> List[Dict]:
        """CBAM 전용 파서 - 국가별 시트에서 CN code별 배출계수 추출"""
        results = []
        default_unit = source_info.get("default_unit", "tCO2e/ton")

        for table in tables:
            if not table or len(table) < 3:
                continue

            # 국가명 또는 시트 식별
            country_name = ""
            header_idx = None

            for i, row in enumerate(table[:5]):
                cells = [str(c).strip() for c in row if str(c).strip() not in ("nan", "None", "")]
                if not cells:
                    continue
                row_text = " ".join(cells).lower()

                # 헤더 행: "Product CN Code" 또는 "CN code"
                if "cn code" in row_text or "product" in row_text:
                    header_idx = i
                    break
                # 첫 행이 국가명
                if i == 0 and len(cells) == 1 and len(cells[0]) < 50:
                    country_name = cells[0]

            if header_idx is None:
                continue

            # 스킵 시트
            if any(skip in country_name.lower() for skip in ["version", "overview", "history"]):
                continue

            header = [str(c).strip() if c else "" for c in table[header_idx]]
            header_lower = [h.lower() for h in header]

            # 값 컬럼 식별
            value_cols = []  # [(col_idx, label, is_markup)]
            for i, h in enumerate(header_lower):
                if "default value" in h:
                    if "direct" in h:
                        value_cols.append((i, "direct", False))
                    elif "indirect" in h:
                        value_cols.append((i, "indirect", False))
                    elif "total" in h:
                        value_cols.append((i, "total", False))
                    elif "including" in h or "mark-up" in header[i].lower():
                        # 2026/2027/2028 mark-up
                        year_match = re.search(r"(20\d{2})", header[i])
                        yr = year_match.group(1) if year_match else ""
                        value_cols.append((i, f"markup_{yr}", True))

            if not value_cols:
                continue

            # CN code 컬럼
            cn_col = None
            desc_col = None
            for i, h in enumerate(header_lower):
                if "cn code" in h or "product" in h:
                    cn_col = i
                elif "description" in h:
                    desc_col = i

            if cn_col is None:
                cn_col = 0

            # 데이터 행 처리
            current_category = ""
            for row in table[header_idx + 1:]:
                if len(row) <= cn_col:
                    continue

                cn_code = str(row[cn_col]).strip()
                if cn_code in ("nan", "None", "", "–", "_"):
                    # 카테고리 행 ("Cement", "Iron and Steel" 등)
                    # 보통 첫 열에만 값이 있는 행
                    non_empty = [str(c).strip() for c in row if str(c).strip() not in ("nan", "None", "", "–", "_")]
                    if len(non_empty) <= 2 and non_empty:
                        cat = non_empty[0]
                        if len(cat) < 50 and not re.match(r"^\d", cat):
                            current_category = cat
                    continue

                # mark-up 행 ("10% mark-up" 등) 스킵
                if "mark-up" in cn_code.lower() or "%" in cn_code:
                    continue

                desc = ""
                if desc_col is not None and desc_col < len(row):
                    desc = str(row[desc_col]).strip()
                    if desc in ("nan", "None"):
                        desc = ""

                for col_idx, label, is_markup in value_cols:
                    if col_idx >= len(row):
                        continue

                    val_str = str(row[col_idx]).strip()
                    if val_str in ("nan", "None", "", "–", "_"):
                        continue

                    try:
                        value = float(val_str)
                    except (ValueError, TypeError):
                        continue

                    if value <= 0 or value > 100000:
                        continue

                    # item name 구성
                    item_parts = []
                    if desc:
                        item_parts.append(desc)
                    else:
                        item_parts.append(cn_code)
                    if country_name:
                        item_parts.append(f"({country_name})")
                    item_parts.append(f"[{label}]")

                    item_name = " ".join(item_parts)

                    # Scope: direct=Scope1, indirect=Scope2, total=Scope1+2
                    scope = ""
                    if "direct" in label:
                        scope = "Scope 1"
                    elif "indirect" in label:
                        scope = "Scope 2"
                    elif "total" in label or "markup" in label:
                        scope = "Scope 1"

                    record = {
                        "item_name_original": item_name,
                        "item_name_standard": cn_code.replace(" ", ""),
                        "category": self.classify_category(desc or current_category) or current_category.lower().replace(" ", "_") or "industrial",
                        "scope": scope,
                        "level1": "Industry",
                        "level2": current_category.lower().replace(" ", "_") if current_category else "industrial",
                        "level3": label,
                        "standard_value": value,
                        "standard_unit": default_unit,
                        "year": None,
                        "extraction_method": "cbam_direct",
                        "table_context": f"CBAM {country_name}",
                    }

                    if source_info:
                        record.update(source_info)
                    results.append(record)

        return results
