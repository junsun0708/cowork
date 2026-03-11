"""
NanoClaw DB Sync Agent
- SQLite DB에 정규화된 배출계수 데이터를 upsert
- UID 생성: [국가코드]-[기관명]-[항목명]-[기준년도]
- diff_report 자동 생성
"""
import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DB_PATH, OUTPUT_DIR

logger = logging.getLogger("nanoclaw.db")


class DBSync:
    """SQLite 기반 배출계수 DB 동기화"""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS processed_emissions (
        uid TEXT PRIMARY KEY,
        country_code TEXT NOT NULL,
        source_org TEXT NOT NULL,
        source_type TEXT,
        data_reliability_score INTEGER,
        category TEXT,
        item_name_original TEXT,
        item_name_standard TEXT,
        standard_value REAL,
        standard_unit TEXT,
        year INTEGER,
        language_code TEXT,
        raw_file_path TEXT,
        mapping_log TEXT,
        conversion_factor REAL DEFAULT 1.0,
        extraction_method TEXT,
        table_context TEXT,
        last_checked_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_country ON processed_emissions(country_code);
    CREATE INDEX IF NOT EXISTS idx_category ON processed_emissions(category);
    CREATE INDEX IF NOT EXISTS idx_year ON processed_emissions(year);
    CREATE INDEX IF NOT EXISTS idx_org ON processed_emissions(source_org);
    """

    # DB에 저장할 컬럼 목록
    VALID_COLUMNS = {
        "uid", "country_code", "source_org", "source_type",
        "data_reliability_score", "category", "item_name_original",
        "item_name_standard", "standard_value", "standard_unit",
        "year", "language_code", "raw_file_path", "mapping_log",
        "conversion_factor", "extraction_method", "table_context",
        "last_checked_at", "created_at",
    }

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """DB 초기화 및 테이블 생성"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript(self.SCHEMA)
        logger.info(f"[DB] 초기화 완료: {self.db_path}")

    @staticmethod
    def generate_uid(country_code: str, org: str, item: str, year: int) -> str:
        """UID 생성: KR-GIR-electricity-2022"""
        item_clean = item.lower().replace(" ", "_").replace("/", "_")
        return f"{country_code}-{org}-{item_clean}-{year}"

    def upsert(self, record: dict) -> dict:
        """
        레코드 upsert (삽입 또는 업데이트)
        반환: {"action": "insert"|"update"|"unchanged", "uid": str, "diff": dict|None}
        """
        uid = record.get("uid") or self.generate_uid(
            record["country_code"],
            record["source_org"],
            record.get("item_name_standard", record.get("item_name_original", "")),
            record.get("year", 0),
        )
        record["uid"] = uid
        record["last_checked_at"] = datetime.now().isoformat()

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                "SELECT * FROM processed_emissions WHERE uid = ?", (uid,)
            ).fetchone()

            if existing is None:
                # INSERT (유효한 컬럼만)
                cols = [k for k in record.keys() if k != "created_at" and k in self.VALID_COLUMNS]
                placeholders = ", ".join(["?"] * len(cols))
                col_names = ", ".join(cols)
                conn.execute(
                    f"INSERT INTO processed_emissions ({col_names}) VALUES ({placeholders})",
                    [record.get(c) for c in cols],
                )
                logger.info(f"[DB] INSERT: {uid}")
                return {"action": "insert", "uid": uid, "diff": None}
            else:
                # 변경 감지
                diff = {}
                existing_dict = dict(existing)
                for key in ["standard_value", "standard_unit", "item_name_standard", "category"]:
                    old_val = existing_dict.get(key)
                    new_val = record.get(key)
                    if new_val is not None and str(old_val) != str(new_val):
                        diff[key] = {"old": old_val, "new": new_val}

                if diff:
                    # UPDATE (유효한 컬럼만)
                    update_cols = [k for k in record.keys() if k in self.VALID_COLUMNS]
                    set_clause = ", ".join([f"{c} = ?" for c in update_cols])
                    conn.execute(
                        f"UPDATE processed_emissions SET {set_clause} WHERE uid = ?",
                        [record.get(c) for c in update_cols] + [uid],
                    )
                    logger.info(f"[DB] UPDATE: {uid} | diff={diff}")
                    return {"action": "update", "uid": uid, "diff": diff}
                else:
                    # 변경 없음 - last_checked_at만 갱신
                    conn.execute(
                        "UPDATE processed_emissions SET last_checked_at = ? WHERE uid = ?",
                        (record["last_checked_at"], uid),
                    )
                    return {"action": "unchanged", "uid": uid, "diff": None}

    def bulk_upsert(self, records: list) -> dict:
        """여러 레코드를 일괄 upsert"""
        results = {"insert": 0, "update": 0, "unchanged": 0, "errors": 0, "diffs": []}
        for rec in records:
            try:
                result = self.upsert(rec)
                results[result["action"]] += 1
                if result["diff"]:
                    results["diffs"].append({"uid": result["uid"], "diff": result["diff"]})
            except Exception as e:
                results["errors"] += 1
                logger.error(f"[DB] upsert 오류: {e} | record={rec}")
        return results

    def query_by_country(self, country_code: str) -> list:
        """국가별 배출계수 조회"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM processed_emissions WHERE country_code = ? ORDER BY category, year DESC",
                (country_code,),
            ).fetchall()
            return [dict(r) for r in rows]

    def query_by_category(self, category: str) -> list:
        """카테고리별 배출계수 조회"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM processed_emissions WHERE category = ? ORDER BY country_code, year DESC",
                (category,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """DB 통계"""
        with sqlite3.connect(str(self.db_path)) as conn:
            total = conn.execute("SELECT COUNT(*) FROM processed_emissions").fetchone()[0]
            countries = conn.execute("SELECT COUNT(DISTINCT country_code) FROM processed_emissions").fetchone()[0]
            orgs = conn.execute("SELECT COUNT(DISTINCT source_org) FROM processed_emissions").fetchone()[0]
            categories = conn.execute("SELECT COUNT(DISTINCT category) FROM processed_emissions").fetchone()[0]
            return {
                "total_records": total,
                "countries": countries,
                "orgs": orgs,
                "categories": categories,
            }

    def generate_diff_report(self, diffs: list, output_dir: str = None) -> str:
        """변경사항 diff 리포트 생성"""
        today = datetime.now().strftime("%Y-%m-%d")
        out_dir = Path(output_dir) if output_dir else OUTPUT_DIR / today
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "diff_report.md"

        lines = [
            f"# NanoClaw Diff Report - {today}\n",
            f"변경 항목: {len(diffs)}건\n",
        ]
        for d in diffs:
            lines.append(f"\n## {d['uid']}")
            for field, vals in d["diff"].items():
                lines.append(f"- **{field}**: `{vals['old']}` → `{vals['new']}`")

        report_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"[DB] Diff report 생성: {report_path}")
        return str(report_path)
