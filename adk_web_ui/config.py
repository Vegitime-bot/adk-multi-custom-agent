"""
ADK Web UI Configuration
환경 변수 또는 .env 파일에서 설정을 로드합니다.
"""

import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """애플리케이션 설정 클래스"""
    
    # ==========================================
    # Server Settings
    # ==========================================
    HOST: str = Field(default="0.0.0.0", description="서버 호스트")
    PORT: int = Field(default=8093, description="서버 포트")
    DEBUG: bool = Field(default=False, description="디버그 모드")
    LOG_LEVEL: str = Field(default="info", description="로그 레벨 (debug, info, warning, error)")
    
    # ==========================================
    # Database Settings (PostgreSQL)
    # ==========================================
    DB_HOST: str = Field(default="localhost", description="PostgreSQL 호스트")
    DB_PORT: str = Field(default="5432", description="PostgreSQL 포트")
    DB_NAME: str = Field(default="adk_chat", description="PostgreSQL 데이터베이스 이름")
    DB_USER: str = Field(default="postgres", description="PostgreSQL 사용자")
    DB_PASSWORD: str = Field(default="password", description="PostgreSQL 비밀번호")
    DB_POOL_SIZE: int = Field(default=10, description="DB 연결 풀 크기")
    DB_MAX_OVERFLOW: int = Field(default=20, description="DB 최대 오버플로우 연결 수")
    DB_POOL_TIMEOUT: int = Field(default=30, description="DB 연결 타임아웃 (초)")
    
    # ==========================================
    # Security Settings
    # ==========================================
    ADMIN_KNOX_IDS: str = Field(default="", description="관리자 Knox ID 목록 (쉼표 구분)")
    SESSION_SECRET: str = Field(default="your-secret-key-change-in-production", description="세션 암호화 키")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="액세스 토큰 만료 시간 (분)")
    
    # ==========================================
    # CORS Settings
    # ==========================================
    CORS_ALLOW_ORIGINS: str = Field(default="*", description="허용된 CORS 오리진 (쉼표 구분)")
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, description="CORS 자격 증명 허용")
    CORS_ALLOW_METHODS: str = Field(default="*", description="허용된 HTTP 메서드")
    CORS_ALLOW_HEADERS: str = Field(default="*", description="허용된 HTTP 헤더")
    
    # ==========================================
    # Feature Flags
    # ==========================================
    ENABLE_SSE: bool = Field(default=True, description="SSE 스트리밍 응답 활성화")
    ENABLE_MESSAGE_PAGINATION: bool = Field(default=True, description="메시지 페이지네이션 활성화")
    ENABLE_FILE_UPLOAD: bool = Field(default=True, description="파일 업로드 기능 활성화")
    MAX_UPLOAD_SIZE_MB: int = Field(default=10, description="최대 업로드 파일 크기 (MB)")
    ALLOWED_FILE_TYPES: str = Field(default="image/*,application/pdf,text/*", description="허용된 파일 타입")
    
    # ==========================================
    # Pagination Settings
    # ==========================================
    DEFAULT_PAGE_SIZE: int = Field(default=20, description="기본 페이지 크기")
    MAX_PAGE_SIZE: int = Field(default=100, description="최대 페이지 크기")
    MESSAGE_PAGE_SIZE: int = Field(default=50, description="메시지 페이지 크기")
    
    # ==========================================
    # Rate Limiting
    # ==========================================
    RATE_LIMIT_REQUESTS: int = Field(default=100, description="분당 최대 요청 수")
    RATE_LIMIT_WINDOW: int = Field(default=60, description="요청 윈도우 (초)")
    
    # ==========================================
    # Export Settings
    # ==========================================
    EXPORT_MAX_SESSIONS: int = Field(default=1000, description="최대 내보내기 세션 수")
    EXPORT_FORMATS: str = Field(default="json,txt,csv", description="지원되는 내보내기 형식")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
    
    # ==========================================
    # Helper Properties
    # ==========================================
    @property
    def db_url(self) -> str:
        """SQLAlchemy 형식의 데이터베이스 URL 생성"""
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def admin_knox_ids_list(self) -> List[str]:
        """관리자 Knox ID 목록을 리스트로 반환"""
        if not self.ADMIN_KNOX_IDS:
            return []
        return [id.strip() for id in self.ADMIN_KNOX_IDS.split(",") if id.strip()]
    
    @property
    def cors_origins_list(self) -> List[str]:
        """CORS 허용 오리진 목록을 리스트로 반환"""
        if self.CORS_ALLOW_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ALLOW_ORIGINS.split(",") if origin.strip()]
    
    @property
    def allowed_file_types_list(self) -> List[str]:
        """허용된 파일 타입 목록을 리스트로 반환"""
        return [ft.strip() for ft in self.ALLOWED_FILE_TYPES.split(",") if ft.strip()]
    
    @property
    def max_upload_size_bytes(self) -> int:
        """최대 업로드 크기를 바이트로 반환"""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


