"""
NanoClaw Normalizer Agent
- 단위 변환 및 표준화
- 다국어 항목명 통합
- 카테고리 매핑
- GWP 다중 버전 CO2e 산출
- Scope/계층 자동 배정
- Factor-id 생성
"""
import logging
from typing import Dict, Optional, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import (
    STANDARD_UNITS,
    RELIABILITY_SCORES,
    GWP_VERSIONS,
    DEFAULT_GWP_VERSION,
    get_hierarchy_for_category,
    get_scope_for_category,
    generate_factor_id,
)

logger = logging.getLogger("nanoclaw.normalizer")


class Normalizer:
    """배출계수 데이터 정규화"""

    # 단위 변환 매핑: (원본단위, 목표단위) -> 변환계수
    CONVERSION_MAP = {
        # ── 전력 관련 ──
        ("gCO2e/kWh", "kgCO2e/kWh"): 0.001,
        ("gCO2/kWh", "kgCO2e/kWh"): 0.001,
        ("tCO2e/MWh", "kgCO2e/kWh"): 1.0,
        ("tCO2/MWh", "kgCO2e/kWh"): 1.0,
        ("lbsCO2/MWh", "kgCO2e/kWh"): 0.000453592,
        ("lbCO2/MWh", "kgCO2e/kWh"): 0.000453592,
        ("lbCO2e/MWh", "kgCO2e/kWh"): 0.000453592,
        ("kgCO2/kWh", "kgCO2e/kWh"): 1.0,
        ("tCO2/kWh", "kgCO2e/kWh"): 1000.0,
        ("tCO2e/kWh", "kgCO2e/kWh"): 1000.0,
        # ── 체적(리터) 관련 ──
        ("gCO2e/L", "kgCO2e/L"): 0.001,
        ("gCO2/L", "kgCO2e/L"): 0.001,
        ("kgCO2/L", "kgCO2e/L"): 1.0,
        # ── 중량(톤) 관련 ──
        ("tCO2e/ton", "kgCO2e/ton"): 1000.0,
        ("tCO2/ton", "kgCO2e/ton"): 1000.0,
        ("kgCO2/ton", "kgCO2e/ton"): 1.0,
        ("tCO2/t", "kgCO2e/ton"): 1000.0,
        # ── 중량(kg) 관련 ──
        ("kgCO2/kg", "kgCO2e/kg"): 1.0,
        ("gCO2/kg", "kgCO2e/kg"): 0.001,
        # ── 체적(m3) 관련 ──
        ("kgCO2/m3", "kgCO2e/m3"): 1.0,
        # ── 에너지(GJ/MJ/TJ) 관련 ──
        ("kgCO2e/GJ", "kgCO2e/GJ"): 1.0,
        ("tCO2/TJ", "kgCO2e/GJ"): 1.0,
        ("kgCO2e/MJ", "kgCO2e/GJ"): 1000.0,
        ("gCO2e/MJ", "kgCO2e/GJ"): 1.0,
        # ── 운송(tkm, pkm) 관련 ──
        ("kgCO2e/tkm", "kgCO2e/tkm"): 1.0,
        ("gCO2e/pkm", "kgCO2e/pkm"): 0.001,
        ("kgCO2e/passenger-km", "kgCO2e/pkm"): 1.0,
        # ── 기타 단위 ──
        ("kgCO2e/unit", "kgCO2e/unit"): 1.0,
        ("kgCO2e/night", "kgCO2e/night"): 1.0,
        ("kgCO2e/person", "kgCO2e/person"): 1.0,
        ("kgCO2e/m2", "kgCO2e/m2"): 1.0,
    }

    def calculate_gwp_values(self, co2: float, ch4: float, n2o: float) -> dict:
        """모든 GWP 버전에 대해 CO2e 값을 산출"""
        results = {}
        for version, gwp in GWP_VERSIONS.items():
            co2e = (co2 * gwp["CO2"]) + (ch4 * gwp["CH4"]) + (n2o * gwp["N2O"])
            results[f"value_{version.lower()}"] = round(co2e, 8)
        return results

    def normalize_record(self, record: dict) -> dict:
        """레코드 전체 정규화"""
        normalized = record.copy()
        mapping_log = []

        # ── 1. 단위 변환 ──
        value, unit, factor = self.convert_unit(
            record.get("standard_value", 0),
            record.get("standard_unit", ""),
        )
        normalized["standard_value"] = value
        normalized["standard_unit"] = unit
        normalized["conversion_factor"] = factor
        if factor != 1.0:
            mapping_log.append(
                f"단위변환: {record.get('standard_unit')} -> {unit} (x{factor})"
            )

        # ── 2. 항목명 표준화 ──
        if "item_name_original" in record and not record.get("item_name_standard"):
            from agents.extractor import Extractor
            ext = Extractor()
            normalized["item_name_standard"] = ext.standardize_item_name(
                record["item_name_original"],
                record.get("language_code", "en"),
            )
        if normalized.get("item_name_standard") != record.get("item_name_original"):
            mapping_log.append(
                f"항목명 표준화: {record.get('item_name_original')} -> {normalized.get('item_name_standard')}"
            )

        # ── 3. 카테고리 매핑 ──
        if not record.get("category"):
            from agents.extractor import Extractor
            ext = Extractor()
            item = normalized.get("item_name_standard") or normalized.get("item_name_original", "")
            normalized["category"] = ext.classify_category(item) or "unknown"

        # ── 4. Scope / 계층 자동 배정 ──
        category = normalized.get("category", "unknown")
        if category and category != "unknown":
            # Scope
            if not record.get("scope"):
                scope = get_scope_for_category(category)
                normalized["scope"] = scope
                mapping_log.append(f"Scope 자동배정: {scope}")

            # 계층 (level1 / level2 / level3)
            if not record.get("level1"):
                hierarchy = get_hierarchy_for_category(category)
                normalized["level1"] = hierarchy.get("level1", "")
                normalized["level2"] = hierarchy.get("level2", "")
                normalized["level3"] = hierarchy.get("level3", "")
                mapping_log.append(
                    f"계층 자동배정: {hierarchy.get('level1')}/{hierarchy.get('level2')}/{hierarchy.get('level3')}"
                )

        # ── 5. GWP 다중 버전 CO2e 산출 ──
        co2_val = record.get("co2_value")
        ch4_val = record.get("ch4_value")
        n2o_val = record.get("n2o_value")

        has_individual_gases = any(v is not None and v != 0 for v in [co2_val, ch4_val, n2o_val])
        if has_individual_gases:
            co2_val = float(co2_val or 0)
            ch4_val = float(ch4_val or 0)
            n2o_val = float(n2o_val or 0)
            normalized["co2_value"] = co2_val
            normalized["ch4_value"] = ch4_val
            normalized["n2o_value"] = n2o_val

            gwp_results = self.calculate_gwp_values(co2_val, ch4_val, n2o_val)
            normalized.update(gwp_results)

            # 기본 GWP 버전으로 standard_value 갱신 (단위 변환 이전 값이 없는 경우)
            if not record.get("standard_value"):
                default_key = f"value_{DEFAULT_GWP_VERSION.lower()}"
                normalized["standard_value"] = gwp_results.get(default_key, 0)

            normalized["gwp_version"] = record.get("gwp_version", DEFAULT_GWP_VERSION)
            versions_str = ", ".join(gwp_results.keys())
            mapping_log.append(
                f"GWP 다중버전 산출(CO2={co2_val}, CH4={ch4_val}, N2O={n2o_val}): {versions_str}"
            )
        else:
            # 개별 가스 없이 합산값만 있는 경우
            if not record.get("gwp_version"):
                normalized["gwp_version"] = DEFAULT_GWP_VERSION

        # ── 6. 신뢰도 점수 ──
        if not record.get("data_reliability_score"):
            source_type = record.get("source_type", "")
            normalized["data_reliability_score"] = RELIABILITY_SCORES.get(source_type, 1)

        # ── 7. Factor-id 생성 ──
        if not record.get("factor_id"):
            try:
                scope_val = normalized.get("scope", "Scope1")
                country = normalized.get("country_code", "XX")
                cat_code = normalized.get("category", "unknown")
                seq = record.get("seq", 0)
                version_year = record.get("year", 0)
                factor_id = generate_factor_id(country, scope_val, cat_code, seq, version_year)
                normalized["factor_id"] = factor_id
                mapping_log.append(f"Factor-id 생성: {factor_id}")
            except Exception as e:
                logger.warning(f"[Normalizer] Factor-id 생성 실패: {e}")

        # ── 8. 매핑 로그 ──
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
