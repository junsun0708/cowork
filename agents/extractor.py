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
               "배출계수", "coefficient", "default value"],
        "unit": ["unit", "단위", "単位", "mmbtu", "per", "t-co2", "kwh", "co2/kwh"],
        "item": ["activity", "fuel", "fuel type", "item", "category", "항목",
                 "연료", "活動", "source", "type", "事業者名", "電気事業者",
                 "메뉴", "メニュー", "description", "emission source", "product"],
        "year": ["year", "연도", "年度", "令和"],
        "co2": ["co2", "carbon dioxide", "이산화탄소", "二酸化炭素"],
        "ch4": ["ch4", "methane", "메탄", "メタン"],
        "n2o": ["n2o", "nitrous oxide", "아산화질소", "一酸化二窒素"],
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
            h = str(header[ef_col]).strip()
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
                            if 0 < v <= 100000 and not (2000 <= v <= 2030):
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
        if v <= 0 or v > 100000 or (2000 <= v <= 2030):
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
            max_cell_len = max(len(c) for c in non_empty) if non_empty else 0
            if max_cell_len > 60:
                continue

            row_text = self._normalize_subscripts(" ".join(c.lower() for c in non_empty))

            # 헤더 키워드 매칭 (ef, unit, item, year + co2, ch4, n2o)
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
            "litres": "L",
            "litre": "L",
            "kwh (net cv)": "kWh",
            "kwh (gross cv)": "kWh",
            "kwh": "kWh",
            "mwh": "MWh",
            "cubic metres": "m3",
            "m3": "m3",
            "kg": "kg",
            "gj": "GJ",
            "mj": "MJ",
            "gallons": "gallon",
            "gallon": "gallon",
            "passenger km": "pkm",
            "passenger mile": "passenger-mile",
            "tonne km": "tkm",
            "tonne.km": "tkm",
            "tonne km": "tkm",
            "km": "km",
            "miles": "mile",
            "mile": "mile",
            "passenger.km": "pkm",
            "passenger km": "pkm",
            "passenger-km": "pkm",
            "room per night": "night",
            "room night": "night",
            "night": "night",
            "scf": "scf",
            "barrel": "barrel",
            "gallon": "gallon",
            "gallons": "gallon",
            "short ton": "short_ton",
            "vehicle-mile": "vehicle-mile",
            "vehicle mile": "vehicle-mile",
            "passenger-mile": "passenger-mile",
            "passenger mile": "passenger-mile",
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
