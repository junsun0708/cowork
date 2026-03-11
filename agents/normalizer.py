"""
NanoClaw Normalizer Agent
- 단위 변환 및 표준화
- 다국어 항목명 통합
- 카테고리 매핑
"""
import logging
from typing import Dict, Optional, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import STANDARD_UNITS, RELIABILITY_SCORES

logger = logging.getLogger("nanoclaw.normalizer")


class Normalizer:
    """배출계수 데이터 정규화"""

    # 단위 변환 매핑: (원본단위, 목표단위) -> 변환계수
    CONVERSION_MAP = {
        ("gCO2e/kWh", "kgCO2e/kWh"): 0.001,
        ("gCO2/kWh", "kgCO2e/kWh"): 0.001,
        ("tCO2e/MWh", "kgCO2e/kWh"): 1.0,
        ("tCO2/MWh", "kgCO2e/kWh"): 1.0,
        ("lbsCO2/MWh", "kgCO2e/kWh"): 0.000453592,
        ("lbCO2/MWh", "kgCO2e/kWh"): 0.000453592,
        ("kgCO2/kWh", "kgCO2e/kWh"): 1.0,
        ("gCO2e/L", "kgCO2e/L"): 0.001,
        ("gCO2/L", "kgCO2e/L"): 0.001,
        ("kgCO2/L", "kgCO2e/L"): 1.0,
        ("tCO2e/ton", "kgCO2e/ton"): 1000.0,
        ("tCO2/ton", "kgCO2e/ton"): 1000.0,
        ("kgCO2/ton", "kgCO2e/ton"): 1.0,
        ("tCO2/kWh", "kgCO2e/kWh"): 1000.0,
        ("tCO2e/kWh", "kgCO2e/kWh"): 1000.0,
        ("kgCO2/m3", "kgCO2e/m3"): 1.0,
        ("kgCO2e/GJ", "kgCO2e/GJ"): 1.0,
        ("tCO2/TJ", "kgCO2e/GJ"): 1.0,
    }

    def normalize_record(self, record: dict) -> dict:
        """레코드 전체 정규화"""
        normalized = record.copy()

        # 1. 단위 변환
        value, unit, factor = self.convert_unit(
            record.get("standard_value", 0),
            record.get("standard_unit", ""),
        )
        normalized["standard_value"] = value
        normalized["standard_unit"] = unit
        normalized["conversion_factor"] = factor

        # 2. 항목명 표준화
        if "item_name_original" in record and not record.get("item_name_standard"):
            from agents.extractor import Extractor
            ext = Extractor()
            normalized["item_name_standard"] = ext.standardize_item_name(
                record["item_name_original"],
                record.get("language_code", "en"),
            )

        # 3. 카테고리 매핑
        if not record.get("category"):
            from agents.extractor import Extractor
            ext = Extractor()
            item = normalized.get("item_name_standard") or normalized.get("item_name_original", "")
            normalized["category"] = ext.classify_category(item) or "unknown"

        # 4. 신뢰도 점수
        if not record.get("data_reliability_score"):
            source_type = record.get("source_type", "")
            normalized["data_reliability_score"] = RELIABILITY_SCORES.get(source_type, 1)

        # 5. 매핑 로그
        mapping_log = []
        if factor != 1.0:
            mapping_log.append(f"단위변환: {record.get('standard_unit')} -> {unit} (x{factor})")
        if normalized.get("item_name_standard") != record.get("item_name_original"):
            mapping_log.append(
                f"항목명 표준화: {record.get('item_name_original')} -> {normalized.get('item_name_standard')}"
            )
        normalized["mapping_log"] = " | ".join(mapping_log) if mapping_log else ""

        return normalized

    def convert_unit(self, value: float, unit: str) -> Tuple[float, str, float]:
        """
        단위 변환
        반환: (변환된 값, 표준 단위, 변환 계수)
        """
        if not unit or not value:
            return value, unit, 1.0

        unit_clean = unit.replace(" ", "")

        # 이미 표준 단위인 경우
        if unit_clean in STANDARD_UNITS:
            return value, unit_clean, 1.0

        # 변환 매핑 탐색
        for (src, dst), factor in self.CONVERSION_MAP.items():
            if unit_clean.lower() == src.lower():
                converted_value = round(value * factor, 8)
                logger.info(f"[Normalizer] 단위 변환: {value} {src} -> {converted_value} {dst}")
                return converted_value, dst, factor

        # 변환 불가 시 원본 유지
        logger.warning(f"[Normalizer] 변환 불가 단위: {unit}")
        return value, unit_clean, 1.0

    def normalize_batch(self, records: list) -> list:
        """여러 레코드 일괄 정규화"""
        normalized = []
        for rec in records:
            try:
                normalized.append(self.normalize_record(rec))
            except Exception as e:
                logger.error(f"[Normalizer] 정규화 오류: {e} | record={rec}")
                rec["mapping_log"] = f"정규화 오류: {e}"
                normalized.append(rec)
        return normalized

    def validate_record(self, record: dict) -> Dict[str, any]:
        """레코드 유효성 검증"""
        issues = []

        if not record.get("country_code"):
            issues.append("country_code 누락")
        if not record.get("source_org"):
            issues.append("source_org 누락")
        if not record.get("standard_value"):
            issues.append("standard_value 누락")
        if record.get("standard_value", 0) <= 0:
            issues.append("standard_value가 0 이하")
        if not record.get("standard_unit"):
            issues.append("standard_unit 누락")
        if record.get("year") and (record["year"] < 1990 or record["year"] > 2030):
            issues.append(f"year 범위 이상: {record['year']}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
        }
