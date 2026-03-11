"""
NanoClaw Web Search Agent
- 웹 검색을 통한 배출계수 데이터 소스 자동 발견
- 검색 결과에서 배출계수 페이지 식별
- 새로운 소스를 Registry에 추가
"""
import json
import logging
import re
from typing import List, Dict
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import PDF_KEYWORDS

logger = logging.getLogger("nanoclaw.websearch")

HEADERS = {
    "User-Agent": "NanoClaw/1.0 (Emission Factor Data Research)",
    "Accept": "text/html,application/xhtml+xml",
}


class WebSearchAgent:
    """웹 검색을 통한 배출계수 소스 발견"""

    # 배출계수 관련 URL 패턴
    EF_URL_PATTERNS = [
        r"emission.?factor",
        r"ghg.?factor",
        r"conversion.?factor",
        r"carbon.?intensity",
        r"co2.?factor",
        r"배출계수",
        r"排出係数",
    ]

    def search_emission_factors(self, query: str, num_results: int = 10) -> List[Dict]:
        """
        배출계수 관련 웹 검색 (Google 사용 불가 시 대안 엔진)
        실제 운영 시 SerpAPI, Google Custom Search API 등 사용 권장
        """
        results = []

        # DuckDuckGo HTML 검색 (API 키 불필요)
        try:
            url = "https://html.duckduckgo.com/html/"
            resp = requests.post(
                url,
                data={"q": query},
                headers=HEADERS,
                timeout=15,
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for result in soup.select(".result__body")[:num_results]:
                    title_el = result.select_one(".result__a")
                    snippet_el = result.select_one(".result__snippet")
                    if title_el:
                        href = title_el.get("href", "")
                        # DuckDuckGo redirect URL에서 실제 URL 추출
                        if "uddg=" in href:
                            from urllib.parse import unquote, parse_qs, urlparse
                            parsed = urlparse(href)
                            params = parse_qs(parsed.query)
                            href = unquote(params.get("uddg", [href])[0])

                        results.append({
                            "title": title_el.get_text(strip=True),
                            "url": href,
                            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                        })
        except Exception as e:
            logger.error(f"[WebSearch] 검색 실패: {e}")

        return results

    def filter_ef_results(self, results: List[Dict]) -> List[Dict]:
        """검색 결과에서 배출계수 관련 결과만 필터링"""
        filtered = []
        for r in results:
            text = f"{r.get('title', '')} {r.get('snippet', '')} {r.get('url', '')}".lower()
            score = 0
            for pattern in self.EF_URL_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    score += 1
            for kw in PDF_KEYWORDS:
                if kw.lower() in text:
                    score += 1
            if score >= 1:
                r["relevance_score"] = score
                filtered.append(r)

        return sorted(filtered, key=lambda x: x.get("relevance_score", 0), reverse=True)

    def discover_sources_for_country(self, country_code: str, country_name: str,
                                       year: int = 2025) -> List[Dict]:
        """국가별 배출계수 소스 자동 발견"""
        queries = [
            f"{country_name} emission factor database {year}",
            f"{country_name} official greenhouse gas emission factors",
            f"{country_name} CO2 emission factors electricity",
        ]

        all_results = []
        for q in queries:
            results = self.search_emission_factors(q)
            filtered = self.filter_ef_results(results)
            all_results.extend(filtered)

        # 중복 URL 제거
        seen_urls = set()
        unique = []
        for r in all_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique.append(r)

        return unique[:20]
