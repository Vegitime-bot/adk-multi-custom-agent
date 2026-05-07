#!/usr/bin/env python3
"""
검증 에이전트 - AgentTool RAG 테스트
Parent/Child 각각의 응답을 검증
"""
import json
import requests
import sys
import time

API_BASE = "http://localhost:8080"
HEADERS = {"Content-Type": "application/json", "x-knox-id": "test-user"}


class VerificationAgent:
    """테스트 주관 및 검증"""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
    
    def log(self, msg: str):
        print(f"  → {msg}")
    
    def test(self, name: str, condition: bool, detail: str = ""):
        if condition:
            self.passed += 1
            print(f"  ✅ PASS: {name}")
        else:
            self.failed += 1
            print(f"  ❌ FAIL: {name}")
            if detail:
                print(f"     Detail: {detail}")
        self.results.append({"name": name, "passed": condition, "detail": detail})
    
    def chat(self, chatbot_id: str, message: str, session_id: str) -> dict:
        """API 호출"""
        resp = requests.post(
            f"{API_BASE}/api/chat",
            headers=HEADERS,
            json={
                "chatbot_id": chatbot_id,
                "message": message,
                "session_id": session_id,
                "mode": "agent"
            },
            stream=True
        )
        
        chunks = []
        full_text = ""
        for line in resp.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith("data: "):
                    data = line[6:]
                    try:
                        obj = json.loads(data)
                        if "chunk" in obj:
                            chunks.append(obj["chunk"])
                        elif "done" in obj:
                            full_text = obj.get("response", "")
                    except:
                        pass
        
        return {
            "chunks": chunks,
            "response": full_text
        }
    
    def run_all_tests(self):
        print("=" * 60)
        print("🧪 AgentTool RAG 검증 시작")
        print("=" * 60)
        
        # ──────────────────────────────────────────
        # Test 1: Mock Ingestion 서버 연결 확인
        # ──────────────────────────────────────────
        print("\n📋 Test 1: Mock Ingestion 서버 연결")
        try:
            r = requests.post(
                "http://localhost:8001/search",
                headers={"x-api-key": "ingestion-server-secret-key", "Content-Type": "application/json"},
                json={"query": "52주차 주간보고", "index_names": ["db_pddi_minutes"], "top_k": 5, "threshold": 0.0}
            )
            data = r.json()
            results = data.get("results", [])
            self.test("Ingestion 서버 연결", r.status_code == 200)
            self.test("52주차 데이터 존재", len(results) > 0, f"결과 수: {len(results)}")
            if results:
                self.test("첫 결과에 '52주차' 포함", "52" in results[0].get("content", ""), 
                         results[0].get("content", "")[:50])
        except Exception as e:
            self.test("Ingestion 서버 연결", False, str(e))
        
        # ──────────────────────────────────────────
        # Test 2: Parent 직접 응답 (위임 없음)
        # ──────────────────────────────────────────
        print("\n📋 Test 2: Parent (pddi_total) 직접 응답")
        result = self.chat("pddi_total", "안녕하세요", "test-parent-001")
        response = result.get("response", "")
        
        self.test("Parent 응답 수신", len(response) > 0, f"길이: {len(response)}")
        self.test("Parent가 tool 호출 없이 응답", "[도구 호출:" not in response, 
                 "tool 호출 포함됨" if "[도구 호출:" in response else "정상")
        
        # ──────────────────────────────────────────
        # Test 3: Parent → Child 위임
        # ──────────────────────────────────────────
        print("\n📋 Test 3: Parent (pddi_total) → Child (pddi_minutes) 위임")
        result = self.chat("pddi_total", "52주차 주간보고 정리해줘", "test-delegate-001")
        response = result.get("response", "")
        
        self.test("위임 응답 수신", len(response) > 0)
        all_chunks = " ".join(result.get("chunks", []))
        has_tool_call = "[도구 호출: pddi_minutes]" in all_chunks
        self.test("pddi_minutes 도구 호출", has_tool_call,
                 f"chunks: {all_chunks[:200] if all_chunks else 'None'}")
        
        # RAG 결과 포함 여부 (검색된 내용이 응답에 반영됐는지)
        # RAG 결과 반영: 52주차 내용이 포함됐는지
        rag_keywords = ["데이터 모델 검증", "통합 테스트", "김철수", "이영희", "52주차", "시스템 연동"]
        has_rag_content = any(kw in response for kw in rag_keywords)
        self.test("RAG 결과가 응답에 반영", has_rag_content,
                 f"응답 프리뷰: {response[:300]}...")
        
        # ──────────────────────────────────────────
        # Test 4: Child 직접 RAG tool 사용
        # ──────────────────────────────────────────
        print("\n📋 Test 4: Child (pddi_minutes) 직접 RAG tool")
        result = self.chat("pddi_minutes", "52주차 주간보고 알려줘", "test-child-001")
        response = result.get("response", "")
        
        self.test("Child 응답 수신", len(response) > 0)
        has_rag_content = any(kw in response for kw in ["데이터 모델 검증", "통합 테스트", "김철수"])
        self.test("Child RAG 결과 반영", has_rag_content,
                 f"응답 프리뷰: {response[:200]}...")
        
        # ──────────────────────────────────────────
        # Test 5: 없는 문서 검색
        # ──────────────────────────────────────────
        print("\n📋 Test 5: 없는 문서 검색 (Negative Test)")
        result = self.chat("pddi_minutes", "100주차 주간보고", "test-negative-001")
        response = result.get("response", "")
        
        self.test("Negative 응답 수신", len(response) > 0)
        has_no_result = any(kw in response for kw in ["없습니다", "찾을 수 없", "결과 없음", "미확인"])
        self.test("결과 없음 표시", has_no_result,
                 f"응답 프리뷰: {response[:200]}...")
        
        # ──────────────────────────────────────────
        # 결과 요약
        # ──────────────────────────────────────────
        print("\n" + "=" * 60)
        print("📊 검증 결과 요약")
        print("=" * 60)
        print(f"  ✅ PASS: {self.passed}")
        print(f"  ❌ FAIL: {self.failed}")
        print(f"  📈 성공률: {self.passed/(self.passed+self.failed)*100:.1f}%")
        print("=" * 60)
        
        return self.failed == 0


if __name__ == "__main__":
    agent = VerificationAgent()
    success = agent.run_all_tests()
    sys.exit(0 if success else 1)
