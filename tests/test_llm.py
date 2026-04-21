"""
LLM 연결 테스트 스크립트

실행 방법:
    source .venv/bin/activate
    python test_llm.py

테스트 항목:
    1. 환경변수 확인
    2. LLM 서버 연결 확인
    3. 간단한 채팅 테스트
"""

import os
from backend.config import settings
from backend.llm.client import get_llm_client

print("=" * 50)
print("LLM 연결 테스트")
print("=" * 50)

# 1. 환경변수 확인
print("\n[1] 환경변수 확인")
print(f"  LLM_BASE_URL: {settings.LLM_BASE_URL}")
print(f"  LLM_API_KEY: {'설정됨' if settings.LLM_API_KEY and settings.LLM_API_KEY != 'dummy-key' else '미설정/dummy-key'}")
print(f"  LLM_DEFAULT_MODEL: {settings.LLM_DEFAULT_MODEL}")
print(f"  LLM_TIMEOUT: {settings.LLM_TIMEOUT}")

# 2. LLM 서버 연결 테스트
print("\n[2] LLM 서버 연결 테스트")
client = get_llm_client()

try:
    # 모델 목록 확인
    models = client.models.list()
    print(f"  ✅ 모델 목록 조회 성공")
    print(f"  사용 가능한 모델 수: {len(models.data) if hasattr(models, 'data') else 'N/A'}")
except Exception as e:
    print(f"  ❌ 모델 목록 조회 실패: {e}")

# 3. 간단한 채팅 테스트
print("\n[3] 간단한 채팅 테스트")
print("  질문: '안녕하세요?'")

try:
    response = client.chat.completions.create(
        model=settings.LLM_DEFAULT_MODEL,
        messages=[{"role": "user", "content": "안녕하세요?"}],
        max_tokens=50,
        stream=False
    )
    answer = response.choices[0].message.content
    print(f"  ✅ 응답 수신 성공")
    print(f"  답변: {answer}")
except Exception as e:
    print(f"  ❌ 채팅 요청 실패: {e}")

# 4. 스트리밍 테스트
print("\n[4] 스트리밍 테스트")
print("  질문: 'FastAPI란 무엇인가요?'")

try:
    stream = client.chat.completions.create(
        model=settings.LLM_DEFAULT_MODEL,
        messages=[{"role": "user", "content": "FastAPI란 무엇인가요? 한 문장으로 답해주세요."}],
        max_tokens=50,
        stream=True
    )
    
    print("  ✅ 스트리밍 응답 수신 중...")
    print("  답변: ", end="", flush=True)
    
    full_response = []
    for chunk in stream:
        if chunk.choices[0].delta.content:
            text = chunk.choices[0].delta.content
            print(text, end="", flush=True)
            full_response.append(text)
    
    print()  # 줄바꿈
    print(f"  전체 응답 길이: {len(''.join(full_response))}자")
    
except Exception as e:
    print(f"  ❌ 스트리밍 요청 실패: {e}")

print("\n" + "=" * 50)
print("테스트 완료")
print("=" * 50)
