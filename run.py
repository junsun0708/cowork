#!/usr/bin/env python3
"""
NanoClaw 실행 스크립트
사용법:
    python run.py                    # 전체 국가 수집
    python run.py KR                 # 한국만 수집
    python run.py KR US JP           # 특정 국가들 수집
    python run.py KR --org GIR       # 특정 기관만 수집
    python run.py --no-slack KR      # Slack 알림 없이 수집
"""
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator import main

if __name__ == "__main__":
    main()
