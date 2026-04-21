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

# 전역 로깅 레벨 설정 (DEBUG)
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# 기본 로거 레벨 설정
for handler in logging.getLogger().handlers:
    handler.setLevel(logging.DEBUG)

from config import settings
from backend.api.admin import router as admin_router
from backend.api.chat import router as chat_router
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
            print("[Startup] PostgreSQL 테이블 초기화 완료")
        except Exception as e:
            print(f"[Startup] PostgreSQL 초기화 오류: {e}")
    
    print(f"[Startup] USE_MOCK_DB={settings.USE_MOCK_DB}, USE_MOCK_AUTH={settings.USE_MOCK_AUTH}")
    print(f"[Startup] 챗봇 {len(app.state.chatbot_manager.list_all())}개 로드됨")
    
    yield
    
    # Shutdown
    print("[Shutdown] 서버 종료 중...")


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

    # ── SSO 인증 (Mock Auth 아닐 때만) ────────────────────────────
    if not settings.USE_MOCK_AUTH:
        try:
            from backend.api.sso import router as sso_router
            app.include_router(sso_router, prefix="")  # 루트에 등록
            print("[Startup] SSO 인증 라우터 등록됨 (/, /sso, /acs, /slo)")
        except Exception as e:
            print(f"[Startup] SSO 라우터 로드 실패: {e}")
            
        # 루트 경로: 인증되면 /admin으로, 미인증이면 /sso로
        @app.get("/")
        async def root_with_sso_check(request: Request):
            """
            루트 경로: SSO 인증 상태에 따라 분기
            - 인증됨: /main으로 리다이렉트 (관리자 페이지)
            - 미인증: /sso로 리다이렉트 (SSO 로그인)
            """
            try:
                if request.session.get('sso'):
                    return RedirectResponse(url="/main")
                return RedirectResponse(url="/sso")
            except Exception:
                return RedirectResponse(url="/sso")
    else:
        # Mock Auth: 챗봇 UI를 루트에 표시
        @app.get("/", response_class=HTMLResponse)
        def index():
            html_file = STATIC_DIR / "index.html"
            if html_file.exists():
                return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
            return HTMLResponse(content="<h1>Multi Custom Agent Service</h1><p>static/index.html 없음</p>")

    # ── 라우터 등록 ───────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(admin_router, prefix="")
    app.include_router(permissions_router)
    app.include_router(conversations_router)

    # ── 정적 파일 마운트 ───────────────────────────────────────────
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


# ── 전역 앱 인스턴스 ─────────────────────────────────────────────
app = create_app()


# ── 직접 실행 (python app.py) ──────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    
    print(f"[Server] Starting on {settings.HOST}:{settings.PORT}")
    print(f"[Server] DEBUG={settings.DEBUG}")
    
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
