-- PostgreSQL Database Setup for Multi Custom Agent Service
-- Table: user_chatbot_access (User-Chatbot Permission Management)

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS test;

-- Drop table if exists (for clean setup)
DROP TABLE IF EXISTS test.user_chatbot_access;

-- Create user_chatbot_access table
CREATE TABLE test.user_chatbot_access (
    id SERIAL NOT NULL,
    knox_id VARCHAR(50) NULL,
    chatbot_id VARCHAR(50) NULL,
    can_access BOOLEAN DEFAULT TRUE NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NULL,
    CONSTRAINT user_chatbot_access_pkey PRIMARY KEY (id),
    CONSTRAINT unique_user_chatbot UNIQUE (knox_id, chatbot_id)
);

-- Create index for faster lookups
CREATE INDEX idx_user_chatbot_knox_id ON test.user_chatbot_access(knox_id);
CREATE INDEX idx_user_chatbot_chatbot_id ON test.user_chatbot_access(chatbot_id);

-- Add comment on table
COMMENT ON TABLE test.user_chatbot_access IS '사용자-챗봇 접근 권한 관리 테이블';
COMMENT ON COLUMN test.user_chatbot_access.knox_id IS '사용자 Knox ID';
COMMENT ON COLUMN test.user_chatbot_access.chatbot_id IS '챗봇 ID';
COMMENT ON COLUMN test.user_chatbot_access.can_access IS '접근 권한 여부';
COMMENT ON COLUMN test.user_chatbot_access.created_at IS '생성 시간';
COMMENT ON COLUMN test.user_chatbot_access.updated_at IS '수정 시간';

-- ============================================
-- MOCK DATA INSERTION
-- ============================================

-- user-001: 모든 챗봘 접근 가능 (관리자 권한)
INSERT INTO test.user_chatbot_access (knox_id, chatbot_id, can_access, created_at) VALUES
('user-001', 'chatbot-a', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-b', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-c', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-d', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-hr', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-hr-policy', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-hr-benefit', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-tech', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-tech-backend', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-tech-frontend', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-tech-devops', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-rtl-verilog', TRUE, CURRENT_TIMESTAMP),
('user-001', 'chatbot-rtl-synthesis', TRUE, CURRENT_TIMESTAMP);

-- user-002: HR 관련만 접근 가능 (인사팀)
INSERT INTO test.user_chatbot_access (knox_id, chatbot_id, can_access, created_at) VALUES
('user-002', 'chatbot-hr', TRUE, CURRENT_TIMESTAMP),
('user-002', 'chatbot-hr-policy', TRUE, CURRENT_TIMESTAMP),
('user-002', 'chatbot-hr-benefit', TRUE, CURRENT_TIMESTAMP),
('user-002', 'chatbot-a', TRUE, CURRENT_TIMESTAMP),
('user-002', 'chatbot-b', FALSE, CURRENT_TIMESTAMP),  -- 기술 챗봘 접근 불가
('user-002', 'chatbot-tech', FALSE, CURRENT_TIMESTAMP),
('user-002', 'chatbot-tech-backend', FALSE, CURRENT_TIMESTAMP);

-- user-003: 기술 개발팀 (Tech 챗봘만 접근)
INSERT INTO test.user_chatbot_access (knox_id, chatbot_id, can_access, created_at) VALUES
('user-003', 'chatbot-tech', TRUE, CURRENT_TIMESTAMP),
('user-003', 'chatbot-tech-backend', TRUE, CURRENT_TIMESTAMP),
('user-003', 'chatbot-tech-frontend', TRUE, CURRENT_TIMESTAMP),
('user-003', 'chatbot-tech-devops', TRUE, CURRENT_TIMESTAMP),
('user-003', 'chatbot-rtl-verilog', TRUE, CURRENT_TIMESTAMP),
('user-003', 'chatbot-rtl-synthesis', TRUE, CURRENT_TIMESTAMP),
('user-003', 'chatbot-c', TRUE, CURRENT_TIMESTAMP),
('user-003', 'chatbot-a', TRUE, CURRENT_TIMESTAMP),
('user-003', 'chatbot-hr', FALSE, CURRENT_TIMESTAMP),  -- 인사 챗봘 접근 불가
('user-003', 'chatbot-b', FALSE, CURRENT_TIMESTAMP);

-- system: 시스템 계정 (모든 권한)
INSERT INTO test.user_chatbot_access (knox_id, chatbot_id, can_access, created_at) VALUES
('system', 'chatbot-a', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-b', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-c', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-d', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-hr', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-hr-policy', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-hr-benefit', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-tech', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-tech-backend', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-tech-frontend', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-tech-devops', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-rtl-verilog', TRUE, CURRENT_TIMESTAMP),
('system', 'chatbot-rtl-synthesis', TRUE, CURRENT_TIMESTAMP);

-- guest: 제한된 접근 (기본 챗봘만)
INSERT INTO test.user_chatbot_access (knox_id, chatbot_id, can_access, created_at) VALUES
('guest', 'chatbot-a', TRUE, CURRENT_TIMESTAMP),
('guest', 'chatbot-b', FALSE, CURRENT_TIMESTAMP),
('guest', 'chatbot-c', FALSE, CURRENT_TIMESTAMP),
('guest', 'chatbot-hr', TRUE, CURRENT_TIMESTAMP),
('guest', 'chatbot-tech', TRUE, CURRENT_TIMESTAMP);

-- ============================================
-- DB 권한 관리 테이블
-- ============================================

DROP TABLE IF EXISTS test.user_db_access;

CREATE TABLE test.user_db_access (
    id SERIAL NOT NULL,
    knox_id VARCHAR(50) NULL,
    db_id VARCHAR(50) NULL,
    can_access BOOLEAN DEFAULT TRUE NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NULL,
    CONSTRAINT user_db_access_pkey PRIMARY KEY (id),
    CONSTRAINT unique_user_db UNIQUE (knox_id, db_id)
);

CREATE INDEX idx_user_db_knox_id ON test.user_db_access(knox_id);
CREATE INDEX idx_user_db_db_id ON test.user_db_access(db_id);

COMMENT ON TABLE test.user_db_access IS '사용자-DB 접근 권한 관리 테이블';
COMMENT ON COLUMN test.user_db_access.knox_id IS '사용자 Knox ID';
COMMENT ON COLUMN test.user_db_access.db_id IS 'DB ID';
COMMENT ON COLUMN test.user_db_access.can_access IS '접근 권한 여부';

-- ============================================
-- Verification Queries
-- ============================================

-- 전체 권한 조회
-- SELECT * FROM test.user_chatbot_access ORDER BY knox_id, chatbot_id;

-- 특정 사용자 권한 조회
-- SELECT * FROM test.user_chatbot_access WHERE knox_id = 'user-001';

-- 특정 챗봘 접근 가능한 사용자 조회
-- SELECT knox_id FROM test.user_chatbot_access WHERE chatbot_id = 'chatbot-tech' AND can_access = TRUE;

-- 권한 통계
-- SELECT knox_id, COUNT(*) as accessible_chatbots 
-- FROM test.user_chatbot_access 
-- WHERE can_access = TRUE 
-- GROUP BY knox_id;

-- 테이블 정보 확인
-- \d test.user_chatbot_access
