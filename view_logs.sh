#!/bin/bash
# view_logs.sh - 실시간 로그 확인 스크립트

LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# 로그 파일 설정
BACKEND_LOG="$LOG_DIR/backend.log"
INGESTION_LOG="$LOG_DIR/ingestion.log"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 헬퍼 함수
show_help() {
    echo "사용법: ./view_logs.sh [옵션]"
    echo ""
    echo "옵션:"
    echo "  backend     - 백엔드 서버 로그만 표시"
    echo "  ingestion   - Ingestion 서버 로그만 표시"
    echo "  delegate    - 위임(delegation) 관련 로그만 필터링"
    echo "  execute     - 실행(execute) 관련 로그만 필터링"
    echo "  all         - 모든 로그 표시 (기본값)"
    echo "  clear       - 로그 파일 초기화"
    echo ""
    echo "예시:"
    echo "  ./view_logs.sh                    # 모든 로그 실시간 표시"
    echo "  ./view_logs.sh delegate           # 위임 로그만 표시"
    echo "  ./view_logs.sh backend            # 백엔드 로그만 표시"
}

# 로그 파일 초기화
clear_logs() {
    echo "로그 파일을 초기화합니다..."
    > "$BACKEND_LOG" 2>/dev/null
    > "$INGESTION_LOG" 2>/dev/null
    echo "✅ 로그 파일 초기화 완료"
    echo "  - $BACKEND_LOG"
    echo "  - $INGESTION_LOG"
}

# 로그 디렉토리 생성 및 심볼릭 링크 설정
setup_logs() {
    mkdir -p "$LOG_DIR"
    
    # /tmp/backend.log 가 있으면 복사
    if [ -f "/tmp/backend.log" ]; then
        tail -n 100 "/tmp/backend.log" > "$BACKEND_LOG" 2>/dev/null
    fi
    
    # /tmp/ingestion.log 가 있으면 복사
    if [ -f "/tmp/ingestion.log" ]; then
        tail -n 100 "/tmp/ingestion.log" > "$INGESTION_LOG" 2>/dev/null
    fi
}

# 모든 로그 표시
show_all_logs() {
    setup_logs
    echo -e "${CYAN}=== 모든 로그 실시간 표시 (Ctrl+C로 종료) ===${NC}"
    echo ""
    
    # 두 로그 파일을 병합하여 시간순으로 표시
    tail -f "$BACKEND_LOG" "$INGESTION_LOG" 2>/dev/null | while read line; do
        echo "$line"
    done
}

# 백엔드 로그만 표시
show_backend_logs() {
    setup_logs
    echo -e "${GREEN}=== 백엔드 서버 로그 (Ctrl+C로 종료) ===${NC}"
    echo ""
    tail -f "$BACKEND_LOG" 2>/dev/null
}

# Ingestion 로그만 표시
show_ingestion_logs() {
    setup_logs
    echo -e "${YELLOW}=== Ingestion 서버 로그 (Ctrl+C로 종료) ===${NC}"
    echo ""
    tail -f "$INGESTION_LOG" 2>/dev/null
}

# 위임(delegation) 로그 필터링
show_delegate_logs() {
    setup_logs
    echo -e "${BLUE}=== 위임(Delegation) 로그 필터링 ===${NC}"
    echo ""
    tail -f "$BACKEND_LOG" 2>/dev/null | grep --line-buffered -E "\[DELEGATE\]|\[EXECUTE\]|sub_chatbot|parent_id|confidence|hybrid|위임|전문가"
}

# 실행(execute) 로그 필터링
show_execute_logs() {
    setup_logs
    echo -e "${CYAN}=== 실행(Execute) 로그 필터링 ===${NC}"
    echo ""
    tail -f "$BACKEND_LOG" 2>/dev/null | grep --line-buffered -E "\[EXECUTE\]|\[Chat|챗봇|Chatbot|session"
}

# 메인 로직
case "${1:-all}" in
    backend|b)
        show_backend_logs
        ;;
    ingestion|i)
        show_ingestion_logs
        ;;
    delegate|d)
        show_delegate_logs
        ;;
    execute|e)
        show_execute_logs
        ;;
    all|a|"")
        show_all_logs
        ;;
    clear|c)
        clear_logs
        ;;
    help|h|-h|--help)
        show_help
        ;;
    *)
        echo "알 수 없는 옵션: $1"
        show_help
        exit 1
        ;;
esac