# 전역 설정 인스턴스 생성
settings = Settings()


# ==========================================
# Agent Configurations
# ==========================================
AGENT_CONFIGS = {
    "chatbot_company_adk": {
        "display_name": "회사 전체 지원",
        "description": "모든 사내 문의 처리",
        "level": 0,
        "sub_agents": ["chatbot_hr_adk", "chatbot_tech_adk"],
        "color": "#667eea"
    },
    "chatbot_hr_adk": {
        "display_name": "인사지원",
        "description": "인사 관련 문의",
        "level": 1,
        "parent": "chatbot_company_adk",
        "sub_agents": [],
        "color": "#f093fb"
    },
    "chatbot_tech_adk": {
        "display_name": "기술지원",
        "description": "기술 관련 문의",
        "level": 1,
        "parent": "chatbot_company_adk",
        "sub_agents": [],
        "color": "#4facfe"
    },
}

KEYWORD_DELEGATION = {
    "chatbot_company_adk": {
        "인사": "chatbot_hr_adk",
        "휴가": "chatbot_hr_adk",
        "급여": "chatbot_hr_adk",
        "복지": "chatbot_hr_adk",
        "채용": "chatbot_hr_adk",
        "기술": "chatbot_tech_adk",
        "개발": "chatbot_tech_adk",
        "시스템": "chatbot_tech_adk",
        "버그": "chatbot_tech_adk",
        "코드": "chatbot_tech_adk",
        "서버": "chatbot_tech_adk",
    }
}


# ==========================================
# Logging Configuration
# ==========================================
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        },
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        },
        "json": {
            "format": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s", "file": "%(filename)s", "line": %(lineno)d}'
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "default",
            "stream": "ext://sys.stdout"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "detailed",
            "filename": "logs/adk_web_ui.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "encoding": "utf-8"
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": "json",
            "filename": "logs/adk_web_ui_errors.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 10,
            "encoding": "utf-8"
        }
    },
    "loggers": {
        "adk_web_ui": {
            "level": "INFO",
            "handlers": ["console", "file", "error_file"],
            "propagate": False
        },
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"]
    }
}


# ==========================================
# OpenAPI Documentation
# ==========================================
OPENAPI_TAGS = [
    {
        "name": "User",
        "description": "사용자 API - 채팅 및 세션 관리"
    },
    {
        "name": "Admin",
        "description": "관리자 API - 통계 및 시스템 관리"
    },
    {
        "name": "Export",
        "description": "데이터 내보내기 API"
    },
    {
        "name": "Search",
        "description": "검색 API"
    }
]

OPENAPI_DESCRIPTION = """
# ADK Web UI API

## 개요
ADK Multi Custom Agent의 Web UI를 위한 REST API 서버입니다.
PostgreSQL 기반의 세션 및 메시지 저장을 지원합니다.

## 기능
- **멀티 Agent 채팅**: 여러 Agent 간 계층적 위임 지원
- **세션 관리**: 사용자별 세션 생성/조회/삭제
- **메시지 히스토리**: 세션별 대화 기록 저장 및 조회
- **관리자 기능**: 통계, 사용자 관리, 모니터링
- **데이터 내보내기**: JSON/TXT/CSV 형식 지원

## 인증
모든 API 요청에는 `x-knox-id` 헤더가 필요합니다.
관리자 API는 추가적으로 관리자 권한이 필요합니다.

## 에러 코드
| 코드 | 설명 |
|------|------|
| 400 | 잘못된 요청 |
| 401 | 인증 실패 (Knox ID 누락) |
| 403 | 권한 없음 |
| 404 | 리소스 없음 |
| 429 | 요청 한도 초과 |
| 500 | 서버 내부 오류 |
"""


# 파일 업로드 설정
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# 로그 디렉토리 생성
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)