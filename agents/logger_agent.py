"""
NanoClaw Logger Agent
- 프롬프트 로그 기록
- 일일 수집 결과 저장
- 오류 리포트 생성
"""
import json
import logging
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import LOGS_DIR, OUTPUT_DIR, TODAY

logger = logging.getLogger("nanoclaw.logger")


class NanoClawLogger:
    """NanoClaw 로그 및 리포트 관리"""

    def __init__(self):
        self.logs_dir = LOGS_DIR
        self.output_dir = OUTPUT_DIR
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def log_prompt(self, country: str, keywords: list, urls: list,
                   results: dict, errors: list = None):
        """프롬프트 실행 로그 기록"""
        log_file = self.logs_dir / f"{TODAY}.md"

        entry = (
            f"\n## 실행 로그 - {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"- **대상 국가**: {country}\n"
            f"- **검색 키워드**: {', '.join(keywords[:5])}\n"
            f"- **탐색 URL**: {len(urls)}개\n"
        )

        for url in urls[:10]:
            entry += f"  - {url}\n"

        entry += (
            f"- **수집 결과**: {results.get('items', 0)}건 수집\n"
            f"- **신규**: {results.get('new', 0)}건\n"
            f"- **변경**: {results.get('changed', 0)}건\n"
        )

        if errors:
            entry += f"- **오류**: {len(errors)}건\n"
            for err in errors[:5]:
                entry += f"  - {err}\n"

        entry += "\n---\n"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)

        logger.info(f"[Logger] 프롬프트 로그 기록: {log_file}")

    def save_daily_output(self, summary: dict, processed_data: list,
                          errors: list = None, new_discoveries: list = None):
        """일일 수집 결과 저장"""
        today_dir = self.output_dir / TODAY
        today_dir.mkdir(parents=True, exist_ok=True)

        # 수집 결과 요약
        summary_file = today_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump({
                "date": TODAY,
                "generated_at": datetime.now().isoformat(),
                "summary": summary,
            }, f, ensure_ascii=False, indent=2)

        # 처리된 데이터 목록
        if processed_data:
            data_file = today_dir / "processed_data.json"
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(processed_data, f, ensure_ascii=False, indent=2)

        # 오류 리포트
        if errors:
            error_file = today_dir / "error_report.md"
            with open(error_file, "w", encoding="utf-8") as f:
                f.write(f"# 오류 리포트 - {TODAY}\n\n")
                for i, err in enumerate(errors, 1):
                    f.write(f"## 오류 {i}\n{err}\n\n")

        # 신규 발견 데이터
        if new_discoveries:
            discovery_file = today_dir / "new_discoveries.json"
            with open(discovery_file, "w", encoding="utf-8") as f:
                json.dump(new_discoveries, f, ensure_ascii=False, indent=2)

        logger.info(f"[Logger] 일일 결과 저장: {today_dir}")
        return str(today_dir)

    def save_collection_summary_md(self, summary: dict, country: str) -> str:
        """마크다운 형식의 수집 요약 생성"""
        today_dir = self.output_dir / TODAY
        today_dir.mkdir(parents=True, exist_ok=True)
        md_file = today_dir / f"collection_summary_{country}.md"

        content = (
            f"# NanoClaw 수집 요약 - {country} ({TODAY})\n\n"
            f"## 개요\n"
            f"- 수집 국가: {country}\n"
            f"- 수집 기관: {summary.get('orgs', 'N/A')}\n"
            f"- 수집 항목: {summary.get('total_items', 0)}건\n"
            f"- DB 신규: {summary.get('new_items', 0)}건\n"
            f"- DB 변경: {summary.get('changed_items', 0)}건\n"
            f"- 오류: {summary.get('errors', 0)}건\n\n"
        )

        if summary.get("categories"):
            content += "## 카테고리별 수집 현황\n"
            for cat, count in summary["categories"].items():
                content += f"- {cat}: {count}건\n"

        md_file.write_text(content, encoding="utf-8")
        return str(md_file)
