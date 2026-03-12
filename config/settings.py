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
BASE_DIR = Path(os.getenv("NANOCLAW_ROOT", str(LOCAL_ROOT)))

# ── 수집 데이터 저장 경로 (DB, 원본파일, 리포트 등 모든 수집 산출물) ──
# 환경변수 NANOCLAW_DATA_ROOT 로 자유롭게 변경 가능
_DEFAULT_DATA_ROOT = str(Path.home() / "projects" / "data" / "emission-factor")
DATA_ROOT = Path(os.getenv("NANOCLAW_DATA_ROOT", _DEFAULT_DATA_ROOT))

DATA_DIR = DATA_ROOT / "data"
RAW_DIR = DATA_ROOT / "raw"
ALERTS_DIR = DATA_ROOT / "alerts"
OUTPUT_DIR = DATA_ROOT / "output"
DB_PATH = Path(os.getenv("NANOCLAW_DB_PATH", str(DATA_ROOT / "nanoclaw.db")))

# ── 소스 코드 내부 경로 (소스 레지스트리, 파싱 프로필, 로그) ──
LOGS_DIR = BASE_DIR / "logs" / "prompts"
SOURCE_REGISTRY_DIR = BASE_DIR / "source_registry"
PARSING_PROFILES_DIR = BASE_DIR / "parsing_profiles"

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
    "kgCO2e/kWh", "kgCO2e/L", "kgCO2e/km", "kgCO2e/ton",
    "kgCO2e/m3", "kgCO2e/GJ", "kgCO2e/MJ", "kgCO2e/kg",
    "kgCO2e/unit", "kgCO2e/tkm", "kgCO2e/pkm",
    "kgCO2e/night", "kgCO2e/person", "kgCO2e/m2",
    "tCO2e/TJ",
]

# ── 4-level 택소노미 계층구조 (Scope → Level1 → Level2 → Level3) ──
TAXONOMY_HIERARCHY = {
    "Scope1": {
        "Fuels": {
            "Gaseous_fuels": ["natural_gas", "lpg", "propane", "butane", "cng", "lng", "biogas"],
            "Liquid_fuels": ["diesel", "gasoline", "kerosene", "jet_fuel", "fuel_oil", "biodiesel", "ethanol", "marine_fuel"],
            "Solid_fuels": ["coal", "anthracite", "bituminous_coal", "sub_bituminous_coal", "lignite", "coke", "peat", "wood_biomass"],
        },
        "Process_emissions": {
            "Industrial": ["cement", "steel", "aluminum", "chemical", "glass", "lime", "ammonia"],
            "Refrigerants": ["hfc", "pfc", "sf6", "refrigerant"],
        },
    },
    "Scope2": {
        "Electricity": {
            "Grid": ["electricity", "grid_electricity"],
            "Renewable": ["renewable_energy", "solar", "wind", "hydro", "geothermal"],
            "District": ["district_heating", "district_cooling", "steam"],
        },
    },
    "Scope3": {
        "Purchased_goods": {
            "Products": ["purchased_goods", "capital_goods", "packaging"],
            "EPD": ["epd_product", "pcf_product"],
            "Services": ["purchased_services", "cloud_services", "it_services"],
        },
        "Transportation": {
            "Road": ["road_transport", "truck", "bus", "car", "motorcycle"],
            "Aviation": ["aviation", "domestic_flight", "international_flight"],
            "Marine": ["marine_transport", "shipping", "ferry"],
            "Rail": ["rail_transport", "subway", "high_speed_rail"],
            "Logistics": ["logistics", "courier", "freight"],
        },
        "Waste": {
            "Disposal": ["landfill", "incineration", "open_burning"],
            "Treatment": ["wastewater", "composting", "anaerobic_digestion"],
            "Recovery": ["recycling", "material_recovery", "energy_recovery"],
        },
        "Employee_activities": {
            "Commuting": ["commuting", "telework"],
            "Travel": ["business_travel", "hotel_stay"],
            "Events": ["events", "conferences"],
        },
        "Supply_chain": {
            "Economic_model": ["spend_base", "eeio", "supply_chain"],
        },
        "Agriculture": {
            "Crops": ["rice", "fertilizer_use", "crop_residue"],
            "Livestock": ["livestock", "cattle", "swine", "poultry", "dairy"],
        },
    },
}

