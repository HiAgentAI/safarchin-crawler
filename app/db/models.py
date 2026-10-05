import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    client_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), default="standard")
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=60)
    daily_quota: Mapped[int] = mapped_column(Integer, default=1000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    logs: Mapped[list["SearchLog"]] = relationship("SearchLog", back_populates="api_key", cascade="all, delete-orphan")

class SearchLog(Base):
    __tablename__ = "search_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    search_params: Mapped[str] = mapped_column(Text, nullable=False)
    providers_called: Mapped[str] = mapped_column(String(200), default="")
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    api_key: Mapped[Optional["APIKey"]] = relationship("APIKey", back_populates="logs")

class CrawlerHealth(Base):
    __tablename__ = "crawler_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    service_name: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avg_response_time_ms: Mapped[float] = mapped_column(Float, default=0.0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
