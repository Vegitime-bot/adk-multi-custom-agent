#!/usr/bin/env python3
"""
핵심 TC 10개 - 타임아웃 60초, 순차 실행 (병렬 제거)
"""
import requests
import json
import time
import uuid

BASE = "http://localhost:8080/api"
TIMEOUT = 60

def chat(cid: str, msg: str, sid: str = None) -> dict:
    sid = sid or f"t-{uuid.uuid4().hex[:6]}"
    try:
        r = requests.post(f"{BASE}/chat", json={"chatbot_id": cid, "message": msg, "session_id": sid, "user_id": "t"},
                       timeout=TIMEOUT, stream=True)
        full = []
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                try:
                    d = json.loads(line[6:])
                    if "chunk" in d: full.append(d["chunk"])
                    if "done" in d: break
                    if "error" in d: return {"ok": False, "err": d["error"], "txt": "".join(full), "sid": sid}
                except: pass
        txt = "".join(full)
        ok = bool(txt) and "[위임 결과를 받지 못" not in txt and "[답변을 생성할 수 없습니다]" not in txt
        return {"ok": ok, "txt": txt, "sid": sid}
    except Exception as e:
        return {"ok": False, "err": str(e), "txt": "", "sid": sid}

print(f"=== TC10 검증 @ {time.strftime('%H:%M:%S')} (timeout={TIMEOUT}s) ===\n")

results = []
def ok(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"  {'✅' if cond else '❌'} {name}: {detail}")

# TC1~2: 기본
print("[그룹1] 기본 연결")
ok("TC1_Health", requests.get(f"{BASE}/debug/health", timeout=10).status_code == 200)
bots = requests.get(f"{BASE}/chatbots", timeout=10).json()
ok("TC2_BotList", len(bots) > 0, f"{len(bots)} bots")

# TC3~5: Delegation 핵심 (순차, timeout 충분히)
print("\n[그룹2] Delegation 핵심")
r3 = chat("pddi_total", "회의록 요약해줘", "tc3")
ok("TC3_ParentDelegate_Minutes", r3["ok"] and len(r3["txt"]) > 30, f"len={len(r3['txt'])}")

r4 = chat("pddi_total", "주간보고 정리해줘", "tc4")
ok("TC4_ParentDelegate_Weekly", r4["ok"] and len(r4["txt"]) > 30, f"len={len(r4['txt'])}")

r5 = chat("pddi_minutes", "회의록 검색해줘", "tc5")
ok("TC5_ChildDirect", r5["ok"] and len(r5["txt"]) > 10, f"len={len(r5['txt'])}")

# TC6~8: 계층 구조
print("\n[그룹3] 계층 구조")
r6 = chat("chatbot_tech", "백엔드 아키텍처 문서 찾아줘", "tc6")
ok("TC6_TechHierarchy", r6["ok"], f"len={len(r6['txt'])}")

r7 = chat("chatbot_hr", "휴가 정책 알려줘", "tc7")
ok("TC7_HRHierarchy", r7["ok"], f"len={len(r7['txt'])}")

r8 = chat("chatbot_company", "회사 소개해줘", "tc8")
ok("TC8_CompanyDirect", r8["ok"], f"len={len(r8['txt'])}")

# TC9: 세션 맥락
print("\n[그룹4] 세션 맥락")
s = f"sess-{uuid.uuid4().hex[:6]}"
r9a = chat("pddi_total", "안녕", s)
r9b = chat("pddi_total", "방금 인사했지?", s)
ok("TC9_SessionContext", r9a["ok"] and r9b["ok"], f"r1={len(r9a['txt'])} r2={len(r9b['txt'])}")

# TC10: fail-closed 버그 수정 확인
print("\n[그룹5] Fail-closed 가드")
r10 = chat("pddi_total", "이번 주 회의록 알려줘", "tc10")
has_fail = "위임 결과를 받지 못" in r10["txt"] or "답변을 생성할 수 없습니다" in r10["txt"]
ok("TC10_NoFailClosed", r10["ok"] and not has_fail, f"len={len(r10['txt'])} fail_triggered={has_fail}")

# 요약
print(f"\n{'='*50}")
p = sum(1 for _, c, _ in results if c)
t = len(results)
print(f"결과: {p}/{t} PASS ({p/t*100:.0f}%)")
for name, cond, det in results:
    if not cond:
        print(f"  ❌ {name}: {det}")
if p == t:
    print("🎉 전체 PASS!")

with open("tc10_results.json", "w") as f:
    json.dump({"ts": time.strftime("%H:%M:%S"), "passed": p, "total": t,
               "details": [{"n":n,"ok":c,"d":d} for n,c,d in results]}, f)
print("저장: tc10_results.json")
