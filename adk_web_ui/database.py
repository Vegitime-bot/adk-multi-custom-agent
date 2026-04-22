"""
Database Layer for ADK Web UI
PostgreSQL + SQLite 지원
"""

import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
from pathlib import Path

from config import settings


# ============================================
# Connection Management
# ============================================

def get_db_connection():
    """DB 연결 반환 (PostgreSQL 또는 SQLite)"""
    if settings.USE_SQLITE:
        return _get_sqlite_connection()
    return _get_postgres_connection()


def _get_postgres_connection():
    """PostgreSQL 연결"""
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD
    )


def _get_sqlite_connection():
    """SQLite 연결"""
    db_path = Path(settings.SQLITE_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    """컨텍스트 매니저용 DB 연결"""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================
# User Operations
# ============================================

def get_or_create_user(knox_id: str) -> Dict[str, Any]:
    """사용자 조회 또는 생성"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 먼저 조회
        if settings.USE_SQLITE:
            cursor.execute('SELECT * FROM users WHERE knox_id = ?', (knox_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            # 없으면 생성
            cursor.execute('''
                INSERT INTO users (knox_id, last_active, is_admin)
                VALUES (?, CURRENT_TIMESTAMP, 0)
            ''', (knox_id,))
        else:
            cursor.execute('SELECT * FROM users WHERE knox_id = %s', (knox_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            cursor.execute('''
                INSERT INTO users (knox_id, last_active, is_admin)
                VALUES (%s, CURRENT_TIMESTAMP, 0)
            ''', (knox_id,))
        
        # 생성된 사용자 반환
        cursor.execute(
            'SELECT * FROM users WHERE knox_id = ?' if settings.USE_SQLITE 
            else 'SELECT * FROM users WHERE knox_id = %s',
            (knox_id,)
        )
        return dict(cursor.fetchone())


def update_user_last_active(knox_id: str) -> None:
    """사용자 마지막 활동 시간 업데이트"""
    with get_db() as conn:
        cursor = conn.cursor()
        if settings.USE_SQLITE:
            cursor.execute('''
                UPDATE users SET last_active = CURRENT_TIMESTAMP
                WHERE knox_id = ?
            ''', (knox_id,))
        else:
            cursor.execute('''
                UPDATE users SET last_active = CURRENT_TIMESTAMP
                WHERE knox_id = %s
            ''', (knox_id,))


def is_admin(knox_id: str) -> bool:
    """관리자 여부 확인"""
    # 환경변수 기준 먼저 체크
    if knox_id in settings.ADMIN_KNOX_LIST:
        return True
    
    # DB 기준 체크
    with get_db() as conn:
        cursor = conn.cursor()
        if settings.USE_SQLITE:
            cursor.execute(
                'SELECT is_admin FROM users WHERE knox_id = ?',
                (knox_id,)
            )
        else:
            cursor.execute(
                'SELECT is_admin FROM users WHERE knox_id = %s',
                (knox_id,)
            )
        row = cursor.fetchone()
        return bool(row and row[0])


def set_admin(knox_id: str, is_admin_flag: bool = True) -> None:
    """관리자 설정"""
    with get_db() as conn:
        cursor = conn.cursor()
        # 사용자가 없으면 먼저 생성
        get_or_create_user(knox_id)
        
        if settings.USE_SQLITE:
            cursor.execute('''
                UPDATE users SET is_admin = ?
                WHERE knox_id = ?
            ''', (1 if is_admin_flag else 0, knox_id))
        else:
            cursor.execute('''
                UPDATE users SET is_admin = %s
                WHERE knox_id = %s
            ''', (1 if is_admin_flag else 0, knox_id))


# ============================================
# Session Operations (Knox ID 필터링)
# ============================================

def create_session(session_id: str, knox_id: str, initial_agent: str) -> Dict[str, Any]:
    """세션 생성 (Knox ID 필수)"""
    # 사용자 존재 확인/생성
    get_or_create_user(knox_id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        if settings.USE_SQLITE:
            cursor.execute('''
                INSERT OR REPLACE INTO sessions 
                (session_id, knox_id, initial_agent, is_active)
                VALUES (?, ?, ?, 1)
            ''', (session_id, knox_id, initial_agent))
        else:
            cursor.execute('''
                INSERT INTO sessions 
                (session_id, knox_id, initial_agent, is_active)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (session_id) DO UPDATE SET
                    updated_at = CURRENT_TIMESTAMP,
                    is_active = 1
            ''', (session_id, knox_id, initial_agent))
        
        return get_session(session_id)


def get_session(session_id: str, knox_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """세션 조회 (권한 체크 포함)"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        if settings.USE_SQLITE:
            cursor.execute('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
        else:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM sessions WHERE session_id = %s', (session_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        session = dict(row) if settings.USE_SQLITE else row
        
        # 권한 체크
        if knox_id and session['knox_id'] != knox_id:
            if not is_admin(knox_id):
                return None
        
        return session


def get_sessions_by_knox(knox_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """특정 사용자의 세션 목록 (일반 사용자용)"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        if settings.USE_SQLITE:
            cursor.execute('''
                SELECT s.*, COUNT(m.id) as message_count
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                WHERE s.knox_id = ? AND s.is_active = 1
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC
                LIMIT ? OFFSET ?
            ''', (knox_id, limit, offset))
        else:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT s.*, COUNT(m.id) as message_count
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                WHERE s.knox_id = %s AND s.is_active = 1
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC
                LIMIT %s OFFSET %s
            ''', (knox_id, limit, offset))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_all_sessions(
    knox_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """전체 세션 목록 (관리자용)"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        query = '''
            SELECT s.*, u.is_admin, COUNT(m.id) as message_count
            FROM sessions s
            LEFT JOIN users u ON s.knox_id = u.knox_id
            LEFT JOIN messages m ON s.session_id = m.session_id
        '''
        params = []
        conditions = []
        
        if knox_id:
            conditions.append('s.knox_id = ?' if settings.USE_SQLITE else 's.knox_id = %s')
            params.append(knox_id)
        
        if is_active is not None:
            conditions.append('s.is_active = ?' if settings.USE_SQLITE else 's.is_active = %s')
            params.append(1 if is_active else 0)
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        query += '''
            GROUP BY s.session_id, u.is_admin
            ORDER BY s.updated_at DESC
        '''
        
        if settings.USE_SQLITE:
            query += ' LIMIT ? OFFSET ?'
        else:
            query += ' LIMIT %s OFFSET %s'
        params.extend([limit, offset])
        
        if settings.USE_SQLITE:
            cursor.execute(query, params)
        else:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params)
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def reset_session(session_id: str, knox_id: Optional[str] = None) -> bool:
    """세션 초기화 (메시지만 삭제)"""
    # 권한 체크
    session = get_session(session_id, knox_id)
    if not session:
        return False
    
    with get_db() as conn:
        cursor = conn.cursor()
        if settings.USE_SQLITE:
            cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
            cursor.execute('DELETE FROM delegation_chains WHERE session_id = ?', (session_id,))
        else:
            cursor.execute('DELETE FROM messages WHERE session_id = %s', (session_id,))
            cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
        return True


def delete_session(session_id: str, knox_id: Optional[str] = None) -> bool:
    """세션 완전 삭제"""
    # 권한 체크
    session = get_session(session_id, knox_id)
    if not session:
        return False
    
    with get_db() as conn:
        cursor = conn.cursor()
        if settings.USE_SQLITE:
            cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
            cursor.execute('DELETE FROM delegation_chains WHERE session_id = ?', (session_id,))
            cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        else:
            cursor.execute('DELETE FROM messages WHERE session_id = %s', (session_id,))
            cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
            cursor.execute('DELETE FROM sessions WHERE session_id = %s', (session_id,))
        return True


# ============================================
# Message Operations
# ============================================

def save_message(
    session_id: str,
    role: str,
    content: str,
    agent_id: Optional[str] = None
) -> int:
    """메시지 저장"""
    with get_db() as conn:
        cursor = conn.cursor()
        if settings.USE_SQLITE:
            cursor.execute('''
                INSERT INTO messages (session_id, role, content, agent_id)
                VALUES (?, ?, ?, ?)
            ''', (session_id, role, content, agent_id))
            return cursor.lastrowid
        else:
            cursor.execute('''
                INSERT INTO messages (session_id, role, content, agent_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (session_id, role, content, agent_id))
            return cursor.fetchone()[0]


def get_messages(session_id: str, limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
    """세션의 메시지 목록"""
    with get_db() as conn:
        cursor = conn.cursor()
        if settings.USE_SQLITE:
            cursor.execute('''
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ? OFFSET ?
            ''', (session_id, limit, offset))
        else:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT * FROM messages
                WHERE session_id = %s
                ORDER BY created_at ASC
                LIMIT %s OFFSET %s
            ''', (session_id, limit, offset))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def search_messages(
    knox_id: str,
    query: str,
    session_id: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """메시지 검색 (사용자별)"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        if settings.USE_SQLITE:
            sql = '''
                SELECT m.*, s.knox_id
                FROM messages m
                JOIN sessions s ON m.session_id = s.session_id
                WHERE s.knox_id = ? AND m.content LIKE ?
            '''
            params = [knox_id, f'%{query}%']
            if session_id:
                sql += ' AND m.session_id = ?'
                params.append(session_id)
            sql += ' ORDER BY m.created_at DESC LIMIT ?'
            params.append(limit)
            cursor.execute(sql, params)
        else:
            sql = '''
                SELECT m.*, s.knox_id
                FROM messages m
                JOIN sessions s ON m.session_id = s.session_id
                WHERE s.knox_id = %s AND m.content ILIKE %s
            '''
            params = [knox_id, f'%{query}%']
            if session_id:
                sql += ' AND m.session_id = %s'
                params.append(session_id)
            sql += ' ORDER BY m.created_at DESC LIMIT %s'
            params.append(limit)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(sql, params)
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


# ============================================
# Delegation Chain Operations
# ============================================

def save_delegation_chain(session_id: str, chain: List[str]) -> None:
    """위임 체인 저장"""
    with get_db() as conn:
        cursor = conn.cursor()
        # 기존 체인 삭제
        if settings.USE_SQLITE:
            cursor.execute('DELETE FROM delegation_chains WHERE session_id = ?', (session_id,))
            for idx, agent_id in enumerate(chain):
                cursor.execute('''
                    INSERT INTO delegation_chains (session_id, agent_id, order_index)
                    VALUES (?, ?, ?)
                ''', (session_id, agent_id, idx))
        else:
            cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
            for idx, agent_id in enumerate(chain):
                cursor.execute('''
                    INSERT INTO delegation_chains (session_id, agent_id, order_index)
                    VALUES (%s, %s, %s)
                ''', (session_id, agent_id, idx))


def get_delegation_chain(session_id: str) -> List[str]:
    """위임 체인 조회"""
    with get_db() as conn:
        cursor = conn.cursor()
        if settings.USE_SQLITE:
            cursor.execute('''
                SELECT agent_id FROM delegation_chains
                WHERE session_id = ?
                ORDER BY order_index ASC
            ''', (session_id,))
        else:
            cursor.execute('''
                SELECT agent_id FROM delegation_chains
                WHERE session_id = %s
                ORDER BY order_index ASC
            ''', (session_id,))
        rows = cursor.fetchall()
        return [row['agent_id'] if settings.USE_SQLITE else row[0] for row in rows]


# ============================================
# Admin Statistics
# ============================================

def get_admin_stats() -> Dict[str, Any]:
    """관리자 통계"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        stats = {}
        
        # 사용자 통계
        if settings.USE_SQLITE:
            cursor.execute('SELECT COUNT(*) FROM users')
            stats['total_users'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
            stats['admin_count'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM sessions WHERE is_active = 1')
            stats['active_sessions'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM sessions')
            stats['total_sessions'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM messages')
            stats['total_messages'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM messages WHERE role = 'user'")
            stats['user_messages'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM messages WHERE role = 'assistant'")
            stats['assistant_messages'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT MAX(created_at) FROM messages')
            row = cursor.fetchone()
            stats['last_message_time'] = row[0] if row else None
        else:
            cursor.execute('SELECT COUNT(*) FROM users')
            stats['total_users'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
            stats['admin_count'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM sessions WHERE is_active = 1')
            stats['active_sessions'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM sessions')
            stats['total_sessions'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM messages')
            stats['total_messages'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM messages WHERE role = 'user'")
            stats['user_messages'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM messages WHERE role = 'assistant'")
            stats['assistant_messages'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT MAX(created_at) FROM messages')
            row = cursor.fetchone()
            stats['last_message_time'] = row[0] if row else None
        
        return stats


def get_user_stats() -> List[Dict[str, Any]]:
    """사용자별 통계"""
    with get_db() as conn:
        cursor = conn.cursor()
        if settings.USE_SQLITE:
            cursor.execute('''
                SELECT 
                    u.knox_id,
                    u.is_admin,
                    u.created_at as user_created,
                    COUNT(DISTINCT s.session_id) as session_count,
                    COUNT(DISTINCT m.id) as message_count,
                    MAX(m.created_at) as last_message_time
                FROM users u
                LEFT JOIN sessions s ON u.knox_id = s.knox_id AND s.is_active = 1
                LEFT JOIN messages m ON s.session_id = m.session_id
                GROUP BY u.knox_id
                ORDER BY session_count DESC
            ''')
        else:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT 
                    u.knox_id,
                    u.is_admin,
                    u.created_at as user_created,
                    COUNT(DISTINCT s.session_id) as session_count,
                    COUNT(DISTINCT m.id) as message_count,
                    MAX(m.created_at) as last_message_time
                FROM users u
                LEFT JOIN sessions s ON u.knox_id = s.knox_id AND s.is_active = 1
                LEFT JOIN messages m ON s.session_id = m.session_id
                GROUP BY u.knox_id, u.is_admin, u.created_at
                ORDER BY session_count DESC
            ''')
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
