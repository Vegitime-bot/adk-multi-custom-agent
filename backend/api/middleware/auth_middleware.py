"""
backend/api/middleware/auth_middleware.py - 인증 및 권한 미들웨어
"""
from __future__ import annotations

from fastapi import Request, HTTPException
from backend.config import settings
from backend.debug_logger import logger
from backend.permissions.repository import (
    PermissionRepository,
    get_permission_repository,
)


def get_current_user(request: Request) -> dict:
    """
    현재 요청의 사용자를 반환한다.
    Mock 모드: 고정 사용자 반환 (개발/테스트)
    운영 모드: 세션 기반 인증
    """
    if settings.USE_MOCK_AUTH:
        return {
            "knox_id": "jyd1234",
            "name": "장영동",
            "team": "AI팀",
            "eng_name": "Youngdong Jang"
        }

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

    raise HTTPException(
        status_code=401,
        detail="인증이 필요합니다.",
    )


# ═══════════════════════════════════════════════════════════════════
# 권한 데이터
# ═══════════════════════════════════════════════════════════════════

# 모의 사용자 권한 데이터 (개발 환경용)
MOCK_USER_PERMISSIONS = {
    "user-001": {
        "chatbot-a": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-b": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-c": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-rtl-verilog": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-rtl-synthesis": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-company": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-hr": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-hr-policy": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-hr-benefit": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-backend": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-frontend": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-devops": {"access": True, "allowed_modes": ["tool", "agent"]},
    },
    "user-002": {
        "chatbot-a": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-b": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-c": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-d": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-hr": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-hr-policy": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-hr-benefit": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-backend": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-frontend": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-devops": {"access": True, "allowed_modes": ["tool", "agent"]},
    },
    "system": {
        "chatbot-a": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-b": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-c": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-d": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-hr": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-hr-policy": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-hr-benefit": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-tech": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-tech-backend": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-tech-frontend": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-tech-devops": {"access": True, "allowed_modes": ["tool"]},
    },
}

# 사용자 DB 스코프 (개발 환경용)
MOCK_USER_DB_SCOPE = {
    "user-001": {"db_001", "db_002", "db_003", "db_004", "db_005"},
    "user-002": {"db_001"},
    "user-003": {"db_002", "db_003"},
    "guest": {"db_001"},
    "jyd1234": {"db_001", "db_002", "db_003", "db_004", "db_005"},
    "yd86.jang": {"db_001", "db_002", "db_003", "db_004", "db_005", "snp"},
}


def load_restricted_chatbots() -> set[str]:
    """파일에서 제한된 챗봇 목록 로드"""
    import json
    from pathlib import Path
    file_path = Path(__file__).parent.parent.parent / "data" / "restricted_chatbots.json"
    if file_path.exists():
        data = json.loads(file_path.read_text())
        return set(data.get("chatbots", []))
    return set()


RESTRICTED_CHATBOTS: set[str] = load_restricted_chatbots()


def get_user_permissions(user: dict) -> dict:
    """사용자의 챗봇별 권한 조회"""
    knox_id = user.get("knox_id", "unknown")

    try:
        repo = get_permission_repository(use_mock=settings.USE_MOCK_DB)
        perms = repo.get_user_permissions(knox_id)
        result = {}
        for p in perms:
            chatbot_id = p.get("chatbot_id")
            can_access = p.get("can_access", False)
            if chatbot_id:
                result[chatbot_id] = {
                    "access": can_access,
                    "allowed_modes": ["tool", "agent"]
                }
        if result:
            return result
    except Exception as e:
        logger.warning(f"[get_user_permissions] DB 조회 실패: {e}")

    return MOCK_USER_PERMISSIONS.get("user-001", {})


def check_chatbot_access(permissions: dict, chatbot_id: str) -> bool:
    """챗봇 접근 권한 확인 - 기본 허용, 특정 챗봇만 체크"""
    if chatbot_id.startswith("test-"):
        return True

    if settings.USE_MOCK_AUTH:
        return True

    if not RESTRICTED_CHATBOTS:
        logger.debug(f"[check_chatbot_access] RESTRICTED_CHATBOTS 비어있음 → {chatbot_id} 허용")
        return True

    if chatbot_id not in RESTRICTED_CHATBOTS:
        logger.debug(f"[check_chatbot_access] {chatbot_id}는 제한 목록에 없음 → 허용")
        return True

    bot_perm = permissions.get(chatbot_id, {})
    can_access = bot_perm.get("access", False)
    logger.info(f"[check_chatbot_access] {chatbot_id}는 제한된 챗봇 → 권한: {can_access}")
    return can_access


def check_mode_permission(permissions: dict, chatbot_id: str, mode: str) -> bool:
    """특정 mode 사용 권한 확인 - 기본 허용, 제한된 챗봇만 체크"""
    if chatbot_id.startswith("test-"):
        return True

    if settings.USE_MOCK_AUTH:
        return True

    if not RESTRICTED_CHATBOTS:
        logger.debug(f"[check_mode_permission] RESTRICTED_CHATBOTS 비어있음 → {chatbot_id}/{mode} 허용")
        return True

    if chatbot_id not in RESTRICTED_CHATBOTS:
        logger.debug(f"[check_mode_permission] {chatbot_id}는 제한 목록에 없음 → {mode} 허용")
        return True

    bot_perm = permissions.get(chatbot_id, {})
    if not bot_perm.get("access", False):
        logger.warning(f"[check_mode_permission] {chatbot_id} 접근 권한 없음 → {mode} 차단")
        return False

    allowed = bot_perm.get("allowed_modes", [])
    has_permission = mode in allowed
    logger.info(f"[check_mode_permission] {chatbot_id}는 제한된 챗봇 → {mode} 권한: {has_permission}")
    return has_permission


def get_user_db_scope(user: dict) -> set[str]:
    """사용자가 접근 가능한 DB 목록 조회"""
    knox_id = user.get("knox_id", "unknown")

    if settings.USE_MOCK_AUTH:
        scope = MOCK_USER_DB_SCOPE.get(knox_id, set())
        logger.info(f"[DB Scope] 사용자 {knox_id}의 접근 가능 DB: {scope}")
        return scope

    return set()