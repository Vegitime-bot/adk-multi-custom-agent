# Users DB 설계 및 연동 전략

_작성일: 2026-03-27_

---

## users 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| knox_id | VARCHAR | 사용자 식별자 (PK) |
| name | VARCHAR | 한국어 이름 |
| team | VARCHAR | 소속 팀 |
| eng_name | VARCHAR | 영문 이름 |

- DB: PostgreSQL (챗봇 서비스 전용 신규 테이블)
- ORM: SQLAlchemy (FastAPI와 연동)

---

## User 모델

```python
from sqlalchemy import Column, String
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'

    knox_id  = Column(String(20), primary_key=True)
    name     = Column(String(50), nullable=False)
    team     = Column(String(50))
    eng_name = Column(String(100))

    def to_dict(self):
        return {
            "knox_id":  self.knox_id,
            "name":     self.name,
            "team":     self.team,
            "eng_name": self.eng_name,
        }
```

---

## Mock → DB 전환 전략

환경변수 두 개로 스위칭:

```
USE_MOCK_DB=true    → MockUserRepository 사용 (개발/테스트)
USE_MOCK_DB=false   → PostgreSQL 실제 연결 (운영)

USE_MOCK_AUTH=true  → SSO bypass, 고정 사용자 반환 (개발/테스트)
USE_MOCK_AUTH=false → 실제 OAuth SSO 검증 (운영)
```

---

## Repository 패턴

### 인터페이스
```python
from abc import ABC, abstractmethod

class UserRepository(ABC):
    @abstractmethod
    def get_user_by_knox_id(self, knox_id: str) -> dict | None:
        pass

    @abstractmethod
    def get_all_users(self) -> list[dict]:
        pass
```

### Mock 구현체
```python
MOCK_USERS = [
    {"knox_id": "jyd1234", "name": "장영동", "team": "AI팀", "eng_name": "Youngdong Jang"},
    {"knox_id": "kim5678", "name": "김철수", "team": "개발팀", "eng_name": "Chulsoo Kim"},
]

class MockUserRepository(UserRepository):
    def get_user_by_knox_id(self, knox_id: str):
        return next((u for u in MOCK_USERS if u["knox_id"] == knox_id), None)

    def get_all_users(self):
        return MOCK_USERS
```

### PostgreSQL 구현체
```python
from sqlalchemy.orm import Session

class PGUserRepository(UserRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_knox_id(self, knox_id: str):
        user = self.db.query(User).filter_by(knox_id=knox_id).first()
        return user.to_dict() if user else None

    def get_all_users(self):
        return [u.to_dict() for u in self.db.query(User).all()]
```

---

## Mock Auth (SSO bypass)

```python
def get_current_user(settings):
    if settings.USE_MOCK_AUTH:
        return {"knox_id": "jyd1234", "name": "장영동", "team": "AI팀"}
    else:
        # 실제 OAuth 토큰 검증 (SSO 코드 확인 후 구현)
        return verify_oauth_token(request)
```

---

## OAuth SSO 연동 (TBD)

- 사내 SSO 방식: **OAuth2**
- 실제 코드 확인 후 구현 예정
- 완료 시 `USE_MOCK_AUTH=false`로 전환

---

## config.py 설정 항목

```python
USE_MOCK_DB: bool = True
USE_MOCK_AUTH: bool = True
PG_HOST: str = "localhost"
PG_PORT: int = 5432
PG_DB: str = "chatbot_db"
PG_USER: str = "postgres"
PG_PASSWORD: str = ""
```

---

_관련 문서: [ARCHITECTURE.md](./ARCHITECTURE.md) | [ENV.md](../ENV.md)_
