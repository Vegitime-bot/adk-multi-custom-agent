"""
backend/adk/adk_storage_backend.py - ADK Storage Backend

Google ADK 기반의 Storage Backend 구현체.
USE_ADK=true 시 ADK 세션 및 메모리 서비스를 사용합니다.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime
from typing import Optional, Any

from backend.core.storage_backend import SessionStorageBackend, MemoryStorageBackend
from backend.core.models import ChatSession, ExecutionRole, Message

logger = logging.getLogger(__name__)

# ADK 사용 가능 여부 확인
try:
    from google.adk.sessions import Session
    from google.adk.sessions.in_memory_session_service import InMemorySessionService
    from google.adk.memory import InMemoryMemoryService
    from google.genai import types as genai_types
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    Session = Any
    InMemorySessionService = Any
    InMemoryMemoryService = Any
    genai_types = Any
    logging.warning("ADK not available. Install with: pip install google-adk")


class ADKSessionStorage(SessionStorageBackend):
    """
    ADK 기반 Session Storage Backend.
    
    ADK InMemorySessionService를 사용하여 세션을 관리합니다.
    """
    
    def __init__(self):
        self._session_service: Optional[InMemorySessionService] = None
        self._local_cache: dict[str, ChatSession] = {}
        self._initialized = False
    
    def is_available(self) -> bool:
        """ADK가 사용 가능한지 확인합니다."""
        return ADK_AVAILABLE
    
    def initialize(self) -> bool:
        """ADK Session Service를 초기화합니다."""
        if not ADK_AVAILABLE:
            logger.warning("[ADKSessionStorage] ADK not available")
            return False
        
        try:
            self._session_service = InMemorySessionService()
            self._local_cache = {}
            self._initialized = True
            logger.info("[ADKSessionStorage] Initialized with ADK InMemorySessionService")
            return True
        except Exception as e:
            logger.error(f"[ADKSessionStorage] Failed to initialize: {e}")
            return False
    
    def shutdown(self) -> None:
        """ADK Session Service를 종료합니다."""
        self._session_service = None
        self._local_cache.clear()
        self._initialized = False
        logger.info("[ADKSessionStorage] Shutdown")
    
    def _adk_to_chat_session(self, adk_session: Session) -> ChatSession:
        """ADK Session을 ChatSession으로 변환합니다."""
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
        """ChatSession을 ADK Session state로 변환합니다."""
        return {
            "chatbot_id": chat_session.chatbot_id,
            "user_knox_id": chat_session.user_knox_id,
            "role_override": {
                k: v.value for k, v in chat_session.role_override.items()
            },
            "active_level": chat_session.active_level,
            "created_at": datetime.utcnow().isoformat(),
        }
    
    def create_session(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: Optional[str] = None,
        role_override: Optional[dict[str, str]] = None,
        active_level: int = 1,
    ) -> ChatSession:
        """새 ADK 세션을 생성합니다."""
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
        
        # ADK 세션 생성
        state = self._chat_to_adk_state(session)
        adk_session = self._session_service.create_session(
            app_name="multi_custom_agent",
            user_id=user_knox_id,
            session_id=sid,
            state=state,
        )
        
        # 로컬 캐시에 저장
        chat_session = self._adk_to_chat_session(adk_session)
        self._local_cache[sid] = chat_session
        
        logger.info(f"[ADKSessionStorage] Created ADK session: {sid}")
        return chat_session
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """세션 ID로 ADK 세션을 조회합니다."""
        # 로컬 캐시에서 먼저 확인
        if session_id in self._local_cache:
            return self._local_cache[session_id]
        
        # ADK에서 세션 검색
        try:
            all_sessions = self._session_service.list_sessions(
                app_name="multi_custom_agent",
                user_id="*",
            )
            for session in all_sessions:
                if session.session_id == session_id:
                    chat_session = self._adk_to_chat_session(session)
                    self._local_cache[session_id] = chat_session
                    return chat_session
        except Exception:
            # list_sessions 실패 시 내부 _sessions 순회
            if hasattr(self._session_service, '_sessions'):
                for key, session in self._session_service._sessions.items():
                    if session.session_id == session_id:
                        chat_session = self._adk_to_chat_session(session)
                        self._local_cache[session_id] = chat_session
                        return chat_session
        
        return None
    
    def find_recent_session(
        self,
        user_knox_id: str,
        chatbot_id: str,
    ) -> Optional[ChatSession]:
        """동일 user + chatbot의 가장 최근 ADK 세션을 찾습니다."""
        try:
            sessions = self._session_service.list_sessions(
                app_name="multi_custom_agent",
                user_id=user_knox_id,
            )
        except Exception:
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
            def get_time(s):
                created = s.state.get("created_at", "") if s.state else ""
                return created
            
            matching.sort(key=get_time, reverse=True)
            return self._adk_to_chat_session(matching[0])
        
        return None
    
    def close_session(self, session_id: str) -> bool:
        """ADK 세션을 종료하고 제거합니다."""
        # 로컬 캐시에서 제거
        local_removed = False
        if session_id in self._local_cache:
            del self._local_cache[session_id]
            local_removed = True
        
        # ADK에서 세션 제거
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
    
    def list_sessions(self, user_knox_id: Optional[str] = None) -> list[dict]:
        """ADK 세션 목록을 조회합니다."""
        try:
            all_sessions = self._session_service.list_sessions(
                app_name="multi_custom_agent",
                user_id=user_knox_id or "*",
            )
            return [self._adk_to_chat_session(s).to_dict() for s in all_sessions]
        except Exception:
            sessions = getattr(self._session_service, '_sessions', {})
            result = []
            for key, s in sessions.items():
                if user_knox_id is None or s.user_id == user_knox_id:
                    result.append(self._adk_to_chat_session(s).to_dict())
            return result


class ADKMemoryStorage(MemoryStorageBackend):
    """
    ADK 기반 Memory Storage Backend.
    
    ADK InMemoryMemoryService를 사용하여 대화 메모리를 관리합니다.
    """
    
    def __init__(self):
        self._adk_memory: Optional[InMemoryMemoryService] = None
        self._local_cache: dict[tuple[str, str], list[Message]] = {}
        self._initialized = False
    
    def _key(self, chatbot_id: str, session_id: str) -> tuple[str, str]:
        """내부 저장용 키를 생성합니다."""
        return (chatbot_id, session_id)
    
    def is_available(self) -> bool:
        """ADK가 사용 가능한지 확인합니다."""
        return ADK_AVAILABLE
    
    def initialize(self) -> bool:
        """ADK Memory Service를 초기화합니다."""
        if not ADK_AVAILABLE:
            logger.warning("[ADKMemoryStorage] ADK not available")
            return False
        
        try:
            self._adk_memory = InMemoryMemoryService()
            self._local_cache = {}
            self._initialized = True
            logger.info("[ADKMemoryStorage] Initialized with ADK InMemoryMemoryService")
            return True
        except Exception as e:
            logger.error(f"[ADKMemoryStorage] Failed to initialize: {e}")
            return False
    
    def shutdown(self) -> None:
        """ADK Memory Service를 종료합니다."""
        self._adk_memory = None
        self._local_cache.clear()
        self._initialized = False
        logger.info("[ADKMemoryStorage] Shutdown")
    
    def _to_adk_content(self, message: Message) -> Any:
        """Message를 ADK Content 형식으로 변환합니다."""
        if not ADK_AVAILABLE or self._adk_memory is None:
            return None
        
        adk_role = "model" if message.role == "assistant" else message.role
        content = genai_types.Content(
            parts=[genai_types.Part(text=message.content)],
            role=adk_role
        )
        return content
    
    def _from_adk_content(self, content: Any, role: str) -> Message:
        """ADK Content를 Message로 변환합니다."""
        if content is None:
            return Message(role=role, content="")
        
        text_parts = []
        if hasattr(content, 'parts') and content.parts:
            for part in content.parts:
                if hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)
        
        if not text_parts and hasattr(content, 'text'):
            text_parts.append(content.text)
        
        content_text = "\n".join(text_parts) if text_parts else ""
        return Message(role=role, content=content_text)
    
    def get_history(self, chatbot_id: str, session_id: str) -> list[Message]:
        """지정된 챗봇/세션의 대화 기록을 반환합니다."""
        key = self._key(chatbot_id, session_id)
        
        # 로컬 캐시에서 확인
        if key in self._local_cache:
            return list(self._local_cache[key])
        
        # ADK 메모리에서 조회
        try:
            adk_session_id = f"{chatbot_id}:{session_id}"
            session_state = self._adk_memory.get_state(
                app_name="adk_multi_agent",
                user_id=session_id,
                session_id=adk_session_id
            )
            
            if session_state and hasattr(session_state, 'messages'):
                messages = []
                for msg in session_state.messages:
                    role = "assistant" if msg.role == "model" else msg.role
                    content_msg = self._from_adk_content(msg.content, role)
                    messages.append(content_msg)
                
                self._local_cache[key] = messages
                return messages
        except Exception:
            pass
        
        return []
    
    def append(self, chatbot_id: str, session_id: str, message: Message) -> None:
        """단일 메시지를 ADK 메모리에 저장합니다."""
        key = self._key(chatbot_id, session_id)
        
        # 로컬 캐시에 추가
        if key not in self._local_cache:
            self._local_cache[key] = []
        self._local_cache[key].append(message)
        
        # ADK 메모리에도 저장
        try:
            adk_session_id = f"{chatbot_id}:{session_id}"
            adk_content = self._to_adk_content(message)
            if adk_content:
                self._adk_memory.add_message(
                    app_name="adk_multi_agent",
                    user_id=session_id,
                    session_id=adk_session_id,
                    message=adk_content
                )
        except Exception:
            pass
    
    def append_pair(
        self,
        chatbot_id: str,
        session_id: str,
        user_content: str,
        assistant_content: str,
        max_messages: int = 20,
    ) -> None:
        """사용자 메시지와 어시스턴트 메시지를 함께 저장하고 길이를 제한합니다."""
        key = self._key(chatbot_id, session_id)
        
        # 로컬 캐시에 추가
        if key not in self._local_cache:
            self._local_cache[key] = []
        
        user_msg = Message(role="user", content=user_content)
        assistant_msg = Message(role="assistant", content=assistant_content)
        
        self._local_cache[key].append(user_msg)
        self._local_cache[key].append(assistant_msg)
        
        # 최대 메시지 수 유지
        if max_messages > 0 and len(self._local_cache[key]) > max_messages:
            excess = len(self._local_cache[key]) - max_messages
            if excess % 2 != 0:
                excess += 1
            self._local_cache[key] = self._local_cache[key][excess:]
        
        # ADK 메모리에도 저장
        try:
            adk_session_id = f"{chatbot_id}:{session_id}"
            
            user_adk = self._to_adk_content(user_msg)
            if user_adk:
                self._adk_memory.add_message(
                    app_name="adk_multi_agent",
                    user_id=session_id,
                    session_id=adk_session_id,
                    message=user_adk
                )
            
            assistant_adk = self._to_adk_content(assistant_msg)
            if assistant_adk:
                self._adk_memory.add_message(
                    app_name="adk_multi_agent",
                    user_id=session_id,
                    session_id=adk_session_id,
                    message=assistant_adk
                )
            
            if max_messages > 0:
                self._adk_memory.trim_messages(
                    app_name="adk_multi_agent",
                    user_id=session_id,
                    session_id=adk_session_id,
                    max_messages=max_messages
                )
        except Exception:
            pass
    
    def clear(self, chatbot_id: str, session_id: str) -> None:
        """지정된 챗봇/세션의 대화 기록을 삭제합니다."""
        key = self._key(chatbot_id, session_id)
        self._local_cache.pop(key, None)
        
        try:
            adk_session_id = f"{chatbot_id}:{session_id}"
            self._adk_memory.delete_session(
                app_name="adk_multi_agent",
                user_id=session_id,
                session_id=adk_session_id
            )
        except Exception:
            pass
    
    def clear_all_for_session(self, session_id: str) -> None:
        """특정 세션에 속한 모든 챗봇 메모리를 삭제합니다."""
        keys_to_remove = [k for k in self._local_cache if k[1] == session_id]
        for k in keys_to_remove:
            del self._local_cache[k]
        
        try:
            for k in keys_to_remove:
                adk_session_id = f"{k[0]}:{k[1]}"
                try:
                    self._adk_memory.delete_session(
                        app_name="adk_multi_agent",
                        user_id=session_id,
                        session_id=adk_session_id
                    )
                except Exception:
                    pass
        except Exception:
            pass
    
    def get_all_keys(self) -> list[tuple[str, str]]:
        """디버깅용: 저장된 모든 키를 반환합니다."""
        return list(self._local_cache.keys())