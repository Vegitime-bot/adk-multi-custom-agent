#!/usr/bin/env python3
"""
confidence 계산 로직 테스트 스크립트
"""

def calculate_confidence(context: str, message: str) -> int:
    """
    검색 결과 기반 Confidence 계산 (개선된 버전)
    """
    if not context or not context.strip():
        return 10

    content_length = len(context)
    message_words = [kw.lower() for kw in message.split() if len(kw) > 1]
    context_lower = context.lower()

    keywords_found = sum(1 for kw in set(message_words) if kw in context_lower)
    keyword_match_ratio = keywords_found / len(message_words) if message_words else 0

    doc_count = context.count('###') + context.count('---') + 1
    avg_doc_length = content_length / doc_count if doc_count > 0 else content_length

    length_score = min(40, content_length / 125)
    keyword_score = keyword_match_ratio * 30
    density_score = min(25, avg_doc_length / 40)

    total_score = int(length_score + keyword_score + density_score)

    if keyword_match_ratio >= 0.7:
        total_score += 10
    elif keyword_match_ratio < 0.2:
        total_score -= 10

    return max(15, min(95, total_score))


# 테스트 케이스
test_cases = [
    ("", "테스트 질문", "컨텍스트 없음"),
    ("짧은 내용", "테스트", "짧은 컨텍스트"),
    ("Verilog HDL is a hardware description language used for digital circuit design. It allows designers to describe the behavior and structure of electronic systems.",
     "Verilog가 뭐야?", "관련 내용 있음 (키워드 매칭)"),
    ("""### 문서 1
Python은 고급 프로그래밍 언어입니다.

### 문서 2
FastAPI는 빠른 웹 프레임워크입니다.

### 문서 3
Docker는 컨테이너 기술입니다.""",
     "Python과 FastAPI 사용법", "긴 컨텍스트 + 다중 문서"),
    ("A" * 3000, "관련 없는 질문", "긴 컨텍스트지만 키워드 불일치"),
    ("회사 규정에 따르면 연차는 1년에 15일이며, 추가로 근속년수에 따라 가산됩니다. 급여는 매월 25일에 지급됩니다.",
     "연차는 몇 일이야?", "실제 유사 케이스 - 관련 내용 있음"),
]

print("=" * 60)
print("Confidence 계산 테스트")
print("=" * 60)

for context, message, desc in test_cases:
    confidence = calculate_confidence(context, message)
    print(f"\n[테스트: {desc}]")
    print(f"  메시지: {message}")
    print(f"  컨텍스트 길이: {len(context)}자")
    print(f"  → Confidence: {confidence}%")

print("\n" + "=" * 60)
print("테스트 완료!")
print("=" * 60)
