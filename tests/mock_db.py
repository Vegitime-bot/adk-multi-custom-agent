"""
Mock DB for testing 3-tier delegation

LSI사업팀 (L0) - lsi-members DB:
- LSI사업팀 구성원: 장영동, 박준일, 김용준

PDDI개발팀 (L1) - pddi-docs DB:
- PDDI개발팀은 LSI사업팀 소속 개발팀입니다.
- 주요 업무: RTL 설계, 검증

PDDI개발팀주간보고모음 (L2) - pddi-weekly-reports DB:
- 52주차 주간보고: 이번 주 RTL 코드 리뷰 완료, 신규 IP 개발 시작
- 51주차 주간보고: 버그 수정 15건, 테스트 커버리지 85% 달성
"""

# Mock DB 데이터
MOCK_DB = {
    "lsi-members": [
        {"id": "1", "content": "LSI사업팀 직속에는 장영동, 박준일, 김용준이 있습니다."},
        {"id": "2", "content": "LSI사업팀은 반도체 사업을 담당합니다."},
    ],
    "pddi-docs": [
        {"id": "1", "content": "PDDI개발팀은 LSI사업팀 소속 개발팀입니다."},
        {"id": "2", "content": "PDDI개발팀의 주요 업무는 RTL 설계 및 검증입니다."},
        {"id": "3", "content": "PDDI개발팀은 주간보고를 매주 작성합니다."},
    ],
    "pddi-weekly-reports": [
        {"id": "1", "content": "52주차 주간보고: RTL 코드 리뷰 완료, 신규 IP 개발 시작"},
        {"id": "2", "content": "51주차 주간보고: 버그 수정 15건, 테스트 커버리지 85% 달성"},
        {"id": "3", "content": "50주차 주간보고: 시뮬레이션 환경 개선, 성능 최적화"},
    ],
}


def mock_retrieve(db_ids, query, top_k=3):
    """Mock RAG 검색"""
    results = []
    for db_id in db_ids:
        if db_id in MOCK_DB:
            for doc in MOCK_DB[db_id]:
                # 간단한 키워드 매칭
                score = 0.5
                query_words = set(query.lower().split())
                content_words = set(doc["content"].lower().split())
                overlap = len(query_words & content_words)
                if overlap > 0:
                    score = min(0.5 + overlap * 0.1, 0.9)
                results.append({
                    "content": doc["content"],
                    "metadata": {"db_id": db_id, "doc_id": doc["id"]},
                    "score": score
                })
    
    # 점수순 정렬
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def mock_generate_answer(context, question, chatbot_name):
    """Mock LLM 답변 생성"""
    if not context:
        return f"[{chatbot_name}] 죄송합니다. 관련 정보를 찾을 수 없습니다."
    
    # 컨텍스트 기반 간단한 답변 생성
    if "52주차" in question and "주간보고" in question:
        if "52주차 주간보고" in str(context):
            return f"[{chatbot_name}] 52주차 주간보고 내용:\n- RTL 코드 리뷰 완료\n- 신규 IP 개발 시작"
    
    if "PDDI개발팀" in question:
        return f"[{chatbot_name}] PDDI개발팀은 LSI사업팀 소속 개발팀으로 RTL 설계 및 검증 업무를 수행합니다."
    
    if "구성원" in question or "누구" in question:
        return f"[{chatbot_name}] LSI사업팀 구성원: 장영동, 박준일, 김용준"
    
    return f"[{chatbot_name}] 질문에 대한 답변: {context[:100]}..."
