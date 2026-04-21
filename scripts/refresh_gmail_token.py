#!/usr/bin/env python3
"""
Gmail OAuth 토큰 갱신 스크립트
refresh_token으로 새 access_token을 발급받습니다.
"""

import json
import requests
from pathlib import Path

# 설정 파일 경로
CONFIG_DIR = Path.home() / ".config" / "gmail-agent"
TOKEN_FILE = CONFIG_DIR / "token.json"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"


def load_credentials():
    """credentials.json에서 클라이언트 정보 로드"""
    with open(CREDENTIALS_FILE, 'r') as f:
        creds = json.load(f)
    return creds['installed']


def load_token():
    """token.json에서 현재 토큰 로드"""
    with open(TOKEN_FILE, 'r') as f:
        return json.load(f)


def refresh_access_token():
    """refresh_token으로 새 access_token 발급"""
    # 설정 로드
    creds = load_credentials()
    token_data = load_token()
    
    client_id = creds['client_id']
    client_secret = creds['client_secret']
    refresh_token = token_data['refresh_token']
    
    # 토큰 갱신 요청
    token_url = "https://oauth2.googleapis.com/token"
    
    payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }
    
    print("토큰 갱신 요청 중...")
    response = requests.post(token_url, data=payload)
    
    if response.status_code == 200:
        new_token = response.json()
        
        # 기존 토큰 데이터 업데이트
        token_data['token'] = new_token['access_token']
        token_data['expiry'] = None  # 필요시 계산
        
        # 파일 저장
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f, indent=2)
        
        print("✅ 토큰 갱신 성공!")
        print(f"Access Token: {new_token['access_token'][:50]}...")
        print(f"Expires in: {new_token.get('expires_in', 'unknown')} seconds")
        
        return new_token['access_token']
    else:
        print(f"❌ 토큰 갱신 실패: {response.status_code}")
        print(f"Error: {response.text}")
        return None


if __name__ == "__main__":
    if not CREDENTIALS_FILE.exists():
        print(f"❌ credentials.json 파일을 찾을 수 없습니다: {CREDENTIALS_FILE}")
        exit(1)
    
    if not TOKEN_FILE.exists():
        print(f"❌ token.json 파일을 찾을 수 없습니다: {TOKEN_FILE}")
        exit(1)
    
    new_token = refresh_access_token()
    
    if new_token:
        print("\n📧 이제 메일 발송이 가능합니다!")
    else:
        print("\n⚠️ 토큰 갱신에 실패했습니다. 다시 인증이 필요할 수 있습니다.")
