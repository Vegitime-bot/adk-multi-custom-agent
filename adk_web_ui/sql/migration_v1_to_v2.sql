-- ADK Web UI Database Migration: v1 -> v2
-- Knox ID Support + Admin Features
-- 
-- 실행 방법:
-- psql -U postgres -d adk_chat -f migration_v1_to_v2.sql

-- ============================================
-- 1. users 테이블 생성 (Knox ID 기반)
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    knox_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_admin INTEGER DEFAULT 0
);

COMMENT ON TABLE users IS 'Knox ID 기반 사용자 정보';
COMMENT ON COLUMN users.knox_id IS 'Knox 플랫폼 사용자 ID';
COMMENT ON COLUMN users.is_admin IS '관리자 여부 (0/1)';

-- ============================================
-- 2. sessions 테이블 수정 (knox_id 추가)
-- ============================================

-- knox_id 컬럼 추가 (nullable)
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS knox_id TEXT;

-- 기존 데이터에 기본 knox_id 할당 (마이그레이션 시)
-- 주의: 실제 운영 환경에서는 사용자별로 매핑 필요
UPDATE sessions SET knox_id = 'legacy_user' WHERE knox_id IS NULL;

-- knox_id를 NOT NULL로 변경
-- 주의: 기존 데이터가 모두 할당된 후 실행
-- ALTER TABLE sessions ALTER COLUMN knox_id SET NOT NULL;

-- 외래키 제약조건 (선택사항 - 성능 vs 무결성)
-- ALTER TABLE sessions ADD CONSTRAINT fk_sessions_knox_id
--     FOREIGN KEY (knox_id) REFERENCES users(knox_id) ON DELETE CASCADE;

-- ============================================
-- 3. 인덱스 생성
-- ============================================

-- 세션용 인덱스
CREATE INDEX IF NOT EXISTS idx_sessions_knox_id ON sessions(knox_id);

-- 사용자용 인덱스
CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin);
CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active);

-- 기존 인덱스 확인
-- CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
-- CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
-- CREATE INDEX IF NOT EXISTS idx_delegation_chains_session_id ON delegation_chains(session_id);
-- CREATE INDEX IF NOT EXISTS idx_sessions_is_active ON sessions(is_active);

-- ============================================
-- 4. 관리자 계정 설정 (예시)
-- ============================================

-- 관리자 Knox ID 설정 (실제 값으로 변경 필요)
-- INSERT INTO users (knox_id, is_admin) VALUES
--     ('admin_knox_id_001', 1),
--     ('admin_knox_id_002', 1)
-- ON CONFLICT (knox_id) DO UPDATE SET is_admin = 1;

-- ============================================
-- 5. 마이그레이션 검증
-- ============================================

-- 세션별 knox_id 할당 현황 확인
SELECT 
    knox_id,
    COUNT(*) as session_count,
    MIN(created_at) as first_session,
    MAX(updated_at) as last_active
FROM sessions
GROUP BY knox_id
ORDER BY session_count DESC;

-- ============================================
-- 롤백 스크립트 (필요시)
-- ============================================
-- 
-- DROP INDEX IF EXISTS idx_sessions_knox_id;
-- DROP INDEX IF EXISTS idx_users_is_admin;
-- DROP INDEX IF EXISTS idx_users_last_active;
-- ALTER TABLE sessions DROP COLUMN IF EXISTS knox_id;
-- DROP TABLE IF EXISTS users;

-- ============================================
-- 마이그레이션 완료 메시지
-- ============================================

DO $$
BEGIN
    RAISE NOTICE 'Migration v1 -> v2 completed successfully!';
    RAISE NOTICE 'Users table: %', (SELECT COUNT(*) FROM users);
    RAISE NOTICE 'Sessions with knox_id: %', (SELECT COUNT(*) FROM sessions WHERE knox_id IS NOT NULL);
END $$;
