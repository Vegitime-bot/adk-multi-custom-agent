"""
backend/api/sso.py - OIDC/OAuth2 SSO 인증 (사내 템플릿 구조)

사내 SSO 템플릿:
- GET /sso      : SSO 인증 요청
- GET /acs      : SSO 콜백 (복호화)
- GET /slo      : 로그아웃

참고: 루트 경로 (/)는 app.py에서 관리

TODO: 사내 SSO Provider에 맞게 구현 필요
"""
from __future__ import annotations
import secrets
from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from config import settings

router = APIRouter(tags=["auth"])

# ── 템플릿 설정 ────────────────────────────────────────────────────
# 사내 템플릿: templates = Jinja2Templates(directory="templates")
templates = Jinja2Templates(directory="templates")


# ── SSO 모델 (사내 템플릿) ─────────────────────────────────────────
# 사내 템플릿: @dataclass class SSOModel: id_token: str = Form(...)
@dataclass
class SSOModel:
    """SSO Form 데이터 모델"""
    id_token: str = Form(...)
    # TODO: 사내 SSO에 맞게 추가 필드 정의
    # code: str = Form(...)
    # state: str = Form(...)


# ── SSO 인증 요청 (GET /sso)
@router.get("/sso")
async def sso(request: Request):
    """
    SSO 인증 요청 시작
    OIDC Provider로 리다이렉트
    """
    # TODO: CSRF 방지용 state 생성 및 저장 방식
    # 사내: 세션? DB? Redis? state 저장 방식 확인
    state = secrets.token_urlsafe(32)
    # request.session["sso_state"] = state  # SessionMiddleware 필요
    
    # TODO: 사내 SSO Authorization URL 구성
    # issuer = settings.SSO_ISSUER
    # client_id = settings.SSO_CLIENT_ID
    # redirect_uri = settings.SSO_REDIRECT_URI
    
    # TODO: 사내에 맞게 리다이렉트
    # return RedirectResponse(url=auth_url)
    
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SSO not implemented yet. TODO: 사내 SSO 로직 추가"
    )


# ── 3. SSO 콜백 (GET /acs)
@router.get("/acs")
async def acs_get(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """
    SSO 콜백 처리 (GET /acs)
    OIDC Provider에서 인증 후 리다이렉트
    """
    # TODO: 사내 SSO 응답 처리
    
    if error:
        # 에러 발생 시 로그인 페이지로 리다이렉트 (쿼리 파라미터 유지)
        error_url = "/?error=" + error
        chatbot = request.query_params.get("chatbot")
        if chatbot:
            error_url += f"&chatbot={chatbot}"
        return RedirectResponse(url=error_url)
    
    if not code:
        return RedirectResponse(url="/?error=no_code")
    
    # TODO: state 검증 (CSRF 방지)
    # TODO: code로 token 교환
    # TODO: 사용자 정보 복호화
    # TODO: JWT 쿠키 설정 또는 세션 생성
    
    # 인증 성공: 원래 요청했던 chatbot으로 리다이렉트
    redirect_url = "/"
    chatbot = request.query_params.get("chatbot")
    if chatbot:
        redirect_url = f"/?chatbot={chatbot}"
    
    return RedirectResponse(url=redirect_url, status_code=302)


# ── 4. SSO 콜백 (POST /acs) - Form 데이터용
# 사내 템플릿: @dataclass class SSOModel: id_token: str = Form(...)
@router.post("/acs")
async def acs_post(request: Request, sso_data: SSOModel = Form(...)):
    """
    SSO 콜백 처리 (POST /acs)
    Form 데이터로 id_token 받는 경우
    """
    # TODO: id_token 검증 및 복호화
    # TODO: 사용자 정보 추출
    
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="ACS POST not implemented yet. TODO: 사내 SSO 로직 추가"
    )


# ── 5. 로그아웃 (GET /slo)
@router.get("/slo")
async def slo(request: Request):
    """
    로그아웃 (Single Logout)
    """
    # TODO: 세션 또는 토큰 삭제
    # TODO: 사내 SSO RP-Initiated Logout (지원 시)
    
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SLO not implemented yet. TODO: 사내 로그아웃 로직 추가"
    )
