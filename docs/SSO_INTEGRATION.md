# SSO 연동 가이드 (OIDC/OAuth2)

## 개요

사내 SSO 서버와 OIDC (OpenID Connect) / OAuth2 Authorization Code Flow로 연동합니다.

## 설정 방법

### 1. .env 파일 설정

```bash
# Mock Auth 비활성화
USE_MOCK_AUTH=false

# 사내 SSO 정보
SSO_ISSUER=https://sso.company.com
SSO_CLIENT_ID=your-app-client-id
SSO_CLIENT_SECRET=your-app-client-secret
SSO_REDIRECT_URI=http://localhost:8080/auth/acs

# 세션 보안 (32바이트 이상 랜덤 문자열)
SECRET_KEY=$(openssl rand -base64 32)
```

### 2. SSO 라우터 동작

| 엔드포인트 | 설명 |
|-----------|------|
| `/auth/sso` | SSO 로그인 시작 (SSO 서버로 리다이렉트) |
| `/auth/acs` | SSO 콜백 (Authorization Code 수신) |
| `/auth/logout` | 로그아웃 |
| `/auth/me` | 현재 로그인한 사용자 정보 |

### 3. SSO Flow

```
사용자 → /auth/sso → SSO 서버 로그인 → /auth/acs → 세션 생성 → 챗봇
```

## 수정이 필요한 부분

### `backend/api/sso.py` 파일 내 TODO 항목

#### 1. SSO_CONFIG 설정 (Line 20-40)
```python
SSO_CONFIG = {
    "issuer": getattr(settings, "SSO_ISSUER", "https://sso.company.com"),
    # TODO: 사내 SSO issuer URL 확인
    
    "client_id": getattr(settings, "SSO_CLIENT_ID", ""),
    # TODO: 사내에서 발급받은 Client ID
    
    "redirect_uri": getattr(settings, "SSO_REDIRECT_URI", ""),
    # TODO: SSO 서버에 등록된 콜백 URI와 일치해야 함
}
```

#### 2. Authorization 파라미터 (Line 70-80)
```python
params = {
    # ... 기본 파라미터들
    
    # TODO: 사내 SSO에 맞게 추가 파라미터 필요 시
    # "prompt": "login",  # 항상 로그인 화면 표시
    # "login_hint": "user@company.com",  # 사전 채워넣기
    # "acr_values": "urn:mace:incommon:iap:silver",  # 인증 수준
}
```

#### 3. 토큰 교환 방식 (Line 160-180)
```python
async def exchange_code_for_token(code: str, code_verifier: str):
    # TODO: 사내 SSO에서 Client Secret 대신 다른 인증 방식 사용 시 수정
    # - Basic Auth (client_id:client_secret base64)
    # - JWT Client Assertion
    # - mTLS
    ...
```

#### 4. 사용자 정보 매핑 (Line 190-220)
```python
async def sso_callback(...):
    # ...
    
    # TODO: 사내 SSO의 사용자 정보 필드명 확인
    request.session["user"] = {
        "id": user_info.get("sub"),        # OIDC 표준: sub
        "email": user_info.get("email"),   # OIDC 표준: email
        "name": user_info.get("name"),     # OIDC 표준: name
        
        # TODO: 사내 필드 추가
        # "employee_id": user_info.get("employee_number"),
        # "department": user_info.get("department"),
        # "role": user_info.get("roles", []),
    }
```

#### 5. JWT 검증 (선택, Line 200-220)
```python
async def get_user_info(...):
    # 방법 1: UserInfo Endpoint 호출
    
    # 방법 2: ID Token 직접 검증
    # TODO: 사내 SSO JWKS endpoint로 서명 검증 필요
    # jwks_url = f"{SSO_CONFIG['issuer']}/.well-known/jwks.json"
    ...
```

## 테스트 방법

### 1. Mock 모드로 테스트 (로컬 개발)
```bash
USE_MOCK_AUTH=true python app.py
# → /auth/* 엔드포인트 비활성화, 기존 mock_auth 사용
```

### 2. SSO 모드로 테스트 (사내망)
```bash
USE_MOCK_AUTH=false python app.py
# → 브라우저에서 http://localhost:8080/auth/sso 접속
```

## 디버깅

### 로그 확인
```python
# backend/api/sso.py에 로그 추가
import logging
logger = logging.getLogger(__name__)

logger.info(f"SSO callback: code={code}, state={state}")
logger.debug(f"Token response: {token_data}")
```

### 브라우저 개발자 도구
- Network 탭에서 `/auth/acs` 요청 확인
- Application → Cookies에서 세션 확인

### curl 테스트
```bash
# SSO 콜백 수동 테스트 (개발용)
curl -v "http://localhost:8080/auth/acs?code=xxx&state=yyy"
```

## 주의사항

1. **Client Secret 보안**: .env 파일만 사용, 절대 코드에 하드코딩 금지
2. **State 검증**: CSRF 방지 위해 반드시 구현됨 (sso.py에 포함)
3. **PKCE**: 모바일/SPA 지원 위해 code_challenge 사용 (sso.py에 포함)
4. **HTTPS**: 운영 환경에서는 반드시 HTTPS 사용

## 참고

- OIDC Discovery: `https://sso.company.com/.well-known/openid-configuration`
- FastAPI Security: https://fastapi.tiangolo.com/advanced/security/

