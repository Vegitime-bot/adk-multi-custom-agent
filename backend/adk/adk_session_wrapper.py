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


@dataclass
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
        
        adk_session = self._session_service.create_session(
            app_name="multi_custom_agent",
            user_id=user_knox_id,
            session_id=new_session_id,
            state=state,
        )
        
        logger.info(f"[ADKSessionWrapper] Created new ADK session: {new_session_id}")
        return self._adk_to_chat_session(adk_session)
    
    def _adk_get_session(self, session_id: str) -> Optional[ChatSession]:
        """ADK 기반 세션 조회."""
        # ADK는 user_id가 필요하므로, 모든 사용자 세션을 검색해야 함
        # 실제로는 user_knox_id를 알아야 하지만, 인메모리 구현에서는 순회 가능
        sessions = self._session_service._sessions if hasattr(
            self._session_service, '_sessions'
        ) else {}
        
        for key, session in sessions.items():
            if session.session_id == session_id:
                return self._adk_to_chat_session(session)
        
        return None
    
    def _adk_close_session(self, session_id: str) -> bool:
        """ADK 기반 세션 종료."""
        # ADK InMemorySessionService는 delete_session이 없으므로 
        # 내부 _sessions dict에서 직접 제거
        if hasattr(self._session_service, '_sessions'):
            sessions = self._session_service._sessions
            keys_to_remove = [
                key for key, session in sessions.items()
                if session.session_id == session_id
            ]
            for key in keys_to_remove:
                del sessions[key]
            return len(keys_to_remove) > 0
        return False
    
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
        """ADK 기반 최근 세션 찾기."""
        # 사용자별 세션 목록 가져오기
        try:
            sessions = self._session_service.list_sessions(
                app_name="multi_custom_agent",
                user_id=user_knox_id,
            )
        except Exception:
            # list_sessions 미지원 시 내부 _sessions 속성 사용
            sessions = [
                s for s in getattr(self._session_service, '_sessions', {}).values()
                if s.user_id == user_knox_id
            ]
        
        matching = []
        for session in sessions:
            state = session.state or {}
            if state.get("chatbot_id") == chatbot_id:
                matching.append(session)
        
        if matching:
            # created_at 기준으로 정렬 (없으면 events 기반)
            def get_time(s):
                created = s.state.get("created_at", "")
                return created if created else ""
            
            matching.sort(key=get_time, reverse=True)
            return self._adk_to_chat_session(matching[0])
        
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
            session_id=adk_session.session_id,
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
            logger.info(f"[ADKSessionWrapper] Created ADK session via create_session: {sid}")
        else:
            self._local_sessions[sid] = session
            logger.info(f"[ADKSessionWrapper] Created local session via create_session: {sid}")
        
        return session
    
    def find_recent_session(self, user_knox_id: str, chatbot_id: str) -> Optional[ChatSession]:
        """
        동일 user + chatbot의 가장 최근 세션 찾기.
        
        Args:
            user_knox_id: 사용자 Knox ID
            chatbot_id: 챗봇 ID
            
        Returns:
            가장 최근 ChatSession 또는 None
        """
        if USE_ADK and ADK_AVAILABLE and self._session_service:
            try:
                # ADK에서 세션 목록 조회
                all_sessions = self._session_service.list_sessions(
                    app_name="multi_custom_agent",
                    user_id=user_knox_id,
                )
                
                # chatbot_id가 일치하는 세션 찾기
                matching = []
                for s in all_sessions:
                    if s.state and s.state.get("chatbot_id") == chatbot_id:
                        matching.append(s)
                
                if matching:
                    # 생성 시간 기준으로 정렬하여 가장 최근 것 반환
                    # ADK Session에는 create_time 속성이 있음
                    matching.sort(key=lambda s: getattr(s, 'create_time', ''), reverse=True)
                    return self._adk_to_chat_session(matching[0])
                    
            except Exception as e:
                logger.warning(f"[ADKSessionWrapper] find_recent_session error: {e}")
                pass
        
        # Fallback: 로컬 세션에서 검색
        matching = [
            s for s in self._local_sessions.values()
            if s.user_knox_id == user_knox_id and s.chatbot_id == chatbot_id
        ]
        if matching:
            return matching[-1]
        return None

    def list_sessions(self, user_knox_id: Optional[str] = None) -> list[dict]:
        """
        세션 목록 조회 (SessionManager 인터페이스 호환).
        
        Args:
            user_knox_id: 사용자 Knox ID (선택, 없으면 전체)
            
        Returns:
            세션 dict 목록
        """
        if USE_ADK and ADK_AVAILABLE and self._session_service:
            try:
                all_sessions = self._session_service.list_sessions(
                    app_name="multi_custom_agent",
                    user_id=user_knox_id or "*",
                )
                return [self._adk_to_chat_session(s).to_dict() for s in all_sessions]
            except Exception:
                # list_sessions 미지원 시 내부 순회
                sessions = getattr(self._session_service, '_sessions', {})
                result = []
                for key, s in sessions.items():
                    if user_knox_id is None or s.user_id == user_knox_id:
                        result.append(self._adk_to_chat_session(s).to_dict())
                return result
        else:
            sessions = self._local_sessions.values()
            if user_knox_id:
                sessions = [s for s in sessions if s.user_knox_id == user_knox_id]
            return [s.to_dict() for s in sessions]


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
