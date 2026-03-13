"""
NanoClaw DB Sync Agent
- SQLite DB에 정규화된 배출계수 데이터를 upsert
- UID 생성: [국가코드]-[기관명]-[scope]-[항목명]-[기준년도]
- diff_report 자동 생성
- 변경 이력을 emission_history 테이블에 보존
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
        factor_id TEXT,
        country_code TEXT NOT NULL,
        source_org TEXT NOT NULL,
        source_type TEXT,
        data_reliability_score INTEGER,

        -- Hierarchy (4-level + Scope)
        scope TEXT,
        level1 TEXT,
        level2 TEXT,
        level3 TEXT,
        category TEXT,

        item_name_original TEXT,
        item_name_standard TEXT,

        -- CO2e integrated value
        standard_value REAL,
        standard_unit TEXT,

        -- Individual gas values
        co2_value REAL,
        ch4_value REAL,
        n2o_value REAL,
        co2_unit TEXT,
        ch4_unit TEXT,
        n2o_unit TEXT,

        -- GWP multi-version values
        gwp_version TEXT DEFAULT 'AR6',
        value_sar REAL,
        value_tar REAL,
        value_ar4 REAL,
        value_ar5 REAL,
        value_ar6 REAL,

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

    -- History table for multi-year data preservation
    CREATE TABLE IF NOT EXISTS emission_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT NOT NULL,
        factor_id TEXT,
        country_code TEXT,
        source_org TEXT,
        scope TEXT,
        level1 TEXT,
        level2 TEXT,
        level3 TEXT,
        category TEXT,
        item_name_standard TEXT,
        standard_value REAL,
        standard_unit TEXT,
        co2_value REAL,
        ch4_value REAL,
        n2o_value REAL,
        gwp_version TEXT,
        value_ar5 REAL,
        value_ar6 REAL,
        year INTEGER,
        changed_at TEXT DEFAULT (datetime('now')),
        change_type TEXT,
        previous_value REAL,
        FOREIGN KEY (uid) REFERENCES processed_emissions(uid)
    );

    CREATE INDEX IF NOT EXISTS idx_country ON processed_emissions(country_code);
    CREATE INDEX IF NOT EXISTS idx_category ON processed_emissions(category);
    CREATE INDEX IF NOT EXISTS idx_year ON processed_emissions(year);
    CREATE INDEX IF NOT EXISTS idx_org ON processed_emissions(source_org);
    CREATE INDEX IF NOT EXISTS idx_scope ON processed_emissions(scope);
    CREATE INDEX IF NOT EXISTS idx_factor_id ON processed_emissions(factor_id);
    CREATE INDEX IF NOT EXISTS idx_level1 ON processed_emissions(level1);
    CREATE INDEX IF NOT EXISTS idx_history_uid ON emission_history(uid);
    CREATE INDEX IF NOT EXISTS idx_history_year ON emission_history(year);

    -- 수동 DB Factor-id ↔ 자동 수집 UID 매핑 테이블
    CREATE TABLE IF NOT EXISTS factor_id_mapping (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        auto_uid TEXT NOT NULL,
        manual_factor_id TEXT,
        manual_factor_id_normalized TEXT,
        country_code_alpha2 TEXT,
        country_code_alpha3 TEXT,
        scope TEXT,
        category_code TEXT,
        unit_code TEXT,
        unit_name TEXT,
        gas_type INTEGER,
        gas_name TEXT,
        mapping_status TEXT DEFAULT 'auto',
        confidence REAL DEFAULT 1.0,
        mapped_at TEXT DEFAULT (datetime('now')),
        notes TEXT,
        UNIQUE(auto_uid, manual_factor_id)
    );

    CREATE INDEX IF NOT EXISTS idx_mapping_auto ON factor_id_mapping(auto_uid);
    CREATE INDEX IF NOT EXISTS idx_mapping_manual ON factor_id_mapping(manual_factor_id);
    CREATE INDEX IF NOT EXISTS idx_mapping_normalized ON factor_id_mapping(manual_factor_id_normalized);

    -- 국가코드 변환표 (alpha-2 ↔ alpha-3)
    CREATE TABLE IF NOT EXISTS country_code_mapping (
        alpha2 TEXT PRIMARY KEY,
        alpha3 TEXT NOT NULL,
        country_name_en TEXT,
        country_name_ko TEXT
    );

    -- 수동 DB 단위코드 해석표
    CREATE TABLE IF NOT EXISTS unit_code_mapping (
        unit_code TEXT PRIMARY KEY,
        unit_name TEXT NOT NULL,
        unit_standard TEXT,
        notes TEXT
    );
    """

    # 초기 데이터 (국가코드 + 단위코드 매핑)
    _COUNTRY_CODES = [
        ("GB", "GBR", "United Kingdom", "영국"),
        ("US", "USA", "United States", "미국"),
        ("KR", "KOR", "South Korea", "대한민국"),
        ("JP", "JPN", "Japan", "일본"),
        ("DE", "DEU", "Germany", "독일"),
        ("FR", "FRA", "France", "프랑스"),
        ("AU", "AUS", "Australia", "호주"),
        ("NZ", "NZL", "New Zealand", "뉴질랜드"),
        ("CN", "CHN", "China", "중국"),
        ("BR", "BRA", "Brazil", "브라질"),
        ("VN", "VNM", "Vietnam", "베트남"),
        ("ID", "IDN", "Indonesia", "인도네시아"),
        ("MX", "MEX", "Mexico", "멕시코"),
        ("CR", "CRI", "Costa Rica", "코스타리카"),
        ("PE", "PER", "Peru", "페루"),
        ("TW", "TWN", "Taiwan", "대만"),
        ("TH", "THA", "Thailand", "태국"),
        ("IN", "IND", "India", "인도"),
        ("INTL", "GLO", "Global", "글로벌"),
    ]

    _UNIT_CODES = [
        ("10", "default", "", "국가별 기본 단위"),
        ("11", "tonne", "kgCO2e/ton", "톤"),
        ("20", "litre", "kgCO2e/L", "리터"),
        ("22", "GJ", "kgCO2e/GJ", "호주 에너지 단위"),
        ("23", "unit_JP_KR", "", "일본/한국 특수 단위"),
        ("26", "gallon", "kgCO2e/gallon", "갤런 (미국)"),
        ("30", "energy", "kgCO2e/GJ", "에너지 단위"),
        ("33", "kWh_net", "kgCO2e/kWh", "kWh 순발열량"),
        ("34", "kWh_gross", "kgCO2e/kWh", "kWh 총발열량"),
        ("39", "mmBtu", "kgCO2/mmBtu", "백만 BTU (미국)"),
        ("9A", "EPD_unit", "kgCO2e/unit", "한국 EPD 특수단위"),
    ]

    # DB에 저장할 컬럼 목록
    VALID_COLUMNS = {
        "uid", "factor_id", "country_code", "source_org", "source_type",
        "data_reliability_score",
        "scope", "level1", "level2", "level3", "category",
        "item_name_original", "item_name_standard",
        "standard_value", "standard_unit",
        "co2_value", "ch4_value", "n2o_value",
        "co2_unit", "ch4_unit", "n2o_unit",
        "gwp_version", "value_sar", "value_tar", "value_ar4", "value_ar5", "value_ar6",
        "year", "language_code", "raw_file_path", "mapping_log",
        "conversion_factor", "extraction_method", "table_context",
        "last_checked_at", "created_at",
    }

    # 변경 감지 대상 필드 및 change_type 매핑
    _DIFF_FIELDS = {
        "value_change": [
            "standard_value", "co2_value", "ch4_value", "n2o_value",
            "value_sar", "value_tar", "value_ar4", "value_ar5", "value_ar6",
            "conversion_factor",
        ],
        "unit_change": [
            "standard_unit", "co2_unit", "ch4_unit", "n2o_unit",
        ],
        "category_change": [
            "category", "scope", "level1", "level2", "level3",
            "item_name_standard", "gwp_version",
        ],
    }

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """DB 초기화 및 테이블 생성"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript(self.SCHEMA)
            # 국가코드/단위코드 초기 데이터 삽입
            self._seed_mapping_tables(conn)
        # 기존 DB 마이그레이션
        self._migrate_schema()
        logger.info(f"[DB] 초기화 완료: {self.db_path}")

    def _seed_mapping_tables(self, conn):
        """국가코드/단위코드 매핑 초기 데이터 삽입"""
        for row in self._COUNTRY_CODES:
            conn.execute(
                "INSERT OR IGNORE INTO country_code_mapping (alpha2, alpha3, country_name_en, country_name_ko) VALUES (?, ?, ?, ?)",
                row,
            )
        for row in self._UNIT_CODES:
            conn.execute(
                "INSERT OR IGNORE INTO unit_code_mapping (unit_code, unit_name, unit_standard, notes) VALUES (?, ?, ?, ?)",
                row,
            )

    def _migrate_schema(self):
        """기존 DB에 새 컬럼 추가 (마이그레이션)

        이미 존재하는 컬럼은 무시하므로 비파괴적 마이그레이션을 보장한다.
        """
        # processed_emissions 테이블에 추가해야 할 컬럼 정의
        new_columns = [
            ("factor_id", "TEXT"),
            ("scope", "TEXT"),
            ("level1", "TEXT"),
            ("level2", "TEXT"),
            ("level3", "TEXT"),
            ("co2_value", "REAL"),
            ("ch4_value", "REAL"),
            ("n2o_value", "REAL"),
            ("co2_unit", "TEXT"),
            ("ch4_unit", "TEXT"),
            ("n2o_unit", "TEXT"),
            ("gwp_version", "TEXT DEFAULT 'AR6'"),
            ("value_sar", "REAL"),
            ("value_tar", "REAL"),
            ("value_ar4", "REAL"),
            ("value_ar5", "REAL"),
            ("value_ar6", "REAL"),
        ]

        with sqlite3.connect(str(self.db_path)) as conn:
            # 현재 컬럼 목록 조회
            cursor = conn.execute("PRAGMA table_info(processed_emissions)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            for col_name, col_type in new_columns:
                # col_name에서 실제 이름만 추출 (DEFAULT 절 제거)
                pure_name = col_name.split()[0] if " " in col_name else col_name
                if pure_name not in existing_cols:
                    try:
                        conn.execute(
                            f"ALTER TABLE processed_emissions ADD COLUMN {col_name} {col_type}"
                        )
                        logger.info(f"[DB] 마이그레이션: 컬럼 추가 {col_name} {col_type}")
                    except sqlite3.OperationalError:
                        # 이미 존재하는 경우 무시
                        pass

            # emission_history 테이블은 CREATE TABLE IF NOT EXISTS로 이미 처리됨
            # 새 인덱스도 CREATE INDEX IF NOT EXISTS로 이미 처리됨

    @staticmethod
    def generate_uid(country_code: str, org: str, item: str, year: int,
                     scope: str = None, unit: str = None) -> str:
        """UID 생성: KR-GIR-scope1-electricity-kgco2e_kwh-2022

        scope 및 unit 정보를 포함하여 고유한 식별자를 생성한다.
        unit 포함으로 동일 항목의 다중 단위(per tonne, per litre) thrashing 방지.
        """
        item_clean = item.lower().replace(" ", "_").replace("/", "_")[:80]
        parts = [country_code, org]
        if scope:
            parts.append(scope.lower().replace(" ", "_"))
        parts.append(item_clean)
        if unit:
            unit_clean = unit.lower().replace("/", "_").replace(" ", "")[:20]
            parts.append(unit_clean)
        parts.append(str(year) if year else "0")
        return "-".join(parts)

    def _detect_changes(self, existing_dict: dict, record: dict) -> tuple:
        """기존 레코드와 새 레코드 사이의 변경사항을 감지한다.

        Returns:
            (diff, change_types): diff는 {field: {old, new}} 딕셔너리,
                                  change_types는 감지된 변경 유형 집합
        """
        diff = {}
        change_types = set()

        for change_type, fields in self._DIFF_FIELDS.items():
            for key in fields:
                old_val = existing_dict.get(key)
                new_val = record.get(key)
                if new_val is not None and str(old_val) != str(new_val):
                    diff[key] = {"old": old_val, "new": new_val}
                    change_types.add(change_type)

        return diff, change_types

    def _save_to_history(self, conn, existing_dict: dict, diff: dict,
                         change_types: set):
        """변경 전 레코드를 emission_history에 저장한다."""
        # 대표 previous_value 결정 (standard_value 우선)
        previous_value = None
        if "standard_value" in diff:
            previous_value = diff["standard_value"]["old"]
        elif diff:
            first_key = next(iter(diff))
            old_val = diff[first_key]["old"]
            if isinstance(old_val, (int, float)):
                previous_value = old_val

        change_type_str = ",".join(sorted(change_types))

        conn.execute(
            """INSERT INTO emission_history (
                uid, factor_id, country_code, source_org,
                scope, level1, level2, level3, category,
                item_name_standard, standard_value, standard_unit,
                co2_value, ch4_value, n2o_value,
                gwp_version, value_ar5, value_ar6,
                year, change_type, previous_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                existing_dict.get("uid"),
                existing_dict.get("factor_id"),
                existing_dict.get("country_code"),
                existing_dict.get("source_org"),
                existing_dict.get("scope"),
                existing_dict.get("level1"),
                existing_dict.get("level2"),
                existing_dict.get("level3"),
                existing_dict.get("category"),
                existing_dict.get("item_name_standard"),
                existing_dict.get("standard_value"),
                existing_dict.get("standard_unit"),
                existing_dict.get("co2_value"),
                existing_dict.get("ch4_value"),
                existing_dict.get("n2o_value"),
                existing_dict.get("gwp_version"),
                existing_dict.get("value_ar5"),
                existing_dict.get("value_ar6"),
                existing_dict.get("year"),
                change_type_str,
                previous_value,
            ),
        )

    def upsert(self, record: dict) -> dict:
        """
        레코드 upsert (삽입 또는 업데이트)
        반환: {"action": "insert"|"update"|"unchanged", "uid": str, "diff": dict|None}
        """
        uid = record.get("uid") or self.generate_uid(
            record["country_code"],
            record["source_org"],
            record.get("item_name_original", record.get("item_name_standard", "")),
            record.get("year", 0),
            scope=record.get("scope"),
            unit=record.get("standard_unit"),
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
                existing_dict = dict(existing)
                diff, change_types = self._detect_changes(existing_dict, record)

                if diff:
                    # 변경 전 레코드를 이력 테이블에 저장
                    self._save_to_history(conn, existing_dict, diff, change_types)

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

    def query_by_scope(self, scope: str) -> list:
        """Scope별 배출계수 조회"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM processed_emissions WHERE scope = ? ORDER BY level1, level2, year DESC",
                (scope,),
            ).fetchall()
            return [dict(r) for r in rows]

    def query_by_hierarchy(self, scope: str = None, level1: str = None,
                           level2: str = None) -> list:
        """계층 구조로 배출계수 조회

        scope, level1, level2를 조합하여 계층적으로 필터링한다.
        None인 파라미터는 필터에서 제외된다.
        """
        conditions = []
        params = []

        if scope is not None:
            conditions.append("scope = ?")
            params.append(scope)
        if level1 is not None:
            conditions.append("level1 = ?")
            params.append(level1)
        if level2 is not None:
            conditions.append("level2 = ?")
            params.append(level2)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM processed_emissions WHERE {where_clause} "
                f"ORDER BY scope, level1, level2, level3, year DESC",
                params,
            ).fetchall()
            return [dict(r) for r in rows]

    def query_history(self, uid: str) -> list:
        """특정 항목의 변경 이력 조회"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM emission_history WHERE uid = ? ORDER BY changed_at DESC",
                (uid,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """DB 통계"""
        with sqlite3.connect(str(self.db_path)) as conn:
            total = conn.execute("SELECT COUNT(*) FROM processed_emissions").fetchone()[0]
            countries = conn.execute("SELECT COUNT(DISTINCT country_code) FROM processed_emissions").fetchone()[0]
            orgs = conn.execute("SELECT COUNT(DISTINCT source_org) FROM processed_emissions").fetchone()[0]
            categories = conn.execute("SELECT COUNT(DISTINCT category) FROM processed_emissions").fetchone()[0]

            # Scope별 통계
            scope_rows = conn.execute(
                "SELECT scope, COUNT(*) as cnt FROM processed_emissions "
                "WHERE scope IS NOT NULL GROUP BY scope ORDER BY scope"
            ).fetchall()
            scope_counts = {row[0]: row[1] for row in scope_rows}

            # 이력 건수
            history_count = conn.execute("SELECT COUNT(*) FROM emission_history").fetchone()[0]

            return {
                "total_records": total,
                "countries": countries,
                "orgs": orgs,
                "categories": categories,
                "scope_counts": scope_counts,
                "history_records": history_count,
            }

    # ── 매핑 테이블 메서드 ──

    def add_factor_mapping(self, auto_uid: str, manual_factor_id: str,
                           gas_type: int = 0, gas_name: str = "Total",
                           unit_code: str = "", unit_name: str = "",
                           mapping_status: str = "auto", confidence: float = 1.0,
                           notes: str = "") -> bool:
        """수동 Factor-id ↔ 자동 UID 매핑 추가"""
        # 정규화: 공백 제거
        normalized = manual_factor_id.replace(" ", "")

        # 국가코드 추출 (alpha-3 → alpha-2)
        parts = manual_factor_id.split("-")
        alpha3 = parts[0] if parts else ""
        scope_str = parts[1] if len(parts) > 1 else ""
        scope = {"S1": "Scope1", "S2": "Scope2", "S3": "Scope3"}.get(scope_str, "")

        with sqlite3.connect(str(self.db_path)) as conn:
            # alpha3 → alpha2 변환
            row = conn.execute(
                "SELECT alpha2 FROM country_code_mapping WHERE alpha3 = ?", (alpha3,)
            ).fetchone()
            alpha2 = row[0] if row else ""

            # 카테고리 코드 추출 (C- 이후 단위코드 전까지)
            category_code = ""
            if len(parts) > 2:
                # "C-11 11 11 00" 또는 "C-3A 11 11 11" 부분
                mid = "-".join(parts[2:-1]) if len(parts) > 3 else parts[2]
                if mid.startswith("C-"):
                    category_code = mid[2:]
                elif mid.startswith("C"):
                    category_code = mid[1:]

            try:
                conn.execute(
                    """INSERT OR REPLACE INTO factor_id_mapping
                    (auto_uid, manual_factor_id, manual_factor_id_normalized,
                     country_code_alpha2, country_code_alpha3, scope,
                     category_code, unit_code, unit_name, gas_type, gas_name,
                     mapping_status, confidence, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (auto_uid, manual_factor_id, normalized,
                     alpha2, alpha3, scope,
                     category_code, unit_code, unit_name, gas_type, gas_name,
                     mapping_status, confidence, notes),
                )
                logger.info(f"[DB] 매핑 추가: {auto_uid} ↔ {manual_factor_id}")
                return True
            except Exception as e:
                logger.error(f"[DB] 매핑 추가 실패: {e}")
                return False

    def query_mapping_by_auto_uid(self, auto_uid: str) -> list:
        """자동 UID로 수동 Factor-id 매핑 조회"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM factor_id_mapping WHERE auto_uid = ?", (auto_uid,)
            ).fetchall()
            return [dict(r) for r in rows]

    def query_mapping_by_manual_id(self, manual_factor_id: str) -> list:
        """수동 Factor-id로 자동 UID 매핑 조회"""
        normalized = manual_factor_id.replace(" ", "")
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM factor_id_mapping WHERE manual_factor_id = ? OR manual_factor_id_normalized = ?",
                (manual_factor_id, normalized),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_country_code(self, alpha2: str = None, alpha3: str = None) -> dict:
        """국가코드 변환 (alpha-2 ↔ alpha-3)"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if alpha2:
                row = conn.execute(
                    "SELECT * FROM country_code_mapping WHERE alpha2 = ?", (alpha2,)
                ).fetchone()
            elif alpha3:
                row = conn.execute(
                    "SELECT * FROM country_code_mapping WHERE alpha3 = ?", (alpha3,)
                ).fetchone()
            else:
                return {}
            return dict(row) if row else {}

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
