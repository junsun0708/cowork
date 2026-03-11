"""
NanoClaw Extractor Agent
- Raw 데이터에서 배출계수 항목을 추출
- 테이블 파싱, 키워드 매칭
- 배출계수 후보 식별
- EPA 스타일 멀티 테이블 지원
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

    # 헤더 키워드 세트
    HEADER_KEYWORDS = {
        "ef": ["emission factor", "ef", "factor", "value", "co2 factor", "ch4 factor",
               "n2o factor", "계수", "排出係数", "排出量", "conversion factor", "kg co2",
               "heat content", "carbon coefficient", "基礎排出係数", "調整後排出係数",
               "배출계수", "coefficient"],
        "unit": ["unit", "단위", "単位", "mmbtu", "per", "t-co2", "kwh", "co2/kwh"],
        "item": ["activity", "fuel", "fuel type", "item", "category", "항목",
                 "연료", "活動", "source", "type", "事業者名", "電気事業者",
                 "메뉴", "メニュー"],
        "year": ["year", "연도", "年度", "令和"],
    }

    def extract_from_tables(self, tables: List[List], source_info: dict = None) -> List[Dict]:
        """테이블 데이터에서 배출계수 추출 (멀티 테이블 지원)"""
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

    def _extract_single_table(self, table: List[List], source_info: dict = None) -> List[Dict]:
        """단일 테이블에서 배출계수 추출"""
        results = []

        # 실제 헤더 행 찾기
        header_idx, header = self._find_header_row(table)
        if header_idx is None:
            return self._extract_from_text_table(table, source_info)

        header_lower = [str(h).lower().strip() for h in header]

        # 배출계수 관련 컬럼 식별
        ef_col = self._find_column(header_lower, self.HEADER_KEYWORDS["ef"])
        unit_col = self._find_column(header_lower, self.HEADER_KEYWORDS["unit"])
        item_col = self._find_column(header_lower, self.HEADER_KEYWORDS["item"])
        year_col = self._find_column(header_lower, self.HEADER_KEYWORDS["year"])

        # 서브 헤더 단위 행 검사 (EPA 스타일)
        unit_from_subheader = ""
        ef_unit_from_subheader = ""
        data_start = header_idx + 1

        if header_idx + 1 < len(table):
            sub_row = table[header_idx + 1]
            sub_cells = [str(c).strip() for c in sub_row]
            sub_text = " ".join(c for c in sub_cells if c not in ("nan", "None", ""))

            is_unit_row = any(u in sub_text.lower() for u in [
                "kg co2", "g co2", "g ch4", "g n2o", "mmbtu", "kwh", "per",
                "lb co2", "short ton", "gallon", "barrel", "scf"
            ])
            if is_unit_row:
                unit_from_subheader = sub_text
                # ef_col 위치의 단위 추출
                if ef_col is not None and ef_col < len(sub_cells):
                    ef_unit_from_subheader = sub_cells[ef_col].strip()
                    if ef_unit_from_subheader in ("nan", "None"):
                        ef_unit_from_subheader = ""
                data_start = header_idx + 2

        if ef_col is None:
            return self._extract_from_text_table(table, source_info)

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

        # 데이터 행 처리
        current_category = ""
        for row in table[data_start:]:
            if len(row) <= ef_col:
                continue

            try:
                value_str = str(row[ef_col]).strip()
                if value_str in ("nan", "None", "", "-"):
                    # 카테고리/섹션 행일 수 있음
                    if item_col is not None and item_col < len(row):
                        candidate = str(row[item_col]).strip()
                        if candidate not in ("nan", "None", "", "-"):
                            # 새 테이블 경계면 중단
                            if self.TABLE_BOUNDARY.match(candidate):
                                break
                            current_category = candidate
                    continue

                value_match = self.NUMBER_PATTERN.search(value_str)
                if not value_match:
                    continue

                value = float(value_match.group(1))
                if value <= 0 or value > 100000:
                    continue
                # 연도값 제외
                if 2000 <= value <= 2030:
                    continue

                item = ""
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

                year = None
                if year_col is not None and year_col < len(row):
                    year_match = self.YEAR_PATTERN.search(str(row[year_col]))
                    year = int(year_match.group(1)) if year_match else None

                record = {
                    "item_name_original": item,
                    "item_name_standard": self.standardize_item_name(item, "en"),
                    "category": self.classify_category(item) or current_category or "",
                    "standard_value": value,
                    "standard_unit": row_unit,
                    "year": year,
                    "extraction_method": "table_column_smart",
                    "table_context": table_context,
                }
                if source_info:
                    record.update(source_info)
                results.append(record)

            except (ValueError, IndexError) as e:
                logger.debug(f"[Extractor] 행 파싱 스킵: {e}")

        return results

    def _find_header_row(self, table: List[List]) -> tuple:
        """테이블에서 실제 헤더 행 찾기 (빈 행/제목 행/긴 문장 건너뛰기)"""
        best_match = (None, None, 0)  # (index, row, score)

        for i, row in enumerate(table[:50]):
            # nan이 아닌 셀만 추출
            non_empty = [str(c).strip() for c in row if str(c).strip() not in ("nan", "None", "")]
            if len(non_empty) < 2:
                continue

            # 긴 셀이 있으면 헤더 아님 (문장/설명 행 필터링)
            max_cell_len = max(len(c) for c in non_empty) if non_empty else 0
            if max_cell_len > 60:
                continue

            row_text = " ".join(c.lower() for c in non_empty)

            # 헤더 키워드 매칭
            match_count = 0
            for kw_list in self.HEADER_KEYWORDS.values():
                if any(kw in row_text for kw in kw_list):
                    match_count += 1

            if match_count >= 2 and match_count > best_match[2]:
                best_match = (i, row, match_count)

        if best_match[0] is not None:
            return best_match[0], best_match[1]
        return None, None

    def extract_from_text(self, text: str, source_info: dict = None) -> List[Dict]:
        """텍스트에서 배출계수 패턴 추출"""
        results = []

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
                        if source_info:
                            record.update(source_info)
                        results.append(record)
                except ValueError:
                    continue

        return results

    def classify_category(self, item_name: str) -> Optional[str]:
        """항목명을 택소노미 카테고리로 분류"""
        item_lower = item_name.lower()

        for parent, children in TAXONOMY.items():
            for child in children:
                if child.replace("_", " ") in item_lower or child in item_lower:
                    return child

        keyword_map = {
            "electricity": ["전력", "전기", "grid", "power", "電力", "electricité", "egrid"],
            "natural_gas": ["천연가스", "lng", "natural gas", "天然ガス", "gaz naturel"],
            "coal": ["석탄", "coal", "anthracite", "bituminous", "lignite", "charbon"],
            "diesel": ["디젤", "경유", "diesel", "distillate"],
            "gasoline": ["가솔린", "휘발유", "gasoline", "petrol", "motor gasoline", "essence"],
            "lpg": ["lpg", "프로판", "부탄", "propane", "butane"],
            "fuel_oil": ["fuel oil", "residual", "중유", "kerosene", "jet fuel", "aviation"],
            "cement": ["시멘트", "cement", "セメント", "ciment"],
            "steel": ["철강", "steel", "鉄鋼", "acier"],
        }

        for category, keywords in keyword_map.items():
            if any(kw in item_lower for kw in keywords):
                return category

        return None

    def standardize_item_name(self, original: str, language_code: str = "en") -> str:
        """항목명을 영문 표준명으로 변환"""
        translations = {
            "전력": "electricity",
            "천연가스": "natural_gas",
            "석탄": "coal",
            "경유": "diesel",
            "휘발유": "gasoline",
            "시멘트": "cement",
            "철강": "steel",
            "電力": "electricity",
            "天然ガス": "natural_gas",
            "石炭": "coal",
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
        }

        original_lower = original.lower().strip()
        for key, std_name in translations.items():
            if key.lower() in original_lower:
                return std_name

        return original_lower.replace(" ", "_")

    def _find_column(self, header: List[str], keywords: List[str]) -> Optional[int]:
        """헤더에서 키워드 매칭 컬럼 인덱스 찾기"""
        for i, h in enumerate(header):
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
                            if source_info:
                                record.update(source_info)
                            results.append(record)
                    except ValueError:
                        continue
        return results
