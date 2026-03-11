"""
NanoClaw 글로벌 배출계수 수집 에이전트 - 설정 파일
"""
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# ── .env 파일 자동 로드 ──
LOCAL_ROOT = Path(__file__).parent.parent
_env_path = LOCAL_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)

# ── 기본 경로 설정 ──
# 로컬 개발 시 이 경로를 사용, 서버 배포 시 SERVER_ROOT로 변경
SERVER_ROOT = Path.home() / "projects" / "cowork" / "nanoclaw"

# 환경변수로 선택 가능 (서버 배포 시: NANOCLAW_ROOT=~/projects/cowork/nanoclaw)
BASE_DIR = Path(os.getenv("NANOCLAW_ROOT", str(LOCAL_ROOT)))

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "storage" / "raw"
ALERTS_DIR = DATA_DIR / "alerts"
LOGS_DIR = BASE_DIR / "logs" / "prompts"
OUTPUT_DIR = BASE_DIR / "output"
SOURCE_REGISTRY_DIR = BASE_DIR / "source_registry"
PARSING_PROFILES_DIR = BASE_DIR / "parsing_profiles"
# DB는 세션 디렉토리(쓰기 가능)에 저장, 서버에서는 BASE_DIR 사용
_SESSION_DIR = Path(os.getenv("NANOCLAW_SESSION_DIR", "/sessions/clever-zen-hypatia"))
DB_PATH = Path(os.getenv("NANOCLAW_DB_PATH", str(_SESSION_DIR / "nanoclaw.db")))
# 서버 배포 시: NANOCLAW_DB_PATH=~/projects/cowork/nanoclaw/data/nanoclaw.db

# ── Slack 설정 ──
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "C0AKQDRG7EH")  # #cowork
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

# ── 날짜 ──
TODAY = datetime.now().strftime("%Y-%m-%d")
TODAY_COMPACT = datetime.now().strftime("%Y%m%d")

# ── 데이터 신뢰도 점수 ──
RELIABILITY_SCORES = {
    "Government": 5,
    "International": 4,
    "Research": 3,
    "NGO": 2,
    "Private": 1,
}

# ── source_type ──
SOURCE_TYPES = ["Government", "International", "Research", "NGO", "Private"]

# ── 표준 단위 ──
STANDARD_UNITS = [
    "kgCO2e/kWh",
    "kgCO2e/L",
    "kgCO2e/km",
    "kgCO2e/ton",
    "kgCO2e/m3",
    "kgCO2e/GJ",
]

# ── 택소노미(Taxonomy) ──
TAXONOMY = {
    "Energy": [
        "electricity", "natural_gas", "coal", "diesel", "gasoline",
        "lpg", "fuel_oil", "renewable_energy",
    ],
    "Transportation": [
        "road_transport", "aviation", "marine_transport", "rail_transport",
    ],
    "Industry": [
        "cement", "steel", "chemical", "aluminum", "fertilizer",
    ],
    "Waste": [
        "landfill", "wastewater", "recycling",
    ],
    "Agriculture": [
        "livestock", "rice", "fertilizer_use",
    ],
}

# ── PDF 탐지 키워드 ──
PDF_KEYWORDS = [
    "Emission Factor", "CO2 factor", "carbon intensity",
    "kg CO2", "GHG factor", "배출계수", "排出係数",
    "facteur d'emission", "Emissionsfaktor",
]

# ── 표 구조 탐색 키워드 ──
TABLE_KEYWORDS = [
    "Activity", "Fuel", "Emission Factor", "Unit", "Year", "Source",
    "Category", "Value", "GHG", "CO2", "CH4", "N2O",
]

# ── 대상 국가 목록 ──
TARGET_COUNTRIES = {
    "KR": "대한민국",
    "JP": "일본",
    "US": "미국",
    "DE": "독일",
    "FR": "프랑스",
    "GB": "영국",
    "AU": "호주",
    "NZ": "뉴질랜드",
    "CN": "중국",
    "BR": "브라질",
}
