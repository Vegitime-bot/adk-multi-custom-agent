#!/usr/bin/env python3
"""
TC 20개 통합 테스트 (사내 환경 시뮬레이션)
timeout=60s, 순차 실행
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
        fail = "[위임 결과를 받지 못" in txt or "[답변을 생성할 수 없습니다]" in txt
        ok = bool(txt) and not fail
        return {"ok": ok, "txt": txt, "sid": sid, "len": len(txt)}
    except Exception as e:
        return {"ok": False, "err": str(e), "txt": "", "sid": sid, "len": 0}

print(f"=== TC20 @ {time.strftime('%H:%M:%S')} ===\n")
results = []
def ok(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"  {'✅' if cond else '❌'} {name}: {detail}")

# === 그룹1: 기본 연결 (TC1-2) ===
print("[그룹1] 기본 연결")
ok("TC1_ServerHealth", requests.get(f"{BASE}/debug/health", timeout=10).status_code == 200)
bots = requests.get(f"{BASE}/chatbots", timeout=10).json()
ok("TC2_ChatbotList", len(bots) > 0, f"{len(bots)} bots loaded")

# === 그룹2: Delegation 핵심 (TC3-5) ===
print("\n[그룹2] Delegation 핵심")
r = chat("pddi_total", "회의록 요약해줘", "tc3")
ok("TC3_ParentToChild_Delegate", r["ok"] and r["len"] > 30, f"len={r['len']}")
r = chat("pddi_total", "주간보고 정리해줘", "tc4")
ok("TC4_ParentToChild_Weekly", r["ok"] and r["len"] > 30, f"len={r['len']}")
r = chat("pddi_minutes", "회의록 검색해줘", "tc5")
ok("TC5_ChildDirectQuery", r["ok"] and r["len"] > 10, f"len={r['len']}")

# === 그룹3: 계층 구조 (TC6-8) ===
print("\n[그룹3] 계층 구조")
r = chat("chatbot_tech", "백엔드 아키텍처 문서 찾아줘", "tc6")
ok("TC6_TechParent_Backend", r["ok"], f"len={r['len']}")
r = chat("chatbot_hr", "휴가 정책 알려줘", "tc7")
ok("TC7_HRParent_Policy", r["ok"], f"len={r['len']}")
r = chat("chatbot_company", "회사 소개해줘", "tc8")
ok("TC8_Standalone_Company", r["ok"], f"len={r['len']}")

# === 그룹4: 세션/맥락 (TC9-10) ===
print("\n[그룹4] 세션/맥락")
s = f"sess-{uuid.uuid4().hex[:6]}"
r1 = chat("pddi_total", "안녕하세요", s)
r2 = chat("pddi_total", "방금 인사했어?", s)
ok("TC9_Session_Context", r1["ok"] and r2["ok"], f"r1={r1['len']} r2={r2['len']}")

r = chat("pddi_total", "이번 주 회의록 알려줘", "tc10")
fail = "위임 결과를 받지 못" in r["txt"] or "답변을 생성할 수 없습니다" in r["txt"]
ok("TC10_FailClosed_NoTrigger", r["ok"] and not fail, f"len={r['len']} fail={fail}")

# === 그룹5: 에지 케이스 (TC11-15) ===
print("\n[그룹5] 에지 케이스")
r = chat("pddi_total", "넌 뭐하는 챗봇이야?", "tc11")
ok("TC11_Parent_GeneralQuery", r["ok"] and r["len"] > 10, f"len={r['len']}")

r = chat("nonexistent_bot_xyz", "안녕", "tc12")
ok("TC12_NonExistentBot", not r["ok"] or "not found" in r["txt"].lower() or "error" in r["txt"].lower(), f"handled={not r['ok']}")

r = chat("pddi_total", "", "tc13")
ok("TC13_EmptyMessage", r["ok"] or not r.get("err","").startswith("Traceback"), f"handled={r['ok']}")

r = chat("pddi_total", "회의록"*50, "tc14")
ok("TC14_LongMessage", r["ok"] or not r.get("err","").startswith("Traceback"), f"len={r['len']}")

r = chat("pddi_total", "!@#$ 회의록 ???", "tc15")
ok("TC15_SpecialChars", r["ok"] or not r.get("err","").startswith("Traceback"), f"len={r['len']}")

# === 그룹6: Debug API (TC16-17) ===
print("\n[그룹6] Debug API")
try:
    d = requests.get(f"{BASE}/debug/agents", timeout=10).json()
    ok("TC16_DebugAgents", len(d.get("agents",[])) > 0, f"agents={len(d.get('agents',[]))}")
except Exception as e:
    ok("TC16_DebugAgents", False, str(e))

try:
    ds = chat("pddi_total", "테스트", "tc17-debug")
    d = requests.get(f"{BASE}/debug/sessions/tc17-debug", timeout=10).json()
    ok("TC17_DebugSession", d.get("session_id") == "tc17-debug", f"found={d.get('session_id')}")
except Exception as e:
    ok("TC17_DebugSession", False, str(e))

# === 그룹7: 추가 계층 (TC18-20) ===
print("\n[그룹7] 추가 계층/위임")
r = chat("chatbot_rtl_verilog", "Verilog 모듈 설명해줘", "tc18")
ok("TC18_Child_RTL", r["ok"], f"len={r['len']}")

r = chat("chatbot_hr_policy", "연차 휴가 규정", "tc19")
ok("TC19_Child_HRPolicy", r["ok"], f"len={r['len']}")

# TC20: Parent가 답변 못 하는 질문 → 위임 필수
r = chat("pddi_total", "지난 달 모든 회의록 요약", "tc20")
ok("TC20_Delegation_Required", r["ok"] and r["len"] > 30, f"len={r['len']}")

# === 요약 ===
print(f"\n{'='*55}")
p = sum(1 for _, c, _ in results if c)
t = len(results)
print(f"총 {t}개 중 {p}개 PASS ({p/t*100:.1f}%)")
for name, cond, det in results:
    if not cond:
        print(f"  ❌ {name}: {det}")
if p == t:
    print("🎉 TC20 전체 PASS!")

with open("tc20_results.json", "w") as f:
    json.dump({"ts": time.strftime("%H:%M:%S"), "passed": p, "total": t,
               "results": [{"n":n,"ok":c,"d":d} for n,c,d in results]}, f)
print("저장: tc20_results.json")
