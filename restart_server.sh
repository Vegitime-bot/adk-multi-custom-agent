#!/bin/bash
# 강제 서버 재시작 스크립트

LOG_DIR="logs"
mkdir -p "$LOG_DIR"

echo "=== 서버 강제 재시작 ==="

# 1. 모든 Python/uvicorn 프로세스 종료
echo "1. 기존 프로세스 종료 중..."
pkill -9 -f python 2>/dev/null
pkill -9 -f uvicorn 2>/dev/null
pkill -9 -f "backend.main" 2>/dev/null

# 2. 8080 포트 사용 중인 프로세스 종료
echo "2. 8080 포트 프로세스 종료 중..."
for pid in $(lsof -t -i:8080 2>/dev/null); do
    kill -9 $pid 2>/dev/null
done

# 3. 잠시 대기
sleep 3

# 4. Python 캐시 삭제
echo "3. Python 캐시 삭제 중..."
cd /Users/vegitime/.openclaw/workspace/projects/multi-custom-agent
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# 5. 서버 시작
echo "4. 서버 시작 중..."
source .venv/bin/activate

# Backend 서버 (로그를 logs/backend.log로)
python -m backend.main > "$LOG_DIR/backend.log" 2>&1 &
SERVER_PID=$!
echo $SERVER_PID > /tmp/backend.pid
echo "Backend PID: $SERVER_PID"

# Mock Ingestion 서버 (로그를 logs/ingestion.log로)
uvicorn mock_ingestion_server:app --host 0.0.0.0 --port 8001 > "$LOG_DIR/ingestion.log" 2>&1 &
INGESTION_PID=$!
echo "Ingestion PID: $INGESTION_PID"

echo ""
echo "로그 파일:"
echo "  - Backend: $LOG_DIR/backend.log"
echo "  - Ingestion: $LOG_DIR/ingestion.log"

# 6. 서버 준비 대기
echo ""
echo "5. 서버 준비 대기 중 (5초)..."
sleep 5

# 7. 헬스 체크
echo "6. 서버 상태 확인..."
echo ""
echo "=== Ingestion 서버 ==="
if curl -s http://localhost:8001/health > /dev/null; then
    echo "✅ Ingestion 서버 정상"
else
    echo "❌ Ingestion 서버 응답 없음"
fi

echo ""
echo "=== Backend 서버 ==="
if curl -s http://localhost:8080/api/chatbots > /dev/null; then
    echo "✅ Backend 서버 정상"
else
    echo "❌ Backend 서버 응답 없음"
fi

echo ""
echo "=== 로그 확인 방법 ==="
echo "./view_logs.sh         # 모든 로그"
echo "./view_logs.sh backend # 백엔드 로그"
echo "./view_logs.sh delegate # 위임 로그"
