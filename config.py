"""
config.py - 환경설정 관리 (루트 위치)
"""
from __future__ import annotations
import os
from pathlib import Path

# 프로젝트 루트 (multi-custom-agent/)
PROJECT_ROOT = Path(__file__).parent

# .env 파일 로드
try:
    from dotenv import load_dotenv
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
except ImportError:
    pass


class Settings:
    # ── 모드 플래그 ──────────────────────────────────────────────
    USE_MOCK_DB: bool = os.getenv("USE_MOCK_DB", "true").lower() == "true"
    USE_MOCK_AUTH: bool = os.getenv("USE_MOCK_AUTH", "true").lower() == "true"

    # ── PostgreSQL ───────────────────────────────────────────────
    PG_HOST: str = os.getenv("PG_HOST", "localhost")
    PG_PORT: int = int(os.getenv("PG_PORT", "5432"))
    PG_DB: str = os.getenv("PG_DB", "chatbot_db")
    PG_USER: str = os.getenv("PG_USER", "postgres")
    PG_PASSWORD: str = os.getenv("PG_PASSWORD", "")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.PG_USER}:{self.PG_PASSWORD}"
            f"@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DB}"
        )

    # ── LLM ───────────────────────────────────────────────────────
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "dummy-key")
    LLM_DEFAULT_MODEL: str = os.getenv("LLM_DEFAULT_MODEL", "GLM4.7")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "120"))
    LLM_DEFAULT_TEMPERATURE: float = float(os.getenv("LLM_DEFAULT_TEMPERATURE", "0.3"))
    LLM_DEFAULT_MAX_TOKENS: int = int(os.getenv("LLM_DEFAULT_MAX_TOKENS", "1024"))

    # ── Ingestion ─────────────────────────────────────────────────
    INGESTION_BASE_URL: str = os.getenv("INGESTION_BASE_URL", "http://localhost:8001")
    INGESTION_API_KEY: str = os.getenv("INGESTION_API_KEY", "")

    # ── SSL ──────────────────────────────────────────────────────
    SSL_VERIFY: bool = os.getenv("SSL_VERIFY", "false").lower() == "true"

    # ── 챗봇 정의 경로 ────────────────────────────────────────────
    CHATBOTS_DIR: Path = PROJECT_ROOT / "chatbots"

    # ── 서버 ─────────────────────────────────────────────────────
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8080"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ── 세션 보안 ─────────────────────────────────────────────────
    # SSO 사용 시 반드시 변경 (32바이트 이상 랜덤 문자열)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-in-production-secret-key-32bytes-minimum")

    # ── SSO/OIDC 설정 ─────────────────────────────────────────────
    # 사내 SSO 연동 시 필요한 환경변수
    # USE_MOCK_AUTH=false 시 아래 설정 사용
    SSO_ISSUER: str = os.getenv("SSO_ISSUER", "https://sso.company.com")
    SSO_CLIENT_ID: str = os.getenv("SSO_CLIENT_ID", "")
    SSO_CLIENT_SECRET: str = os.getenv("SSO_CLIENT_SECRET", "")
    SSO_REDIRECT_URI: str = os.getenv("SSO_REDIRECT_URI", "http://localhost:8080/auth/acs")
    
    # OIDC Endpoints (자동 Discovery 실패 시 수동 설정)
    SSO_AUTH_URL: str = os.getenv("SSO_AUTH_URL", "")
    SSO_TOKEN_URL: str = os.getenv("SSO_TOKEN_URL", "")
    SSO_USERINFO_URL: str = os.getenv("SSO_USERINFO_URL", "")
    SSO_LOGOUT_URL: str = os.getenv("SSO_LOGOUT_URL", "")  # Optional
    SSO_SCOPES: str = os.getenv("SSO_SCOPES", "openid email profile")

    # ── 관리자 설정 ─────────────────────────────────────────────────
    # Admin 권한을 가진 SSO 사용자 ID 목록 (콤마로 구분)
    ADMIN_USER_IDS: list[str] = [uid.strip() for uid in os.getenv("ADMIN_USER_IDS", "user-001").split(",") if uid.strip()]


settings = Settings()
