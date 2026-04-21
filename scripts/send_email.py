#!/usr/bin/env python3
"""
Gmail API로 HTML 파일과 이미지 첨부 메일 발송
"""

import json
import base64
import os
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import requests

# 설정
CONFIG_DIR = Path.home() / ".config" / "gmail-agent"
TOKEN_FILE = CONFIG_DIR / "token.json"
PROJECT_DIR = Path("/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent")

# 발송 정보
TO_EMAIL = "yd86.jang@samsung.com"
FROM_EMAIL = "vegitime@gmail.com"  # OAuth 인증된 계정
SUBJECT = "[Multi Custom Agent] 기술 지원팀용 프로모션 자료"


def load_access_token():
    """token.json에서 access_token 로드"""
    with open(TOKEN_FILE, 'r') as f:
        token_data = json.load(f)
    return token_data['token']


def create_email_with_attachments():
    """HTML과 이미지 첨부된 MIME 메시지 생성"""
    msg = MIMEMultipart('related')
    msg['to'] = TO_EMAIL
    msg['from'] = FROM_EMAIL
    msg['subject'] = SUBJECT
    
    # HTML 파일 읽기
    html_path = PROJECT_DIR / "docs" / "promo-onepager.html"
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # HTML 본문 생성
    msg_alternative = MIMEMultipart('alternative')
    msg.attach(msg_alternative)
    
    # 텍스트 버전
    text_content = """Multi Custom Agent Service 프로모션 자료입니다.

첨부 파일:
- promo-onepager.html (기술 지원팀 버전)
- 01-chat-ui.png
- 02-admin-ui.png  
- 03-admin-hierarchy.png
"""
    msg_alternative.attach(MIMEText(text_content, 'plain', 'utf-8'))
    
    # HTML 버전 (이미지 참조 수정)
    msg_alternative.attach(MIMEText(html_content, 'html', 'utf-8'))
    
    # 이미지 파일 첨부
    images = [
        ("01-chat-ui.png", "image01"),
        ("02-admin-ui.png", "image02"),
        ("03-admin-hierarchy.png", "image03"),
    ]
    
    for filename, cid in images:
        img_path = PROJECT_DIR / "docs" / "assets" / filename
        if img_path.exists():
            with open(img_path, 'rb') as f:
                img_data = f.read()
            
            # MIME 첨부
            mime_base = MIMEBase('image', 'png')
            mime_base.set_payload(img_data)
            encoders.encode_base64(mime_base)
            mime_base.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            msg.attach(mime_base)
            print(f"  ✅ 첨부: {filename}")
        else:
            print(f"  ⚠️ 파일 없음: {filename}")
    
    # HTML 파일 첨부
    html_attachment = MIMEBase('text', 'html')
    with open(html_path, 'rb') as f:
        html_attachment.set_payload(f.read())
    encoders.encode_base64(html_attachment)
    html_attachment.add_header('Content-Disposition', 'attachment; filename="promo-onepager.html"')
    msg.attach(html_attachment)
    print(f"  ✅ 첨부: promo-onepager.html")
    
    return msg


def send_email():
    """Gmail API로 메일 발송"""
    access_token = load_access_token()
    
    # MIME 메시지 생성
    print("📧 메일 작성 중...")
    msg = create_email_with_attachments()
    
    # base64 인코딩
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
    
    # Gmail API 호출
    print("📤 메일 발송 중...")
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "raw": raw_message
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ 메일 발송 성공!")
        print(f"   Message ID: {result.get('id')}")
        print(f"   To: {TO_EMAIL}")
        return True
    else:
        print(f"❌ 메일 발송 실패: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


if __name__ == "__main__":
    if not TOKEN_FILE.exists():
        print(f"❌ token.json 파일을 찾을 수 없습니다: {TOKEN_FILE}")
        print("먼저 refresh_gmail_token.py를 실행해주세요.")
        exit(1)
    
    send_email()