# ── 택소노미(Taxonomy) - 하위 호환용 flat dict (TAXONOMY_HIERARCHY에서 자동 생성) ──
TAXONOMY = {}
for _scope, _level1s in TAXONOMY_HIERARCHY.items():
    for _level1, _level2s in _level1s.items():
        _flat_items = []
        for _level2, _level3s in _level2s.items():
            _flat_items.extend(_level3s)
        TAXONOMY[_level1] = _flat_items

# ── GWP 100-year values by IPCC Assessment Report ──
GWP_VERSIONS = {
    "SAR": {"CO2": 1, "CH4": 21, "N2O": 310},        # IPCC 1995
    "TAR": {"CO2": 1, "CH4": 23, "N2O": 296},        # IPCC 2001
    "AR4": {"CO2": 1, "CH4": 25, "N2O": 298},        # IPCC 2007
    "AR5": {"CO2": 1, "CH4": 28, "N2O": 265},        # IPCC 2014
    "AR6": {"CO2": 1, "CH4": 27.9, "N2O": 273},      # IPCC 2021
}
DEFAULT_GWP_VERSION = "AR6"

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
    "KR": "대한민국", "JP": "일본", "US": "미국",
    "DE": "독일", "FR": "프랑스", "GB": "영국",
    "AU": "호주", "NZ": "뉴질랜드", "CN": "중국",
    "BR": "브라질", "VN": "베트남", "ID": "인도네시아",
    "MX": "멕시코", "CR": "코스타리카", "PE": "페루",
    "TW": "대만", "TH": "태국", "IN": "인도",
}

