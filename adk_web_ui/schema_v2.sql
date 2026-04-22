-- ADK Web UI PostgreSQL Schema v2
-- Knox ID 기반 저장 + 관리자 기능

-- 세션 테이블 (knox_id 추가)
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    knox_id TEXT NOT NULL,  -- 사용자 식별자
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    initial_agent TEXT,
    is_active INTEGER DEFAULT 1,
    title TEXT  -- 세션 제목 (선택)
);

-- 메시지 테이블
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT,
    agent_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 위임 체인 테이블
CREATE TABLE IF NOT EXISTS delegation_chains (
    id SERIAL PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 관리자 목록 테이블
CREATE TABLE IF NOT EXISTS admin_users (
    knox_id TEXT PRIMARY KEY,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by TEXT
);

-- 인덱스 생성
CREATE INDEX idx_sessions_knox_id ON sessions(knox_id);
CREATE INDEX idx_sessions_is_active ON sessions(is_active);
CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_delegation_chains_session_id ON delegation_chains(session_id);

-- 설명
COMMENT ON TABLE sessions IS '채팅 세션 (Knox ID 기준)';
COMMENT ON TABLE messages IS '세션별 메시지 기록';
COMMENT ON TABLE delegation_chains IS 'Agent 위임 체인';
COMMENT ON TABLE admin_users IS '관리자 목록';
