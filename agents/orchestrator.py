"""
NanoClaw Orchestrator
- 전체 수집 파이프라인 관리
- 국가별 순차/병렬 수집 실행
- 에이전트 간 조율
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import (
    BASE_DIR, RAW_DIR, OUTPUT_DIR, ALERTS_DIR,
    TODAY, TODAY_COMPACT, RELIABILITY_SCORES,
)
from agents.source_discovery import SourceDiscovery
from agents.fetcher import Fetcher
from agents.extractor import Extractor
from agents.normalizer import Normalizer
from agents.db_sync import DBSync
from agents.logger_agent import NanoClawLogger
from agents.slack_reporter import SlackReporter

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            str(BASE_DIR / "logs" / f"nanoclaw_{TODAY}.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("nanoclaw.orchestrator")


class Orchestrator:
    """NanoClaw 메인 오케스트레이터"""

    def __init__(self, use_slack: bool = True):
        self.discovery = SourceDiscovery()
        self.fetcher = Fetcher()
        self.extractor = Extractor()
        self.normalizer = Normalizer()
        self.db = DBSync()
        self.logger_agent = NanoClawLogger()
        self.slack = SlackReporter() if use_slack else None

        # 수집 통계
        self.stats = {
            "countries_processed": 0,
            "orgs_processed": 0,
            "items_collected": 0,
            "items_new": 0,
            "items_changed": 0,
            "errors": [],
        }

    def run(self, country_codes: List[str] = None):
        """
        메인 실행 메서드
        country_codes: 수집할 국가 목록 (None이면 전체)
        """
        start_time = datetime.now()
        logger.info("=" * 60)
        logger.info(f"[Orchestrator] NanoClaw 수집 시작: {start_time.isoformat()}")
        logger.info("=" * 60)

        if self.slack:
            self.slack.send_progress(0, "NanoClaw 수집 파이프라인 시작")

        # 대상 국가 결정
        if country_codes is None:
            country_codes = self.discovery.get_all_countries()

        total = len(country_codes)
        logger.info(f"[Orchestrator] 대상 국가: {total}개 - {country_codes}")

        all_processed = []
        all_diffs = []

        for idx, country in enumerate(country_codes):
            progress = int((idx / total) * 100)
            logger.info(f"\n{'='*40}")
            logger.info(f"[Orchestrator] [{idx+1}/{total}] {country} 수집 시작")

            if self.slack and idx % 2 == 0:
                self.slack.send_progress(progress, f"{country} 수집 중... ({idx+1}/{total})")

            try:
                result = self.collect_country(country)
                all_processed.extend(result.get("processed", []))
                all_diffs.extend(result.get("diffs", []))
                self.stats["countries_processed"] += 1
            except Exception as e:
                error_msg = f"[{country}] 수집 실패: {e}"
                logger.error(error_msg)
                self.stats["errors"].append(error_msg)
                if self.slack:
                    self.slack.send_alert("error", error_msg)

        # ── 후처리 ──
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"\n{'='*60}")
        logger.info(f"[Orchestrator] 수집 완료 (소요: {elapsed:.1f}초)")

        # Diff Report 생성
        if all_diffs:
            self.db.generate_diff_report(all_diffs)

        # 일일 결과 저장
        summary = {
            "countries": self.stats["countries_processed"],
            "orgs": self.stats["orgs_processed"],
            "items": self.stats["items_collected"],
            "new_items": self.stats["items_new"],
            "changed_items": self.stats["items_changed"],
            "errors": len(self.stats["errors"]),
            "elapsed_seconds": elapsed,
        }
        self.logger_agent.save_daily_output(summary, all_processed, self.stats["errors"])

        # Slack 최종 보고
        if self.slack:
            self.slack.send_progress(100, "수집 완료!")
            self.slack.send_daily_summary(summary)

        # DB 통계
        db_stats = self.db.get_stats()
        logger.info(f"[DB 통계] {db_stats}")

        return summary

    def collect_country(self, country_code: str) -> dict:
        """단일 국가 수집 파이프라인"""
        result = {"processed": [], "diffs": [], "errors": []}

        # 1. 소스 탐색
        sources = self.discovery.get_sources(country_code)
        keywords = self.discovery.get_search_keywords(country_code)
        logger.info(f"[{country_code}] 소스 {len(sources)}개, 키워드 {len(keywords)}개")

        urls_visited = []

        for source in sources:
            org = source.get("org", "unknown")
            url = source.get("url", "")
            data_urls = source.get("data_urls", [])
            data_format = source.get("data_format", "html")
            source_type = source.get("type", "Government")
            reliability = source.get("reliability_score", RELIABILITY_SCORES.get(source_type, 1))

            if not url and not data_urls:
                continue

            # data_urls가 있으면 우선 수집, 없으면 메인 URL
            fetch_targets = data_urls if data_urls else [url]

            self.stats["orgs_processed"] += 1

            for target_url in fetch_targets:
                logger.info(f"[{country_code}/{org}] 수집 시작: {target_url}")
                urls_visited.append(target_url)

                try:
                    # 2. 포맷에 따라 자동 수집 (xlsx/csv/pdf/html)
                    save_dir = RAW_DIR / country_code / org / datetime.now().strftime("%Y")
                    fetched = self.fetcher.fetch_auto(target_url, data_format, save_dir)

                    if not fetched.get("success"):
                        error_msg = f"[{country_code}/{org}] 수집 실패: {fetched.get('error')}"
                        result["errors"].append(error_msg)
                        self.stats["errors"].append(error_msg)
                        continue

                    # 3. Raw 저장
                    source_info = {
                        "country_code": country_code,
                        "source_org": org,
                        "source_type": source_type,
                        "data_reliability_score": reliability,
                        "language_code": source.get("language_code",
                                                    self.discovery.load_registry(country_code).get("language_code", "en")),
                    }

                    # 테이블에서 배출계수 추출 시도
                    extracted = []
                    if fetched.get("tables"):
                        extracted = self.extractor.extract_from_tables(
                            fetched["tables"], source_info
                        )

                    # 텍스트에서도 추출 시도
                    if fetched.get("text"):
                        text_extracted = self.extractor.extract_from_text(
                            fetched["text"], source_info
                        )
                        extracted.extend(text_extracted)

                    if not extracted:
                        logger.info(f"[{country_code}/{org}] 추출 항목 없음 - Raw만 저장")

                    # Raw 저장 (추출 여부와 무관하게)
                    raw_path = self.fetcher.save_raw(
                        country_code=country_code,
                        source_org=org,
                        category="mixed",
                        data=fetched,
                        source_url=target_url,
                        source_type=source_type,
                        reliability_score=reliability,
                        language_code=source_info["language_code"],
                    )

                    # 4. 정규화 및 DB 저장
                    if extracted:
                        for item in extracted:
                            item["raw_file_path"] = raw_path

                        normalized = self.normalizer.normalize_batch(extracted)

                        # 유효성 검증
                        valid_records = []
                        for rec in normalized:
                            validation = self.normalizer.validate_record(rec)
                            if validation["valid"]:
                                valid_records.append(rec)
                            else:
                                logger.debug(f"[{country_code}/{org}] 검증 실패: {validation['issues']}")

                        # DB upsert
                        if valid_records:
                            db_result = self.db.bulk_upsert(valid_records)
                            self.stats["items_collected"] += len(valid_records)
                            self.stats["items_new"] += db_result["insert"]
                            self.stats["items_changed"] += db_result["update"]
                            result["diffs"].extend(db_result.get("diffs", []))
                            result["processed"].extend(valid_records)

                            logger.info(
                                f"[{country_code}/{org}] DB: "
                                f"+{db_result['insert']} 신규, "
                                f"~{db_result['update']} 변경, "
                                f"={db_result['unchanged']} 동일"
                            )

                            if self.slack:
                                self.slack.send_collection_result(
                                    country_code, org, len(valid_records), db_result["errors"]
                                )

                except Exception as e:
                    error_msg = f"[{country_code}/{org}] 처리 오류: {e}"
                    logger.error(error_msg, exc_info=True)
                    result["errors"].append(error_msg)
                    self.stats["errors"].append(error_msg)

        # 프롬프트 로그
        self.logger_agent.log_prompt(
            country=country_code,
            keywords=keywords[:5],
            urls=urls_visited,
            results={
                "items": len(result["processed"]),
                "new": self.stats["items_new"],
                "changed": self.stats["items_changed"],
            },
            errors=result["errors"],
        )

        return result

    def collect_single(self, country_code: str, org: str = None):
        """단일 국가/기관 수집 (디버깅/테스트용)"""
        if org:
            sources = self.discovery.get_sources(country_code)
            sources = [s for s in sources if s.get("org") == org]
            if not sources:
                logger.error(f"[{country_code}] {org} 소스를 찾을 수 없음")
                return
            # 임시로 국가 소스를 제한
            registry = self.discovery.load_registry(country_code)
            registry["sources"] = sources
        return self.collect_country(country_code)


def main():
    """CLI 실행 진입점"""
    import argparse

    parser = argparse.ArgumentParser(description="NanoClaw 글로벌 배출계수 수집 에이전트")
    parser.add_argument(
        "countries",
        nargs="*",
        default=None,
        help="수집할 국가 코드 (예: KR US JP). 미입력시 전체 수집",
    )
    parser.add_argument(
        "--no-slack",
        action="store_true",
        help="Slack 알림 비활성화",
    )
    parser.add_argument(
        "--org",
        type=str,
        default=None,
        help="특정 기관만 수집 (예: EPA, GIR)",
    )

    args = parser.parse_args()

    orch = Orchestrator(use_slack=not args.no_slack)

    if args.org and args.countries:
        # 특정 기관 수집
        orch.collect_single(args.countries[0], args.org)
    else:
        # 국가별 수집
        countries = args.countries if args.countries else None
        summary = orch.run(countries)
        print(f"\n[완료] 수집 요약: {json.dumps(summary, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
