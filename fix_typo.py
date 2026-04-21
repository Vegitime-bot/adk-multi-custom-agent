#!/usr/bin/env python3
import re

# app.js 파일 읽기
with open('/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent/static/admin/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# '챗봘'을 '챗봇'으로 치환 (주석 포함 모든 곳)
content = content.replace('챗봘', '챗봇')

# 파일 쓰기
with open('/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent/static/admin/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ app.js: '챗봘' → '챗봇' 치환 완료")

# index.html 파일도 처리
with open('/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent/static/admin/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('챗봘', '챗봇')

with open('/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent/static/admin/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ index.html: '챗봘' → '챗봇' 치환 완료")

# static/index.html도 처리
try:
    with open('/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent/static/index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace('챗봘', '챗봇')
    with open('/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent/static/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ static/index.html: '챗봘' → '챗봇' 치환 완료")
except:
    pass

print("\n모든 파일 처리 완료!")
