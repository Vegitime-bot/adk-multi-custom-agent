#!/bin/bash
# 권한 관리 API 테스트 스크립트

echo "=== Permission API Test ==="
echo ""

BASE_URL="http://localhost:8080"

# 1. 전체 권한 목록 조회
echo "1. GET /api/permissions"
curl -s "$BASE_URL/api/permissions" | python3 -m json.tool | head -20
echo ""

# 2. 사용자 권한 통계 조회
echo "2. GET /api/permissions/admin/stats"
curl -s "$BASE_URL/api/permissions/admin/stats" | python3 -m json.tool
echo ""

# 3. 특정 사용자 권한 조회 (user-001)
echo "3. GET /api/permissions/users/user-001"
curl -s "$BASE_URL/api/permissions/users/user-001" | python3 -m json.tool | head -30
echo ""

# 4. 새 권한 추가 테스트
echo "4. POST /api/permissions (Add permission for user-001 to chatbot-rtl-verilog)"
curl -s -X POST "$BASE_URL/api/permissions" \
  -H "Content-Type: application/json" \
  -d '{"knox_id": "user-001", "chatbot_id": "chatbot-rtl-verilog", "can_access": true}' | python3 -m json.tool
echo ""

# 5. 권한 수정 테스트
echo "5. PUT /api/permissions/user-001/chatbot-rtl-verilog (Change to denied)"
curl -s -X PUT "$BASE_URL/api/permissions/user-001/chatbot-rtl-verilog" \
  -H "Content-Type: application/json" \
  -d '{"can_access": false}' | python3 -m json.tool
echo ""

# 6. 권한 확인
echo "6. GET /api/permissions/check/user-001/chatbot-rtl-verilog"
curl -s "$BASE_URL/api/permissions/check/user-001/chatbot-rtl-verilog" | python3 -m json.tool
echo ""

# 7. 권한 삭제
echo "7. DELETE /api/permissions/user-001/chatbot-rtl-verilog"
curl -s -X DELETE "$BASE_URL/api/permissions/user-001/chatbot-rtl-verilog" | python3 -m json.tool
echo ""

echo "=== Test Complete ==="
