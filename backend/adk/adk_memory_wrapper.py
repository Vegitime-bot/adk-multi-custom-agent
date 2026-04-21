"""
adk/adk_memory_wrapper.py - Google ADK 기반 MemoryWrapper

ADK 1.31.1 기준으로 구현된 메모리 래퍼.
기존 MemoryManager 인터페이스와 100% 호환되도록 설계됨.
USE_ADK 플래그로 ADK/인메모리 구현체 전환 가능.

Key: (chatbot_id, session_id) → 격리 원칙 유지
"""

from __future__ import annotations

import os
from typing import Any, Optional

from backend.core.models import Message

# ADK 사용 여부 플래그
USE_ADK = os.environ.get("USE_ADK", "false").lower() == "true"

# ADK 타입 임포트 (사용 가능한 경우)
try:
    from google.adk.agents import Agent
    from google.adk.memory import InMemoryMemoryService
    from google.adk.sessions import Session
    from google.genai import types as genai_types
    
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    # ADK가 없을 때 타입 스텁
    Agent = Any
    InMemoryMemoryService = Any
    Session = Any
    genai_types = Any


class ADKMemoryWrapper:
    """
    Google ADK 기반 메모리 관리자.
    
    기존 MemoryManager와 동일한 인터페이스 제공:
    - get_history(chatbot_id, session_id) → list[Message]
    - append_pair(chatbot_id, session_id, user_msg, assistant_msg)
    - clear(chatbot_id, session_id)
    - get_all_keys() → list[tuple[str, str]]
    
    내부적으로 ADK의 InMemoryMemoryService를 활용하며,
    (chatbot_id, session_id) 튜플을 키로 사용하여
    각 챗봇/세션 조합별로 완전히 격리된 대화 기록을 유지함.
    """
    
    def __init__(self):
        self._store: dict[tuple[str, str], list[Message]] = {}
        
        # ADK 메모리 서비스 초기화 (사용 가능한 경우)
        if USE_ADK and ADK_AVAILABLE:
            self._adk_memory = InMemoryMemoryService()
        else:
            self._adk_memory = None
    
    def _key(self, chatbot_id: str, session_id: str) -> tuple[str, str]:
        """내부 저장용 키 생성."""
        return (chatbot_id, session_id)
    
    def _to_adk_content(self, message: Message) -> Any:
        """
        Message dataclass를 ADK Content 형식으로 변환.
        
        ADK 1.31.1 기준:
        - Content는 parts 리스트를 가짐
        - Part는 text 필드를 가짐
        - Message는 Content와 author(role)을 가짐
        """
        if not ADK_AVAILABLE or self._adk_memory is None:
            return None
        
        # genai_types.Content 생성
        # role: "user" 또는 "model" (ADK에서는 assistant를 model로 표현)
        adk_role = "model" if message.role == "assistant" else message.role
        
        # Content with parts
        content = genai_types.Content(
            parts=[genai_types.Part(text=message.content)],
            role=adk_role
        )
        return content
    
    def _from_adk_content(self, content: Any, role: str) -> Message:
        """
        ADK Content/Message 형식을 Message dataclass로 변환.
        
        Args:
            content: ADK Content 객체
            role: 역할 정보 ("user" | "assistant")
        """
        if content is None:
            return Message(role=role, content="")
        
        # Content.parts에서 텍스트 추출
        text_parts = []
        if hasattr(content, 'parts') and content.parts:
            for part in content.parts:
                if hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)
        
        # Content에서 직접 텍스트 추출 (fallback)
        if not text_parts and hasattr(content, 'text'):
            text_parts.append(content.text)
        
        content_text = "\n".join(text_parts) if text_parts else ""
        
        return Message(role=role, content=content_text)
    
    def get_history(self, chatbot_id: str, session_id: str) -> list[Message]:
        """
        지정된 챗봇/세션의 대화 기록을 반환.
        
        Args:
            chatbot_id: 챗봇 ID
            session_id: 세션 ID
            
        Returns:
            Message 객체 리스트 (user/assistant 쌍)
        """
        key = self._key(chatbot_id, session_id)
        
        # 내부 저장소에서 조회
        if key in self._store:
            return list(self._store[key])
        
        # ADK 메모리에서 조회 (활성화된 경우)
        if USE_ADK and self._adk_memory is not None and ADK_AVAILABLE:
            # ADK 세션 ID 형식: "{chatbot_id}:{session_id}"
            adk_session_id = f"{chatbot_id}:{session_id}"
            
            try:
                # ADK 메모리에서 상태 조회
                session_state = self._adk_memory.get_state(
                    app_name="adk_multi_agent",
                    user_id=session_id,
                    session_id=adk_session_id
                )
                
                if session_state and hasattr(session_state, 'messages'):
                    messages = []
                    for msg in session_state.messages:
                        # ADK Message에서 role과 content 추출
                        role = "assistant" if msg.role == "model" else msg.role
                        content_msg = self._from_adk_content(msg.content, role)
                        messages.append(content_msg)
                    
                    # 내부 캐시 업데이트
                    self._store[key] = messages
                    return messages
            except Exception:
                # ADK 조회 실패 시 빈 리스트 반환
                pass
        
        return []
    
    def append(self, chatbot_id: str, session_id: str, message: Message) -> None:
        """
        단일 메시지를 저장.
        
        Args:
            chatbot_id: 챗봇 ID
            session_id: 세션 ID
            message: 저장할 Message 객체
        """
        key = self._key(chatbot_id, session_id)
        
        # 내부 저장소에 추가
        if key not in self._store:
            self._store[key] = []
        self._store[key].append(message)
        
        # ADK 메모리에도 저장 (활성화된 경우)
        if USE_ADK and self._adk_memory is not None and ADK_AVAILABLE:
            try:
                adk_session_id = f"{chatbot_id}:{session_id}"
                
                # ADK Content로 변환
                adk_content = self._to_adk_content(message)
                if adk_content:
                    # ADK 메모리에 메시지 추가
                    self._adk_memory.add_message(
                        app_name="adk_multi_agent",
                        user_id=session_id,
                        session_id=adk_session_id,
                        message=adk_content
                    )
            except Exception:
                # ADK 저장 실패 시 무시 (내부 저장소에만 유지)
                pass
    
    def append_pair(
        self,
        chatbot_id: str,
        session_id: str,
        user_content: str,
        assistant_content: str,
        max_messages: int = 20,
    ) -> None:
        """
        사용자 메시지와 어시스턴트 메시지를 함께 저장하고 길이를 제한.
        
        Args:
            chatbot_id: 챗봇 ID
            session_id: 세션 ID
            user_content: 사용자 메시지 내용
            assistant_content: 어시스턴트 메시지 내용
            max_messages: 최대 메시지 수 (0은 무제한)
        """
        key = self._key(chatbot_id, session_id)
        
        # 내부 저장소에 추가
        if key not in self._store:
            self._store[key] = []
        
        user_msg = Message(role="user", content=user_content)
        assistant_msg = Message(role="assistant", content=assistant_content)
        
        self._store[key].append(user_msg)
        self._store[key].append(assistant_msg)
        
        # 최대 메시지 수 유지 (오래된 것부터 제거, 최소 단위 2개씩)
        if max_messages > 0 and len(self._store[key]) > max_messages:
            excess = len(self._store[key]) - max_messages
            # 짝수 단위로 제거해 user/assistant 쌍을 보존
            if excess % 2 != 0:
                excess += 1
            self._store[key] = self._store[key][excess:]
        
        # ADK 메모리에도 저장 (활성화된 경우)
        if USE_ADK and self._adk_memory is not None and ADK_AVAILABLE:
            try:
                adk_session_id = f"{chatbot_id}:{session_id}"
                
                # 사용자 메시지 추가
                user_adk = self._to_adk_content(user_msg)
                if user_adk:
                    self._adk_memory.add_message(
                        app_name="adk_multi_agent",
                        user_id=session_id,
                        session_id=adk_session_id,
                        message=user_adk
                    )
                
                # 어시스턴트 메시지 추가
                assistant_adk = self._to_adk_content(assistant_msg)
                if assistant_adk:
                    self._adk_memory.add_message(
                        app_name="adk_multi_agent",
                        user_id=session_id,
                        session_id=adk_session_id,
                        message=assistant_adk
                    )
                
                # ADK 메모리 정리 (max_messages 제한 적용)
                if max_messages > 0:
                    self._adk_memory.trim_messages(
                        app_name="adk_multi_agent",
                        user_id=session_id,
                        session_id=adk_session_id,
                        max_messages=max_messages
                    )
            except Exception:
                # ADK 저장 실패 시 내부 저장소만 유지
                pass
    
    def clear(self, chatbot_id: str, session_id: str) -> None:
        """
        지정된 챗봇/세션의 대화 기록을 삭제.
        
        Args:
            chatbot_id: 챗봇 ID
            session_id: 세션 ID
        """
        key = self._key(chatbot_id, session_id)
        
        # 내부 저장소에서 삭제
        self._store.pop(key, None)
        
        # ADK 메모리에서도 삭제 (활성화된 경우)
        if USE_ADK and self._adk_memory is not None and ADK_AVAILABLE:
            try:
                adk_session_id = f"{chatbot_id}:{session_id}"
                self._adk_memory.delete_session(
                    app_name="adk_multi_agent",
                    user_id=session_id,
                    session_id=adk_session_id
                )
            except Exception:
                # ADK 삭제 실패 시 무시
                pass
    
    def clear_all_for_session(self, session_id: str) -> None:
        """
        특정 세션에 속한 모든 챗봇 메모리를 삭제.
        
        Args:
            session_id: 세션 ID
        """
        # 내부 저장소에서 삭제
        keys_to_remove = [k for k in self._store if k[1] == session_id]
        for k in keys_to_remove:
            del self._store[k]
        
        # ADK 메모리에서도 삭제 (활성화된 경우)
        if USE_ADK and self._adk_memory is not None and ADK_AVAILABLE:
            try:
                # 해당 세션의 모든 챗봿 메모리 삭제
                # ADK API는 특정 패턴으로 삭제하는 기능이 제한적이므로
                # 개별적으로 삭제 시도
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
        """
        디버깅용: 저장된 모든 키 반환.
        
        Returns:
            (chatbot_id, session_id) 튜플 리스트
        """
        return list(self._store.keys())
    
    def is_adk_available(self) -> bool:
        """
        ADK 사용 가능 여부 확인.
        
        Returns:
            ADK가 사용 가능하고 활성화된 경우 True
        """
        return USE_ADK and ADK_AVAILABLE and self._adk_memory is not None


# 하위호환: MemoryManager와 동일한 인터페이스 제공
# 기존 코드에서 from backend.managers.memory_manager import MemoryManager
# 대신 from backend.adk.adk_memory_wrapper import ADKMemoryWrapper as MemoryManager
# 로 교체 가능
MemoryManager = ADKMemoryWrapper
