"""
app.py - 메인 애플리케이션 진입점
사내 SSO 템플릿 구조에 맞춘 FastAPI 앱
"""
from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import base64
import json
import logging

from config import settings
from backend.utils.logger import configure_logging, get_logger
from backend.utils.metrics import PrometheusMiddleware, setup_metrics

# 구조화된 로깅 설정 (settings import 후에 설정)
configure_logging(
    level=settings.DEBUG and "DEBUG" or "INFO",
    json_format=True
)

logger = get_logger(__name__)

from backend.api.admin import router as admin_router
from backend.api.chat import router as chat_router
from backend.api.sessions import router as sessions_router
from backend.api.health import router as health_router
from backend.api.permissions import router as permissions_router
from backend.api.conversations import router as conversations_router
from backend.managers.chatbot_manager import ChatbotManager
from backend.managers.memory_manager import MemoryManager
from backend.managers.session_manager import SessionManager
from backend.retrieval.ingestion_client import IngestionClient
from backend.roles.router import RoleRouter

# ── 정적 파일 경로 ─────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"

# ── Lifespan 이벤트 핸들러 ────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행되는 lifespan 이벤트"""
    # Startup
    app.state.chatbot_manager = ChatbotManager()
    app.state.session_manager = SessionManager()
    app.state.memory_manager = MemoryManager()
    app.state.ingestion_client = IngestionClient()
    app.state.role_router = RoleRouter(app.state.ingestion_client)
    
    # PostgreSQL 테이블 초기화
    if not settings.USE_MOCK_DB:
        try:
            from backend.database.session import init_tables
            init_tables()
            logger.info("PostgreSQL 테이블 초기화 완료")
        except Exception as e:
            logger.error("PostgreSQL 초기화 오류", extra={"error": str(e)})
    
    chatbot_count = len(app.state.chatbot_manager.list_all())
    logger.info("애플리케이션 시작 완료", extra={
        "use_mock_db": settings.USE_MOCK_DB,
        "use_mock_auth": settings.USE_MOCK_AUTH,
        "chatbot_count": chatbot_count
    })
    
    yield
    
    # Shutdown
    logger.info("서버 종료 중...")


# ── FastAPI 앱 생성 ────────────────────────────────────────────────
def create_app() -> FastAPI:
    """
    FastAPI 애플리케이션 팩토리
    """
    app = FastAPI(
        title="Multi Custom Agent Service",
        description="멀티 테넌트 RAG 챗봇 플랫폼",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── Session 미들웨어 (SSO 인증용) ─────────────────────────────
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY or "your-secret-key-change-in-production",
        session_cookie="session",
        max_age=3600,  # 1시간
        same_site="lax",  # SSO 리다이렉트용 lax 설정
        https_only=False,  # 개발 환경용 (프로덕션에서는 True)
    )

    # ── Prometheus 메트릭스 미들웨어 ───────────────────────────────
    app.add_middleware(PrometheusMiddleware)
    
    # ── Prometheus 메트릭스 엔드포인트 설정 ──────────────────────────
    setup_metrics(app, metrics_path="/metrics")

    # ── SSO 인증 (Mock Auth 아닐 때만) ────────────────────────────
    # NOTE: SSO는 사내 환경에서 별도 구현 필요
    # 현재는 Mock Auth만 사용 (USE_MOCK_AUTH=true 권장)
    if not settings.USE_MOCK_AUTH:
        logger.warning("SSO not implemented in ADK version. Use USE_MOCK_AUTH=true")
    
    # ── 루트 경로 /main으로 리다이렉트 ──────────────────────────
    @app.get("/")
    def root_redirect():
        return RedirectResponse(url="/main")

    # ── 챗봇 상세 페이지 (chatbot 파라미터 지원) ─────────────────
    @app.get("/detail", response_class=HTMLResponse)
    def detail_page(chatbot: str = None):
        """챗봇 상세 페이지 - chatbot 파라미터로 ID 전달"""
        html_file = STATIC_DIR / "detail.html"
        if html_file.exists():
            return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
        # detail.html이 없으면 index.html 반환 (SPA 방식)
        html_file = STATIC_DIR / "index.html"
        if html_file.exists():
            return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
        return HTMLResponse(content=f"<h1>Chatbot Detail</h1><p>ID: {chatbot}</p><p>static/detail.html 없음</p>")

    # ── 라우터 등록 ───────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(sessions_router, prefix="/api")  # /api/sessions 경로로 등록
    app.include_router(admin_router, prefix="")
    app.include_router(permissions_router)
    app.include_router(conversations_router)

    # ── Admin 페이지 라우팅 ─────────────────────────────────────────
    # 테스트 및 사용자 편의를 위한 /admin 경로 추가
    admin_html_path = STATIC_DIR / "admin" / "index.html"
    if admin_html_path.exists():
        @app.get("/admin", response_class=HTMLResponse)
        async def admin_page():
            return HTMLResponse(content=admin_html_path.read_text(encoding="utf-8"))
    
    # ── 정적 파일 마운트 ───────────────────────────────────────────
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


# ── 전역 앱 인스턴스 ─────────────────────────────────────────────
app = create_app()


# ── 직접 실행 (python app.py) ──────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    
    logger.info("서버 시작", extra={"host": settings.HOST, "port": settings.PORT, "debug": settings.DEBUG})
    
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