# ── 다국어 사전 ──
MULTILINGUAL_DICT = {
    "electricity": {"ko": "전력", "ja": "電力", "zh": "电力", "de": "Strom", "fr": "électricité", "es": "electricidad", "pt": "eletricidade", "th": "ไฟฟ้า"},
    "natural_gas": {"ko": "천연가스", "ja": "天然ガス", "zh": "天然气", "de": "Erdgas", "fr": "gaz naturel", "es": "gas natural", "pt": "gás natural", "th": "ก๊าซธรรมชาติ"},
    "coal": {"ko": "석탄", "ja": "石炭", "zh": "煤炭", "de": "Kohle", "fr": "charbon", "es": "carbón", "pt": "carvão", "th": "ถ่านหิน"},
    "diesel": {"ko": "경유", "ja": "軽油", "zh": "柴油", "de": "Diesel", "fr": "diesel", "es": "diésel", "pt": "diesel", "th": "ดีเซล"},
    "gasoline": {"ko": "휘발유", "ja": "ガソリン", "zh": "汽油", "de": "Benzin", "fr": "essence", "es": "gasolina", "pt": "gasolina", "th": "น้ำมันเบนซิน"},
    "lpg": {"ko": "액화석유가스", "ja": "LPG", "zh": "液化石油气", "de": "Flüssiggas", "fr": "GPL", "es": "GLP", "pt": "GLP", "th": "ก๊าซหุงต้ม"},
    "kerosene": {"ko": "등유", "ja": "灯油", "zh": "煤油", "de": "Kerosin", "fr": "kérosène", "es": "queroseno", "pt": "querosene", "th": "น้ำมันก๊าด"},
    "cement": {"ko": "시멘트", "ja": "セメント", "zh": "水泥", "de": "Zement", "fr": "ciment", "es": "cemento", "pt": "cimento", "th": "ซีเมนต์"},
    "steel": {"ko": "철강", "ja": "鉄鋼", "zh": "钢铁", "de": "Stahl", "fr": "acier", "es": "acero", "pt": "aço", "th": "เหล็กกล้า"},
    "aluminum": {"ko": "알루미늄", "ja": "アルミニウム", "zh": "铝", "de": "Aluminium", "fr": "aluminium", "es": "aluminio", "pt": "alumínio", "th": "อลูมิเนียม"},
    "fuel_oil": {"ko": "중유", "ja": "重油", "zh": "燃料油", "de": "Heizöl", "fr": "fioul", "es": "fueloil", "pt": "óleo combustível", "th": "น้ำมันเตา"},
    "jet_fuel": {"ko": "항공유", "ja": "ジェット燃料", "zh": "航空燃油", "de": "Kerosin", "fr": "kérosène", "es": "combustible de aviación", "pt": "querosene de aviação", "th": "เชื้อเพลิงเครื่องบิน"},
    "renewable_energy": {"ko": "재생에너지", "ja": "再生可能エネルギー", "zh": "可再生能源", "de": "erneuerbare Energie", "fr": "énergie renouvelable", "es": "energía renovable", "pt": "energia renovável", "th": "พลังงานทดแทน"},
    "road_transport": {"ko": "도로운송", "ja": "道路輸送", "zh": "公路运输", "de": "Straßentransport", "fr": "transport routier", "es": "transporte por carretera", "pt": "transporte rodoviário", "th": "การขนส่งทางถนน"},
    "aviation": {"ko": "항공", "ja": "航空", "zh": "航空", "de": "Luftfahrt", "fr": "aviation", "es": "aviación", "pt": "aviação", "th": "การบิน"},
    "marine_transport": {"ko": "해운", "ja": "海運", "zh": "海运", "de": "Seeverkehr", "fr": "transport maritime", "es": "transporte marítimo", "pt": "transporte marítimo", "th": "การขนส่งทางทะเล"},
    "rail_transport": {"ko": "철도", "ja": "鉄道", "zh": "铁路运输", "de": "Schienenverkehr", "fr": "transport ferroviaire", "es": "transporte ferroviario", "pt": "transporte ferroviário", "th": "การขนส่งทางราง"},
    "landfill": {"ko": "매립", "ja": "埋立", "zh": "填埋", "de": "Deponie", "fr": "enfouissement", "es": "vertedero", "pt": "aterro", "th": "ฝังกลบ"},
    "wastewater": {"ko": "폐수", "ja": "排水", "zh": "废水", "de": "Abwasser", "fr": "eaux usées", "es": "aguas residuales", "pt": "águas residuais", "th": "น้ำเสีย"},
    "recycling": {"ko": "재활용", "ja": "リサイクル", "zh": "回收利用", "de": "Recycling", "fr": "recyclage", "es": "reciclaje", "pt": "reciclagem", "th": "การรีไซเคิล"},
    "livestock": {"ko": "축산", "ja": "畜産", "zh": "畜牧", "de": "Viehzucht", "fr": "élevage", "es": "ganadería", "pt": "pecuária", "th": "ปศุสัตว์"},
    "rice": {"ko": "쌀", "ja": "米", "zh": "水稻", "de": "Reis", "fr": "riz", "es": "arroz", "pt": "arroz", "th": "ข้าว"},
    "fertilizer": {"ko": "비료", "ja": "肥料", "zh": "化肥", "de": "Düngemittel", "fr": "engrais", "es": "fertilizante", "pt": "fertilizante", "th": "ปุ๋ย"},
    "commuting": {"ko": "통근", "ja": "通勤", "zh": "通勤", "de": "Pendeln", "fr": "déplacement domicile-travail", "es": "desplazamiento", "pt": "deslocamento", "th": "การเดินทางไปทำงาน"},
    "business_travel": {"ko": "출장", "ja": "出張", "zh": "出差", "de": "Geschäftsreise", "fr": "voyage d'affaires", "es": "viaje de negocios", "pt": "viagem de negócios", "th": "การเดินทางเพื่อธุรกิจ"},
}


# ── 헬퍼 함수 ──

def get_scope_for_category(category: str) -> str:
    """카테고리로부터 Scope 자동 판별"""
    for scope, level1s in TAXONOMY_HIERARCHY.items():
        for level1, level2s in level1s.items():
            for level2, level3s in level2s.items():
                if category in level3s:
                    return scope
    return "Scope1"  # default


def get_hierarchy_for_category(category: str) -> dict:
    """카테고리로부터 전체 계층 정보 반환"""
    for scope, level1s in TAXONOMY_HIERARCHY.items():
        for level1, level2s in level1s.items():
            for level2, level3s in level2s.items():
                if category in level3s:
                    return {"scope": scope, "level1": level1, "level2": level2, "level3": category}
    return {"scope": "Scope1", "level1": "unknown", "level2": "unknown", "level3": category}


def generate_factor_id(country_code: str, scope: str, category_code: str, seq: int, version_year: int) -> str:
    """수동 DB 호환 Factor-id 생성
    형식: GBR-S1-C-11 11 11 00-11-0-2022
    """
    scope_num = {"Scope1": "S1", "Scope2": "S2", "Scope3": "S3"}.get(scope, "S1")
    return f"{country_code}-{scope_num}-C-{category_code}-{seq}-0-{version_year}"
