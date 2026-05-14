"""
adk_session_wrapper.py - ADK Session 래퍼

ADK 1.31.1 버전의 Session API를 사용하여 기존 SessionManager와 
100% 호환되는 인터페이스를 제공합니다.

환경 변수 USE_ADK=true 시 ADK Session을 사용합니다.
"""

from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime
from typing import Any, Optional
from dataclasses import dataclass, field

# 기존 모델 import
from backend.core.models import ChatSession, ExecutionRole

# ADK import (버전 1.31.1 기준)
try:
    from google.adk.sessions import Session
    from google.adk.sessions.in_memory_session_service import InMemorySessionService
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    logging.warning("ADK not available. Install with: pip install google-adk==1.31.1")

logger = logging.getLogger(__name__)

# 환경 변수로 ADK 사용 여부 결정
USE_ADK = os.environ.get("USE_ADK", "false").lower() == "true"


class ADKSessionWrapper:
    """
    ADK Session을 기존 SessionManager 인터페이스와 호환되게 래핑하는 클래스.
    
    ADK Session의 state에 다음 값들을 저장:
    - chatbot_id: str
    - user_knox_id: str  
    - role_override: dict[str, str] (ExecutionRole을 string으로 저장)
    - active_level: int
    - created_at: str (ISO format)
    """
    
    def __init__(self):
        self._local_sessions: dict[str, ChatSession] = {}  # ADK 비활성화 시 fallback
        
        if USE_ADK and ADK_AVAILABLE:
            self._session_service = InMemorySessionService()
            logger.info("[ADKSessionWrapper] Initialized with ADK InMemorySessionService")
        else:
            self._session_service = None
            logger.info(f"[ADKSessionWrapper] Initialized in legacy mode (USE_ADK={USE_ADK}, ADK_AVAILABLE={ADK_AVAILABLE})")
    
    # ─────────────────────────────────────────────────────────────────
    # Public API - 기존 SessionManager와 100% 호환
    # ─────────────────────────────────────────────────────────────────
    
    def get_or_create(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: Optional[str] = None,
    ) -> ChatSession:
        """
        세션 조회 또는 생성. 
        session_id가 없으면 최근 세션 자동 연결.
        
        Args:
            chatbot_id: 챗봇 ID
            user_knox_id: 사용자 Knox ID
            session_id: 세션 ID (선택)
            
        Returns:
            ChatSession 객체
        """
        if USE_ADK and ADK_AVAILABLE and self._session_service:
            return self._adk_get_or_create(chatbot_id, user_knox_id, session_id)
        else:
            return self._legacy_get_or_create(chatbot_id, user_knox_id, session_id)
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """
        세션 ID로 세션 조회.
        
        Args:
            session_id: 세션 ID
            
        Returns:
            ChatSession 객체 또는 None
        """
        if USE_ADK and ADK_AVAILABLE and self._session_service:
            return self._adk_get_session(session_id)
        else:
            return self._local_sessions.get(session_id)
    
    def close_session(self, session_id: str) -> bool:
        """
        세션 종료 및 제거.
        
        Args:
            session_id: 세션 ID
            
        Returns:
            성공 여부
        """
        if USE_ADK and ADK_AVAILABLE and self._session_service:
            return self._adk_close_session(session_id)
        else:
            if session_id in self._local_sessions:
                del self._local_sessions[session_id]
                return True
            return False
    
    # ─────────────────────────────────────────────────────────────────
    # Internal Methods - ADK 구현
    # ─────────────────────────────────────────────────────────────────
    
    def _adk_get_or_create(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: Optional[str] = None,
    ) -> ChatSession:
        """ADK 기반 get_or_create 구현."""
        try:
            # 1. 명시적 session_id로 조회
            if session_id:
                adk_session = self._session_service.get_session(
                    app_name="multi_custom_agent",
                    user_id=user_knox_id,
                    session_id=session_id,
                )
                if adk_session:
                    logger.info(f"[ADKSessionWrapper] Found existing session: {session_id}")
                    return self._adk_to_chat_session(adk_session)
            
            # 2. 동일 user + chatbot의 최근 세션 찾기
            recent_session = self._find_recent_session(user_knox_id, chatbot_id)
            if recent_session:
                logger.info(
                    f"[ADKSessionWrapper] Reusing recent session: {recent_session.session_id} "
                    f"for {user_knox_id}/{chatbot_id}"
                )
                return recent_session
            
            # 3. 새 ADK 세션 생성
            new_session_id = session_id or str(uuid.uuid4())
            state = {
                "chatbot_id": chatbot_id,
                "user_knox_id": user_knox_id,
                "role_override": {},
                "active_level": 1,
                "created_at": datetime.utcnow().isoformat(),
            }
            
            logger.info(f"[ADKSessionWrapper] Creating ADK session: {new_session_id}")
            adk_session = self._session_service.create_session_sync(
                app_name="multi_custom_agent",
                user_id=user_knox_id,
                session_id=new_session_id,
                state=state,
            )
            
            logger.info(f"[ADKSessionWrapper] ADK session created, type={type(adk_session)}, id={getattr(adk_session, 'id', 'N/A')}")
            chat_session = self._adk_to_chat_session(adk_session)
            # 로컬 캐시에 저장 (list_sessions에서 조회 가능하도록)
            self._local_sessions[new_session_id] = chat_session
            logger.info(f"[ADKSessionWrapper] Saved to local cache: {new_session_id}, total={len(self._local_sessions)}")
            return chat_session
        except Exception as e:
            logger.error(f"[ADKSessionWrapper] _adk_get_or_create ERROR: {type(e).__name__}: {e}")
            raise
    
    def _adk_get_session(self, session_id: str) -> Optional[ChatSession]:
        """ADK 기반 세션 조회."""
        # 먼저 로컬 캐시에서 확인
        if session_id in self._local_sessions:
            return self._local_sessions[session_id]
        
        # ADK에서 모든 사용자 세션을 검색
        try:
            # list_sessions로 모든 세션 조회
            all_sessions = self._session_service.list_sessions(
                app_name="multi_custom_agent",
                user_id="*",  # 와일드카드로 모든 사용자
            )
            for session in all_sessions:
                if session.session_id == session_id:
                    chat_session = self._adk_to_chat_session(session)
                    # 로컬 캐시에 저장
                    self._local_sessions[session_id] = chat_session
                    return chat_session
        except Exception:
            # list_sessions 실패 시 내부 _sessions 순회
            if hasattr(self._session_service, '_sessions'):
                for key, session in self._session_service._sessions.items():
                    if session.session_id == session_id:
                        chat_session = self._adk_to_chat_session(session)
                        self._local_sessions[session_id] = chat_session
                        return chat_session
        
        return None
    
    def _adk_close_session(self, session_id: str) -> bool:
        """ADK 기반 세션 종료."""
        # 로컬 캐시에서 제거
        local_removed = False
        if session_id in self._local_sessions:
            del self._local_sessions[session_id]
            local_removed = True
        
        # ADK 내부 _sessions에서도 제거
        if hasattr(self._session_service, '_sessions'):
            sessions = self._session_service._sessions
            keys_to_remove = [
                key for key, session in sessions.items()
                if session.session_id == session_id
            ]
            for key in keys_to_remove:
                del sessions[key]
            return local_removed or len(keys_to_remove) > 0
        
        return local_removed
    
    def _find_recent_session(
        self,
        user_knox_id: str,
        chatbot_id: str,
    ) -> Optional[ChatSession]:
        """
        동일 user + chatbot의 가장 최근 세션 찾기.
        
        ADK 사용 시: 해당 사용자의 모든 세션을 순회하며 chatbot_id가 일치하는 세션 찾기
        레거시 모드: 인메모리 세션 딕셔너리 순회
        """
        if USE_ADK and ADK_AVAILABLE and self._session_service:
            return self._adk_find_recent_session(user_knox_id, chatbot_id)
        else:
            return self._legacy_find_recent_session(user_knox_id, chatbot_id)
    
    def _adk_find_recent_session(
        self,
        user_knox_id: str,
        chatbot_id: str,
    ) -> Optional[ChatSession]:
        """ADK 기반 최근 세션 찾기. _local_sessions를 primary로 사용."""
        # 먼저 로컬 캐시에서 검색 (ADK async 호출 문제 회피)
        matching = [
            s for s in self._local_sessions.values()
            if s.user_knox_id == user_knox_id and s.chatbot_id == chatbot_id
        ]
        if matching:
            # 생성 시간 기준으로 정렬하여 가장 최근 것 반환
            matching.sort(key=lambda s: s.created_at, reverse=True)
            logger.info(f"[ADKSessionWrapper] _adk_find_recent_session: found {len(matching)} in local cache")
            return matching[0]
        
        # 로컬에 없으면 ADK 시도 (fallback)
        try:
            # ADK list_sessions는 async coroutine이므로 sync 함수에서 직접 호출하면 RuntimeWarning
            # asyncio.run()은 이미 실행 중인 event loop가 있으면 불가
            # 일단 로컬 캐시 우선 정책으로 처리
            logger.info(f"[ADKSessionWrapper] _adk_find_recent_session: not found in local cache, returning None")
        except Exception as e:
            logger.warning(f"[ADKSessionWrapper] _adk_find_recent_session error: {e}")
        
        return None
        
        return None
    
    def _adk_to_chat_session(self, adk_session: Session) -> ChatSession:
        """
        ADK Session을 ChatSession으로 변환.
        
        Args:
            adk_session: ADK Session 객체
            
        Returns:
            ChatSession 객체
        """
        state = adk_session.state or {}
        
        # role_override 복원 (dict[str, str] -> dict[str, ExecutionRole])
        role_override_raw = state.get("role_override", {})
        role_override = {}
        if isinstance(role_override_raw, dict):
            for bot_id, role_str in role_override_raw.items():
                try:
                    role_override[bot_id] = ExecutionRole(role_str)
                except ValueError:
                    role_override[bot_id] = ExecutionRole.AGENT
        
        return ChatSession(
            session_id=adk_session.id,
            chatbot_id=state.get("chatbot_id", ""),
            user_knox_id=state.get("user_knox_id", adk_session.user_id),
            role_override=role_override,
            active_level=state.get("active_level", 1),
        )
    
    def _chat_to_adk_state(self, chat_session: ChatSession) -> dict[str, Any]:
        """
        ChatSession을 ADK Session state로 변환.
        
        Args:
            chat_session: ChatSession 객체
            
        Returns:
            ADK state dict
        """
        return {
            "chatbot_id": chat_session.chatbot_id,
            "user_knox_id": chat_session.user_knox_id,
            "role_override": {
                k: v.value for k, v in chat_session.role_override.items()
            },
            "active_level": chat_session.active_level,
            "created_at": datetime.utcnow().isoformat(),
        }
    
    # ─────────────────────────────────────────────────────────────────
    # Internal Methods - 레거시 구현 (Fallback)
    # ─────────────────────────────────────────────────────────────────
    
    def _legacy_get_or_create(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: Optional[str] = None,
    ) -> ChatSession:
        """레거시 인메모리 get_or_create 구현."""
        
        # 1. 명시적 session_id로 조회
        if session_id and session_id in self._local_sessions:
            logger.info(f"[ADKSessionWrapper] Found existing session: {session_id}")
            return self._local_sessions[session_id]
        
        # 2. 동일 user + chatbot의 최근 세션 찾기
        recent_session = self._legacy_find_recent_session(user_knox_id, chatbot_id)
        if recent_session:
            logger.info(
                f"[ADKSessionWrapper] Reusing recent session: {recent_session.session_id} "
                f"for {user_knox_id}/{chatbot_id}"
            )
            return recent_session
        
        # 3. 새 세션 생성
        sid = session_id or str(uuid.uuid4())
        session = ChatSession(
            session_id=sid,
            chatbot_id=chatbot_id,
            user_knox_id=user_knox_id,
            role_override={},
            active_level=1,
        )
        self._local_sessions[sid] = session
        logger.info(f"[ADKSessionWrapper] Created new session: {sid}")
        return session
    
    def _legacy_find_recent_session(
        self,
        user_knox_id: str,
        chatbot_id: str,
    ) -> Optional[ChatSession]:
        """레거시 인메모리 최근 세션 찾기."""
        matching = [
            s for s in self._local_sessions.values()
            if s.user_knox_id == user_knox_id and s.chatbot_id == chatbot_id
        ]
        if matching:
            return matching[-1]  # 가장 마지막에 추가된 세션
        return None
    
    # ─────────────────────────────────────────────────────────────────
    # SessionManager 인터페이스 호환성을 위한 추가 메서드
    # ─────────────────────────────────────────────────────────────────
    
    def create_session(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: Optional[str] = None,
        role_override: Optional[dict[str, str]] = None,
        active_level: int = 1,
    ) -> ChatSession:
        """
        새 세션 생성 (SessionManager 인터페이스 호환).
        
        Args:
            chatbot_id: 챗봇 ID
            user_knox_id: 사용자 Knox ID
            session_id: 세션 ID (선택)
            role_override: 역할 오버라이드 설정
            active_level: 활성 레벨
            
        Returns:
            ChatSession 객체
        """
        sid = session_id or str(uuid.uuid4())
        
        # role_override 변환 (str -> ExecutionRole)
        overrides: dict[str, ExecutionRole] = {}
        if role_override:
            for bot_id, role_str in role_override.items():
                try:
                    overrides[bot_id] = ExecutionRole(role_str)
                except ValueError:
                    overrides[bot_id] = ExecutionRole.AGENT
        
        session = ChatSession(
            session_id=sid,
            chatbot_id=chatbot_id,
            user_knox_id=user_knox_id,
            role_override=overrides,
            active_level=active_level,
        )
        
        if USE_ADK and ADK_AVAILABLE and self._session_service:
            # ADK 세션 생성
            state = self._chat_to_adk_state(session)
            self._session_service.create_session(
                app_name="multi_custom_agent",
                user_id=user_knox_id,
                session_id=sid,
                state=state,
            )
            # 로컬 캐시에도 저장 (get_session용)
            self._local_sessions[sid] = session
            logger.info(f"[ADKSessionWrapper] Created ADK session via create_session: {sid}")
        else:
            self._local_sessions[sid] = session
            logger.info(f"[ADKSessionWrapper] Created local session via create_session: {sid}")
        
        return session
    
    def find_recent_session(self, user_knox_id: str, chatbot_id: str) -> Optional[ChatSession]:
        """
        동일 user + chatbot의 가장 최근 세션 찾기.
        
        ADK list_sessions는 async coroutine이므로 sync 함수에서는 호출할 수 없습니다.
        _local_sessions 캐시에서만 검색합니다.
        
        Args:
            user_knox_id: 사용자 Knox ID
            chatbot_id: 챗봇 ID
            
        Returns:
            가장 최근 ChatSession 또는 None
        """
        # _local_sessions 캐시에서만 검색 (ADK sync 호출 불가)
        matching = [
            s for s in self._local_sessions.values()
            if s.user_knox_id == user_knox_id and s.chatbot_id == chatbot_id
        ]
        if matching:
            return matching[-1]
        return None

    async def list_sessions(self, user_knox_id: Optional[str] = None) -> list[dict]:
        """
        세션 목록 조회 (SessionManager 인터페이스 호환).

        ADK list_sessions는 async coroutine이므로 await가 필요합니다.
        create_session에서 await 없이 호출되면 ADK에 저장되지 않으므로
        _local_sessions 캐시를 primary source로, ADK를 secondary로 사용합니다.

        Args:
            user_knox_id: 사용자 Knox ID (선택, 없으면 전체)

        Returns:
            세션 dict 목록
        """
        # 먼저 local 캐시에서 조회 (create_session은 sync로 _local_sessions에 저장)
        local_sessions = list(self._local_sessions.values())
        if user_knox_id:
            local_sessions = [s for s in local_sessions if s.user_knox_id == user_knox_id]
        
        local_count = len(local_sessions)
        logger.info(f"[ADKSessionWrapper] list_sessions: local cache has {local_count} sessions")
        
        # ADK 세션 서비스가 있으면 추가 조회 (병합)
        adk_sessions = []
        if USE_ADK and ADK_AVAILABLE and self._session_service:
            try:
                # ADK list_sessions는 async coroutine → 반드시 await
                all_sessions = await self._session_service.list_sessions(
                    app_name="multi_custom_agent",
                    user_id=user_knox_id or "*",
                )
                adk_sessions = [self._adk_to_chat_session(s) for s in all_sessions]
                logger.info(f"[ADKSessionWrapper] list_sessions: ADK returned {len(adk_sessions)} sessions")
            except Exception as e:
                logger.warning(f"[ADKSessionWrapper] ADK list_sessions error: {e}")
        
        # ADK 결과를 local 캐시에 동기화
        for adk_session in adk_sessions:
            if adk_session.session_id not in self._local_sessions:
                self._local_sessions[adk_session.session_id] = adk_session
                local_count += 1
        
        # 최종 결과: local 캐시 기준 (ADK sync 문제로 인해 local이 더 신뢰할 수 있음)
        result = [s.to_dict() for s in local_sessions]
        logger.info(f"[ADKSessionWrapper] list_sessions: returning {len(result)} sessions (local={local_count}, adk={len(adk_sessions)})")
        return result


# ─────────────────────────────────────────────────────────────────
# 싱글톤 인스턴스 (기존 SessionManager 대체용)
# ─────────────────────────────────────────────────────────────────

_session_wrapper: Optional[ADKSessionWrapper] = None


def get_session_wrapper() -> ADKSessionWrapper:
    """
    ADKSessionWrapper 싱글톤 인스턴스 반환.
    
    Returns:
        ADKSessionWrapper 인스턴스
    """
    global _session_wrapper
    if _session_wrapper is None:
        _session_wrapper = ADKSessionWrapper()
    return _session_wrapper


def reset_session_wrapper() -> None:
    """싱글톤 인스턴스 초기화 (테스트용)."""
    global _session_wrapper
    _session_wrapper = None
