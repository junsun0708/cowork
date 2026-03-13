"""
NanoClaw Fetcher Agent
- HTML, PDF, API 데이터 수집
- Raw 데이터 저장 (원본 무수정)
- 구조 변경 감지
"""
import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import (
    RAW_DIR, ALERTS_DIR, TODAY_COMPACT, PDF_KEYWORDS, TABLE_KEYWORDS
)

logger = logging.getLogger("nanoclaw.fetcher")

# User-Agent 설정
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json,application/pdf",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,ja;q=0.7",
}


class Fetcher:
    """웹 페이지 및 PDF 데이터 수집기"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_html(self, url: str, timeout: int = 30) -> dict:
        """HTML 페이지 수집"""
        try:
            resp = self.session.get(url, timeout=timeout, allow_redirects=True, verify=True)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # 테이블 추출
            tables = []
            for table in soup.find_all("table"):
                rows = []
                for tr in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if cells:
                        rows.append(cells)
                if rows:
                    tables.append(rows)

            # 본문 텍스트
            text_content = soup.get_text(separator="\n", strip=True)

            return {
                "success": True,
                "url": url,
                "status_code": resp.status_code,
                "content_type": resp.headers.get("Content-Type", ""),
                "text": text_content[:50000],  # 50K 제한
                "tables": tables,
                "html_hash": hashlib.md5(resp.text.encode()).hexdigest(),
            }
        except Exception as e:
            logger.error(f"[Fetcher] HTML 수집 실패: {url} | {e}")
            return {"success": False, "url": url, "error": str(e)}

    def fetch_pdf(self, url: str, save_dir: Path = None, timeout: int = 60) -> dict:
        """PDF 다운로드 및 텍스트/표 추출"""
        try:
            resp = self.session.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()

            # PDF 바이너리 저장
            if save_dir:
                save_dir.mkdir(parents=True, exist_ok=True)
                filename = urlparse(url).path.split("/")[-1] or "document.pdf"
                if not filename.endswith(".pdf"):
                    filename += ".pdf"
                pdf_path = save_dir / filename
                with open(pdf_path, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                logger.info(f"[Fetcher] PDF 저장: {pdf_path}")
            else:
                # 임시 저장
                import tempfile
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                for chunk in resp.iter_content(8192):
                    tmp.write(chunk)
                tmp.close()
                pdf_path = Path(tmp.name)

            # 텍스트 및 테이블 추출
            extracted = self._extract_pdf(pdf_path)
            extracted["url"] = url
            extracted["pdf_path"] = str(pdf_path)
            return extracted

        except Exception as e:
            logger.error(f"[Fetcher] PDF 수집 실패: {url} | {e}")
            return {"success": False, "url": url, "error": str(e)}

    def _extract_pdf(self, pdf_path: Path) -> dict:
        """PDF에서 텍스트 및 테이블 추출"""
        result = {"success": True, "text": "", "tables": []}

        try:
            import pdfplumber
            with pdfplumber.open(str(pdf_path)) as pdf:
                texts = []
                tables = []
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    texts.append(page_text)

                    page_tables = page.extract_tables() or []
                    for t in page_tables:
                        if t and len(t) > 1:
                            tables.append(t)

                result["text"] = "\n".join(texts)[:100000]
                result["tables"] = tables
        except ImportError:
            logger.warning("[Fetcher] pdfplumber 미설치, 기본 텍스트 추출 시도")
        except Exception as e:
            logger.error(f"[Fetcher] PDF 추출 오류: {e}")
            result["error"] = str(e)

        return result

    def fetch_excel(self, url: str, save_dir: Path = None, timeout: int = 60) -> dict:
        """Excel 파일 다운로드 및 데이터 추출"""
        try:
            resp = self.session.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()

            import tempfile
            suffix = ".xlsx" if ".xlsx" in url.lower() else ".xls"
            if save_dir:
                save_dir.mkdir(parents=True, exist_ok=True)
                filename = url.split("/")[-1] or f"data{suffix}"
                xlsx_path = save_dir / filename
            else:
                tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
                xlsx_path = Path(tmp.name)
                tmp.close()

            with open(xlsx_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)

            logger.info(f"[Fetcher] Excel 다운로드: {xlsx_path}")

            # pandas로 파싱
            import pandas as pd
            tables = []
            text_parts = []
            try:
                xls = pd.ExcelFile(str(xlsx_path))
                for sheet_name in xls.sheet_names[:100]:  # 최대 100시트 (DEFRA 80+시트 대응)
                    df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
                    if len(df) > 0:
                        # DataFrame → 리스트 변환 (header=None이므로 모든 행이 데이터)
                        rows = []
                        for _, row in df.head(2000).iterrows():  # 시트당 최대 2000행
                            rows.append([str(v) for v in row.tolist()])
                        tables.append(rows)
                        text_parts.append(f"[Sheet: {sheet_name}]\n{df.head(30).to_string()}")
            except Exception as e:
                logger.error(f"[Fetcher] Excel 파싱 오류: {e}")

            return {
                "success": True,
                "url": url,
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "text": "\n\n".join(text_parts)[:50000],
                "tables": tables,
                "xlsx_path": str(xlsx_path),
            }
        except Exception as e:
            logger.error(f"[Fetcher] Excel 수집 실패: {url} | {e}")
            return {"success": False, "url": url, "error": str(e)}

    def fetch_csv(self, url: str, timeout: int = 120) -> dict:
        """CSV 파일 다운로드 및 파싱"""
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()

            import pandas as pd
            from io import StringIO

            text = resp.text
            df = pd.read_csv(StringIO(text), nrows=50000)  # 대규모 CSV 지원 (Ember 등)

            header = [str(c) for c in df.columns.tolist()]
            rows = [header]
            for _, row in df.iterrows():
                rows.append([str(v) for v in row.tolist()])

            return {
                "success": True,
                "url": url,
                "content_type": "text/csv",
                "text": df.head(50).to_string()[:50000],
                "tables": [rows],
            }
        except Exception as e:
            logger.error(f"[Fetcher] CSV 수집 실패: {url} | {e}")
            return {"success": False, "url": url, "error": str(e)}

    def _guess_format_from_url(self, url: str) -> str:
        """URL 경로에서 파일 포맷을 추측. 파일 확장자가 없으면 빈 문자열 반환."""
        path = url.lower().split("?")[0].split("#")[0]
        if path.endswith((".xlsx", ".xls")):
            return "xlsx"
        elif path.endswith(".csv"):
            return "csv"
        elif path.endswith(".pdf"):
            return "pdf"
        return ""

    def fetch_auto(self, url: str, data_format: str = "html", save_dir: Path = None) -> dict:
        """URL과 포맷에 따라 자동으로 적절한 메서드 선택

        판별 우선순위: URL 확장자 > Content-Type > data_format 설정
        (소스 레벨 data_format이 모든 URL에 동일 적용되는 문제 방지)
        """
        # 1순위: URL 확장자로 판별
        url_format = self._guess_format_from_url(url)
        if url_format:
            fmt = url_format
        elif data_format == "json":
            fmt = "json"
        elif data_format != "html":
            # 2순위: data_format이 html이 아닌 경우, HEAD 요청으로 Content-Type 확인
            fmt = self._detect_content_type(url, data_format)
        else:
            fmt = "html"

        if fmt == "xlsx":
            return self.fetch_excel(url, save_dir)
        elif fmt == "csv":
            return self.fetch_csv(url)
        elif fmt == "pdf":
            return self.fetch_pdf(url, save_dir)
        elif fmt == "json":
            return self.fetch_api(url)
        else:
            return self.fetch_html(url)

    def _detect_content_type(self, url: str, fallback: str) -> str:
        """HEAD 요청으로 Content-Type을 확인하여 실제 포맷 판별"""
        try:
            resp = self.session.head(url, timeout=10, allow_redirects=True)
            ct = resp.headers.get("Content-Type", "").lower()
            if "spreadsheet" in ct or "excel" in ct:
                return "xlsx"
            elif "csv" in ct:
                return "csv"
            elif "pdf" in ct:
                return "pdf"
            elif "html" in ct or "text" in ct:
                return "html"
        except Exception:
            pass
        return fallback

    def fetch_api(self, url: str, params: dict = None, timeout: int = 30) -> dict:
        """API JSON 데이터 수집 — 결과를 tables/text 형태로도 변환"""
        try:
            resp = self.session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()

            data = resp.json()

            # JSON 데이터를 tables 형태로 변환 (extractor 호환)
            tables = []
            text_parts = []
            if isinstance(data, list) and len(data) > 0:
                # 리스트 형태: 각 항목을 테이블 행으로 변환
                if isinstance(data[0], dict):
                    headers = list(data[0].keys())
                    rows = [headers]
                    for item in data[:2000]:
                        rows.append([str(item.get(k, "")) for k in headers])
                    tables.append(rows)
                    text_parts.append(str(data[:10]))
            elif isinstance(data, dict):
                text_parts.append(json.dumps(data, ensure_ascii=False)[:50000])

            return {
                "success": True,
                "url": url,
                "status_code": resp.status_code,
                "content_type": "application/json",
                "data": data,
                "tables": tables,
                "text": "\n".join(text_parts)[:50000],
            }
        except Exception as e:
            logger.error(f"[Fetcher] API 수집 실패: {url} | {e}")
            return {"success": False, "url": url, "error": str(e)}

    def save_raw(
        self,
        country_code: str,
        source_org: str,
        category: str,
        data: dict,
        source_url: str = "",
        source_type: str = "Government",
        reliability_score: int = 5,
        language_code: str = "en",
        version: int = 1,
    ) -> str:
        """
        Raw 데이터를 JSON으로 저장
        경로: raw/[국가코드]/[기관명]/[수집년도]/YYYYMMDD_[카테고리]_v[버전].json
        """
        year = datetime.now().strftime("%Y")
        save_dir = RAW_DIR / country_code / source_org / year
        save_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{TODAY_COMPACT}_{category}_v{version}.json"
        filepath = save_dir / filename

        # 동일 파일 존재 시 버전 증가
        while filepath.exists():
            version += 1
            filename = f"{TODAY_COMPACT}_{category}_v{version}.json"
            filepath = save_dir / filename

        raw_record = {
            "source_url": source_url,
            "country_code": country_code,
            "source_org": source_org,
            "source_type": source_type,
            "data_reliability_score": reliability_score,
            "collected_at": datetime.now().isoformat(),
            "language_code": language_code,
            "category": category,
            "raw_content_type": data.get("content_type", "text/html"),
            "raw_text": data.get("text", ""),
            "raw_table": data.get("tables", []),
            "raw_binary_ref": data.get("pdf_path", ""),
            "notes": data.get("notes", ""),
        }

        filepath.write_text(
            json.dumps(raw_record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[Fetcher] Raw 저장: {filepath}")
        return str(filepath)

    def detect_structure_change(
        self, url: str, previous_hash: str, current_hash: str
    ) -> bool:
        """HTML 구조 변경 감지"""
        if previous_hash and previous_hash != current_hash:
            self._write_alert(url, previous_hash, current_hash)
            return True
        return False

    def _write_alert(self, url: str, old_hash: str, new_hash: str):
        """구조 변경 알림 파일 생성"""
        ALERTS_DIR.mkdir(parents=True, exist_ok=True)
        alert_path = ALERTS_DIR / f"structure_change_{TODAY_COMPACT}.md"

        content = (
            f"# 구조 변경 감지\n\n"
            f"- **URL**: {url}\n"
            f"- **이전 해시**: {old_hash}\n"
            f"- **현재 해시**: {new_hash}\n"
            f"- **감지 시각**: {datetime.now().isoformat()}\n"
            f"- **조치**: 파싱 프로필 업데이트 필요\n"
        )

        with open(alert_path, "a", encoding="utf-8") as f:
            f.write(content + "\n---\n\n")

        logger.warning(f"[Fetcher] 구조 변경 감지: {url}")
