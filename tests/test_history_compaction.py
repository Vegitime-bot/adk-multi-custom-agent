#!/usr/bin/env python3
"""
히스토리 압축 기능 테스트 스크립트

테스트 시나리오:
1. "A회의록 검색해줘" -> 답변
2. "이 리스크 헤지 설명해" -> 히스토리 압축으로 "A회의록 리스크 헤지"로 확장되어 검색

실행:
    python tests/test_history_compaction.py
"""

import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.models import Message


def compact_history(history: list, max_turns: int = 3) -> str:
    """
    대화 히스토리를 압축하여 검색 컨텍스트 생성
    
    Args:
        history: 메시지 리스트 (user/assistant pairs)
        max_turns: 압축할 최근 턴 수
        
    Returns:
        압축된 히스토리 컨텍스트 문자열
    """
    if not history or len(history) < 2:
        return ""
    
    # 최근 N개 턴 (user + assistant = 2개씩) 추출
    recent = history[-(max_turns * 2):]
    
    # 간단한 키워드 기반 압축 (향후 LLM 기반으로 개선 가능)
    compact_parts = []
    for msg in recent:
        if msg.role == "user":
            # 사용자 질문에서 핵심 키워드 추출
            content = msg.content.strip()
            if content:
                compact_parts.append(f"Q: {content[:100]}")
        elif msg.role == "assistant":
            # 답변에서 핵심 내용 추출 (앞부분만)
            content = msg.content.strip()
            if content:
                # 주요 키워드 포함한 첫 문장 추출
                first_sentence = content.split('.')[0] if '.' in content else content[:100]
                compact_parts.append(f"A: {first_sentence[:150]}")
    
    return "\n".join(compact_parts)


def build_contextual_query(compacted_history: str, message: str) -> str:
    """
    압축된 히스토리와 현재 질문을 결합한 검색 쿼리 생성
    
    Examples:
        - "A회의록 검색해줘" + "이 리스크 헤지 설명해" 
          -> "A회의록 리스크 헤지 설명해"
    """
    if not compacted_history:
        return message
    
    # 히스토리에서 주요 키워드/주제 추출
    history_keywords = extract_keywords(compacted_history)
    
    # 현재 질문이 모호한 대명사/지시어로 시작하는지 확인
    vague_starts = ['이 ', '이것', '이거', '그 ', '그것', '그거', '저 ', '저것', '이번', '위의', '앞서', '지금']
    is_vague = any(message.startswith(v) for v in vague_starts)
    
    if is_vague and history_keywords:
        # 대명사를 히스토리 키워드로 치환
        # 예: "이 리스크 헤지" -> "A회의록 리스크 헤지"
        return f"{history_keywords} {message}"
    
    return message


def extract_keywords(text: str) -> str:
    """텍스트에서 핵심 키워드 추출 (회의록명, 프로젝트명 등)"""
    import re
    
    # 회의록/문서 관련 패턴
    doc_patterns = [
        r'([A-Z가-힣]+\d*\s*(?:회의록|보고서|주간보고|주보|회의|문서))',
        r'([A-Z가-힣]+\d*\s*(?:minutes|report|meeting|doc))',
    ]
    
    keywords = []
    for pattern in doc_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        keywords.extend(matches)
    
    # 중복 제거 및 결합
    unique_keywords = list(dict.fromkeys(keywords))
    return " ".join(unique_keywords[:3])  # 최대 3개 키워드


def test_compact_history():
    """히스토리 압축 기능 테스트"""
    print("=" * 60)
    print("테스트 1: 히스토리 압축 기능")
    print("=" * 60)
    
    # 테스트 히스토리 생성
    history = [
        Message(role="user", content="A회의록 검색해줘"),
        Message(role="assistant", content="A회의록에는 다음 내용이 있습니다:\n1. 리스크 헤지 관련 논의\n2. Z 프로젝트 일정 조정\n\n어떤 내용이 궁금하신가요?"),
        Message(role="user", content="이 리스크 헤지 설명해"),
    ]
    
    # 히스토리 압축 테스트
    compacted = compact_history(history)
    print(f"\n원본 히스토리 ({len(history)}개 메시지):")
    for msg in history:
        print(f"  [{msg.role}] {msg.content[:50]}...")
    
    print(f"\n압축된 히스토리:\n{compacted}")
    
    # 검증
    assert "A회의록" in compacted, "압축 결과에 'A회의록'이 포함되어야 함"
    assert "리스크 헤지" in compacted, "압축 결과에 '리스크 헤지'가 포함되어야 함"
    print("\n✅ 히스토리 압축 테스트 통과")


