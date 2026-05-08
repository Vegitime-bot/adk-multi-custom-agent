# route_and_stream_with_tools() 수정 지침

## 문제
function_call, function_response, invocation_results가 SSE로 채팅에 노출됨
→ 내부 도구 호출 과정이 사용자 화면에 보임

## 수정 원칙
- text chunk만 yield self._sse_data()로 스트리밍
- function_call/function_response/invocation_results는 로그만 남기고 yield 금지

## 수정 3곳

### 1) function_call 감지 시
**삭제:**
```python
tool_info = f"[도구 호출: {part.function_call.name}]"
yield self._sse_data(tool_info)
```
**변경:**
```python
logger.info(f"[DelegationRouter] Tool call: {part.function_call.name}")
# 로그만 남기고 yield 없음
```

### 2) function_response 감지 시
**삭제:**
```python
if hasattr(part.function_response, 'output') ...:
    yield self._sse_data(output_str)
elif hasattr(part.function_response, 'result') ...:
    yield self._sse_data(result_str)
elif hasattr(part.function_response, 'response') ...:
    yield self._sse_data(response_str)
```
**변경:**
```python
logger.info(f"[DelegationRouter] Tool response received")
# 로그만 남기고 yield 없음
```

### 3) invocation_results 감지 시
**삭제:**
```python
for result in event.actions.invocation_results:
    result_str = str(result)
    full_response.append(result_str)
    yield self._sse_data(result_str)
```
**변경:**
```python
logger.info(f"[DelegationRouter] Invocation results received: {len(event.actions.invocation_results)}")
# 로그만 남기고 yield + append 없음
```

## 원리
ADK Runner는 도구 호출 후 LLM이 최종 답변을 text chunk로 돌려줌.
text chunk만 스트리밍하면 됨. 중간 과정 노출 금지.
