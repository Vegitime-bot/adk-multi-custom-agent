"""
Configuration for ADK Web UI
환경변수 기반 설정 관리
"""

import os
from typing import List
from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """앱 설정"""
    
    # ============================================
    # App Settings
    # ============================================
    APP_NAME: str = Field(default="ADK Web UI", description="앱 이름")
    DEBUG: bool = Field(default=False, description="디버그 모드")
    LOG_LEVEL: str = Field(default="INFO", description="로그 레벨")
    
    # ============================================
    # Database Settings (PostgreSQL)
    # ============================================
    DB_HOST: str = Field(default="localhost", description="DB 호스트")
    DB_PORT: int = Field(default=5432, description="DB 포트")
    DB_NAME: str = Field(default="adk_chat", description="DB 이름")
    DB_USER: str = Field(default="postgres", description="DB 사용자")
    DB_PASSWORD: str = Field(default="password", description="DB 비밀번호")
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    # ============================================
    # SQLite Settings (테스트용)
    # ============================================
    USE_SQLITE: bool = Field(default=False, description="SQLite 사용 여부")
    SQLITE_PATH: str = Field(default="adk_chat.db", description="SQLite 파일 경로")
    
    # ============================================
    # Knox ID Settings
    # ============================================
    DEFAULT_KNOX_ID: str = Field(
        default="anonymous", 
        description="기본 Knox ID (인증 실패시)"
    )
    REQUIRE_KNOX_ID: bool = Field(
        default=True, 
        description="Knox ID 필수 여부"
    )
    
    # ============================================
    # Admin Settings
    # ============================================
    ADMIN_KNOX_IDS: str = Field(
        default="",
        description="관리자 Knox ID 목록 (쉼표 구분)"
    )
    
    @property
    def ADMIN_KNOX_LIST(self) -> List[str]:
        """관리자 Knox ID 목록 (파싱된)"""
        if not self.ADMIN_KNOX_IDS:
            return []
        return [k.strip() for k in self.ADMIN_KNOX_IDS.split(",") if k.strip()]
    
    @validator('LOG_LEVEL')
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()
    
    @validator('ADMIN_KNOX_IDS')
    def validate_admin_ids(cls, v):
        """관리자 ID 형식 검증"""
        if v:
            ids = [k.strip() for k in v.split(",") if k.strip()]
            for id in ids:
                if len(id) > 255:
                    raise ValueError(f"Knox ID too long: {id}")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 전역 설정 인스턴스
settings = Settings()


def is_admin(knox_id: str) -> bool:
    """관리자 여부 확인"""
    return knox_id in settings.ADMIN_KNOX_LIST


def require_admin(knox_id: str) -> None:
    """관리자 권한 필요 (예외 발생)"""
    if not is_admin(knox_id):
        raise PermissionError(f"Admin access required for: {knox_id}")


# 환경별 프리셋
def get_development_settings() -> Settings:
    """개발 환경 설정"""
    return Settings(
        DEBUG=True,
        LOG_LEVEL="DEBUG",
        USE_SQLITE=True,
    )


def get_production_settings() -> Settings:
    """운영 환경 설정"""
    return Settings(
        DEBUG=False,
        LOG_LEVEL="WARNING",
        REQUIRE_KNOX_ID=True,
    )


# 설정 검증
def validate_settings() -> List[str]:
    """설정 검증 및 경고 반환"""
    warnings = []
    
    if not settings.ADMIN_KNOX_IDS:
        warnings.append("⚠️  ADMIN_KNOX_IDS not set - admin features disabled")
    
    if settings.DEBUG:
        warnings.append("⚠️  DEBUG mode enabled - not for production")
    
    if settings.DEFAULT_KNOX_ID == "anonymous":
        warnings.append("⚠️  Using default Knox ID 'anonymous'")
    
    if not settings.REQUIRE_KNOX_ID:
        warnings.append("⚠️  Knox ID not required - security risk")
    
    return warnings
