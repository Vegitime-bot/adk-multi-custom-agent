-- ADK Web UI PostgreSQL Schema
-- 채팅 데이터 저장 및 세션 관리

-- 세션 테이블
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    initial_agent TEXT,
    is_active INTEGER DEFAULT 1
);

-- 메시지 테이블
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL,  -- 'user' or 'assistant'
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, agent_id, order_index)
);

-- 인덱스 생성 (성능 최적화)
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_delegation_chains_session_id ON delegation_chains(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_is_active ON sessions(is_active);

-- 설명
COMMENT ON TABLE sessions IS '채팅 세션 정보';
COMMENT ON TABLE messages IS '세션별 메시지 기록';
COMMENT ON TABLE delegation_chains IS 'Agent 위임 체인';
