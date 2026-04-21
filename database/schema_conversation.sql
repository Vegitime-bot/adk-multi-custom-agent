-- PostgreSQL Schema - Conversation History
-- 대화 히스토리 저장 테이블

CREATE SCHEMA IF NOT EXISTS test;

-- Drop if exists (for clean setup)
DROP TABLE IF EXISTS test.conversation_logs;

-- Conversation logs table
CREATE TABLE test.conversation_logs (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    knox_id VARCHAR(50) NOT NULL,
    chatbot_id VARCHAR(50) NOT NULL,
    user_message TEXT NOT NULL,
    assistant_response TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    search_results_count INTEGER DEFAULT 0,
    confidence_score FLOAT DEFAULT NULL,
    delegated_to VARCHAR(50) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_conv_session ON test.conversation_logs(session_id);
CREATE INDEX idx_conv_knox ON test.conversation_logs(knox_id);
CREATE INDEX idx_conv_chatbot ON test.conversation_logs(chatbot_id);
CREATE INDEX idx_conv_created ON test.conversation_logs(created_at DESC);
CREATE INDEX idx_conv_session_created ON test.conversation_logs(session_id, created_at DESC);

-- Comments
COMMENT ON TABLE test.conversation_logs IS '사용자-챗봘 대화 히스토리';
COMMENT ON COLUMN test.conversation_logs.session_id IS '대화 세션 ID';
COMMENT ON COLUMN test.conversation_logs.knox_id IS '사용자 Knox ID';
COMMENT ON COLUMN test.conversation_logs.chatbot_id IS '챗봘 ID';
COMMENT ON COLUMN test.conversation_logs.tokens_used IS '사용된 토큰 수';
COMMENT ON COLUMN test.conversation_logs.latency_ms IS '응답 지연시간(ms)';
COMMENT ON COLUMN test.conversation_logs.search_results_count IS '검색 결과 수';
COMMENT ON COLUMN test.conversation_logs.confidence_score IS '위임 신뢰도 점수';
COMMENT ON COLUMN test.conversation_logs.delegated_to IS '위임된 하위 Agent ID';

-- Sample data
INSERT INTO test.conversation_logs (session_id, knox_id, chatbot_id, user_message, assistant_response, tokens_used, latency_ms, search_results_count, confidence_score) VALUES
('sess-001', 'user-001', 'chatbot-hr', '연차 신청은 어떻게 하나요?', '연차 신청은 HR 시스템에서 가능합니다. 3일 이상 연차는 사전 승인이 필요합니다.', 245, 1200, 5, 85.5),
('sess-001', 'user-001', 'chatbot-hr', '4대보험은 어떤 것들이 있나요?', '국민연금, 건강보험, 고용보험, 산재보험이 포함됩니다.', 189, 980, 3, 65.0),
('sess-002', 'user-002', 'chatbot-tech', 'FastAPI에서 DB 연결은?', 'SQLAlchemy를 사용하여 연결합니다. 예시: engine = create_async_engine(...)', 312, 1500, 8, 92.0),
('sess-002', 'user-002', 'chatbot-tech', 'Docker compose 파일 예시', 'version: "3.8"\nservices:\n  app:\n    build: .\n    ports:\n      - "8080:8080"', 256, 1100, 4, 88.5),
('sess-003', 'user-001', 'chatbot-rtl-verilog', '4비트 카운터 Verilog 코드', 'module counter4bit(\n  input clk, reset,\n  output [3:0] count\n);\n  always @(posedge clk)\n    if (reset) count <= 0;\n    else count <= count + 1;\nendmodule', 420, 2100, 6, 95.0);
