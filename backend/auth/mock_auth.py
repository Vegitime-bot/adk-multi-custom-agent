from __future__ import annotations
"""
auth/mock_auth.py - 인증 처리
USE_MOCK_AUTH=true: 고정 사용자 반환 (개발/테스트)
USE_MOCK_AUTH=false: 세션 또는 헤더 기반 인증 (운영)
"""
from fastapi import Request, HTTPException, status

from backend.config import settings


def get_current_user(request: Request) -> dict:
    """
    현재 요청의 사용자를 반환한다.
    """
    # Mock 모드: 고정 사용자 반환
    if settings.USE_MOCK_AUTH:
        return {"knox_id": "jyd1234", "name": "장영동", "team": "AI팀", "eng_name": "Youngdong Jang"}

    # 운영 모드: 세션 기반 인증
    try:
        if request.session.get('sso') and request.session.get('knox_id'):
            return {
                "knox_id": request.session['knox_id'],
                "name": request.session.get('user_info', {}).get('name', 'Unknown'),
                "team": "AI팀",
            }
    except Exception:
        pass

    # 세션 인증 실패 시 401 반환 (sso.py에서 리다이렉트 처리)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증이 필요합니다.",
    )
