from __future__ import annotations
"""
users/models.py - SQLAlchemy User 모델
docs/USERS_DB.md 기준
"""
from sqlalchemy import Column, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    knox_id  = Column(String(20), primary_key=True)
    name     = Column(String(50), nullable=False)
    team     = Column(String(50))
    eng_name = Column(String(100))

    def to_dict(self) -> dict:
        return {
            "knox_id":  self.knox_id,
            "name":     self.name,
            "team":     self.team,
            "eng_name": self.eng_name,
        }
