from __future__ import annotations
"""
roles/base.py - 실행 역할 공통 인터페이스
Tool / Agent 핸들러가 구현해야 하는 추상 기반 클래스를 정의한다.
"""
from abc import ABC, abstractmethod
from typing import Generator

from backend.core.models import ExecutionContext


class BaseRoleHandler(ABC):
    """
    실행 역할(Tool / Agent)의 공통 인터페이스.
    run() → 논스트리밍 전체 응답
    stream() → SSE 스트리밍 제너레이터
    """

    @abstractmethod
    def run(self, context: ExecutionContext, user_message: str) -> str:
        """전체 응답을 한 번에 반환한다."""

    @abstractmethod
    def stream(
        self, context: ExecutionContext, user_message: str
    ) -> Generator[str, None, None]:
        """응답 텍스트를 청크 단위로 yield한다."""
