"""
backend/main.py - Thin Wrapper (legacy support)

새로운 진입점: app.py (루트)
사용 예:
  - 신규: python app.py
  - 기존: uvicorn backend.main:app

이 파일은 하위호환을 위해 유지됩니다.
"""
from __future__ import annotations

# 루트 app.py에서 앱 가져오기
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app import create_app, settings

# FastAPI 앱 인스턴스 (기존 코드와 호환)
app = create_app()


# 직접 실행 시 (python backend/main.py)
if __name__ == "__main__":
    import uvicorn
    
    print(f"[Legacy] Starting via backend/main.py")
    print(f"[Hint] Consider using 'python app.py' instead")
    
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