def test_build_contextual_query():
    """검색 쿼리 확장 기능 테스트"""
    print("\n" + "=" * 60)
    print("테스트 2: 검색 쿼리 확장 기능")
    print("=" * 60)
    
    # 테스트 케이스들
    test_cases = [
        {
            "name": "대명사로 시작하는 질문 (압축된 히스토리 있음)",
            "compacted": "Q: A회의록 검색해줘\nA: A회의록에는 리스크 헤지 관련 논의가 있습니다",
            "message": "이 리스크 헤지 설명해",
            "expected_contains": ["A회의록", "리스크 헤지"]
        },
        {
            "name": "구체적인 질문 (압축 불필요)",
            "compacted": "Q: A회의록 검색해줘",
            "message": "B프로젝트 일정 알려줘",
            "expected_contains": ["B프로젝트"]  # 압축된 히스토리와 관계없이 원본 유지
        },
        {
            "name": "빈 히스토리",
            "compacted": "",
            "message": "안녕하세요",
            "expected_equals": "안녕하세요"
        },
        {
            "name": "그것으로 시작하는 질문",
            "compacted": "Q: 주간보고 검색해줘\nA: 52주차 주간보고에는 매출 관련 내용이 있습니다",
            "message": "그것 자세히 설명해",
            "expected_contains": ["주간보고"]
        },
    ]
    
    for tc in test_cases:
        print(f"\n[케이스: {tc['name']}]")
        print(f"  압축된 히스토리: {tc['compacted'][:60]}...")
        print(f"  현재 질문: {tc['message']}")
        
        result = build_contextual_query(tc['compacted'], tc['message'])
        print(f"  확장된 쿼리: {result}")
        
        if 'expected_contains' in tc:
            for expected in tc['expected_contains']:
                assert expected in result, f"'{expected}'가 결과에 포함되어야 함"
        
        if 'expected_equals' in tc:
            assert result == tc['expected_equals'], f"결과가 '{tc['expected_equals']}'와 같아야 함"
        
        print(f"  ✅ 통과")
    
    print("\n✅ 검색 쿼리 확장 테스트 통과")


def test_extract_keywords():
    """키워드 추출 기능 테스트"""
    print("\n" + "=" * 60)
    print("테스트 3: 키워드 추출 기능")
    print("=" * 60)
    
    test_cases = [
        ("A회의록에는 리스크 헤지 관련 논의가 있습니다", ["A회의록"]),
        ("PDDI 52주차 주간보고를 검색했습니다", ["주간보고"]),
        ("B프로젝트 분기 보고서 내용입니다", ["보고서"]),
        ("인사정책 회의록을 확인했어요", ["회의록"]),
    ]
    
    for text, expected_keywords in test_cases:
        print(f"\n입력: {text}")
        result = extract_keywords(text)
        print(f"추출된 키워드: {result}")
        
        for kw in expected_keywords:
            assert kw in result, f"'{kw}'가 추출되어야 함"
        print(f"  ✅ 통과")
    
    print("\n✅ 키워드 추출 테스트 통과")


def test_end_to_end_scenario():
    """End-to-End 시나리오 테스트"""
    print("\n" + "=" * 60)
    print("테스트 4: End-to-End 시나리오")
    print("=" * 60)
    
    # 시나리오: 회의록 검색 -> 후속 질문
    print("\n[시나리오: 회의록 검색 후 후속 질문]")
    
    # 1차 대화
    history = [
        Message(role="user", content="A회의록 검색해줘"),
        Message(role="assistant", content="A회의록에는 리스크 헤지, Z 프로젝트 일정 조정 내용이 있습니다."),
    ]
    
    # 2차 대화 (후속 질문)
    current_message = "이 리스크 헤지에 대해 자세히 설명해"
    
    # 히스토리 압축
    compacted = compact_history(history)
    print(f"1. 히스토리 압축:\n   {compacted.replace(chr(10), ' | ')}")
    
    # 쿼리 확장
    enhanced = build_contextual_query(compacted, current_message)
    print(f"2. 원본 질문: '{current_message}'")
    print(f"3. 확장된 쿼리: '{enhanced}'")
    
    # 검증
    assert "A회의록" in enhanced, "확장된 쿼리에 'A회의록'이 포함되어야 함"
    assert "리스크 헤지" in enhanced, "확장된 쿼리에 '리스크 헤지'가 포함되어야 함"
    
    print("\n✅ End-to-End 시나리오 테스트 통과")


if __name__ == "__main__":
    print("히스토리 압축 기능 테스트 시작")
    print("=" * 60)
    
    try:
        test_compact_history()
        test_build_contextual_query()
        test_extract_keywords()
        test_end_to_end_scenario()
        
        print("\n" + "=" * 60)
        print("모든 테스트 통과! ✅")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
