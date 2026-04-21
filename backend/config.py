"""
backend/config.py - 환경설정 재export
루트 config.py에서 설정을 가져와 재export
"""
from __future__ import annotations
import sys
from pathlib import Path

# 루트 디렉토리를 path에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 루트 config에서 import
try:
    from config import Settings, settings
except ImportError:
    # Fallback: 직접 정의 (순환 import 방지)
    import os

    class Settings:
        USE_MOCK_DB: bool = os.getenv("USE_MOCK_DB", "true").lower() == "true"
        USE_MOCK_AUTH: bool = os.getenv("USE_MOCK_AUTH", "true").lower() == "true"
        PG_HOST: str = os.getenv("PG_HOST", "localhost")
        PG_PORT: int = int(os.getenv("PG_PORT", "5432"))
        PG_DB: str = os.getenv("PG_DB", "chatbot_db")
        PG_USER: str = os.getenv("PG_USER", "postgres")
        PG_PASSWORD: str = os.getenv("PG_PASSWORD", "")

        @property
        def DATABASE_URL(self) -> str:
            return f"postgresql://{self.PG_USER}:{self.PG_PASSWORD}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DB}"

        LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        LLM_API_KEY: str = os.getenv("LLM_API_KEY", "dummy-key")
        LLM_DEFAULT_MODEL: str = os.getenv("LLM_DEFAULT_MODEL", "GLM4.7")
        LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "120"))
        LLM_DEFAULT_TEMPERATURE: float = float(os.getenv("LLM_DEFAULT_TEMPERATURE", "0.3"))
        LLM_DEFAULT_MAX_TOKENS: int = int(os.getenv("LLM_DEFAULT_MAX_TOKENS", "1024"))
        INGESTION_BASE_URL: str = os.getenv("INGESTION_BASE_URL", "http://localhost:8001")
        INGESTION_API_KEY: str = os.getenv("INGESTION_API_KEY", "")
        SSL_VERIFY: bool = os.getenv("SSL_VERIFY", "false").lower() == "true"
        CHATBOTS_DIR: Path = Path(__file__).parent.parent / "chatbots"
        HOST: str = os.getenv("HOST", "0.0.0.0")
        PORT: int = int(os.getenv("PORT", "8080"))
        DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    settings = Settings()

# 재export
__all__ = ["Settings", "settings"]
