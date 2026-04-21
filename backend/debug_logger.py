"""
debug_logger.py - 상세 디버깅 로그 출력

사용법:
    import logging
    from backend.debug_logger import setup_logging
    
    logger = setup_logging()
    logger.info("메시지")
    logger.debug("디버그 정보")
"""

import logging
import sys
from datetime import datetime


def setup_logging():
    """상세 디버깅 로그 설정"""
    
    # 로거 생성
    logger = logging.getLogger("multi_agent")
    logger.setLevel(logging.INFO)
    
    # 이미 핸들러가 있으면 추가하지 않음
    if logger.handlers:
        return logger
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # 포맷
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    return logger


# 글로벌 로거 인스턴스
logger = setup_logging()
