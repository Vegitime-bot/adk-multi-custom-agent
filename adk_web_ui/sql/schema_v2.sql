-- ADK Web UI Schema v2
-- Knox ID 기반 사용자 분리 + 관리자 기능

-- ============================================
-- 1. users 테이블 (Knox ID 기반)
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    knox_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_admin INTEGER DEFAULT 0
);

COMMENT ON TABLE users IS 'Knox ID 기반 사용자 정보';
COMMENT ON COLUMN users.knox_id IS 'Knox 플랫폼 사용자 ID';
COMMENT ON COLUMN users.is_admin IS '관리자 여부 (0: 일반, 1: 관리자)';

-- ============================================
-- 2. sessions 테이블 (knox_id 추가)
-- ============================================

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    knox_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    initial_agent TEXT,
    is_active INTEGER DEFAULT 1
);

COMMENT ON TABLE sessions IS '채팅 세션 정보 (사용자별 분리)';
COMMENT ON COLUMN sessions.knox_id IS '세션 소유자의 Knox ID';

-- 외래키 제약조건
ALTER TABLE sessions ADD CONSTRAINT fk_sessions_knox_id
    FOREIGN KEY (knox_id) REFERENCES users(knox_id) ON DELETE CASCADE;

-- ============================================
-- 3. messages 테이블 (변경 없음)
-- ============================================

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT,
    agent_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE messages IS '세션별 메시지 기록';

-- ============================================
-- 4. delegation_chains 테이블 (변경 없음)
-- ============================================

CREATE TABLE IF NOT EXISTS delegation_chains (
    id SERIAL PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, agent_id, order_index)
);

COMMENT ON TABLE delegation_chains IS 'Agent 위임 체인';

-- ============================================
-- 5. 인덱스
-- ============================================

-- 기존 인덱스
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_delegation_chains_session_id ON delegation_chains(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_is_active ON sessions(is_active);

-- v2 추가 인덱스
CREATE INDEX IF NOT EXISTS idx_sessions_knox_id ON sessions(knox_id);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin);
CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active);

-- ============================================
-- 6. 관리자용 뷰
-- ============================================

-- 전체 통계 뷰
CREATE OR REPLACE VIEW admin_stats AS
SELECT
    (SELECT COUNT(*) FROM users) as total_users,
    (SELECT COUNT(*) FROM users WHERE is_admin = 1) as admin_count,
    (SELECT COUNT(*) FROM sessions WHERE is_active = 1) as active_sessions,
    (SELECT COUNT(*) FROM sessions) as total_sessions,
    (SELECT COUNT(*) FROM messages) as total_messages,
    (SELECT COUNT(*) FROM messages WHERE role = 'user') as user_messages,
    (SELECT COUNT(*) FROM messages WHERE role = 'assistant') as assistant_messages,
    (SELECT MAX(created_at) FROM messages) as last_message_time;

-- 사용자별 통계 뷰
CREATE OR REPLACE VIEW user_stats AS
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
GROUP BY u.knox_id, u.is_admin, u.created_at;

-- ============================================
-- 7. 권장 초기 설정
-- ============================================

-- 관리자 계정 예시 (실제 Knox ID로 변경 필요)
-- INSERT INTO users (knox_id, is_admin) VALUES
--     ('your_knox_id_here', 1)
-- ON CONFLICT (knox_id) DO UPDATE SET is_admin = 1;
