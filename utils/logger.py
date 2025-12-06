import logging
import sys
import os
from datetime import datetime

def setup_logger(name: str = "CCB_v2") -> logging.Logger:
    """
    프로젝트 전역 로거 설정 (Design Doc 3.1)
    - Console Output (StreamHandler): 실시간 모니터링용
    - File Output (FileHandler): logs/debug.log 에 기록
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 중복 핸들러 방지 (이미 설정된 경우 반환)
    if logger.handlers:
        return logger

    # 로그 포맷 정의
    # 예: [10:23:45][INFO] Parsing file: utils/logger.py
    formatter = logging.Formatter(
        '[%(asctime)s][%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )

    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)  # 콘솔에는 INFO 이상만 출력 (너무 시끄럽지 않게)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. File Handler
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # 매번 실행 시 로그 파일 초기화 혹은 append 모드 선택 (여기서는 append)
    file_handler = logging.FileHandler(
        os.path.join(log_dir, "debug.log"), 
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)    # 파일에는 모든 상세 로그 기록
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# 싱글톤처럼 쓰기 위해 미리 인스턴스 생성
logger = setup_logger()