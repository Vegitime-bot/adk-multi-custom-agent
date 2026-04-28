# ADK Web Console 연결 가이드

## 🔍 현재 상황

Google ADK는 `adk web` 명령으로 내장 웹 콘솔을 제공합니다.
하지만 이는 **독립적인 FastAPI 서버**로 실행되며, 현재 프로젝트의 `app.py`와는 **별개**입니다.

```
┌─────────────────┐     ┌─────────────────┐
│   현재 서버      │     │  ADK Web Console │
│   (app.py)      │     │   (adk web)     │
│   port: 8080    │     │   port: 8000    │
│                 │     │                 │
│  Custom API     │     │  ADK Debug UI   │
│  + Web UI       │     │  + Agent Trace  │
└─────────────────┘     └─────────────────┘
        │                        │
        └────────┬───────────────┘
                 │
        ┌────────▼────────┐
        │   ADK Agents    │
        │  (공통 사용)    │
        └─────────────────┘
```

---

## ✅ 방법 1: ADK CLI Web Server 직접 실행

### 1-1. ADK 프로젝트 구조로 변경

ADK CLI는 특정 폴더 구조를 요구합니다:

```
adk-multi-custom-agent/
├── adk_agents/
│   ├── __init__.py
│   └── root_agent.py          # ← Root Agent 정의
├── chatbots/                  # ← JSON 설정
└── .env
```

### 1-2. Root Agent 파일 생성

```python
# adk_agents/__init__.py
from adk_agents.delegation_router_agent import get_router

def get_root_agent():
    """ADK Web Console용 Root Agent"""
    router = get_router()
    return router.root_agent
```

### 1-3. ADK Web 실행

```bash
cd /Users/vegitime/.openclaw/workspace/projects/adk-multi-custom-agent
source .venv/bin/activate

# ADK Web Console 실행
adk web --port 8000
```

접속: http://localhost:8000

---

## ✅ 방법 2: 현재 서버에 디버그 UI 통합 (권장)

### 2-1. 디버그 엔드포인트 추가

```python
# backend/api/debug.py
from fastapi import APIRouter
from adk_agents.delegation_router_agent import get_router

router = APIRouter(prefix="/api/debug", tags=["debug"])

@router.get("/agents")
async def list_agents():
    """등록된 ADK Agents 목록"""
    router = get_router()
    return {
        "root_agent": router.root_agent.name,
        "tools": [t.name for t in router.root_agent.tools],
        "sub_agents": list(router.sub_agent_cache.keys())
    }

@router.get("/sessions/{session_id}")
async def get_session_events(session_id: str):
    """세션 이벤트 조회"""
    from backend.adk.adk_session_wrapper import get_session_wrapper
    wrapper = get_session_wrapper()
    
    session = wrapper.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    # ADK 내부 세션 접근
    adk_sessions = getattr(wrapper._session_service, '_sessions', {})
    for key, adk_session in adk_sessions.items():
        if adk_session.session_id == session_id:
            events = []
            if hasattr(adk_session, 'events'):
                for event in adk_session.events:
                    events.append({
                        "role": getattr(event, 'role', 'unknown'),
                        "content": getattr(event, 'content', '')[:200],
                        "timestamp": getattr(event, 'timestamp', '')
                    })
            return {
                "session_id": session_id,
                "event_count": len(events),
                "events": events
            }
    
    return {"error": "ADK session not found"}

@router.post("/run")
async def debug_run(chatbot_id: str, message: str, session_id: str = None):
    """디버그 실행 (상세 로그)"""
    import asyncio
    from backend.api.chat_service_v2 import get_chat_service_v2
    
    service = get_chat_service_v2()
    
    chunks = []
    async for chunk in service.chat_stream(
        chatbot_id=chatbot_id,
        message=message,
        session_id=session_id or "debug-session"
    ):
        chunks.append(chunk)
    
    return {
        "chunks": chunks,
        "total_chunks": len(chunks)
    }
```

### 2-2. app.py에 라우터 등록

```python
# app.py
from backend.api.debug import router as debug_router

# ... 기존 라우터 등록 후
app.include_router(debug_router)
```

### 2-3. 사용 예시

```bash
# Agents 목록 조회
curl http://localhost:8080/api/debug/agents

# 세션 이벤트 조회
curl http://localhost:8080/api/debug/sessions/test-session-001

# 디버그 실행
curl -X POST http://localhost:8080/api/debug/run \
  -H "Content-Type: application/json" \
  -d '{
    "chatbot_id": "chatbot_company",
    "message": "인사 정책 알려줘",
    "session_id": "debug-001"
  }'
```

---

## ✅ 방법 3: OpenTelemetry Trace 연동 (고급)

### 3-1. OpenTelemetry 설정

```python
# backend/telemetry.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

def setup_telemetry():
    """OpenTelemetry 설정"""
    provider = TracerProvider()
    
    # Jaeger 또는 Zipkin으로 전송
    exporter = OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)
    return provider
```

### 3-2. ADK Runner에 Trace 추가

```python
# adk_agents/delegation_router_agent.py
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

class DelegationRouter:
    async def route_and_stream_with_tools(self, ...):
        with tracer.start_as_current_span("adk.route_and_stream") as span:
            span.set_attribute("chatbot_id", chatbot_id)
            span.set_attribute("message", message)
            
            async for event in runner.run_async(...):
                span.add_event("adk.event", {
                    "role": event.role,
                    "content_length": len(event.content)
                })
                yield event
```

### 3-3. Jaeger UI로 확인

```bash
# Jaeger 실행
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest

# 접속: http://localhost:16686
```

---

## 🎯 권장 방법

| 방법 | 난이도 | 효과 | 권장 여부 |
|------|--------|------|-----------|
| **방법 1: adk web** | 쉬움 | 기본 디버그 | ⭐⭐⭐ |
| **방법 2: Debug API** | 중간 | 커스텀 디버그 | ⭐⭐⭐⭐⭐ |
| **방법 3: OpenTelemetry** | 어려움 | 전체 추적 | ⭐⭐⭐⭐ |

**가장 현실적인 방법은 방법 2 (Debug API 추가)**입니다:
- 기존 서버와 통합
- 원하는 정보 노출
- Web UI에서도 호출 가능

---

## 🚀 다음 단계

1. **Debug API 구현** (방법 2)
2. **Web UI에 디버그 패널** 추가
3. **세션 이벤트 시각화**

어떤 방법으로 진행할까요?