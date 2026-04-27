"""
backend/repository/mock_repository.py - Mock Repository for PostgreSQL
PostgreSQL 없이 파일 기반으로 동작하는 Repository
"""
import json
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4, UUID
from pathlib import Path

# config에서 설정 가져오기
from config import settings

# 데이터 저장 경로 (config.py에서 설정)
DATA_DIR = settings.MOCK_DATA_DIR
SESSIONS_FILE = settings.MOCK_SESSIONS_FILE
MESSAGES_DIR = settings.MOCK_MESSAGES_DIR


def _ensure_data_dir():
    """데이터 디렉토리 생성"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MESSAGES_DIR.mkdir(parents=True, exist_ok=True)


def _load_sessions() -> Dict[str, Any]:
    """세션 데이터 로드"""
    _ensure_data_dir()
    if SESSIONS_FILE.exists():
        return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    return {}


def _save_sessions(sessions: Dict[str, Any]):
    """세션 데이터 저장"""
    _ensure_data_dir()
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _load_messages(session_id: str) -> List[Dict]:
    """메시지 데이터 로드"""
    msg_file = MESSAGES_DIR / f"{session_id}.json"
    if msg_file.exists():
        return json.loads(msg_file.read_text(encoding="utf-8"))
    return []


def _save_messages(session_id: str, messages: List[Dict]):
    """메시지 데이터 저장"""
    msg_file = MESSAGES_DIR / f"{session_id}.json"
    msg_file.write_text(json.dumps(messages, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


class MockSessionRepository:
    """목업 세션 저장소"""
    
    def create(self, user_id: str, chatbot_id: str, 
               session_id: Optional[str] = None) -> Dict[str, Any]:
        """새 세션 생성"""
        sessions = _load_sessions()
        
        sid = session_id or str(uuid4())
        session = {
            "session_id": sid,
            "user_id": user_id,
            "chatbot_id": chatbot_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "last_accessed": datetime.utcnow().isoformat(),
            "message_count": 0
        }
        
        sessions[sid] = session
        _save_sessions(sessions)
        return session
    
    def get_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """ID로 세션 조회"""
        sessions = _load_sessions()
        session = sessions.get(session_id)
        if session:
            # last_accessed 업데이트
            session["last_accessed"] = datetime.utcnow().isoformat()
            _save_sessions(sessions)
        return session
    
    def list_by_user(self, user_id: str, limit: int = 30, 
                     offset: int = 0) -> List[Dict[str, Any]]:
        """사용자별 세션 목록"""
        sessions = _load_sessions()
        user_sessions = [
            s for s in sessions.values() 
            if s.get("user_id") == user_id
        ]
        # last_accessed 기준 정렬 (최근 순)
        user_sessions.sort(
            key=lambda x: x.get("last_accessed", ""), 
            reverse=True
        )
        return user_sessions[offset:offset + limit]
    
    def update_last_accessed(self, session_id: str) -> bool:
        """last_accessed 업데이트"""
        sessions = _load_sessions()
        if session_id in sessions:
            sessions[session_id]["last_accessed"] = datetime.utcnow().isoformat()
            _save_sessions(sessions)
            return True
        return False
    
    def delete_old_sessions(self, days: int = 30) -> int:
        """오래된 세션 삭제"""
        sessions = _load_sessions()
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        to_delete = []
        for sid, session in sessions.items():
            last_accessed = session.get("last_accessed")
            if last_accessed:
                try:
                    accessed = datetime.fromisoformat(last_accessed)
                    if accessed < cutoff:
                        to_delete.append(sid)
                except:
                    pass
        
        for sid in to_delete:
            del sessions[sid]
            # 관련 메시지 파일도 삭제
            msg_file = MESSAGES_DIR / f"{sid}.json"
            if msg_file.exists():
                msg_file.unlink()
        
        _save_sessions(sessions)
        return len(to_delete)
    
    def get_user_session_count(self, user_id: str) -> int:
        """사용자별 세션 총 개수"""
        sessions = _load_sessions()
        return len([s for s in sessions.values() if s.get("user_id") == user_id])


class MockMessageRepository:
    """목업 메시지 저장소"""
    
    def create(self, session_id: str, role: str, content: str,
               tokens_used: int = 0, latency_ms: int = 0,
               confidence_score: Optional[float] = None,
               delegated_to: Optional[str] = None) -> Dict[str, Any]:
        """메시지 생성"""
        messages = _load_messages(session_id)
        
        message = {
            "message_id": len(messages) + 1,
            "session_id": session_id,
            "role": role,
            "content": content,
            "tokens_used": tokens_used,
            "latency_ms": latency_ms,
            "confidence_score": confidence_score,
            "delegated_to": delegated_to,
            "created_at": datetime.utcnow().isoformat()
        }
        
        messages.append(message)
        _save_messages(session_id, messages)
        
        # 세션 메시지 카운트 업데이트
        sessions = _load_sessions()
        if session_id in sessions:
            sessions[session_id]["message_count"] = len(messages)
            sessions[session_id]["updated_at"] = datetime.utcnow().isoformat()
            _save_sessions(sessions)
        
        return message
    
    def get_by_session(self, session_id: str, limit: int = 30,
                       offset: int = 0) -> List[Dict[str, Any]]:
        """세션별 메시지 조회"""
        messages = _load_messages(session_id)
        # 시간순 정렬
        messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return messages[offset:offset + limit]
    
    def get_by_session_all(self, session_id: str) -> List[Dict[str, Any]]:
        """세션별 모든 메시지 조회"""
        messages = _load_messages(session_id)
        messages.sort(key=lambda x: x.get("created_at", ""))
        return messages
    
    def get_message_count(self, session_id: str) -> int:
        """세션별 메시지 총 개수"""
        messages = _load_messages(session_id)
        return len(messages)


class MockDelegationRepository:
    """목업 위임 체인 저장소"""
    
    def __init__(self):
        self._chains: Dict[str, List[Dict]] = {}
    
    def create(self, session_id: str, parent_agent: str, 
               child_agent: str, delegation_reason: Optional[str] = None,
               confidence_score: Optional[float] = None) -> Dict[str, Any]:
        """위임 기록 생성"""
        if session_id not in self._chains:
            self._chains[session_id] = []
        
        chain = {
            "id": len(self._chains[session_id]) + 1,
            "session_id": session_id,
            "parent_agent": parent_agent,
            "child_agent": child_agent,
            "delegation_reason": delegation_reason,
            "confidence_score": confidence_score,
            "created_at": datetime.utcnow().isoformat()
        }
        
        self._chains[session_id].append(chain)
        return chain
    
    def get_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """세션별 위임 체인 조회"""
        return self._chains.get(session_id, [])
    
    def get_chain_path(self, session_id: str) -> List[Dict[str, Any]]:
        """위임 경로 반환"""
        chains = self.get_by_session(session_id)
        return [
            {
                "from": c["parent_agent"],
                "to": c["child_agent"],
                "reason": c.get("delegation_reason"),
                "confidence": c.get("confidence_score"),
                "time": c.get("created_at")
            }
            for c in chains
        ]
