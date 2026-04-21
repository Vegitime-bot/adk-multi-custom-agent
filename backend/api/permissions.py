"""
backend/api/permissions.py - 권한 관리 API
사용자-챗봇 권한 CRUD API
"""
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.permissions.repository import (
    PermissionRepository,
    get_perm_repo,
    get_permission_repository,
)
from backend.config import settings

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


# ── 요청/응답 모델 ─────────────────────────────────────────────────
class PermissionCreate(BaseModel):
    knox_id: str
    chatbot_id: str
    can_access: bool = True


class PermissionUpdate(BaseModel):
    can_access: bool


class PermissionResponse(BaseModel):
    id: int
    knox_id: str
    chatbot_id: str
    can_access: bool
    created_at: Optional[str] = None


class UserPermissionsResponse(BaseModel):
    knox_id: str
    permissions: List[PermissionResponse]
    accessible_count: int
    total: int


class BulkPermissionRequest(BaseModel):
    knox_id: str
    chatbot_ids: List[str]
    can_access: bool


class BulkPermissionResponse(BaseModel):
    total: int
    success_count: int
    failed_count: int
    errors: List[str] = []


class PermissionStats(BaseModel):
    total_permissions: int
    unique_users: int
    unique_chatbots: int
    user_stats: dict


# ── API 엔드포인트 ────────────────────────────────────────────────

@router.get("", response_model=List[PermissionResponse])
async def get_all_permissions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    knox_id: Optional[str] = Query(None, description="사용자 ID로 필터링"),
    chatbot_id: Optional[str] = Query(None, description="챗봇 ID로 필터링"),
    repo: PermissionRepository = Depends(get_perm_repo),
):
    """전체 권한 목록 조회 (페이징 지원)"""
    permissions = repo.get_all_permissions(skip=skip, limit=limit)
    
    # 필터링 적용
    if knox_id:
        permissions = [p for p in permissions if p.get("knox_id") == knox_id]
    if chatbot_id:
        permissions = [p for p in permissions if p.get("chatbot_id") == chatbot_id]
    
    return [PermissionResponse(**p) for p in permissions]


@router.get("/users/{knox_id}", response_model=UserPermissionsResponse)
async def get_user_permissions(
    knox_id: str,
    repo: PermissionRepository = Depends(get_perm_repo),
):
    """특정 사용자의 모든 권한 조회"""
    permissions = repo.get_user_permissions(knox_id)
    
    accessible = sum(1 for p in permissions if p.get("can_access"))
    
    return UserPermissionsResponse(
        knox_id=knox_id,
        permissions=[PermissionResponse(**p) for p in permissions],
        accessible_count=accessible,
        total=len(permissions),
    )


@router.get("/chatbots/{chatbot_id}/users", response_model=List[dict])
async def get_chatbot_users(
    chatbot_id: str,
    repo: PermissionRepository = Depends(get_perm_repo),
):
    """특정 챗봇에 접근 가능한 사용자 목록 조회"""
    users = repo.get_chatbot_users(chatbot_id)
    return users


@router.post("", response_model=PermissionResponse)
async def create_permission(
    data: PermissionCreate,
    repo: PermissionRepository = Depends(get_perm_repo),
):
    """새로운 권한 추가 (사용자-챗봇 권한 부여)"""
    success = repo.grant_access(
        knox_id=data.knox_id,
        chatbot_id=data.chatbot_id,
        can_access=data.can_access,
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="권한 생성 실패")
    
    # 생성된 권한 조회
    perms = repo.get_user_permissions(data.knox_id)
    for p in perms:
        if p.get("chatbot_id") == data.chatbot_id:
            return PermissionResponse(**p)
    
    raise HTTPException(status_code=404, detail="생성된 권한을 찾을 수 없음")


@router.put("/{knox_id}/{chatbot_id}", response_model=PermissionResponse)
async def update_permission(
    knox_id: str,
    chatbot_id: str,
    data: PermissionUpdate,
    repo: PermissionRepository = Depends(get_perm_repo),
):
    """권한 수정 (can_access 값 변경)"""
    success = repo.grant_access(
        knox_id=knox_id,
        chatbot_id=chatbot_id,
        can_access=data.can_access,
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="권한을 찾을 수 없음")
    
    # 수정된 권한 반환
    perms = repo.get_user_permissions(knox_id)
    for p in perms:
        if p.get("chatbot_id") == chatbot_id:
            return PermissionResponse(**p)
    
    raise HTTPException(status_code=404, detail="수정된 권한을 찾을 수 없음")


@router.delete("/{knox_id}/{chatbot_id}")
async def delete_permission(
    knox_id: str,
    chatbot_id: str,
    repo: PermissionRepository = Depends(get_perm_repo),
):
    """권한 삭제 (철회)"""
    success = repo.revoke_access(knox_id, chatbot_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="삭제할 권한을 찾을 수 없음")
    
    return {"message": "권한이 삭제되었습니다"}


@router.post("/bulk", response_model=BulkPermissionResponse)
async def bulk_create_permissions(
    data: BulkPermissionRequest,
    repo: PermissionRepository = Depends(get_perm_repo),
):
    """여러 챗봇에 대해 일괄 권한 설정"""
    success_count = 0
    failed_count = 0
    errors = []
    
    for chatbot_id in data.chatbot_ids:
        try:
            success = repo.grant_access(
                knox_id=data.knox_id,
                chatbot_id=chatbot_id,
                can_access=data.can_access,
            )
            if success:
                success_count += 1
            else:
                failed_count += 1
                errors.append(f"{chatbot_id}: 처리 실패")
        except Exception as e:
            failed_count += 1
            errors.append(f"{chatbot_id}: {str(e)}")
    
    return BulkPermissionResponse(
        total=len(data.chatbot_ids),
        success_count=success_count,
        failed_count=failed_count,
        errors=errors,
    )


@router.get("/admin/stats", response_model=PermissionStats)
async def get_permission_stats(
    repo: PermissionRepository = Depends(get_perm_repo),
):
    """권한 통계 정보 조회 (관리자용)"""
    all_perms = repo.get_all_permissions(limit=10000)
    
    # 사용자별 통계
    user_stats = {}
    for p in all_perms:
        knox_id = p.get("knox_id", "unknown")
        if knox_id not in user_stats:
            user_stats[knox_id] = {"accessible": 0, "total": 0}
        user_stats[knox_id]["total"] += 1
        if p.get("can_access"):
            user_stats[knox_id]["accessible"] += 1
    
    # 고유 사용자/챗봇 수
    unique_users = len(set(p.get("knox_id") for p in all_perms))
    unique_chatbots = len(set(p.get("chatbot_id") for p in all_perms))
    
    return PermissionStats(
        total_permissions=len(all_perms),
        unique_users=unique_users,
        unique_chatbots=unique_chatbots,
        user_stats=user_stats,
    )


@router.get("/check/{knox_id}/{chatbot_id}")
async def check_permission(
    knox_id: str,
    chatbot_id: str,
    repo: PermissionRepository = Depends(get_perm_repo),
):
    """특정 사용자-챗봇 권한 확인"""
    has_access = repo.check_access(knox_id, chatbot_id)
    return {
        "knox_id": knox_id,
        "chatbot_id": chatbot_id,
        "can_access": has_access,
    }
