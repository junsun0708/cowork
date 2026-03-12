"""
NanoClaw Source Discovery Agent
- 국가별 배출계수 데이터 소스 자동 발견
- Source Registry 기반 + 웹 검색 보완
"""
import json
import logging
from pathlib import Path
from typing import List, Dict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import SOURCE_REGISTRY_DIR

logger = logging.getLogger("nanoclaw.discovery")


class SourceDiscovery:
    """국가별 배출계수 데이터 소스 탐색"""

    # 국가별 검색 키워드 템플릿
    SEARCH_TEMPLATES = {
        "en": [
            "{country} emission factor database {year}",
            "{country} greenhouse gas emission factors official",
            "{country} CO2 emission factors electricity {year}",
            "{country} national GHG inventory emission factors",
        ],
        "ko": [
            "한국 배출계수 {year}",
            "국가 온실가스 배출계수 {year}",
            "온실가스 배출계수 공식 데이터",
        ],
        "ja": [
            "日本 排出係数 {year}",
            "温室効果ガス 排出係数 {year}",
        ],
        "de": [
            "Deutschland Emissionsfaktoren {year}",
            "Treibhausgas Emissionsfaktoren {year}",
        ],
        "fr": [
            "France facteurs d'emission {year}",
            "facteurs d'emission GES {year}",
        ],
        "zh": [
            "中国 排放因子 {year}",
            "温室气体排放因子 {year}",
        ],
    }

    def __init__(self):
        self.registry_dir = SOURCE_REGISTRY_DIR

    def load_registry(self, country_code: str) -> dict:
        """Source Registry에서 국가 정보 로드"""
        registry_file = self.registry_dir / f"{country_code}.json"
        if registry_file.exists():
            with open(registry_file, "r", encoding="utf-8") as f:
                return json.load(f)
        logger.warning(f"[Discovery] Registry 없음: {country_code}")
        return {"country": country_code, "sources": []}

    def get_search_keywords(self, country_code: str, year: int = 2025) -> List[str]:
        """국가별 검색 키워드 생성"""
        registry = self.load_registry(country_code)
        keywords = []

        # Registry 키워드
        for source in registry.get("sources", []):
            keywords.extend(source.get("search_keywords", []))

        # 언어별 템플릿 키워드
        lang = registry.get("language_code", "en")
        templates = self.SEARCH_TEMPLATES.get(lang, self.SEARCH_TEMPLATES["en"])
        country_name = registry.get("country_name", country_code)

        for template in templates:
            keywords.append(template.format(country=country_name, year=year))

        # 영어 템플릿도 항상 추가
        if lang != "en":
            for template in self.SEARCH_TEMPLATES["en"]:
                keywords.append(template.format(country=country_name, year=year))

        return list(set(keywords))

    def get_sources(self, country_code: str) -> List[Dict]:
        """국가별 데이터 소스 목록 반환"""
        registry = self.load_registry(country_code)
        sources = registry.get("sources", [])

        # 국제기구 소스 추가 (data_urls가 있는 것만 — 없으면 홈페이지만 불필요 크롤링)
        intl = self.load_registry("INTL")
        for src in intl.get("sources", []):
            if src.get("data_urls"):
                src_copy = src.copy()
                src_copy["scope"] = "international"
                sources.append(src_copy)

        return sources

    def get_all_countries(self) -> List[str]:
        """등록된 모든 국가 코드 반환"""
        countries = []
        for f in self.registry_dir.glob("*.json"):
            code = f.stem
            if code != "INTL":
                countries.append(code)
        return sorted(countries)

    def save_discovered_source(self, country_code: str, source: dict):
        """새로 발견된 소스를 Registry에 추가"""
        registry = self.load_registry(country_code)
        existing_orgs = {s["org"] for s in registry.get("sources", [])}

        if source.get("org") not in existing_orgs:
            registry.setdefault("sources", []).append(source)
            registry_file = self.registry_dir / f"{country_code}.json"
            with open(registry_file, "w", encoding="utf-8") as f:
                json.dump(registry, f, ensure_ascii=False, indent=2)
            logger.info(f"[Discovery] 신규 소스 추가: {country_code}/{source['org']}")
